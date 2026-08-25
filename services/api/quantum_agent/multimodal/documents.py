"""Normalized native -> MinerU -> OCR document-intelligence cascade."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Protocol
from uuid import UUID

import anyio
from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantum_agent.knowledge.ingestion import (
    IngestedDocument,
    IngestionStatus,
    LocatorType,
    SourceUnit,
    parse_document,
    parse_scanned_pdf_document,
)
from quantum_agent.multimodal.contracts import (
    Ambiguity,
    BoundingBox,
    ConfirmationState,
    CoordinateSystem,
    DocumentBlock,
    DocumentEvidence,
    DocumentLocator,
    ExtractionMethod,
    NormalizedDocumentUnit,
    ParseAttempt,
)
from quantum_agent.multimodal.document_capabilities import (
    DocumentCapabilityUnavailableError,
)
from quantum_agent.multimodal.perception import VisionTranscriber
from quantum_agent.multimodal.security import UploadValidationPolicy, validate_upload


class DocumentIntelligenceError(RuntimeError):
    pass


class DocumentParserAdapter(Protocol):
    """Injectable MinerU/OCR-compatible normalized document adapter."""

    method: ExtractionMethod
    name: str

    async def parse(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentEvidence: ...


@dataclass(frozen=True, slots=True)
class DocumentAnalysisResult:
    evidence: DocumentEvidence


def _coordinate_system(document: IngestedDocument) -> CoordinateSystem:
    suffix = Path(document.filename).suffix.casefold()
    if suffix == ".pdf":
        return CoordinateSystem.POINTS
    if suffix in {".ppt", ".pptx"}:
        return CoordinateSystem.EMU
    return CoordinateSystem.POINTS


def _document_locator(unit: SourceUnit) -> DocumentLocator:
    locator = unit.locator
    start = int(locator.start) if isinstance(locator.start, (int, str)) else 0
    end = int(locator.end) if isinstance(locator.end, (int, str)) else start
    if locator.locator_type == LocatorType.PAGE:
        return DocumentLocator(
            page_number=locator.physical_page,
            page_label=locator.page_label,
        )
    if locator.locator_type == LocatorType.SLIDE:
        return DocumentLocator(slide_number=start)
    if locator.locator_type == LocatorType.PARAGRAPH:
        return DocumentLocator(paragraph_start=start, paragraph_end=end)
    if locator.locator_type == LocatorType.LINE:
        return DocumentLocator(line_start=max(1, start), line_end=max(1, end))
    # Student PPTX/PDF/DOCX/TXT/MD inputs never produce spreadsheet locators.
    raise DocumentIntelligenceError(f"unsupported student-document locator: {locator.locator_type}")


def _block_kind(
    kind: str,
) -> Literal["text", "formula", "table", "figure", "caption", "other"]:
    normalized = kind.casefold()
    if normalized == "text":
        return "text"
    if normalized == "formula":
        return "formula"
    if normalized == "table":
        return "table"
    if normalized == "figure":
        return "figure"
    if normalized == "caption":
        return "caption"
    if normalized == "image":
        return "figure"
    return "other"


def _normalized_bbox(
    *,
    unit: SourceUnit,
    bbox: tuple[float, float, float, float] | None,
    coordinate_system: CoordinateSystem,
    region_id: str,
) -> BoundingBox | None:
    if bbox is None:
        return None
    x_min, y_min, x_max, y_max = bbox
    if x_max <= x_min or y_max <= y_min:
        return None
    locator = unit.locator
    return BoundingBox(
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
        coordinate_system=coordinate_system,
        page_number=locator.physical_page if locator.locator_type == LocatorType.PAGE else None,
        slide_number=(int(locator.start) if locator.locator_type == LocatorType.SLIDE else None),
        region_id=region_id,
    )


def normalize_ingested_document(
    document: IngestedDocument,
    *,
    attachment_id: UUID,
    filename: str,
    media_type: str,
    extraction_method: ExtractionMethod = ExtractionMethod.NATIVE,
    force_confirmation: bool = False,
    fallback_chain: tuple[ParseAttempt, ...] = (),
) -> DocumentEvidence:
    """Map existing deterministic parser output without inventing missing structure."""

    coordinate_system = _coordinate_system(document)
    units: list[NormalizedDocumentUnit] = []
    ambiguities: list[Ambiguity] = []
    review_required = force_confirmation
    for unit_ordinal, unit in enumerate(document.units):
        blocks: list[DocumentBlock] = []
        formulas: list[str] = []
        tables: list[str] = []
        figures: list[str] = []
        captions: list[str] = []
        for block in unit.blocks:
            kind = _block_kind(block.kind)
            exact_text = block.exact_text
            if kind == "formula" and exact_text:
                formulas.append(exact_text)
            elif kind == "table" and exact_text:
                tables.append(exact_text)
            elif kind == "figure":
                figures.append(exact_text)
            elif kind == "caption" and exact_text:
                captions.append(exact_text)
            blocks.append(
                DocumentBlock(
                    reading_order=block.ordinal,
                    kind=kind,
                    exact_text=exact_text,
                    latex=exact_text if kind == "formula" and exact_text else None,
                    bounding_box=_normalized_bbox(
                        unit=unit,
                        bbox=block.bbox,
                        coordinate_system=coordinate_system,
                        region_id=f"unit-{unit_ordinal}-block-{block.ordinal}",
                    ),
                )
            )
        needs_review = (
            unit.status != IngestionStatus.READY or unit.render_required or bool(unit.flags)
        )
        if needs_review:
            review_required = True
            ambiguities.append(
                Ambiguity(
                    ambiguity_id=f"unit-{unit_ordinal}-parser-review",
                    field_path=f"units[{unit_ordinal}]",
                    reason=(
                        "Native parser marked this source region for review: "
                        + ", ".join(unit.flags or (unit.status.value,))
                    ),
                    requires_confirmation=True,
                )
            )
        units.append(
            NormalizedDocumentUnit(
                ordinal=unit_ordinal,
                locator=_document_locator(unit),
                headings=unit.section_path,
                blocks=tuple(blocks),
                exact_text=unit.content_text,
                formulas_latex=tuple(formulas),
                tables=tuple(tables),
                figures=tuple(figures),
                captions=tuple(captions),
            )
        )

    suffix = Path(filename).suffix.casefold()
    page_count = len(units) if suffix == ".pdf" else None
    slide_count = len(units) if suffix in {".ppt", ".pptx"} else None
    confidence = 0.60 if review_required else 1.0
    return DocumentEvidence(
        attachment_id=attachment_id,
        original_file_reference=f"attachment:{attachment_id}",
        filename=filename,
        media_type=media_type,
        extraction_method=extraction_method,
        parser_name=document.parser_name,
        parser_version=document.parser_version,
        units=tuple(units),
        page_count=page_count,
        slide_count=slide_count,
        confidence=confidence,
        ambiguities=tuple(ambiguities),
        fallback_chain=fallback_chain,
        confirmation_state=(
            ConfirmationState.REQUIRED if review_required else ConfirmationState.NOT_REQUIRED
        ),
        requires_confirmation=review_required,
    )


class NativeDocumentAdapter:
    method = ExtractionMethod.NATIVE
    name = "native"

    async def parse(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentEvidence:
        parsed = await anyio.to_thread.run_sync(lambda: parse_document(path, source_name=filename))
        return normalize_ingested_document(
            parsed,
            attachment_id=attachment_id,
            filename=filename,
            media_type=media_type,
        )


class LegacyOfficeConversionRequest(BaseModel):
    """Bounded binary-office input for an isolated operator-supplied converter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_extension: Literal[".doc", ".ppt"]
    target_extension: Literal[".docx", ".pptx"]
    content: bytes = Field(min_length=1, max_length=200 * 1024 * 1024)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_output_bytes: int = Field(ge=1, le=200 * 1024 * 1024)

    @model_validator(mode="after")
    def request_is_consistent(self) -> LegacyOfficeConversionRequest:
        expected = ".docx" if self.source_extension == ".doc" else ".pptx"
        if self.target_extension != expected:
            raise ValueError("legacy Office conversion target does not match its source")
        if len(self.content) > self.max_output_bytes:
            raise ValueError("legacy Office input exceeds its conversion byte budget")
        if sha256(self.content).hexdigest() != self.content_sha256:
            raise ValueError("legacy Office conversion input checksum mismatch")
        return self


class LegacyOfficeConversionResult(BaseModel):
    """Typed modern-Office artifact returned by an isolated converter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_extension: Literal[".docx", ".pptx"]
    content: bytes = Field(min_length=1, max_length=200 * 1024 * 1024)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    converter_name: str = Field(min_length=1, max_length=80)
    converter_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def output_checksum_matches(self) -> LegacyOfficeConversionResult:
        if sha256(self.content).hexdigest() != self.content_sha256:
            raise ValueError("legacy Office conversion output checksum mismatch")
        return self


class LegacyOfficeConverter(Protocol):
    """External conversion boundary; no shell command is inferred by the API."""

    async def convert(
        self,
        request: LegacyOfficeConversionRequest,
    ) -> LegacyOfficeConversionResult: ...


class LegacyOfficeDocumentAdapter:
    """Convert validated CFB Office input, then reuse the deterministic native parser."""

    method = ExtractionMethod.LEGACY_CONVERSION
    name = "legacy-office-conversion"

    def __init__(
        self,
        *,
        converter: LegacyOfficeConverter,
        native_adapter: DocumentParserAdapter | None = None,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        if not 1 <= max_bytes <= 200 * 1024 * 1024:
            raise ValueError("legacy Office conversion byte limit is invalid")
        self._converter = converter
        self._native = native_adapter or NativeDocumentAdapter()
        self._max_bytes = max_bytes

    async def parse(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentEvidence:
        source_extension = path.suffix.casefold()
        if source_extension not in {".doc", ".ppt"}:
            raise DocumentIntelligenceError(
                "legacy conversion adapter accepts only .doc and .ppt"
            )
        stat = await anyio.Path(path).stat()
        if stat.st_size <= 0 or stat.st_size > self._max_bytes:
            raise DocumentIntelligenceError("legacy Office input exceeds the byte bound")
        content = await anyio.Path(path).read_bytes()
        if len(content) != stat.st_size:
            raise DocumentIntelligenceError("legacy Office input changed while being read")
        target_extension: Literal[".docx", ".pptx"] = (
            ".docx" if source_extension == ".doc" else ".pptx"
        )
        request = LegacyOfficeConversionRequest(
            source_extension=source_extension,
            target_extension=target_extension,
            content=content,
            content_sha256=sha256(content).hexdigest(),
            max_output_bytes=self._max_bytes,
        )
        converted = LegacyOfficeConversionResult.model_validate(
            await self._converter.convert(request)
        )
        if converted.output_extension != target_extension:
            raise DocumentIntelligenceError(
                "legacy Office converter returned the wrong modern format"
            )
        if len(converted.content) > request.max_output_bytes:
            raise DocumentIntelligenceError("legacy Office conversion exceeded its byte bound")
        modern_media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if target_extension == ".docx"
            else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        validated = validate_upload(
            content=converted.content,
            filename=f"converted{target_extension}",
            declared_media_type=modern_media_type,
            policy=UploadValidationPolicy(
                max_bytes=self._max_bytes,
                max_archive_uncompressed_bytes=max(
                    250 * 1024 * 1024,
                    self._max_bytes,
                ),
            ),
        )
        with TemporaryDirectory(prefix="quantum-agent-legacy-office-") as temporary:
            converted_path = Path(temporary) / validated.safe_filename
            await anyio.Path(converted_path).write_bytes(validated.content)
            evidence = await self._native.parse(
                path=converted_path,
                attachment_id=attachment_id,
                filename=validated.safe_filename,
                media_type=modern_media_type,
            )
        return DocumentEvidence.model_validate(
            {
                **evidence.model_dump(mode="python"),
                "filename": filename,
                "media_type": media_type,
                "extraction_method": ExtractionMethod.LEGACY_CONVERSION,
                "parser_name": (
                    f"{converted.converter_name}->{evidence.parser_name}"[:200]
                ),
                "parser_version": (
                    f"{converted.converter_version}->{evidence.parser_version}"[:100]
                ),
            }
        )


class VisionOCRDocumentAdapter:
    """Existing VisionGateway as a conservative PDF-only OCR fallback."""

    method = ExtractionMethod.VISION_OCR
    name = "vision-ocr"

    def __init__(self, vision_gateway: VisionTranscriber) -> None:
        self._vision_gateway = vision_gateway

    async def parse(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentEvidence:
        if path.suffix.casefold() != ".pdf":
            raise DocumentIntelligenceError("vision OCR fallback currently supports PDF only")

        async def transcribe(image_bytes: bytes) -> str:
            return await self._vision_gateway.transcribe(
                image_bytes=image_bytes,
                mime_type="image/png",
                instruction=(
                    "Transcribe only the visible page. Preserve equations in LaTeX. "
                    "Do not correct uncertain text; mark uncertainty explicitly in the text."
                ),
            )

        parsed = await parse_scanned_pdf_document(
            path,
            source_name=filename,
            transcribe=transcribe,
        )
        return normalize_ingested_document(
            parsed,
            attachment_id=attachment_id,
            filename=filename,
            media_type=media_type,
            extraction_method=ExtractionMethod.VISION_OCR,
            force_confirmation=True,
        )


class DocumentIntelligenceService:
    """Use native parsing first and bounded injectable fallbacks only when needed."""

    pipeline_name = "student-document-intelligence"
    pipeline_version = "1.1.0"

    def __init__(
        self,
        *,
        native_adapter: DocumentParserAdapter | None = None,
        legacy_adapter: DocumentParserAdapter | None = None,
        mineru_adapter: DocumentParserAdapter | None = None,
        ocr_adapter: DocumentParserAdapter | None = None,
        vision_ocr_adapter: DocumentParserAdapter | None = None,
        confirmation_threshold: float = 0.80,
    ) -> None:
        if not 0 < confirmation_threshold <= 1:
            raise ValueError("confirmation_threshold must be within (0, 1]")
        self._native = native_adapter or NativeDocumentAdapter()
        if self._native.method is not ExtractionMethod.NATIVE:
            raise ValueError("primary native adapter must use the native extraction method")
        if legacy_adapter is not None and (
            legacy_adapter.method is not ExtractionMethod.LEGACY_CONVERSION
        ):
            raise ValueError("legacy adapter must use the legacy-conversion method")
        if mineru_adapter is not None and mineru_adapter.method is not ExtractionMethod.MINERU:
            raise ValueError("MinerU adapter must use the MinerU extraction method")
        if ocr_adapter is not None and ocr_adapter.method is not ExtractionMethod.UNLIMITED_OCR:
            raise ValueError("OCR adapter must use the unlimited-OCR extraction method")
        if vision_ocr_adapter is not None and (
            vision_ocr_adapter.method is not ExtractionMethod.VISION_OCR
        ):
            raise ValueError("vision OCR adapter must use the vision-OCR extraction method")
        self._legacy = legacy_adapter
        self._mineru = mineru_adapter
        self._ocr = ocr_adapter
        self._vision_ocr = vision_ocr_adapter
        self._confirmation_threshold = confirmation_threshold

    def _usable(self, evidence: DocumentEvidence) -> bool:
        has_content = any(
            unit.exact_text
            or unit.formulas_latex
            or unit.tables
            or any(block.exact_text for block in unit.blocks)
            for unit in evidence.units
        )
        return has_content and evidence.confidence >= self._confirmation_threshold

    async def analyze(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentAnalysisResult:
        attempts: list[ParseAttempt] = []
        selected: DocumentEvidence | None = None
        is_legacy = path.suffix.casefold() in {".doc", ".ppt"}
        primary = self._legacy if is_legacy else self._native
        primary_method = (
            ExtractionMethod.LEGACY_CONVERSION if is_legacy else ExtractionMethod.NATIVE
        )
        if primary is None:
            attempts.append(
                ParseAttempt(
                    method=primary_method,
                    status="unavailable",
                    detail="Legacy Office conversion service is not configured",
                )
            )
        else:
            try:
                selected = await primary.parse(
                    path=path,
                    attachment_id=attachment_id,
                    filename=filename,
                    media_type=media_type,
                )
                if selected.attachment_id != attachment_id:
                    raise DocumentIntelligenceError(
                        "primary parser returned evidence for another attachment"
                    )
                attempts.append(
                    ParseAttempt(
                        method=selected.extraction_method,
                        status=(
                            "partial" if selected.requires_confirmation else "succeeded"
                        ),
                        detail=(
                            "Primary extraction requires fallback or confirmation"
                            if selected.requires_confirmation
                            else "Primary extraction preserved source provenance"
                        ),
                    )
                )
            except Exception as error:
                attempts.append(
                    ParseAttempt(
                        method=primary_method,
                        status="failed",
                        detail=f"Primary extraction failed: {type(error).__name__}",
                    )
                )

        needs_fallback = selected is None or not self._usable(selected)
        fallbacks = (
            (ExtractionMethod.MINERU, self._mineru),
            (ExtractionMethod.UNLIMITED_OCR, self._ocr),
            (ExtractionMethod.VISION_OCR, self._vision_ocr),
        )
        for expected_method, adapter in fallbacks:
            if not needs_fallback:
                attempts.append(
                    ParseAttempt(
                        method=expected_method,
                        status="not_needed",
                        detail=(
                            "Earlier extraction returned usable structured content; "
                            "confirmation may still be required"
                        ),
                    )
                )
                continue
            if adapter is None:
                attempts.append(
                    ParseAttempt(
                        method=expected_method,
                        status="unavailable",
                        detail=f"{expected_method.value} adapter is not configured",
                    )
                )
                continue
            try:
                candidate = await adapter.parse(
                    path=path,
                    attachment_id=attachment_id,
                    filename=filename,
                    media_type=media_type,
                )
                if candidate.attachment_id != attachment_id:
                    raise DocumentIntelligenceError(
                        "adapter returned evidence for another attachment"
                    )
                if candidate.extraction_method != adapter.method:
                    raise DocumentIntelligenceError("adapter returned the wrong extraction method")
                if candidate.original_file_reference != f"attachment:{attachment_id}":
                    raise DocumentIntelligenceError(
                        "adapter returned an invalid original-file reference"
                    )
                if candidate.filename != filename or candidate.media_type != media_type:
                    raise DocumentIntelligenceError(
                        "adapter returned evidence for different source metadata"
                    )
                attempts.append(
                    ParseAttempt(
                        method=adapter.method,
                        status="partial" if candidate.requires_confirmation else "succeeded",
                        detail=f"{adapter.name} returned normalized document evidence",
                    )
                )
                selected = candidate
                needs_fallback = not self._usable(candidate)
            except DocumentCapabilityUnavailableError:
                attempts.append(
                    ParseAttempt(
                        method=adapter.method,
                        status="unavailable",
                        detail=(
                            "Server capability is registered but no file transport "
                            "has been configured and probed"
                        ),
                    )
                )
            except Exception as error:
                attempts.append(
                    ParseAttempt(
                        method=adapter.method,
                        status="failed",
                        detail=f"{adapter.name} failed: {type(error).__name__}",
                    )
                )

        if selected is None:
            raise DocumentIntelligenceError("all configured document parsers failed")
        requires_confirmation = (
            selected.requires_confirmation
            or selected.confidence < self._confirmation_threshold
            or any(ambiguity.requires_confirmation for ambiguity in selected.ambiguities)
        )
        selected = selected.model_copy(
            update={
                "fallback_chain": tuple(attempts),
                "requires_confirmation": requires_confirmation,
                "confirmation_state": (
                    ConfirmationState.REQUIRED
                    if requires_confirmation
                    else ConfirmationState.NOT_REQUIRED
                ),
            }
        )
        # model_copy does not revalidate updates; validate once at the service boundary.
        selected = DocumentEvidence.model_validate(selected.model_dump())
        return DocumentAnalysisResult(evidence=selected)


__all__ = [
    "DocumentAnalysisResult",
    "DocumentIntelligenceError",
    "DocumentIntelligenceService",
    "DocumentParserAdapter",
    "LegacyOfficeConversionRequest",
    "LegacyOfficeConversionResult",
    "LegacyOfficeConverter",
    "LegacyOfficeDocumentAdapter",
    "NativeDocumentAdapter",
    "VisionOCRDocumentAdapter",
    "normalize_ingested_document",
]
