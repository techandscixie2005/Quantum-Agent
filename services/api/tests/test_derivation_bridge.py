from uuid import uuid4

import pytest

from quantum_agent.db_models import AnswerReleaseLevel
from quantum_agent.teaching.derivation import (
    BridgeSource,
    DerivationBridge,
    DerivationStep,
    constrain_bridge,
)
from tests.test_teaching_state_machine import _packet


def test_bridge_checks_source_spans_and_enforces_release_budget() -> None:
    packet = _packet(uuid4(), uuid4())
    ref = BridgeSource(
        evidence_id=packet.evidence[0].evidence_id,
        quote=packet.evidence[0].evidence_snippet,
    )
    bridge = DerivationBridge(
        source_step="A", target_step="D",
        missing_steps=[
            DerivationStep(formula="B", justification="definition", source_refs=[ref]),
            DerivationStep(formula="C", justification="substitution", source_refs=[ref]),
        ], source_refs=[ref], partial=False,
    )
    assert constrain_bridge(bridge, packet, AnswerReleaseLevel.QUESTION_ONLY) is None
    assert constrain_bridge(bridge, packet, AnswerReleaseLevel.HINT) is None
    partial = constrain_bridge(bridge, packet, AnswerReleaseLevel.SCAFFOLD)
    assert partial is not None and partial.partial and len(partial.missing_steps) == 1
    full = constrain_bridge(bridge, packet, AnswerReleaseLevel.FULL_EXPLANATION)
    assert full is not None and not full.partial and len(full.missing_steps) == 2
    assert full.support_basis == "unverified_model_inference"
    bridge.source_refs = [BridgeSource(evidence_id=uuid4(), quote=ref.quote)]
    with pytest.raises(ValueError, match="source spans"):
        constrain_bridge(bridge, packet, AnswerReleaseLevel.SCAFFOLD)
    bridge.source_refs = [BridgeSource(evidence_id=ref.evidence_id, quote="invented")]
    with pytest.raises(ValueError, match="source spans"):
        constrain_bridge(bridge, packet, AnswerReleaseLevel.FULL_SOLUTION)


@pytest.mark.asyncio
async def test_valid_bridge_does_not_publish_a_mislabeled_companion_claim() -> None:
    from quantum_agent.db_models import TeachingMode
    from quantum_agent.llm.gateway import FakeModelGateway
    from quantum_agent.teaching.models import DiagnosisOutput, DiagnosisStatus, TeachingTurnInput
    from quantum_agent.teaching.state_machine import draft_response

    packet = _packet(uuid4(), uuid4())
    ref = {"evidence_id": str(packet.evidence[0].evidence_id),
           "quote": packet.evidence[0].evidence_snippet}
    gateway = FakeModelGateway({"compose_grounded_teaching_response": {
        "orientation": "One step", "next_question": "What follows?",
        "claims": [{"text": "Not a literal source span", "support_basis": "course_material",
                    "evidence_ids": [ref["evidence_id"]]}],
        "derivation_bridge": {"source_step": "A", "target_step": "D", "source_refs": [ref],
                              "missing_steps": [{"formula": "B", "justification": "definition",
                                                 "source_refs": [ref]}]},
    }})
    response, validation, degraded = await draft_response(
        request=TeachingTurnInput(mode=TeachingMode.REVIEW_DERIVATIONS, message="A to D"),
        packet=packet, diagnosis=DiagnosisOutput(
            status=DiagnosisStatus.MODEL_INFERENCE, summary="A gap",
        ), release_level=AnswerReleaseLevel.SCAFFOLD, scientific_results=[],
        model_gateway=gateway,
    )
    assert response.derivation_bridge is not None and not degraded
    assert response.claims == []
    assert validation.passed
    assert "unsupported_companion_claims_omitted" in validation.warnings


@pytest.mark.asyncio
async def test_catalog_bridge_uses_real_quotes_and_student_endpoints() -> None:
    from quantum_agent.llm.gateway import FakeModelGateway
    from quantum_agent.teaching.derivation import explicit_endpoints, selected_bridge

    packet = _packet(uuid4(), uuid4())
    message = "Explain one step\n原式\uff1ay''=b^2 y\n目标式\uff1ay=C exp(bx)+D exp(-bx)"
    endpoints = explicit_endpoints(message)
    assert endpoints == ("y''=b^2 y", "y=C exp(bx)+D exp(-bx)")
    gateway = FakeModelGateway({"compose_grounded_teaching_response": {
        "steps": [
            {"formula": "r^2=b^2", "justification": "Exponential trial", "sources": [0]},
            {"formula": "r=+-b", "justification": "Roots", "sources": [0]},
        ], "assumptions": ["constant b"],
    }})
    bridge, _ = await selected_bridge(message=message, endpoints=endpoints, packet=packet,
                                     release=AnswerReleaseLevel.SCAFFOLD, gateway=gateway)
    assert bridge is not None and bridge.partial
    assert len(bridge.missing_steps) == 1
    assert bridge.source_step == endpoints[0]
    assert bridge.target_step == endpoints[1]
    assert bridge.source_refs[0].quote == packet.evidence[0].evidence_snippet
    assert bridge.source_refs[0].evidence_id == packet.evidence[0].evidence_id
    assert bridge.support_basis == "unverified_model_inference"


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [-1, 8])
async def test_catalog_bridge_rejects_unknown_sources(index: int) -> None:
    from quantum_agent.llm.gateway import FakeModelGateway
    from quantum_agent.teaching.derivation import selected_bridge

    gateway = FakeModelGateway({"compose_grounded_teaching_response": {
        "steps": [{"formula": "B", "justification": "step", "sources": [index]}],
    }})
    with pytest.raises(ValueError, match="unknown source"):
        await selected_bridge(message="any", endpoints=("A", "C"),
                              packet=_packet(uuid4(), uuid4()),
                              release=AnswerReleaseLevel.SCAFFOLD, gateway=gateway)


@pytest.mark.asyncio
async def test_catalog_bridge_withholds_at_hint_and_allows_uncertainty() -> None:
    from quantum_agent.llm.gateway import FakeModelGateway
    from quantum_agent.teaching.derivation import selected_bridge

    gateway = FakeModelGateway({"compose_grounded_teaching_response": {
        "steps": [], "clarification": "Please supply the missing definition",
    }})
    packet = _packet(uuid4(), uuid4())
    bridge, _ = await selected_bridge(message="any", endpoints=("A", "C"), packet=packet,
                                     release=AnswerReleaseLevel.HINT, gateway=gateway)
    assert bridge is None and not gateway.calls
    bridge, question = await selected_bridge(message="any", endpoints=("A", "C"), packet=packet,
                                            release=AnswerReleaseLevel.SCAFFOLD, gateway=gateway)
    assert bridge is None and question == "Please supply the missing definition"
