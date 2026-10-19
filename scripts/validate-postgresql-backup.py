"""Synthetic full PostgreSQL dump/restore validation; never a production backup claim.

Run on the isolated Linux trial host with credentials injected privately:
  PYTHONPATH=services/api /opt/qa-api-env/bin/python scripts/with-trial-environment.py \
    --private-env /opt/qa-trial/private.env -- /opt/qa-api-env/bin/python \
    scripts/validate-postgresql-backup.py

The only permitted container is qa-classroom-trial-postgres-1. The input database
is read-only, its exported snapshot is shared with pg_dump, and only a new
qa_restore_<UUID> database may be created/dropped. The full archive contains
sensitive auth hashes and stays mode0600 under /opt/qa-trial/backups, outside the
source/evidence bundle. Safe evidence contains counts/digests, never rows or SQL
dump contents. Redis vault, encryption keys, off-host durability and real-student
retention are outside this synthetic verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "qa-classroom-trial-postgres-1"
SOURCE = "quantum_backend_live_browser_20261020_a2"
PRIVATE_ROOT = Path("/opt/qa-trial/backups")
MAX_DUMP_BYTES = 256 * 1024 * 1024


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def docker_command(program: str, *arguments: str) -> list[str]:
    if program not in {"pg_dump", "pg_restore"}:
        raise ValueError("unsupported database program")
    if arguments == ("--version",):
        # These tools recognize --version as their first argument only.
        return ["docker", "exec", CONTAINER, program, "--version"]
    return [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "sh",
        "-c",
        'export PGPASSWORD="$POSTGRES_PASSWORD"; exec "$0" --username="$POSTGRES_USER" "$@"',
        program,
        *arguments,
    ]


def run_command(command: list[str], *, source: Any = None, destination: Any = None) -> bytes:
    result = subprocess.run(
        command,
        stdin=source,
        stdout=destination or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if result.returncode:
        # Do not serialize command/error output; it can contain database rows.
        raise RuntimeError("database_tool_failed")
    return result.stdout or b""


def schema_metadata(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    queries = {
        "columns": "SELECT table_schema,table_name,column_name,ordinal_position,data_type,"
        "udt_schema,udt_name,column_default,is_nullable FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
        "ORDER BY table_schema,table_name,ordinal_position",
        "constraints": "SELECT n.nspname,c.relname,k.conname,k.contype,k.condeferrable,"
        "k.condeferred,k.convalidated,pg_get_constraintdef(k.oid),"
        "pg_get_expr(k.conbin,k.conrelid) "
        "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' "
        "ORDER BY n.nspname,c.relname,k.conname",
        "indexes": "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes "
        "WHERE schemaname !~ '^pg_' AND schemaname<>'information_schema' "
        "ORDER BY schemaname,tablename,indexname",
        "triggers": "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid) "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal "
        "AND n.nspname !~ '^pg_' AND n.nspname<>'information_schema' "
        "ORDER BY n.nspname,c.relname,t.tgname",
        "enums": "SELECT n.nspname,t.typname,e.enumsortorder,e.enumlabel "
        "FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid "
        "JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname !~ '^pg_' ORDER BY n.nspname,t.typname,e.enumsortorder",
        "extensions": "SELECT e.extname,e.extversion,n.nspname FROM pg_extension e "
        "JOIN pg_namespace n ON n.oid=e.extnamespace ORDER BY e.extname",
        "functions": "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),"
        "pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND p.prokind<>'a' "
        "ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)",
        "sequences": "SELECT schemaname,sequencename,data_type,start_value,min_value,max_value,"
        "increment_by,cycle,last_value FROM pg_sequences WHERE schemaname !~ '^pg_' "
        "ORDER BY schemaname,sequencename",
    }
    metadata = {name: connection.execute(query).fetchall() for name, query in queries.items()}
    constraints = []
    # PostgreSQL15 reparses varchar-array CHECK casts when restoring: one
    # array-wide ::text[] coercion becomes element-wise ::text coercions. Use
    # the server's planned projection to compare these equivalent expressions,
    # preserving identity, validation/deferral flags and every non-CHECK DDL.
    # EXPLAIN does not read rows; only its Output expression is retained/hashable.
    connection.execute("SET LOCAL max_parallel_workers_per_gather=0")
    for row in metadata["constraints"]:
        definition = row[7]
        if row[3] == "c":
            explained = connection.execute(
                sql.SQL("EXPLAIN (FORMAT JSON,VERBOSE,COSTS OFF) SELECT ({}) FROM {}.{}").format(
                    sql.SQL(row[8]), sql.Identifier(row[0]), sql.Identifier(row[1])
                )
            ).fetchone()
            if not explained:
                raise ValueError("check_constraint_plan_unavailable")
            definition = explained[0][0]["Plan"]["Output"]
        constraints.append((*row[:7], definition))
    metadata["constraints"] = constraints
    return metadata


def fingerprint(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    tables = connection.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname !~ '^pg_' "
        "AND schemaname<>'information_schema' ORDER BY schemaname,tablename"
    ).fetchall()
    hashes = {}
    for schema, table in tables:
        aggregate = hashlib.sha256()
        count, total = 0, 0
        with connection.cursor(name="backup_hash_" + uuid4().hex) as cursor:
            cursor.itersize = 128
            cursor.execute(
                sql.SQL(
                    'SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text COLLATE "C"'
                ).format(sql.Identifier(schema), sql.Identifier(table))
            )
            for row in cursor:
                raw = row[0].encode("utf-8")
                total += len(raw)
                if total > MAX_DUMP_BYTES:
                    raise ValueError("synthetic_table_size_limit")
                aggregate.update(len(raw).to_bytes(8, "big"))
                aggregate.update(raw)
                count += 1
        hashes[schema + "." + table] = {"rows": count, "sha256": aggregate.hexdigest()}
    metadata = schema_metadata(connection)
    head = connection.execute(
        "SELECT version_num FROM alembic_version ORDER BY version_num"
    ).fetchall()
    budgets = connection.execute(
        "SELECT count(*) FROM teaching_turns WHERE execution_budget_json<>'{}'::jsonb"
    ).fetchone()
    return {
        "tables": hashes,
        "schema_sha256": digest(metadata),
        "schema_categories": {name: digest(rows) for name, rows in metadata.items()},
        "alembic_head": head,
        "enum_sha256": digest(metadata["enums"]),
        "enum_labels": len(metadata["enums"]),
        "trigger_definitions": len(metadata["triggers"]),
        "budget_turns": budgets[0] if budgets else 0,
    }


def verify_append_only(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    results = {}
    for table, field in (
        ("learning_evidence", "observation"),
        ("agent_traces", "workflow_version"),
        ("teaching_reviews", "reason"),
        ("audit_logs", "id"),
    ):
        with connection.transaction(force_rollback=True):
            row = connection.execute(
                sql.SQL("SELECT id FROM {} LIMIT 1").format(sql.Identifier(table))
            ).fetchone()
            synthetic = False
            if row is None and table == "audit_logs":
                identity = uuid4()
                connection.execute(
                    "INSERT INTO audit_logs (id,event_type,resource_type,summary) "
                    "VALUES (%s,'settings_changed','course',%s)",
                    (identity, "Synthetic restore-only append-only trigger probe; rolled back"),
                )
                row = (identity,)
                synthetic = True
            if row is None and table == "teaching_reviews":
                # Restore-only fixture, explicitly rolled back after checking
                # the restored review trigger. Never write to the source.
                context = connection.execute(
                    "SELECT c.course_id,c.curriculum_edition_id,c.id,c.student_user_id,t.id "
                    "FROM teaching_conversations c JOIN teaching_turns t ON t.conversation_id=c.id "
                    "WHERE t.status='completed' LIMIT 1"
                ).fetchone()
                reviewer = (
                    connection.execute(
                        "SELECT user_id FROM course_memberships WHERE course_id=%s "
                        "AND role IN ('teacher','admin') LIMIT 1",
                        (context[0],),
                    ).fetchone()
                    if context
                    else None
                )
                if context and reviewer:
                    identity = uuid4()
                    connection.execute(
                        "INSERT INTO teaching_reviews "
                        "(id,course_id,curriculum_edition_id,conversation_id,student_user_id,"
                        "source_turn_id,reviewer_user_id,decision,reason,follow_up) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,'needs_follow_up',%s,'continue')",
                        (
                            identity,
                            *context[:4],
                            context[4],
                            reviewer[0],
                            "Synthetic restore-only trigger test; never actual teacher approval",
                        ),
                    )
                    row = (identity,)
                    synthetic = True
            if row is None:
                raise ValueError("missing_append_only_fixture")
            checks = {}
            for operation in ("UPDATE", "DELETE"):
                statement = (
                    sql.SQL("UPDATE {} SET {}={} WHERE id=%s").format(
                        sql.Identifier(table), sql.Identifier(field), sql.Identifier(field)
                    )
                    if operation == "UPDATE"
                    else sql.SQL("DELETE FROM {} WHERE id=%s").format(sql.Identifier(table))
                )
                try:
                    with connection.transaction():
                        connection.execute(statement, (row[0],))
                except psycopg.Error as exc:
                    checks[operation.casefold()] = exc.sqlstate == "P0001"
                else:
                    checks[operation.casefold()] = False
            if not all(checks.values()):
                raise ValueError("append_only_trigger_not_enforced")
            results[table] = {**checks, "restore_only_rolled_back_fixture": synthetic}
    return results


def validate(report: dict[str, Any], *, source_database: str, archive: Path) -> None:
    url = make_url(os.environ["DATABASE_URL"])
    if (
        source_database != SOURCE
        or url.drivername != "postgresql+asyncpg"
        or "backend_live" not in (url.database or "")
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 55432
    ):
        raise ValueError("isolated_trial_database_required")
    options: dict[str, Any] = {
        "user": url.username,
        "password": url.password,
        "host": url.host,
        "port": url.port,
        "connect_timeout": 10,
        "autocommit": True,
        "options": "-c statement_timeout=30000",
    }
    restore_database = "qa_restore_" + uuid4().hex
    created = False
    config = Config(str(ROOT / "services/api/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    report["tools"] = {
        tool: run_command(docker_command(tool, "--version")).decode().strip()
        for tool in ("pg_dump", "pg_restore")
    }
    with psycopg.connect(dbname="postgres", **options) as admin:
        version_row = admin.execute("SHOW server_version").fetchone()
        if version_row is None:
            raise ValueError("server_version_unavailable")
        report["server_version"] = version_row[0]
        try:
            report["stage"] = "source_snapshot_and_dump"
            with (
                psycopg.connect(dbname=source_database, **options) as source,
                source.transaction(),
            ):
                source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                snapshot_row = source.execute("SELECT pg_export_snapshot()").fetchone()
                if snapshot_row is None:
                    raise ValueError("snapshot_unavailable")
                snapshot = snapshot_row[0]
                report["source_snapshot"] = fingerprint(source)
                if report["source_snapshot"]["alembic_head"] != [(expected_head,)]:
                    raise ValueError("source_migration_head_mismatch")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                with os.fdopen(os.open(archive, flags, 0o600), "wb") as target:
                    run_command(
                        docker_command(
                            "pg_dump",
                            "--format=custom",
                            "--no-password",
                            "--dbname=" + source_database,
                            "--snapshot=" + snapshot,
                        ),
                        destination=target,
                    )
            size = archive.stat().st_size
            if size <= 0 or size > MAX_DUMP_BYTES or archive.stat().st_mode & 0o777 != 0o600:
                raise ValueError("private_archive_envelope_failed")
            with archive.open("rb") as private_file:
                archive_digest = hashlib.file_digest(private_file, "sha256").hexdigest()
            report["private_archive"] = {
                "bytes": size,
                "sha256": archive_digest,
                "mode": "0600",
                "excluded_from_source_and_evidence_bundle": True,
            }
            admin.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(restore_database)
                )
            )
            created = True
            report["stage"] = "restore_new_database"
            with archive.open("rb") as source_file:
                run_command(
                    docker_command(
                        "pg_restore",
                        "--no-password",
                        "--exit-on-error",
                        "--single-transaction",
                        "--dbname=" + restore_database,
                    ),
                    source=source_file,
                )
            with psycopg.connect(dbname=restore_database, **options) as restored:
                with restored.transaction():
                    restored.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                    report["restored_snapshot"] = fingerprint(restored)
                report["stage"] = "compare_snapshot_fingerprints"
                if report["restored_snapshot"] != report["source_snapshot"]:
                    raise ValueError("snapshot_fingerprint_mismatch")
                report["stage"] = "restored_append_only_triggers"
                report["append_only_checks"] = verify_append_only(restored)
                with restored.transaction():
                    restored.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                    if fingerprint(restored) != report["source_snapshot"]:
                        raise ValueError("trigger_probe_changed_restored_data")
            report["snapshot_matches_dump_and_restore"] = True
            report["stage"] = "completed"
        finally:
            if created:
                if not re.fullmatch(r"qa_restore_[a-f0-9]{32}", restore_database):
                    raise ValueError("restore_cleanup_identity_rejected")
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(restore_database)
                    )
                )
                report["restore_database_removed"] = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-database", default=SOURCE)
    args = parser.parse_args()
    if args.source_database != SOURCE or os.name != "posix":
        raise ValueError("only_explicit_isolated_linux_source_is_permitted")
    run_id = str(uuid4())
    output = ROOT / "outputs/classroom-20261020" / ("postgresql-backup-restore-" + run_id + ".json")
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if PRIVATE_ROOT.resolve() != PRIVATE_ROOT:
        raise ValueError("private_backup_directory_must_not_be_a_symlink")
    os.chmod(PRIVATE_ROOT, 0o700)
    archive = PRIVATE_ROOT / (run_id + ".dump")
    report: dict[str, Any] = {
        "schema_version": "synthetic-postgresql-backup-restore/1",
        "run_id": run_id,
        "label": "SYNTHETIC ISOLATED RESTORE TEST; NO PRODUCTION/CLASSROOM RECOVERY CLAIM",
        "started_at": datetime.now(UTC).isoformat(),
        "source_database": SOURCE,
        "container": CONTAINER,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "snapshot_method": "pg_export_snapshot shared with read-only fingerprint and pg_dump",
        "check_constraint_comparison": "PostgreSQL planned projection (array coercion canonicalized); "
        "identity/validation/deferral flags and non-CHECK definitions preserved",
        "limits": {
            "tool_seconds_each": 120,
            "sql_statement_seconds": 30,
            "private_archive_bytes": MAX_DUMP_BYTES,
            "total_seconds": 600,
        },
        "not_certified": [
            "Redis credential vault or encryption-key restore",
            "off-host backups",
            "roles/global cluster restore",
            "real-student retention/deletion policy",
            "availability or live-writer sequence recovery",
        ],
    }
    started = time.monotonic()

    def deadline(signum: int, frame: Any) -> None:
        raise TimeoutError("synthetic_backup_deadline")

    signum = getattr(signal, "SIGALRM", None)
    alarm = getattr(signal, "alarm", None)
    if signum is None or alarm is None:
        raise ValueError("linux_deadline_signal_unavailable")
    signal.signal(signum, deadline)
    alarm(600)
    try:
        validate(report, source_database=args.source_database, archive=archive)
        report["passed"] = True
    except Exception as exc:  # noqa: BLE001 -- persist a safe failure, never raw database errors
        report["passed"] = False
        report["failure_type"] = type(exc).__name__
        # Never retain exception text/rows/SQL dump contents or credential values.
    finally:
        alarm(0)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["completed_at"] = datetime.now(UTC).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"report": str(output), "passed": report["passed"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
