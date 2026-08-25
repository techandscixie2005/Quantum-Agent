from __future__ import annotations

# Exact course labels intentionally preserve Chinese punctuation.
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from quantum_agent.auth import CourseActor, hash_session_token, issue_opaque_session_token
from quantum_agent.database import create_session_factory
from quantum_agent.db_models import (
    CourseMembership,
    CourseRole,
    GraphNodeCandidate,
    MembershipStatus,
    SourceDocument,
    SourceDocumentVersion,
    SystemRole,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.knowledge.evidence_packets import (
    LocatorType,
    RetrievalChannel,
    RetrievalCoverage,
)
from quantum_agent.knowledge.graph_store import InMemoryGraphStore
from quantum_agent.knowledge.graph_sync import GraphOutboxWorker
from quantum_agent.knowledge.pipeline import ingest_course_manifest
from quantum_agent.knowledge.retrieval import (
    HybridEvidenceRetriever,
    RetrievalScope,
    StudentVisibleEvidenceRepository,
)
from quantum_agent.knowledge.review import ReviewService
from quantum_agent.llm.embeddings import HashingEmbeddingGateway

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "content" / "quantum_course" / "manifest.toml"


def _require_real_materials() -> None:
    if not (REPOSITORY_ROOT / "knowledge").is_dir():
        pytest.skip("private course materials are not mounted")


async def test_real_material_reaches_review_graph_and_hybrid_evidence_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase-1 smoke: real XLSX -> review -> graph -> cited retrieval."""

    _require_real_materials()
    database_path = tmp_path / "phase1-real.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    alembic_config = Config(str(API_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(API_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    engine = create_async_engine(database_url)
    session_factory = create_session_factory(engine)
    embedding = HashingEmbeddingGateway()
    try:
        async with session_factory() as session:
            report = await ingest_course_manifest(
                session,
                manifest_path=MANIFEST_PATH,
                repository_root=REPOSITORY_ROOT,
                embedding_gateway=embedding,
            )
            await session.commit()

        taxonomy_edition_id = report.curriculum_edition_ids["lecture-decks-2022"]
        async with session_factory() as session:
            user = User(
                email="phase1-smoke-teacher@example.edu",
                display_name="Phase 1 smoke teacher",
                system_role=SystemRole.USER,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.flush()
            raw_token = issue_opaque_session_token()
            user_session = UserSession(
                user_id=user.id,
                session_token_sha256=hash_session_token(raw_token),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            membership = CourseMembership(
                course_id=report.course_id,
                user_id=user.id,
                role=CourseRole.TEACHER,
                status=MembershipStatus.ACTIVE,
                joined_at=datetime.now(UTC),
            )
            session.add_all([user_session, membership])
            await session.flush()
            actor = CourseActor(
                user_id=user.id,
                session_id=user_session.id,
                course_id=report.course_id,
                email=user.email,
                display_name=user.display_name,
                system_role=user.system_role,
                course_role=membership.role,
            )
            taxonomy_document = await session.scalar(
                select(SourceDocument).where(
                    SourceDocument.course_id == report.course_id,
                    SourceDocument.source_filename == "量子物理-知识图谱(1).xlsx",
                )
            )
            assert taxonomy_document is not None
            taxonomy_version = await session.scalar(
                select(SourceDocumentVersion).where(
                    SourceDocumentVersion.document_id == taxonomy_document.id
                )
            )
            candidate = await session.scalar(
                select(GraphNodeCandidate).where(
                    GraphNodeCandidate.course_id == report.course_id,
                    GraphNodeCandidate.curriculum_edition_id == taxonomy_edition_id,
                    GraphNodeCandidate.label == "波函数的统计解释",
                )
            )
            assert taxonomy_version is not None and candidate is not None
            service = ReviewService(session)
            await service.approve_document_version(
                actor=actor,
                curriculum_edition_id=taxonomy_edition_id,
                document_version_id=taxonomy_version.id,
                rationale="Real-source smoke review verified all worksheet row locators.",
            )
            await service.publish_document_version(
                actor=actor,
                curriculum_edition_id=taxonomy_edition_id,
                document_version_id=taxonomy_version.id,
                rationale="Publish the reviewed teacher-authored taxonomy for this edition.",
                priority=100,
            )
            await service.approve_node(
                actor=actor,
                curriculum_edition_id=taxonomy_edition_id,
                candidate_id=candidate.id,
                rationale="The concept label is an exact worksheet row claim.",
            )
            await session.commit()
            candidate_id = candidate.id

        graph = InMemoryGraphStore()
        worker = GraphOutboxWorker(
            session_factory=session_factory,
            graph_store=graph,
            worker_id="phase1-real-smoke",
        )
        assert await worker.run_batch(limit=10) == 1

        repository = StudentVisibleEvidenceRepository(session_factory)
        scope = RetrievalScope(
            course_id=report.course_id,
            curriculum_edition_id=taxonomy_edition_id,
        )
        lexical_hits = await repository.full_text(
            scope,
            "波函数的统计解释",
            limit=20,
        )
        assert lexical_hits
        hydrated = await repository.hydrate(
            scope,
            [hit.chunk_id for hit in lexical_hits],
        )
        assert hydrated

        retriever = HybridEvidenceRetriever(
            repository=repository,
            embedding_gateway=embedding,
            graph_store=graph,
        )
        packet = await retriever.retrieve(
            scope,
            "波函数的统计解释",
        )

        assert packet.coverage is RetrievalCoverage.PARTIAL
        assert packet.curriculum_edition_id == taxonomy_edition_id
        assert packet.evidence
        citation = packet.evidence[0]
        assert citation.source_file_name == "量子物理-知识图谱(1).xlsx"
        assert "波函数的统计解释" in citation.evidence_snippet
        assert citation.evidence_snippet in citation.source_chunk
        assert citation.locator.locator_type is LocatorType.XLSX_ROW
        assert citation.locator.sheet_name == "Sheet3"
        assert citation.locator.row_start == 41
        assert any(node.id == candidate_id for node in packet.graph_nodes)
        assert RetrievalChannel.SEMANTIC in packet.degraded_channels
    finally:
        await engine.dispose()
