from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantum_agent.knowledge.ontology import (
    ALLOWED_TRIPLE_PATTERNS,
    EvidenceReference,
    ExtractionReviewStatus,
    GroundingStatus,
    NodeCandidate,
    NodeType,
    RelationshipCandidate,
    RelationshipType,
    evidence_quote_is_substring,
    is_allowed_triple,
    normalize_evidence_text,
    simple_kg_pipeline_schema,
)


def evidence(
    *, quote: str = "厄米算符的本征值是实数。", chunk: str | None = None
) -> EvidenceReference:
    return EvidenceReference(
        source_document_id="doc-version-1",
        source_chunk_id="chunk-7",
        source_file="第1-2章.pdf",
        chapter="第二章",
        page_number=12,
        quote=quote,
        source_chunk_text=chunk if chunk is not None else "定义:厄米算符的本征值是实数。",
    )


def test_ontology_contains_course_semantic_types_and_concrete_patterns() -> None:
    assert {
        NodeType.COURSE,
        NodeType.CONCEPT,
        NodeType.OPERATOR,
        NodeType.QUANTUM_STATE,
        NodeType.FORMULA,
        NodeType.DERIVATION,
        NodeType.MISCONCEPTION,
        NodeType.SOURCE_CHUNK,
        NodeType.EVIDENCE,
    } <= set(NodeType)
    assert {
        RelationshipType.PREREQUISITE_OF,
        RelationshipType.ACTS_ON,
        RelationshipType.COMMUTES_WITH,
        RelationshipType.HAS_EIGENSTATE,
        RelationshipType.REMEDIATED_BY,
        RelationshipType.SUPPORTED_BY,
    } <= set(RelationshipType)
    assert (
        NodeType.OPERATOR,
        RelationshipType.ACTS_ON,
        NodeType.QUANTUM_STATE,
    ) in ALLOWED_TRIPLE_PATTERNS
    assert is_allowed_triple("Concept", "PREREQUISITE_OF", "Concept")
    assert not is_allowed_triple("Exercise", "ACTS_ON", "Course")
    assert not is_allowed_triple("InjectedLabel", "USES", "Concept")


def test_evidence_matching_normalizes_unicode_case_and_whitespace() -> None:
    source = "态矢量  Ψ\n满足归一化条件"
    quote = "态矢量 ψ 满足归一化条件"
    assert normalize_evidence_text("\uff21  B") == "a b"
    assert evidence_quote_is_substring(quote, source)


def test_grounded_candidate_is_pending_for_teacher_review_not_approved() -> None:
    candidate = NodeCandidate(
        candidate_id="node-hermitian",
        course_id="quantum-physics",
        curriculum_edition_id="2026",
        node_type=NodeType.CONCEPT,
        canonical_key="hermitian-operator",
        label="厄米算符",
        confidence=0.94,
        provenance=(evidence(),),
    )

    assert candidate.provenance[0].quote_verified is True
    assert candidate.grounding is GroundingStatus.GROUNDED
    assert candidate.status is ExtractionReviewStatus.PENDING
    assert candidate.review_reasons == ()
    assert not hasattr(ExtractionReviewStatus, "APPROVED")


def test_unsupported_quote_is_retained_but_forced_to_review_required() -> None:
    reference = evidence(quote="课程材料并未出现的断言")
    candidate = NodeCandidate(
        candidate_id="unsupported",
        course_id="quantum-physics",
        curriculum_edition_id="2026",
        node_type=NodeType.PRINCIPLE,
        canonical_key="unsupported-claim",
        label="Unsupported claim",
        confidence=0.99,
        provenance=(reference,),
        status=ExtractionReviewStatus.PENDING,
    )

    assert reference.quote_verified is False
    assert reference.verification_note == "evidence_quote_not_normalized_substring"
    assert candidate.grounding is GroundingStatus.UNSUPPORTED
    assert candidate.status is ExtractionReviewStatus.REVIEW_REQUIRED
    assert any("chunk-7" in reason for reason in candidate.review_reasons)


def test_quote_verification_fields_cannot_be_spoofed_by_model_output() -> None:
    reference = EvidenceReference(
        source_document_id="doc",
        source_chunk_id="chunk",
        source_file="notes.pdf",
        quote="fabricated quote",
        source_chunk_text="authoritative text",
        quote_verified=True,
        verification_note=None,
    )
    assert reference.quote_verified is False
    assert reference.verification_note == "evidence_quote_not_normalized_substring"


def test_missing_evidence_or_low_confidence_requires_review() -> None:
    candidate = NodeCandidate(
        course_id="quantum-physics",
        curriculum_edition_id="2026",
        node_type=NodeType.FORMULA,
        canonical_key="formula:no-source",
        label="E = h\u03bd",
        confidence=0.60,
    )
    assert candidate.grounding is GroundingStatus.UNSUPPORTED
    assert candidate.status is ExtractionReviewStatus.REVIEW_REQUIRED
    assert set(candidate.review_reasons) == {
        "confidence_below_grounding_threshold",
        "no_evidence_provenance",
    }


def test_invalid_triple_is_preserved_for_review_not_silently_accepted() -> None:
    candidate = RelationshipCandidate(
        candidate_id="bad-edge",
        course_id="quantum-physics",
        curriculum_edition_id="2026",
        relationship_type=RelationshipType.ACTS_ON,
        source_candidate_id="exercise-1",
        target_candidate_id="course-1",
        source_node_type=NodeType.EXERCISE,
        target_node_type=NodeType.COURSE,
        confidence=0.98,
        provenance=(evidence(),),
    )
    assert candidate.grounding is GroundingStatus.GROUNDED
    assert candidate.status is ExtractionReviewStatus.REVIEW_REQUIRED
    assert "ontology_pattern_not_allowed" in candidate.review_reasons


def test_extraction_status_cannot_be_set_to_approved() -> None:
    with pytest.raises(ValidationError):
        NodeCandidate(
            course_id="quantum-physics",
            curriculum_edition_id="2026",
            node_type=NodeType.CONCEPT,
            canonical_key="x",
            label="x",
            confidence=1,
            provenance=(evidence(),),
            status="approved",
        )


def test_simple_kg_pipeline_adapter_is_closed_world_and_review_gated() -> None:
    schema = simple_kg_pipeline_schema()
    assert schema["additional_node_types"] is False
    assert {item["label"] for item in schema["node_types"]} == {
        node_type.value for node_type in NodeType
    }
    assert {item["label"] for item in schema["relationship_types"]} == {
        relationship_type.value for relationship_type in RelationshipType
    }
    assert set(schema["patterns"]) == {
        (source.value, relationship.value, target.value)
        for source, relationship, target in ALLOWED_TRIPLE_PATTERNS
    }
