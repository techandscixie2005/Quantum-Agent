from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from alembic.config import Config
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from quantum_agent.auth import hash_session_token, issue_opaque_session_token
from quantum_agent.config import Settings
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AnswerPolicy,
    AuditEventType,
    AuditLog,
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    MembershipStatus,
    SystemRole,
    TeachingConversation,
    TeachingConversationStatus,
    TeachingMode,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.knowledge.evidence_packets import EvidencePacket, RetrievalCoverage
from quantum_agent.knowledge.retrieval import RetrievalScope
from quantum_agent.main import create_app
from quantum_agent.teaching.state_machine import TeachingStateMachine
from quantum_agent.tutor.graph import TutorGraph

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
async def teaching_api_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "teaching-api.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class ApiSeed:
    def __init__(
        self,
        *,
        course_id: UUID,
        edition_id: UUID,
        student_token: str,
        teacher_token: str,
    ) -> None:
        self.course_id = course_id
        self.edition_id = edition_id
        self.student_token = student_token
        self.teacher_token = teacher_token


async def _seed(session: AsyncSession) -> ApiSeed:
    now = datetime.now(UTC)
    course = Course(
        code=f"API-{uuid4()}",
        title="Quantum Physics",
        status=CourseStatus.ACTIVE,
    )
    student = User(
        email=f"student-{uuid4()}@example.edu",
        display_name="Student",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    teacher = User(
        email=f"teacher-{uuid4()}@example.edu",
        display_name="Teacher",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add_all([course, student, teacher])
    await session.flush()
    edition = CurriculumEdition(
        course_id=course.id,
        edition_key="2026",
        title="Quantum Physics 2026",
        status=CurriculumEditionStatus.PUBLISHED,
        published_at=now,
    )
    session.add(edition)
    await session.flush()
    student_token = issue_opaque_session_token()
    teacher_token = issue_opaque_session_token()
    session.add_all(
        [
            UserSession(
                user_id=student.id,
                session_token_sha256=hash_session_token(student_token),
                expires_at=now + timedelta(hours=1),
            ),
            UserSession(
                user_id=teacher.id,
                session_token_sha256=hash_session_token(teacher_token),
                expires_at=now + timedelta(hours=1),
            ),
            CourseMembership(
                course_id=course.id,
                user_id=student.id,
                role=CourseRole.STUDENT,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            ),
            CourseMembership(
                course_id=course.id,
                user_id=teacher.id,
                role=CourseRole.TEACHER,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            ),
        ]
    )
    await session.commit()
    return ApiSeed(
        course_id=course.id,
        edition_id=edition.id,
        student_token=student_token,
        teacher_token=teacher_token,
    )


class EmptyRetriever:
    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        return EvidencePacket(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            query=query,
            coverage=RetrievalCoverage.NOT_FOUND,
        )


async def test_teaching_api_auth_stream_and_teacher_owned_policy(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        seeded = await _seed(session)

    app = create_app(
        Settings(
            _env_file=None,
            ENVIRONMENT="test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            USTC_API=None,
            NEO4J_PASSWORD=None,
        )
    )
    app.state.teaching_state_machine = TeachingStateMachine(
        evidence_retriever=EmptyRetriever(),
        model_gateway=None,
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}/teaching"
    student_headers = {"Authorization": f"Bearer {seeded.student_token}"}
    teacher_headers = {"Authorization": f"Bearer {seeded.teacher_token}"}
    payload = {"mode": "learn_concepts", "message": "解释一个课程概念。"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthenticated = await client.post(f"{base}/turns", json=payload)
        course_context = await client.get(
            "/api/v1/me/course-context",
            headers=student_headers,
        )
        turn = await client.post(f"{base}/turns", headers=student_headers, json=payload)
        student_policy_mutation = await client.put(
            f"{base}/answer-policies/review_derivations",
            headers=student_headers,
            json={
                "allow_full_solution": True,
                "minimum_attempts_for_scaffold": 1,
                "minimum_attempts_for_full_solution": 2,
                "max_hint_level": 3,
                "rationale": "Student must not be able to set this.",
            },
        )
        teacher_policy = await client.put(
            f"{base}/answer-policies/review_derivations",
            headers=teacher_headers,
            json={
                "allow_full_solution": True,
                "minimum_attempts_for_scaffold": 1,
                "minimum_attempts_for_full_solution": 2,
                "max_hint_level": 3,
                "rationale": "Require two observed derivation attempts.",
            },
        )
        read_policy = await client.get(
            f"{base}/answer-policies/review_derivations",
            headers=teacher_headers,
        )
        streamed = await client.post(
            f"{base}/turns/stream",
            headers=student_headers,
            json=payload,
        )

    assert unauthenticated.status_code == 401
    assert course_context.status_code == 200
    context_payload = course_context.json()
    assert context_payload["display_name"] == "Student"
    assert len(context_payload["courses"]) == 1
    assert context_payload["courses"][0] == {
        "course_id": str(seeded.course_id),
        "course_code": context_payload["courses"][0]["course_code"],
        "course_title": "Quantum Physics",
        "institution": "USTC",
        "role": "student",
        "curriculum_edition_id": str(seeded.edition_id),
        "edition_title": "Quantum Physics 2026",
        "academic_year": None,
        "term": None,
        "chapters": [],
    }
    assert turn.status_code == 200
    assert turn.json()["response"]["status"] == "insufficient_course_evidence"
    assert student_policy_mutation.status_code == 403
    assert teacher_policy.status_code == 200
    assert teacher_policy.json()["source"] == "teacher_configured"
    assert read_policy.status_code == 200
    assert read_policy.json()["minimum_attempts_for_full_solution"] == 2
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: workflow.started" in streamed.text
    assert "event: workflow.completed" in streamed.text

    async with teaching_api_database() as session:
        policy_count = await session.scalar(select(func.count(AnswerPolicy.id)))
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.event_type == AuditEventType.SETTINGS_CHANGED)
        )
    assert policy_count == 1
    assert audit is not None and audit.actor_user_id is not None


async def test_hitl_api_inspection_resume_and_role_authorization(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        seeded = await _seed(session)

    app = create_app(
        Settings(
            _env_file=None,
            ENVIRONMENT="test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            USTC_API=None,
            NEO4J_PASSWORD=None,
        )
    )
    app.state.teaching_workflow = TutorGraph(
        evidence_retriever=EmptyRetriever(),
        model_gateway=None,
        checkpointer=InMemorySaver(),
        enable_hitl=True,
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}"
    student_headers = {"Authorization": f"Bearer {seeded.student_token}"}
    teacher_headers = {"Authorization": f"Bearer {seeded.teacher_token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        paused = await client.post(
            f"{base}/teaching/turns",
            headers=student_headers,
            json={
                "mode": "learn_concepts",
                "message": "课程材料没有覆盖的内容是什么？",
            },
        )
        assert paused.status_code == 202
        paused_body = paused.json()
        conversation_id = paused_body["conversation_id"]
        interrupt_url = f"{base}/teaching/threads/{conversation_id}/interrupt"
        resume_url = f"{base}/teaching/threads/{conversation_id}/resume"

        student_inspection = await client.get(interrupt_url, headers=student_headers)
        student_approval = await client.post(
            resume_url,
            headers=student_headers,
            json={"action": "approve"},
        )
        teacher_inspection = await client.get(interrupt_url, headers=teacher_headers)
        approved = await client.post(
            resume_url,
            headers=teacher_headers,
            json={"action": "approve"},
        )
        trace_page = await client.get(
            f"{base}/teacher/agent-traces",
            headers=teacher_headers,
        )
        trace_id = trace_page.json()["items"][0]["id"]
        trace_detail = await client.get(
            f"{base}/teacher/agent-traces/{trace_id}",
            headers=teacher_headers,
        )

    assert student_inspection.status_code == 200
    assert student_approval.status_code == 403
    assert teacher_inspection.status_code == 200
    assert teacher_inspection.json()["artifacts"]["diagnosis"] is not None
    assert teacher_inspection.json()["artifacts"]["policy"]["source"] == "safe_default"
    assert approved.status_code == 200
    assert approved.json()["conversation_id"] == conversation_id
    assert approved.json()["response"]["status"] == "insufficient_course_evidence"
    assert trace_page.status_code == 200
    assert trace_page.json()["total"] == 1
    assert trace_detail.status_code == 200
    assert trace_detail.json()["diagnosis"] is not None
    assert trace_detail.json()["release_decision"] is not None
    assert len(trace_detail.json()["hitl_events"]) == 1


async def test_conversation_state_restores_durable_phase_after_refresh(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    """§13 refresh restoration: the state endpoint returns the last completed
    turn's persisted result snapshot (with learning_native) plus the durable
    phase, so a refreshed page re-renders the actionable surface from the
    backend.  Unknown conversations 404 — never a synthetic default.
    """
    async with teaching_api_database() as session:
        seeded = await _seed(session)

    app = create_app(
        Settings(
            _env_file=None,
            ENVIRONMENT="test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            USTC_API=None,
            NEO4J_PASSWORD=None,
        )
    )
    app.state.teaching_workflow = TutorGraph(
        evidence_retriever=EmptyRetriever(),
        model_gateway=None,
        checkpointer=InMemorySaver(),
        enable_hitl=False,
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}"
    student_headers = {"Authorization": f"Bearer {seeded.student_token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        turn = await client.post(
            f"{base}/teaching/turns",
            headers=student_headers,
            json={"mode": "learn_concepts", "message": "解释一个课程概念。"},
        )
        assert turn.status_code == 200
        conversation_id = turn.json()["conversation_id"]

        state = await client.get(
            f"{base}/teaching/threads/{conversation_id}/state",
            headers=student_headers,
        )
        missing = await client.get(
            f"{base}/teaching/threads/{uuid4()}/state",
            headers=student_headers,
        )
        unauthenticated = await client.get(
            f"{base}/teaching/threads/{conversation_id}/state",
        )

    assert state.status_code == 200
    state_body = state.json()
    assert state_body["conversation_id"] == conversation_id
    assert state_body["mode"] == "learn_concepts"
    assert state_body["status"] == "active"
    assert state_body["turn_id"] == turn.json()["turn_id"]
    # The first turn fires the commitment gate, so the durable phase is
    # commitment_required (not open) — the refreshed page must re-render
    # the commitment card, not silently reset to OPEN.
    assert state_body["durable_phase"]["phase"] == "commitment_required"
    snapshot = state_body["result"]
    assert snapshot is not None
    assert snapshot["learning_native"] is not None
    assert snapshot["learning_native"]["phase"] == "commitment_required"
    assert snapshot["conversation_id"] == conversation_id
    # The restored snapshot must be exactly the persisted last-turn result.
    assert snapshot["response"] == turn.json()["response"]
    assert snapshot["policy"] == turn.json()["policy"]
    assert missing.status_code == 404
    assert unauthenticated.status_code == 401


async def test_conversation_state_redacts_transfer_oracle(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    """The state endpoint must never leak the transfer oracle to the student.

    ``durable_phase.transfer_verification.expected_value`` holds the
    numerically correct transmission coefficient the student must derive
    themselves during Solo Mode.  A student who reads the raw
    ``/state`` payload (browser devtools) could copy it into the solo
    attempt and close the loop with zero physics done.  The redacted
    payload must show ``transfer_verification: null`` even when the
    persisted durable phase carries a live oracle.
    """
    async with teaching_api_database() as session:
        seeded = await _seed(session)
        student_user_id = await session.scalar(
            select(User.id).where(
                User.id.in_(
                    select(CourseMembership.user_id).where(
                        CourseMembership.course_id == seeded.course_id,
                        CourseMembership.role == CourseRole.STUDENT,
                    )
                )
            )
        )
        conversation = TeachingConversation(
            id=uuid4(),
            course_id=seeded.course_id,
            curriculum_edition_id=seeded.edition_id,
            student_user_id=student_user_id,
            status=TeachingConversationStatus.ACTIVE,
            mode=TeachingMode.REVIEW_DERIVATIONS,
            title="solo oracle redaction",
            learning_phase_json={
                "phase": "solo_active",
                "loop_required": True,
                "solo_assistance_locked": True,
                "transfer_verification": {
                    "scientific_request": {"metric": "transmission"},
                    "metric_name": "transmission_coefficient",
                    "expected_value": 0.0718,
                    "absolute_tolerance": 0.005,
                },
            },
        )
        session.add(conversation)
        await session.commit()

    app = create_app(
        Settings(
            _env_file=None,
            ENVIRONMENT="test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            USTC_API=None,
            NEO4J_PASSWORD=None,
        )
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}"
    student_headers = {"Authorization": f"Bearer {seeded.student_token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        state = await client.get(
            f"{base}/teaching/threads/{conversation.id}/state",
            headers=student_headers,
        )

    assert state.status_code == 200
    durable_phase = state.json()["durable_phase"]
    assert durable_phase["phase"] == "solo_active"
    assert durable_phase["solo_assistance_locked"] is True
    # The oracle answer is the attack: the student-facing payload must not
    # contain the expected value, its metric contract, or any key of the
    # verification spec — while every non-oracle field stays intact.
    assert durable_phase["transfer_verification"] is None
    assert "expected_value" not in json.dumps(state.json())
    assert "metric_name" not in json.dumps(state.json())
