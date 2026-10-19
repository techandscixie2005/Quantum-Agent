"""Synthetic provenance checks; these do not claim model or classroom efficacy."""

import asyncio
import json
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.db_models import TeachingMode, TeachingTurn
from quantum_agent.llm.gateway import FakeModelGateway, Message
from quantum_agent.llm.observability import turn_scope
from quantum_agent.llm.routing import ModelCapabilityRegistry, ModelRouter
from quantum_agent.teaching.course_packages import FINITE_BARRIERS
from quantum_agent.teaching.hitl import HitlAction, HitlInterruptResponse, HitlResumeRequest
from quantum_agent.teaching.models import TeachingTurnInput, TeachingTurnResult
from quantum_agent.tutor.graph import TutorGraph
from quantum_agent.versioning import (
    build_evidence_provenance,
    current_model_calls,
    record_model_call,
    version_scope,
)
from tests.test_model_routing import StrictOutput, _router_with_outcomes
from tests.test_tutor_graph import StaticRetriever, _packet, _seed, _seed_staff
from tests.test_tutor_graph import teaching_database as teaching_database


@pytest.mark.parametrize("revision,expected", [
    (None, "unknown"), ("branch-name", "unknown"), ("abc123", "unknown"),
    ("a" * 40, "a" * 40), ("b" * 64, "b" * 64),
])
def test_code_revision_is_explicit_and_content_is_traceable(
    monkeypatch: pytest.MonkeyPatch, revision: str | None, expected: str,
) -> None:
    if revision is None:
        monkeypatch.delenv("BUILD_REVISION", raising=False)
    else:
        monkeypatch.setenv("BUILD_REVISION", revision)
    packet = _packet(uuid4(), uuid4())
    package = FINITE_BARRIERS.reference().model_dump(mode="json")
    provenance = build_evidence_provenance(packet=packet, workflow_version="synthetic/1",
                                         course_package=package)
    assert provenance["code_revision"] == expected
    assert provenance["course_package"] == package
    assert provenance["content"][0]["document_version_id"] == str(
        packet.evidence[0].document_version_id)
    assert provenance["content"][0]["evidence_sha256"] == packet.evidence[0].evidence_sha256
    assert provenance["model_calls"] == []


async def test_router_records_attempted_aliases_and_outcomes_without_student_content() -> None:
    router, _, _ = _router_with_outcomes({
        "reasoning_primary": {"value": "invalid"}, "reasoning_second_pass": {"value": 7},
    })
    with turn_scope(uuid4(), uuid4()):
        output = await router.structured_generate(
            task="diagnose_student_progress",
            messages=[Message(role="user", content="PRIVATE SYNTHETIC STUDENT ANSWER")],
            output_type=StrictOutput,
        )
        calls = current_model_calls()
        assert output.value == 7
        assert [call["profile"] for call in calls] == [
            "reasoning_primary", "reasoning_second_pass",
        ]
        assert [call["outcome"] for call in calls] == ["failed", "completed"]
        assert all(call["model"] for call in calls)
        assert "PRIVATE SYNTHETIC STUDENT ANSWER" not in json.dumps(calls)
        calls[0]["model"] = "modified copy"
        assert current_model_calls()[0]["model"] != "modified copy"
    assert current_model_calls() == []


async def test_parallel_turn_version_scopes_are_isolated_and_bounded() -> None:
    async def run(name: str) -> list[dict[str, str]]:
        with version_scope():
            for _ in range(140):
                record_model_call(model=name, task="synthetic", profile="test", outcome="completed")
                await asyncio.sleep(0)
            return current_model_calls()

    first, second = await asyncio.gather(run("first"), run("second"))
    assert len(first) == len(second) == 128
    assert {call["model"] for call in first} == {"first"}
    assert {call["model"] for call in second} == {"second"}


async def test_interrupted_model_provenance_survives_resume_and_replay(
    teaching_database: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BUILD_REVISION", "a" * 40)
    async with teaching_database() as session:
        seeded = await _seed(session)
        staff = await _seed_staff(session, seeded)
        router = ModelRouter(registry=ModelCapabilityRegistry.ustc_default(),
                             gateway_factory=lambda _profile: FakeModelGateway())
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id, found=False)),
            model_gateway=router, checkpointer=InMemorySaver(), enable_hitl=True,
        )
        interrupted = await graph.run(session=session, actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS,
                message="Synthetic unsupported claim", student_attempt="Synthetic initial answer"))
        assert isinstance(interrupted, HitlInterruptResponse)
        turn = await session.get(TeachingTurn, interrupted.turn_id)
        assert turn is not None
        initial = turn.scientific_results_json["__provenance"]
        assert initial["model_calls"]
        assert initial["code_revision"] == "a" * 40
        decision = HitlResumeRequest(interrupt_id=interrupted.interrupt.interrupt_id,
            action=HitlAction.APPROVE, note="Synthetic review allows only a bounded prompt.")
        monkeypatch.setenv("BUILD_REVISION", "b" * 40)
        result = await graph.resume(session=session, actor=staff,
            curriculum_edition_id=seeded.edition_id,
            conversation_id=interrupted.conversation_id, request=decision)
        assert isinstance(result, TeachingTurnResult)
        await session.commit()
        persisted = turn.scientific_results_json["__provenance"]
        assert persisted["model_calls"] == initial["model_calls"]
        assert persisted["code_revision"] == "b" * 40
        assert [segment["code_revision"] for segment in persisted["execution_segments"]] == [
            "a" * 40, "b" * 40,
        ]
        monkeypatch.setenv("BUILD_REVISION", "c" * 40)
        replay = await graph.resume(session=session, actor=staff,
            curriculum_edition_id=seeded.edition_id,
            conversation_id=interrupted.conversation_id, request=decision)
        assert replay == result
        assert turn.scientific_results_json["__provenance"] == persisted
