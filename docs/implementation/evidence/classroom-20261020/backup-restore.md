# Synthetic PostgreSQL backup and restore drill

This is an automated test of an isolated synthetic database. It provides no
classroom outcome or teacher approval, and does not certify a school's production
backup policy.

The frozen [validation script](../../../../scripts/validate-postgresql-backup.py)
completed run `e39bb9c7-dd3b-46ca-aa64-87ee863937c1` successfully in **8.379 seconds**.
The [safe report](postgresql-backup-restore.json) records the exact tool/server
versions, script hash, counts, canonical digests, bounds and trigger checks.
Its SHA256 is
`e89705127ebda8cd270cfe6e85f3d2a05bb0e816652addd13af7898b6c7a219a`.
The script SHA256 for that run is
`af10072ec4f5d0ae627cde0063acefad6c13326d07b52782fb8d551d7256798d`.

The input was the completed two-worker browser test database
`quantum_backend_live_browser_20261020_a2`, inside the explicit isolated container
`qa-classroom-trial-postgres-1`. There were no active writers. The script opens a
read-only repeatable-read transaction and shares its `pg_export_snapshot()` with
`pg_dump`, so the reference table hashes and dump use the same snapshot. It
restores the complete custom-format dump into a newly generated
`qa_restore_<UUID>` database, never resetting or writing to the input database.
Only the database created by that invocation can be dropped, with an additional
UUID-name check before cleanup. The report confirms that cleanup succeeded.

Both `pg_dump` and `pg_restore`, and the server, were PostgreSQL **15.19
(Debian 15.19-1.pgdg12+2)**. The restored database matched all 36 tables' row counts
and canonical content hash, schema category hashes and Alembic head `0011`. This
included **15 turns with execution budgets, 11 learning-evidence records, 13 agent
traces and one teacher-review record**. Those are synthetic workflow fixtures;
the review is not approval by an actual teacher. All seven noninternal trigger
definitions were preserved. There are zero native PostgreSQL enum labels: this
schema represents the relevant value restrictions with CHECK constraints, which
are included in the schema verification.

CHECK expressions require one deliberate canonicalization. PostgreSQL 15's
dump/reparse can distribute a varchar-array `::text[]` coercion across individual
elements, changing `pg_get_constraintdef()` text without changing its meaning.
The script compares PostgreSQL's planned projection of each CHECK expression;
constraint identity, validation and deferral flags remain explicit, and
non-CHECK constraint definitions are compared directly. Earlier strict text-hash
attempts correctly failed on this difference; they were not reported as passes.
No source row or SQL dump content is included in the evidence report.

After content and schema comparison, the script verifies that both UPDATE and
DELETE fail with trigger SQLSTATE `P0001` for `learning_evidence`, `agent_traces`,
`teaching_reviews` and `audit_logs`. The source contained no audit rows, so that
last probe uses an explicitly synthetic **restore-only** row, inside a transaction
that is always rolled back. The entire restored database is fingerprinted again
after the probes and must still match the source snapshot. This verifies trigger
behavior rather than merely counting trigger definitions.

The full private archive is **406,158 bytes**, mode **0600**, under the mode0700
directory `/opt/qa-trial/backups`, outside the repository and evidence bundle. It
contains sensitive synthetic authentication hashes and must not be copied into
the source archive. The safe report contains only its size and SHA256
`3e3c5ca6a18dbbfd9d8569584ac71771f6b3e31eb0efe2761bf7f7a64365e56f`.
Its private filename and dump contents are excluded. This drill preserves the
private archives for the operator; it does not implement their retention policy.

To reproduce on the same isolated Linux trial host, with credentials injected
privately and never printed:

```bash
cd /mnt/d/QuantumAgent
PYTHONPATH=services/api /opt/qa-api-env/bin/python scripts/with-trial-environment.py \
  --private-env /opt/qa-trial/private.env -- /opt/qa-api-env/bin/python \
  scripts/validate-postgresql-backup.py
```

The guard requires the explicit source name and a loopback PostgreSQL connection
on port 55432. The whole drill is capped at 600 seconds, individual tools at 120
seconds and SQL statements at 30 seconds; accepted private archives and each
table's streamed hash input are capped at 256 MiB. The script exits nonzero on a
failed comparison, missing fixture, tool failure or cleanup error, without
serializing raw errors. Six [offline safety tests](../../../../scripts/tests/test_postgresql_backup.py)
pass, covering target restrictions, shell argument separation, no credential
expansion into command arguments, bounded subprocesses and safe error reporting:

```bash
services/api/.venv/Scripts/python.exe -m pytest -q scripts/tests/test_postgresql_backup.py
```

Raw safe attempts/logs remain under `outputs/classroom-20261020/`. They preserve
the initial tool-version invocation failure, the raw CHECK-text comparison
failures, and the missing-audit-fixture failure before the successful frozen run.
None was a production outage; none is counted as a successful restore.

This verifies a full database round trip on this PostgreSQL build and synthetic
fixture only. Redis credential-vault restoration and its encryption keys,
off-host durability, global PostgreSQL roles, real-student retention/deletion,
availability under disaster conditions and sequence recovery under concurrent
writers remain unverified. A school deployment still needs its own isolated
restore exercise and authorized retention/key-management procedure.
