"""Synthetic status recovery exercises real authorization, SQL and graph pauses."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.auth import hash_session_token
from quantum_agent.config import Settings
from quantum_agent.database import session_dependency
from quantum_agent.db_models import CourseMembership, CourseRole, MembershipStatus, UserSession
from quantum_agent.main import create_app
from quantum_agent.tutor.graph import TutorGraph
from tests.test_teaching_api import EmptyRetriever, _seed
from tests.test_teaching_api import teaching_api_database as teaching_api_database


async def test_lost_first_response_status_is_owner_scoped_and_has_no_answers(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        seeded = await _seed(session)
        peer = await _seed(session)
        peer_session = await session.scalar(select(UserSession).where(
            UserSession.session_token_sha256 == hash_session_token(peer.student_token)
        ))
        assert peer_session is not None
        session.add(CourseMembership(
            course_id=seeded.course_id, user_id=peer_session.user_id,
            role=CourseRole.STUDENT, status=MembershipStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        ))
        await session.commit()
    app = create_app(Settings(
        _env_file=None, ENVIRONMENT="test", DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USTC_API=None, NEO4J_PASSWORD=None,
    ))
    app.state.teaching_workflow = TutorGraph(
        evidence_retriever=EmptyRetriever(), model_gateway=None,
        checkpointer=InMemorySaver(), enable_hitl=True,
    )

    async def dependency() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = dependency
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}/teaching"
    key = str(uuid4())
    headers = {"Authorization": f"Bearer {seeded.student_token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"{base}/turns", headers=headers, json={
            "client_request_id": key, "mode": "learn_concepts", "message": "Fixture concept",
            "student_attempt": "PRIVATE first answer must not appear in status",
        })
        assert response.status_code == 202, response.text
        paused = response.json()
        path = f"{base}/requests/status?client_request_id={key}"
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers={
            "Authorization": f"Bearer {peer.student_token}"
        })).status_code == 404
        status = await client.get(path, headers=headers)
        assert status.status_code == 200, status.text
        data = status.json()
        assert data["conversation_id"] == paused["conversation_id"]
        assert data["turn_id"] == paused["turn_id"]
        assert data["recovery_action"] == "review_required"
        assert data["execution_budget"]["state"] == "waiting"
        assert data["execution_budget"]["human_wait_seconds"] >= 0
        assert "lease" not in data["execution_budget"]
        assert "PRIVATE" not in status.text and "proposed_response" not in status.text
        assert (await client.get(path.replace(str(seeded.edition_id), str(uuid4())),
                                 headers=headers)).status_code == 404
        rejected = await client.post(
            f"{base}/threads/{paused['conversation_id']}/resume",
            headers={"Authorization": f"Bearer {seeded.teacher_token}"},
            json={"interrupt_id": paused["interrupt"]["interrupt_id"], "action": "reject",
                  "note": "Synthetic test review; no real teacher approval"},
        )
        assert rejected.status_code == 200, rejected.text
        status = await client.get(path, headers=headers)
        assert status.json()["status"] == "failed"
        assert status.json()["recovery_action"] == "new_explicit_turn"
