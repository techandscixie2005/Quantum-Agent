from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from quantum_agent.auth import CourseActor, hash_session_token, issue_opaque_session_token
from quantum_agent.config import Settings
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AuditLog,
    CandidateMergeLineage,
    CandidateOrigin,
    CandidateStatus,
    ChunkExtractionStatus,
    Course,
    CourseMembership,
    CourseRole,
    CurriculumEdition,
    DocumentChunk,
    DocumentStatus,
    DocumentType,
    DocumentVersionStatus,
    Evidence,
    EvidenceStatus,
    EvidenceSupportRole,
    EvidenceType,
    GraphNodeCandidate,
    GraphNodeType,
    GraphRelationCandidate,
    GraphRelationType,
    GraphSyncOperation,
    GraphSyncOutbox,
    LocatorType,
    MembershipStatus,
    NodeCandidateEvidenceSupport,
    RelationCandidateEvidenceSupport,
    ReviewDecision,
    SourceDocument,
    SourceDocumentVersion,
    SystemRole,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.knowledge.review import (
    CandidateKind,
    EvidenceGroundingError,
    NodeEdit,
    ReviewConflictError,
    ReviewService,
)
from quantum_agent.main import create_app

API_ROOT = Path(__file__).resolve().parents[1]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
async def review_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "review.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class SeededReview:
    def __init__(
        self,
        *,
        actor: CourseActor,
        edition_id: UUID,
        document_id: UUID,
        version_id: UUID,
        chunk_id: UUID,
        evidence_id: UUID,
        node_id: UUID,
        session_token: str,
    ) -> None:
        self.actor = actor
        self.edition_id = edition_id
        self.document_id = document_id
        self.version_id = version_id
        self.chunk_id = chunk_id
        self.evidence_id = evidence_id
        self.node_id = node_id
        self.session_token = session_token


async def _seed_review(
    session: AsyncSession,
    *,
    chunk_status: ChunkExtractionStatus = ChunkExtractionStatus.EXTRACTED,
    stale_evidence: bool = False,
) -> SeededReview:
    now = datetime.now(UTC)
    user = User(
        email=f"teacher-{uuid4()}@example.edu",
        display_name="Quantum teacher",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    course = Course(code=f"QP-{uuid4()}", title="Quantum Physics")
    session.add_all([user, course])
    await session.flush()
    edition = CurriculumEdition(
        course_id=course.id,
        edition_key="2026-fall",
        title="2026 秋课程大纲",
    )
    session.add(edition)
    await session.flush()
    session_token = issue_opaque_session_token()
    user_session = UserSession(
        user_id=user.id,
        session_token_sha256=hash_session_token(session_token),
        expires_at=now + timedelta(hours=2),
    )
    membership = CourseMembership(
        course_id=course.id,
        user_id=user.id,
        role=CourseRole.TEACHER,
        status=MembershipStatus.ACTIVE,
        joined_at=now,
    )
    session.add_all([user_session, membership])
    await session.flush()

    document = SourceDocument(
        course_id=course.id,
        curriculum_edition_id=edition.id,
        logical_key=f"lecture-{uuid4()}",
        title="第二章 量子力学基础",
        source_filename="量子力学基础.pdf",
        source_path="knowledge/量子力学基础.pdf",
        media_type="application/pdf",
        document_type=DocumentType.LECTURE_SLIDES,
        status=DocumentStatus.REVIEW_REQUIRED,
    )
    session.add(document)
    await session.flush()
    version = SourceDocumentVersion(
        document_id=document.id,
        version_number=1,
        source_file_sha256="a" * 64,
        byte_size=1024,
        immutable_source_path="knowledge/量子力学基础.pdf",
        status=DocumentVersionStatus.REVIEW_REQUIRED,
    )
    session.add(version)
    await session.flush()
    source_text = "波函数的统计解释给出粒子在空间中出现的概率密度。"
    snippet = "波函数的统计解释"
    start = source_text.index(snippet)
    chunk = DocumentChunk(
        document_version_id=version.id,
        ordinal=0,
        locator_type=LocatorType.PAGE,
        locator_start="7",
        locator_end="7",
        physical_page=7,
        section_path=["第二章", "波函数的统计解释"],
        content=source_text,
        content_sha256=_hash(source_text),
        search_text="波函数 统计解释 概率密度",
        extraction_status=chunk_status,
    )
    session.add(chunk)
    await session.flush()
    evidence = Evidence(
        source_chunk_id=chunk.id,
        evidence_type=EvidenceType.CLAIM,
        evidence_snippet=snippet,
        char_start=start,
        char_end=start + len(snippet),
        evidence_sha256=_hash(snippet),
        chunk_content_sha256="f" * 64 if stale_evidence else chunk.content_sha256,
        status=EvidenceStatus.GROUNDED,
        locator_json={"physical_page": 7},
    )
    node = GraphNodeCandidate(
        course_id=course.id,
        curriculum_edition_id=edition.id,
        node_type=GraphNodeType.CONCEPT,
        canonical_key="wave-function/statistical-interpretation",
        label="波函数的统计解释",
        description=source_text,
        origin=CandidateOrigin.IMPORTED,
        confidence=0.99,
    )
    session.add_all([evidence, node])
    await session.flush()
    session.add(
        NodeCandidateEvidenceSupport(
            node_candidate_id=node.id,
            evidence_id=evidence.id,
            support_role=EvidenceSupportRole.PRIMARY,
            confidence=1.0,
        )
    )
    await session.commit()
    return SeededReview(
        actor=CourseActor(
            user_id=user.id,
            session_id=user_session.id,
            course_id=course.id,
            email=user.email,
            display_name=user.display_name,
            system_role=user.system_role,
            course_role=membership.role,
        ),
        edition_id=edition.id,
        document_id=document.id,
        version_id=version.id,
        chunk_id=chunk.id,
        evidence_id=evidence.id,
        node_id=node.id,
        session_token=session_token,
    )


async def test_node_approval_is_grounded_audited_and_outboxed(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        service = ReviewService(session)
        decision = await service.approve_node(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=seeded.node_id,
            rationale="Verified against the cited course page.",
        )
        await session.commit()

    async with review_database() as session:
        candidate = await session.get(GraphNodeCandidate, seeded.node_id)
        outbox = await session.scalar(
            select(GraphSyncOutbox).where(GraphSyncOutbox.node_candidate_id == seeded.node_id)
        )
        audit_count = await session.scalar(select(func.count()).select_from(AuditLog))
        persisted_decision = await session.get(ReviewDecision, decision.id)
        approved_view_count = await session.scalar(
            text("SELECT count(*) FROM approved_graph_nodes WHERE id = :id"),
            {"id": seeded.node_id.hex},
        )

    assert candidate is not None and candidate.status is CandidateStatus.APPROVED
    assert persisted_decision is not None
    assert outbox is not None and outbox.operation is GraphSyncOperation.UPSERT
    assert outbox.payload_json["evidence"][0]["source_chunk_id"] == str(seeded.chunk_id)
    assert audit_count == 1
    assert approved_view_count == 1


async def test_stale_evidence_fails_closed(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session, stale_evidence=True)
        with pytest.raises(EvidenceGroundingError, match="stale"):
            await ReviewService(session).approve_node(
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                candidate_id=seeded.node_id,
                rationale="Attempted review.",
            )
        await session.rollback()

    async with review_database() as session:
        candidate = await session.get(GraphNodeCandidate, seeded.node_id)
        outbox_count = await session.scalar(select(func.count()).select_from(GraphSyncOutbox))

    assert candidate is not None and candidate.status is CandidateStatus.REVIEW_REQUIRED
    assert outbox_count == 0


async def test_relation_requires_approved_endpoints_and_explicit_ontology(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        second = GraphNodeCandidate(
            course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id,
            node_type=GraphNodeType.CONCEPT,
            canonical_key="probability-density",
            label="概率密度",
            origin=CandidateOrigin.IMPORTED,
            confidence=0.98,
        )
        session.add(second)
        await session.flush()
        session.add(
            NodeCandidateEvidenceSupport(
                node_candidate_id=second.id,
                evidence_id=seeded.evidence_id,
                support_role=EvidenceSupportRole.PRIMARY,
                confidence=1.0,
            )
        )
        relation = GraphRelationCandidate(
            course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id,
            source_node_candidate_id=seeded.node_id,
            target_node_candidate_id=second.id,
            relation_type=GraphRelationType.PREREQUISITE_OF,
            canonical_key=f"{seeded.node_id}:prerequisite_of:{second.id}",
            origin=CandidateOrigin.IMPORTED,
            confidence=0.95,
        )
        session.add(relation)
        await session.flush()
        session.add(
            RelationCandidateEvidenceSupport(
                relation_candidate_id=relation.id,
                evidence_id=seeded.evidence_id,
                support_role=EvidenceSupportRole.PRIMARY,
                confidence=1.0,
            )
        )
        await session.commit()

        service = ReviewService(session)
        with pytest.raises(ReviewConflictError, match="endpoints"):
            await service.approve_relation(
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                candidate_id=relation.id,
                rationale="Check the hierarchy.",
            )
        await service.approve_node(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=seeded.node_id,
            rationale="Verified source node.",
        )
        await service.approve_node(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=second.id,
            rationale="Verified target node.",
        )
        await service.approve_relation(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=relation.id,
            rationale="Endpoints and prerequisite statement verified.",
        )
        await session.commit()

    async with review_database() as session:
        persisted = await session.get(GraphRelationCandidate, relation.id)
        relation_outbox = await session.scalar(
            select(GraphSyncOutbox).where(GraphSyncOutbox.relation_candidate_id == relation.id)
        )

    assert persisted is not None and persisted.status is CandidateStatus.APPROVED
    assert relation_outbox is not None


async def test_editing_approved_node_removes_projection_until_reapproval(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        service = ReviewService(session)
        await service.approve_node(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=seeded.node_id,
            rationale="Initial verification.",
        )
        await service.edit_node(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=seeded.node_id,
            patch=NodeEdit(
                label="波函数统计诠释（教师修订）"  # noqa: RUF001 - Chinese typography
            ),
            rationale="Align terminology with the current syllabus.",
        )
        await session.commit()

    async with review_database() as session:
        candidate = await session.get(GraphNodeCandidate, seeded.node_id)
        operations = list(
            (
                await session.scalars(
                    select(GraphSyncOutbox.operation)
                    .where(GraphSyncOutbox.node_candidate_id == seeded.node_id)
                    .order_by(GraphSyncOutbox.created_at)
                )
            ).all()
        )

    assert candidate is not None
    assert candidate.status is CandidateStatus.REVIEW_REQUIRED
    assert candidate.revision_number == 2
    assert operations == [GraphSyncOperation.UPSERT, GraphSyncOperation.DELETE]


async def test_document_publication_requires_teacher_approval_and_exposes_chunks(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        service = ReviewService(session)
        with pytest.raises(ReviewConflictError, match="approved"):
            await service.publish_document_version(
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                document_version_id=seeded.version_id,
                rationale="Publish now.",
            )
        await service.approve_document_version(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            document_version_id=seeded.version_id,
            rationale="Checked extraction and locator.",
        )
        await service.publish_document_version(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            document_version_id=seeded.version_id,
            rationale="Approved for the current course edition.",
            priority=90,
        )
        await session.commit()

    async with review_database() as session:
        visible = await session.scalar(
            text(
                "SELECT count(*) FROM student_visible_chunks "
                "WHERE id = :id AND publication_curriculum_edition_id = :edition_id"
            ),
            {"id": seeded.chunk_id.hex, "edition_id": seeded.edition_id.hex},
        )
        document = await session.get(SourceDocument, seeded.document_id)
        version = await session.get(SourceDocumentVersion, seeded.version_id)

    assert visible == 1
    assert document is not None and document.status is DocumentStatus.PUBLISHED
    assert version is not None and version.status is DocumentVersionStatus.PUBLISHED


async def test_ocr_required_chunk_blocks_bulk_document_approval(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session, chunk_status=ChunkExtractionStatus.OCR_REQUIRED)
        with pytest.raises(ReviewConflictError, match="OCR-required"):
            await ReviewService(session).approve_document_version(
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                document_version_id=seeded.version_id,
                rationale="Review the scan.",
            )


async def test_review_queue_is_scoped_and_contains_evidence_count(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        service = ReviewService(session)
        queue = await service.list_queue(
            course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id,
        )
        detail = await service.get_node_detail(
            course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=seeded.node_id,
        )
        unknown = await service.list_queue(
            course_id=uuid4(),
            curriculum_edition_id=seeded.edition_id,
        )

    assert len(queue) == 1 and queue[0].evidence_count == 1
    assert detail.evidence[0].source_chunk_id == seeded.chunk_id
    assert detail.evidence[0].source_chunk.startswith("波函数")
    assert unknown == []


async def test_rejection_is_audited_without_publishing(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        await ReviewService(session).reject_candidate(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=seeded.node_id,
            kind=CandidateKind.NODE,
            rationale="This duplicates the canonical syllabus concept.",
        )
        await session.commit()

    async with review_database() as session:
        candidate = await session.get(GraphNodeCandidate, seeded.node_id)
        outbox_count = await session.scalar(select(func.count()).select_from(GraphSyncOutbox))
        decision_count = await session.scalar(select(func.count()).select_from(ReviewDecision))

    assert candidate is not None and candidate.status is CandidateStatus.REJECTED
    assert outbox_count == 0
    assert decision_count == 1


async def test_node_merge_preserves_lineage_and_requires_survivor_reapproval(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)
        survivor = GraphNodeCandidate(
            course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id,
            node_type=GraphNodeType.CONCEPT,
            canonical_key="wave-function/born-interpretation",
            label="波函数的统计解释（规范词条）",  # noqa: RUF001 - Chinese typography
            origin=CandidateOrigin.MANUAL,
            confidence=1.0,
        )
        session.add(survivor)
        await session.flush()
        session.add(
            NodeCandidateEvidenceSupport(
                node_candidate_id=survivor.id,
                evidence_id=seeded.evidence_id,
                support_role=EvidenceSupportRole.PRIMARY,
                confidence=1.0,
            )
        )
        await session.commit()
        service = ReviewService(session)
        await service.approve_node(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            candidate_id=survivor.id,
            rationale="Canonical entry verified.",
        )
        await service.merge_nodes(
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            duplicate_candidate_id=seeded.node_id,
            survivor_candidate_id=survivor.id,
            rationale="Both labels refer to the same course concept.",
        )
        await session.commit()

    async with review_database() as session:
        duplicate = await session.get(GraphNodeCandidate, seeded.node_id)
        persisted_survivor = await session.get(GraphNodeCandidate, survivor.id)
        lineage = await session.scalar(
            select(CandidateMergeLineage).where(
                CandidateMergeLineage.merged_node_candidate_id == seeded.node_id
            )
        )
        survivor_operations = list(
            (
                await session.scalars(
                    select(GraphSyncOutbox.operation)
                    .where(GraphSyncOutbox.node_candidate_id == survivor.id)
                    .order_by(GraphSyncOutbox.created_at)
                )
            ).all()
        )

    assert duplicate is not None and duplicate.status is CandidateStatus.SUPERSEDED
    assert duplicate.superseded_by_node_candidate_id == survivor.id
    assert persisted_survivor is not None
    assert persisted_survivor.status is CandidateStatus.REVIEW_REQUIRED
    assert persisted_survivor.revision_number == 2
    assert lineage is not None and lineage.surviving_node_candidate_id == survivor.id
    assert survivor_operations == [GraphSyncOperation.UPSERT, GraphSyncOperation.DELETE]


async def test_review_http_api_requires_backend_role_and_commits_approval(
    review_database: async_sessionmaker[AsyncSession],
) -> None:
    async with review_database() as session:
        seeded = await _seed_review(session)

    app = create_app(
        Settings(
            _env_file=None,
            ENVIRONMENT="test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with review_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base_path = (
        f"/api/v1/courses/{seeded.actor.course_id}/editions/"
        f"{seeded.edition_id}/knowledge"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthenticated = await client.get(f"{base_path}/review-queue")
        queue = await client.get(
            f"{base_path}/review-queue",
            headers={"Authorization": f"Bearer {seeded.session_token}"},
        )
        approved = await client.post(
            f"{base_path}/nodes/{seeded.node_id}/approve",
            headers={"Authorization": f"Bearer {seeded.session_token}"},
            json={"rationale": "Verified through the teacher review API."},
        )
        evidence_packet = await client.post(
            (
                f"/api/v1/courses/{seeded.actor.course_id}/editions/"
                f"{seeded.edition_id}/evidence-packets"
            ),
            headers={"Authorization": f"Bearer {seeded.session_token}"},
            json={"query": "波函数的统计解释"},
        )

    assert unauthenticated.status_code == 401
    assert queue.status_code == 200
    assert queue.json()[0]["candidate_id"] == str(seeded.node_id)
    assert approved.status_code == 200
    assert approved.json()["projection_state"] == "pending_upsert"
    assert evidence_packet.status_code == 200
    assert evidence_packet.json()["course_id"] == str(seeded.actor.course_id)
    assert evidence_packet.json()["curriculum_edition_id"] == str(seeded.edition_id)
    assert evidence_packet.json()["coverage"] == "not_found"
    async with review_database() as session:
        candidate = await session.get(GraphNodeCandidate, seeded.node_id)
    assert candidate is not None and candidate.status is CandidateStatus.APPROVED
