"""Explicit, review-gated ontology for the Quantum Agent course graph.

This module is deliberately independent from Neo4j and from the extraction
provider.  An LLM may *propose* :class:`NodeCandidate` and
:class:`RelationshipCandidate` objects, but it cannot approve them.  Approval
is a PostgreSQL review decision and only approved projections may be copied to
Neo4j (see ``graph_store.py``).

The source chunk text carried by ``EvidenceReference`` is verification input,
not generated evidence.  Callers must hydrate it from the authoritative
ingestion record before validation.  A quote that is not a normalized
substring of that text is retained for teacher inspection and automatically
marked ``REVIEW_REQUIRED``; it is never silently accepted.
"""

from __future__ import annotations

import json
import re
import unicodedata
from enum import StrEnum
from typing import Any, Final, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NodeType(StrEnum):
    COURSE = "Course"
    CHAPTER = "Chapter"
    SECTION = "Section"
    CONCEPT = "Concept"
    PRINCIPLE = "Principle"
    PHYSICAL_SYSTEM = "PhysicalSystem"
    MATHEMATICAL_OBJECT = "MathematicalObject"
    OPERATOR = "Operator"
    QUANTUM_STATE = "QuantumState"
    APPROXIMATION = "Approximation"
    FORMULA = "Formula"
    SYMBOL = "Symbol"
    DERIVATION = "Derivation"
    EXAMPLE = "Example"
    EXERCISE = "Exercise"
    MISCONCEPTION = "Misconception"
    HINT = "Hint"
    EXPERIMENT = "Experiment"
    VISUALIZATION = "Visualization"
    PROJECT = "Project"
    SOURCE_DOCUMENT = "SourceDocument"
    SOURCE_CHUNK = "SourceChunk"
    EVIDENCE = "Evidence"


class RelationshipType(StrEnum):
    PART_OF = "PART_OF"
    PREREQUISITE_OF = "PREREQUISITE_OF"
    DEFINES = "DEFINES"
    USES = "USES"
    DEPENDS_ON = "DEPENDS_ON"
    DERIVES_FROM = "DERIVES_FROM"
    APPLIES_TO = "APPLIES_TO"
    ACTS_ON = "ACTS_ON"
    COMMUTES_WITH = "COMMUTES_WITH"
    HAS_EIGENSTATE = "HAS_EIGENSTATE"
    APPROXIMATES = "APPROXIMATES"
    VALID_UNDER = "VALID_UNDER"
    CONTRASTS_WITH = "CONTRASTS_WITH"
    RELATED_TO = "RELATED_TO"
    HAS_MISCONCEPTION = "HAS_MISCONCEPTION"
    REMEDIATED_BY = "REMEDIATED_BY"
    VISUALIZED_BY = "VISUALIZED_BY"
    VERIFIED_BY = "VERIFIED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"


class ExtractionReviewStatus(StrEnum):
    """Statuses an extraction process is allowed to assign.

    There is intentionally no ``APPROVED`` member.  Approved/rejected/
    superseded states live in the PostgreSQL review model, not in LLM output.
    """

    PENDING = "pending"
    REVIEW_REQUIRED = "review_required"


class GroundingStatus(StrEnum):
    GROUNDED = "grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNSUPPORTED = "unsupported"


class ExtractionMethod(StrEnum):
    LLM = "llm"
    RULE = "rule"
    IMPORT = "import"
    OCR = "ocr"


type TriplePattern = tuple[NodeType, RelationshipType, NodeType]


_CONTENT_NODE_TYPES: Final[frozenset[NodeType]] = frozenset(
    {
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.PHYSICAL_SYSTEM,
        NodeType.MATHEMATICAL_OBJECT,
        NodeType.OPERATOR,
        NodeType.QUANTUM_STATE,
        NodeType.APPROXIMATION,
        NodeType.FORMULA,
        NodeType.SYMBOL,
        NodeType.DERIVATION,
        NodeType.EXAMPLE,
        NodeType.EXERCISE,
        NodeType.MISCONCEPTION,
        NodeType.HINT,
        NodeType.EXPERIMENT,
        NodeType.VISUALIZATION,
        NodeType.PROJECT,
    }
)


# Every accepted relation is represented by a concrete source/type/target
# triple.  There are no wildcard patterns at validation time.  Small, named
# comprehensions make repeated families inspectable without weakening the
# whitelist.
_STRUCTURAL_PATTERNS: set[TriplePattern] = {
    (NodeType.CHAPTER, RelationshipType.PART_OF, NodeType.COURSE),
    (NodeType.SECTION, RelationshipType.PART_OF, NodeType.CHAPTER),
    (NodeType.SECTION, RelationshipType.PART_OF, NodeType.SECTION),
    (NodeType.SOURCE_DOCUMENT, RelationshipType.PART_OF, NodeType.COURSE),
    (NodeType.SOURCE_CHUNK, RelationshipType.PART_OF, NodeType.SOURCE_DOCUMENT),
    (NodeType.EVIDENCE, RelationshipType.SUPPORTED_BY, NodeType.SOURCE_CHUNK),
}
_STRUCTURAL_PATTERNS.update(
    (node_type, RelationshipType.PART_OF, container)
    for node_type in _CONTENT_NODE_TYPES
    for container in (NodeType.COURSE, NodeType.CHAPTER, NodeType.SECTION)
)

_PEDAGOGICAL_PATTERNS: set[TriplePattern] = {
    (NodeType.CONCEPT, RelationshipType.PREREQUISITE_OF, NodeType.CONCEPT),
    (NodeType.PRINCIPLE, RelationshipType.PREREQUISITE_OF, NodeType.CONCEPT),
    (NodeType.MATHEMATICAL_OBJECT, RelationshipType.PREREQUISITE_OF, NodeType.CONCEPT),
    (NodeType.CONCEPT, RelationshipType.PREREQUISITE_OF, NodeType.DERIVATION),
    (NodeType.CONCEPT, RelationshipType.PREREQUISITE_OF, NodeType.EXERCISE),
    (NodeType.CHAPTER, RelationshipType.DEFINES, NodeType.CONCEPT),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.CONCEPT),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.PRINCIPLE),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.MATHEMATICAL_OBJECT),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.OPERATOR),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.QUANTUM_STATE),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.APPROXIMATION),
    (NodeType.SECTION, RelationshipType.DEFINES, NodeType.SYMBOL),
    (NodeType.CONCEPT, RelationshipType.DEFINES, NodeType.SYMBOL),
    (NodeType.FORMULA, RelationshipType.DEFINES, NodeType.SYMBOL),
    (NodeType.CONCEPT, RelationshipType.HAS_MISCONCEPTION, NodeType.MISCONCEPTION),
    (NodeType.PRINCIPLE, RelationshipType.HAS_MISCONCEPTION, NodeType.MISCONCEPTION),
    (NodeType.FORMULA, RelationshipType.HAS_MISCONCEPTION, NodeType.MISCONCEPTION),
    (NodeType.DERIVATION, RelationshipType.HAS_MISCONCEPTION, NodeType.MISCONCEPTION),
    (NodeType.EXERCISE, RelationshipType.HAS_MISCONCEPTION, NodeType.MISCONCEPTION),
    (NodeType.MISCONCEPTION, RelationshipType.REMEDIATED_BY, NodeType.HINT),
    (NodeType.MISCONCEPTION, RelationshipType.REMEDIATED_BY, NodeType.EXAMPLE),
    (NodeType.MISCONCEPTION, RelationshipType.REMEDIATED_BY, NodeType.EXERCISE),
    (NodeType.MISCONCEPTION, RelationshipType.REMEDIATED_BY, NodeType.VISUALIZATION),
}

_SCIENTIFIC_PATTERNS: set[TriplePattern] = {
    (NodeType.OPERATOR, RelationshipType.ACTS_ON, NodeType.QUANTUM_STATE),
    (NodeType.OPERATOR, RelationshipType.ACTS_ON, NodeType.MATHEMATICAL_OBJECT),
    (NodeType.OPERATOR, RelationshipType.COMMUTES_WITH, NodeType.OPERATOR),
    (NodeType.OPERATOR, RelationshipType.HAS_EIGENSTATE, NodeType.QUANTUM_STATE),
    (NodeType.APPROXIMATION, RelationshipType.APPROXIMATES, NodeType.PHYSICAL_SYSTEM),
    (NodeType.APPROXIMATION, RelationshipType.APPROXIMATES, NodeType.FORMULA),
    (NodeType.FORMULA, RelationshipType.APPROXIMATES, NodeType.FORMULA),
    (NodeType.DERIVATION, RelationshipType.DERIVES_FROM, NodeType.FORMULA),
    (NodeType.DERIVATION, RelationshipType.DERIVES_FROM, NodeType.PRINCIPLE),
    (NodeType.DERIVATION, RelationshipType.DERIVES_FROM, NodeType.DERIVATION),
    (NodeType.FORMULA, RelationshipType.DERIVES_FROM, NodeType.FORMULA),
    (NodeType.FORMULA, RelationshipType.DERIVES_FROM, NodeType.PRINCIPLE),
    (NodeType.PRINCIPLE, RelationshipType.APPLIES_TO, NodeType.PHYSICAL_SYSTEM),
    (NodeType.APPROXIMATION, RelationshipType.APPLIES_TO, NodeType.PHYSICAL_SYSTEM),
    (NodeType.FORMULA, RelationshipType.APPLIES_TO, NodeType.PHYSICAL_SYSTEM),
    (NodeType.CONCEPT, RelationshipType.APPLIES_TO, NodeType.PHYSICAL_SYSTEM),
    (NodeType.FORMULA, RelationshipType.VALID_UNDER, NodeType.APPROXIMATION),
    (NodeType.PRINCIPLE, RelationshipType.VALID_UNDER, NodeType.APPROXIMATION),
    (NodeType.DERIVATION, RelationshipType.VALID_UNDER, NodeType.APPROXIMATION),
    (NodeType.APPROXIMATION, RelationshipType.VALID_UNDER, NodeType.CONCEPT),
    (NodeType.APPROXIMATION, RelationshipType.VALID_UNDER, NodeType.PHYSICAL_SYSTEM),
    (NodeType.FORMULA, RelationshipType.VERIFIED_BY, NodeType.EXPERIMENT),
    (NodeType.PRINCIPLE, RelationshipType.VERIFIED_BY, NodeType.EXPERIMENT),
    (NodeType.DERIVATION, RelationshipType.VERIFIED_BY, NodeType.EXAMPLE),
    (NodeType.FORMULA, RelationshipType.VERIFIED_BY, NodeType.EXAMPLE),
}

_USABLE_TARGETS: Final[frozenset[NodeType]] = frozenset(
    {
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.PHYSICAL_SYSTEM,
        NodeType.MATHEMATICAL_OBJECT,
        NodeType.OPERATOR,
        NodeType.QUANTUM_STATE,
        NodeType.APPROXIMATION,
        NodeType.FORMULA,
        NodeType.SYMBOL,
        NodeType.DERIVATION,
        NodeType.EXAMPLE,
        NodeType.EXPERIMENT,
        NodeType.VISUALIZATION,
    }
)
_USING_SOURCES: Final[frozenset[NodeType]] = frozenset(
    {
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.OPERATOR,
        NodeType.APPROXIMATION,
        NodeType.FORMULA,
        NodeType.DERIVATION,
        NodeType.EXAMPLE,
        NodeType.EXERCISE,
        NodeType.EXPERIMENT,
        NodeType.PROJECT,
    }
)
_USAGE_PATTERNS: set[TriplePattern] = {
    (source, RelationshipType.USES, target)
    for source in _USING_SOURCES
    for target in _USABLE_TARGETS
}
_DEPENDENCY_PATTERNS: set[TriplePattern] = {
    (source, RelationshipType.DEPENDS_ON, target)
    for source in (
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.OPERATOR,
        NodeType.QUANTUM_STATE,
        NodeType.APPROXIMATION,
        NodeType.FORMULA,
        NodeType.DERIVATION,
        NodeType.EXPERIMENT,
        NodeType.PROJECT,
    )
    for target in (
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.MATHEMATICAL_OBJECT,
        NodeType.OPERATOR,
        NodeType.APPROXIMATION,
        NodeType.FORMULA,
    )
}
_VISUALIZATION_PATTERNS: set[TriplePattern] = {
    (source, RelationshipType.VISUALIZED_BY, NodeType.VISUALIZATION)
    for source in (
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.PHYSICAL_SYSTEM,
        NodeType.MATHEMATICAL_OBJECT,
        NodeType.OPERATOR,
        NodeType.QUANTUM_STATE,
        NodeType.FORMULA,
        NodeType.DERIVATION,
        NodeType.EXPERIMENT,
    )
}
_CONTRAST_PATTERNS: set[TriplePattern] = {
    (node_type, RelationshipType.CONTRASTS_WITH, node_type)
    for node_type in (
        NodeType.CONCEPT,
        NodeType.PRINCIPLE,
        NodeType.PHYSICAL_SYSTEM,
        NodeType.MATHEMATICAL_OBJECT,
        NodeType.OPERATOR,
        NodeType.QUANTUM_STATE,
        NodeType.APPROXIMATION,
        NodeType.FORMULA,
    )
}
_RELATED_PATTERNS: set[TriplePattern] = {
    (source, RelationshipType.RELATED_TO, target)
    for source in _CONTENT_NODE_TYPES
    for target in _CONTENT_NODE_TYPES
    if source is target
    or (source, target)
    in {
        (NodeType.CONCEPT, NodeType.PRINCIPLE),
        (NodeType.CONCEPT, NodeType.FORMULA),
        (NodeType.CONCEPT, NodeType.EXAMPLE),
        (NodeType.CONCEPT, NodeType.EXERCISE),
        (NodeType.CONCEPT, NodeType.EXPERIMENT),
        (NodeType.CONCEPT, NodeType.PROJECT),
        (NodeType.PRINCIPLE, NodeType.FORMULA),
        (NodeType.PHYSICAL_SYSTEM, NodeType.EXPERIMENT),
        (NodeType.FORMULA, NodeType.DERIVATION),
        (NodeType.EXAMPLE, NodeType.EXERCISE),
        (NodeType.EXPERIMENT, NodeType.PROJECT),
    }
}
_SUPPORT_PATTERNS: set[TriplePattern] = {
    (node_type, RelationshipType.SUPPORTED_BY, NodeType.EVIDENCE)
    for node_type in ({NodeType.COURSE, NodeType.CHAPTER, NodeType.SECTION} | _CONTENT_NODE_TYPES)
}
_SUPPORT_PATTERNS.update(
    (node_type, RelationshipType.SUPPORTED_BY, NodeType.SOURCE_CHUNK)
    for node_type in _CONTENT_NODE_TYPES
)

ALLOWED_TRIPLE_PATTERNS: Final[frozenset[TriplePattern]] = frozenset(
    _STRUCTURAL_PATTERNS
    | _PEDAGOGICAL_PATTERNS
    | _SCIENTIFIC_PATTERNS
    | _USAGE_PATTERNS
    | _DEPENDENCY_PATTERNS
    | _VISUALIZATION_PATTERNS
    | _CONTRAST_PATTERNS
    | _RELATED_PATTERNS
    | _SUPPORT_PATTERNS
)

NODE_LABEL_WHITELIST: Final[frozenset[str]] = frozenset(item.value for item in NodeType)
RELATIONSHIP_TYPE_WHITELIST: Final[frozenset[str]] = frozenset(
    item.value for item in RelationshipType
)

MIN_CONFIDENT_GROUNDING: Final[float] = 0.75


def is_allowed_triple(
    source_type: NodeType | str,
    relationship_type: RelationshipType | str,
    target_type: NodeType | str,
) -> bool:
    """Return whether a fully concrete ontology triple is permitted."""

    try:
        triple = (
            NodeType(source_type),
            RelationshipType(relationship_type),
            NodeType(target_type),
        )
    except ValueError:
        return False
    return triple in ALLOWED_TRIPLE_PATTERNS


def normalize_evidence_text(text: str) -> str:
    """Normalize Unicode, case and whitespace for quote containment checks."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def evidence_quote_is_substring(quote: str, source_chunk_text: str | None) -> bool:
    """Verify evidence without inventing offsets or approximate matching."""

    if source_chunk_text is None:
        return False
    normalized_quote = normalize_evidence_text(quote)
    normalized_source = normalize_evidence_text(source_chunk_text)
    return bool(normalized_quote) and normalized_quote in normalized_source


class EvidenceReference(BaseModel):
    """Auditable provenance hydrated from one authoritative source chunk."""

    model_config = ConfigDict(extra="forbid")

    source_document_id: str = Field(min_length=1)
    source_chunk_id: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    document_version_id: str | None = None
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    chunk_checksum: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    chapter: str | None = None
    section_path: tuple[str, ...] = ()
    page_number: int | None = Field(default=None, ge=1)
    page_label: str | None = None
    slide_number: int | None = Field(default=None, ge=1)
    locator_type: Literal["page", "slide", "paragraph", "sheet_row", "line"] | None = None
    locator_start: str | int | None = None
    locator_end: str | int | None = None
    quote: str = ""
    source_chunk_text: str | None = Field(default=None, repr=False)
    quote_start: int | None = Field(default=None, ge=0)
    quote_end: int | None = Field(default=None, ge=0)
    quote_verified: bool = Field(default=False, description="Computed; caller input is ignored")
    verification_note: str | None = Field(
        default=None, description="Computed; caller input is ignored"
    )

    @model_validator(mode="after")
    def verify_quote(self) -> EvidenceReference:
        note: str | None = None
        verified = evidence_quote_is_substring(self.quote, self.source_chunk_text)
        if self.source_chunk_text is None:
            note = "source_chunk_text_missing"
        elif not normalize_evidence_text(self.quote):
            note = "evidence_quote_empty"
        elif not verified:
            note = "evidence_quote_not_normalized_substring"

        offsets_supplied = self.quote_start is not None or self.quote_end is not None
        if offsets_supplied:
            if self.quote_start is None or self.quote_end is None:
                verified = False
                note = "evidence_offsets_incomplete"
            elif self.source_chunk_text is None:
                verified = False
                note = "source_chunk_text_missing"
            elif self.quote_end < self.quote_start or self.quote_end > len(self.source_chunk_text):
                verified = False
                note = "evidence_offsets_out_of_bounds"
            else:
                offset_text = self.source_chunk_text[self.quote_start : self.quote_end]
                if normalize_evidence_text(offset_text) != normalize_evidence_text(self.quote):
                    verified = False
                    note = "evidence_offsets_do_not_match_quote"

        # Computed fields cannot be spoofed by an extraction response.
        object.__setattr__(self, "quote_verified", verified)
        object.__setattr__(self, "verification_note", None if verified else note)
        return self


def _validate_json_object(value: dict[str, Any]) -> dict[str, Any]:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("properties must contain finite JSON values") from exc
    return value


def _assess_grounding(
    *,
    provenance: tuple[EvidenceReference, ...],
    confidence: float,
    requested_status: ExtractionReviewStatus,
    existing_reasons: tuple[str, ...],
    extra_reasons: tuple[str, ...] = (),
) -> tuple[GroundingStatus, ExtractionReviewStatus, tuple[str, ...]]:
    verified_count = sum(item.quote_verified for item in provenance)
    if provenance and verified_count == len(provenance):
        grounding = GroundingStatus.GROUNDED
    elif verified_count:
        grounding = GroundingStatus.PARTIALLY_GROUNDED
    else:
        grounding = GroundingStatus.UNSUPPORTED

    reasons = set(existing_reasons)
    reasons.update(extra_reasons)
    if not provenance:
        reasons.add("no_evidence_provenance")
    for item in provenance:
        if not item.quote_verified:
            reasons.add(f"{item.verification_note or 'evidence_unverified'}:{item.source_chunk_id}")
    if confidence < MIN_CONFIDENT_GROUNDING:
        reasons.add("confidence_below_grounding_threshold")

    must_review = (
        grounding is not GroundingStatus.GROUNDED
        or confidence < MIN_CONFIDENT_GROUNDING
        or bool(reasons)
    )
    status = ExtractionReviewStatus.REVIEW_REQUIRED if must_review else requested_status
    return grounding, status, tuple(sorted(reasons))


class NodeCandidate(BaseModel):
    """Typed node proposal.  This is never an approval record."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    course_id: str = Field(min_length=1)
    curriculum_edition_id: str = Field(min_length=1)
    node_type: NodeType
    canonical_key: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=512)
    description: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    extraction_method: ExtractionMethod = ExtractionMethod.LLM
    extraction_run_id: str | None = None
    provenance: tuple[EvidenceReference, ...] = ()
    grounding: GroundingStatus = GroundingStatus.UNSUPPORTED
    status: ExtractionReviewStatus = ExtractionReviewStatus.PENDING
    review_reasons: tuple[str, ...] = ()

    @field_validator("candidate_id", "course_id", "curriculum_edition_id", "canonical_key", "label")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_object(value)

    @model_validator(mode="after")
    def enforce_grounding_review(self) -> NodeCandidate:
        grounding, status, reasons = _assess_grounding(
            provenance=self.provenance,
            confidence=self.confidence,
            requested_status=self.status,
            existing_reasons=self.review_reasons,
        )
        object.__setattr__(self, "grounding", grounding)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "review_reasons", reasons)
        return self


class RelationshipCandidate(BaseModel):
    """Typed relationship proposal with concrete endpoint ontology types."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    course_id: str = Field(min_length=1)
    curriculum_edition_id: str = Field(min_length=1)
    relationship_type: RelationshipType
    source_candidate_id: str = Field(min_length=1)
    target_candidate_id: str = Field(min_length=1)
    source_node_type: NodeType
    target_node_type: NodeType
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    extraction_method: ExtractionMethod = ExtractionMethod.LLM
    extraction_run_id: str | None = None
    provenance: tuple[EvidenceReference, ...] = ()
    grounding: GroundingStatus = GroundingStatus.UNSUPPORTED
    status: ExtractionReviewStatus = ExtractionReviewStatus.PENDING
    review_reasons: tuple[str, ...] = ()

    @field_validator(
        "candidate_id",
        "course_id",
        "curriculum_edition_id",
        "source_candidate_id",
        "target_candidate_id",
    )
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_object(value)

    @model_validator(mode="after")
    def enforce_ontology_and_grounding_review(self) -> RelationshipCandidate:
        extra_reasons: tuple[str, ...] = ()
        if not is_allowed_triple(
            self.source_node_type,
            self.relationship_type,
            self.target_node_type,
        ):
            extra_reasons = ("ontology_pattern_not_allowed",)
        grounding, status, reasons = _assess_grounding(
            provenance=self.provenance,
            confidence=self.confidence,
            requested_status=self.status,
            existing_reasons=self.review_reasons,
            extra_reasons=extra_reasons,
        )
        object.__setattr__(self, "grounding", grounding)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "review_reasons", reasons)
        return self


class ExtractionCandidateBatch(BaseModel):
    """Validated structured-output envelope for an extraction call."""

    model_config = ConfigDict(extra="forbid")

    nodes: tuple[NodeCandidate, ...] = ()
    relationships: tuple[RelationshipCandidate, ...] = ()


_NODE_DESCRIPTIONS: Final[dict[NodeType, str]] = {
    NodeType.COURSE: "A governed university course and its curriculum edition.",
    NodeType.CHAPTER: "A chapter in the course's authoritative teaching order.",
    NodeType.SECTION: "A page/slide-grounded section or subsection.",
    NodeType.CONCEPT: "A named quantum-physics idea taught by the course.",
    NodeType.PRINCIPLE: "A physical postulate, law, theorem, or principle.",
    NodeType.PHYSICAL_SYSTEM: "A physical system to which quantum theory is applied.",
    NodeType.MATHEMATICAL_OBJECT: "A mathematical structure used in the course.",
    NodeType.OPERATOR: "A quantum-mechanical operator with its course notation.",
    NodeType.QUANTUM_STATE: "A ket, wavefunction, eigenstate, or state family.",
    NodeType.APPROXIMATION: "An approximation together with its validity conditions.",
    NodeType.FORMULA: "A formula preserving the course's exact notation and assumptions.",
    NodeType.SYMBOL: "A symbol whose meaning and scope are explicitly defined.",
    NodeType.DERIVATION: "An ordered derivation grounded in source steps.",
    NodeType.EXAMPLE: "A worked or illustrative example from the materials.",
    NodeType.EXERCISE: "An exercise or assessment item from the materials.",
    NodeType.MISCONCEPTION: "A teacher-reviewable misunderstanding, never inferred as fact.",
    NodeType.HINT: "A staged hint governed by an answer-release policy.",
    NodeType.EXPERIMENT: "A physical or computational experiment.",
    NodeType.VISUALIZATION: "A course figure or reproducible scientific visualization.",
    NodeType.PROJECT: "A course project, milestone, or deliverable.",
    NodeType.SOURCE_DOCUMENT: "An immutable version of an authoritative course file.",
    NodeType.SOURCE_CHUNK: "A locator-aware chunk preserving exact source text.",
    NodeType.EVIDENCE: "A quote and locator that supports a graph claim.",
}

_RELATIONSHIP_DESCRIPTIONS: Final[dict[RelationshipType, str]] = {
    item: re.sub(r"_+", " ", item.value).lower() for item in RelationshipType
}


def simple_kg_pipeline_schema() -> dict[str, Any]:
    """Return the constrained schema accepted by official SimpleKGPipeline.

    This is an extraction adapter only.  ``SimpleKGPipeline`` must not write
    directly to the production graph: convert its output to the candidates
    above, hydrate/verify provenance, persist it to PostgreSQL, and require a
    teacher review decision before calling ``GraphStore.sync_*``.
    """

    return {
        "node_types": [
            {
                "label": node_type.value,
                "description": _NODE_DESCRIPTIONS[node_type],
                "properties": [
                    {"name": "name", "type": "STRING"},
                    {"name": "description", "type": "STRING"},
                    {"name": "canonical_key", "type": "STRING"},
                ],
            }
            for node_type in NodeType
        ],
        "relationship_types": [
            {
                "label": relationship_type.value,
                "description": _RELATIONSHIP_DESCRIPTIONS[relationship_type],
            }
            for relationship_type in RelationshipType
        ],
        "patterns": [
            (source.value, relationship.value, target.value)
            for source, relationship, target in sorted(
                ALLOWED_TRIPLE_PATTERNS,
                key=lambda item: (item[0].value, item[1].value, item[2].value),
            )
        ],
        "additional_node_types": False,
    }
