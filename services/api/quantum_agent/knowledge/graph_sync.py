"""Transactional PostgreSQL-outbox dispatcher for the Neo4j read projection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.db_models import (
    GraphSyncOperation,
    GraphSyncOutbox,
    OutboxStatus,
)
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    ApprovedGraphRelationship,
    GraphScope,
    GraphStore,
)


class GraphSyncPayloadError(RuntimeError):
    """An outbox payload does not match its authoritative envelope."""


class GraphOutboxWorker:
    """Claim, dispatch, and finalize graph projection events safely.

    External Neo4j calls occur outside the claim transaction.  Stable graph
    keys make retries idempotent; a short processing lease can be recovered by
    a separate maintenance operation if a worker dies mid-call.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        graph_store: GraphStore,
        worker_id: str | None = None,
        max_attempts: int = 5,
        retry_base_seconds: int = 5,
    ) -> None:
        if not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        if not 1 <= retry_base_seconds <= 3600:
            raise ValueError("retry_base_seconds must be between 1 and 3600")
        self._session_factory = session_factory
        self._graph_store = graph_store
        self._worker_id = worker_id or f"graph-sync-{uuid4()}"
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds

    async def run_once(self) -> bool:
        event = await self._claim_one()
        if event is None:
            return False
        try:
            await self._dispatch(event)
        except Exception as error:
            await self._mark_failed(event.id, error)
        else:
            await self._mark_published(event.id)
        return True

    async def run_batch(self, *, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("batch limit must be between 1 and 1000")
        processed = 0
        while processed < limit and await self.run_once():
            processed += 1
        return processed

    async def recover_expired_leases(self, *, lease_seconds: int = 300) -> int:
        """Return abandoned PROCESSING events to FAILED for a later retry."""

        if not 30 <= lease_seconds <= 86400:
            raise ValueError("lease_seconds must be between 30 and 86400")
        cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
        recovered = 0
        async with self._session_factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(GraphSyncOutbox)
                        .where(
                            GraphSyncOutbox.status == OutboxStatus.PROCESSING,
                            GraphSyncOutbox.locked_at < cutoff,
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for event in events:
                event.status = OutboxStatus.FAILED
                event.available_at = datetime.now(UTC)
                event.locked_at = None
                event.locked_by = None
                event.last_error = "ProcessingLeaseExpired"
                recovered += 1
            await session.commit()
        return recovered

    async def _claim_one(self) -> GraphSyncOutbox | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            event = await session.scalar(
                select(GraphSyncOutbox)
                .where(
                    GraphSyncOutbox.status.in_((OutboxStatus.PENDING, OutboxStatus.FAILED)),
                    GraphSyncOutbox.available_at <= now,
                )
                .order_by(GraphSyncOutbox.created_at, GraphSyncOutbox.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return None
            event.status = OutboxStatus.PROCESSING
            event.locked_at = now
            event.locked_by = self._worker_id
            event.attempt_count += 1
            await session.commit()
            return event

    async def _dispatch(self, event: GraphSyncOutbox) -> None:
        scope = GraphScope(
            course_id=str(event.course_id),
            curriculum_edition_id=str(event.curriculum_edition_id),
        )
        if event.node_candidate_id is not None:
            if event.operation is GraphSyncOperation.UPSERT:
                node = ApprovedGraphNode.model_validate(event.payload_json)
                self._validate_envelope(
                    scope=scope,
                    candidate_id=event.node_candidate_id,
                    payload_scope=node.scope,
                    payload_candidate_id=node.candidate_id,
                )
                await self._graph_store.sync_node(node)
            else:
                self._validate_delete_payload(event, event.node_candidate_id)
                await self._graph_store.delete_node(scope, str(event.node_candidate_id))
            return
        if event.relation_candidate_id is None:
            raise GraphSyncPayloadError("outbox event has no graph candidate")
        if event.operation is GraphSyncOperation.UPSERT:
            relationship = ApprovedGraphRelationship.model_validate(event.payload_json)
            self._validate_envelope(
                scope=scope,
                candidate_id=event.relation_candidate_id,
                payload_scope=relationship.scope,
                payload_candidate_id=relationship.candidate_id,
            )
            await self._graph_store.sync_relationship(relationship)
        else:
            self._validate_delete_payload(event, event.relation_candidate_id)
            await self._graph_store.delete_relationship(scope, str(event.relation_candidate_id))

    @staticmethod
    def _validate_envelope(
        *,
        scope: GraphScope,
        candidate_id: UUID,
        payload_scope: GraphScope,
        payload_candidate_id: str,
    ) -> None:
        if payload_scope != scope or payload_candidate_id != str(candidate_id):
            raise GraphSyncPayloadError("outbox payload does not match its scope envelope")

    @staticmethod
    def _validate_delete_payload(event: GraphSyncOutbox, candidate_id: UUID) -> None:
        if event.payload_json.get("candidate_id") != str(candidate_id):
            raise GraphSyncPayloadError("delete payload does not match its candidate envelope")

    async def _mark_published(self, event_id: UUID) -> None:
        async with self._session_factory() as session:
            event = await session.scalar(
                select(GraphSyncOutbox).where(GraphSyncOutbox.id == event_id).with_for_update()
            )
            self._require_owned_processing_event(event)
            assert event is not None
            event.status = OutboxStatus.PUBLISHED
            event.published_at = datetime.now(UTC)
            event.locked_at = None
            event.locked_by = None
            event.last_error = None
            await session.commit()

    async def _mark_failed(self, event_id: UUID, error: Exception) -> None:
        async with self._session_factory() as session:
            event = await session.scalar(
                select(GraphSyncOutbox).where(GraphSyncOutbox.id == event_id).with_for_update()
            )
            self._require_owned_processing_event(event)
            assert event is not None
            terminal = event.attempt_count >= self._max_attempts
            event.status = OutboxStatus.DEAD_LETTER if terminal else OutboxStatus.FAILED
            delay = self._retry_base_seconds * (2 ** max(0, event.attempt_count - 1))
            event.available_at = datetime.now(UTC) + timedelta(seconds=min(delay, 3600))
            event.locked_at = None
            event.locked_by = None
            event.last_error = type(error).__name__[:1000]
            await session.commit()

    def _require_owned_processing_event(self, event: GraphSyncOutbox | None) -> None:
        if (
            event is None
            or event.status is not OutboxStatus.PROCESSING
            or event.locked_by != self._worker_id
        ):
            raise GraphSyncPayloadError("outbox processing lease is no longer owned")


__all__ = ["GraphOutboxWorker", "GraphSyncPayloadError"]
