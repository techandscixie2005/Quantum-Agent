"""Teacher governance transactions for source material and graph knowledge.

PostgreSQL is the review authority.  Every graph approval validates immutable
source evidence, records a reviewer decision and revision snapshot, appends an
audit event, then emits an approval-gated outbox record.  Neo4j never decides
or stores review state on its own.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    AuditEventType,
    AuditLog,
    AuditResourceType,
    CandidateMergeLineage,
    CandidateRevision,
    CandidateStatus,
    ChunkExtractionStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    DocumentChunk,
    DocumentPublication,
    DocumentStatus,
    DocumentVersionStatus,
    Evidence,
    EvidenceStatus,
    EvidenceSupportRole,
    GraphNodeCandidate,
    GraphRelationCandidate,
    GraphSyncOperation,
    GraphSyncOutbox,
    NodeCandidateEvidenceSupport,
    PublicationStatus,
    RelationCandidateEvidenceSupport,
    ReviewDecision,
    ReviewDecisionType,
    SourceDocument,
    SourceDocumentVersion,
)
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    ApprovedGraphRelationship,
    GraphEvidence,
    GraphScope,
)
from quantum_agent.knowledge.ontology import NodeType, RelationshipType, is_allowed_triple


class CandidateKind(StrEnum):
    NODE = "node"
    RELATION = "relation"


class ReviewConflictError(RuntimeError):
    """The requested review transition is invalid or stale."""


class EvidenceGroundingError(RuntimeError):
    """Approval failed because authoritative evidence could not be verified."""


class ReviewNotFoundError(RuntimeError):
    """A scoped review resource was not found."""


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: UUID
    kind: CandidateKind
    status: CandidateStatus
    type_name: str
    label: str
    confidence: float
    revision_number: int
    evidence_count: int = Field(ge=0)
    updated_at: datetime


class ReviewEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    source_document_id: UUID
    source_document_title: str
    source_file_name: str
    document_version_id: UUID
    source_file_sha256: str
    source_chunk_id: UUID
    source_chunk: str
    evidence_snippet: str
    char_start: int
    char_end: int
    locator: dict[str, Any]
    support_role: EvidenceSupportRole
    confidence: float


class ReviewCandidateDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item: ReviewQueueItem
    canonical_key: str
    description: str | None
    properties: dict[str, Any]
    formula_latex: str | None = None
    source_candidate_id: UUID | None = None
    target_candidate_id: UUID | None = None
    evidence: list[ReviewEvidenceItem]


class NodeEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_key: str | None = Field(default=None, min_length=1, max_length=700)
    label: str | None = Field(default=None, min_length=1, max_length=1000)
    description: str | None = None
    formula_latex: str | None = None
    properties: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> NodeEdit:
        if not self.model_fields_set:
            raise ValueError("at least one editable field is required")
        return self


class RelationEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node_candidate_id: UUID | None = None
    target_node_candidate_id: UUID | None = None
    relationship_type: RelationshipType | None = None
    description: str | None = None
    properties: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> RelationEdit:
        if not self.model_fields_set:
            raise ValueError("at least one editable field is required")
        return self


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _node_type(candidate: GraphNodeCandidate) -> NodeType:
    return NodeType[candidate.node_type.name]


def _relationship_type(candidate: GraphRelationCandidate) -> RelationshipType:
    return RelationshipType[candidate.relation_type.name]


def _node_snapshot(candidate: GraphNodeCandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "course_id": str(candidate.course_id),
        "curriculum_edition_id": str(candidate.curriculum_edition_id),
        "node_type": candidate.node_type.value,
        "canonical_key": candidate.canonical_key,
        "label": candidate.label,
        "description": candidate.description,
        "formula_latex": candidate.formula_latex,
        "properties": candidate.properties_json,
        "origin": candidate.origin.value,
        "confidence": candidate.confidence,
        "status": candidate.status.value,
        "revision_number": candidate.revision_number,
    }


def _relation_snapshot(candidate: GraphRelationCandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "course_id": str(candidate.course_id),
        "curriculum_edition_id": str(candidate.curriculum_edition_id),
        "source_node_candidate_id": str(candidate.source_node_candidate_id),
        "target_node_candidate_id": str(candidate.target_node_candidate_id),
        "relation_type": candidate.relation_type.value,
        "canonical_key": candidate.canonical_key,
        "description": candidate.description,
        "properties": candidate.properties_json,
        "origin": candidate.origin.value,
        "confidence": candidate.confidence,
        "status": candidate.status.value,
        "revision_number": candidate.revision_number,
    }


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    }


class _EvidenceRow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    evidence: Evidence
    chunk: DocumentChunk
    version: SourceDocumentVersion
    document: SourceDocument
    support_role: EvidenceSupportRole
    confidence: float


class ReviewService:
    """Atomic graph and document review operations for one SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_queue(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        statuses: Sequence[CandidateStatus] = (
            CandidateStatus.REVIEW_REQUIRED,
            CandidateStatus.IN_REVIEW,
        ),
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewQueueItem]:
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("invalid review queue pagination")
        requested = tuple(statuses)
        if not requested:
            return []

        node_support_count = (
            select(
                NodeCandidateEvidenceSupport.node_candidate_id.label("candidate_id"),
                func.count().label("evidence_count"),
            )
            .group_by(NodeCandidateEvidenceSupport.node_candidate_id)
            .subquery()
        )
        relation_support_count = (
            select(
                RelationCandidateEvidenceSupport.relation_candidate_id.label("candidate_id"),
                func.count().label("evidence_count"),
            )
            .group_by(RelationCandidateEvidenceSupport.relation_candidate_id)
            .subquery()
        )
        nodes = await self._session.execute(
            select(GraphNodeCandidate, func.coalesce(node_support_count.c.evidence_count, 0))
            .outerjoin(
                node_support_count,
                node_support_count.c.candidate_id == GraphNodeCandidate.id,
            )
            .where(
                GraphNodeCandidate.course_id == course_id,
                GraphNodeCandidate.curriculum_edition_id == curriculum_edition_id,
                GraphNodeCandidate.status.in_(requested),
            )
        )
        relations = await self._session.execute(
            select(
                GraphRelationCandidate,
                func.coalesce(relation_support_count.c.evidence_count, 0),
            )
            .outerjoin(
                relation_support_count,
                relation_support_count.c.candidate_id == GraphRelationCandidate.id,
            )
            .where(
                GraphRelationCandidate.course_id == course_id,
                GraphRelationCandidate.curriculum_edition_id == curriculum_edition_id,
                GraphRelationCandidate.status.in_(requested),
            )
        )
        items = [
            ReviewQueueItem(
                candidate_id=candidate.id,
                kind=CandidateKind.NODE,
                status=candidate.status,
                type_name=candidate.node_type.value,
                label=candidate.label,
                confidence=candidate.confidence,
                revision_number=candidate.revision_number,
                evidence_count=count,
                updated_at=candidate.updated_at,
            )
            for candidate, count in nodes.all()
        ]
        items.extend(
            ReviewQueueItem(
                candidate_id=candidate.id,
                kind=CandidateKind.RELATION,
                status=candidate.status,
                type_name=candidate.relation_type.value,
                label=candidate.canonical_key,
                confidence=candidate.confidence,
                revision_number=candidate.revision_number,
                evidence_count=count,
                updated_at=candidate.updated_at,
            )
            for candidate, count in relations.all()
        )
        items.sort(key=lambda item: (-item.updated_at.timestamp(), str(item.candidate_id)))
        return items[offset : offset + limit]

    async def get_node_detail(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
    ) -> ReviewCandidateDetail:
        candidate = await self._get_node(
            course_id=course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
        )
        evidence = await self._node_evidence(candidate)
        return ReviewCandidateDetail(
            item=ReviewQueueItem(
                candidate_id=candidate.id,
                kind=CandidateKind.NODE,
                status=candidate.status,
                type_name=candidate.node_type.value,
                label=candidate.label,
                confidence=candidate.confidence,
                revision_number=candidate.revision_number,
                evidence_count=len(evidence),
                updated_at=candidate.updated_at,
            ),
            canonical_key=candidate.canonical_key,
            description=candidate.description,
            formula_latex=candidate.formula_latex,
            properties=candidate.properties_json,
            evidence=[self._review_evidence(row) for row in evidence],
        )

    async def get_relation_detail(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
    ) -> ReviewCandidateDetail:
        candidate = await self._get_relation(
            course_id=course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
        )
        evidence = await self._relation_evidence(candidate)
        return ReviewCandidateDetail(
            item=ReviewQueueItem(
                candidate_id=candidate.id,
                kind=CandidateKind.RELATION,
                status=candidate.status,
                type_name=candidate.relation_type.value,
                label=candidate.canonical_key,
                confidence=candidate.confidence,
                revision_number=candidate.revision_number,
                evidence_count=len(evidence),
                updated_at=candidate.updated_at,
            ),
            canonical_key=candidate.canonical_key,
            description=candidate.description,
            properties=candidate.properties_json,
            source_candidate_id=candidate.source_node_candidate_id,
            target_candidate_id=candidate.target_node_candidate_id,
            evidence=[self._review_evidence(row) for row in evidence],
        )

    async def approve_node(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        rationale: str,
    ) -> ReviewDecision:
        rationale = self._rationale(rationale)
        candidate = await self._get_node(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            for_update=True,
        )
        self._require_reviewable(candidate.status)
        evidence = await self._node_evidence(candidate)
        self._validate_evidence(evidence, candidate.course_id, candidate.curriculum_edition_id)
        before = _node_snapshot(candidate)
        revision = await self._revision_for_node(candidate, actor.user_id, before)
        candidate.status = CandidateStatus.APPROVED
        candidate.reviewed_by_user_id = actor.user_id
        candidate.reviewed_at = datetime.now(UTC)
        after = _node_snapshot(candidate)
        decision = ReviewDecision(
            node_candidate_id=candidate.id,
            candidate_revision_id=revision.id,
            decision=ReviewDecisionType.APPROVE,
            reviewer_user_id=actor.user_id,
            rationale=rationale,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
        self._session.add(decision)
        await self._session.flush()
        projection = self._node_projection(candidate, decision.id, evidence)
        self._session.add(
            GraphSyncOutbox(
                course_id=candidate.course_id,
                curriculum_edition_id=candidate.curriculum_edition_id,
                node_candidate_id=candidate.id,
                operation=GraphSyncOperation.UPSERT,
                payload_json=projection.model_dump(mode="json"),
                review_decision_id=decision.id,
                idempotency_key=self._outbox_key(
                    CandidateKind.NODE,
                    candidate.id,
                    candidate.revision_number,
                    GraphSyncOperation.UPSERT,
                    decision.id,
                ),
            )
        )
        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_REVIEWED,
            resource_type=AuditResourceType.NODE_CANDIDATE,
            resource_id=candidate.id,
            summary="Approved graph node candidate",
            before=before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def approve_relation(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        rationale: str,
    ) -> ReviewDecision:
        rationale = self._rationale(rationale)
        candidate = await self._get_relation(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            for_update=True,
        )
        self._require_reviewable(candidate.status)
        source, target = await self._relation_endpoints(candidate, require_approved=True)
        if not is_allowed_triple(
            _node_type(source), _relationship_type(candidate), _node_type(target)
        ):
            raise ReviewConflictError("relationship violates the explicit ontology")
        evidence = await self._relation_evidence(candidate)
        self._validate_evidence(evidence, candidate.course_id, candidate.curriculum_edition_id)
        before = _relation_snapshot(candidate)
        revision = await self._revision_for_relation(candidate, actor.user_id, before)
        candidate.status = CandidateStatus.APPROVED
        candidate.reviewed_by_user_id = actor.user_id
        candidate.reviewed_at = datetime.now(UTC)
        after = _relation_snapshot(candidate)
        decision = ReviewDecision(
            relation_candidate_id=candidate.id,
            candidate_revision_id=revision.id,
            decision=ReviewDecisionType.APPROVE,
            reviewer_user_id=actor.user_id,
            rationale=rationale,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
        self._session.add(decision)
        await self._session.flush()
        projection = self._relation_projection(candidate, source, target, decision.id, evidence)
        self._session.add(
            GraphSyncOutbox(
                course_id=candidate.course_id,
                curriculum_edition_id=candidate.curriculum_edition_id,
                relation_candidate_id=candidate.id,
                operation=GraphSyncOperation.UPSERT,
                payload_json=projection.model_dump(mode="json"),
                review_decision_id=decision.id,
                idempotency_key=self._outbox_key(
                    CandidateKind.RELATION,
                    candidate.id,
                    candidate.revision_number,
                    GraphSyncOperation.UPSERT,
                    decision.id,
                ),
            )
        )
        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_REVIEWED,
            resource_type=AuditResourceType.RELATION_CANDIDATE,
            resource_id=candidate.id,
            summary="Approved graph relationship candidate",
            before=before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def reject_candidate(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        kind: CandidateKind,
        rationale: str,
    ) -> ReviewDecision:
        rationale = self._rationale(rationale)
        reviewed_candidate: GraphNodeCandidate | GraphRelationCandidate
        if kind is CandidateKind.NODE:
            node_candidate = await self._get_node(
                course_id=actor.course_id,
                curriculum_edition_id=curriculum_edition_id,
                candidate_id=candidate_id,
                for_update=True,
            )
            if node_candidate.status in {
                CandidateStatus.REJECTED,
                CandidateStatus.SUPERSEDED,
            }:
                raise ReviewConflictError("terminal candidate cannot be rejected again")
            before = _node_snapshot(node_candidate)
            was_approved = node_candidate.status is CandidateStatus.APPROVED
            node_candidate.status = CandidateStatus.REJECTED
            node_candidate.reviewed_by_user_id = actor.user_id
            node_candidate.reviewed_at = datetime.now(UTC)
            after = _node_snapshot(node_candidate)
            revision = await self._revision_for_node(node_candidate, actor.user_id, before)
            decision = ReviewDecision(
                node_candidate_id=node_candidate.id,
                candidate_revision_id=revision.id,
                decision=ReviewDecisionType.REJECT,
                reviewer_user_id=actor.user_id,
                rationale=rationale,
                before_snapshot_json=before,
                after_snapshot_json=after,
            )
            reviewed_candidate = node_candidate
            resource_type = AuditResourceType.NODE_CANDIDATE
        else:
            relation = await self._get_relation(
                course_id=actor.course_id,
                curriculum_edition_id=curriculum_edition_id,
                candidate_id=candidate_id,
                for_update=True,
            )
            if relation.status in {
                CandidateStatus.REJECTED,
                CandidateStatus.SUPERSEDED,
            }:
                raise ReviewConflictError("terminal candidate cannot be rejected again")
            before = _relation_snapshot(relation)
            was_approved = relation.status is CandidateStatus.APPROVED
            relation.status = CandidateStatus.REJECTED
            relation.reviewed_by_user_id = actor.user_id
            relation.reviewed_at = datetime.now(UTC)
            after = _relation_snapshot(relation)
            revision = await self._revision_for_relation(relation, actor.user_id, before)
            decision = ReviewDecision(
                relation_candidate_id=relation.id,
                candidate_revision_id=revision.id,
                decision=ReviewDecisionType.REJECT,
                reviewer_user_id=actor.user_id,
                rationale=rationale,
                before_snapshot_json=before,
                after_snapshot_json=after,
            )
            reviewed_candidate = relation
            resource_type = AuditResourceType.RELATION_CANDIDATE
        self._session.add(decision)
        await self._session.flush()
        if was_approved:
            self._session.add(
                GraphSyncOutbox(
                    course_id=reviewed_candidate.course_id,
                    curriculum_edition_id=reviewed_candidate.curriculum_edition_id,
                    node_candidate_id=(
                        reviewed_candidate.id if kind is CandidateKind.NODE else None
                    ),
                    relation_candidate_id=(
                        reviewed_candidate.id if kind is CandidateKind.RELATION else None
                    ),
                    operation=GraphSyncOperation.DELETE,
                    payload_json={"candidate_id": str(reviewed_candidate.id)},
                    review_decision_id=decision.id,
                    idempotency_key=self._outbox_key(
                        kind,
                        reviewed_candidate.id,
                        reviewed_candidate.revision_number,
                        GraphSyncOperation.DELETE,
                        decision.id,
                    ),
                )
            )
        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_REVIEWED,
            resource_type=resource_type,
            resource_id=reviewed_candidate.id,
            summary=f"Rejected graph {kind.value} candidate",
            before=before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def edit_node(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        patch: NodeEdit,
        rationale: str,
    ) -> ReviewDecision:
        rationale = self._rationale(rationale)
        candidate = await self._get_node(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            for_update=True,
        )
        if candidate.status in {CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED}:
            raise ReviewConflictError("terminal candidate cannot be edited")
        before = _node_snapshot(candidate)
        was_approved = candidate.status is CandidateStatus.APPROVED
        revision = await self._revision_for_node(candidate, actor.user_id, before)
        for field_name in patch.model_fields_set:
            target = "properties_json" if field_name == "properties" else field_name
            value = getattr(patch, field_name)
            if field_name in {"canonical_key", "label"} and value is None:
                raise ReviewConflictError(f"{field_name} cannot be null")
            if field_name == "properties":
                value = value or {}
            setattr(candidate, target, value)
        candidate.revision_number += 1
        candidate.status = CandidateStatus.REVIEW_REQUIRED
        candidate.reviewed_by_user_id = None
        candidate.reviewed_at = None
        after = _node_snapshot(candidate)
        decision = ReviewDecision(
            node_candidate_id=candidate.id,
            candidate_revision_id=revision.id,
            decision=ReviewDecisionType.EDIT,
            reviewer_user_id=actor.user_id,
            rationale=rationale,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
        self._session.add(decision)
        await self._session.flush()
        if was_approved:
            self._session.add(
                GraphSyncOutbox(
                    course_id=candidate.course_id,
                    curriculum_edition_id=candidate.curriculum_edition_id,
                    node_candidate_id=candidate.id,
                    operation=GraphSyncOperation.DELETE,
                    payload_json={"candidate_id": str(candidate.id)},
                    review_decision_id=decision.id,
                    idempotency_key=self._outbox_key(
                        CandidateKind.NODE,
                        candidate.id,
                        candidate.revision_number,
                        GraphSyncOperation.DELETE,
                        decision.id,
                    ),
                )
            )
        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_EDITED,
            resource_type=AuditResourceType.NODE_CANDIDATE,
            resource_id=candidate.id,
            summary="Edited graph node candidate; re-approval required",
            before=before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def edit_relation(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        patch: RelationEdit,
        rationale: str,
    ) -> ReviewDecision:
        rationale = self._rationale(rationale)
        candidate = await self._get_relation(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            for_update=True,
        )
        if candidate.status in {CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED}:
            raise ReviewConflictError("terminal candidate cannot be edited")
        before = _relation_snapshot(candidate)
        was_approved = candidate.status is CandidateStatus.APPROVED
        revision = await self._revision_for_relation(candidate, actor.user_id, before)
        for field_name in patch.model_fields_set:
            if field_name == "properties":
                candidate.properties_json = patch.properties or {}
            elif field_name == "relationship_type":
                if patch.relationship_type is None:
                    raise ReviewConflictError("relationship_type cannot be null")
                candidate.relation_type = type(candidate.relation_type)[
                    patch.relationship_type.name
                ]
            else:
                value = getattr(patch, field_name)
                if (
                    field_name
                    in {
                        "source_node_candidate_id",
                        "target_node_candidate_id",
                    }
                    and value is None
                ):
                    raise ReviewConflictError(f"{field_name} cannot be null")
                setattr(candidate, field_name, value)
        if candidate.source_node_candidate_id == candidate.target_node_candidate_id:
            raise ReviewConflictError("relationship endpoints must be distinct")
        source, target = await self._relation_endpoints(candidate, require_approved=False)
        if not is_allowed_triple(
            _node_type(source), _relationship_type(candidate), _node_type(target)
        ):
            raise ReviewConflictError("edited relationship violates the explicit ontology")
        candidate.canonical_key = (
            f"{candidate.source_node_candidate_id}:"
            f"{candidate.relation_type.value}:"
            f"{candidate.target_node_candidate_id}"
        )
        candidate.revision_number += 1
        candidate.status = CandidateStatus.REVIEW_REQUIRED
        candidate.reviewed_by_user_id = None
        candidate.reviewed_at = None
        after = _relation_snapshot(candidate)
        decision = ReviewDecision(
            relation_candidate_id=candidate.id,
            candidate_revision_id=revision.id,
            decision=ReviewDecisionType.EDIT,
            reviewer_user_id=actor.user_id,
            rationale=rationale,
            before_snapshot_json=before,
            after_snapshot_json=after,
        )
        self._session.add(decision)
        await self._session.flush()
        if was_approved:
            self._session.add(
                GraphSyncOutbox(
                    course_id=candidate.course_id,
                    curriculum_edition_id=candidate.curriculum_edition_id,
                    relation_candidate_id=candidate.id,
                    operation=GraphSyncOperation.DELETE,
                    payload_json={"candidate_id": str(candidate.id)},
                    review_decision_id=decision.id,
                    idempotency_key=self._outbox_key(
                        CandidateKind.RELATION,
                        candidate.id,
                        candidate.revision_number,
                        GraphSyncOperation.DELETE,
                        decision.id,
                    ),
                )
            )
        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_EDITED,
            resource_type=AuditResourceType.RELATION_CANDIDATE,
            resource_id=candidate.id,
            summary="Edited graph relationship candidate; re-approval required",
            before=before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def merge_nodes(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        duplicate_candidate_id: UUID,
        survivor_candidate_id: UUID,
        rationale: str,
    ) -> ReviewDecision:
        """Merge one duplicate into a survivor and require survivor re-approval.

        Relationship rewrites are preflighted as a unit.  A merge that would
        create a self-loop or a semantic duplicate fails closed so a teacher
        can resolve the affected relationships explicitly first.
        """

        rationale = self._rationale(rationale)
        if duplicate_candidate_id == survivor_candidate_id:
            raise ReviewConflictError("merge candidates must be distinct")
        locked_nodes = list(
            (
                await self._session.scalars(
                    select(GraphNodeCandidate)
                    .where(
                        GraphNodeCandidate.id.in_((duplicate_candidate_id, survivor_candidate_id)),
                        GraphNodeCandidate.course_id == actor.course_id,
                        GraphNodeCandidate.curriculum_edition_id == curriculum_edition_id,
                    )
                    .with_for_update()
                )
            ).all()
        )
        by_id = {candidate.id: candidate for candidate in locked_nodes}
        duplicate = by_id.get(duplicate_candidate_id)
        survivor = by_id.get(survivor_candidate_id)
        if duplicate is None or survivor is None:
            raise ReviewNotFoundError("merge candidate not found")
        if duplicate.node_type is not survivor.node_type:
            raise ReviewConflictError("node merges require the same ontology type")
        if duplicate.status in {CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED}:
            raise ReviewConflictError("duplicate candidate is already terminal")
        if survivor.status in {CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED}:
            raise ReviewConflictError("survivor candidate is terminal")

        affected_relations = list(
            (
                await self._session.scalars(
                    select(GraphRelationCandidate)
                    .where(
                        GraphRelationCandidate.course_id == actor.course_id,
                        GraphRelationCandidate.curriculum_edition_id == curriculum_edition_id,
                        (
                            (GraphRelationCandidate.source_node_candidate_id == duplicate.id)
                            | (GraphRelationCandidate.target_node_candidate_id == duplicate.id)
                        ),
                        GraphRelationCandidate.status.not_in(
                            (CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED)
                        ),
                    )
                    .with_for_update()
                )
            ).all()
        )
        rewrites: list[tuple[GraphRelationCandidate, UUID, UUID]] = []
        for relation in affected_relations:
            new_source = (
                survivor.id
                if relation.source_node_candidate_id == duplicate.id
                else relation.source_node_candidate_id
            )
            new_target = (
                survivor.id
                if relation.target_node_candidate_id == duplicate.id
                else relation.target_node_candidate_id
            )
            if new_source == new_target:
                raise ReviewConflictError(
                    "node merge would create a self-loop; resolve that relationship first"
                )
            semantic_duplicate = await self._session.scalar(
                select(GraphRelationCandidate.id).where(
                    GraphRelationCandidate.id != relation.id,
                    GraphRelationCandidate.curriculum_edition_id == curriculum_edition_id,
                    GraphRelationCandidate.source_node_candidate_id == new_source,
                    GraphRelationCandidate.target_node_candidate_id == new_target,
                    GraphRelationCandidate.relation_type == relation.relation_type,
                    GraphRelationCandidate.status.not_in(
                        (CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED)
                    ),
                )
            )
            if semantic_duplicate is not None:
                raise ReviewConflictError(
                    "node merge would duplicate a relationship; merge relationships first"
                )
            rewrites.append((relation, new_source, new_target))

        duplicate_before = _node_snapshot(duplicate)
        survivor_before = _node_snapshot(survivor)
        duplicate_revision = await self._revision_for_node(
            duplicate, actor.user_id, duplicate_before
        )
        await self._copy_node_support(duplicate.id, survivor.id)
        survivor_was_approved = survivor.status is CandidateStatus.APPROVED
        if survivor_was_approved:
            await self._revision_for_node(survivor, actor.user_id, survivor_before)
            survivor.revision_number += 1
            survivor.status = CandidateStatus.REVIEW_REQUIRED
            survivor.reviewed_by_user_id = None
            survivor.reviewed_at = None

        duplicate_was_approved = duplicate.status is CandidateStatus.APPROVED
        duplicate.status = CandidateStatus.SUPERSEDED
        duplicate.superseded_by_node_candidate_id = survivor.id
        duplicate.reviewed_by_user_id = actor.user_id
        duplicate.reviewed_at = datetime.now(UTC)
        duplicate_after = _node_snapshot(duplicate)
        duplicate_after["superseded_by_node_candidate_id"] = str(survivor.id)
        duplicate_after["survivor_requires_reapproval"] = survivor_was_approved
        duplicate_after["rewired_relation_ids"] = [str(relation.id) for relation, _, _ in rewrites]
        decision = ReviewDecision(
            node_candidate_id=duplicate.id,
            candidate_revision_id=duplicate_revision.id,
            decision=ReviewDecisionType.MERGE,
            reviewer_user_id=actor.user_id,
            rationale=rationale,
            before_snapshot_json=duplicate_before,
            after_snapshot_json=duplicate_after,
        )
        self._session.add(decision)
        await self._session.flush()
        self._session.add(
            CandidateMergeLineage(
                merged_node_candidate_id=duplicate.id,
                surviving_node_candidate_id=survivor.id,
                review_decision_id=decision.id,
                merged_by_user_id=actor.user_id,
                rationale=rationale,
            )
        )
        if duplicate_was_approved:
            self._add_delete_outbox(
                candidate=duplicate,
                kind=CandidateKind.NODE,
                decision_id=decision.id,
            )
        if survivor_was_approved:
            self._add_delete_outbox(
                candidate=survivor,
                kind=CandidateKind.NODE,
                decision_id=decision.id,
            )

        for relation, new_source, new_target in rewrites:
            before = _relation_snapshot(relation)
            relation_was_approved = relation.status is CandidateStatus.APPROVED
            revision = await self._revision_for_relation(relation, actor.user_id, before)
            relation.source_node_candidate_id = new_source
            relation.target_node_candidate_id = new_target
            relation.canonical_key = f"{new_source}:{relation.relation_type.value}:{new_target}"
            relation.revision_number += 1
            relation.status = CandidateStatus.REVIEW_REQUIRED
            relation.reviewed_by_user_id = None
            relation.reviewed_at = None
            after = _relation_snapshot(relation)
            relation_decision = ReviewDecision(
                relation_candidate_id=relation.id,
                candidate_revision_id=revision.id,
                decision=ReviewDecisionType.EDIT,
                reviewer_user_id=actor.user_id,
                rationale=f"Rewired during node merge: {rationale}",
                before_snapshot_json=before,
                after_snapshot_json=after,
            )
            self._session.add(relation_decision)
            await self._session.flush()
            if relation_was_approved:
                self._add_delete_outbox(
                    candidate=relation,
                    kind=CandidateKind.RELATION,
                    decision_id=relation_decision.id,
                )

        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_MERGED,
            resource_type=AuditResourceType.NODE_CANDIDATE,
            resource_id=duplicate.id,
            summary="Merged duplicate graph node into survivor; re-approval enforced",
            before=duplicate_before,
            after=duplicate_after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def merge_relations(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        duplicate_candidate_id: UUID,
        survivor_candidate_id: UUID,
        rationale: str,
    ) -> ReviewDecision:
        rationale = self._rationale(rationale)
        if duplicate_candidate_id == survivor_candidate_id:
            raise ReviewConflictError("merge candidates must be distinct")
        candidates = list(
            (
                await self._session.scalars(
                    select(GraphRelationCandidate)
                    .where(
                        GraphRelationCandidate.id.in_(
                            (duplicate_candidate_id, survivor_candidate_id)
                        ),
                        GraphRelationCandidate.course_id == actor.course_id,
                        GraphRelationCandidate.curriculum_edition_id == curriculum_edition_id,
                    )
                    .with_for_update()
                )
            ).all()
        )
        by_id = {candidate.id: candidate for candidate in candidates}
        duplicate = by_id.get(duplicate_candidate_id)
        survivor = by_id.get(survivor_candidate_id)
        if duplicate is None or survivor is None:
            raise ReviewNotFoundError("merge candidate not found")
        duplicate_identity = (
            duplicate.source_node_candidate_id,
            duplicate.target_node_candidate_id,
            duplicate.relation_type,
        )
        survivor_identity = (
            survivor.source_node_candidate_id,
            survivor.target_node_candidate_id,
            survivor.relation_type,
        )
        if duplicate_identity != survivor_identity:
            raise ReviewConflictError("relationship merges require identical typed endpoints")
        if duplicate.status in {CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED}:
            raise ReviewConflictError("duplicate candidate is already terminal")
        if survivor.status in {CandidateStatus.REJECTED, CandidateStatus.SUPERSEDED}:
            raise ReviewConflictError("survivor candidate is terminal")

        duplicate_before = _relation_snapshot(duplicate)
        survivor_before = _relation_snapshot(survivor)
        duplicate_revision = await self._revision_for_relation(
            duplicate, actor.user_id, duplicate_before
        )
        await self._copy_relation_support(duplicate.id, survivor.id)
        survivor_was_approved = survivor.status is CandidateStatus.APPROVED
        if survivor_was_approved:
            await self._revision_for_relation(survivor, actor.user_id, survivor_before)
            survivor.revision_number += 1
            survivor.status = CandidateStatus.REVIEW_REQUIRED
            survivor.reviewed_by_user_id = None
            survivor.reviewed_at = None

        duplicate_was_approved = duplicate.status is CandidateStatus.APPROVED
        duplicate.status = CandidateStatus.SUPERSEDED
        duplicate.superseded_by_relation_candidate_id = survivor.id
        duplicate.reviewed_by_user_id = actor.user_id
        duplicate.reviewed_at = datetime.now(UTC)
        after = _relation_snapshot(duplicate)
        after["superseded_by_relation_candidate_id"] = str(survivor.id)
        after["survivor_requires_reapproval"] = survivor_was_approved
        decision = ReviewDecision(
            relation_candidate_id=duplicate.id,
            candidate_revision_id=duplicate_revision.id,
            decision=ReviewDecisionType.MERGE,
            reviewer_user_id=actor.user_id,
            rationale=rationale,
            before_snapshot_json=duplicate_before,
            after_snapshot_json=after,
        )
        self._session.add(decision)
        await self._session.flush()
        self._session.add(
            CandidateMergeLineage(
                merged_relation_candidate_id=duplicate.id,
                surviving_relation_candidate_id=survivor.id,
                review_decision_id=decision.id,
                merged_by_user_id=actor.user_id,
                rationale=rationale,
            )
        )
        if duplicate_was_approved:
            self._add_delete_outbox(
                candidate=duplicate,
                kind=CandidateKind.RELATION,
                decision_id=decision.id,
            )
        if survivor_was_approved:
            self._add_delete_outbox(
                candidate=survivor,
                kind=CandidateKind.RELATION,
                decision_id=decision.id,
            )
        await self._audit_candidate(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_MERGED,
            resource_type=AuditResourceType.RELATION_CANDIDATE,
            resource_id=duplicate.id,
            summary="Merged duplicate graph relationship into survivor",
            before=duplicate_before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()
        return decision

    async def approve_document_version(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        document_version_id: UUID,
        rationale: str,
    ) -> None:
        rationale = self._rationale(rationale)
        document, version = await self._document_version(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            document_version_id=document_version_id,
            for_update=True,
        )
        if document.status in {
            DocumentStatus.ARCHIVED,
            DocumentStatus.QUARANTINED,
            DocumentStatus.PUBLISHED,
        } or version.status in {
            DocumentVersionStatus.ARCHIVED,
            DocumentVersionStatus.FAILED,
            DocumentVersionStatus.SUPERSEDED,
            DocumentVersionStatus.PUBLISHED,
        }:
            raise ReviewConflictError("document version is not reviewable")
        chunks = list(
            (
                await self._session.scalars(
                    select(DocumentChunk)
                    .where(DocumentChunk.document_version_id == version.id)
                    .with_for_update()
                )
            ).all()
        )
        if not chunks:
            raise ReviewConflictError("document has no extracted chunks")
        blocked = [
            chunk
            for chunk in chunks
            if chunk.extraction_status
            in {ChunkExtractionStatus.OCR_REQUIRED, ChunkExtractionStatus.REJECTED}
        ]
        if blocked:
            raise ReviewConflictError("document has OCR-required or rejected chunks")
        before = {
            "document_status": document.status.value,
            "version_status": version.status.value,
            "chunk_statuses": {str(chunk.id): chunk.extraction_status.value for chunk in chunks},
        }
        for chunk in chunks:
            chunk.extraction_status = ChunkExtractionStatus.APPROVED
        document.status = DocumentStatus.APPROVED
        version.status = DocumentVersionStatus.APPROVED
        after = {
            "document_status": document.status.value,
            "version_status": version.status.value,
            "chunk_statuses": {str(chunk.id): chunk.extraction_status.value for chunk in chunks},
        }
        await self._audit_document(
            actor=actor,
            resource_type=AuditResourceType.DOCUMENT_VERSION,
            resource_id=version.id,
            summary="Approved source document version and extracted chunks",
            before=before,
            after=after,
            rationale=rationale,
        )
        await self._session.flush()

    async def publish_document_version(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        document_version_id: UUID,
        rationale: str,
        priority: int = 50,
    ) -> DocumentPublication:
        rationale = self._rationale(rationale)
        if not 0 <= priority <= 100:
            raise ValueError("publication priority must be between 0 and 100")
        document, version = await self._document_version(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            document_version_id=document_version_id,
            for_update=True,
        )
        if document.status is not DocumentStatus.APPROVED:
            raise ReviewConflictError("source document must be approved before publication")
        if version.status is not DocumentVersionStatus.APPROVED:
            raise ReviewConflictError("source version must be approved before publication")
        unapproved_count = await self._session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.document_version_id == version.id,
                DocumentChunk.extraction_status != ChunkExtractionStatus.APPROVED,
            )
        )
        if unapproved_count:
            raise ReviewConflictError("every source chunk must be approved before publication")
        existing = await self._session.scalar(
            select(DocumentPublication)
            .where(
                DocumentPublication.course_id == actor.course_id,
                DocumentPublication.document_version_id == version.id,
            )
            .with_for_update()
        )
        if existing is not None and existing.status is PublicationStatus.PUBLISHED:
            raise ReviewConflictError("document version is already published")
        now = datetime.now(UTC)
        publication = existing or DocumentPublication(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            document_version_id=version.id,
            published_by_user_id=actor.user_id,
        )
        publication.curriculum_edition_id = curriculum_edition_id
        publication.status = PublicationStatus.PUBLISHED
        publication.priority = priority
        publication.published_by_user_id = actor.user_id
        publication.published_at = now
        publication.unpublished_at = None
        publication.notes = rationale
        self._session.add(publication)
        before = {
            "document_status": document.status.value,
            "version_status": version.status.value,
        }
        document.status = DocumentStatus.PUBLISHED
        version.status = DocumentVersionStatus.PUBLISHED
        edition = await self._session.get(CurriculumEdition, curriculum_edition_id)
        if edition is None or edition.course_id != actor.course_id:
            raise ReviewNotFoundError("curriculum edition not found")
        if edition.status is not CurriculumEditionStatus.PUBLISHED:
            edition.status = CurriculumEditionStatus.PUBLISHED
            edition.published_at = now
        await self._audit_document(
            actor=actor,
            resource_type=AuditResourceType.DOCUMENT_VERSION,
            resource_id=version.id,
            summary="Published approved source document version",
            before=before,
            after={
                "document_status": document.status.value,
                "version_status": version.status.value,
                "publication_status": publication.status.value,
                "curriculum_edition_id": str(curriculum_edition_id),
            },
            rationale=rationale,
        )
        await self._session.flush()
        return publication

    async def _get_node(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        for_update: bool = False,
    ) -> GraphNodeCandidate:
        statement = select(GraphNodeCandidate).where(
            GraphNodeCandidate.id == candidate_id,
            GraphNodeCandidate.course_id == course_id,
            GraphNodeCandidate.curriculum_edition_id == curriculum_edition_id,
        )
        if for_update:
            statement = statement.with_for_update()
        candidate = await self._session.scalar(statement)
        if candidate is None:
            raise ReviewNotFoundError("node candidate not found")
        return candidate

    async def _get_relation(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        candidate_id: UUID,
        for_update: bool = False,
    ) -> GraphRelationCandidate:
        statement = select(GraphRelationCandidate).where(
            GraphRelationCandidate.id == candidate_id,
            GraphRelationCandidate.course_id == course_id,
            GraphRelationCandidate.curriculum_edition_id == curriculum_edition_id,
        )
        if for_update:
            statement = statement.with_for_update()
        candidate = await self._session.scalar(statement)
        if candidate is None:
            raise ReviewNotFoundError("relationship candidate not found")
        return candidate

    def _evidence_statement(
        self,
        support_model: type[NodeCandidateEvidenceSupport] | type[RelationCandidateEvidenceSupport],
        candidate_column: Any,
        candidate_id: UUID,
    ) -> Select[tuple[Evidence, DocumentChunk, SourceDocumentVersion, SourceDocument, Any, Any]]:
        return (
            select(
                Evidence,
                DocumentChunk,
                SourceDocumentVersion,
                SourceDocument,
                support_model.support_role,
                support_model.confidence,
            )
            .join(support_model, support_model.evidence_id == Evidence.id)
            .join(DocumentChunk, DocumentChunk.id == Evidence.source_chunk_id)
            .join(
                SourceDocumentVersion,
                SourceDocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(SourceDocument, SourceDocument.id == SourceDocumentVersion.document_id)
            .where(candidate_column == candidate_id)
            .order_by(Evidence.created_at, Evidence.id)
        )

    async def _node_evidence(self, candidate: GraphNodeCandidate) -> list[_EvidenceRow]:
        result = await self._session.execute(
            self._evidence_statement(
                NodeCandidateEvidenceSupport,
                NodeCandidateEvidenceSupport.node_candidate_id,
                candidate.id,
            )
        )
        return [
            _EvidenceRow(
                evidence=e,
                chunk=c,
                version=v,
                document=d,
                support_role=r,
                confidence=x,
            )
            for e, c, v, d, r, x in result.all()
        ]

    async def _relation_evidence(self, candidate: GraphRelationCandidate) -> list[_EvidenceRow]:
        result = await self._session.execute(
            self._evidence_statement(
                RelationCandidateEvidenceSupport,
                RelationCandidateEvidenceSupport.relation_candidate_id,
                candidate.id,
            )
        )
        return [
            _EvidenceRow(
                evidence=e,
                chunk=c,
                version=v,
                document=d,
                support_role=r,
                confidence=x,
            )
            for e, c, v, d, r, x in result.all()
        ]

    def _validate_evidence(
        self,
        rows: Sequence[_EvidenceRow],
        course_id: UUID,
        curriculum_edition_id: UUID,
    ) -> None:
        if not rows:
            raise EvidenceGroundingError("candidate has no source evidence")
        if not any(row.support_role is EvidenceSupportRole.PRIMARY for row in rows):
            raise EvidenceGroundingError("candidate has no primary source evidence")
        for row in rows:
            evidence = row.evidence
            chunk = row.chunk
            document = row.document
            if document.course_id != course_id or document.curriculum_edition_id not in {
                None,
                curriculum_edition_id,
            }:
                raise EvidenceGroundingError("evidence is outside the candidate scope")
            if evidence.status is not EvidenceStatus.GROUNDED:
                raise EvidenceGroundingError("evidence has not passed grounding validation")
            if evidence.chunk_content_sha256 != chunk.content_sha256:
                raise EvidenceGroundingError("evidence refers to a stale source chunk")
            if _sha256_text(chunk.content) != chunk.content_sha256:
                raise EvidenceGroundingError("source chunk checksum no longer matches")
            if not 0 <= evidence.char_start < evidence.char_end <= len(chunk.content):
                raise EvidenceGroundingError("evidence character span is invalid")
            if chunk.content[evidence.char_start : evidence.char_end] != evidence.evidence_snippet:
                raise EvidenceGroundingError("evidence is not an exact source span")
            if _sha256_text(evidence.evidence_snippet) != evidence.evidence_sha256:
                raise EvidenceGroundingError("evidence checksum no longer matches")

    async def _relation_endpoints(
        self,
        candidate: GraphRelationCandidate,
        *,
        require_approved: bool,
    ) -> tuple[GraphNodeCandidate, GraphNodeCandidate]:
        nodes = list(
            (
                await self._session.scalars(
                    select(GraphNodeCandidate).where(
                        GraphNodeCandidate.id.in_(
                            (
                                candidate.source_node_candidate_id,
                                candidate.target_node_candidate_id,
                            )
                        ),
                        GraphNodeCandidate.course_id == candidate.course_id,
                        GraphNodeCandidate.curriculum_edition_id == candidate.curriculum_edition_id,
                    )
                )
            ).all()
        )
        by_id = {node.id: node for node in nodes}
        source = by_id.get(candidate.source_node_candidate_id)
        target = by_id.get(candidate.target_node_candidate_id)
        if source is None or target is None:
            raise ReviewConflictError("relationship endpoints are missing or out of scope")
        if require_approved and (
            source.status is not CandidateStatus.APPROVED
            or target.status is not CandidateStatus.APPROVED
        ):
            raise ReviewConflictError("relationship endpoints must be approved first")
        return source, target

    async def _copy_node_support(self, duplicate_id: UUID, survivor_id: UUID) -> None:
        existing_ids = set(
            (
                await self._session.scalars(
                    select(NodeCandidateEvidenceSupport.evidence_id).where(
                        NodeCandidateEvidenceSupport.node_candidate_id == survivor_id
                    )
                )
            ).all()
        )
        supports = list(
            (
                await self._session.scalars(
                    select(NodeCandidateEvidenceSupport).where(
                        NodeCandidateEvidenceSupport.node_candidate_id == duplicate_id
                    )
                )
            ).all()
        )
        for support in supports:
            if support.evidence_id not in existing_ids:
                self._session.add(
                    NodeCandidateEvidenceSupport(
                        node_candidate_id=survivor_id,
                        evidence_id=support.evidence_id,
                        support_role=support.support_role,
                        confidence=support.confidence,
                        extraction_span_json=support.extraction_span_json,
                    )
                )
                existing_ids.add(support.evidence_id)

    async def _copy_relation_support(self, duplicate_id: UUID, survivor_id: UUID) -> None:
        existing_ids = set(
            (
                await self._session.scalars(
                    select(RelationCandidateEvidenceSupport.evidence_id).where(
                        RelationCandidateEvidenceSupport.relation_candidate_id == survivor_id
                    )
                )
            ).all()
        )
        supports = list(
            (
                await self._session.scalars(
                    select(RelationCandidateEvidenceSupport).where(
                        RelationCandidateEvidenceSupport.relation_candidate_id == duplicate_id
                    )
                )
            ).all()
        )
        for support in supports:
            if support.evidence_id not in existing_ids:
                self._session.add(
                    RelationCandidateEvidenceSupport(
                        relation_candidate_id=survivor_id,
                        evidence_id=support.evidence_id,
                        support_role=support.support_role,
                        confidence=support.confidence,
                        extraction_span_json=support.extraction_span_json,
                    )
                )
                existing_ids.add(support.evidence_id)

    async def _revision_for_node(
        self,
        candidate: GraphNodeCandidate,
        user_id: UUID,
        snapshot: dict[str, Any],
    ) -> CandidateRevision:
        existing = await self._session.scalar(
            select(CandidateRevision).where(
                CandidateRevision.node_candidate_id == candidate.id,
                CandidateRevision.revision_number == candidate.revision_number,
            )
        )
        if existing is not None:
            return existing
        revision = CandidateRevision(
            node_candidate_id=candidate.id,
            revision_number=candidate.revision_number,
            snapshot_json=snapshot,
            diff_json={},
            change_summary="Teacher review snapshot",
            created_by_user_id=user_id,
        )
        self._session.add(revision)
        await self._session.flush()
        return revision

    async def _revision_for_relation(
        self,
        candidate: GraphRelationCandidate,
        user_id: UUID,
        snapshot: dict[str, Any],
    ) -> CandidateRevision:
        existing = await self._session.scalar(
            select(CandidateRevision).where(
                CandidateRevision.relation_candidate_id == candidate.id,
                CandidateRevision.revision_number == candidate.revision_number,
            )
        )
        if existing is not None:
            return existing
        revision = CandidateRevision(
            relation_candidate_id=candidate.id,
            revision_number=candidate.revision_number,
            snapshot_json=snapshot,
            diff_json={},
            change_summary="Teacher review snapshot",
            created_by_user_id=user_id,
        )
        self._session.add(revision)
        await self._session.flush()
        return revision

    def _node_projection(
        self,
        candidate: GraphNodeCandidate,
        decision_id: UUID,
        evidence: Sequence[_EvidenceRow],
    ) -> ApprovedGraphNode:
        properties = dict(candidate.properties_json)
        if candidate.formula_latex:
            properties["formula_latex"] = candidate.formula_latex
        properties["origin"] = candidate.origin.value
        properties["confidence"] = candidate.confidence
        return ApprovedGraphNode(
            candidate_id=str(candidate.id),
            scope=GraphScope(
                course_id=str(candidate.course_id),
                curriculum_edition_id=str(candidate.curriculum_edition_id),
            ),
            node_type=_node_type(candidate),
            canonical_key=candidate.canonical_key,
            label=candidate.label,
            description=candidate.description,
            properties=properties,
            evidence=tuple(self._graph_evidence(row) for row in evidence),
            review_decision_id=str(decision_id),
            review_revision=candidate.revision_number,
        )

    def _relation_projection(
        self,
        candidate: GraphRelationCandidate,
        source: GraphNodeCandidate,
        target: GraphNodeCandidate,
        decision_id: UUID,
        evidence: Sequence[_EvidenceRow],
    ) -> ApprovedGraphRelationship:
        properties = dict(candidate.properties_json)
        if candidate.description:
            properties["description"] = candidate.description
        properties["origin"] = candidate.origin.value
        properties["confidence"] = candidate.confidence
        return ApprovedGraphRelationship(
            candidate_id=str(candidate.id),
            scope=GraphScope(
                course_id=str(candidate.course_id),
                curriculum_edition_id=str(candidate.curriculum_edition_id),
            ),
            relationship_type=_relationship_type(candidate),
            source_candidate_id=str(source.id),
            target_candidate_id=str(target.id),
            source_node_type=_node_type(source),
            target_node_type=_node_type(target),
            properties=properties,
            evidence=tuple(self._graph_evidence(row) for row in evidence),
            review_decision_id=str(decision_id),
            review_revision=candidate.revision_number,
        )

    @staticmethod
    def _graph_evidence(row: _EvidenceRow) -> GraphEvidence:
        chunk = row.chunk
        locator_type = chunk.locator_type.value
        if locator_type not in {"page", "slide", "paragraph", "sheet_row", "line"}:
            raise EvidenceGroundingError("unsupported source locator cannot be approved")
        return GraphEvidence(
            source_document_id=str(row.document.id),
            source_chunk_id=str(chunk.id),
            source_file=row.document.source_filename,
            document_version_id=str(row.version.id),
            document_sha256=row.version.source_file_sha256,
            chunk_checksum=chunk.content_sha256,
            chapter=chunk.section_path[0] if chunk.section_path else None,
            section_path=tuple(chunk.section_path),
            page_number=chunk.physical_page,
            page_label=chunk.printed_page_label,
            slide_number=chunk.slide_number,
            locator_type=locator_type,
            locator_start=chunk.locator_start,
            locator_end=chunk.locator_end,
            quote=row.evidence.evidence_snippet,
            quote_start=row.evidence.char_start,
            quote_end=row.evidence.char_end,
        )

    @staticmethod
    def _review_evidence(row: _EvidenceRow) -> ReviewEvidenceItem:
        chunk = row.chunk
        return ReviewEvidenceItem(
            evidence_id=row.evidence.id,
            source_document_id=row.document.id,
            source_document_title=row.document.title,
            source_file_name=row.document.source_filename,
            document_version_id=row.version.id,
            source_file_sha256=row.version.source_file_sha256,
            source_chunk_id=chunk.id,
            source_chunk=chunk.content,
            evidence_snippet=row.evidence.evidence_snippet,
            char_start=row.evidence.char_start,
            char_end=row.evidence.char_end,
            locator={
                "type": chunk.locator_type.value,
                "start": chunk.locator_start,
                "end": chunk.locator_end,
                "physical_page": chunk.physical_page,
                "printed_page_label": chunk.printed_page_label,
                "slide_number": chunk.slide_number,
                "paragraph_start": chunk.paragraph_start,
                "paragraph_end": chunk.paragraph_end,
                "section_path": chunk.section_path,
                "bounding_boxes": chunk.bounding_boxes_json,
            },
            support_role=row.support_role,
            confidence=row.confidence,
        )

    async def _document_version(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        document_version_id: UUID,
        for_update: bool,
    ) -> tuple[SourceDocument, SourceDocumentVersion]:
        statement = (
            select(SourceDocument, SourceDocumentVersion)
            .join(
                SourceDocumentVersion,
                SourceDocumentVersion.document_id == SourceDocument.id,
            )
            .where(
                SourceDocumentVersion.id == document_version_id,
                SourceDocument.course_id == course_id,
                (
                    (SourceDocument.curriculum_edition_id.is_(None))
                    | (SourceDocument.curriculum_edition_id == curriculum_edition_id)
                ),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise ReviewNotFoundError("document version not found")
        return row[0], row[1]

    async def _audit_candidate(
        self,
        *,
        actor: CourseActor,
        event_type: AuditEventType,
        resource_type: AuditResourceType,
        resource_id: UUID,
        summary: str,
        before: dict[str, Any],
        after: dict[str, Any],
        rationale: str,
    ) -> None:
        await self._append_audit(
            actor=actor,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            before=before,
            after=after,
            context={"rationale": rationale},
        )

    async def _audit_document(
        self,
        *,
        actor: CourseActor,
        resource_type: AuditResourceType,
        resource_id: UUID,
        summary: str,
        before: dict[str, Any],
        after: dict[str, Any],
        rationale: str,
    ) -> None:
        await self._append_audit(
            actor=actor,
            event_type=AuditEventType.CANDIDATE_REVIEWED,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            before=before,
            after=after,
            context={"rationale": rationale},
        )

    async def _append_audit(
        self,
        *,
        actor: CourseActor,
        event_type: AuditEventType,
        resource_type: AuditResourceType,
        resource_id: UUID,
        summary: str,
        before: dict[str, Any],
        after: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        previous_hash = await self._session.scalar(
            select(AuditLog.event_sha256)
            .where(AuditLog.course_id == actor.course_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        payload = {
            "event_type": event_type.value,
            "resource_type": resource_type.value,
            "resource_id": str(resource_id),
            "actor_user_id": str(actor.user_id),
            "actor_session_id": str(actor.session_id),
            "course_id": str(actor.course_id),
            "summary": summary,
            "before": before,
            "after": after,
            "context": context,
            "previous_event_sha256": previous_hash,
        }
        event_hash = _sha256_text(_canonical_json(payload))
        self._session.add(
            AuditLog(
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
                course_id=actor.course_id,
                summary=summary,
                before_json=before,
                after_json=after,
                context_json=context,
                previous_event_sha256=previous_hash,
                event_sha256=event_hash,
            )
        )

    @staticmethod
    def _require_reviewable(status: CandidateStatus) -> None:
        if status not in {CandidateStatus.REVIEW_REQUIRED, CandidateStatus.IN_REVIEW}:
            raise ReviewConflictError(f"candidate status {status.value!r} is not approvable")

    @staticmethod
    def _rationale(value: str) -> str:
        rationale = value.strip()
        if not rationale:
            raise ValueError("review rationale is required")
        return rationale

    @staticmethod
    def _outbox_key(
        kind: CandidateKind,
        candidate_id: UUID,
        revision_number: int,
        operation: GraphSyncOperation,
        decision_id: UUID,
    ) -> str:
        return (
            f"{kind.value}:{candidate_id}:revision:{revision_number}:"
            f"{operation.value}:decision:{decision_id}"
        )

    def _add_delete_outbox(
        self,
        *,
        candidate: GraphNodeCandidate | GraphRelationCandidate,
        kind: CandidateKind,
        decision_id: UUID,
    ) -> None:
        self._session.add(
            GraphSyncOutbox(
                course_id=candidate.course_id,
                curriculum_edition_id=candidate.curriculum_edition_id,
                node_candidate_id=(candidate.id if kind is CandidateKind.NODE else None),
                relation_candidate_id=(candidate.id if kind is CandidateKind.RELATION else None),
                operation=GraphSyncOperation.DELETE,
                payload_json={"candidate_id": str(candidate.id)},
                review_decision_id=decision_id,
                idempotency_key=self._outbox_key(
                    kind,
                    candidate.id,
                    candidate.revision_number,
                    GraphSyncOperation.DELETE,
                    decision_id,
                ),
            )
        )


__all__ = [
    "CandidateKind",
    "EvidenceGroundingError",
    "NodeEdit",
    "RelationEdit",
    "ReviewCandidateDetail",
    "ReviewConflictError",
    "ReviewEvidenceItem",
    "ReviewNotFoundError",
    "ReviewQueueItem",
    "ReviewService",
]
