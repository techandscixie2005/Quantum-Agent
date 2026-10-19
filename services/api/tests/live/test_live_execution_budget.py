"""Opt-in PostgreSQL row-lock check; no model calls or classroom participants."""

from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import httpx2
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, sql
from sqlalchemy import delete

from quantum_agent.config import Settings
from quantum_agent.database import create_database_engine, create_session_factory
from quantum_agent.db_models import Course, TeachingMode, TeachingTurn, User
from quantum_agent.teaching.execution_budget import (
    ExecutionBudget,
    ExecutionBudgetBusyError,
    ExecutionBudgetError,
    ExecutionLimits,
    budget_status,
)
from quantum_agent.teaching.models import TeachingTurnInput
from quantum_agent.teaching.repository import TeachingRepository
from quantum_agent.tutor.checkpoints import setup_checkpoint_schema
from tests.test_tutor_graph import _seed


def _checkpoint_url() -> str:
    if os.environ.get("QA_LIVE_INFRA") != "1":
        pytest.skip("set QA_LIVE_INFRA=1 with a migrated PostgreSQL DATABASE_URL")
    settings = Settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.live_infra
async def test_fresh_postgresql_checkpoint_schema_is_safe_for_simultaneous_workers() -> None:
    url = _checkpoint_url()
    schema = "qa_checkpoint_" + uuid4().hex
    async with await AsyncConnection.connect(url, autocommit=True) as admin:
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:

            async def start_worker() -> None:
                async with AsyncPostgresSaver.from_conn_string(url) as saver:
                    assert isinstance(saver.conn, AsyncConnection)
                    await saver.conn.execute(
                        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                    )
                    await setup_checkpoint_schema(saver, url)

            await asyncio.wait_for(asyncio.gather(start_worker(), start_worker()), timeout=30)
            await admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            cursor = await admin.execute("SELECT v FROM checkpoint_migrations ORDER BY v")
            assert [row[0] for row in await cursor.fetchall()] == list(
                range(len(AsyncPostgresSaver.MIGRATIONS))
            )
            cursor = await admin.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname=%s", (schema,)
            )
            assert {row[0] for row in await cursor.fetchall()} == {
                "checkpoint_migrations",
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            }
        finally:
            await admin.execute("SET search_path TO public")
            await admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.live_infra
@pytest.mark.parametrize("cancel", [False, True])
async def test_checkpoint_setup_lock_is_released_after_failure_or_cancellation(
    cancel: bool,
) -> None:
    url = _checkpoint_url()
    entered = asyncio.Event()

    class FaultSetup:
        async def setup(self) -> None:
            entered.set()
            if cancel:
                await asyncio.Event().wait()
            raise RuntimeError("synthetic checkpoint setup failure")

    task = asyncio.create_task(setup_checkpoint_schema(FaultSetup(), url))
    await asyncio.wait_for(entered.wait(), timeout=10)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await task

    class RecoveredSetup:
        async def setup(self) -> None:
            pass

    # A new independent connection must acquire the identical session lock.
    await asyncio.wait_for(setup_checkpoint_schema(RecoveredSetup(), url), timeout=10)


@pytest.mark.live_infra
async def test_postgresql_concurrent_workers_cannot_claim_or_refill_same_execution() -> None:
    if os.environ.get("QA_LIVE_INFRA") != "1":
        pytest.skip("set QA_LIVE_INFRA=1 with a migrated PostgreSQL DATABASE_URL")
    settings = Settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    course_id: UUID | None = None
    user_id: UUID | None = None
    try:
        async with factory() as session:
            seeded = await _seed(session)
            course_id, user_id = seeded.actor.course_id, seeded.actor.user_id
            started = await TeachingRepository(session).start_turn(
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.LEARN_CONCEPTS,
                    message="Synthetic PostgreSQL execution lease fixture",
                ),
            )
            turn_id = started.turn.id
            await session.commit()
        barrier = asyncio.Barrier(2)

        async def claim() -> str:
            async with factory() as session:
                turn = await session.get(TeachingTurn, turn_id)
                assert turn is not None
                budget = ExecutionBudget(
                    session,
                    turn,
                    limits=ExecutionLimits(active_seconds=5),
                    clock=lambda: 1000,
                    wall_clock=lambda: 1000,
                )
                await barrier.wait()
                try:
                    await budget.start()
                except ExecutionBudgetBusyError:
                    await session.rollback()
                    return "busy"
                await budget.reserve_provider(
                    httpx2.Request(
                        "POST",
                        "https://local.invalid/v1/chat/completions",
                        json={"model": "synthetic", "messages": [], "max_tokens": 16},
                    )
                )
                # Deliberately abandon the lease to model a worker termination.
                return "claimed"

        assert sorted(await asyncio.gather(claim(), claim())) == ["busy", "claimed"]
        async with factory() as recovered:
            turn = await recovered.get(TeachingTurn, turn_id)
            assert turn is not None
            budget = ExecutionBudget(
                recovered,
                turn,
                limits=ExecutionLimits(active_seconds=600),
                clock=lambda: 1006,
                wall_clock=lambda: 1006,
            )
            with pytest.raises(ExecutionBudgetError) as error:
                await budget.start()
            assert error.value.reason == "active_seconds"
            status = budget_status(turn, wall_time=1006)
            assert status["active_used_seconds"] == 5
            assert status["provider_requests"] == 1
            assert status["state"] == "exhausted"
    finally:
        async with factory() as cleanup:
            if course_id is not None:
                await cleanup.execute(delete(Course).where(Course.id == course_id))
            if user_id is not None:
                await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
