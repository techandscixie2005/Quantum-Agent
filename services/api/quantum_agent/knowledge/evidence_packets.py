"""Student-safe retrieval contract carrying original evidence and provenance."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalChannel(StrEnum):
    FULL_TEXT = "postgres_full_text"
    SEMANTIC = "pgvector_semantic"
    GRAPH = "neo4j_graph"


class EvidenceKind(StrEnum):
    COURSE_MATERIAL = "course_material"
    TEACHER_CURATED = "teacher_curated"
    SYMBOLIC_VERIFICATION = "symbolic_verification"
    NUMERICAL_VERIFICATION = "numerical_verification"
    SIMULATION = "simulation"
    CODE_TEST = "code_test"
    MODEL_INFERENCE = "model_inference"


class LocatorType(StrEnum):
    PDF_PAGE = "pdf_page"
    SLIDE = "slide"
    DOCX_PARAGRAPH = "docx_paragraph"
    XLSX_ROW = "xlsx_row"
    TEXT_LINES = "text_lines"


class EvidenceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locator_type: LocatorType
    physical_page: int | None = Field(default=None, ge=1)
    printed_page_label: str | None = None
    slide_number: int | None = Field(default=None, ge=1)
    paragraph_start: int | None = Field(default=None, ge=1)
    paragraph_end: int | None = Field(default=None, ge=1)
    sheet_name: str | None = None
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_matching_locator(self) -> EvidenceLocator:
        present = {
            LocatorType.PDF_PAGE: self.physical_page is not None,
            LocatorType.SLIDE: self.slide_number is not None,
            LocatorType.DOCX_PARAGRAPH: self.paragraph_start is not None,
            LocatorType.XLSX_ROW: self.sheet_name is not None and self.row_start is not None,
            LocatorType.TEXT_LINES: self.line_start is not None,
        }
        if not present[self.locator_type]:
            raise ValueError(f"{self.locator_type.value} locator is incomplete")
        return self


class RetrievalContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: RetrievalChannel
    rank: int = Field(ge=1)
    raw_score: float | None = None
    fused_score: float = Field(ge=0)


class EvidenceItem(BaseModel):
    """Immutable source text returned to a caller, not a generated paraphrase."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_title: str = Field(min_length=1)
    document_version: int = Field(ge=1)
    source_file_name: str = Field(min_length=1)
    source_file_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    source_chunk_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    evidence_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    curriculum_edition_id: UUID | None = None
    chapter: str | None = None
    section_path: list[str] = Field(default_factory=list)
    locator: EvidenceLocator
    source_chunk: str = Field(min_length=1)
    evidence_snippet: str = Field(min_length=1)
    kind: EvidenceKind = EvidenceKind.COURSE_MATERIAL
    authority_priority: int = Field(ge=0, le=100)
    contributions: list[RetrievalContribution] = Field(min_length=1)

    @model_validator(mode="after")
    def snippet_must_come_from_source(self) -> EvidenceItem:
        def normalize(value: str) -> str:
            return "".join(value.casefold().split())

        if normalize(self.evidence_snippet) not in normalize(self.source_chunk):
            raise ValueError("evidence_snippet is not grounded in source_chunk")
        if hashlib.sha256(self.source_chunk.encode("utf-8")).hexdigest() != (
            self.source_chunk_sha256
        ):
            raise ValueError("source_chunk_sha256 does not match source_chunk")
        if hashlib.sha256(self.evidence_snippet.encode("utf-8")).hexdigest() != (
            self.evidence_sha256
        ):
            raise ValueError("evidence_sha256 does not match evidence_snippet")
        return self

    def redacted_for_gate(self) -> EvidenceItem:
        """Return a copy with answer-bearing text replaced by safe provenance.

        Used by the commitment gate (PRD V3.0 Axiom 1) so the student cannot
        read the exact answer-bearing snippet while the gate is still open.
        Provenance (document title, chapter, locator, evidence id) is preserved
        so the student knows evidence exists and where it comes from.
        """

        placeholder = "[evidence withheld while the commitment gate is active]"
        return EvidenceItem(
            evidence_id=self.evidence_id,
            chunk_id=self.chunk_id,
            document_id=self.document_id,
            document_version_id=self.document_version_id,
            document_title=self.document_title,
            document_version=self.document_version,
            source_file_name=self.source_file_name,
            source_file_sha256=self.source_file_sha256,
            source_chunk_sha256=hashlib.sha256(placeholder.encode("utf-8")).hexdigest(),
            evidence_sha256=hashlib.sha256(placeholder.encode("utf-8")).hexdigest(),
            curriculum_edition_id=self.curriculum_edition_id,
            chapter=self.chapter,
            section_path=list(self.section_path),
            locator=self.locator,
            source_chunk=placeholder,
            evidence_snippet=placeholder,
            kind=self.kind,
            authority_priority=self.authority_priority,
            contributions=list(self.contributions),
        )


class GraphContextNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    node_type: str
    name: str
    aliases: list[str] = Field(default_factory=list)


class GraphContextEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_id: UUID
    target_id: UUID
    relation_type: str


class RetrievalCoverage(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"


class EvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    course_id: UUID
    curriculum_edition_id: UUID
    query: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    coverage: RetrievalCoverage
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=6)
    graph_nodes: list[GraphContextNode] = Field(default_factory=list)
    graph_edges: list[GraphContextEdge] = Field(default_factory=list)
    degraded_channels: list[RetrievalChannel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coverage_matches_evidence(self) -> EvidencePacket:
        if self.coverage is RetrievalCoverage.NOT_FOUND and self.evidence:
            raise ValueError("not_found packets cannot contain evidence")
        if self.coverage is not RetrievalCoverage.NOT_FOUND and not self.evidence:
            raise ValueError("covered packets must contain original evidence")
        return self

    def citation_ids(self) -> set[UUID]:
        return {item.evidence_id for item in self.evidence}

    def redacted_for_gate(self) -> EvidencePacket:
        """Return a copy where every evidence item's answer-bearing text is redacted.

        Provenance (document, chapter, locator, evidence id) is preserved so
        the student knows evidence exists and where it comes from, but the
        exact answer-bearing snippet is withheld until the commitment gate
        is satisfied (PRD V3.0 Axiom 1).
        """

        return EvidencePacket(
            id=self.id,
            course_id=self.course_id,
            curriculum_edition_id=self.curriculum_edition_id,
            query=self.query,
            created_at=self.created_at,
            coverage=self.coverage,
            evidence=[item.redacted_for_gate() for item in self.evidence],
            graph_nodes=list(self.graph_nodes),
            graph_edges=list(self.graph_edges),
            degraded_channels=list(self.degraded_channels),
            warnings=list(self.warnings),
        )


RRF_K: Annotated[int, Field(ge=1)] = 60
