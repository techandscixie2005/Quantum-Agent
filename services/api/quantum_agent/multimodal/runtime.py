"""Application service for scoped attachments, extraction, and confirmation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import anyio
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.config import Settings
from quantum_agent.db_models import (
    AttachmentKind,
    AttachmentStatus,
    CurriculumEdition,
    DocumentParseRun,
    DocumentParseRunStatus,
    MultimodalExtraction,
    MultimodalExtractionKind,
    MultimodalExtractionStatus,
    UserAttachment,
)
from quantum_agent.gateways import build_model_capability_registry
from quantum_agent.llm.routing import ModelCapabilityRegistry
from quantum_agent.multimodal.contracts import (
    ConfirmationState,
    ConfirmedEvidence,
    DocumentEvidence,
    ExtractionMethod,
    VisualEvidence,
)
from quantum_agent.multimodal.document_capabilities import (
    DocumentCapabilityTransport,
    build_registry_document_adapters,
)
from quantum_agent.multimodal.documents import (
    DocumentIntelligenceService,
    DocumentParserAdapter,
    LegacyOfficeConverter,
    LegacyOfficeDocumentAdapter,
    VisionOCRDocumentAdapter,
)
from quantum_agent.multimodal.perception import (
    MultimodalPerceptionService,
    PerceptionResult,
    VisionTranscriber,
)
from quantum_agent.multimodal.security import (
    AsyncUpload,
    UploadValidationPolicy,
    read_bounded,
    validate_upload,
)
from quantum_agent.multimodal.storage import LocalAttachmentStorage


class AttachmentNotFoundError(LookupError):
    pass


class AttachmentConflictError(RuntimeError):
    pass


class AttachmentProcessingError(RuntimeError):
    pass


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    extraction_id: UUID
    decision: Literal["accept", "correct", "reject"]
    ambiguity_resolutions: dict[str, str] = Field(default_factory=dict, max_length=100)
    corrected_evidence: ConfirmedEvidence | None = None

    def model_post_init(self, __context: object) -> None:
        if self.decision == "correct" and self.corrected_evidence is None:
            raise ValueError("correct requires corrected_evidence")
        if self.decision != "correct" and self.corrected_evidence is not None:
            raise ValueError("corrected_evidence is valid only for a correction")
        for ambiguity_id, resolution in self.ambiguity_resolutions.items():
            if not ambiguity_id or len(ambiguity_id) > 160:
                raise ValueError("ambiguity-resolution identifiers must be 1-160 characters")
            if not resolution.strip() or len(resolution) > 4000:
                raise ValueError(
                    "ambiguity resolutions must be nonblank and at most 4000 characters"
                )


@dataclass(frozen=True, slots=True)
class CreatedAttachment:
    attachment: UserAttachment
    extraction: MultimodalExtraction | None
    idempotent_replay: bool


@dataclass(slots=True)
class AttachmentRuntime:
    storage: LocalAttachmentStorage
    validation_policy: UploadValidationPolicy
    perception: MultimodalPerceptionService
    documents: DocumentIntelligenceService
    auto_process: bool = True

    async def _verify_edition(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
    ) -> None:
        edition = await session.scalar(
            select(CurriculumEdition.id).where(
                CurriculumEdition.id == curriculum_edition_id,
                CurriculumEdition.course_id == course_id,
            )
        )
        if edition is None:
            raise AttachmentNotFoundError("Curriculum edition not found")

    async def create(
        self,
        session: AsyncSession,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        upload: AsyncUpload,
    ) -> CreatedAttachment:
        await self._verify_edition(
            session,
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
        )
        content = await read_bounded(upload, max_bytes=self.validation_policy.max_bytes)
        validated = validate_upload(
            content=content,
            filename=upload.filename,
            declared_media_type=upload.content_type,
            policy=self.validation_policy,
        )
        existing = await session.scalar(
            select(UserAttachment).where(
                UserAttachment.course_id == actor.course_id,
                UserAttachment.curriculum_edition_id == curriculum_edition_id,
                UserAttachment.owner_user_id == actor.user_id,
                UserAttachment.content_sha256 == validated.content_sha256,
            )
        )
        storage_key = self.storage.storage_key(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            owner_user_id=actor.user_id,
            content_sha256=validated.content_sha256,
            extension=validated.extension,
        )
        await self.storage.store(
            storage_key=storage_key,
            content=validated.content,
            expected_sha256=validated.content_sha256,
        )

        idempotent_replay = existing is not None and existing.status != AttachmentStatus.DELETED
        if existing is None:
            attachment = UserAttachment(
                course_id=actor.course_id,
                curriculum_edition_id=curriculum_edition_id,
                owner_user_id=actor.user_id,
                kind=validated.kind,
                original_filename=validated.safe_filename,
                detected_media_type=validated.detected_media_type,
                byte_size=validated.byte_size,
                content_sha256=validated.content_sha256,
                storage_key=storage_key,
                status=AttachmentStatus.QUARANTINED,
                validation_json=validated.metadata,
            )
            try:
                async with session.begin_nested():
                    session.add(attachment)
                    await session.flush()
            except IntegrityError:
                concurrent_attachment = await session.scalar(
                    select(UserAttachment).where(
                        UserAttachment.course_id == actor.course_id,
                        UserAttachment.curriculum_edition_id == curriculum_edition_id,
                        UserAttachment.owner_user_id == actor.user_id,
                        UserAttachment.content_sha256 == validated.content_sha256,
                    )
                )
                if concurrent_attachment is None:
                    raise
                attachment = concurrent_attachment
                idempotent_replay = attachment.status != AttachmentStatus.DELETED
        else:
            attachment = existing

        if attachment.status == AttachmentStatus.REJECTED:
            raise AttachmentConflictError("A rejected attachment cannot be replayed")
        if attachment.status == AttachmentStatus.DELETED:
            attachment.deleted_at = None
            attachment.rejection_code = None
            idempotent_replay = False
        attachment.storage_key = storage_key
        attachment.status = AttachmentStatus.READY
        attachment.validation_json = validated.metadata
        await session.flush()

        if self.auto_process:
            pipeline_name = (
                self.perception.pipeline_name
                if attachment.kind == AttachmentKind.IMAGE
                else self.documents.pipeline_name
            )
            pipeline_version = (
                self.perception.pipeline_version
                if attachment.kind == AttachmentKind.IMAGE
                else self.documents.pipeline_version
            )
            extraction = await session.scalar(
                select(MultimodalExtraction).where(
                    MultimodalExtraction.attachment_id == attachment.id,
                    MultimodalExtraction.pipeline_name == pipeline_name,
                    MultimodalExtraction.pipeline_version == pipeline_version,
                )
            )
            if extraction is None:
                extraction = await self.process(session, attachment=attachment)
        else:
            extraction = await self.latest_extraction(session, attachment_id=attachment.id)
        return CreatedAttachment(
            attachment=attachment,
            extraction=extraction,
            idempotent_replay=idempotent_replay,
        )

    async def scoped_attachment(
        self,
        session: AsyncSession,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        attachment_id: UUID,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> UserAttachment:
        statement = select(UserAttachment).where(
            UserAttachment.id == attachment_id,
            UserAttachment.course_id == actor.course_id,
            UserAttachment.curriculum_edition_id == curriculum_edition_id,
            UserAttachment.owner_user_id == actor.user_id,
        )
        if not include_deleted:
            statement = statement.where(UserAttachment.status != AttachmentStatus.DELETED)
        if for_update:
            statement = statement.with_for_update()
        attachment = await session.scalar(statement)
        if attachment is None:
            raise AttachmentNotFoundError("Attachment not found")
        return attachment

    async def list_scoped(
        self,
        session: AsyncSession,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        limit: int,
        offset: int,
    ) -> list[UserAttachment]:
        await self._verify_edition(
            session,
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
        )
        result = await session.scalars(
            select(UserAttachment)
            .where(
                UserAttachment.course_id == actor.course_id,
                UserAttachment.curriculum_edition_id == curriculum_edition_id,
                UserAttachment.owner_user_id == actor.user_id,
                UserAttachment.status != AttachmentStatus.DELETED,
            )
            .order_by(UserAttachment.created_at.desc(), UserAttachment.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def latest_extraction(
        self,
        session: AsyncSession,
        *,
        attachment_id: UUID,
    ) -> MultimodalExtraction | None:
        extraction: MultimodalExtraction | None = await session.scalar(
            select(MultimodalExtraction)
            .where(MultimodalExtraction.attachment_id == attachment_id)
            .order_by(MultimodalExtraction.created_at.desc(), MultimodalExtraction.id.desc())
            .limit(1)
        )
        return extraction

    async def process(
        self,
        session: AsyncSession,
        *,
        attachment: UserAttachment,
    ) -> MultimodalExtraction:
        if attachment.status != AttachmentStatus.READY or not attachment.storage_key:
            raise AttachmentConflictError("Attachment is not ready for perception")
        path = self.storage.resolve(attachment.storage_key, require_file=True)
        is_image = attachment.kind == AttachmentKind.IMAGE
        pipeline_name = self.perception.pipeline_name if is_image else self.documents.pipeline_name
        pipeline_version = (
            self.perception.pipeline_version if is_image else self.documents.pipeline_version
        )
        existing = await session.scalar(
            select(MultimodalExtraction).where(
                MultimodalExtraction.attachment_id == attachment.id,
                MultimodalExtraction.pipeline_name == pipeline_name,
                MultimodalExtraction.pipeline_version == pipeline_version,
            )
        )
        if existing is not None:
            return existing

        extraction = MultimodalExtraction(
            attachment_id=attachment.id,
            course_id=attachment.course_id,
            curriculum_edition_id=attachment.curriculum_edition_id,
            owner_user_id=attachment.owner_user_id,
            kind=(
                MultimodalExtractionKind.VISION if is_image else MultimodalExtractionKind.DOCUMENT
            ),
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            extraction_method=(
                ExtractionMethod.QWEN_VISION.value if is_image else ExtractionMethod.NATIVE.value
            ),
            status=MultimodalExtractionStatus.RUNNING,
        )
        session.add(extraction)
        await session.flush()

        if is_image:
            return await self._process_image(session, attachment, extraction, path)
        return await self._process_document(session, attachment, extraction, path)

    async def _process_image(
        self,
        session: AsyncSession,
        attachment: UserAttachment,
        extraction: MultimodalExtraction,
        path: Path,
    ) -> MultimodalExtraction:
        try:
            image_bytes = await anyio.Path(path).read_bytes()
            result: PerceptionResult = await self.perception.analyze(
                attachment_id=attachment.id,
                image_bytes=image_bytes,
                mime_type=attachment.detected_media_type,
            )
            evidence = result.evidence
            extraction.model_name = result.model_name
            extraction.confidence = evidence.confidence
            extraction.raw_output_json = json.loads(result.raw_provider_output)
            extraction.evidence_json = evidence.model_dump(mode="json")
            extraction.ambiguities_json = [
                ambiguity.model_dump(mode="json") for ambiguity in evidence.ambiguities
            ]
            extraction.requires_confirmation = evidence.requires_confirmation
            extraction.status = (
                MultimodalExtractionStatus.NEEDS_CONFIRMATION
                if evidence.requires_confirmation
                else MultimodalExtractionStatus.SUCCEEDED
            )
        except Exception as error:
            extraction.status = MultimodalExtractionStatus.FAILED
            extraction.failure_code = f"VISION_{type(error).__name__.upper()}"[:160]
        await session.flush()
        return extraction

    async def _process_document(
        self,
        session: AsyncSession,
        attachment: UserAttachment,
        extraction: MultimodalExtraction,
        path: Path,
    ) -> MultimodalExtraction:
        now = datetime.now(UTC)
        parse_run = DocumentParseRun(
            attachment_id=attachment.id,
            extraction_id=extraction.id,
            course_id=attachment.course_id,
            curriculum_edition_id=attachment.curriculum_edition_id,
            owner_user_id=attachment.owner_user_id,
            pipeline_name=self.documents.pipeline_name,
            pipeline_version=self.documents.pipeline_version,
            selected_method="pending",
            parser_name="pending",
            parser_version="pending",
            status=DocumentParseRunStatus.RUNNING,
            started_at=now,
        )
        session.add(parse_run)
        await session.flush()
        try:
            result = await self.documents.analyze(
                path=path,
                attachment_id=attachment.id,
                filename=attachment.original_filename,
                media_type=attachment.detected_media_type,
            )
            evidence = result.evidence
            extraction.extraction_method = evidence.extraction_method.value
            extraction.confidence = evidence.confidence
            extraction.raw_output_json = {
                "parser_name": evidence.parser_name,
                "parser_version": evidence.parser_version,
            }
            extraction.evidence_json = evidence.model_dump(mode="json")
            extraction.ambiguities_json = [
                ambiguity.model_dump(mode="json") for ambiguity in evidence.ambiguities
            ]
            extraction.requires_confirmation = evidence.requires_confirmation
            extraction.status = (
                MultimodalExtractionStatus.NEEDS_CONFIRMATION
                if evidence.requires_confirmation
                else MultimodalExtractionStatus.SUCCEEDED
            )
            parse_run.selected_method = evidence.extraction_method.value
            parse_run.parser_name = evidence.parser_name
            parse_run.parser_version = evidence.parser_version
            parse_run.page_count = evidence.page_count
            parse_run.slide_count = evidence.slide_count
            parse_run.fallback_chain_json = [
                attempt.model_dump(mode="json") for attempt in evidence.fallback_chain
            ]
            parse_run.provenance_json = {
                "original_file_reference": evidence.original_file_reference,
                "content_sha256": attachment.content_sha256,
            }
            parse_run.output_json = evidence.model_dump(mode="json")
            parse_run.status = (
                DocumentParseRunStatus.PARTIAL
                if evidence.requires_confirmation
                else DocumentParseRunStatus.SUCCEEDED
            )
            parse_run.completed_at = datetime.now(UTC)
        except Exception as error:
            code = f"DOCUMENT_{type(error).__name__.upper()}"[:160]
            extraction.status = MultimodalExtractionStatus.FAILED
            extraction.failure_code = code
            parse_run.status = DocumentParseRunStatus.FAILED
            parse_run.error_code = code
            parse_run.completed_at = datetime.now(UTC)
        await session.flush()
        return extraction

    async def delete(
        self,
        session: AsyncSession,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        attachment_id: UUID,
    ) -> None:
        attachment = await self.scoped_attachment(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            attachment_id=attachment_id,
            for_update=True,
        )
        storage_key = attachment.storage_key
        attachment.status = AttachmentStatus.DELETED
        attachment.deleted_at = datetime.now(UTC)
        await session.flush()
        if storage_key:
            await self.storage.delete(storage_key)

    async def confirm(
        self,
        session: AsyncSession,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        attachment_id: UUID,
        confirmation: ConfirmationRequest,
    ) -> MultimodalExtraction:
        await self.scoped_attachment(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            attachment_id=attachment_id,
        )
        extraction = await session.scalar(
            select(MultimodalExtraction)
            .where(
                MultimodalExtraction.id == confirmation.extraction_id,
                MultimodalExtraction.attachment_id == attachment_id,
                MultimodalExtraction.course_id == actor.course_id,
                MultimodalExtraction.curriculum_edition_id == curriculum_edition_id,
                MultimodalExtraction.owner_user_id == actor.user_id,
            )
            .with_for_update()
        )
        if extraction is None:
            raise AttachmentNotFoundError("Multimodal extraction not found")
        if extraction.status != MultimodalExtractionStatus.NEEDS_CONFIRMATION:
            raise AttachmentConflictError("Extraction is not awaiting confirmation")

        correction_json: dict[str, object] | None = None
        if confirmation.corrected_evidence is not None:
            corrected = confirmation.corrected_evidence
            if corrected.attachment_id != attachment_id:
                raise AttachmentConflictError("Corrected evidence belongs to another attachment")
            if corrected.confirmation_state != ConfirmationState.CONFIRMED:
                raise AttachmentConflictError("Corrected evidence must be explicitly confirmed")
            correction_json = corrected.model_dump(mode="json")
        extraction.confirmed_by_user_id = actor.user_id
        extraction.confirmed_at = datetime.now(UTC)
        extraction.requires_confirmation = False
        extraction.confirmation_json = {
            "decision": confirmation.decision,
            "ambiguity_resolutions": confirmation.ambiguity_resolutions,
            "corrected_evidence": correction_json,
            "original_evidence_preserved": True,
        }
        extraction.status = (
            MultimodalExtractionStatus.REJECTED
            if confirmation.decision == "reject"
            else MultimodalExtractionStatus.CONFIRMED
        )
        await session.flush()
        return extraction


def build_attachment_runtime(
    settings: Settings,
    *,
    vision_gateway: VisionTranscriber | None = None,
    mineru_adapter: DocumentParserAdapter | None = None,
    ocr_adapter: DocumentParserAdapter | None = None,
    document_capability_transport: DocumentCapabilityTransport | None = None,
    model_registry: ModelCapabilityRegistry | None = None,
    legacy_office_converter: LegacyOfficeConverter | None = None,
    auto_process: bool = True,
) -> AttachmentRuntime:
    """Build an injectable runtime without coupling it to application startup."""

    policy = UploadValidationPolicy(
        max_bytes=settings.attachment_max_bytes,
        max_image_pixels=settings.attachment_max_image_pixels,
        max_image_dimension=settings.attachment_max_image_dimension,
        max_document_pages=settings.attachment_max_document_pages,
        max_archive_entries=settings.attachment_max_archive_entries,
        max_archive_uncompressed_bytes=settings.attachment_max_archive_uncompressed_bytes,
        max_archive_compression_ratio=settings.attachment_max_archive_compression_ratio,
        allow_legacy_office=legacy_office_converter is not None,
    )
    registry = model_registry or build_model_capability_registry(settings)
    registry_adapters = build_registry_document_adapters(
        registry=registry,
        transport=document_capability_transport,
        max_bytes=min(settings.attachment_max_bytes, 25 * 1024 * 1024),
        max_pages=settings.attachment_max_document_pages,
    )
    effective_mineru = mineru_adapter or registry_adapters.mineru
    effective_ocr = ocr_adapter or registry_adapters.unlimited_ocr
    vision_ocr = (
        VisionOCRDocumentAdapter(vision_gateway) if vision_gateway is not None else None
    )
    legacy_adapter = (
        LegacyOfficeDocumentAdapter(
            converter=legacy_office_converter,
            max_bytes=settings.attachment_max_bytes,
        )
        if legacy_office_converter is not None
        else None
    )
    return AttachmentRuntime(
        storage=LocalAttachmentStorage(Path(settings.attachment_storage_root)),
        validation_policy=policy,
        perception=MultimodalPerceptionService(
            vision_gateway=vision_gateway,
            model_name=settings.ustc_vision_model,
        ),
        documents=DocumentIntelligenceService(
            legacy_adapter=legacy_adapter,
            mineru_adapter=effective_mineru,
            ocr_adapter=effective_ocr,
            vision_ocr_adapter=vision_ocr,
        ),
        auto_process=auto_process,
    )


def validate_confirmed_evidence(value: object) -> VisualEvidence | DocumentEvidence:
    """Public helper for consumers loading corrected evidence from persistence."""

    try:
        return TypeAdapter(ConfirmedEvidence).validate_python(value)
    except ValidationError as error:
        raise AttachmentProcessingError("stored confirmed evidence is invalid") from error


__all__ = [
    "AttachmentConflictError",
    "AttachmentNotFoundError",
    "AttachmentProcessingError",
    "AttachmentRuntime",
    "ConfirmationRequest",
    "CreatedAttachment",
    "build_attachment_runtime",
    "validate_confirmed_evidence",
]
