"""Deterministic aggregate budgets; local HTTP transports never contact a model."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.db_models import LearningEvidence, TeachingMode, TeachingTurn, TeachingTurnStatus
from quantum_agent.llm.gateway import Message, PydanticAIModelGateway
from quantum_agent.llm.observability import provider_request, provider_response
from quantum_agent.llm.routing import ModelCapabilityRegistry, ModelRouter
from quantum_agent.teaching.execution_budget import (
    ExecutionBudget,
    ExecutionBudgetBusyError,
    ExecutionBudgetError,
    ExecutionLimits,
    budget_status,
    budget_status_json,
    execution_budget_scope,
)
from quantum_agent.teaching.hitl import HitlAction, HitlInterruptResponse, HitlResumeRequest
from quantum_agent.teaching.models import (
    LearningNativeSubmission,
    SoloAttemptSubmission,
    TeachingTurnInput,
)
from quantum_agent.teaching.repository import TeachingRepository
from quantum_agent.tutor.graph import TutorGraph
from tests.test_llm_gateway import StructuredProbe, _chat_response
from tests.test_tutor_graph import StaticRetriever, _packet, _seed, _seed_staff
from tests.test_tutor_graph import teaching_database as teaching_database


class Clock:
    def __init__(self, seconds: float = 1000) -> None:
        self.seconds = seconds

    def __call__(self) -> float:
        return self.seconds


def test_sql_budget_projection_does_not_accept_invalid_or_unversioned_ledger() -> None:
    assert budget_status_json({}, uuid4()) == {"state": "not_initialized"}
    raw_values: tuple[Any, ...] = (None, [], {"state": "running"}, {"secret": "must not appear"})
    for raw in raw_values:
        with pytest.raises(ExecutionBudgetError) as error:
            budget_status_json(raw, uuid4())
        assert error.value.reason == "invalid_ledger"
        assert "secret" not in str(error.value)


def request() -> httpx2.Request:
    return httpx2.Request(
        "POST",
        "https://local.invalid/v1/chat/completions",
        json={
            "model": "synthetic",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 32,
        },
    )


async def test_review_wait_and_provider_reservations_survive_new_session_and_limits(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    clock = Clock()
    async with teaching_database() as session:
        seed = await _seed(session)
        started = await TeachingRepository(session).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="Synthetic question",
                client_request_id="persisted-budget",
            ),
        )
        turn_id = started.turn.id
        budget = ExecutionBudget(
            session,
            started.turn,
            limits=ExecutionLimits(active_seconds=10, provider_requests=2),
            clock=clock,
            wall_clock=clock,
        )
        assert await budget.start() == 10
        first = request()
        await budget.reserve_provider(first)
        await budget.reserve_provider(first)  # repeated hook, same physical request
        async with budget.stage("interpret"):
            clock.seconds += 3
        await budget.finish("waiting")
        await session.rollback()  # committed reservations cannot be refunded
    clock.seconds += 10_000
    async with teaching_database() as recovered:
        turn = await recovered.get(TeachingTurn, turn_id)
        assert turn is not None
        snapshot = budget_status(turn, wall_time=clock())
        assert snapshot["human_wait_seconds"] == 10_000
        assert snapshot["active_used_seconds"] == 3
        resumed = ExecutionBudget(
            recovered,
            turn,
            limits=ExecutionLimits(active_seconds=600),
            clock=clock,
            wall_clock=clock,
        )
        assert await resumed.start() == 7  # deployment changes cannot refill
        await resumed.reserve_provider(request())
        clock.seconds += 2
        await resumed.finish("finished")
    async with teaching_database() as replay_session:
        turn = await replay_session.get(TeachingTurn, turn_id)
        assert turn is not None
        status = budget_status(turn, wall_time=clock())
        assert status["provider_requests"] == 2
        assert status["active_used_seconds"] == 5
        assert status["human_wait_seconds"] == 10_000
        assert status["limits"]["active_seconds"] == 10
        assert status["stage_timings"]["interpret"] == {
            "active_seconds": 3,
            "invocations": 1,
            "completed": 1,
        }
        exhausted = ExecutionBudget(
            replay_session, turn, limits=ExecutionLimits(), clock=clock, wall_clock=clock
        )
        await exhausted.start()
        with pytest.raises(ExecutionBudgetError, match="EXECUTION_BUDGET_EXHAUSTED") as error:
            await exhausted.reserve_provider(request())
        assert error.value.reason == "provider_requests"
        assert turn.status is TeachingTurnStatus.FAILED
        with pytest.raises(ExecutionBudgetError):
            await TeachingRepository(replay_session).start_turn(
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.LEARN_CONCEPTS,
                    message="Synthetic question",
                    client_request_id="persisted-budget",
                ),
            )


async def test_abandoned_worker_lease_blocks_parallel_recovery_then_cannot_refill(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    clock = Clock()
    async with teaching_database() as first:
        seed = await _seed(first)
        started = await TeachingRepository(first).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS, message="Crash fixture"),
        )
        turn_id = started.turn.id
        abandoned = ExecutionBudget(
            first,
            started.turn,
            limits=ExecutionLimits(active_seconds=5),
            clock=clock,
            wall_clock=clock,
        )
        await abandoned.start()
        await abandoned.reserve_provider(request())
        # Simulate worker exit without finally/refund; no process-local state is used below.
    async with teaching_database() as other:
        turn = await other.get(TeachingTurn, turn_id)
        assert turn is not None
        recovery = ExecutionBudget(
            other, turn, limits=ExecutionLimits(), clock=clock, wall_clock=clock
        )
        with pytest.raises(ExecutionBudgetBusyError):
            await recovery.start()
        await other.rollback()
        clock.seconds += 6
        with pytest.raises(ExecutionBudgetError) as error:
            await recovery.start()
        assert error.value.reason == "active_seconds"
        assert budget_status(turn, wall_time=clock())["provider_requests"] == 1
        assert budget_status(turn, wall_time=clock())["active_used_seconds"] == 5


async def test_late_worker_cannot_overwrite_recovered_exhausted_lease(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as original:
        seed = await _seed(original)
        started = await TeachingRepository(original).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS, message="Late worker fixture"
            ),
        )
        turn_id = started.turn.id
        slow_worker = ExecutionBudget(
            original,
            started.turn,
            limits=ExecutionLimits(active_seconds=5),
            clock=lambda: 1000,
            wall_clock=lambda: 1000,
        )
        await slow_worker.start()
        await slow_worker.reserve_provider(request())
        async with teaching_database() as recovery_session:
            turn = await recovery_session.get(TeachingTurn, turn_id)
            assert turn is not None
            recovered = ExecutionBudget(
                recovery_session,
                turn,
                limits=ExecutionLimits(),
                clock=lambda: 1006,
                wall_clock=lambda: 1006,
            )
            with pytest.raises(ExecutionBudgetError):
                await recovered.start()
        with pytest.raises(ExecutionBudgetError):
            await slow_worker.reserve_provider(request())
    async with teaching_database() as verify:
        turn = await verify.get(TeachingTurn, turn_id)
        assert turn is not None
        status = budget_status(turn, wall_time=1006)
        assert status["state"] == "exhausted"
        assert status["provider_requests"] == 1
        assert status["active_used_seconds"] == 5


@pytest.mark.parametrize(
    "reason,limits,payload",
    [
        ("request_bytes", ExecutionLimits(request_bytes=1024), {"messages": ["x" * 1100]}),
        ("reserved_tokens", ExecutionLimits(token_units=1024), {"max_tokens": 32}),
        ("output_tokens", ExecutionLimits(output_tokens=16), {"max_tokens": 32}),
    ],
)
async def test_rejected_provider_admission_never_reaches_transport(
    teaching_database: async_sessionmaker[AsyncSession],
    reason: str,
    limits: ExecutionLimits,
    payload: dict[str, Any],
) -> None:
    sent = 0

    async def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal sent
        sent += 1
        return httpx2.Response(200)

    async with teaching_database() as session:
        seed = await _seed(session)
        started = await TeachingRepository(session).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS, message="Resource fixture"),
        )
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), event_hooks={"request": [provider_request]}
        ) as client:
            with pytest.raises(ExecutionBudgetError) as error:
                async with execution_budget_scope(session, started.turn, limits):
                    await client.post("https://local.invalid/v1/chat/completions", json=payload)
        assert error.value.reason == reason
        assert sent == 0
        assert started.turn.execution_budget_json["provider_requests"] == 0


async def test_sdk_retries_and_router_fallback_share_actual_http_request_allowance(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    requests_seen: list[dict[str, Any]] = []

    async def handler(req: httpx2.Request) -> httpx2.Response:
        requests_seen.append(json.loads(req.content))
        return httpx2.Response(500, json={"error": {"message": "synthetic upstream failure"}})

    async with teaching_database() as session:
        seed = await _seed(session)
        started = await TeachingRepository(session).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS, message="Retry fixture"),
        )
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            router = ModelRouter(
                registry=ModelCapabilityRegistry.ustc_default(),
                gateway_factory=lambda profile: PydanticAIModelGateway(
                    api_key=SecretStr("synthetic-key"),
                    model_http_client=client,
                    default_model=profile.provider_model,
                    max_retries=0,
                    transient_retry_attempts=1,
                ),
            )
            with pytest.raises(ExecutionBudgetError) as error:
                async with execution_budget_scope(
                    session, started.turn, ExecutionLimits(provider_requests=2, output_tokens=64)
                ):
                    await router.structured_generate(
                        task="interpret_teaching_turn",
                        messages=[Message(role="user", content="synthetic")],
                        output_type=StructuredProbe,
                    )
        assert error.value.reason == "provider_requests"
        assert len(requests_seen) == 2
        assert all(body["max_completion_tokens"] == 64 for body in requests_seen)


async def test_reported_usage_is_preserved_once_across_request_hooks(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seed = await _seed(session)
        started = await TeachingRepository(session).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS, message="Usage fixture"),
        )
        async with execution_budget_scope(session, started.turn, ExecutionLimits()):
            req = request()
            await provider_request(req)
            response = httpx2.Response(200, json=_chat_response('{"value":7}'), request=req)
            await provider_response(response)
            await provider_response(response)
        status = budget_status(started.turn)
        assert status["reported_total_tokens"] == 8
        assert status["usage_reported_requests"] == 1
        assert status["provider_requests"] == 1
        assert status["usage_completeness"] == "reported"


@pytest.mark.parametrize("cancel", [False, True])
async def test_global_deadline_or_disconnect_persists_terminal_safe_state(
    teaching_database: async_sessionmaker[AsyncSession],
    cancel: bool,
) -> None:
    entered = asyncio.Event()

    async with teaching_database() as session:
        seed = await _seed(session)
        submitted = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="Deadline fixture",
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response=(
                        "Synthetic initial Solo answer\nwith original interior spacing  retained"
                    ),
                    transfer_task_id=uuid4(),
                )
            ),
        )
        started = await TeachingRepository(session).start_turn(
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=submitted,
        )
        turn_id = started.turn.id

        async def work() -> None:
            async with execution_budget_scope(
                session, started.turn, ExecutionLimits(active_seconds=0.2 if not cancel else 30)
            ):
                await provider_request(request())
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(work())
        if cancel:
            await entered.wait()
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else ExecutionBudgetError):
            await task
        await session.rollback()
    async with teaching_database() as after_restart:
        turn = await after_restart.get(TeachingTurn, turn_id)
        assert turn is not None
        status = budget_status(turn)
        assert status["provider_requests"] == 1
        assert status["active_used_seconds"] > 0
        assert status["state"] == ("cancelled" if cancel else "exhausted")
        assert turn.status is TeachingTurnStatus.FAILED
        assert "key" not in json.dumps(status).lower()
        assert turn.scientific_results_json["__initial_request"] == submitted.model_dump(
            mode="json"
        )
        assert turn.student_attempt is None
        assert not (
            await after_restart.scalars(
                select(LearningEvidence).where(
                    LearningEvidence.teaching_turn_id == turn_id,
                )
            )
        ).all()


async def test_hitl_budget_pauses_carries_forward_and_completed_replay_is_free(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seed = await _seed(session)
        staff = await _seed_staff(session, seed)
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seed.actor.course_id, seed.edition_id, found=False)
            ),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            enable_hitl=True,
        )
        original = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="Synthetic unclear concept",
            student_attempt="Synthetic committed answer",
            client_request_id="pause-budget",
        )
        paused = await graph.run(
            session=session,
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=original,
        )
        assert isinstance(paused, HitlInterruptResponse)
        turn = await session.get(TeachingTurn, paused.turn_id)
        assert turn is not None
        first_status = budget_status(turn)
        assert first_status["state"] == "waiting"
        # Simulate a long real teacher wait, not active execution.
        turn.execution_budget_json = {
            **turn.execution_budget_json,
            "wait_started_at": turn.execution_budget_json["wait_started_at"] - 3600,
        }
        await session.commit()
        decision = HitlResumeRequest(
            action=HitlAction.APPROVE,
            interrupt_id=paused.interrupt.interrupt_id,
            note="Synthetic teacher test decision; not classroom approval",
        )
        result = await graph.resume(
            session=session,
            actor=staff,
            curriculum_edition_id=seed.edition_id,
            conversation_id=paused.conversation_id,
            request=decision,
        )
        await session.refresh(turn)
        finished = budget_status(turn)
        assert finished["human_wait_seconds"] >= 3600
        assert finished["active_used_seconds"] < 5
        assert finished["active_used_seconds"] >= first_status["active_used_seconds"]
        assert finished["state"] == "finished"
        # Both exact first-turn and HITL retries read persisted snapshots for free.
        replay = await graph.run(
            session=session,
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=original,
        )
        repeated = await graph.resume(
            session=session,
            actor=staff,
            curriculum_edition_id=seed.edition_id,
            conversation_id=paused.conversation_id,
            request=decision,
        )
        assert replay.turn_id == result.turn_id == repeated.turn_id
        assert budget_status(turn) == finished
        assert len((await session.scalars(select(TeachingTurn))).all()) == 1
