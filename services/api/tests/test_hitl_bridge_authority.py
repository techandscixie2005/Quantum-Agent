"""Staff edits cannot bypass derivation release/citation authority."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.db_models import AnswerReleaseLevel, TeachingAction, TeachingMode
from quantum_agent.teaching.derivation import BridgeSource, DerivationBridge, DerivationStep
from quantum_agent.teaching.hitl import (
    HitlAction,
    HitlInterruptResponse,
    HitlResolutionValidationError,
    HitlResumeRequest,
    validate_human_response,
)
from quantum_agent.teaching.models import (
    ReleaseDecision,
    ResponseStatus,
    TeachingResponse,
    TeachingTurnInput,
)
from quantum_agent.tutor.graph import TutorGraph
from tests import test_tutor_graph
from tests.test_tutor_graph import StaticRetriever, _packet, _seed, _seed_staff

teaching_database = test_tutor_graph.teaching_database


def _response(bridge: DerivationBridge | None = None) -> TeachingResponse:
    return TeachingResponse(
        status=ResponseStatus.MIXED if bridge else ResponseStatus.MODEL_DEGRADED,
        orientation="Inspected response", next_question="Which step can you justify?",
        claims=[], derivation_bridge=bridge,
    )


def _release(level: AnswerReleaseLevel) -> ReleaseDecision:
    return ReleaseDecision(
        action=TeachingAction.CHECK_DERIVATION_STEP, release_level=level,
        attempts_observed=1, reason_code="scripted_test",
    )


@pytest.mark.parametrize("level", [AnswerReleaseLevel.QUESTION_ONLY, AnswerReleaseLevel.HINT])
def test_empty_claims_cannot_smuggle_forged_bridge_past_low_release(
    level: AnswerReleaseLevel,
) -> None:
    packet = _packet(uuid4(), uuid4())
    ref = BridgeSource(evidence_id=uuid4(), quote="forged published-source quote")
    bridge = DerivationBridge(
        source_step="A", target_step="Z", source_refs=[ref],
        missing_steps=[DerivationStep(formula="Z=42", justification="forged", source_refs=[ref])],
    )
    report = validate_human_response(
        response=_response(bridge), proposed_response=_response(), packet=packet,
        scientific_results=[], release=_release(level),
    )
    assert not report.passed and not report.citation_ids_valid
    assert "human_response_changes_inspected_derivation_bridge" in report.warnings
    assert "human_bridge_exceeds_release_level" in report.warnings


def _bridge(ref: BridgeSource) -> DerivationBridge:
    return DerivationBridge(
        source_step="A", target_step="C", source_refs=[ref],
        missing_steps=[DerivationStep(formula="B", justification="one step", source_refs=[ref])],
    )


@pytest.mark.parametrize("change", ["add", "remove", "formula", "target"])
def test_staff_may_edit_prose_but_cannot_change_inspected_bridge(change: str) -> None:
    packet = _packet(uuid4(), uuid4())
    bridge = _bridge(BridgeSource(evidence_id=packet.evidence[0].evidence_id,
                                 quote=packet.evidence[0].evidence_snippet))
    original = _response(None if change == "add" else bridge)
    edited_bridge = bridge.model_copy(deep=True)
    if change == "formula":
        edited_bridge.missing_steps[0].formula = "uninspected complete answer"
    elif change == "target":
        edited_bridge.target_step = "uninspected target"
    edited = _response(None if change == "remove" else edited_bridge)
    report = validate_human_response(
        response=edited, proposed_response=original, packet=packet, scientific_results=[],
        release=_release(AnswerReleaseLevel.FULL_EXPLANATION),
    )
    assert not report.passed
    assert "human_response_changes_inspected_derivation_bridge" in report.warnings


@pytest.mark.parametrize("location", ["bridge", "step"])
@pytest.mark.parametrize("forgery", ["evidence_id", "quote"])
def test_unchanged_inspected_bridge_still_revalidates_all_source_references(
    location: str, forgery: str,
) -> None:
    packet = _packet(uuid4(), uuid4())
    ref = BridgeSource(evidence_id=packet.evidence[0].evidence_id,
                       quote=packet.evidence[0].evidence_snippet)
    bridge = _bridge(ref.model_copy(deep=True))
    broken = ref.model_copy(update={forgery: uuid4() if forgery == "evidence_id" else "invented"})
    if location == "bridge":
        bridge.source_refs = [broken]
    else:
        bridge.missing_steps[0].source_refs = [broken]
    response = _response(bridge)
    report = validate_human_response(
        response=response, proposed_response=response.model_copy(deep=True), packet=packet,
        scientific_results=[], release=_release(AnswerReleaseLevel.FULL_EXPLANATION),
    )
    assert not report.passed
    assert not (report.citation_ids_valid if forgery == "evidence_id"
                else report.literal_course_claims_valid)


@pytest.mark.parametrize("budget_violation", ["complete", "two_steps", "grounded_status"])
def test_unchanged_bridge_cannot_exceed_scaffold_or_inference_envelope(
    budget_violation: str,
) -> None:
    packet = _packet(uuid4(), uuid4())
    bridge = _bridge(BridgeSource(evidence_id=packet.evidence[0].evidence_id,
                                 quote=packet.evidence[0].evidence_snippet))
    if budget_violation == "complete":
        bridge.partial = False
    elif budget_violation == "two_steps":
        bridge.missing_steps.append(bridge.missing_steps[0].model_copy(deep=True))
    response = _response(bridge)
    if budget_violation == "grounded_status":
        response.status = ResponseStatus.GROUNDED
    report = validate_human_response(
        response=response, proposed_response=response.model_copy(deep=True), packet=packet,
        scientific_results=[], release=_release(AnswerReleaseLevel.SCAFFOLD),
    )
    assert not report.passed


def test_staff_can_edit_orientation_while_preserving_valid_inspected_partial_bridge() -> None:
    packet = _packet(uuid4(), uuid4())
    response = _response(_bridge(BridgeSource(evidence_id=packet.evidence[0].evidence_id,
                                             quote=packet.evidence[0].evidence_snippet)))
    edited = response.model_copy(update={"orientation": "An edited bounded introduction"})
    report = validate_human_response(
        response=edited, proposed_response=response, packet=packet,
        scientific_results=[], release=_release(AnswerReleaseLevel.SCAFFOLD),
    )
    assert report.passed


async def test_direct_authenticated_staff_resume_rejects_uninspected_bridge_and_keeps_pause(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seed = await _seed(session)
        staff = await _seed_staff(session, seed)
        await session.commit()
        packet = _packet(seed.actor.course_id, seed.edition_id)
        graph = TutorGraph(evidence_retriever=StaticRetriever(packet), model_gateway=None,
                           checkpointer=InMemorySaver(), enable_hitl=True)
        interrupted = await graph.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS, message="@TA inspect the next explanation",
                student_attempt="I relate the density to the squared amplitude.",
            ),
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        assert interrupted.artifacts.proposed_response.derivation_bridge is None
        ref = BridgeSource(evidence_id=packet.evidence[0].evidence_id,
                           quote="forged quote, even though the evidence ID exists")
        edited = interrupted.artifacts.proposed_response.model_copy(update={
            "claims": [], "derivation_bridge": _bridge(ref),
        })
        with pytest.raises(HitlResolutionValidationError, match="derivation_bridge"):
            await graph.resume(
                session=session, actor=staff, curriculum_edition_id=seed.edition_id,
                conversation_id=interrupted.conversation_id,
                request=HitlResumeRequest(action=HitlAction.EDIT, edited_response=edited,
                                          interrupt_id=interrupted.interrupt.interrupt_id),
            )
        inspected = await graph.inspect_interrupt(
            session=session, actor=staff, curriculum_edition_id=seed.edition_id,
            conversation_id=interrupted.conversation_id,
        )
        assert inspected.interrupt.interrupt_id == interrupted.interrupt.interrupt_id
        assert inspected.artifacts.proposed_response.derivation_bridge is None
