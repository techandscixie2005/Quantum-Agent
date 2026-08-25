from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from alembic.config import Config
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateTable, Table

from alembic import command
from quantum_agent.config import Settings
from quantum_agent.database import create_database_engine, create_session_factory
from quantum_agent.db_models import (
    Base,
    CandidateOrigin,
    CandidateStatus,
    ChunkExtractionStatus,
    Course,
    CurriculumEdition,
    DocumentChunk,
    DocumentStatus,
    DocumentType,
    DocumentVersionStatus,
    Evidence,
    EvidenceSupportRole,
    EvidenceType,
    GraphNodeCandidate,
    GraphNodeType,
    LocatorType,
    NodeCandidateEvidenceSupport,
    SourceDocument,
    SourceDocumentVersion,
)

API_ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def test_settings_normalize_async_postgres_and_hide_secrets() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://qa:password@db:5432/qa",
        USTC_API="server-only-token",
        NEO4J_PASSWORD="graph-secret",
    )

    assert settings.database_url == "postgresql+asyncpg://qa:password@db:5432/qa"
    assert isinstance(settings.ustc_api, SecretStr)
    assert "server-only-token" not in repr(settings)
    assert "graph-secret" not in repr(settings)


def test_settings_reject_sqlite_in_production() -> None:
    with pytest.raises(ValidationError, match="SQLite is test-only"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )


def test_postgresql_and_sqlite_type_variants_compile() -> None:
    table = cast(Table, DocumentChunk.__table__)
    pg_dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    pg_ddl = str(CreateTable(table).compile(dialect=pg_dialect))
    sqlite_ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))

    assert "TIMESTAMP WITH TIME ZONE" in pg_ddl
    assert "section_path JSONB" in pg_ddl
    assert "search_vector TSVECTOR" in pg_ddl
    assert "embedding VECTOR(384)" in pg_ddl
    assert "section_path JSON" in sqlite_ddl
    assert "search_vector TEXT" in sqlite_ddl
    assert "embedding JSON" in sqlite_ddl
    assert "embedding_fixed_dimension" in pg_ddl


def test_document_lifecycle_is_explicit() -> None:
    required = {
        "uploaded",
        "processing",
        "review_required",
        "approved",
        "published",
        "archived",
    }
    assert required <= {status.value for status in DocumentStatus}
    assert required <= {status.value for status in DocumentVersionStatus}


@pytest.mark.asyncio
async def test_source_evidence_and_multiple_candidate_support_round_trip() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///:memory:")
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    course_id = uuid4()
    edition_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()
    candidate_id = uuid4()
    evidence_one_id = uuid4()
    evidence_two_id = uuid4()

    async with session_factory() as session:
        session.add_all(
            [
                Course(
                    id=course_id,
                    code="QP-2026",
                    title="Quantum Physics",
                    institution="USTC",
                ),
                CurriculumEdition(
                    id=edition_id,
                    course_id=course_id,
                    edition_key="fall-2026",
                    title="Fall 2026 syllabus",
                    ontology_version="1.0.0",
                ),
            ]
        )
        await session.flush()
        session.add(
            SourceDocument(
                id=document_id,
                course_id=course_id,
                curriculum_edition_id=edition_id,
                logical_key="lecture-01",
                title="Lecture 1",
                source_filename="lecture-01.pdf",
                source_path="/knowledge/lecture-01.pdf",
                media_type="application/pdf",
                document_type=DocumentType.LECTURE_SLIDES,
            )
        )
        await session.flush()
        session.add(
            SourceDocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                source_file_sha256=SHA_A,
                byte_size=1234,
                immutable_source_path="/knowledge/lecture-01.pdf",
            )
        )
        await session.flush()
        session.add(
            DocumentChunk(
                id=chunk_id,
                document_version_id=version_id,
                ordinal=0,
                locator_type=LocatorType.SLIDE,
                physical_page=2,
                printed_page_label=None,
                slide_number=1,
                paragraph_start=0,
                paragraph_end=1,
                section_path=["Chapter 1", "State vectors"],
                content="A quantum state is represented by a ray in Hilbert space.",
                evidence_snippet="represented by a ray in Hilbert space",
                content_sha256=SHA_B,
                search_text="quantum state ray Hilbert space 量子态 希尔伯特空间",
                embedding=[0.0] * 384,
                embedding_dimension=384,
                embedding_model="test-embedding",
                extraction_quality=1.0,
                extraction_status=ChunkExtractionStatus.APPROVED,
            )
        )
        await session.flush()
        session.add_all(
            [
                Evidence(
                    id=evidence_one_id,
                    source_chunk_id=chunk_id,
                    evidence_type=EvidenceType.CLAIM,
                    evidence_snippet="A quantum state is represented by a ray",
                    char_start=0,
                    char_end=39,
                    evidence_sha256=SHA_A,
                    chunk_content_sha256=SHA_B,
                ),
                Evidence(
                    id=evidence_two_id,
                    source_chunk_id=chunk_id,
                    evidence_type=EvidenceType.TEXT,
                    evidence_snippet="ray in Hilbert space",
                    char_start=36,
                    char_end=56,
                    evidence_sha256=SHA_C,
                    chunk_content_sha256=SHA_B,
                ),
                GraphNodeCandidate(
                    id=candidate_id,
                    course_id=course_id,
                    curriculum_edition_id=edition_id,
                    node_type=GraphNodeType.QUANTUM_STATE,
                    canonical_key="quantum-state/ray",
                    label="Quantum state ray",
                    origin=CandidateOrigin.LLM,
                    confidence=0.93,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                NodeCandidateEvidenceSupport(
                    node_candidate_id=candidate_id,
                    evidence_id=evidence_one_id,
                    support_role=EvidenceSupportRole.PRIMARY,
                    confidence=0.98,
                ),
                NodeCandidateEvidenceSupport(
                    node_candidate_id=candidate_id,
                    evidence_id=evidence_two_id,
                    support_role=EvidenceSupportRole.CORROBORATING,
                    confidence=0.88,
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        candidate = await session.get(GraphNodeCandidate, candidate_id)
        support_count = await session.scalar(
            select(func.count())
            .select_from(NodeCandidateEvidenceSupport)
            .where(NodeCandidateEvidenceSupport.node_candidate_id == candidate_id)
        )
        chunk = await session.get(DocumentChunk, chunk_id)

        assert candidate is not None
        assert candidate.status is CandidateStatus.REVIEW_REQUIRED
        assert support_count == 2
        assert chunk is not None
        assert chunk.exact_text == chunk.content
        assert chunk.page_label is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_database_check_constraints_fail_closed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    course_id = uuid4()
    edition_id = uuid4()
    async with session_factory() as session:
        session.add(Course(id=course_id, code="QP", title="Quantum Physics", institution="USTC"))
        session.add(
            CurriculumEdition(
                id=edition_id,
                course_id=course_id,
                edition_key="test",
                title="Test",
                ontology_version="1.0.0",
            )
        )
        await session.commit()

        session.add(
            GraphNodeCandidate(
                course_id=course_id,
                curriculum_edition_id=edition_id,
                node_type=GraphNodeType.CONCEPT,
                canonical_key="invalid-confidence",
                label="Invalid",
                origin=CandidateOrigin.LLM,
                confidence=1.1,
            )
        )
        with pytest.raises(IntegrityError, match="confidence_unit_interval"):
            await session.commit()
        await session.rollback()

    await engine.dispose()


def test_alembic_baseline_installs_review_and_provenance_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "schema.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")

    alembic_config = Config(str(API_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")

    connection = sqlite3.connect(database_path)
    try:
        objects = {
            (row[0], row[1])
            for row in connection.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view', 'trigger')"
            )
        }
        assert ("approved_graph_nodes", "view") in objects
        assert ("approved_graph_relations", "view") in objects
        assert ("student_visible_chunks", "view") in objects
        assert ("trg_source_version_identity_immutable", "trigger") in objects
        assert ("trg_audit_logs_no_update", "trigger") in objects
        assert ("trg_graph_sync_outbox_approved_only", "trigger") in objects

        reviewer_id = uuid4().hex
        course_id = uuid4().hex
        edition_id = uuid4().hex
        approved_node_id = uuid4().hex
        pending_node_id = uuid4().hex
        decision_id = uuid4().hex
        connection.execute(
            "INSERT INTO users "
            "(id, email, display_name, system_role, status) VALUES (?, ?, ?, ?, ?)",
            (reviewer_id, "teacher@example.edu", "Teacher", "user", "active"),
        )
        connection.execute(
            "INSERT INTO courses "
            "(id, code, title, institution, default_locale, status) VALUES (?, ?, ?, ?, ?, ?)",
            (course_id, "QP", "Quantum Physics", "USTC", "zh-CN", "active"),
        )
        connection.execute(
            "INSERT INTO curriculum_editions "
            "(id, course_id, edition_key, title, ontology_version, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (edition_id, course_id, "fall-2026", "Fall 2026", "1.0.0", "draft"),
        )
        node_sql = (
            "INSERT INTO graph_node_candidates "
            "(id, course_id, curriculum_edition_id, node_type, canonical_key, label, "
            "origin, confidence, status, revision_number, reviewed_by_user_id, reviewed_at) "
            "VALUES (?, ?, ?, 'concept', ?, ?, 'manual', 1.0, ?, 1, ?, ?)"
        )
        connection.execute(
            node_sql,
            (
                approved_node_id,
                course_id,
                edition_id,
                "approved-node",
                "Approved node",
                "approved",
                reviewer_id,
                "2026-08-22T12:00:00+00:00",
            ),
        )
        connection.execute(
            node_sql,
            (
                pending_node_id,
                course_id,
                edition_id,
                "pending-node",
                "Pending node",
                "review_required",
                None,
                None,
            ),
        )
        connection.execute(
            "INSERT INTO review_decisions "
            "(id, node_candidate_id, decision, reviewer_user_id, rationale, before_snapshot_json) "
            "VALUES (?, ?, 'approve', ?, ?, '{}')",
            (decision_id, approved_node_id, reviewer_id, "Grounded in source evidence"),
        )
        document_id = uuid4().hex
        version_id = uuid4().hex
        approved_chunk_id = uuid4().hex
        connection.execute(
            "INSERT INTO source_documents "
            "(id, course_id, curriculum_edition_id, logical_key, title, source_filename, "
            "source_path, media_type, document_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'lecture_slides', 'published')",
            (
                document_id,
                course_id,
                edition_id,
                "published-lecture",
                "Published lecture",
                "lecture.pdf",
                "/knowledge/lecture.pdf",
                "application/pdf",
            ),
        )
        connection.execute(
            "INSERT INTO source_document_versions "
            "(id, document_id, version_number, source_file_sha256, byte_size, "
            "immutable_source_path, status) VALUES (?, ?, 1, ?, 100, ?, 'published')",
            (version_id, document_id, SHA_A, "/knowledge/lecture.pdf"),
        )
        connection.execute(
            "INSERT INTO document_publications "
            "(id, course_id, curriculum_edition_id, document_version_id, status, "
            "published_by_user_id, priority, published_at) "
            "VALUES (?, ?, ?, ?, 'published', ?, 90, ?)",
            (
                uuid4().hex,
                course_id,
                edition_id,
                version_id,
                reviewer_id,
                "2026-08-22T12:00:00+00:00",
            ),
        )
        chunk_insert = (
            "INSERT INTO document_chunks "
            "(id, document_version_id, ordinal, locator_type, physical_page, content, "
            "content_sha256, search_text, extraction_status) "
            "VALUES (?, ?, ?, 'page', ?, ?, ?, ?, ?)"
        )
        connection.execute(
            chunk_insert,
            (
                approved_chunk_id,
                version_id,
                0,
                1,
                "Approved material",
                SHA_B,
                "approved material",
                "approved",
            ),
        )
        connection.execute(
            chunk_insert,
            (
                uuid4().hex,
                version_id,
                1,
                2,
                "Still needs review",
                SHA_C,
                "review required",
                "review_required",
            ),
        )
        connection.commit()

        assert connection.execute("SELECT count(*) FROM approved_graph_nodes").fetchone() == (1,)
        assert connection.execute("SELECT id FROM student_visible_chunks").fetchall() == [
            (approved_chunk_id,)
        ]

        with pytest.raises(sqlite3.IntegrityError, match="approved, in-scope knowledge"):
            connection.execute(
                "INSERT INTO graph_sync_outbox "
                "(id, course_id, curriculum_edition_id, node_candidate_id, operation, "
                "payload_json, idempotency_key) VALUES (?, ?, ?, ?, 'upsert', '{}', ?)",
                (uuid4().hex, course_id, edition_id, pending_node_id, "pending:1"),
            )

        connection.execute(
            "INSERT INTO graph_sync_outbox "
            "(id, course_id, curriculum_edition_id, node_candidate_id, operation, "
            "payload_json, review_decision_id, idempotency_key) "
            "VALUES (?, ?, ?, ?, 'upsert', '{}', ?, ?)",
            (
                uuid4().hex,
                course_id,
                edition_id,
                approved_node_id,
                decision_id,
                "approved:1",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    command.downgrade(alembic_config, "base")
