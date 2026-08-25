from __future__ import annotations

import asyncio
import json
import stat
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantum_agent.cli import _seed_live_e2e
from quantum_agent.db_models import (
    Base,
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    UserSession,
)


def test_live_e2e_seed_writes_private_tokens_without_printing_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "live-e2e.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")

    async def seed_course() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            course = Course(
                code="LIVE-E2E",
                title="Live E2E Quantum Physics",
                status=CourseStatus.DRAFT,
            )
            session.add(course)
            await session.flush()
            session.add(
                CurriculumEdition(
                    course_id=course.id,
                    edition_key="live-e2e",
                    title="Live E2E edition",
                    status=CurriculumEditionStatus.PUBLISHED,
                    published_at=datetime.now(UTC),
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_course())
    output = tmp_path / "auth.json"
    result = _seed_live_e2e(
        Namespace(output=str(output), expires_hours=2, activate_course=True)
    )
    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["student_token"]) >= 32
    assert len(payload["ta_token"]) >= 32
    assert payload["student_token"] != payload["ta_token"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    captured = capsys.readouterr().out
    assert payload["student_token"] not in captured
    assert payload["ta_token"] not in captured

    async def verify_database() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            course = await session.scalar(select(Course))
            memberships = list(await session.scalars(select(CourseMembership)))
            sessions = list(await session.scalars(select(UserSession)))
        await engine.dispose()
        assert course is not None and course.status == CourseStatus.ACTIVE
        assert {membership.role for membership in memberships} == {
            CourseRole.STUDENT,
            CourseRole.TA,
        }
        assert len(sessions) == 2

    asyncio.run(verify_database())
