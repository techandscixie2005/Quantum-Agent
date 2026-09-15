"""Extract pedagogical candidates from persisted, immutable course chunks.

No approval or publication occurs here. Every candidate and relation receives
an exact quote support, and reruns preserve existing teacher decisions.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.db_models import (
    CandidateOrigin,
    CandidateStatus,
    DocumentChunk,
    Evidence,
    EvidenceStatus,
    ExtractionRun,
    ExtractionRunStatus,
    GraphNodeCandidate,
    GraphNodeType,
    GraphRelationCandidate,
    GraphRelationType,
    NodeCandidateEvidenceSupport,
    RelationCandidateEvidenceSupport,
)
from quantum_agent.knowledge.extraction import SYSTEM_INSTRUCTIONS, RawChunkExtraction
from quantum_agent.knowledge.ontology import is_allowed_triple
from quantum_agent.knowledge.pipeline import deterministic_uuid
from quantum_agent.knowledge.retrieval import (
    STUDENT_VISIBLE_CHUNKS,
    RetrievalScope,
    is_instructional_passage,
)
from quantum_agent.llm.gateway import Message, ModelGateway, ModelTier

INSTRUCTIONS = SYSTEM_INSTRUCTIONS + """
Focus on DerivationStep, Assumption, ValidityCondition, Misconception and Hint,
and the Formula/Derivation/Concept they support. Connect steps using DERIVES_FROM,
conditions with VALID_UNDER, misconceptions with HAS_MISCONCEPTION and REMEDIATED_BY.
Do not invent a misconception merely to fill the schema. A source without an
explicit warning should have no misconception candidate.
Quotes must preserve original characters: use short prose spans instead of
reconstructing a matrix layout or replacing intervening text with ellipses.
"""


def grounded_subset(raw: RawChunkExtraction, content: str) -> RawChunkExtraction:
    """Retain supported candidates; whitespace alignment never repairs symbols."""

    positions = [i for i, char in enumerate(content) if not char.isspace()]
    normalized = "".join(content[i] for i in positions)

    def exact_quote(quote: str) -> str | None:
        needle = "".join(quote.split())
        start = normalized.find(needle)
        if not needle or start < 0:
            return None
        return content[positions[start]:positions[start + len(needle) - 1] + 1]

    nodes = []
    for node in raw.nodes:
        quote = exact_quote(node.evidence_quote)
        if quote is not None:
            nodes.append(node.model_copy(update={"evidence_quote": quote}))
    by_id = {node.local_id: node for node in nodes}
    relationships = []
    for relation in raw.relationships:
        quote = exact_quote(relation.evidence_quote)
        if (
            quote is not None and relation.source_local_id in by_id
            and relation.target_local_id in by_id
            and is_allowed_triple(
                by_id[relation.source_local_id].node_type, relation.relationship_type,
                by_id[relation.target_local_id].node_type,
            )
        ):
            relationships.append(relation.model_copy(update={"evidence_quote": quote}))
    return RawChunkExtraction(nodes=nodes, relationships=relationships)


def validate_extraction(raw: RawChunkExtraction, content: str) -> None:
    nodes = {node.local_id: node for node in raw.nodes}
    quotes = [node.evidence_quote for node in raw.nodes]
    quotes.extend(relation.evidence_quote for relation in raw.relationships)
    for quote in quotes:
        if quote not in content:
            raise ValueError("candidate quote is not an exact source span")
    for relation in raw.relationships:
        if not is_allowed_triple(
            nodes[relation.source_local_id].node_type,
            relation.relationship_type,
            nodes[relation.target_local_id].node_type,
        ):
            raise ValueError("candidate relationship is outside the ontology")


async def persist_extraction(
    session: AsyncSession, *, scope: RetrievalScope, chunk: DocumentChunk,
    raw: RawChunkExtraction, run: ExtractionRun,
) -> dict[str, int]:
    validate_extraction(raw, chunk.content)
    quotes = {node.evidence_quote for node in raw.nodes}
    quotes.update(relation.evidence_quote for relation in raw.relationships)
    evidence_ids: dict[str, UUID] = {}
    for quote in sorted(quotes):
        start = chunk.content.index(quote)
        evidence_id = deterministic_uuid("pedagogical-evidence", chunk.id, start, quote)
        evidence_ids[quote] = evidence_id
        existing = await session.scalar(select(Evidence).where(
            Evidence.source_chunk_id == chunk.id, Evidence.char_start == start,
            Evidence.char_end == start + len(quote),
            Evidence.evidence_sha256 == hashlib.sha256(quote.encode()).hexdigest(),
        ))
        if existing is not None:
            evidence_ids[quote] = existing.id
        else:
            session.add(Evidence(
                id=evidence_id, source_chunk_id=chunk.id, evidence_snippet=quote,
                char_start=start, char_end=start + len(quote),
                evidence_sha256=hashlib.sha256(quote.encode()).hexdigest(),
                chunk_content_sha256=chunk.content_sha256, status=EvidenceStatus.GROUNDED,
                locator_json={"physical_page": chunk.physical_page, "start": chunk.locator_start},
            ))
    await session.flush()
    ids: dict[str, UUID] = {}
    for node in raw.nodes:
        candidate_id = deterministic_uuid(
            "pedagogical-node", scope.curriculum_edition_id, chunk.id,
            node.node_type.name, node.canonical_key,
        )
        ids[node.local_id] = candidate_id
        if await session.get(GraphNodeCandidate, candidate_id) is not None:
            continue
        session.add(GraphNodeCandidate(
            id=candidate_id, course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id, extraction_run_id=run.id,
            node_type=GraphNodeType[node.node_type.name],
            canonical_key=f"pedagogical:{chunk.id}:{node.canonical_key}",
            label=node.label, description=node.description, formula_latex=node.formula_latex,
            properties_json={**node.properties, "aliases": node.aliases},
            origin=CandidateOrigin.LLM, confidence=node.confidence,
            status=CandidateStatus.REVIEW_REQUIRED,
        ))
        await session.flush()
        session.add(NodeCandidateEvidenceSupport(
            node_candidate_id=candidate_id, evidence_id=evidence_ids[node.evidence_quote],
            confidence=node.confidence,
            extraction_span_json={"quote": node.evidence_quote},
        ))
    await session.flush()
    for relation in raw.relationships:
        source, target = ids[relation.source_local_id], ids[relation.target_local_id]
        candidate_id = deterministic_uuid(
            "pedagogical-relation", source, relation.relationship_type.name, target,
        )
        if await session.get(GraphRelationCandidate, candidate_id) is not None:
            continue
        session.add(GraphRelationCandidate(
            id=candidate_id, course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id, extraction_run_id=run.id,
            source_node_candidate_id=source, target_node_candidate_id=target,
            relation_type=GraphRelationType[relation.relationship_type.name],
            canonical_key=f"pedagogical:{candidate_id}", properties_json=relation.properties,
            origin=CandidateOrigin.LLM, confidence=relation.confidence,
            status=CandidateStatus.REVIEW_REQUIRED,
        ))
        await session.flush()
        session.add(RelationCandidateEvidenceSupport(
            relation_candidate_id=candidate_id,
            evidence_id=evidence_ids[relation.evidence_quote], confidence=relation.confidence,
            extraction_span_json={"quote": relation.evidence_quote},
        ))
    await session.flush()
    return {"nodes": len(raw.nodes), "relations": len(raw.relationships)}


async def extract_pedagogical_content(
    session: AsyncSession, *, scope: RetrievalScope, gateway: ModelGateway,
    query: str, limit: int = 4,
) -> list[dict[str, object]]:
    if not query.strip() or not 1 <= limit <= 50:
        raise ValueError("query is required and limit must be 1-50")
    visible = select(STUDENT_VISIBLE_CHUNKS.c.id).where(
        STUDENT_VISIBLE_CHUNKS.c.course_id == scope.course_id,
        STUDENT_VISIBLE_CHUNKS.c.publication_curriculum_edition_id == scope.curriculum_edition_id,
    )
    chunks = (await session.scalars(
        select(DocumentChunk).where(
            DocumentChunk.id.in_(visible), DocumentChunk.content.contains(query, autoescape=True),
        ).order_by(DocumentChunk.document_version_id, DocumentChunk.ordinal).limit(limit)
    )).all()
    report: list[dict[str, object]] = []
    for chunk in chunks:
        if not is_instructional_passage(chunk.content):
            continue
        run_id = deterministic_uuid("pedagogical-run-v2", scope.curriculum_edition_id, chunk.id)
        run = await session.get(ExtractionRun, run_id)
        if run is not None and run.status == ExtractionRunStatus.SUCCEEDED:
            report.append({"chunk_id": str(chunk.id), "replay": True, **run.metrics_json})
            continue
        if run is None:
            run = ExtractionRun(
                id=run_id, document_version_id=chunk.document_version_id,
                pipeline_name="pedagogical-content", pipeline_version="2", ontology_version="1.1",
                configuration_sha256=hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
                status=ExtractionRunStatus.RUNNING, started_at=datetime.now(UTC),
            )
            session.add(run)
            await session.flush()
        try:
            raw = await gateway.structured_generate(
                task="quantum_course_knowledge_extraction",
                messages=[Message(role="system", content=INSTRUCTIONS),
                          Message(role="user", content=chunk.content)],
                output_type=RawChunkExtraction, model_tier=ModelTier.DEFAULT,
            )
            run.metrics_json = {"raw_candidates": raw.model_dump(mode="json")}
            grounded = grounded_subset(raw, chunk.content)
            async with session.begin_nested():
                counts = await persist_extraction(
                    session, scope=scope, chunk=chunk, raw=grounded, run=run,
                )
            run.status = ExtractionRunStatus.SUCCEEDED
            run.error_summary = None
            run.metrics_json = {
                **counts, "teacher_review_required": True,
                "omitted_nodes": len(raw.nodes) - len(grounded.nodes),
                "omitted_relations": len(raw.relationships) - len(grounded.relationships),
            }
            report.append({"chunk_id": str(chunk.id), **run.metrics_json})
        except Exception as error:
            run.status = ExtractionRunStatus.FAILED
            code = type(error).__name__
            if str(error) in {
                "candidate quote is not an exact source span",
                "candidate relationship is outside the ontology",
            }:
                code = str(error)
            run.error_summary = code
            report.append({"chunk_id": str(chunk.id), "failure": code})
        run.completed_at = datetime.now(UTC)
        await session.commit()
    return report
