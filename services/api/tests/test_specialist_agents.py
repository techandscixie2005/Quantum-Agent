from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from quantum_agent.db_models import TeachingMode
from quantum_agent.knowledge.evidence_packets import (
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidencePacket,
    GraphContextEdge,
    GraphContextNode,
    LocatorType,
    RetrievalChannel,
    RetrievalContribution,
    RetrievalCoverage,
)
from quantum_agent.knowledge.retrieval import RetrievalScope
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.science import ComplexValue, NumericalNormalizationRequest
from quantum_agent.teaching.agents import (
    DiagnosisAgent,
    DiagnosisInput,
    EvidenceAgent,
    EvidenceBundle,
    EvidenceConflict,
)
from quantum_agent.teaching.models import (
    DiagnosisOutput,
    DiagnosisProgressState,
    DiagnosisStatus,
    StudentSnapshot,
    TeachingTurnInput,
)

COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")
EDITION_ID = UUID("00000000-0000-0000-0000-000000000020")


class StaticRetriever:
    def __init__(self, packet: EvidencePacket) -> None:
        self.packet = packet
        self.calls: list[tuple[RetrievalScope, str]] = []

    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        self.calls.append((scope, query))
        return self.packet.model_copy(update={"query": query})


def _evidence_item(index: int, locator: EvidenceLocator) -> EvidenceItem:
    snippet = f"课程证据片段 {index}"
    source = f"第 {index} 个来源保留完整定位。{snippet}。"
    return EvidenceItem(
        evidence_id=UUID(f"00000000-0000-0000-0000-{400 + index:012d}"),
        chunk_id=UUID(f"00000000-0000-0000-0000-{100 + index:012d}"),
        document_id=UUID(f"00000000-0000-0000-0000-{200 + index:012d}"),
        document_version_id=UUID(f"00000000-0000-0000-0000-{300 + index:012d}"),
        document_title=f"课程来源 {index}",
        document_version=index,
        source_file_name=f"source-{index}.dat",
        source_file_sha256=f"{index:x}" * 64,
        source_chunk_sha256=hashlib.sha256(source.encode()).hexdigest(),
        evidence_sha256=hashlib.sha256(snippet.encode()).hexdigest(),
        curriculum_edition_id=EDITION_ID,
        chapter="第二章",
        section_path=["第二章", f"第 {index} 节"],
        locator=locator,
        source_chunk=source,
        evidence_snippet=snippet,
        kind=EvidenceKind.COURSE_MATERIAL,
        authority_priority=90,
        contributions=[
            RetrievalContribution(
                channel=RetrievalChannel.FULL_TEXT,
                rank=index,
                raw_score=1.0 / index,
                fused_score=1.0 / (60 + index),
            )
        ],
    )


def _graph_context() -> tuple[list[GraphContextNode], list[GraphContextEdge]]:
    prerequisite = GraphContextNode(
        id=UUID("00000000-0000-0000-0000-000000000501"),
        node_type="Concept",
        name="线性代数",
    )
    target = GraphContextNode(
        id=UUID("00000000-0000-0000-0000-000000000502"),
        node_type="Concept",
        name="波函数统计解释",
    )
    misconception = GraphContextNode(
        id=UUID("00000000-0000-0000-0000-000000000503"),
        node_type="Misconception",
        name="波函数本身就是概率",
    )
    formula = GraphContextNode(
        id=UUID("00000000-0000-0000-0000-000000000504"),
        node_type="Formula",
        name=r"\rho=|\psi|^2",
    )
    prerequisite_edge = GraphContextEdge(
        id=UUID("00000000-0000-0000-0000-000000000601"),
        source_id=prerequisite.id,
        target_id=target.id,
        relation_type="PREREQUISITE_OF",
    )
    misconception_edge = GraphContextEdge(
        id=UUID("00000000-0000-0000-0000-000000000602"),
        source_id=target.id,
        target_id=misconception.id,
        relation_type="HAS_MISCONCEPTION",
    )
    return [target, prerequisite, misconception, formula], [
        prerequisite_edge,
        misconception_edge,
    ]


def _packet(*, all_locator_types: bool = False) -> EvidencePacket:
    locators = [EvidenceLocator(locator_type=LocatorType.PDF_PAGE, physical_page=12)]
    if all_locator_types:
        locators.extend(
            [
                EvidenceLocator(
                    locator_type=LocatorType.SLIDE,
                    slide_number=3,
                    physical_page=3,
                ),
                EvidenceLocator(
                    locator_type=LocatorType.DOCX_PARAGRAPH,
                    paragraph_start=7,
                    paragraph_end=9,
                ),
                EvidenceLocator(
                    locator_type=LocatorType.XLSX_ROW,
                    sheet_name="公式表",
                    row_start=11,
                    row_end=12,
                ),
                EvidenceLocator(
                    locator_type=LocatorType.TEXT_LINES,
                    line_start=20,
                    line_end=24,
                ),
            ]
        )
    nodes, edges = _graph_context()
    return EvidencePacket(
        course_id=COURSE_ID,
        curriculum_edition_id=EDITION_ID,
        query="波函数",
        coverage=RetrievalCoverage.PARTIAL,
        evidence=[
            _evidence_item(index, locator)
            for index, locator in enumerate(locators, start=1)
        ],
        graph_nodes=nodes,
        graph_edges=edges,
        degraded_channels=[RetrievalChannel.SEMANTIC],
        warnings=["pgvector_semantic_unavailable:probe_failed"],
    )


async def _bundle(*, all_locator_types: bool = False) -> EvidenceBundle:
    packet = _packet(all_locator_types=all_locator_types)
    retriever = StaticRetriever(packet)
    return await EvidenceAgent(retriever).gather(
        scope=RetrievalScope(course_id=COURSE_ID, curriculum_edition_id=EDITION_ID),
        query="  波函数的统计解释  ",
        concept_hints=[" 概率密度 "],
    )


async def test_evidence_bundle_preserves_typed_provenance_and_graph_direction() -> None:
    packet = _packet(all_locator_types=True)
    retriever = StaticRetriever(packet)
    bundle = await EvidenceAgent(retriever).gather(
        scope=RetrievalScope(course_id=COURSE_ID, curriculum_edition_id=EDITION_ID),
        query="  波函数的统计解释  ",
        concept_hints=[" 概率密度 "],
    )

    assert retriever.calls[0][1] == "波函数的统计解释 概率密度"
    assert bundle.query == "波函数的统计解释"
    assert bundle.source_chunks == packet.evidence
    assert [citation.locator for citation in bundle.citations] == [
        item.locator for item in packet.evidence
    ]
    assert [citation.document_version for citation in bundle.citations] == [1, 2, 3, 4, 5]
    assert bundle.citations[2].locator.paragraph_end == 9
    assert bundle.citations[3].locator.sheet_name == "公式表"
    assert bundle.citations[4].locator.line_end == 24

    path = bundle.prerequisite_paths[0]
    assert path.prerequisite.name == "线性代数"
    assert path.target.name == "波函数统计解释"
    assert bundle.primary_concept == "波函数统计解释"
    assert bundle.misconception_links[0].source.name == "波函数统计解释"
    assert bundle.misconception_links[0].misconception.name == "波函数本身就是概率"
    assert [formula.name for formula in bundle.formulas] == [r"\rho=|\psi|^2"]


async def test_retrieval_warning_is_not_fabricated_as_evidence_conflict() -> None:
    bundle = await _bundle()

    assert bundle.warnings == ["pgvector_semantic_unavailable:probe_failed"]
    assert bundle.conflicts == []
    assert "warnings describe retrieval limitations" in bundle.coverage_rationale

    invalid = bundle.model_dump()
    invalid["conflicts"] = [
        EvidenceConflict(
            evidence_ids=[bundle.citations[0].evidence_id, uuid4()],
            summary="Unallowlisted evidence must not enter a conflict record.",
        ).model_dump()
    ]
    with pytest.raises(ValidationError, match="bundled citations"):
        EvidenceBundle.model_validate(invalid)


async def test_diagnosis_skips_model_without_student_attempt() -> None:
    gateway: FakeModelGateway[Any] = FakeModelGateway()
    diagnosis_input = DiagnosisInput(
        request=TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我应该从哪里开始?",
        ),
        evidence_bundle=await _bundle(),
    )

    diagnosis, degraded = await DiagnosisAgent(gateway).diagnose(
        diagnosis_input=diagnosis_input
    )

    assert gateway.calls == []
    assert degraded is False
    assert diagnosis.status is DiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert diagnosis.progress_state is DiagnosisProgressState.NO_ATTEMPT
    assert diagnosis.first_error is None
    assert diagnosis.confidence == 0.0
    assert diagnosis.reason.strip()


async def test_invalid_specialist_output_uses_validated_directed_fallback() -> None:
    gateway: FakeModelGateway[Any] = FakeModelGateway(
        {
            "diagnose_student_progress_structured": {
                "status": "observed",
                "summary": "invalid",
                "observation_basis": ["student_attempt"],
                "confidence": 1.5,
                "reason": " ",
            }
        }
    )
    diagnosis_input = DiagnosisInput(
        request=TeachingTurnInput(
            mode=TeachingMode.REVIEW_DERIVATIONS,
            message="检查我的推导。",
            student_attempt=r"\rho=\psi",
        ),
        evidence_bundle=await _bundle(),
        student_snapshot=StudentSnapshot(recent_no_progress_count=1),
    )

    diagnosis, degraded = await DiagnosisAgent(gateway).diagnose(
        diagnosis_input=diagnosis_input
    )

    assert len(gateway.calls) == 1
    assert degraded is True
    assert diagnosis.confidence == 0.0
    assert diagnosis.reason.strip()
    assert diagnosis.target_concepts[0] == "波函数统计解释"
    assert diagnosis.missing_prerequisites == ["线性代数"]
    assert diagnosis.progress_state is DiagnosisProgressState.STRUGGLING


async def test_specialist_confidence_reason_and_verification_request_are_preserved() -> None:
    gateway: FakeModelGateway[Any] = FakeModelGateway(
        {
            "diagnose_student_progress_structured": {
                "status": "model_inference",
                "summary": "学生把振幅与概率密度混为一谈。",
                "likely_misconception": "波函数本身就是概率",
                "observation_basis": ["student_attempt", "course_evidence"],
                "misconception_candidates": [
                    {"statement": "波函数本身就是概率", "confidence": 0.82}
                ],
                "progress_state": "confident",
                "confidence": 0.82,
                "verification_needed": True,
                "reason": (
                    "The attempt equates psi with rho while the cited formula uses modulus "
                    "squared."
                ),
            }
        }
    )
    diagnosis_input = DiagnosisInput(
        request=TeachingTurnInput(
            mode=TeachingMode.REVIEW_DERIVATIONS,
            message="检查我的推导。",
            student_attempt=r"\rho=\psi",
        ),
        evidence_bundle=await _bundle(),
        student_snapshot=StudentSnapshot(prior_attempt_count=2),
    )

    diagnosis, degraded = await DiagnosisAgent(gateway).diagnose(
        diagnosis_input=diagnosis_input
    )

    assert degraded is False
    assert diagnosis.confidence == 0.82
    assert diagnosis.reason.startswith("The attempt equates")
    assert diagnosis.verification_needed is True
    assert diagnosis.progress_state is DiagnosisProgressState.PROGRESSING
    assert diagnosis.missing_prerequisites == ["线性代数"]
    assert diagnosis.first_error is not None


async def test_typed_scientific_request_cannot_be_downgraded_by_model() -> None:
    gateway: FakeModelGateway[Any] = FakeModelGateway(
        {
            "diagnose_student_progress_structured": {
                "status": "observed",
                "summary": "已观察归一化计算。",
                "observation_basis": ["student_attempt"],
                "confidence": 0.4,
                "verification_needed": False,
                "reason": "A numerical normalization claim is present and needs an external check.",
            }
        }
    )
    diagnosis_input = DiagnosisInput(
        request=TeachingTurnInput(
            mode=TeachingMode.REVIEW_DERIVATIONS,
            message="检查归一化。",
            student_attempt="我得到范数为 1。",
            scientific_request=NumericalNormalizationRequest(
                state=[ComplexValue(real=1.0), ComplexValue(real=0.0)]
            ),
        ),
        evidence_bundle=await _bundle(),
    )

    diagnosis, degraded = await DiagnosisAgent(gateway).diagnose(
        diagnosis_input=diagnosis_input
    )

    assert degraded is False
    assert diagnosis.verification_needed is True
    assert len(gateway.calls) == 1


def test_diagnosis_output_retains_baseline_compatibility_but_rejects_blank_reason() -> None:
    baseline = DiagnosisOutput(
        status=DiagnosisStatus.OBSERVED,
        summary="B0/B1 observed-only diagnosis.",
        observation_basis=["student_attempt"],
    )
    assert baseline.confidence == 0.0
    assert baseline.reason.strip()

    with pytest.raises(ValidationError, match="must not be blank"):
        DiagnosisOutput(
            status=DiagnosisStatus.OBSERVED,
            summary="Invalid specialist diagnosis.",
            observation_basis=["student_attempt"],
            confidence=0.5,
            reason="   ",
        )
