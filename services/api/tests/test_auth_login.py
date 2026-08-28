"""Tests for the API-key login endpoint (PRD V3.1 §3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantum_agent.api.auth import router as auth_router
from quantum_agent.config import Settings
from quantum_agent.credential_router import CredentialScopedRouterFactory
from quantum_agent.credential_vault import (
    CredentialVault,
    MemoryCredentialVaultBackend,
)
from quantum_agent.database import session_dependency
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
    UserSession,
    UserStatus,
)
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.llm.routing import ModelCapabilityRegistry


async def _seed_login_account(
    session: AsyncSession,
    *,
    email: str,
) -> tuple[Course, CurriculumEdition, User]:
    user = User(
        email=email,
        display_name="Competition Login Student",
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
    return course, edition, user


@pytest.fixture
async def login_database(tmp_path: object) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _fernet_key() -> SecretStr:
    return SecretStr(Fernet.generate_key().decode("ascii"))


def _build_app(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    fernet_key: SecretStr | None,
    email: str = "demo-student@quantum-agent.local",
    environment: str = "development",
) -> FastAPI:
    app = FastAPI()
    settings = Settings(
        environment=environment,  # type: ignore[arg-type]
        session_vault_key=fernet_key,
        login_course_email=email,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    vault = (
        CredentialVault(
            backend=MemoryCredentialVaultBackend(),
            fernet_key=fernet_key,
        )
        if fernet_key is not None
        else None
    )
    app.state.credential_vault = vault
    app.state.credential_router_factory = CredentialScopedRouterFactory(
        registry=ModelCapabilityRegistry.ustc_default(),
        gateway_factory=lambda **_kwargs: FakeModelGateway(),
        fallback_router=None,
        vault=vault,
        base_url=settings.ustc_base_url,
    )

    async def app_session_dependency() -> AsyncSession:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[session_dependency] = app_session_dependency
    app.include_router(auth_router)
    return app


def _mock_probe_ok(*_args: object, **_kwargs: object) -> AsyncMock:
    response = AsyncMock()
    response.status_code = 200
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return client


def _mock_probe_unauthorized(*_args: object, **_kwargs: object) -> AsyncMock:
    response = AsyncMock()
    response.status_code = 401
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return client


async def test_login_returns_session_when_probe_succeeds(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    async with login_database() as session:
        course, edition, user = await _seed_login_account(session, email="demo-student@quantum-agent.local")
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    with patch("quantum_agent.api.auth.httpx.AsyncClient", side_effect=_mock_probe_ok):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"api_key": "sk-test-key-1234567890abcdef"},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["course_id"] == str(course.id)
    assert body["curriculum_edition_id"] == str(edition.id)
    assert body["user_id"] == str(user.id)
    assert "session_token" in body
    # The API key must never appear in the response body.
    assert "sk-test-key-1234567890abcdef" not in response.text


async def test_login_rejects_when_probe_fails(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    async with login_database() as session:
        await _seed_login_account(session, email="demo-student@quantum-agent.local")
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    with patch("quantum_agent.api.auth.httpx.AsyncClient", side_effect=_mock_probe_unauthorized):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"api_key": "sk-bad-key-1234567890abcdef"},
            )
    assert response.status_code == 401
    assert "sk-bad-key" not in response.text


async def test_login_409_when_account_not_seeded(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    with patch("quantum_agent.api.auth.httpx.AsyncClient", side_effect=_mock_probe_ok):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"api_key": "sk-test-key-1234567890abcdef"},
            )
    assert response.status_code == 409


async def test_login_rejects_short_key(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"api_key": "short"},
        )
    assert response.status_code == 422  # pydantic min_length=16


async def test_login_stores_key_in_vault(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    async with login_database() as session:
        await _seed_login_account(session, email="demo-student@quantum-agent.local")
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    vault = app.state.credential_vault
    assert vault is not None
    with patch("quantum_agent.api.auth.httpx.AsyncClient", side_effect=_mock_probe_ok):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"api_key": "sk-test-key-1234567890abcdef"},
            )
    assert response.status_code == 200
    # The vault should now have an entry for the new session_id.
    from quantum_agent.db_models import UserSession
    async with login_database() as session:
        from sqlalchemy import select
        user_session = (await session.execute(select(UserSession).limit(1))).scalar_one()
        loaded = await vault.load(user_session.id)
    assert loaded is not None
    assert loaded.get_secret_value() == "sk-test-key-1234567890abcdef"


async def test_login_validation_error_never_echoes_api_key(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    rejected_key = "sk-" + ("sensitive" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"api_key": rejected_key},
        )

    assert response.status_code == 422
    assert rejected_key not in response.text


async def test_login_fails_closed_when_session_vault_is_unavailable(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    async with login_database() as session:
        await _seed_login_account(session, email="demo-student@quantum-agent.local")
    app = _build_app(session_factory=login_database, fernet_key=None)

    with patch("quantum_agent.api.auth.httpx.AsyncClient", side_effect=_mock_probe_ok):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"api_key": "sk-session-only-key-1234567890"},
            )

    assert response.status_code == 503
    assert "sk-session-only" not in response.text


async def test_logout_evicts_vault_and_cached_router(
    login_database: async_sessionmaker[AsyncSession],
) -> None:
    async with login_database() as session:
        await _seed_login_account(session, email="demo-student@quantum-agent.local")
    app = _build_app(session_factory=login_database, fernet_key=_fernet_key())
    factory = app.state.credential_router_factory
    vault = app.state.credential_vault

    with patch("quantum_agent.api.auth.httpx.AsyncClient", side_effect=_mock_probe_ok):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"api_key": "sk-logout-key-1234567890abcdef"},
            )
            token = login.json()["session_token"]
            async with login_database() as session:
                user_session = (await session.execute(select(UserSession).limit(1))).scalar_one()
            assert await factory.router_for_session(user_session.id) is not None
            assert factory._routers

            logout = await client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )

    assert logout.status_code == 200
    assert await vault.load(user_session.id) is None
    assert not factory._routers
