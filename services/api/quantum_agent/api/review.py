"""Teacher-only knowledge governance HTTP API."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import (
    TEACHER_ROLES,
    TEACHING_STAFF_ROLES,
    CourseActor,
    authenticate_course_actor,
    bearer_credential,
)
from quantum_agent.database import session_dependency
from quantum_agent.db_models import CandidateStatus
from quantum_agent.knowledge.review import (
    CandidateKind,
    EvidenceGroundingError,
    NodeEdit,
    RelationEdit,
    ReviewCandidateDetail,
    ReviewConflictError,
    ReviewNotFoundError,
    ReviewQueueItem,
    ReviewService,
)

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/knowledge",
    tags=["knowledge-governance"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


class RationaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rationale: str = Field(min_length=1, max_length=4000)


class CandidateActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    kind: CandidateKind
    action: Literal["approve", "reject", "edit", "merge"]
    decision_id: UUID
    projection_state: Literal["pending_upsert", "pending_delete", "not_published"]


class RejectRequest(RationaleRequest):
    kind: CandidateKind


class EditNodeRequest(RationaleRequest):
    patch: NodeEdit


class EditRelationRequest(RationaleRequest):
    patch: RelationEdit


class MergeRequest(RationaleRequest):
    duplicate_candidate_id: UUID
    survivor_candidate_id: UUID


class PublishDocumentRequest(RationaleRequest):
    priority: int = Field(default=50, ge=0, le=100)


class DocumentActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_version_id: UUID
    action: Literal["approve", "publish"]
    student_visible: bool


async def _actor(
    request: Request,
    session: AsyncSession,
    course_id: UUID,
    *,
    mutate: bool,
) -> CourseActor:
    return await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
        allowed_roles=TEACHER_ROLES if mutate else TEACHING_STAFF_ROLES,
    )


def _translate_review_error(error: Exception) -> HTTPException:
    if isinstance(error, ReviewNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, (ReviewConflictError, EvidenceGroundingError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Knowledge review failed",
    )


@router.get("/review-queue", response_model=list[ReviewQueueItem])
async def review_queue(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    session: DatabaseSession,
    statuses: Annotated[list[CandidateStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReviewQueueItem]:
    await _actor(request, session, course_id, mutate=False)
    return await ReviewService(session).list_queue(
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
        statuses=statuses or [CandidateStatus.REVIEW_REQUIRED, CandidateStatus.IN_REVIEW],
        limit=limit,
        offset=offset,
    )


@router.get("/nodes/{candidate_id}", response_model=ReviewCandidateDetail)
async def node_detail(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    session: DatabaseSession,
) -> ReviewCandidateDetail:
    await _actor(request, session, course_id, mutate=False)
    try:
        return await ReviewService(session).get_node_detail(
            course_id=course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
        )
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        raise _translate_review_error(error) from error


@router.get("/relations/{candidate_id}", response_model=ReviewCandidateDetail)
async def relation_detail(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    session: DatabaseSession,
) -> ReviewCandidateDetail:
    await _actor(request, session, course_id, mutate=False)
    try:
        return await ReviewService(session).get_relation_detail(
            course_id=course_id,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
        )
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        raise _translate_review_error(error) from error


@router.post("/nodes/{candidate_id}/approve", response_model=CandidateActionResponse)
async def approve_node(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    body: RationaleRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).approve_node(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=candidate_id,
        kind=CandidateKind.NODE,
        action="approve",
        decision_id=decision.id,
        projection_state="pending_upsert",
    )


@router.post("/relations/{candidate_id}/approve", response_model=CandidateActionResponse)
async def approve_relation(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    body: RationaleRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).approve_relation(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=candidate_id,
        kind=CandidateKind.RELATION,
        action="approve",
        decision_id=decision.id,
        projection_state="pending_upsert",
    )


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateActionResponse)
async def reject_candidate(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    body: RejectRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).reject_candidate(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            kind=body.kind,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=candidate_id,
        kind=body.kind,
        action="reject",
        decision_id=decision.id,
        projection_state="pending_delete",
    )


@router.post("/nodes/{candidate_id}/edit", response_model=CandidateActionResponse)
async def edit_node(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    body: EditNodeRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).edit_node(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            patch=body.patch,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=candidate_id,
        kind=CandidateKind.NODE,
        action="edit",
        decision_id=decision.id,
        projection_state="pending_delete",
    )


@router.post("/relations/{candidate_id}/edit", response_model=CandidateActionResponse)
async def edit_relation(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    body: EditRelationRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).edit_relation(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            candidate_id=candidate_id,
            patch=body.patch,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=candidate_id,
        kind=CandidateKind.RELATION,
        action="edit",
        decision_id=decision.id,
        projection_state="pending_delete",
    )


@router.post("/merge/nodes", response_model=CandidateActionResponse)
async def merge_nodes(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    body: MergeRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).merge_nodes(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            duplicate_candidate_id=body.duplicate_candidate_id,
            survivor_candidate_id=body.survivor_candidate_id,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=body.duplicate_candidate_id,
        kind=CandidateKind.NODE,
        action="merge",
        decision_id=decision.id,
        projection_state="pending_delete",
    )


@router.post("/merge/relations", response_model=CandidateActionResponse)
async def merge_relations(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    body: MergeRequest,
    session: DatabaseSession,
) -> CandidateActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        decision = await ReviewService(session).merge_relations(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            duplicate_candidate_id=body.duplicate_candidate_id,
            survivor_candidate_id=body.survivor_candidate_id,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return CandidateActionResponse(
        candidate_id=body.duplicate_candidate_id,
        kind=CandidateKind.RELATION,
        action="merge",
        decision_id=decision.id,
        projection_state="pending_delete",
    )


@router.post(
    "/documents/{document_version_id}/approve",
    response_model=DocumentActionResponse,
)
async def approve_document(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    document_version_id: UUID,
    body: RationaleRequest,
    session: DatabaseSession,
) -> DocumentActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        await ReviewService(session).approve_document_version(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            document_version_id=document_version_id,
            rationale=body.rationale,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return DocumentActionResponse(
        document_version_id=document_version_id,
        action="approve",
        student_visible=False,
    )


@router.post(
    "/documents/{document_version_id}/publish",
    response_model=DocumentActionResponse,
)
async def publish_document(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    document_version_id: UUID,
    body: PublishDocumentRequest,
    session: DatabaseSession,
) -> DocumentActionResponse:
    actor = await _actor(request, session, course_id, mutate=True)
    try:
        await ReviewService(session).publish_document_version(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            document_version_id=document_version_id,
            rationale=body.rationale,
            priority=body.priority,
        )
        await session.commit()
    except (ReviewNotFoundError, ReviewConflictError, EvidenceGroundingError) as error:
        await session.rollback()
        raise _translate_review_error(error) from error
    return DocumentActionResponse(
        document_version_id=document_version_id,
        action="publish",
        student_visible=True,
    )


__all__ = ["router"]
