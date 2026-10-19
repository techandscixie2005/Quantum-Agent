"""Automated export/isolation checks with synthetic answers, never classroom data."""

import hashlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.api import learning_records
from quantum_agent.auth import hash_session_token, issue_opaque_session_token
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    CourseMembership,
    CourseRole,
    LearningEvidence,
    LearningEvidenceKind,
    MembershipStatus,
    TeachingConversation,
    TeachingMode,
    TeachingReview,
    TeachingTurn,
    TeachingTurnStatus,
    User,
    UserSession,
    UserStatus,
)
from tests.test_teaching_api import _seed
from tests.test_teaching_api import teaching_api_database as teaching_api_database


async def _client(factory: async_sessionmaker[AsyncSession]) -> AsyncClient:
    app = FastAPI()
    app.include_router(learning_records.router)

    async def dependency() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[session_dependency] = dependency
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _episode(
    session: AsyncSession,
    course: UUID,
    edition: UUID,
    student: UUID,
) -> tuple[TeachingConversation, list[TeachingTurn]]:
    conversation = TeachingConversation(
        course_id=course,
        curriculum_edition_id=edition,
        student_user_id=student,
        mode=TeachingMode.RUN_EXPERIMENTS,
    )
    session.add(conversation)
    await session.flush()
    turns = [
        TeachingTurn(
            conversation_id=conversation.id,
            sequence_number=i,
            user_message=f"Synthetic question {i}",
            student_attempt=f"Synthetic answer {i}",
            status=TeachingTurnStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            response_json={"next_question": f"Synthetic intervention {i}"},
            scientific_results_json={
                "__provenance": {
                    "code_revision": "a" * 40,
                    "model_calls": [{"model": "test-model"}],
                }
            },
        )
        for i in (1, 2)
    ]
    session.add_all(turns)
    await session.flush()
    session.add(
        LearningEvidence(
            teaching_turn_id=turns[0].id,
            course_id=course,
            curriculum_edition_id=edition,
            student_user_id=student,
            kind=LearningEvidenceKind.STUDENT_ATTEMPT,
            observation="Synthetic initial answer",
            evidence_json={"response": "first"},
        )
    )
    return conversation, turns


async def test_export_links_answers_interventions_and_attributed_decisions_and_isolates_accounts(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        seed = await _seed(session)
        student = await session.scalar(
            select(UserSession.user_id).where(
                UserSession.session_token_sha256 == hash_session_token(seed.student_token)
            )
        )
        teacher = await session.scalar(
            select(UserSession.user_id).where(
                UserSession.session_token_sha256 == hash_session_token(seed.teacher_token)
            )
        )
        assert student and teacher
        conversation, turns = await _episode(session, seed.course_id, seed.edition_id, student)
        session.add(
            TeachingReview(
                course_id=seed.course_id,
                curriculum_edition_id=seed.edition_id,
                conversation_id=conversation.id,
                source_turn_id=turns[1].id,
                student_user_id=student,
                reviewer_user_id=teacher,
                decision="needs_follow_up",
                reason="Synthetic teacher reason",
                follow_up="request_revision",
                probe="Explain the boundary conditions",
                rubric_json={},
            )
        )
        other = User(
            email=f"other-{uuid4()}@example.edu",
            display_name="Other synthetic student",
            status=UserStatus.ACTIVE,
        )
        session.add(other)
        await session.flush()
        token = issue_opaque_session_token()
        session.add_all(
            [
                CourseMembership(
                    course_id=seed.course_id,
                    user_id=other.id,
                    role=CourseRole.STUDENT,
                    status=MembershipStatus.ACTIVE,
                    joined_at=datetime.now(UTC),
                ),
                UserSession(
                    user_id=other.id,
                    session_token_sha256=hash_session_token(token),
                    expires_at=datetime(2099, 1, 1, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()
    path = (
        f"/api/v1/courses/{seed.course_id}/editions/{seed.edition_id}"
        f"/learning-records/{conversation.id}/export"
    )
    async with await _client(teaching_api_database) as client:
        assert (await client.get(path)).status_code == 401
        assert (
            await client.get(path, headers={"Authorization": f"Bearer {token}"})
        ).status_code == 404
        assert (
            await client.get(
                path.replace(str(seed.edition_id), str(uuid4())),
                headers={"Authorization": f"Bearer {seed.teacher_token}"},
            )
        ).status_code == 404
        response = await client.get(path, headers={"Authorization": f"Bearer {seed.student_token}"})
        assert response.status_code == 200
        assert "no-store" in response.headers["cache-control"]
        exported = response.json()
        record = exported["record"]
        assert [turn["student_answer"] for turn in record["turns"]] == [
            "Synthetic answer 1",
            "Synthetic answer 2",
        ]
        assert record["events"][0]["turn_id"] == str(turns[0].id)
        assert record["teacher_decisions"][0]["source_turn_id"] == str(turns[1].id)
        assert record["teacher_decisions"][0]["reason"] == "Synthetic teacher reason"
        assert record["semantics"]["classroom_outcomes"] == "not_established_by_this_export"
        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode()).hexdigest() == exported["record_sha256"]
        assert (
            await client.get(path, headers={"Authorization": f"Bearer {seed.teacher_token}"})
        ).status_code == 200
        async with teaching_api_database() as session:
            stored = await session.get(TeachingConversation, conversation.id)
            assert stored
            stored.learning_phase_json = {"phase": "solo_active", "solo_assistance_locked": True}
            await session.commit()
        assert (
            await client.get(path, headers={"Authorization": f"Bearer {seed.student_token}"})
        ).status_code == 409
        assert (
            await client.get(path, headers={"Authorization": f"Bearer {seed.teacher_token}"})
        ).status_code == 200


async def test_export_rejects_budget_overflow_instead_of_silent_truncation(
    teaching_api_database: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with teaching_api_database() as session:
        seed = await _seed(session)
        student = await session.scalar(
            select(UserSession.user_id).where(
                UserSession.session_token_sha256 == hash_session_token(seed.student_token)
            )
        )
        assert student
        conversation, _ = await _episode(session, seed.course_id, seed.edition_id, student)
        await session.commit()
    monkeypatch.setattr(learning_records, "MAX_EXPORT_TURNS", 1)
    async with await _client(teaching_api_database) as client:
        response = await client.get(
            f"/api/v1/courses/{seed.course_id}/editions/{seed.edition_id}"
            f"/learning-records/{conversation.id}/export",
            headers={"Authorization": f"Bearer {seed.student_token}"},
        )
    assert response.status_code == 413


@pytest.mark.parametrize("legacy", [False, True])
async def test_rejected_hitl_reason_survives_export_without_agent_trace(
    teaching_api_database: async_sessionmaker[AsyncSession], legacy: bool,
) -> None:
    from quantum_agent.teaching.hitl import (
        HitlAction,
        HitlEvent,
        HitlReason,
        HitlResolution,
        HitlResumeRequest,
        build_interrupt_payload,
    )

    async with teaching_api_database() as session:
        seed = await _seed(session)
        student = await session.scalar(select(UserSession.user_id).where(
            UserSession.session_token_sha256 == hash_session_token(seed.student_token)))
        teacher = await session.scalar(select(UserSession.user_id).where(
            UserSession.session_token_sha256 == hash_session_token(seed.teacher_token)))
        assert student and teacher
        conversation, _ = await _episode(session, seed.course_id, seed.edition_id, student)
        rejected = TeachingTurn(
            conversation_id=conversation.id, sequence_number=3,
            user_message="Synthetic unsupported claim", student_attempt="Synthetic first answer",
            status=TeachingTurnStatus.FAILED, failure_code="HITL_REJECTED",
            completed_at=datetime.now(UTC),
        )
        session.add(rejected)
        await session.flush()
        payload = build_interrupt_payload(conversation_id=conversation.id, turn_id=rejected.id,
                                          reasons=(HitlReason.INSUFFICIENT_COVERAGE,))
        resolution = HitlResolution.authenticated(payload=payload,
            request=HitlResumeRequest(action=HitlAction.REJECT,
                                     note="Synthetic reviewer requires authoritative evidence."),
            actor_user_id=teacher, actor_role=CourseRole.TEACHER)
        event = HitlEvent(interrupt=payload, resolution=resolution).model_dump(mode="json")
        if legacy:
            rejected.validation_json = {"hitl": event}
        else:
            rejected.scientific_results_json = {"__hitl_decisions": {
                str(payload.interrupt_id): event,
            }}
        await session.commit()
    async with await _client(teaching_api_database) as client:
        response = await client.get(
            f"/api/v1/courses/{seed.course_id}/editions/{seed.edition_id}"
            f"/learning-records/{conversation.id}/export",
            headers={"Authorization": f"Bearer {seed.teacher_token}"})
    assert response.status_code == 200
    turn = response.json()["record"]["turns"][2]
    assert turn["trace_id"] is None
    assert turn["hitl_decisions"] == [event]
    assert turn["hitl_decisions"][0]["resolution"]["actor_user_id"] == str(teacher)
    assert turn["provenance"]["code_revision"] == "unknown"


async def test_export_does_not_materialize_unexported_snapshots_and_enforces_utf8_byte_budget(
    teaching_api_database: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with teaching_api_database() as session:
        seed = await _seed(session)
        student = await session.scalar(select(UserSession.user_id).where(
            UserSession.session_token_sha256 == hash_session_token(seed.student_token)))
        assert student
        conversation, turns = await _episode(session, seed.course_id, seed.edition_id, student)
        turns[0].scientific_results_json = {"__result_snapshot": {"unexported": "x" * 100_000}}
        await session.commit()
    path = (f"/api/v1/courses/{seed.course_id}/editions/{seed.edition_id}"
            f"/learning-records/{conversation.id}/export")
    monkeypatch.setattr(learning_records, "MAX_EXPORT_BYTES", 10_000)
    async with await _client(teaching_api_database) as client:
        response = await client.get(path, headers={"Authorization": f"Bearer {seed.student_token}"})
        assert response.status_code == 200
        assert "unexported" not in response.text
        async with teaching_api_database() as session:
            stored = await session.get(TeachingTurn, turns[0].id)
            assert stored
            stored.response_json = {"synthetic_unicode": "科学" * 5000}
            await session.commit()
        response = await client.get(path, headers={"Authorization": f"Bearer {seed.student_token}"})
        assert response.status_code == 413
        assert "record" not in response.json()


async def test_export_stops_serialization_and_closes_cursor_on_byte_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import Any

    from fastapi import HTTPException

    read = 0
    closed = False

    async def records() -> AsyncGenerator[dict[str, Any], None]:
        nonlocal read, closed
        try:
            for _ in range(1000):
                read += 1
                yield {"synthetic": "科学" * 100}
        finally:
            closed = True

    monkeypatch.setattr(learning_records, "MAX_EXPORT_BYTES", 300)
    with pytest.raises(HTTPException) as caught:
        await learning_records._serialize_export({}, {"turns": (records(), 1000)})
    assert caught.value.status_code == 413
    assert read == 1
    assert closed


async def test_export_byte_budget_includes_utf8_and_checksum_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import Any

    from fastapi import HTTPException

    async def records() -> AsyncGenerator[dict[str, Any], None]:
        yield {"synthetic": "科学", "answer": "Initial answer"}

    metadata = {"semantics": {"source": "automated_fixture"}}
    first = await learning_records._serialize_export(metadata, {"turns": (records(), 1)})
    monkeypatch.setattr(learning_records, "MAX_EXPORT_BYTES", len(first))
    assert await learning_records._serialize_export(metadata, {"turns": (records(), 1)}) == first
    exported = json.loads(first)
    canonical = json.dumps(exported["record"], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == exported["record_sha256"]
    monkeypatch.setattr(learning_records, "MAX_EXPORT_BYTES", len(first) - 1)
    with pytest.raises(HTTPException) as caught:
        await learning_records._serialize_export(metadata, {"turns": (records(), 1)})
    assert caught.value.status_code == 413


async def test_cross_course_teacher_cannot_read_or_substitute_an_episode_scope(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        original = await _seed(session)
        other = await _seed(session)
        student = await session.scalar(select(UserSession.user_id).where(
            UserSession.session_token_sha256 == hash_session_token(original.student_token)))
        assert student
        conversation, _ = await _episode(session, original.course_id, original.edition_id, student)
        await session.commit()
    path = (f"/api/v1/courses/{original.course_id}/editions/{original.edition_id}"
            f"/learning-records/{conversation.id}/export")
    async with await _client(teaching_api_database) as client:
        response = await client.get(
            path, headers={"Authorization": f"Bearer {other.teacher_token}"})
        assert response.status_code == 401
        forged = path.replace(str(original.course_id), str(other.course_id)).replace(
            str(original.edition_id), str(other.edition_id))
        response = await client.get(
            forged, headers={"Authorization": f"Bearer {other.teacher_token}"})
        assert response.status_code == 404
