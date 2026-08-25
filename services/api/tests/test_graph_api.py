from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantum_agent.api.graph import router
from quantum_agent.auth import hash_session_token, issue_opaque_session_token
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    Base,
    Course,
    CourseMembership,
    CourseRole,
    MembershipStatus,
    SessionStatus,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.knowledge.explorer import (
    ConceptSearchResponse,
    PrerequisitePathsResponse,
    StudentSubgraphResponse,
)
from quantum_agent.knowledge.retrieval import RetrievalScope


@pytest.fixture
async def api_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_student(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, UUID]:
    token = issue_opaque_session_token()
    now = datetime.now(UTC)
    async with session_factory() as session:
        user = User(
            email=f"student-{uuid4()}@example.edu",
            display_name="Quantum student",
            status=UserStatus.ACTIVE,
        )
        course = Course(code=f"QPHY-{uuid4()}", title="Quantum Physics")
        session.add_all([user, course])
        await session.flush()
        session.add_all(
            [
                CourseMembership(
                    course_id=course.id,
                    user_id=user.id,
                    role=CourseRole.STUDENT,
                    status=MembershipStatus.ACTIVE,
                    joined_at=now,
                ),
                UserSession(
                    user_id=user.id,
                    session_token_sha256=hash_session_token(token),
                    status=SessionStatus.ACTIVE,
                    expires_at=now + timedelta(hours=1),
                ),
            ]
        )
        await session.commit()
        return token, course.id


class RecordingExplorer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RetrievalScope, object]] = []

    async def search_concepts(
        self,
        scope: RetrievalScope,
        query: str,
        *,
        limit: int = 20,
    ) -> ConceptSearchResponse:
        if not query.strip():
            raise ValueError("query must not be blank")
        self.calls.append(("search", scope, (query, limit)))
        return ConceptSearchResponse(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            query=query,
        )

    async def subgraph(
        self,
        scope: RetrievalScope,
        root_candidate_id: UUID,
        *,
        max_depth: int = 2,
        limit: int = 100,
    ) -> StudentSubgraphResponse:
        self.calls.append(("subgraph", scope, (root_candidate_id, max_depth, limit)))
        return StudentSubgraphResponse(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            root_candidate_id=root_candidate_id,
            root_visible=False,
        )

    async def prerequisite_paths(
        self,
        scope: RetrievalScope,
        target_candidate_id: UUID,
        *,
        max_depth: int = 4,
        limit: int = 20,
    ) -> PrerequisitePathsResponse:
        self.calls.append(
            ("prerequisites", scope, (target_candidate_id, max_depth, limit))
        )
        return PrerequisitePathsResponse(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            target_candidate_id=target_candidate_id,
        )


def build_test_app(
    session_factory: async_sessionmaker[AsyncSession],
    explorer: RecordingExplorer | None,
) -> FastAPI:
    app = FastAPI()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    if explorer is not None:
        app.state.graph_explorer = explorer
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_active_student_can_use_all_scoped_graph_endpoints(
    api_database: async_sessionmaker[AsyncSession],
) -> None:
    token, course_id = await seed_student(api_database)
    edition_id = uuid4()
    candidate_id = uuid4()
    explorer = RecordingExplorer()
    app = build_test_app(api_database, explorer)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/courses/{course_id}/editions/{edition_id}/graph"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        search = await client.get(
            f"{base}/concepts/search",
            headers=headers,
            params={"q": "波函数%' OR true --", "limit": 7},
        )
        subgraph = await client.get(
            f"{base}/nodes/{candidate_id}/subgraph",
            headers=headers,
            params={"max_depth": 3, "limit": 40},
        )
        prerequisites = await client.get(
            f"{base}/nodes/{candidate_id}/prerequisites",
            headers=headers,
            params={"max_depth": 5, "limit": 9},
        )

    assert search.status_code == 200
    assert subgraph.status_code == 200
    assert prerequisites.status_code == 200
    expected_scope = RetrievalScope(course_id=course_id, curriculum_edition_id=edition_id)
    assert all(call[1] == expected_scope for call in explorer.calls)
    assert explorer.calls[0][2] == ("波函数%' OR true --", 7)
    assert explorer.calls[1][2] == (candidate_id, 3, 40)
    assert explorer.calls[2][2] == (candidate_id, 5, 9)


@pytest.mark.asyncio
async def test_router_authenticates_before_exposing_graph_or_service_state(
    api_database: async_sessionmaker[AsyncSession],
) -> None:
    token, course_id = await seed_student(api_database)
    edition_id = uuid4()
    app = build_test_app(api_database, None)
    base = f"/api/v1/courses/{course_id}/editions/{edition_id}/graph/concepts/search"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthenticated = await client.get(base, params={"q": "波函数"})
        unavailable = await client.get(
            base,
            params={"q": "波函数"},
            headers={"Authorization": f"Bearer {token}"},
        )
        wrong_course = await client.get(
            base.replace(str(course_id), str(uuid4())),
            params={"q": "波函数"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert unauthenticated.status_code == 401
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "Graph explorer is unavailable"}
    assert wrong_course.status_code == 401


@pytest.mark.asyncio
async def test_blank_search_is_rejected_after_course_authentication(
    api_database: async_sessionmaker[AsyncSession],
) -> None:
    token, course_id = await seed_student(api_database)
    explorer = RecordingExplorer()
    app = build_test_app(api_database, explorer)
    path = (
        f"/api/v1/courses/{course_id}/editions/{uuid4()}"
        "/graph/concepts/search"
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            path,
            params={"q": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
    assert explorer.calls == []
