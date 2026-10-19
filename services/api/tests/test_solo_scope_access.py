"""Synthetic cross-tab Solo bypass checks; no claim about external unaided work."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.api import teaching
from quantum_agent.auth import hash_session_token
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    CourseMembership,
    CourseRole,
    CurriculumEdition,
    MembershipStatus,
    TeachingConversation,
    TeachingMode,
    TeachingTurn,
    UserSession,
)
from quantum_agent.teaching.models import TeachingTurnInput
from quantum_agent.teaching.repository import TeachingConversationConflictError, TeachingRepository
from quantum_agent.tutor.graph import TutorGraph
from tests.test_teaching_api import _seed as _api_seed
from tests.test_teaching_api import teaching_api_database as teaching_api_database
from tests.test_tutor_graph import StaticRetriever, _packet, _seed
from tests.test_tutor_graph import teaching_database as teaching_database


@pytest.mark.parametrize("entry", ["new", "continuation", "replay", "other_edition"])
async def test_active_solo_blocks_other_episode_starts_and_replays_before_retrieval(
    teaching_database: async_sessionmaker[AsyncSession], entry: str,
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        retriever = StaticRetriever(_packet(seeded.actor.course_id, seeded.edition_id))
        graph = TutorGraph(evidence_retriever=retriever, model_gateway=None)
        request = TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS,
            message="Synthetic concept question", student_attempt="Synthetic initial answer",
            client_request_id="earlier-help")
        earlier = await graph.run(session=session, actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id, request=request)
        solo = TeachingConversation(course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id, student_user_id=seeded.actor.user_id,
            mode=TeachingMode.LEARN_CONCEPTS,
            learning_phase_json={"phase": "solo_active", "solo_assistance_locked": True})
        session.add(solo)
        edition_id = seeded.edition_id
        if entry == "other_edition":
            edition = CurriculumEdition(course_id=seeded.actor.course_id,
                                        edition_key="another", title="Another edition")
            session.add(edition)
            await session.flush()
            edition_id = edition.id
        await session.commit()
        if entry == "replay":
            attempted = request
        else:
            attempted = TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS,
                message="Synthetic request for help", student_attempt="Synthetic second answer",
                conversation_id=earlier.conversation_id if entry == "continuation" else None,
                client_request_id="attempted-bypass")
        retrievals = len(retriever.scopes)
        with pytest.raises(TeachingConversationConflictError, match="Solo is active"):
            await graph.run(session=session, actor=seeded.actor,
                curriculum_edition_id=edition_id, request=attempted)
        assert len(retriever.scopes) == retrievals
        assert await session.scalar(select(func.count(TeachingTurn.id))) == 1


async def test_first_turn_key_resolves_own_solo_retry_before_scope_guard(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        repository = TeachingRepository(session)
        request = TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS,
            message="Synthetic Solo arming request", client_request_id="lost-solo-response")
        first = await repository.start_turn(actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id, request=request)
        first.conversation.learning_phase_json = {
            "phase": "solo_active", "solo_assistance_locked": True,
        }
        # Old data can contain more than one active Solo. Own bounded
        # participation/exits must remain possible in either episode.
        session.add(TeachingConversation(course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id, student_user_id=seeded.actor.user_id,
            mode=TeachingMode.LEARN_CONCEPTS,
            learning_phase_json={"phase": "solo_active", "solo_assistance_locked": True}))
        await session.commit()
        replay = await repository.start_turn(actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id, request=request)
        assert replay.idempotent_replay
        assert replay.turn.id == first.turn.id


async def test_graph_rechecks_course_lock_after_a_workflow_commit(
    teaching_database: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        graph = TutorGraph(evidence_retriever=StaticRetriever(
            _packet(seeded.actor.course_id, seeded.edition_id)), model_gateway=None)
        original = graph._execute_graph

        async def arm_solo_after_execution(*args: Any, **kwargs: Any) -> Any:
            result = await original(*args, **kwargs)
            # Represents a node/HITL transaction releasing its lock while the
            # request remains in flight and another tab arms an independent task.
            await session.commit()
            async with teaching_database() as other_session:
                other_session.add(TeachingConversation(course_id=seeded.actor.course_id,
                    curriculum_edition_id=seeded.edition_id, student_user_id=seeded.actor.user_id,
                    mode=TeachingMode.LEARN_CONCEPTS,
                    learning_phase_json={"phase": "solo_active", "solo_assistance_locked": True}))
                await other_session.commit()
            return result

        monkeypatch.setattr(graph, "_execute_graph", arm_solo_after_execution)
        with pytest.raises(TeachingConversationConflictError, match="Solo is active"):
            await graph.run(session=session, actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS,
                    message="Synthetic question", student_attempt="Synthetic attempt"))


async def test_corrupt_own_solo_phase_does_not_reset_to_unrestricted_help(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        conversation = TeachingConversation(course_id=seeded.actor.course_id,
            curriculum_edition_id=seeded.edition_id, student_user_id=seeded.actor.user_id,
            mode=TeachingMode.LEARN_CONCEPTS,
            learning_phase_json={"phase": "solo_active", "solo_assistance_locked": True,
                                 "unexpected_corrupt_field": True})
        session.add(conversation)
        await session.commit()
        retriever = StaticRetriever(_packet(seeded.actor.course_id, seeded.edition_id))
        graph = TutorGraph(evidence_retriever=retriever, model_gateway=None)
        with pytest.raises(TeachingConversationConflictError, match="requires repair"):
            await graph.run(session=session, actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                request=TeachingTurnInput(conversation_id=conversation.id,
                    mode=TeachingMode.LEARN_CONCEPTS, message="Synthetic request for help"))
        assert retriever.scopes == []


async def test_http_solo_scope_blocks_other_edition_reads_resume_and_stream_but_not_staff_or_peers(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        seeded = await _api_seed(session)
        other = await _api_seed(session)
        student = await session.scalar(select(UserSession.user_id).where(
            UserSession.session_token_sha256 == hash_session_token(seeded.student_token)))
        other_student = await session.scalar(select(UserSession.user_id).where(
            UserSession.session_token_sha256 == hash_session_token(other.student_token)))
        assert student and other_student
        edition = CurriculumEdition(course_id=seeded.course_id,
                                    edition_key="other-edition", title="Other edition")
        session.add(edition)
        await session.flush()
        solo = TeachingConversation(course_id=seeded.course_id, curriculum_edition_id=edition.id,
            student_user_id=student, mode=TeachingMode.LEARN_CONCEPTS,
            learning_phase_json={"phase": "solo_active", "solo_assistance_locked": True})
        peer = TeachingConversation(course_id=seeded.course_id,
            curriculum_edition_id=seeded.edition_id, student_user_id=other_student,
            mode=TeachingMode.LEARN_CONCEPTS)
        other_course = TeachingConversation(course_id=other.course_id,
            curriculum_edition_id=other.edition_id, student_user_id=student,
            mode=TeachingMode.LEARN_CONCEPTS)
        session.add_all([solo, peer, other_course,
            CourseMembership(course_id=seeded.course_id, user_id=other_student,
                role=CourseRole.STUDENT, status=MembershipStatus.ACTIVE,
                joined_at=datetime.now(UTC)),
            CourseMembership(course_id=other.course_id, user_id=student,
                role=CourseRole.STUDENT, status=MembershipStatus.ACTIVE,
                joined_at=datetime.now(UTC))])
        await session.commit()
        # Arm Solo only after obtaining a genuine pending HITL episode below.
        solo.learning_phase_json = None
        await session.commit()
    app = FastAPI()
    app.include_router(teaching.router)
    app.state.teaching_workflow = TutorGraph(evidence_retriever=StaticRetriever(
        _packet(seeded.course_id, seeded.edition_id, found=False)),
        model_gateway=None, checkpointer=InMemorySaver(), enable_hitl=True)

    async def dependency() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = dependency
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}/teaching"
    student_headers = {"Authorization": f"Bearer {seeded.student_token}"}
    teacher_headers = {"Authorization": f"Bearer {seeded.teacher_token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url="http://test") as client:
        pending = await client.post(f"{base}/turns", headers=student_headers, json={
            "mode": "learn_concepts", "message": "Synthetic unsupported claim",
            "student_attempt": "Synthetic first answer"})
        assert pending.status_code == 202
        conversation_id = pending.json()["conversation_id"]
        async with teaching_api_database() as session:
            persisted = await session.get(TeachingConversation, solo.id)
            assert persisted
            persisted.learning_phase_json = {"phase": "solo_active", "solo_assistance_locked": True}
            await session.commit()
        for suffix in ("state", "state?review_stage=verify", "interrupt"):
            response = await client.get(f"{base}/threads/{conversation_id}/{suffix}",
                                        headers=student_headers)
            assert response.status_code == 409
        resumed = await client.post(f"{base}/threads/{conversation_id}/resume",
            headers=student_headers, json={"action": "confirm_transcription",
                "interrupt_id": pending.json()["interrupt"]["interrupt_id"],
                "confirmed_student_attempt": "Synthetic retry"})
        assert resumed.status_code == 409
        streamed = await client.post(f"{base}/turns/stream", headers=student_headers,
            json={"mode": "learn_concepts", "message": "Synthetic cross-tab help"})
        assert "workflow.failed" in streamed.text
        assert "workflow.completed" not in streamed.text
        assert (await client.get(f"{base}/threads/{conversation_id}/interrupt",
                                 headers=teacher_headers)).status_code == 200
        assert (await client.post(f"{base}/threads/{conversation_id}/resume",
            headers=teacher_headers, json={"action": "approve", "note": "Synthetic staff review",
                "interrupt_id": pending.json()["interrupt"]["interrupt_id"]})).status_code == 200
        assert (await client.get(f"{base}/threads/{peer.id}/state",
            headers={"Authorization": f"Bearer {other.student_token}"})).status_code == 200
        assert (await client.get(
            f"/api/v1/courses/{other.course_id}/editions/{other.edition_id}"
            f"/teaching/threads/{other_course.id}/state",
            headers=student_headers)).status_code == 200
        assert (await client.get(
            f"/api/v1/courses/{seeded.course_id}/editions/{edition.id}"
            f"/teaching/threads/{solo.id}/state", headers=student_headers)).status_code == 200
