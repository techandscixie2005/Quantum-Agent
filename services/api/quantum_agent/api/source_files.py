"""Authenticated access to immutable, teacher-published course source files."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import authenticate_course_actor, bearer_credential
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    DocumentPublication,
    DocumentStatus,
    DocumentVersionStatus,
    PublicationStatus,
    SourceDocument,
    SourceDocumentVersion,
)
from quantum_agent.knowledge.source_manifest import sha256_file

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/sources",
    tags=["published-course-sources"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]

_SUPPORTED_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_MAX_RANGE_HEADER_CHARACTERS = 200


class SourceBoundaryError(ValueError):
    """A stored source path does not resolve inside the configured boundary."""


class SourceUnavailableError(FileNotFoundError):
    """A stored source no longer resolves to a regular file."""


@dataclass(frozen=True, slots=True)
class SourceFileRepository:
    """Resolve database paths under one explicit repository/knowledge root.

    Database paths are repository-relative.  Absolute paths, Windows drive
    paths, traversal, and symlink escapes fail closed.
    """

    repository_root: Path
    knowledge_root: Path = Path("knowledge")

    def __post_init__(self) -> None:
        repository = self.repository_root.expanduser().resolve()
        configured_knowledge = self.knowledge_root
        windows_knowledge = PureWindowsPath(str(configured_knowledge))
        if (
            configured_knowledge.is_absolute()
            or windows_knowledge.is_absolute()
            or windows_knowledge.drive
            or ".." in configured_knowledge.parts
            or configured_knowledge == Path(".")
        ):
            raise SourceBoundaryError("knowledge root must be a safe relative path")
        knowledge = (repository / configured_knowledge).resolve()
        try:
            knowledge.relative_to(repository)
        except ValueError as error:
            raise SourceBoundaryError("knowledge root escapes repository") from error
        object.__setattr__(self, "repository_root", repository)
        object.__setattr__(self, "knowledge_root", knowledge)

    def resolve(self, stored_path: str) -> Path:
        if not stored_path or "\x00" in stored_path or "\\" in stored_path:
            raise SourceBoundaryError("invalid stored source path")
        relative = Path(stored_path)
        windows_path = PureWindowsPath(stored_path)
        if (
            relative.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or ".." in relative.parts
        ):
            raise SourceBoundaryError("stored source path is not repository-relative")
        unresolved = self.repository_root / relative
        try:
            resolved = unresolved.resolve(strict=True)
            resolved.relative_to(self.knowledge_root)
        except FileNotFoundError as error:
            raise SourceUnavailableError("published source file is unavailable") from error
        except (OSError, ValueError) as error:
            raise SourceBoundaryError("stored source path escapes knowledge root") from error
        if not resolved.is_file():
            raise SourceUnavailableError("published source is not a regular file")
        return resolved


class PublishedSourceMetadata(BaseModel):
    """Student-safe source identity; filesystem paths are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: UUID
    document_version_id: UUID
    title: str
    filename: str
    media_type: str
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class _PublishedSource:
    document: SourceDocument
    version: SourceDocumentVersion


def source_file_repository_dependency(request: Request) -> SourceFileRepository:
    repository = getattr(request.app.state, "source_file_repository", None)
    if not isinstance(repository, SourceFileRepository):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Published source access is unavailable",
        )
    return repository


SourceRepository = Annotated[
    SourceFileRepository,
    Depends(source_file_repository_dependency),
]


async def _published_source(
    session: AsyncSession,
    *,
    course_id: UUID,
    curriculum_edition_id: UUID,
    document_version_id: UUID,
) -> _PublishedSource:
    row = (
        await session.execute(
            select(SourceDocument, SourceDocumentVersion)
            .join(
                SourceDocumentVersion,
                SourceDocumentVersion.document_id == SourceDocument.id,
            )
            .join(
                DocumentPublication,
                DocumentPublication.document_version_id == SourceDocumentVersion.id,
            )
            .where(
                SourceDocumentVersion.id == document_version_id,
                SourceDocument.course_id == course_id,
                SourceDocument.status == DocumentStatus.PUBLISHED,
                SourceDocumentVersion.status == DocumentVersionStatus.PUBLISHED,
                DocumentPublication.course_id == course_id,
                DocumentPublication.curriculum_edition_id == curriculum_edition_id,
                DocumentPublication.status == PublicationStatus.PUBLISHED,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published source not found",
        )
    document, version = row
    return _PublishedSource(document=document, version=version)


def _safe_filename(document: SourceDocument, resolved_path: Path) -> tuple[str, str]:
    expected_media_type = _SUPPORTED_MEDIA_TYPES.get(resolved_path.suffix.casefold())
    if expected_media_type is None or document.media_type != expected_media_type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published source metadata failed integrity validation",
        )
    normalized = unicodedata.normalize("NFC", document.source_filename)
    filename = Path(normalized.replace("\\", "/")).name
    filename = "".join(
        character
        for character in filename
        if character not in {"\r", "\n", "\x00"}
        and not unicodedata.category(character).startswith("C")
    ).strip()
    if (
        not filename
        or filename in {".", ".."}
        or Path(filename).suffix.casefold() != resolved_path.suffix.casefold()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published source metadata failed integrity validation",
        )
    return filename, expected_media_type


async def _authenticate(
    request: Request,
    session: AsyncSession,
    *,
    course_id: UUID,
) -> None:
    await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
    )


@router.get("/{document_version_id}", response_model=PublishedSourceMetadata)
async def published_source_metadata(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    document_version_id: UUID,
    session: DatabaseSession,
) -> PublishedSourceMetadata:
    await _authenticate(request, session, course_id=course_id)
    source = await _published_source(
        session,
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
        document_version_id=document_version_id,
    )
    suffix = Path(source.document.source_filename).suffix.casefold()
    if suffix not in _SUPPORTED_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published source not found",
        )
    return PublishedSourceMetadata(
        document_id=source.document.id,
        document_version_id=source.version.id,
        title=source.document.title,
        filename=Path(source.document.source_filename.replace("\\", "/")).name,
        media_type=_SUPPORTED_MEDIA_TYPES[suffix],
        byte_size=source.version.byte_size,
        sha256=source.version.source_file_sha256,
    )


@router.api_route("/{document_version_id}/original", methods=["GET", "HEAD"])
async def open_published_source(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    document_version_id: UUID,
    session: DatabaseSession,
    repository: SourceRepository,
) -> FileResponse:
    """Stream one exact published source after a fresh SHA-256 verification."""

    await _authenticate(request, session, course_id=course_id)
    source = await _published_source(
        session,
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
        document_version_id=document_version_id,
    )
    try:
        resolved_path = repository.resolve(source.version.immutable_source_path)
    except SourceBoundaryError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published source path failed integrity validation",
        ) from error
    except SourceUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Published source file is unavailable",
        ) from error

    range_header = request.headers.get("range")
    if range_header is not None and (
        len(range_header) > _MAX_RANGE_HEADER_CHARACTERS or "," in range_header
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only one bounded byte range is supported",
        )

    filename, media_type = _safe_filename(source.document, resolved_path)
    try:
        before = resolved_path.stat()
        actual_sha256 = await anyio.to_thread.run_sync(sha256_file, resolved_path)
        after = resolved_path.stat()
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Published source file is unavailable",
        ) from error
    stable_file = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if (
        not stable_file
        or actual_sha256 != source.version.source_file_sha256
        or after.st_size != source.version.byte_size
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published source file failed integrity validation",
        )

    response = FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=filename,
        stat_result=after,
        content_disposition_type=(
            "inline" if resolved_path.suffix.casefold() == ".pdf" else "attachment"
        ),
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
    response.headers["ETag"] = f'"sha256-{actual_sha256}"'
    return response


__all__ = [
    "PublishedSourceMetadata",
    "SourceBoundaryError",
    "SourceFileRepository",
    "SourceUnavailableError",
    "router",
    "source_file_repository_dependency",
]
