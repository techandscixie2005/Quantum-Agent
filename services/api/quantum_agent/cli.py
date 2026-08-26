"""Operational commands for the knowledge-model backend."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from alembic.config import Config as AlembicConfig
from sqlalchemy import select

from alembic import command
from quantum_agent.auth import (
    CourseActor,
    hash_session_token,
    issue_opaque_session_token,
)
from quantum_agent.config import Settings
from quantum_agent.database import create_database_engine, create_session_factory
from quantum_agent.db_models import (
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    MembershipStatus,
    SessionStatus,
    SystemRole,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.gateways import (
    build_embedding_gateway,
    build_graph_store,
    build_model_gateway,
    build_vision_gateway,
)
from quantum_agent.knowledge.graph_sync import GraphOutboxWorker
from quantum_agent.knowledge.pipeline import CourseKnowledgePipeline, ingest_course_manifest
from quantum_agent.knowledge.review import ReviewService

API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "content" / "quantum_course" / "manifest.toml"
LIVE_E2E_STUDENT_EMAIL = "live-e2e-student@quantum-agent.invalid"
LIVE_E2E_TA_EMAIL = "live-e2e-ta@quantum-agent.invalid"


def _json_output(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _migrate(_: argparse.Namespace) -> int:
    config = AlembicConfig(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(config, "head")
    _json_output({"migration": "head", "status": "complete"})
    return 0


async def _ingest_async(arguments: argparse.Namespace) -> int:
    settings = Settings()
    embedding = build_embedding_gateway(settings)
    if embedding is None:
        raise RuntimeError(
            "Ingestion requires EMBEDDING_PROVIDER=local_hashing or openai_compatible"
        )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            try:
                report = await ingest_course_manifest(
                    session,
                    manifest_path=Path(arguments.manifest),
                    repository_root=REPOSITORY_ROOT,
                    embedding_gateway=embedding,
                )
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
        _json_output(
            {
                "status": "complete",
                "course_id": str(report.course_id),
                "documents": report.document_count,
                "versions": report.version_count,
                "chunks": report.chunk_count,
                "evidence": report.evidence_count,
                "node_candidates": report.node_candidate_count,
                "relation_candidates": report.relation_candidate_count,
                "student_visible_chunks": report.student_visible_chunk_count,
                "embedding_provider": report.embedding.provider,
                "embedding_mode": report.embedding.retrieval_mode,
                "curriculum_editions": {
                    key: str(value) for key, value in report.curriculum_edition_ids.items()
                },
            }
        )
        return 0
    finally:
        await engine.dispose()


def _ingest(arguments: argparse.Namespace) -> int:
    arguments.manifest = str(Path(arguments.manifest).resolve())
    return asyncio.run(_ingest_async(arguments))


async def _sync_graph_async(arguments: argparse.Namespace) -> int:
    settings = Settings()
    graph_store = build_graph_store(settings)
    if graph_store is None:
        raise RuntimeError("NEO4J_PASSWORD is required for graph synchronization")
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    worker = GraphOutboxWorker(
        session_factory=session_factory,
        graph_store=graph_store,
        worker_id=arguments.worker_id,
    )
    processed = 0
    try:
        await graph_store.ensure_schema()
        if not arguments.watch:
            processed = await worker.run_batch(limit=arguments.limit)
        else:
            while True:
                batch = await worker.run_batch(limit=arguments.limit)
                processed += batch
                if batch == 0:
                    await asyncio.sleep(arguments.poll_seconds)
        _json_output({"status": "complete", "processed": processed})
        return 0
    finally:
        await graph_store.close()
        await engine.dispose()


def _sync_graph(arguments: argparse.Namespace) -> int:
    return asyncio.run(_sync_graph_async(arguments))


async def _probe_model_async(_: argparse.Namespace) -> int:
    gateway = build_model_gateway(Settings())
    if gateway is None:
        raise RuntimeError("USTC_API is not configured")
    capabilities = await gateway.probe()
    _json_output(capabilities.model_dump(mode="json"))
    return 0 if capabilities.chat_completions else 2


def _probe_model(arguments: argparse.Namespace) -> int:
    return asyncio.run(_probe_model_async(arguments))


async def _probe_embedding_async(_: argparse.Namespace) -> int:
    gateway = build_embedding_gateway(Settings())
    if gateway is None:
        _json_output({"available": False, "provider": "disabled"})
        return 2
    probe = await gateway.probe()
    _json_output(probe.model_dump(mode="json"))
    return 0 if probe.available else 2


def _probe_embedding(arguments: argparse.Namespace) -> int:
    return asyncio.run(_probe_embedding_async(arguments))


async def _probe_live_model_async(_: argparse.Namespace) -> int:
    """Exercise representative USTC capabilities with retry, surfacing model/latency/status.

    This is the PRD V3.0 §18 live smoke check.  It spends real tokens on a
    small deep-reasoning call, a small lightweight call, and (when configured)
    a vision call and an embedding call.  Transient failures (timeout, 429,
    5xx) are retried with bounded backoff; auth/config 4xx are not.  The
    output never includes the API key.
    """

    import time

    from quantum_agent.llm.gateway import GatewayError, Message, ModelTier
    from quantum_agent.teaching.learning_native import (
        propose_commitment,
    )
    from quantum_agent.teaching.models import InterpretationOutput

    settings = Settings()
    gateway = build_model_gateway(settings)
    if gateway is None:
        _json_output({"available": False, "reason": "USTC_API not configured"})
        return 2

    report: dict[str, Any] = {"available": True, "checks": []}

    async def _check(name: str, coro_factory: Any) -> None:
        start = time.perf_counter()
        entry: dict[str, Any] = {"name": name, "status": "unknown"}
        try:
            result = await coro_factory()
            elapsed = time.perf_counter() - start
            entry["status"] = "success"
            entry["latency_seconds"] = round(elapsed, 3)
            entry["result_type"] = type(result).__name__ if result is not None else "None"
        except GatewayError as exc:
            elapsed = time.perf_counter() - start
            entry["status"] = "gateway_error"
            entry["latency_seconds"] = round(elapsed, 3)
            entry["error"] = str(exc)[:200]
        except Exception as exc:
            elapsed = time.perf_counter() - start
            entry["status"] = "error"
            entry["latency_seconds"] = round(elapsed, 3)
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        report["checks"].append(entry)

    # 1. Deep reasoning / tutoring capability.
    await _check(
        "deep_reasoning_interpret",
        lambda: gateway.structured_generate(
            task="interpret_teaching_turn",
            messages=[
                Message(
                    role="system",
                    content="Classify the student request only. Do not answer it.",
                ),
                Message(role="user", content="什么是量子隧穿？"),
            ],
            output_type=InterpretationOutput,
            model_tier=ModelTier.DEFAULT,
        ),
    )

    # 2. Lightweight / commitment proposal capability.
    await _check(
        "lightweight_commitment_proposal",
        lambda: propose_commitment(
            message="为什么 E<V0 时仍可能透射？",
            release_is_question_only=True,
            model_gateway=gateway,
        ),
    )

    # 3. Embedding capability (separately configured).
    embedding_gateway = build_embedding_gateway(settings)
    if embedding_gateway is not None:
        await _check(
            "embedding_probe",
            lambda: embedding_gateway.probe(),
        )
    else:
        report["checks"].append(
            {"name": "embedding_probe", "status": "skipped", "reason": "not configured"}
        )

    # 4. Rerank capability is optional; skip when not separately configured.
    report["checks"].append(
        {"name": "rerank_probe", "status": "skipped", "reason": "not separately configured"}
    )

    successes = sum(1 for c in report["checks"] if c.get("status") == "success")
    report["summary"] = {
        "total": len(report["checks"]),
        "successes": successes,
        "failures": sum(1 for c in report["checks"] if c.get("status") == "gateway_error"),
        "errors": sum(1 for c in report["checks"] if c.get("status") == "error"),
        "skipped": sum(1 for c in report["checks"] if c.get("status") == "skipped"),
    }
    _json_output(report)
    # Non-zero exit only when every required check failed (no successes at all
    # on the two chat capabilities).
    if successes == 0:
        return 2
    return 0


def _probe_live_model(arguments: argparse.Namespace) -> int:
    return asyncio.run(_probe_live_model_async(arguments))


async def _teacher_actor(
    session: Any,
    *,
    course_id: UUID,
) -> CourseActor:
    """Load or seed a teacher actor for operational governance commands."""
    user = (
        await session.scalars(
            select(User).where(User.email == "ops-teacher@example.edu").limit(1)
        )
    ).first()
    if user is None:
        user = User(
            email="ops-teacher@example.edu",
            display_name="Operations Teacher",
            system_role=SystemRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()
    membership = (
        await session.scalars(
            select(CourseMembership)
            .where(
                CourseMembership.user_id == user.id,
                CourseMembership.course_id == course_id,
            )
            .limit(1)
        )
    ).first()
    if membership is None:
        membership = CourseMembership(
            course_id=course_id,
            user_id=user.id,
            role=CourseRole.TEACHER,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
        await session.flush()
    now = datetime.now(UTC)
    user_session = UserSession(
        user_id=user.id,
        session_token_sha256=hash_session_token(issue_opaque_session_token()),
        status=SessionStatus.ACTIVE,
        expires_at=now + timedelta(hours=2),
    )
    session.add(user_session)
    await session.flush()
    return CourseActor(
        user_id=user.id,
        session_id=user_session.id,
        course_id=course_id,
        email=user.email,
        display_name=user.display_name,
        system_role=user.system_role,
        course_role=membership.role,
    )


async def _publish_documents_async(arguments: argparse.Namespace) -> int:
    settings = Settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    version_ids = [
        UUID(token) for token in arguments.document_version_ids.split(",") if token.strip()
    ]
    published: list[dict[str, Any]] = []
    try:
        async with session_factory() as session:
            actor = await _teacher_actor(session, course_id=UUID(arguments.course_id))
            review = ReviewService(session)
            for version_id in version_ids:
                await review.approve_document_version(
                    actor=actor,
                    curriculum_edition_id=UUID(arguments.edition_id),
                    document_version_id=version_id,
                    rationale=arguments.rationale,
                )
                await session.flush()
                publication = await review.publish_document_version(
                    actor=actor,
                    curriculum_edition_id=UUID(arguments.edition_id),
                    document_version_id=version_id,
                    rationale=arguments.rationale,
                    priority=arguments.priority,
                )
                published.append(
                    {
                        "document_version_id": str(version_id),
                        "published": True,
                        "student_visible": True,
                        "priority": publication.priority,
                    }
                )
            await session.commit()
        _json_output({"status": "complete", "published": published})
        return 0
    except BaseException:
        raise
    finally:
        await engine.dispose()


def _publish_documents(arguments: argparse.Namespace) -> int:
    return asyncio.run(_publish_documents_async(arguments))


async def _ocr_textbook_async(arguments: argparse.Namespace) -> int:
    settings = Settings()
    vision_gateway = build_vision_gateway(settings)
    if vision_gateway is None:
        raise RuntimeError("USTC_API is required for vision OCR")
    embedding = build_embedding_gateway(settings)
    if embedding is None:
        raise RuntimeError("Embedding gateway is required for ingestion")

    async def transcribe(image_bytes: bytes) -> str:
        return await vision_gateway.transcribe(image_bytes=image_bytes, mime_type="image/png")

    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    manifest_path = Path(arguments.manifest)
    pipeline = CourseKnowledgePipeline(embedding_gateway=embedding)
    try:
        async with session_factory() as session:
            report = await pipeline.reprocess_scanned_source(
                session,
                manifest_path=manifest_path,
                repository_root=REPOSITORY_ROOT,
                source_path=arguments.source,
                transcribe=transcribe,
                render_dpi=arguments.render_dpi,
            )
            await session.commit()
        _json_output(
            {
                "status": "complete",
                "document_version_id": str(report.document_version_id),
                "parsed_chunks": report.parsed_chunks,
                "persisted_chunks": report.persisted_chunks,
                "persisted_evidence": report.persisted_evidence,
                "statuses": report.statuses,
            }
        )
        return 0
    except BaseException:
        raise
    finally:
        await engine.dispose()


def _ocr_textbook(arguments: argparse.Namespace) -> int:
    arguments.manifest = str(Path(arguments.manifest).resolve())
    return asyncio.run(_ocr_textbook_async(arguments))


def _write_private_json(path: Path, value: dict[str, str]) -> None:
    """Create a credential artifact without ever sending its contents to stdout."""

    resolved = path.expanduser().resolve()
    if not resolved.parent.is_dir():
        raise ValueError("The live-E2E output directory must already exist")
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise


async def _seed_live_e2e_async(arguments: argparse.Namespace) -> int:
    """Seed bounded development identities used by the real Playwright workflow."""

    settings = Settings()
    if settings.environment == "production":
        raise RuntimeError("Live-E2E identities cannot be seeded in production")
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    now = datetime.now(UTC)
    try:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Course, CurriculumEdition)
                    .join(CurriculumEdition, CurriculumEdition.course_id == Course.id)
                    .where(CurriculumEdition.status == CurriculumEditionStatus.PUBLISHED)
                    .order_by(
                        (Course.status == CourseStatus.ACTIVE).desc(),
                        CurriculumEdition.published_at.desc(),
                        CurriculumEdition.id.asc(),
                    )
                    .limit(1)
                )
            ).one_or_none()
            if row is None:
                raise RuntimeError("A published curriculum edition is required for live E2E")
            course, edition = row
            if course.status != CourseStatus.ACTIVE:
                if not arguments.activate_course:
                    raise RuntimeError(
                        "The selected course is not active; pass --activate-course explicitly"
                    )
                course.status = CourseStatus.ACTIVE

            seeded: dict[CourseRole, tuple[User, str]] = {}
            for role, email, display_name in (
                (CourseRole.STUDENT, LIVE_E2E_STUDENT_EMAIL, "Live E2E Student"),
                (CourseRole.TA, LIVE_E2E_TA_EMAIL, "Live E2E TA"),
            ):
                user = await session.scalar(select(User).where(User.email == email).limit(1))
                if user is None:
                    user = User(
                        email=email,
                        display_name=display_name,
                        system_role=SystemRole.USER,
                        status=UserStatus.ACTIVE,
                    )
                    session.add(user)
                    await session.flush()
                else:
                    user.display_name = display_name
                    user.status = UserStatus.ACTIVE
                membership = await session.scalar(
                    select(CourseMembership)
                    .where(
                        CourseMembership.course_id == course.id,
                        CourseMembership.user_id == user.id,
                    )
                    .limit(1)
                )
                if membership is None:
                    membership = CourseMembership(
                        course_id=course.id,
                        user_id=user.id,
                        role=role,
                        status=MembershipStatus.ACTIVE,
                        joined_at=now,
                    )
                    session.add(membership)
                else:
                    membership.role = role
                    membership.status = MembershipStatus.ACTIVE
                    membership.joined_at = membership.joined_at or now
                    membership.ended_at = None
                raw_token = issue_opaque_session_token()
                session.add(
                    UserSession(
                        user_id=user.id,
                        session_token_sha256=hash_session_token(raw_token),
                        status=SessionStatus.ACTIVE,
                        expires_at=now + timedelta(hours=arguments.expires_hours),
                        user_agent="quantum-agent-live-e2e",
                    )
                )
                seeded[role] = (user, raw_token)
            await session.commit()

        student, student_token = seeded[CourseRole.STUDENT]
        ta, ta_token = seeded[CourseRole.TA]
        _write_private_json(
            Path(arguments.output),
            {
                "course_id": str(course.id),
                "curriculum_edition_id": str(edition.id),
                "student_user_id": str(student.id),
                "student_token": student_token,
                "ta_user_id": str(ta.id),
                "ta_token": ta_token,
            },
        )
        _json_output(
            {
                "status": "complete",
                "credential_output": arguments.output,
                "course_activated": bool(arguments.activate_course),
            }
        )
        return 0
    finally:
        await engine.dispose()


def _seed_live_e2e(arguments: argparse.Namespace) -> int:
    arguments.output = str(Path(arguments.output).expanduser().resolve())
    return asyncio.run(_seed_live_e2e_async(arguments))


async def _seed_demo_account_async(arguments: argparse.Namespace) -> int:
    """Seed the competition demo student account (PRD V3.0 P1-4).

    Creates (or re-activates) the demo student with an active membership in
    the first active published course, so a judge can POST
    ``/api/v1/auth/demo-login`` with the shared ``DEMO_LOGIN_SECRET`` to
    receive a ``qa_session`` cookie without manual SQL.  No session token is
    issued here — the demo-login endpoint mints one on demand.
    """

    settings = Settings()
    if settings.environment == "production":
        raise RuntimeError("Demo accounts cannot be seeded in production")
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    now = datetime.now(UTC)
    email = settings.demo_login_course_email
    try:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Course, CurriculumEdition)
                    .join(CurriculumEdition, CurriculumEdition.course_id == Course.id)
                    .where(CurriculumEdition.status == CurriculumEditionStatus.PUBLISHED)
                    .order_by(
                        (Course.status == CourseStatus.ACTIVE).desc(),
                        CurriculumEdition.published_at.desc(),
                        CurriculumEdition.id.asc(),
                    )
                    .limit(1)
                )
            ).one_or_none()
            if row is None:
                raise RuntimeError(
                    "A published curriculum edition is required for the demo account"
                )
            course, edition = row
            if course.status != CourseStatus.ACTIVE:
                if not arguments.activate_course:
                    raise RuntimeError(
                        "The selected course is not active; pass --activate-course explicitly"
                    )
                course.status = CourseStatus.ACTIVE

            user = await session.scalar(select(User).where(User.email == email).limit(1))
            if user is None:
                user = User(
                    email=email,
                    display_name="Competition Demo Student",
                    system_role=SystemRole.USER,
                    status=UserStatus.ACTIVE,
                )
                session.add(user)
                await session.flush()
            else:
                user.display_name = "Competition Demo Student"
                user.status = UserStatus.ACTIVE
            membership = await session.scalar(
                select(CourseMembership)
                .where(
                    CourseMembership.course_id == course.id,
                    CourseMembership.user_id == user.id,
                )
                .limit(1)
            )
            if membership is None:
                membership = CourseMembership(
                    course_id=course.id,
                    user_id=user.id,
                    role=CourseRole.STUDENT,
                    status=MembershipStatus.ACTIVE,
                    joined_at=now,
                )
                session.add(membership)
            else:
                membership.role = CourseRole.STUDENT
                membership.status = MembershipStatus.ACTIVE
                membership.joined_at = membership.joined_at or now
                membership.ended_at = None
            await session.commit()

        _json_output(
            {
                "status": "complete",
                "demo_email": email,
                "course_id": str(course.id),
                "curriculum_edition_id": str(edition.id),
                "course_activated": bool(arguments.activate_course),
                "next_step": (
                    "POST /api/v1/auth/demo-login with the DEMO_LOGIN_SECRET "
                    "to receive a session token."
                ),
            }
        )
        return 0
    finally:
        await engine.dispose()


def _seed_demo_account(arguments: argparse.Namespace) -> int:
    return asyncio.run(_seed_demo_account_async(arguments))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantum-agent")
    commands = parser.add_subparsers(dest="command", required=True)

    migrate = commands.add_parser("migrate", help="upgrade the authoritative database")
    migrate.set_defaults(handler=_migrate)

    ingest = commands.add_parser("ingest", help="verify and ingest the course manifest")
    ingest.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ingest.set_defaults(handler=_ingest)

    graph = commands.add_parser("sync-graph", help="dispatch approved graph outbox events")
    graph.add_argument("--limit", type=int, default=100)
    graph.add_argument("--worker-id", default=None)
    graph.add_argument("--watch", action="store_true")
    graph.add_argument("--poll-seconds", type=float, default=2.0)
    graph.set_defaults(handler=_sync_graph)

    model_probe = commands.add_parser("probe-model", help="test observed USTC chat capabilities")
    model_probe.set_defaults(handler=_probe_model)

    embedding_probe = commands.add_parser(
        "probe-embedding", help="test the separately configured embedding provider"
    )
    embedding_probe.set_defaults(handler=_probe_embedding)

    live_model_probe = commands.add_parser(
        "probe-live-model",
        help="exercise representative USTC capabilities with retry (live smoke)",
    )
    live_model_probe.set_defaults(handler=_probe_live_model)

    publish = commands.add_parser(
        "publish-documents", help="approve then publish document versions (teacher governance)"
    )
    publish.add_argument("--course-id", required=True)
    publish.add_argument("--edition-id", required=True)
    publish.add_argument("--document-version-ids", required=True, help="comma-separated UUIDs")
    publish.add_argument("--priority", type=int, default=50)
    publish.add_argument(
        "--rationale", default="Operational publication of grounded narrative evidence"
    )
    publish.set_defaults(handler=_publish_documents)

    ocr = commands.add_parser(
        "ocr-textbook", help="OCR a scanned textbook source via the vision model"
    )
    ocr.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ocr.add_argument("--source", required=True, help="manifest source path, e.g. the scanned PDF")
    ocr.add_argument("--render-dpi", type=int, default=120)
    ocr.set_defaults(handler=_ocr_textbook)

    live_e2e = commands.add_parser(
        "seed-live-e2e",
        help="seed development-only student/TA sessions into a mode-0600 JSON file",
    )
    live_e2e.add_argument("--output", required=True)
    live_e2e.add_argument("--expires-hours", type=int, default=2)
    live_e2e.add_argument("--activate-course", action="store_true")
    live_e2e.set_defaults(handler=_seed_live_e2e)

    demo = commands.add_parser(
        "seed-demo-account",
        help="seed the competition demo student account for /api/v1/auth/demo-login",
    )
    demo.add_argument("--activate-course", action="store_true")
    demo.set_defaults(handler=_seed_demo_account)
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    if arguments.command == "sync-graph":
        if not 1 <= arguments.limit <= 1000:
            parser.error("--limit must be between 1 and 1000")
        if not 0.1 <= arguments.poll_seconds <= 300:
            parser.error("--poll-seconds must be between 0.1 and 300")
    if arguments.command == "seed-live-e2e" and not 1 <= arguments.expires_hours <= 24:
        parser.error("--expires-hours must be between 1 and 24")
    try:
        return int(arguments.handler(arguments))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        _json_output({"status": "error", "error": type(error).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
