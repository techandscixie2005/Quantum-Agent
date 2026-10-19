"""Scripted integration checks; these are not classroom observations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.config import Settings
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AnswerReleaseLevel,
    CourseMembership,
    CourseRole,
    LearningEvidence,
    LearningEvidenceKind,
    TeachingConversation,
    TeachingMode,
    TeachingReview,
)
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.main import create_app
from quantum_agent.science import ComplexValue, NumericalNormalizationRequest, ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest
from quantum_agent.teaching.course_packages import FINITE_BARRIERS, CoursePackageSelection
from quantum_agent.teaching.hitl import (
    HitlAction,
    HitlInterruptResponse,
    HitlRejectedResponse,
    HitlResumeRequest,
)
from quantum_agent.teaching.models import (
    DiagnosisOutput,
    DiagnosisStatus,
    LearningNativeSubmission,
    LearningPhase,
    SoloAttemptSubmission,
    TeachingTurnInput,
    TeachingTurnResult,
    TransferVerificationSpec,
)
from quantum_agent.teaching.reviews import TeacherReviewRequest
from quantum_agent.teaching.state_machine import TeachingStateMachine, _answer_grounded_probe
from quantum_agent.tutor.graph import TutorGraph
from quantum_agent.tutor.nodes import _attempt_verified
from tests import test_learning_native, test_teaching_api
from tests.test_learning_native import (
    TunnelingRetriever,
    _seed_actor,
    _seed_conversation_with_phase,
)
from tests.test_teaching_api import _seed

learning_native_database = test_learning_native.learning_native_database
teaching_api_database = test_teaching_api.teaching_api_database


def test_versioned_package_is_immutable_and_internally_traceable() -> None:
    reference = FINITE_BARRIERS.reference()
    assert reference == FINITE_BARRIERS.reference()
    assert len(reference.content_sha256) == 64
    assert len(reference.objective_ids) == len(reference.rubric_ids) == 4
    assert FINITE_BARRIERS.validation_status.endswith("classroom effectiveness unevaluated")
    with pytest.raises(ValidationError):
        FINITE_BARRIERS.version = "rewritten"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="unknown course package"):
        CoursePackageSelection(package_id="finite-barriers", version="unpublished")
    broken = FINITE_BARRIERS.model_dump()
    broken["rubric"][0]["objective_id"] = "invented"
    with pytest.raises(ValidationError, match="reference package objectives"):
        type(FINITE_BARRIERS).model_validate(broken)


@pytest.mark.parametrize("key", ["", "  "])
def test_empty_request_keys_and_solo_answers_are_rejected(key: str) -> None:
    with pytest.raises(ValidationError):
        TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS, message="question", client_request_id=key,
        )
    with pytest.raises(ValidationError):
        SoloAttemptSubmission(response=key)


async def test_solo_first_answer_survives_feedback_revisions_and_task_mismatch(
    learning_native_database: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    scientific = NumericalNormalizationRequest(state=[ComplexValue(real=1)])
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        conversation_id = await _seed_conversation_with_phase(
            session, seed, phase="solo_active", extra_phase={
                "active_transfer_task_id": str(task_id),
                "active_transfer_task_prompt": "Explain transmission under changed width.",
                "solo_assistance_locked": True,
                "course_package": FINITE_BARRIERS.reference().model_dump(mode="json"),
                "transfer_verification": TransferVerificationSpec(
                    scientific_request=scientific.model_dump(mode="json"),
                    metric_name="norm", expected_value=1,
                ).model_dump(mode="json"),
            },
        )
    graph = TutorGraph(evidence_retriever=TunnelingRetriever(), model_gateway=None,
                       checkpointer=InMemorySaver(), enable_hitl=False)
    results: list[TeachingTurnResult] = []
    for response, submitted_task in [
        ("A response to a different task", uuid4()),
        ("My unaided first answer: transmission is zero", task_id),
        ("My later revised explanation: transmission can be nonzero", task_id),
    ]:
        async with learning_native_database() as session:
            result = await graph.run(
                session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
                request=TeachingTurnInput(
                    conversation_id=conversation_id, mode=TeachingMode.LEARN_CONCEPTS,
                    message="Submit independent answer", client_request_id=str(uuid4()),
                    learning_native=LearningNativeSubmission(solo_attempt=SoloAttemptSubmission(
                        response=response, transfer_task_id=submitted_task,
                    )),
                ),
            )
            assert isinstance(result, TeachingTurnResult)
            results.append(result)
            await session.commit()
    assert results[0].learning_native is not None
    assert results[0].learning_native.solo_first_attempt is None
    assert results[0].scientific_results == []
    assert results[0].response.claims == []
    first = results[1].learning_native
    last = results[2].learning_native
    assert first is not None and last is not None and first.solo_first_attempt is not None
    assert first.solo_first_attempt == last.solo_first_attempt
    assert first.solo_first_attempt.response.startswith("My unaided first answer")
    assert last.phase is LearningPhase.SOLO_ACTIVE
    async with learning_native_database() as session:
        mismatches = (await session.scalars(select(LearningEvidence).where(
            LearningEvidence.teaching_turn_id == results[0].turn_id,
        ))).all()
        assert len(mismatches) == 1
        assert mismatches[0].kind is LearningEvidenceKind.CHECK_RESPONSE
        assert mismatches[0].evidence_json["assessment_status"] == "task_mismatch"
        assert mismatches[0].evidence_json["active_transfer_task_id"] == str(task_id)
        assert mismatches[0].evidence_json["submitted_transfer_task_id"] != str(task_id)
        assert mismatches[0].evidence_json["unaided"] is False
        rows = (await session.scalars(select(LearningEvidence).where(
            LearningEvidence.student_user_id == seed.actor.user_id,
            LearningEvidence.kind == LearningEvidenceKind.SOLO_ATTEMPT,
        ))).all()
        conversation = await session.get(TeachingConversation, conversation_id)
        assert len(rows) == 1 and rows[0].evidence_json["first_attempt"] is True
        assert rows[0].evidence_json["course_package"]["content_sha256"]
        assert conversation is not None and conversation.learning_phase_json is not None
        assert conversation.learning_phase_json["solo_attempt_count"] == 2


async def test_solo_correct_retry_is_revision_success_without_independent_credit(
    learning_native_database: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    scientific = NumericalNormalizationRequest(state=[ComplexValue(real=1)])
    spec = TransferVerificationSpec(
        scientific_request=scientific.model_dump(mode="json"), metric_name="norm",
        expected_value=1,
    )
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        conversation_id = await _seed_conversation_with_phase(
            session, seed, phase="solo_active", extra_phase={
                "active_transfer_task_id": str(task_id), "solo_assistance_locked": True,
                "active_transfer_task_prompt": "Calculate the norm independently.",
                "transfer_verification": spec.model_dump(mode="json"),
            },
        )
    graph = TutorGraph(evidence_retriever=TunnelingRetriever(), model_gateway=None,
                       checkpointer=InMemorySaver(), enable_hitl=False)
    results: list[TeachingTurnResult] = []
    for answer in ("0", "1"):
        async with learning_native_database() as session:
            result = await graph.run(
                session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.LEARN_CONCEPTS, message="Independent submission",
                    conversation_id=conversation_id,
                    learning_native=LearningNativeSubmission(solo_attempt=SoloAttemptSubmission(
                        response=answer, transfer_task_id=task_id,
                    )),
                ),
            )
            assert isinstance(result, TeachingTurnResult)
            results.append(result)
            await session.commit()
    assert results[0].scientific_results == []
    assert results[1].learning_loop_completed is True
    native = results[1].learning_native
    assert native is not None and native.solo_first_attempt is not None
    assert native.solo_first_attempt.response == "0"
    assert native.cognitive_mirror is not None
    assert all(not item.unaided_retrieval for item in native.cognitive_mirror.concept_states)
    async with learning_native_database() as session:
        row = await session.scalar(select(LearningEvidence).where(
            LearningEvidence.teaching_turn_id == results[1].turn_id,
            LearningEvidence.kind == LearningEvidenceKind.TRANSFER_VERIFIED,
        ))
        assert row is not None and row.evidence_json["unaided"] is False
        assert row.evidence_json["first_attempt"] is False
        assert row.evidence_json["attempt_number"] == 2
        ended = await session.scalar(select(LearningEvidence).where(
            LearningEvidence.teaching_turn_id == results[1].turn_id,
            LearningEvidence.kind == LearningEvidenceKind.SOLO_VERIFIED,
        ))
        assert ended is not None and ended.evidence_json["unaided"] is False


async def test_solo_missing_task_id_cannot_receive_assessment_or_oracle(
    learning_native_database: async_sessionmaker[AsyncSession],
) -> None:
    scientific = NumericalNormalizationRequest(state=[ComplexValue(real=1)])
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        conversation_id = await _seed_conversation_with_phase(
            session, seed, phase="solo_active", extra_phase={
                "active_transfer_task_id": str(uuid4()), "solo_assistance_locked": True,
                "active_transfer_task_prompt": "Calculate the norm independently.",
                "transfer_verification": TransferVerificationSpec(
                    scientific_request=scientific.model_dump(mode="json"),
                    metric_name="norm", expected_value=1,
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
                message="Submit the right number without a task identity",
                learning_native=LearningNativeSubmission(
                    solo_attempt=SoloAttemptSubmission(response="1"),
                ),
            ),
        )
        assert isinstance(result, TeachingTurnResult)
        assert result.scientific_results == []
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.SOLO_ACTIVE
        assert result.learning_native.solo_first_attempt is None
        rows = (await session.scalars(select(LearningEvidence).where(
            LearningEvidence.teaching_turn_id == result.turn_id,
        ))).all()
        assert len(rows) == 1 and rows[0].kind is LearningEvidenceKind.CHECK_RESPONSE
        assert rows[0].evidence_json["assessment_status"] == "missing_task_id"
        assert rows[0].evidence_json["unaided"] is False


async def test_rejected_hitl_turn_keeps_immutable_solo_first_answer(
    learning_native_database: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        conversation_id = await _seed_conversation_with_phase(
            session, seed, phase="solo_active", extra_phase={
                "active_transfer_task_id": str(task_id), "solo_assistance_locked": True,
                "active_transfer_task_prompt": "Explain the independent task.",
            },
        )
    graph = TutorGraph(evidence_retriever=TunnelingRetriever(), model_gateway=None,
                       checkpointer=InMemorySaver(), enable_hitl=True)
    async with learning_native_database() as session:
        interrupted = await graph.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                conversation_id=conversation_id, mode=TeachingMode.LEARN_CONCEPTS,
                message="request teacher approval", learning_native=LearningNativeSubmission(
                    solo_attempt=SoloAttemptSubmission(
                        response="Original unaided answer survives rejection",
                        transfer_task_id=task_id,
                    ),
                ),
            ),
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        await session.commit()
    async with learning_native_database() as session:
        rejected = await graph.resume(
            session=session,
            actor=seed.actor.model_copy(update={"course_role": CourseRole.TEACHER}),
            curriculum_edition_id=seed.edition_id, conversation_id=conversation_id,
            request=HitlResumeRequest(
                action=HitlAction.REJECT, note="Scripted teacher rejects this turn",
                interrupt_id=interrupted.interrupt.interrupt_id,
            ),
        )
        assert isinstance(rejected, HitlRejectedResponse)
    async with learning_native_database() as session:
        rows = (await session.scalars(select(LearningEvidence).where(
            LearningEvidence.teaching_turn_id == interrupted.turn_id,
            LearningEvidence.kind == LearningEvidenceKind.SOLO_ATTEMPT,
        ))).all()
        assert len(rows) == 1
        assert rows[0].evidence_json["response"] == "Original unaided answer survives rejection"


async def test_teacher_review_requires_authority_reason_and_changes_next_action(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        seed = await _seed(session)
    app = create_app(Settings(_env_file=None, ENVIRONMENT="test",
                             DATABASE_URL="sqlite+aiosqlite:///:memory:", USTC_API=None,
                             NEO4J_PASSWORD=None))
    app.state.teaching_workflow = TutorGraph(
        evidence_retriever=TunnelingRetriever(), model_gateway=None,
        checkpointer=InMemorySaver(), enable_hitl=False,
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seed.course_id}/editions/{seed.edition_id}"
    student = {"Authorization": f"Bearer {seed.student_token}"}
    teacher = {"Authorization": f"Bearer {seed.teacher_token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        opened = await client.post(f"{base}/teaching/turns", headers=student, json={
            "mode": "learn_concepts", "message": "What is transmission?",
            "course_package": {"package_id": "finite-barriers", "version": "1.0.0"},
        })
        assert opened.status_code == 200, opened.text
        conversation_id = opened.json()["conversation_id"]
        reviews = f"{base}/teacher/conversations/{conversation_id}/reviews"
        payload = {
            "source_turn_id": opened.json()["turn_id"], "decision": "revise",
            "reason": "The answer equates density with transmitted flux; ask for the distinction.",
            "follow_up": "request_revision", "probe": "Explain how flux differs from density.",
            "criterion_ratings": {"FB-R2": "needs_revision"},
        }
        forbidden = await client.post(reviews, headers=student, json=payload)
        assert forbidden.status_code == 403
        blank = await client.post(reviews, headers=teacher, json={**payload, "reason": " "})
        assert blank.status_code == 422
        invalid_source = await client.post(reviews, headers=teacher, json={
            **payload, "source_turn_id": str(uuid4()),
        })
        assert invalid_source.status_code == 404
        unknown_rubric = await client.post(reviews, headers=teacher, json={
            **payload, "criterion_ratings": {"foreign-criterion": "meets"},
        })
        assert unknown_rubric.status_code == 422
        created = await client.post(reviews, headers=teacher, json=payload)
        assert created.status_code == 201, created.text
        duplicate_pending = await client.post(reviews, headers=teacher, json=payload)
        assert duplicate_pending.status_code == 409
        continued = await client.post(f"{base}/teaching/turns", headers=student, json={
            "conversation_id": conversation_id, "mode": "learn_concepts",
            "message": "What is transmission?", "client_request_id": "review-follow-up",
        })
        assert continued.status_code == 200, continued.text
        result = continued.json()
        assert result["release"]["reason_code"] == "teacher_request_revision"
        assert result["response"]["next_question"] == payload["probe"]
        assert result["response"]["claims"] == []
        assert (
            result["learning_native"]["teacher_follow_up"]["review_id"]
            == created.json()["review_id"]
        )
        switched = await client.post(f"{base}/teaching/turns", headers=student, json={
            "conversation_id": conversation_id, "mode": "run_experiments",
            "message": "Predict a change", "student_attempt": "I predict transmission decreases.",
        })
        assert switched.status_code == 200, switched.text
        traces = await client.get(f"{base}/teacher/agent-traces", headers=teacher)
        old_trace = next(item for item in traces.json()["items"]
                         if item["teaching_turn_id"] == opened.json()["turn_id"])
        assert old_trace["mode"] == "learn_concepts"
        old_detail = await client.get(
            f"{base}/teacher/agent-traces/{old_trace['id']}", headers=teacher,
        )
        assert old_detail.status_code == 200
        assert old_detail.json()["course_package"]["content_sha256"] == (
            FINITE_BARRIERS.reference().content_sha256
        )
        forbidden_read = await client.get(reviews, headers=student)
        assert forbidden_read.status_code == 403
        recorded = await client.get(reviews, headers=teacher)
        assert recorded.status_code == 200 and len(recorded.json()) == 1
        assert recorded.json()[0]["reason"] == payload["reason"]
        async with teaching_api_database() as session:
            membership = await session.scalar(select(CourseMembership).where(
                CourseMembership.course_id == seed.course_id,
                CourseMembership.role == CourseRole.TEACHER,
            ))
            assert membership is not None
            membership.role = CourseRole.TA
            await session.commit()
        ta_mutation = await client.post(reviews, headers=teacher, json=payload)
        assert ta_mutation.status_code == 403
        ta_read = await client.get(reviews, headers=teacher)
        assert ta_read.status_code == 200
    async with teaching_api_database() as session:
        rows = (await session.scalars(select(TeachingReview))).all()
        assert len(rows) == 1
        conversation = await session.get(TeachingConversation, UUID(conversation_id))
        assert conversation is not None and conversation.learning_phase_json is not None
        assert conversation.learning_phase_json["pending_teacher_follow_up"] is None
        assert conversation.learning_phase_json["last_applied_teacher_review_id"] == str(rows[0].id)
        with pytest.raises(IntegrityError, match="append-only"):
            await session.execute(update(TeachingReview).values(reason="rewritten history"))
        await session.rollback()


def test_revision_decision_requires_an_actionable_probe() -> None:
    with pytest.raises(ValidationError, match="requires a concrete probe"):
        TeacherReviewRequest(source_turn_id=uuid4(), decision="revise", reason="A real reason",
                             follow_up="revisit_prerequisite")


def test_near_zero_transmission_assessment_requires_relative_accuracy() -> None:
    request = RectangularBarrierRequest(
        energy_eV=1, barrier_height_eV=4, barrier_width_m=5e-9,
        particle_mass_kg=9.1093837139e-31,
    )
    result = ScientificToolbox().verify(request)
    expected = result.metrics["T"]
    assert isinstance(expected, (int, float)) and 0 < expected < 1e-12
    spec = TransferVerificationSpec(
        scientific_request=request.model_dump(mode="json"), metric_name="T",
        expected_value=expected, absolute_tolerance=1e-6,
    )
    assert not _attempt_verified({"scientific_results": [result]}, "T=0", spec)
    assert not _attempt_verified({"scientific_results": [result]}, f"T={expected*1.1}", spec)
    assert _attempt_verified({"scientific_results": [result]}, f"T={expected*1.005}", spec)


def test_adaptive_probe_quotes_current_answer_without_asserting_a_deficit() -> None:
    request = TeachingTurnInput(
        mode=TeachingMode.LEARN_CONCEPTS, message="Explain transmission",
        student_attempt="I think finite width makes transmission exactly zero.",
    )
    question, anchor = _answer_grounded_probe(request, DiagnosisOutput(
        status=DiagnosisStatus.OBSERVED, summary="An attempt was submitted.",
    ), AnswerReleaseLevel.SCAFFOLD)
    assert anchor == request.student_attempt
    assert anchor is not None and anchor in question
    # The question elicits a reason/check; observing an answer is not a diagnosis.
    assert "missing" not in question and "prerequisite" not in question


async def test_legacy_credential_override_does_not_mutate_shared_gateway(
    learning_native_database: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, first, second = FakeModelGateway(), FakeModelGateway(), FakeModelGateway()
    machine = TeachingStateMachine(evidence_retriever=TunnelingRetriever(), model_gateway=base)
    entered = asyncio.Event()
    release = asyncio.Event()
    observed: list[object] = []

    async def blocked_run(
        runner: TeachingStateMachine, *_args: object, **_kwargs: object,
    ) -> TeachingTurnResult:
        observed.append(runner._model_gateway)
        if len(observed) == 2:
            entered.set()
        await release.wait()
        observed.append(runner._model_gateway)
        return cast(TeachingTurnResult, object())

    monkeypatch.setattr(TeachingStateMachine, "_run_with_gateway", blocked_run)
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        request = TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS, message="What is T?")
        one = asyncio.create_task(machine.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=request, model_gateway_override=first,
        ))
        two = asyncio.create_task(machine.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=request, model_gateway_override=second,
        ))
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert machine._model_gateway is base
        release.set()
        await asyncio.gather(one, two)
    assert observed == [first, second, first, second]


async def test_legacy_first_turn_retry_returns_stored_snapshot(
    learning_native_database: async_sessionmaker[AsyncSession],
) -> None:
    machine = TeachingStateMachine(evidence_retriever=TunnelingRetriever(), model_gateway=None)
    async with learning_native_database() as session:
        seed = await _seed_actor(session)
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS, message="What is T?", client_request_id="first-retry",
        )
        original = await machine.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=request,
        )
        await session.commit()
    async with learning_native_database() as session:
        replay = await machine.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=request,
        )
        assert replay == original
