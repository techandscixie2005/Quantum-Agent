from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantum_agent.db_models import (
    Base,
    CandidateOrigin,
    CandidateStatus,
    Course,
    CurriculumEdition,
    GraphNodeCandidate,
    GraphNodeType,
    GraphSyncOperation,
    GraphSyncOutbox,
    OutboxStatus,
    ReviewDecision,
    ReviewDecisionType,
    User,
    UserStatus,
)
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    GraphScope,
    InMemoryGraphStore,
)
from quantum_agent.knowledge.graph_sync import GraphOutboxWorker
from quantum_agent.knowledge.ontology import NodeType


@pytest.fixture
async def sync_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_outbox(
    factory: async_sessionmaker[AsyncSession],
    *,
    tamper_scope: bool = False,
) -> tuple[GraphSyncOutbox, GraphScope]:
    async with factory() as session:
        course = Course(code=f"QP-{uuid4()}", title="Quantum Physics")
        teacher = User(
            email=f"teacher-{uuid4()}@example.edu",
            display_name="Teacher",
            status=UserStatus.ACTIVE,
        )
        session.add_all([course, teacher])
        await session.flush()
        edition = CurriculumEdition(
            course_id=course.id,
            edition_key="2026-fall",
            title="2026 Fall",
        )
        session.add(edition)
        await session.flush()
        candidate = GraphNodeCandidate(
            course_id=course.id,
            curriculum_edition_id=edition.id,
            node_type=GraphNodeType.CONCEPT,
            canonical_key="wave-function",
            label="波函数",
            origin=CandidateOrigin.MANUAL,
            confidence=1.0,
            status=CandidateStatus.APPROVED,
            reviewed_by_user_id=teacher.id,
            reviewed_at=datetime.now(UTC),
        )
        session.add(candidate)
        await session.flush()
        decision = ReviewDecision(
            node_candidate_id=candidate.id,
            decision=ReviewDecisionType.APPROVE,
            reviewer_user_id=teacher.id,
            rationale="Verified.",
            before_snapshot_json={"status": "review_required"},
            after_snapshot_json={"status": "approved"},
        )
        session.add(decision)
        await session.flush()
        scope = GraphScope(
            course_id=str(course.id),
            curriculum_edition_id=str(edition.id),
        )
        payload_scope = (
            GraphScope(course_id=str(uuid4()), curriculum_edition_id=str(edition.id))
            if tamper_scope
            else scope
        )
        payload = ApprovedGraphNode(
            candidate_id=str(candidate.id),
            scope=payload_scope,
            node_type=NodeType.CONCEPT,
            canonical_key=candidate.canonical_key,
            label=candidate.label,
            review_decision_id=str(decision.id),
            review_revision=1,
        )
        event = GraphSyncOutbox(
            course_id=course.id,
            curriculum_edition_id=edition.id,
            node_candidate_id=candidate.id,
            operation=GraphSyncOperation.UPSERT,
            payload_json=payload.model_dump(mode="json"),
            review_decision_id=decision.id,
            idempotency_key=f"test:{uuid4()}",
        )
        session.add(event)
        await session.commit()
        return event, scope


async def test_worker_projects_and_marks_event_published(
    sync_database: async_sessionmaker[AsyncSession],
) -> None:
    event, scope = await _seed_outbox(sync_database)
    graph = InMemoryGraphStore()
    worker = GraphOutboxWorker(
        session_factory=sync_database,
        graph_store=graph,
        worker_id="test-worker",
    )

    assert await worker.run_once() is True
    assert await worker.run_once() is False

    hits = await graph.search_nodes(scope, "波函数")
    async with sync_database() as session:
        persisted = await session.get(GraphSyncOutbox, event.id)
    assert len(hits) == 1
    assert persisted is not None and persisted.status is OutboxStatus.PUBLISHED
    assert persisted.attempt_count == 1
    assert persisted.published_at is not None


async def test_tampered_payload_is_dead_lettered_without_graph_write(
    sync_database: async_sessionmaker[AsyncSession],
) -> None:
    event, scope = await _seed_outbox(sync_database, tamper_scope=True)
    graph = InMemoryGraphStore()
    worker = GraphOutboxWorker(
        session_factory=sync_database,
        graph_store=graph,
        worker_id="test-worker",
        max_attempts=1,
    )

    assert await worker.run_once() is True

    async with sync_database() as session:
        persisted = await session.get(GraphSyncOutbox, event.id)
    assert persisted is not None and persisted.status is OutboxStatus.DEAD_LETTER
    assert persisted.last_error == "GraphSyncPayloadError"
    assert await graph.search_nodes(scope, "wave") == []
