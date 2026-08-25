"""Authenticated student attachment and confirmation API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor, authenticate_course_actor, bearer_credential
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AttachmentKind,
    AttachmentStatus,
    MultimodalExtraction,
    MultimodalExtractionStatus,
    UserAttachment,
)
from quantum_agent.multimodal.runtime import (
    AttachmentConflictError,
    AttachmentNotFoundError,
    AttachmentRuntime,
    ConfirmationRequest,
)
from quantum_agent.multimodal.security import UploadValidationError
from quantum_agent.multimodal.storage import AttachmentStorageError

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/attachments",
    tags=["student-attachments"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]
UploadedFile = Annotated[UploadFile, File(description="Bounded image or course/project document")]


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    kind: str
    pipeline_name: str
    pipeline_version: str
    extraction_method: str
    status: MultimodalExtractionStatus
    confidence: float | None
    requires_confirmation: bool
    evidence: dict[str, Any]
    ambiguities: list[dict[str, Any]]
    confirmation: dict[str, Any]
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    course_id: UUID
    curriculum_edition_id: UUID
    kind: AttachmentKind
    filename: str
    media_type: str
    byte_size: int
    sha256: str
    status: AttachmentStatus
    validation: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False
    extraction: ExtractionResponse | None = None


def attachment_runtime_dependency(request: Request) -> AttachmentRuntime:
    runtime: Any = getattr(request.app.state, "attachment_runtime", None)
    if not isinstance(runtime, AttachmentRuntime):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attachment processing is unavailable",
        )
    return runtime


AttachmentService = Annotated[AttachmentRuntime, Depends(attachment_runtime_dependency)]


async def _actor(
    request: Request,
    session: AsyncSession,
    *,
    course_id: UUID,
) -> CourseActor:
    return await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
    )


def _extraction_response(extraction: MultimodalExtraction | None) -> ExtractionResponse | None:
    if extraction is None:
        return None
    return ExtractionResponse(
        id=extraction.id,
        kind=extraction.kind.value,
        pipeline_name=extraction.pipeline_name,
        pipeline_version=extraction.pipeline_version,
        extraction_method=extraction.extraction_method,
        status=extraction.status,
        confidence=extraction.confidence,
        requires_confirmation=extraction.requires_confirmation,
        evidence=extraction.evidence_json,
        ambiguities=extraction.ambiguities_json,
        confirmation=extraction.confirmation_json,
        failure_code=extraction.failure_code,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


def _attachment_response(
    attachment: UserAttachment,
    *,
    extraction: MultimodalExtraction | None,
    idempotent_replay: bool = False,
) -> AttachmentResponse:
    return AttachmentResponse(
        id=attachment.id,
        course_id=attachment.course_id,
        curriculum_edition_id=attachment.curriculum_edition_id,
        kind=attachment.kind,
        filename=attachment.original_filename,
        media_type=attachment.detected_media_type,
        byte_size=attachment.byte_size,
        sha256=attachment.content_sha256,
        status=attachment.status,
        validation=attachment.validation_json,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
        idempotent_replay=idempotent_replay,
        extraction=_extraction_response(extraction),
    )


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, UploadValidationError):
        return HTTPException(
            status_code=error.http_status, detail={"code": error.code, "message": error.detail}
        )
    if isinstance(error, AttachmentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, AttachmentConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, AttachmentStorageError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attachment storage is unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Attachment operation failed",
    )


@router.post("", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    request: Request,
    response: Response,
    course_id: UUID,
    curriculum_edition_id: UUID,
    file: UploadedFile,
    session: DatabaseSession,
    runtime: AttachmentService,
) -> AttachmentResponse:
    actor = await _actor(request, session, course_id=course_id)
    try:
        created = await runtime.create(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            upload=file,
        )
        await session.commit()
    except (
        UploadValidationError,
        AttachmentNotFoundError,
        AttachmentConflictError,
        AttachmentStorageError,
    ) as error:
        await session.rollback()
        raise _translate_error(error) from error
    if created.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return _attachment_response(
        created.attachment,
        extraction=created.extraction,
        idempotent_replay=created.idempotent_replay,
    )


@router.get("", response_model=list[AttachmentResponse])
async def list_attachments(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    session: DatabaseSession,
    runtime: AttachmentService,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AttachmentResponse]:
    actor = await _actor(request, session, course_id=course_id)
    try:
        attachments = await runtime.list_scoped(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            limit=limit,
            offset=offset,
        )
    except AttachmentNotFoundError as error:
        raise _translate_error(error) from error
    responses: list[AttachmentResponse] = []
    for attachment in attachments:
        extraction = await runtime.latest_extraction(session, attachment_id=attachment.id)
        responses.append(_attachment_response(attachment, extraction=extraction))
    return responses


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    attachment_id: UUID,
    session: DatabaseSession,
    runtime: AttachmentService,
) -> AttachmentResponse:
    actor = await _actor(request, session, course_id=course_id)
    try:
        attachment = await runtime.scoped_attachment(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            attachment_id=attachment_id,
        )
    except AttachmentNotFoundError as error:
        raise _translate_error(error) from error
    extraction = await runtime.latest_extraction(session, attachment_id=attachment.id)
    return _attachment_response(attachment, extraction=extraction)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    attachment_id: UUID,
    session: DatabaseSession,
    runtime: AttachmentService,
) -> Response:
    actor = await _actor(request, session, course_id=course_id)
    try:
        await runtime.delete(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            attachment_id=attachment_id,
        )
        await session.commit()
    except (AttachmentNotFoundError, AttachmentConflictError, AttachmentStorageError) as error:
        await session.rollback()
        raise _translate_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{attachment_id}/confirm", response_model=AttachmentResponse)
async def confirm_attachment_extraction(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    attachment_id: UUID,
    body: ConfirmationRequest,
    session: DatabaseSession,
    runtime: AttachmentService,
) -> AttachmentResponse:
    actor = await _actor(request, session, course_id=course_id)
    try:
        extraction = await runtime.confirm(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            attachment_id=attachment_id,
            confirmation=body,
        )
        attachment = await runtime.scoped_attachment(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            attachment_id=attachment_id,
        )
        await session.commit()
    except (AttachmentNotFoundError, AttachmentConflictError) as error:
        await session.rollback()
        raise _translate_error(error) from error
    return _attachment_response(attachment, extraction=extraction)


__all__ = [
    "AttachmentResponse",
    "ExtractionResponse",
    "attachment_runtime_dependency",
    "router",
]
