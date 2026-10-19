"""Scripted reviewer-decision recovery; worker failure is not teacher rejection."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.db_models import TeachingMode, TeachingTurn, TeachingTurnStatus
from quantum_agent.teaching.execution_budget import (
    ExecutionBudgetError,
    current_execution_budget,
)
from quantum_agent.teaching.hitl import (
    HitlAction,
    HitlConflictError,
    HitlEvent,
    HitlInterruptResponse,
    HitlRejectedResponse,
    HitlResumeRequest,
)
from quantum_agent.teaching.models import TeachingTurnInput
from quantum_agent.teaching.repository import StartedTeachingTurn, TeachingRepository
from quantum_agent.tutor.graph import TutorGraph
from tests import test_tutor_graph
from tests.test_tutor_graph import StaticRetriever, _packet, _seed, _seed_staff

teaching_database = test_tutor_graph.teaching_database


@pytest.mark.parametrize("failure", ["budget", "worker", "contradictory_rejection_marker"])
async def test_replayed_persisted_approval_never_fabricates_teacher_rejection_after_failure(
    teaching_database: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    async with teaching_database() as session:
        seed = await _seed(session)
        staff = await _seed_staff(session, seed)
        retriever = StaticRetriever(_packet(seed.actor.course_id, seed.edition_id, found=False))
        graph = TutorGraph(evidence_retriever=retriever, model_gateway=None,
                           checkpointer=InMemorySaver(), enable_hitl=True)
        interrupted = await graph.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS, message="Inspect an unsupported claim",
                student_attempt="I cannot justify this claim from the course evidence.",
            ),
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        decision = HitlResumeRequest(
            interrupt_id=interrupted.interrupt.interrupt_id, action=HitlAction.APPROVE,
            note="SCRIPTED approval fixture; not an actual teacher decision.",
        )
        original = TeachingRepository.record_resolution

        async def fail_after_durable_approval(
            repository: TeachingRepository, *, started: StartedTeachingTurn, event: HitlEvent,
        ) -> None:
            await original(repository, started=started, event=event)
            await session.commit()
            if failure == "budget":
                budget = current_execution_budget()
                assert budget is not None
                await budget.exhaust("provider_requests")
            # A resumable pause intentionally survives a mere request error.
            # Simulate a worker/service persisting a terminal failure instead;
            # the independent approval receipt must remain unchanged.
            await repository.fail_turn(started, failure_code="execution_failed")
            await session.commit()
            raise RuntimeError("scripted worker failure after durable approval")

        monkeypatch.setattr(TeachingRepository, "record_resolution", fail_after_durable_approval)
        with pytest.raises(ExecutionBudgetError if failure == "budget" else RuntimeError):
            await graph.resume(
                session=session, actor=staff, curriculum_edition_id=seed.edition_id,
                conversation_id=interrupted.conversation_id, request=decision,
            )
        monkeypatch.setattr(TeachingRepository, "record_resolution", original)
        turn = await session.get(TeachingTurn, interrupted.turn_id)
        assert turn is not None and turn.status is TeachingTurnStatus.FAILED
        receipt = turn.scientific_results_json["__hitl_decisions"][str(decision.interrupt_id)]
        assert receipt["resolution"]["action"] == "approve"
        if failure == "contradictory_rejection_marker":
            turn.failure_code = "HITL_REJECTED"
            await session.commit()
        restarted = TutorGraph(evidence_retriever=retriever, model_gateway=None,
                               checkpointer=InMemorySaver(), enable_hitl=True)
        expected_error = ExecutionBudgetError if failure == "budget" else HitlConflictError
        with pytest.raises(expected_error) as error:
            await restarted.resume(
                session=session, actor=staff, curriculum_edition_id=seed.edition_id,
                conversation_id=interrupted.conversation_id, request=decision,
            )
        if failure == "budget":
            assert isinstance(error.value, ExecutionBudgetError)
            assert error.value.reason == "provider_requests"
        await session.refresh(turn)
        stored = turn.scientific_results_json["__hitl_decisions"][str(decision.interrupt_id)]
        assert stored == receipt


async def test_actual_rejected_decision_replays_as_rejected_after_checkpoint_restart(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seed = await _seed(session)
        staff = await _seed_staff(session, seed)
        retriever = StaticRetriever(_packet(seed.actor.course_id, seed.edition_id, found=False))
        graph = TutorGraph(evidence_retriever=retriever, model_gateway=None,
                           checkpointer=InMemorySaver(), enable_hitl=True)
        interrupted = await graph.run(
            session=session, actor=seed.actor, curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS, message="Inspect the unsupported explanation",
                student_attempt="I do not have adequate evidence for that assertion.",
            ),
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        decision = HitlResumeRequest(
            interrupt_id=interrupted.interrupt.interrupt_id, action=HitlAction.REJECT,
            note="SCRIPTED rejection fixture; not an actual teacher decision.",
        )
        rejected = await graph.resume(
            session=session, actor=staff, curriculum_edition_id=seed.edition_id,
            conversation_id=interrupted.conversation_id, request=decision,
        )
        assert isinstance(rejected, HitlRejectedResponse)
        restarted = TutorGraph(evidence_retriever=retriever, model_gateway=None,
                               checkpointer=InMemorySaver(), enable_hitl=True)
        replay = await restarted.resume(
            session=session, actor=staff, curriculum_edition_id=seed.edition_id,
            conversation_id=interrupted.conversation_id, request=decision,
        )
        assert replay == rejected
