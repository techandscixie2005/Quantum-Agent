"""Offline identity and authorization tests; provider probes are test doubles."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import quantum_agent.api.auth as auth_api
from quantum_agent.api.course_context import router as context_router
from quantum_agent.auth import (
    TEACHER_ROLES,
    SessionCredential,
    authenticate_course_actor,
    hash_session_token,
)
from quantum_agent.classroom import provision_classroom_access
from quantum_agent.cli import _classroom_access_async, build_parser
from quantum_agent.config import Settings
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
from tests.test_auth_login import _build_app, _fernet_key, _seed_login_account

_SHARED_PROVIDER_KEY = "sk-TEST-DOUBLE-shared-provider-key-1234567890"


@pytest.fixture
async def classroom_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _app(factory: async_sessionmaker[AsyncSession], *, production: bool = False) -> FastAPI:
    app = _build_app(session_factory=factory, fernet_key=_fernet_key())
    app.state.settings = app.state.settings.model_copy(update={
        "allow_shared_demo_login": False,
        "environment": "production" if production else "test",
    })
    app.include_router(context_router)
    return app


async def _issue(
    factory: async_sessionmaker[AsyncSession], course_id: UUID, *,
    email: str = "student-a@example.edu", role: CourseRole = CourseRole.STUDENT,
) -> dict[str, str]:
    async with factory() as session:
        payload = await provision_classroom_access(
            session, email=email, display_name=email.split("@")[0],
            course_id=course_id, role=role,
        )
        await session.commit()
        return payload


async def _login(
    client: AsyncClient, token: str | None = None, *, course_id: UUID | None = None,
) -> Response:
    # Use a distinct simulated client address so authentication tests exercise
    # policy without sharing the process-local login-rate counter.
    body = {"api_key": _SHARED_PROVIDER_KEY}
    if token is not None:
        body["classroom_access_token"] = token
    if course_id is not None:
        body["course_id"] = str(course_id)
    return await client.post(
        "/api/v1/auth/login", json=body, headers={"x-forwarded-for": str(uuid4())},
    )


async def _course(factory: async_sessionmaker[AsyncSession]) -> Course:
    async with factory() as session:
        course, _, _ = await _seed_login_account(session, email=f"fixture-{uuid4()}@example.edu")
        return course


async def test_shared_provider_key_never_merges_named_learning_identities(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    alice = await _issue(classroom_database, course.id)
    bob = await _issue(classroom_database, course.id, email="student-b@example.edu")
    app = _app(classroom_database)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=AsyncMock(return_value=True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await _login(client, alice["classroom_access_token"], course_id=course.id)
            second = await _login(client, bob["classroom_access_token"], course_id=course.id)
    assert first.status_code == second.status_code == 200
    assert first.json()["user_id"] == alice["user_id"]
    assert second.json()["user_id"] == bob["user_id"]
    assert first.json()["user_id"] != second.json()["user_id"]
    assert first.json()["session_token"] != second.json()["session_token"]
    assert _SHARED_PROVIDER_KEY not in first.text + second.text


async def test_classroom_burst_with_no_forwarded_ip_has_per_invitation_budgets(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    invitations = [await _issue(classroom_database, course.id, email=f"burst-{i}@example.edu")
                   for i in range(12)]
    app = _app(classroom_database)
    probe = AsyncMock(return_value=True)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=probe):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = []
            for invitation in invitations:
                response = await client.post("/api/v1/auth/login", json={
                    "api_key": _SHARED_PROVIDER_KEY,
                    "classroom_access_token": invitation["classroom_access_token"],
                })
                statuses.append(response.status_code)
    assert statuses == [200] * 12
    assert probe.await_count == 12
    assert all(item["classroom_access_token"] not in auth_api._login_attempts
               for item in invitations)


async def test_rejected_provider_keys_exhaust_only_the_valid_invitation_budget(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    app = _app(classroom_database)
    probe = AsyncMock(return_value=False)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=probe):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = [(await _login(client, access["classroom_access_token"])).status_code
                        for _ in range(11)]
    assert statuses == [401] * 10 + [429]
    assert probe.await_count == 10


async def test_fabricated_invitation_digests_share_coarse_guessing_quota(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    app = _app(classroom_database)
    probe = AsyncMock(return_value=True)
    headers = {"x-forwarded-for": f"invalid-tokens-{uuid4()}"}
    with patch("quantum_agent.api.auth._probe_ustc_key", new=probe):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = []
            for _ in range(11):
                response = await client.post("/api/v1/auth/login", json={
                    "api_key": _SHARED_PROVIDER_KEY, "classroom_access_token": uuid4().hex * 2,
                }, headers=headers)
                statuses.append(response.status_code)
    assert statuses == [401] * 10 + [429]
    probe.assert_not_awaited()


def test_backend_rate_buckets_have_a_hard_memory_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_api, "_LOGIN_RATE_MAX_BUCKETS", 2)
    # Use a defaultdict as production does; retain active quota on exhaustion.
    from collections import defaultdict
    monkeypatch.setattr(auth_api, "_login_attempts", defaultdict(list))
    auth_api._check_rate_limit("first")
    auth_api._check_rate_limit("second")
    with pytest.raises(HTTPException) as exhausted:
        auth_api._check_rate_limit("third")
    assert exhausted.value.status_code == 429
    assert len(auth_api._login_attempts) == 2
    assert auth_api._login_attempts["first"]
    for bucket in auth_api._login_attempts:
        auth_api._login_attempts[bucket] = [0.0]
    auth_api._check_rate_limit("after-expiry")
    assert set(auth_api._login_attempts) == {"after-expiry"}


@pytest.mark.parametrize("demo_opt_in", [False, True])
async def test_provider_key_alone_is_denied_by_default_and_in_production(
    classroom_database: async_sessionmaker[AsyncSession], demo_opt_in: bool,
) -> None:
    await _course(classroom_database)
    app = _app(classroom_database, production=demo_opt_in)
    app.state.settings = app.state.settings.model_copy(
        update={"allow_shared_demo_login": demo_opt_in},
    )
    probe = AsyncMock(return_value=True)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=probe):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _login(client)
    assert response.status_code == 401
    probe.assert_not_awaited()
    assert Settings(_env_file=None).allow_shared_demo_login is False


async def test_production_can_exchange_individual_teacher_roster_identity(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    teacher = await _issue(
        classroom_database, course.id, email="teacher@example.edu", role=CourseRole.TEACHER,
    )
    app = _app(classroom_database, production=True)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=AsyncMock(return_value=True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _login(client, teacher["classroom_access_token"])
    assert response.status_code == 200
    async with classroom_database() as session:
        actor = await authenticate_course_actor(
            session, credential=SessionCredential(token=response.json()["session_token"]),
            course_id=course.id, allowed_roles=TEACHER_ROLES,
        )
    assert str(actor.user_id) == teacher["user_id"]
    assert actor.course_role is CourseRole.TEACHER


async def test_consumed_classroom_token_cannot_be_exchanged_again(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    app = _app(classroom_database)
    probe = AsyncMock(return_value=True)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=probe):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await _login(client, access["classroom_access_token"])
            second = await _login(client, access["classroom_access_token"])
    assert first.status_code == 200
    assert second.status_code == 401
    assert probe.await_count == 1


@pytest.mark.parametrize("failure", ["provider_rejected", "vault_unconfigured"])
async def test_failed_login_preserves_the_unconsumed_roster_token_for_retry(
    classroom_database: async_sessionmaker[AsyncSession], failure: str,
) -> None:
    course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    app = _app(classroom_database)
    vault = app.state.credential_vault
    if failure == "vault_unconfigured":
        app.state.credential_vault = None
    probe = AsyncMock(side_effect=[failure != "provider_rejected", True])
    with patch("quantum_agent.api.auth._probe_ustc_key", new=probe):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            failed = await _login(client, access["classroom_access_token"])
            app.state.credential_vault = vault
            retried = await _login(client, access["classroom_access_token"])
    assert failed.status_code == (401 if failure == "provider_rejected" else 503)
    assert retried.status_code == 200
    async with classroom_database() as session:
        login_sessions = list((await session.scalars(select(UserSession).where(
            UserSession.user_id == UUID(access["user_id"]),
            UserSession.user_agent == "quantum-agent-api-key-login",
        ))).all())
    assert len(login_sessions) == 1


@pytest.mark.parametrize("state", ["expired", "revoked", "inactive_user", "inactive_membership"])
async def test_invalid_roster_access_cannot_create_login_session(
    classroom_database: async_sessionmaker[AsyncSession], state: str,
) -> None:
    course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    async with classroom_database() as session:
        access_digest = hash_session_token(access["classroom_access_token"])
        ticket = await session.scalar(select(UserSession).where(
            UserSession.session_token_sha256 == access_digest,
        ))
        assert ticket is not None
        if state == "expired":
            ticket.created_at = datetime.now(UTC) - timedelta(hours=2)
            ticket.expires_at = datetime.now(UTC) - timedelta(hours=1)
        elif state == "revoked":
            ticket.status = SessionStatus.REVOKED
            ticket.revoked_at = datetime.now(UTC)
        elif state == "inactive_user":
            user = await session.get(User, UUID(access["user_id"]))
            assert user is not None
            user.status = UserStatus.SUSPENDED
        else:
            membership = await session.scalar(select(CourseMembership).where(
                CourseMembership.user_id == UUID(access["user_id"]),
                CourseMembership.course_id == course.id,
            ))
            assert membership is not None
            membership.status = MembershipStatus.SUSPENDED
        await session.commit()
    app = _app(classroom_database)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=AsyncMock(return_value=True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _login(client, access["classroom_access_token"])
    assert response.status_code in {401, 403, 409}
    async with classroom_database() as session:
        sessions = list((await session.scalars(select(UserSession).where(
            UserSession.user_id == UUID(access["user_id"]),
            UserSession.user_agent == "quantum-agent-api-key-login",
        ))).all())
    assert sessions == []


async def test_student_cannot_self_promote_or_access_other_course(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    other_course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    app = _app(classroom_database)
    with patch("quantum_agent.api.auth._probe_ustc_key", new=AsyncMock(return_value=True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            denied_course = await _login(
                client, access["classroom_access_token"], course_id=other_course.id,
            )
            denied_role = await client.post("/api/v1/auth/login", json={
                "api_key": _SHARED_PROVIDER_KEY,
                "classroom_access_token": access["classroom_access_token"],
                "role": "teacher",
            })
            accepted = await _login(client, access["classroom_access_token"], course_id=course.id)
    assert denied_course.status_code == 409
    assert denied_role.status_code == 422
    assert accepted.status_code == 200
    async with classroom_database() as session:
        credential = SessionCredential(token=accepted.json()["session_token"])
        with pytest.raises(HTTPException) as teacher_error:
            await authenticate_course_actor(
                session, credential=credential, course_id=course.id, allowed_roles=TEACHER_ROLES,
            )
        assert teacher_error.value.status_code == 403
        with pytest.raises(HTTPException) as other_error:
            await authenticate_course_actor(
                session, credential=credential, course_id=other_course.id,
            )
        assert other_error.value.status_code == 401


async def test_unexchanged_roster_token_is_not_a_bearer_session(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    async with classroom_database() as session:
        with pytest.raises(HTTPException) as error:
            await authenticate_course_actor(
                session, credential=SessionCredential(token=access["classroom_access_token"]),
                course_id=course.id,
            )
        assert error.value.status_code == 401
    app = _app(classroom_database)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me/course-context", headers={
            "authorization": f"Bearer {access['classroom_access_token']}",
        })
    assert response.status_code == 401


async def test_reprovisioning_never_silently_changes_student_role(
    classroom_database: async_sessionmaker[AsyncSession],
) -> None:
    course = await _course(classroom_database)
    access = await _issue(classroom_database, course.id)
    with pytest.raises(ValueError, match="operator must review"):
        await _issue(classroom_database, course.id, role=CourseRole.TEACHER)
    async with classroom_database() as session:
        membership = await session.scalar(select(CourseMembership).where(
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == UUID(access["user_id"]),
        ))
    assert membership is not None
    assert membership.role is CourseRole.STUDENT


async def test_operator_cli_provisions_without_provider_key_and_keeps_token_out_of_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'classroom.sqlite').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        course, _, _ = await _seed_login_account(session, email="fixture@example.edu")
    await engine.dispose()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("USTC_API", raising=False)
    destination = tmp_path / "private-roster-access.json"
    arguments = build_parser().parse_args([
        "issue-classroom-access", "--email", "named-student@example.edu",
        "--display-name", "Named Student", "--course-id", str(course.id),
        "--output", str(destination),
    ])
    assert await _classroom_access_async(arguments) == 0
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["role"] == "student"
    assert payload["classroom_access_token"] not in capsys.readouterr().out
    if os.name == "posix":
        assert destination.stat().st_mode & 0o777 == 0o600
    # The exclusive output-file creation makes a repeated command fail before
    # creating another credential or replacing the existing credential file.
    with pytest.raises(FileExistsError):
        await _classroom_access_async(arguments)
    assert json.loads(destination.read_text(encoding="utf-8")) == payload
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ticket = await session.scalar(select(UserSession).where(
                UserSession.session_token_sha256 == hash_session_token(
                    payload["classroom_access_token"],
                ),
            ))
            assert ticket is not None
            assert str(ticket.user_id) == payload["user_id"]
            assert ticket.user_agent == "classroom-access"
    finally:
        await engine.dispose()
