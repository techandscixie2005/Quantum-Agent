import pytest

from quantum_agent.knowledge.extraction import RawChunkExtraction
from quantum_agent.knowledge.ontology import NodeType, RelationshipType, is_allowed_triple
from quantum_agent.knowledge.pedagogical_import import grounded_subset, validate_extraction


def test_teaching_content_requires_verbatim_sources_and_valid_relations() -> None:
    raw = RawChunkExtraction.model_validate({
        "nodes": [
            {"local_id": "step", "node_type": "DerivationStep", "canonical_key": "step",
             "label": "substitute", "evidence_quote": "insert completeness", "confidence": 0.9},
            {"local_id": "condition", "node_type": "ValidityCondition", "canonical_key": "domain",
             "label": "complete basis", "evidence_quote": "complete basis", "confidence": 0.9},
        ],
        "relationships": [{"source_local_id": "step", "target_local_id": "condition",
                           "relationship_type": "VALID_UNDER",
                           "evidence_quote": "complete basis", "confidence": 0.9}],
    })
    validate_extraction(raw, "In a complete basis, insert completeness.")
    with pytest.raises(ValueError, match="exact source span"):
        validate_extraction(raw, "An unrelated course chapter.")
    raw.relationships[0].relationship_type = RelationshipType.COMMUTES_WITH
    with pytest.raises(ValueError, match="ontology"):
        validate_extraction(raw, "In a complete basis, insert completeness.")
    assert is_allowed_triple(
        NodeType.DERIVATION_STEP, RelationshipType.PART_OF, NodeType.DERIVATION,
    )
    assert is_allowed_triple(
        NodeType.FORMULA, RelationshipType.VALID_UNDER, NodeType.ASSUMPTION,
    )


def test_quote_alignment_preserves_characters_and_omits_invented_algebra() -> None:
    raw = RawChunkExtraction.model_validate({"nodes": [
        {"local_id": "supported", "node_type": "Assumption", "canonical_key": "basis",
         "label": "complete basis", "evidence_quote": "complete basis", "confidence": 0.8},
        {"local_id": "invented", "node_type": "DerivationStep", "canonical_key": "wrong",
         "label": "x=2", "evidence_quote": "x=2", "confidence": 0.9},
    ]})
    content = "In a complete\n basis, x=1."
    grounded = grounded_subset(raw, content)
    assert [node.local_id for node in grounded.nodes] == ["supported"]
    assert grounded.nodes[0].evidence_quote == "complete\n basis"
    validate_extraction(grounded, content)
