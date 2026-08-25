from __future__ import annotations

from typing import Any

from quantum_agent.knowledge.extraction import (
    ExtractionContext,
    QuantumKnowledgeExtractor,
)
from quantum_agent.knowledge.ingestion import (
    IngestionStatus,
    LocatorType,
    SourceChunk,
    SourceLocator,
    sha256_text,
)
from quantum_agent.knowledge.ontology import (
    ExtractionReviewStatus,
    GroundingStatus,
    NodeType,
)
from quantum_agent.llm.gateway import FakeModelGateway


def _chunk() -> SourceChunk:
    text = "若力学量算符不显含时间且它与体系的哈密顿算符对易，则该力学量的平均值不随时间变化。"  # noqa: RUF001 - source text
    return SourceChunk(
        id="chunk-1",
        document_id="doc-1",
        document_version_id="version-1",
        source_unit_id="unit-1",
        ordinal=0,
        exact_text=text,
        checksum=sha256_text(text),
        section_path=("§3—1 中心力场中的粒子", "守恒量"),
        locator=SourceLocator(
            locator_type=LocatorType.PAGE,
            start=3,
            end=3,
            physical_page=3,
        ),
        content_char_start=0,
        content_char_end=len(text),
        evidence_snippet=text,
        evidence_char_start=0,
        evidence_char_end=len(text),
        status=IngestionStatus.READY,
    )


def _context() -> ExtractionContext:
    return ExtractionContext(
        course_id="course-1",
        curriculum_edition_id="deck-2022",
        source_document_id="doc-1",
        source_file="第三章 单电子原子 .pdf",
        document_sha256="a" * 64,
        document_version_id="version-1",
        chapter="第三章 单电子原子",
    )


async def test_extractor_hydrates_ids_and_forces_teacher_review() -> None:
    gateway: FakeModelGateway[Any] = FakeModelGateway(
        {
            "quantum_course_knowledge_extraction": {
                "nodes": [
                    {
                        "local_id": "conservation",
                        "node_type": "Principle",
                        "canonical_key": "conserved-observable-criterion",
                        "label": "守恒量判据",
                        "description": "算符不显含时间并与哈密顿算符对易。",
                        "evidence_quote": "与体系的哈密顿算符对易",
                        "confidence": 0.98,
                    }
                ],
                "relationships": [],
            }
        }
    )
    batch = await QuantumKnowledgeExtractor(gateway).extract_chunk(
        context=_context(), chunk=_chunk()
    )
    node = batch.nodes[0]
    assert node.node_type is NodeType.PRINCIPLE
    assert node.grounding is GroundingStatus.GROUNDED
    assert node.status is ExtractionReviewStatus.REVIEW_REQUIRED
    assert "teacher_approval_required" in node.review_reasons
    assert node.provenance[0].page_number == 3


async def test_unsupported_quote_is_never_promoted() -> None:
    gateway: FakeModelGateway[Any] = FakeModelGateway(
        {
            "quantum_course_knowledge_extraction": {
                "nodes": [
                    {
                        "local_id": "invented",
                        "node_type": "Concept",
                        "canonical_key": "invented",
                        "label": "未出现的概念",
                        "evidence_quote": "这句话不在原文里",
                        "confidence": 0.99,
                    }
                ]
            }
        }
    )
    batch = await QuantumKnowledgeExtractor(gateway).extract_chunk(
        context=_context(), chunk=_chunk()
    )
    node = batch.nodes[0]
    assert node.grounding is GroundingStatus.UNSUPPORTED
    assert node.status is ExtractionReviewStatus.REVIEW_REQUIRED
    assert any(
        "evidence_quote_not_normalized_substring" in reason for reason in node.review_reasons
    )
