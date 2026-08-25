"""Strict, source-hydrated quantum knowledge extraction.

The model proposes local entities and relationships.  Application code assigns
tenant IDs, candidate IDs, source locators and evidence.  Every proposal remains
`REVIEW_REQUIRED`, including a well-grounded one, until a teacher decision is
persisted.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantum_agent.knowledge.ingestion import (
    LocatorType as IngestionLocatorType,
)
from quantum_agent.knowledge.ingestion import (
    SourceChunk,
)
from quantum_agent.knowledge.ontology import (
    EvidenceReference,
    ExtractionCandidateBatch,
    ExtractionMethod,
    ExtractionReviewStatus,
    NodeCandidate,
    NodeType,
    RelationshipCandidate,
    RelationshipType,
)
from quantum_agent.llm.gateway import Message, ModelGateway, ModelTier

EXTRACTABLE_NODE_TYPES = frozenset(
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


class RawExtractedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(min_length=1, max_length=80)
    node_type: NodeType
    canonical_key: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=512)
    description: str | None = None
    formula_latex: str | None = None
    aliases: list[str] = Field(default_factory=list, max_length=12)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_quote: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator("node_type")
    @classmethod
    def content_nodes_only(cls, value: NodeType) -> NodeType:
        if value not in EXTRACTABLE_NODE_TYPES:
            raise ValueError("course/source structure is imported deterministically")
        return value


class RawExtractedRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: RelationshipType
    source_local_id: str = Field(min_length=1, max_length=80)
    target_local_id: str = Field(min_length=1, max_length=80)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_quote: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class RawChunkExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[RawExtractedNode] = Field(default_factory=list, max_length=40)
    relationships: list[RawExtractedRelationship] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def validate_local_references(self) -> RawChunkExtraction:
        ids = [node.local_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("local node IDs must be unique")
        known = set(ids)
        dangling = {
            endpoint
            for relation in self.relationships
            for endpoint in (relation.source_local_id, relation.target_local_id)
            if endpoint not in known
        }
        if dangling:
            raise ValueError(f"relationship endpoints are missing: {sorted(dangling)}")
        return self


class ExtractionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    curriculum_edition_id: str
    source_document_id: str
    source_file: str
    document_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    document_version_id: str
    chapter: str | None = None
    extraction_run_id: str | None = None


SYSTEM_INSTRUCTIONS = """You extract candidate knowledge from one authoritative
Quantum Physics course chunk. Use only the supplied chunk. Preserve the source's
terminology, notation and language. Every entity and relationship needs a short
verbatim evidence_quote copied from the chunk. Do not create Course, Chapter,
Section, SourceDocument, SourceChunk or Evidence nodes; application code owns them.
Do not repair a typo silently: keep the verbatim label and place a proposed canonical
form in aliases/properties. Do not infer prerequisites or scientific claims that the
chunk does not state. If a formula is corrupted or uncertain, keep the exact quote and
lower confidence. Misconceptions and hints may be extracted only when the source
explicitly teaches or warns about them. Return an empty list when the chunk contains
no confident extractable knowledge.
"""


def _candidate_id(context: ExtractionContext, node: RawExtractedNode) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "|".join(
                (
                    context.course_id,
                    context.curriculum_edition_id,
                    node.node_type.value,
                    node.canonical_key.casefold().strip(),
                )
            ),
        )
    )


def _relation_id(
    context: ExtractionContext,
    relation: RawExtractedRelationship,
    source_candidate_id: str,
    target_candidate_id: str,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "|".join(
                (
                    context.course_id,
                    context.curriculum_edition_id,
                    source_candidate_id,
                    relation.relationship_type.value,
                    target_candidate_id,
                )
            ),
        )
    )


def _locator_type(chunk: SourceChunk) -> str:
    return {
        IngestionLocatorType.PAGE: "page",
        IngestionLocatorType.SLIDE: "slide",
        IngestionLocatorType.PARAGRAPH: "paragraph",
        IngestionLocatorType.SHEET_ROW: "sheet_row",
        IngestionLocatorType.LINE: "line",
    }[chunk.locator.locator_type]


def _provenance(
    context: ExtractionContext,
    chunk: SourceChunk,
    evidence_quote: str,
) -> EvidenceReference:
    return EvidenceReference(
        source_document_id=context.source_document_id,
        source_chunk_id=chunk.id,
        source_file=context.source_file,
        document_version_id=context.document_version_id,
        document_sha256=context.document_sha256,
        chunk_checksum=chunk.checksum,
        chapter=context.chapter,
        section_path=chunk.section_path,
        page_number=chunk.locator.physical_page,
        page_label=chunk.locator.page_label,
        slide_number=(
            int(chunk.locator.start)
            if chunk.locator.locator_type is IngestionLocatorType.SLIDE
            else None
        ),
        locator_type=_locator_type(chunk),
        locator_start=chunk.locator.start,
        locator_end=chunk.locator.end,
        quote=evidence_quote,
        source_chunk_text=chunk.exact_text,
    )


def hydrate_candidates(
    raw: RawChunkExtraction,
    *,
    context: ExtractionContext,
    chunk: SourceChunk,
) -> ExtractionCandidateBatch:
    local_nodes = {node.local_id: node for node in raw.nodes}
    candidate_ids = {
        local_id: _candidate_id(context, node) for local_id, node in local_nodes.items()
    }
    nodes = tuple(
        NodeCandidate(
            candidate_id=candidate_ids[node.local_id],
            course_id=context.course_id,
            curriculum_edition_id=context.curriculum_edition_id,
            node_type=node.node_type,
            canonical_key=node.canonical_key,
            label=node.label,
            description=node.description,
            properties={
                **node.properties,
                **({"formula_latex": node.formula_latex} if node.formula_latex else {}),
                **({"aliases": node.aliases} if node.aliases else {}),
            },
            confidence=node.confidence,
            extraction_method=ExtractionMethod.LLM,
            extraction_run_id=context.extraction_run_id,
            provenance=(_provenance(context, chunk, node.evidence_quote),),
            status=ExtractionReviewStatus.REVIEW_REQUIRED,
            review_reasons=("teacher_approval_required",),
        )
        for node in raw.nodes
    )
    relationships = tuple(
        RelationshipCandidate(
            candidate_id=_relation_id(
                context,
                relation,
                candidate_ids[relation.source_local_id],
                candidate_ids[relation.target_local_id],
            ),
            course_id=context.course_id,
            curriculum_edition_id=context.curriculum_edition_id,
            relationship_type=relation.relationship_type,
            source_candidate_id=candidate_ids[relation.source_local_id],
            target_candidate_id=candidate_ids[relation.target_local_id],
            source_node_type=local_nodes[relation.source_local_id].node_type,
            target_node_type=local_nodes[relation.target_local_id].node_type,
            properties=relation.properties,
            confidence=relation.confidence,
            extraction_method=ExtractionMethod.LLM,
            extraction_run_id=context.extraction_run_id,
            provenance=(_provenance(context, chunk, relation.evidence_quote),),
            status=ExtractionReviewStatus.REVIEW_REQUIRED,
            review_reasons=("teacher_approval_required",),
        )
        for relation in raw.relationships
    )
    return ExtractionCandidateBatch(nodes=nodes, relationships=relationships)


class QuantumKnowledgeExtractor:
    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

    async def extract_chunk(
        self,
        *,
        context: ExtractionContext,
        chunk: SourceChunk,
    ) -> ExtractionCandidateBatch:
        raw = await self._gateway.structured_generate(
            task="quantum_course_knowledge_extraction",
            messages=[
                Message(role="system", content=SYSTEM_INSTRUCTIONS),
                Message(
                    role="user",
                    content=(
                        f"Source file: {context.source_file}\n"
                        f"Chapter: {context.chapter or 'not supplied'}\n"
                        f"Section path: {' > '.join(chunk.section_path) or 'not supplied'}\n"
                        f"Locator: {_locator_type(chunk)} {chunk.locator.start}\n\n"
                        "AUTHORITATIVE SOURCE CHUNK\n"
                        f"{chunk.exact_text}"
                    ),
                ),
            ],
            output_type=RawChunkExtraction,
            model_tier=ModelTier.DEFAULT,
        )
        return hydrate_candidates(raw, context=context, chunk=chunk)


async def extract_chunks(
    extractor: QuantumKnowledgeExtractor,
    *,
    context: ExtractionContext,
    chunks: Sequence[SourceChunk],
) -> list[ExtractionCandidateBatch]:
    # Deliberately sequential by default: preserves provider rate limits and
    # deterministic trace order. A bounded worker controls concurrency outside
    # this pure extraction service when the endpoint has been load-tested.
    batches: list[ExtractionCandidateBatch] = []
    for chunk in chunks:
        batches.append(await extractor.extract_chunk(context=context, chunk=chunk))
    return batches
