from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantum_agent.auth import (
    SessionCredential,
    authenticate_course_actor,
    hash_session_token,
    issue_opaque_session_token,
)
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


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_actor(
    session: AsyncSession,
    *,
    role: CourseRole = CourseRole.TEACHER,
    expired: bool = False,
) -> tuple[str, Course, UserSession]:
    token = issue_opaque_session_token()
    user = User(
        email=f"teacher-{uuid4()}@example.edu",
        display_name="Course teacher",
        status=UserStatus.ACTIVE,
    )
    course = Course(code=f"QA-{uuid4()}", title="Quantum Physics")
    session.add_all([user, course])
    await session.flush()
    membership = CourseMembership(
        course_id=course.id,
        user_id=user.id,
        role=role,
        status=MembershipStatus.ACTIVE,
        joined_at=datetime.now(UTC),
    )
    now = datetime.now(UTC)
    user_session = UserSession(
        user_id=user.id,
        session_token_sha256=hash_session_token(token),
        status=SessionStatus.ACTIVE,
        created_at=now - timedelta(hours=2) if expired else now,
        expires_at=now - timedelta(minutes=1) if expired else now + timedelta(hours=1),
    )
    session.add_all([membership, user_session])
    await session.commit()
    return token, course, user_session


async def test_authenticates_active_course_teacher(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        token, course, persisted_session = await _seed_actor(session)
        actor = await authenticate_course_actor(
            session,
            credential=SessionCredential(token=token),
            course_id=course.id,
            allowed_roles=frozenset({CourseRole.TEACHER}),
        )

    assert actor.course_id == course.id
    assert actor.session_id == persisted_session.id
    assert actor.course_role is CourseRole.TEACHER


async def test_rejects_expired_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        token, course, _ = await _seed_actor(session, expired=True)
        with pytest.raises(HTTPException) as error:
            await authenticate_course_actor(
                session,
                credential=SessionCredential(token=token),
                course_id=course.id,
            )

    assert error.value.status_code == 401


async def test_enforces_course_role_in_backend(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        token, course, _ = await _seed_actor(session, role=CourseRole.STUDENT)
        with pytest.raises(HTTPException) as error:
            await authenticate_course_actor(
                session,
                credential=SessionCredential(token=token),
                course_id=course.id,
                allowed_roles=frozenset({CourseRole.TEACHER}),
            )

    assert error.value.status_code == 403


async def test_unknown_course_is_not_disclosed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        token, _, _ = await _seed_actor(session)
        with pytest.raises(HTTPException) as error:
            await authenticate_course_actor(
                session,
                credential=SessionCredential(token=token),
                course_id=uuid4(),
            )

    assert error.value.status_code == 401
