"""Tests for the competition demo-account login endpoint (PRD V3.0 P1-4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantum_agent.api.auth import router as auth_router
from quantum_agent.config import Settings
from quantum_agent.db_models import (
    Base,
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    MembershipStatus,
    User,
    UserStatus,
)


async def _seed_demo_account(
    session: AsyncSession,
    *,
    email: str,
) -> tuple[Course, CurriculumEdition]:
    user = User(
        email=email,
        display_name="Competition Demo Student",
        system_role="user",
        status=UserStatus.ACTIVE,
    )
    course = Course(
        code=f"QA-{uuid4()}",
        title="Quantum Physics",
        status=CourseStatus.ACTIVE,
    )
    session.add_all([user, course])
    await session.flush()
    edition = CurriculumEdition(
        course_id=course.id,
        edition_key=f"edition-{uuid4()}",
        title="Quantum Physics Edition",
        status=CurriculumEditionStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )
    session.add(edition)
    await session.flush()
    membership = CourseMembership(
        course_id=course.id,
        user_id=user.id,
        role=CourseRole.STUDENT,
        status=MembershipStatus.ACTIVE,
        joined_at=datetime.now(UTC),
    )
    session.add(membership)
    await session.commit()
    return course, edition


@pytest.fixture
async def demo_database(tmp_path: object) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _build_app(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    secret: str | None,
    email: str = "demo-student@quantum-agent.local",
    environment: str = "development",
) -> FastAPI:
    app = FastAPI()
    settings = Settings(
        environment=environment,  # type: ignore[arg-type]
        demo_login_secret=SecretStr(secret) if secret else None,
        demo_login_course_email=email,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory

    async def session_dependency() -> AsyncSession:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[
        __import__(
            "quantum_agent.database", fromlist=["session_dependency"]
        ).session_dependency
    ] = session_dependency
    app.include_router(auth_router)
    return app


async def test_demo_login_refuses_when_secret_unset(
    demo_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(session_factory=demo_database, secret=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/demo-login",
            json={"secret": "whatever"},
        )
    assert response.status_code == 404


async def test_demo_login_refuses_in_production(
    demo_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(
        session_factory=demo_database,
        secret="super-secret-demo-key",
        environment="production",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/demo-login",
            json={"secret": "super-secret-demo-key"},
        )
    assert response.status_code == 404


async def test_demo_login_rejects_wrong_secret(
    demo_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(session_factory=demo_database, secret="super-secret-demo-key")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/demo-login",
            json={"secret": "wrong-secret-value"},
        )
    assert response.status_code == 401


async def test_demo_login_returns_session_when_seeded(
    demo_database: async_sessionmaker[AsyncSession],
) -> None:
    secret = "super-secret-demo-key"
    email = "demo-student@quantum-agent.local"
    async with demo_database() as session:
        course, edition = await _seed_demo_account(session, email=email)

    app = _build_app(session_factory=demo_database, secret=secret, email=email)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/demo-login",
            json={"secret": secret},
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data["session_token"], str)
    assert len(data["session_token"]) >= 32
    assert data["course_id"] == str(course.id)
    assert data["curriculum_edition_id"] == str(edition.id)
    assert data["display_name"] == "Competition Demo Student"
    assert data["expires_at"]


async def test_demo_login_409_when_account_not_seeded(
    demo_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(session_factory=demo_database, secret="super-secret-demo-key")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/demo-login",
            json={"secret": "super-secret-demo-key"},
        )
    assert response.status_code == 409
