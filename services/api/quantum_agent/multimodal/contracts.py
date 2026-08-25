"""Strict contracts for model-derived visual and document evidence."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoordinateSystem(StrEnum):
    PIXELS = "pixels"
    POINTS = "points"
    NORMALIZED = "normalized"
    EMU = "emu"


class ExtractionMethod(StrEnum):
    NATIVE = "native"
    LEGACY_CONVERSION = "legacy_conversion"
    QWEN_VISION = "qwen_vision"
    MINERU = "mineru"
    VISION_OCR = "vision_ocr"
    UNLIMITED_OCR = "unlimited_ocr"


class ConfirmationState(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class BoundingBox(BaseModel):
    """A non-invented rectangular source locator in a declared coordinate system."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x_min: float = Field(ge=0)
    y_min: float = Field(ge=0)
    x_max: float = Field(gt=0)
    y_max: float = Field(gt=0)
    coordinate_system: CoordinateSystem
    page_number: int | None = Field(default=None, ge=1)
    slide_number: int | None = Field(default=None, ge=1)
    region_id: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("bounding-box maximums must exceed minimums")
        if self.page_number is not None and self.slide_number is not None:
            raise ValueError("a bounding box cannot identify both a page and a slide")
        if self.coordinate_system == CoordinateSystem.NORMALIZED and (
            self.x_max > 1 or self.y_max > 1
        ):
            raise ValueError("normalized bounding-box coordinates must not exceed one")
        return self


class AmbiguityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)


class Ambiguity(BaseModel):
    """One uncertainty which must not be silently resolved by a model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ambiguity_id: str = Field(min_length=1, max_length=160)
    field_path: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    candidates: tuple[AmbiguityCandidate, ...] = Field(default_factory=tuple, max_length=12)
    bounding_boxes: tuple[BoundingBox, ...] = Field(default_factory=tuple, max_length=20)
    requires_confirmation: bool = True


class DetectedEquation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_text: str = Field(min_length=1, max_length=8000)
    latex: str = Field(min_length=1, max_length=8000)
    confidence: float = Field(ge=0, le=1)
    bounding_boxes: tuple[BoundingBox, ...] = Field(default_factory=tuple, max_length=20)
    ambiguity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)


class DerivationStep(BaseModel):
    """A verbatim/transcribed student step, not a corrected derivation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=1)
    source_text: str = Field(min_length=1, max_length=12000)
    latex: str = Field(min_length=1, max_length=12000)
    confidence: float = Field(ge=0, le=1)
    bounding_boxes: tuple[BoundingBox, ...] = Field(default_factory=tuple, max_length=20)
    ambiguity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)


class PlotAxis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    axis: Literal["x", "y", "z", "color"]
    label: str | None = Field(default=None, max_length=500)
    unit: str | None = Field(default=None, max_length=160)
    minimum: float | None = None
    maximum: float | None = None
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("plot-axis maximum must not be below its minimum")
        return self


class VisualModelEvidence(BaseModel):
    """Exact JSON schema expected from the vision provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    detected_text: str = Field(default="", max_length=100_000)
    equations: tuple[DetectedEquation, ...] = Field(default_factory=tuple, max_length=200)
    derivation_steps: tuple[DerivationStep, ...] = Field(default_factory=tuple, max_length=200)
    diagram_interpretation: str | None = Field(default=None, max_length=20_000)
    plot_axes: tuple[PlotAxis, ...] = Field(default_factory=tuple, max_length=8)
    plot_interpretation: str | None = Field(default=None, max_length=20_000)
    figure_description: str | None = Field(default=None, max_length=20_000)
    confidence: float = Field(ge=0, le=1)
    bounding_boxes: tuple[BoundingBox, ...] = Field(default_factory=tuple, max_length=500)
    ambiguities: tuple[Ambiguity, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def validate_ambiguity_references(self) -> Self:
        known = {ambiguity.ambiguity_id for ambiguity in self.ambiguities}
        if len(known) != len(self.ambiguities):
            raise ValueError("ambiguity identifiers must be unique")
        referenced = {
            ambiguity_id for equation in self.equations for ambiguity_id in equation.ambiguity_ids
        } | {ambiguity_id for step in self.derivation_steps for ambiguity_id in step.ambiguity_ids}
        if not referenced <= known:
            raise ValueError("equations and derivation steps reference unknown ambiguities")
        ordinals = [step.ordinal for step in self.derivation_steps]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise ValueError("derivation-step ordinals must be contiguous and one-based")
        return self


class VisualEvidence(VisualModelEvidence):
    """Auditable image perception bound to an immutable student attachment."""

    evidence_type: Literal["visual"] = "visual"
    attachment_id: UUID
    original_file_reference: str = Field(min_length=1, max_length=500)
    extraction_method: ExtractionMethod
    confirmation_state: ConfirmationState
    requires_confirmation: bool

    @model_validator(mode="after")
    def validate_confirmation_state(self) -> Self:
        if self.requires_confirmation != (self.confirmation_state == ConfirmationState.REQUIRED):
            raise ValueError("confirmation state and requires_confirmation disagree")
        return self


class DocumentLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int | None = Field(default=None, ge=1)
    page_label: str | None = Field(default=None, max_length=160)
    slide_number: int | None = Field(default=None, ge=1)
    paragraph_start: int | None = Field(default=None, ge=0)
    paragraph_end: int | None = Field(default=None, ge=0)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_locator(self) -> Self:
        primary = [self.page_number, self.slide_number, self.paragraph_start, self.line_start]
        if all(value is None for value in primary):
            raise ValueError("a document locator requires a page, slide, paragraph, or line")
        if self.page_number is not None and self.slide_number is not None:
            raise ValueError("a document unit cannot be both a page and a slide")
        if (
            self.paragraph_start is not None
            and self.paragraph_end is not None
            and self.paragraph_end < self.paragraph_start
        ):
            raise ValueError("paragraph range is reversed")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line range is reversed")
        return self


class DocumentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reading_order: int = Field(ge=0)
    kind: Literal["text", "formula", "table", "figure", "caption", "other"]
    exact_text: str = Field(default="", max_length=100_000)
    latex: str | None = Field(default=None, max_length=20_000)
    bounding_box: BoundingBox | None = None


class NormalizedDocumentUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=0)
    locator: DocumentLocator
    headings: tuple[str, ...] = Field(default_factory=tuple, max_length=40)
    blocks: tuple[DocumentBlock, ...] = Field(default_factory=tuple, max_length=2000)
    exact_text: str = Field(default="", max_length=500_000)
    formulas_latex: tuple[str, ...] = Field(default_factory=tuple, max_length=500)
    tables: tuple[str, ...] = Field(default_factory=tuple, max_length=200)
    figures: tuple[str, ...] = Field(default_factory=tuple, max_length=200)
    captions: tuple[str, ...] = Field(default_factory=tuple, max_length=200)

    @model_validator(mode="after")
    def validate_reading_order_and_bounding_boxes(self) -> Self:
        reading_order = [block.reading_order for block in self.blocks]
        if reading_order != sorted(reading_order) or len(reading_order) != len(
            set(reading_order)
        ):
            raise ValueError("document-block reading order must be unique and ascending")
        for block in self.blocks:
            box = block.bounding_box
            if box is None:
                continue
            if (
                box.page_number is not None
                and box.page_number != self.locator.page_number
            ):
                raise ValueError("block page bounding box conflicts with its unit locator")
            if (
                box.slide_number is not None
                and box.slide_number != self.locator.slide_number
            ):
                raise ValueError("block slide bounding box conflicts with its unit locator")
        return self


class ParseAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: ExtractionMethod
    status: Literal["succeeded", "partial", "failed", "unavailable", "not_needed"]
    detail: str = Field(min_length=1, max_length=2000)


class DocumentEvidence(BaseModel):
    """Normalized but untrusted evidence extracted from a student document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_type: Literal["document"] = "document"
    attachment_id: UUID
    original_file_reference: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    extraction_method: ExtractionMethod
    parser_name: str = Field(min_length=1, max_length=200)
    parser_version: str = Field(min_length=1, max_length=100)
    units: tuple[NormalizedDocumentUnit, ...] = Field(default_factory=tuple, max_length=2000)
    page_count: int | None = Field(default=None, ge=0)
    slide_count: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    ambiguities: tuple[Ambiguity, ...] = Field(default_factory=tuple, max_length=100)
    fallback_chain: tuple[ParseAttempt, ...] = Field(default_factory=tuple, max_length=12)
    confirmation_state: ConfirmationState
    requires_confirmation: bool

    @model_validator(mode="after")
    def validate_document(self) -> Self:
        if self.requires_confirmation != (self.confirmation_state == ConfirmationState.REQUIRED):
            raise ValueError("confirmation state and requires_confirmation disagree")
        if self.page_count is not None and self.slide_count is not None:
            raise ValueError("a normalized document cannot have page and slide counts")
        ordinals = [unit.ordinal for unit in self.units]
        if ordinals != list(range(len(ordinals))):
            raise ValueError("document-unit ordinals must be contiguous and zero-based")
        return self


ConfirmedEvidence = Annotated[
    VisualEvidence | DocumentEvidence, Field(discriminator="evidence_type")
]


__all__ = [
    "Ambiguity",
    "AmbiguityCandidate",
    "BoundingBox",
    "ConfirmationState",
    "ConfirmedEvidence",
    "CoordinateSystem",
    "DerivationStep",
    "DetectedEquation",
    "DocumentBlock",
    "DocumentEvidence",
    "DocumentLocator",
    "ExtractionMethod",
    "NormalizedDocumentUnit",
    "ParseAttempt",
    "PlotAxis",
    "VisualEvidence",
    "VisualModelEvidence",
]
