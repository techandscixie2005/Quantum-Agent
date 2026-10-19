"""Scripted checks of assessment scope; no student or teacher outcomes."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.db_models import LearningEvidence, LearningEvidenceKind, TeachingMode
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest
from quantum_agent.teaching.course_packages import (
    FINITE_BARRIERS,
    FINITE_BARRIERS_1_1,
    CoursePackageSelection,
    course_package,
)
from quantum_agent.teaching.learning_native import LearningNativePolicy
from quantum_agent.teaching.models import (
    AssessmentEvidence,
    ConceptStateLabel,
    LearningNativeSubmission,
    SoloAttemptSubmission,
    TeachingTurnInput,
    TeachingTurnResult,
    TransferVerificationSpec,
)
from quantum_agent.tutor.graph import TutorGraph
from tests import test_learning_native
from tests.test_learning_native import (
    TunnelingRetriever,
    _seed_actor,
    _seed_conversation_with_phase,
)

learning_native_database = test_learning_native.learning_native_database


def test_new_package_is_explicit_and_original_content_digest_is_preserved() -> None:
    assert FINITE_BARRIERS.reference().content_sha256 == (
        "dff1a96d36bc0f4345750196d8a9bc7b1ad66b6bfe05c8a897caeb5e3f96ce7d"
    )
    assert FINITE_BARRIERS_1_1.reference() != FINITE_BARRIERS.reference()
    assert course_package(CoursePackageSelection(
        package_id="finite-barriers", version="1.0.0",
    )) is FINITE_BARRIERS
    assert course_package(CoursePackageSelection(
        package_id="finite-barriers", version="1.1.0",
    )) is FINITE_BARRIERS_1_1
    assert "not_assessed" in FINITE_BARRIERS_1_1.evidence_policy
    with pytest.raises(ValidationError):
        AssessmentEvidence.model_validate({"mastery_status": "demonstrated"})


def _evidence(
    kind: LearningEvidenceKind, assessment: AssessmentEvidence | None,
) -> LearningEvidence:
    return LearningEvidence(
        kind=kind, observation="Scripted scoped check",
        evidence_json={
            "verified": True, "unaided": True, "confidence": 0.8,
            **({"assessment_evidence": assessment.model_dump(mode="json")}
               if assessment is not None else {}),
        },
    )


@pytest.mark.parametrize("assessment", [
    None,
    AssessmentEvidence(valid_independent_submission=True, numeric_correctness="correct"),
    AssessmentEvidence(valid_independent_submission=True),
    AssessmentEvidence(explanation_assessment="model_supported"),
])
def test_legacy_numeric_only_missing_and_revised_checks_do_not_imply_mastery(
    assessment: AssessmentEvidence | None,
) -> None:
    state = LearningNativePolicy._concept_state(
        concept_id=uuid4(), observations=[_evidence(
            LearningEvidenceKind.TRANSFER_VERIFIED, assessment,
        )], diagnosis=None,
    )
    assert state.label is ConceptStateLabel.DEVELOPING
    assert state.unaided_retrieval is False
    assert state.last_demonstrated_at is None
    assert state.assessment_evidence.mastery_status == "not_assessed"
    assert state.confidence_history == (
        [(0.8, True)] if assessment is not None
        and assessment.numeric_correctness == "correct" else []
    )


def test_first_model_supported_explanation_is_still_not_a_mastery_verdict() -> None:
    state = LearningNativePolicy._concept_state(
        concept_id=uuid4(), observations=[_evidence(
            LearningEvidenceKind.TRANSFER_VERIFIED,
            AssessmentEvidence(valid_independent_submission=True,
                               explanation_assessment="model_supported"),
        )], diagnosis=None,
    )
    assert state.unaided_retrieval is True
    assert state.label is ConceptStateLabel.DEVELOPING
    assert state.assessment_evidence.mastery_status == "not_assessed"
    assert state.confidence_history == []


@pytest.mark.parametrize(("answer_kind", "correctness"), [
    ("number", "correct"), ("contradictory_explanation", "correct"),
    ("wrong_number", "incorrect"), ("missing", "not_assessed"),
])
async def test_locked_first_submission_and_numeric_check_are_separate_from_explanation(
    learning_native_database: async_sessionmaker[AsyncSession],
    answer_kind: str, correctness: str,
) -> None:
    task_id = uuid4()
    scientific = RectangularBarrierRequest(
        energy_eV=5, barrier_height_eV=10, barrier_width_m=0.1e-9,
        particle_mass_kg=9.1093837015e-31,
    )
    expected = float(ScientificToolbox().verify(scientific).metrics["T"])
    answers = {
        "number": str(expected),
        "contradictory_explanation": f"T={expected}; the wavefunction inside is exactly zero.",
        "wrong_number": "T=0", "missing": "I do not know the answer or mechanism.",
    }
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        conversation_id = await _seed_conversation_with_phase(
            session, seed, phase="solo_active", extra_phase={
                "active_transfer_task_id": str(task_id), "solo_assistance_locked": True,
                "active_transfer_task_prompt": "Calculate T and explain the physics.",
                "transfer_verification": TransferVerificationSpec(
                    scientific_request=scientific.model_dump(mode="json"), metric_name="T",
                    expected_value=expected,
                ).model_dump(mode="json"),
            },
        )
    graph = TutorGraph(evidence_retriever=TunnelingRetriever(), model_gateway=None,
                       checkpointer=InMemorySaver(), enable_hitl=False)
    async with learning_native_database() as session:
        result = await graph.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                conversation_id=conversation_id, mode=TeachingMode.LEARN_CONCEPTS,
                message="Submit scripted independent response",
                learning_native=LearningNativeSubmission(solo_attempt=SoloAttemptSubmission(
                    response=answers[answer_kind], transfer_task_id=task_id, confidence=0.8,
                )),
            ),
        )
        assert isinstance(result, TeachingTurnResult) and result.learning_native is not None
        assessment = result.learning_native.assessment_evidence
        assert assessment.valid_independent_submission is True
        assert assessment.numeric_correctness == correctness
        assert assessment.explanation_assessment == "not_assessed"
        assert assessment.mastery_status == "not_assessed"
        mirror = result.learning_native.cognitive_mirror
        if correctness == "correct":
            assert mirror is not None and mirror.concept_states
            assert all(item.label not in {ConceptStateLabel.DEMONSTRATED,
                                         ConceptStateLabel.TRANSFER_READY}
                       and not item.unaided_retrieval for item in mirror.concept_states)
        else:
            assert mirror is None  # Active Solo suppresses answer-bearing projections.
        row = await session.scalar(select(LearningEvidence).where(
            LearningEvidence.teaching_turn_id == result.turn_id,
            LearningEvidence.kind == LearningEvidenceKind.SOLO_ATTEMPT,
        ))
        assert row is not None
        assert row.evidence_json["assessment_evidence"] == assessment.model_dump(mode="json")


@pytest.mark.parametrize("model_available", [False, True])
async def test_explanation_inference_is_scoped_and_unavailable_is_not_incorrect(
    learning_native_database: async_sessionmaker[AsyncSession], model_available: bool,
) -> None:
    task_id = uuid4()
    baseline = RectangularBarrierRequest(
        energy_eV=5, barrier_height_eV=10, barrier_width_m=0.1e-9,
        particle_mass_kg=9.1093837015e-31,
    )
    changed = baseline.model_copy(update={"barrier_width_m": 0.2e-9})
    answer = "T decreases; kappa stays fixed, and the attenuation distance is longer."
    gateway = FakeModelGateway({"evaluate_barrier_trend": {
        "trend": "decreases", "trend_quote": "T decreases",
        "mechanism": "evanescent_width_dependence",
        "mechanism_quote": "attenuation distance is longer", "contradictions": [],
        "rationale": "Scripted model candidate; no teacher review.",
    }}) if model_available else None
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        conversation_id = await _seed_conversation_with_phase(
            session, seed, phase="solo_active", extra_phase={
                "active_transfer_task_id": str(task_id), "solo_assistance_locked": True,
                "active_transfer_task_prompt": "Explain the fixed E,V0 width trend.",
                "transfer_verification": TransferVerificationSpec(
                    scientific_request=changed.model_dump(mode="json"),
                    baseline_request=baseline.model_dump(mode="json"), metric_name="T",
                    expected_value=float(ScientificToolbox().verify(changed).metrics["T"]),
                    evaluation_mode="barrier_trend",
                ).model_dump(mode="json"),
            },
        )
    graph = TutorGraph(evidence_retriever=TunnelingRetriever(), model_gateway=gateway,
                       checkpointer=InMemorySaver(), enable_hitl=False)
    async with learning_native_database() as session:
        result = await graph.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                conversation_id=conversation_id, mode=TeachingMode.LEARN_CONCEPTS,
                message="Submit explanation",
                learning_native=LearningNativeSubmission(solo_attempt=SoloAttemptSubmission(
                    response=answer, transfer_task_id=task_id,
                )),
            ),
        )
        assert isinstance(result, TeachingTurnResult) and result.learning_native is not None
        assessment = result.learning_native.assessment_evidence
        assert assessment.valid_independent_submission is True
        assert assessment.numeric_correctness == "not_assessed"
        assert assessment.explanation_assessment == (
            "model_supported" if model_available else "not_assessed"
        )
        assert assessment.mastery_status == "not_assessed"
