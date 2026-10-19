"""Real SQL/graph pause discovery; all actors and decisions are synthetic fixtures."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.config import Settings
from quantum_agent.database import session_dependency
from quantum_agent.db_models import AgentTrace, CurriculumEdition, CurriculumEditionStatus
from quantum_agent.main import create_app
from quantum_agent.tutor.graph import TutorGraph
from tests.test_teaching_api import EmptyRetriever, _seed
from tests.test_teaching_api import teaching_api_database as teaching_api_database


async def test_first_turn_pending_queue_is_scoped_and_resolves_without_fabricated_trace(
    teaching_api_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_api_database() as session:
        first = await _seed(session)
        foreign = await _seed(session)
        other_edition = CurriculumEdition(
            course_id=first.course_id,
            edition_key="other-edition",
            title="Other edition",
            status=CurriculumEditionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        session.add(other_edition)
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
    app.state.teaching_workflow = TutorGraph(
        evidence_retriever=EmptyRetriever(),
        model_gateway=None,
        checkpointer=InMemorySaver(),
        enable_hitl=True,
    )

    async def dependency() -> AsyncIterator[AsyncSession]:
        async with teaching_api_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = dependency
    base = f"/api/v1/courses/{first.course_id}/editions/{first.edition_id}"
    foreign_base = f"/api/v1/courses/{foreign.course_id}/editions/{foreign.edition_id}"
    other_base = f"/api/v1/courses/{first.course_id}/editions/{other_edition.id}"
    teacher = {"Authorization": f"Bearer {first.teacher_token}"}
    student = {"Authorization": f"Bearer {first.student_token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        paused = []
        for index in range(2):
            response = await client.post(
                f"{base}/teaching/turns",
                headers=student,
                json={
                    "mode": "learn_concepts",
                    "message": "Synthetic unsupported concept",
                    "student_attempt": "Synthetic answer",
                    "client_request_id": f"pending-{index}",
                },
            )
            assert response.status_code == 202, response.text
            paused.append(response.json())
        for path, token in (
            (foreign_base, foreign.student_token),
            (other_base, first.student_token),
        ):
            response = await client.post(
                f"{path}/teaching/turns",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "mode": "learn_concepts",
                    "message": "Separate scoped pending review",
                    "student_attempt": "Synthetic answer",
                },
            )
            assert response.status_code == 202, response.text
        async with teaching_api_database() as session:
            assert await session.scalar(select(func.count(AgentTrace.id))) == 0
        assert (await client.get(f"{base}/teacher/pending-reviews")).status_code == 401
        assert (
            await client.get(f"{base}/teacher/pending-reviews", headers=student)
        ).status_code == 403
        assert (
            await client.get(f"{foreign_base}/teacher/pending-reviews", headers=teacher)
        ).status_code == 401
        response = await client.get(f"{base}/teacher/pending-reviews?limit=1", headers=teacher)
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 2 and page["has_more"]
        first_item = page["items"][0]
        assert first_item["conversation_id"] == paused[0]["conversation_id"]
        assert first_item["turn_id"] == paused[0]["turn_id"]
        assert first_item["interrupt_id"] == paused[0]["interrupt"]["interrupt_id"]
        assert first_item["student_display_name"] == "Student"
        assert first_item["status"] == "pending"
        assert "insufficient_coverage" in first_item["reasons"]
        assert "trace_id" not in first_item
        second_page = await client.get(
            f"{base}/teacher/pending-reviews?limit=1&offset=1", headers=teacher
        )
        assert not second_page.json()["has_more"]
        assert second_page.json()["items"][0]["turn_id"] == paused[1]["turn_id"]
        inspection = await client.get(
            f"{base}/teaching/threads/{first_item['conversation_id']}/interrupt", headers=teacher
        )
        assert inspection.status_code == 200
        resolved = await client.post(
            f"{base}/teaching/threads/{first_item['conversation_id']}/resume",
            headers=teacher,
            json={
                "action": "approve",
                "interrupt_id": first_item["interrupt_id"],
                "note": "Synthetic automated fixture decision; no actual teacher approval",
            },
        )
        assert resolved.status_code == 200, resolved.text
        remaining = await client.get(f"{base}/teacher/pending-reviews", headers=teacher)
        assert remaining.json()["total"] == 1
        assert remaining.json()["items"][0]["turn_id"] == paused[1]["turn_id"]
