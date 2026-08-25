"""Bounded registry adapters for unprobed document-parser transports.

The public USTC API contract currently documents OpenAI-compatible chat and
embedding endpoints, not a file/document-parser transport.  Registry profiles
therefore select capabilities server-side, while an explicit transport must be
injected before any file is sent.  With no probed transport the adapters fail
as *unavailable*; they never reinterpret a parser alias as a chat model.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol, Self
from uuid import UUID

import anyio
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from quantum_agent.llm.routing import (
    ModelCapability,
    ModelCapabilityRegistry,
    ModelProfile,
    ModelTask,
    ModelTransport,
)
from quantum_agent.multimodal.contracts import (
    Ambiguity,
    ConfirmationState,
    DocumentEvidence,
    ExtractionMethod,
    NormalizedDocumentUnit,
)


class DocumentCapabilityUnavailableError(RuntimeError):
    """No explicitly configured and probed document transport is available."""


class DocumentCapabilityResponseError(RuntimeError):
    """A capability transport returned malformed or scope-inconsistent output."""


class DocumentCapabilityRequest(BaseModel):
    """Bounded request passed only to a server-owned transport implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attachment_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    content: bytes = Field(min_length=1, max_length=25 * 1024 * 1024)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_pages: int = Field(default=500, ge=1, le=5_000)

    @model_validator(mode="after")
    def content_digest_matches(self) -> Self:
        if sha256(self.content).hexdigest() != self.content_sha256:
            raise ValueError("document capability request checksum mismatch")
        return self


class DocumentCapabilityOutput(BaseModel):
    """Provider-neutral structured output; model aliases are not accepted here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parser_name: str = Field(min_length=1, max_length=200)
    parser_version: str = Field(min_length=1, max_length=100)
    units: tuple[NormalizedDocumentUnit, ...] = Field(default_factory=tuple, max_length=2_000)
    page_count: int | None = Field(default=None, ge=0, le=5_000)
    slide_count: int | None = Field(default=None, ge=0, le=5_000)
    confidence: float = Field(ge=0, le=1)
    ambiguities: tuple[Ambiguity, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def locators_fit_declared_document(self) -> Self:
        if self.page_count is not None and self.slide_count is not None:
            raise ValueError("capability output cannot declare pages and slides")
        for unit in self.units:
            locator = unit.locator
            if (
                self.page_count is not None
                and locator.page_number is not None
                and locator.page_number > self.page_count
            ):
                raise ValueError("unit page exceeds declared page count")
            if (
                self.slide_count is not None
                and locator.slide_number is not None
                and locator.slide_number > self.slide_count
            ):
                raise ValueError("unit slide exceeds declared slide count")
        return self


class DocumentTransportProbe(BaseModel):
    """Startup probe evidence required before a file transport may be called."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["quantum-agent-document-transport/1.0"] = (
        "quantum-agent-document-transport/1.0"
    )
    status: Literal["passed"] = "passed"
    supports_document_parsing: bool
    supports_ocr: bool
    max_bytes: int = Field(ge=1, le=25 * 1024 * 1024)
    max_pages: int = Field(ge=1, le=5_000)


class DocumentCapabilityTransport(Protocol):
    """Explicit transport implemented only after its file API has been probed."""

    probe: DocumentTransportProbe

    async def parse_document(
        self,
        *,
        profile: ModelProfile,
        request: DocumentCapabilityRequest,
    ) -> object: ...


class RegistryDocumentParserAdapter:
    """Bind one internal registry profile to a validated parser contract."""

    def __init__(
        self,
        *,
        profile: ModelProfile,
        transport: DocumentCapabilityTransport | None,
        max_bytes: int = 25 * 1024 * 1024,
        max_pages: int = 500,
        confirmation_threshold: float = 0.80,
    ) -> None:
        if profile.transport is not ModelTransport.DOCUMENT_PARSER:
            raise ValueError("document adapter requires a document-parser profile")
        if ModelCapability.DOCUMENT_PARSING not in profile.capabilities:
            raise ValueError("profile does not declare document parsing")
        if not 1 <= max_bytes <= 25 * 1024 * 1024:
            raise ValueError("document capability byte limit is outside the supported bound")
        if not 1 <= max_pages <= 5_000:
            raise ValueError("document capability page limit is outside the supported bound")
        if not 0 < confirmation_threshold <= 1:
            raise ValueError("confirmation threshold must be within (0, 1]")
        self._profile = profile
        is_ocr = ModelCapability.OCR in profile.capabilities
        self.method = (
            ExtractionMethod.UNLIMITED_OCR if is_ocr else ExtractionMethod.MINERU
        )
        self.name = "ocr-capability" if is_ocr else "document-parser-capability"
        if transport is not None:
            try:
                probe = DocumentTransportProbe.model_validate(transport.probe)
            except (AttributeError, ValidationError, TypeError, ValueError) as error:
                raise ValueError(
                    "document transport requires a validated successful capability probe"
                ) from error
            supported = (
                probe.supports_ocr if is_ocr else probe.supports_document_parsing
            )
            if not supported:
                raise ValueError("document transport probe does not support this profile")
            max_bytes = min(max_bytes, probe.max_bytes)
            max_pages = min(max_pages, probe.max_pages)
        self._transport = transport
        self._max_bytes = max_bytes
        self._max_pages = max_pages
        self._confirmation_threshold = confirmation_threshold

    async def parse(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentEvidence:
        if self._transport is None:
            raise DocumentCapabilityUnavailableError(
                "server document-parser transport is not configured or capability-probed"
            )
        stat = await anyio.Path(path).stat()
        if stat.st_size <= 0 or stat.st_size > self._max_bytes:
            raise DocumentCapabilityResponseError(
                "document is outside the capability adapter byte bound"
            )
        content = await anyio.Path(path).read_bytes()
        if len(content) != stat.st_size or len(content) > self._max_bytes:
            raise DocumentCapabilityResponseError("document changed while being read")
        request = DocumentCapabilityRequest(
            attachment_id=attachment_id,
            filename=filename,
            media_type=media_type,
            content=content,
            content_sha256=sha256(content).hexdigest(),
            max_pages=self._max_pages,
        )
        raw = await self._transport.parse_document(
            profile=self._profile,
            request=request,
        )
        try:
            output = DocumentCapabilityOutput.model_validate(raw)
        except (ValidationError, TypeError, ValueError) as error:
            raise DocumentCapabilityResponseError(
                "document capability output failed its structured contract"
            ) from error
        if output.page_count is not None and output.page_count > request.max_pages:
            raise DocumentCapabilityResponseError("document parser exceeded the page bound")
        if output.slide_count is not None and output.slide_count > request.max_pages:
            raise DocumentCapabilityResponseError("document parser exceeded the slide bound")
        requires_confirmation = (
            output.confidence < self._confirmation_threshold
            or any(item.requires_confirmation for item in output.ambiguities)
        )
        return DocumentEvidence(
            attachment_id=attachment_id,
            original_file_reference=f"attachment:{attachment_id}",
            filename=filename,
            media_type=media_type,
            extraction_method=self.method,
            parser_name=output.parser_name,
            parser_version=output.parser_version,
            units=output.units,
            page_count=output.page_count,
            slide_count=output.slide_count,
            confidence=output.confidence,
            ambiguities=output.ambiguities,
            confirmation_state=(
                ConfirmationState.REQUIRED
                if requires_confirmation
                else ConfirmationState.NOT_REQUIRED
            ),
            requires_confirmation=requires_confirmation,
        )


@dataclass(frozen=True, slots=True)
class RegistryDocumentAdapters:
    mineru: RegistryDocumentParserAdapter
    unlimited_ocr: RegistryDocumentParserAdapter


def build_registry_document_adapters(
    *,
    registry: ModelCapabilityRegistry,
    transport: DocumentCapabilityTransport | None,
    max_bytes: int = 25 * 1024 * 1024,
    max_pages: int = 500,
) -> RegistryDocumentAdapters:
    """Resolve parser/OCR by capability, never by a student or model-name string."""

    mineru_profile: ModelProfile | None = None
    ocr_profile: ModelProfile | None = None
    for profile in registry.profiles_for(ModelTask.DOCUMENT_PARSING):
        if ModelCapability.OCR in profile.capabilities:
            ocr_profile = ocr_profile or profile
        else:
            mineru_profile = mineru_profile or profile
    if mineru_profile is None or ocr_profile is None:
        raise ValueError("document route requires a parser and an OCR fallback profile")
    return RegistryDocumentAdapters(
        mineru=RegistryDocumentParserAdapter(
            profile=mineru_profile,
            transport=transport,
            max_bytes=max_bytes,
            max_pages=max_pages,
        ),
        unlimited_ocr=RegistryDocumentParserAdapter(
            profile=ocr_profile,
            transport=transport,
            max_bytes=max_bytes,
            max_pages=max_pages,
        ),
    )


__all__ = [
    "DocumentCapabilityOutput",
    "DocumentCapabilityRequest",
    "DocumentCapabilityResponseError",
    "DocumentCapabilityTransport",
    "DocumentCapabilityUnavailableError",
    "DocumentTransportProbe",
    "RegistryDocumentAdapters",
    "RegistryDocumentParserAdapter",
    "build_registry_document_adapters",
]
