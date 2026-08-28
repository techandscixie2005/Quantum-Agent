"""Regression checks that deliberately reject SQLite and in-memory substitutes."""

from __future__ import annotations

import os
from collections.abc import Awaitable
from typing import cast
from uuid import uuid4

import httpx
import pytest
from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis
from sqlalchemy import text

from quantum_agent.config import Settings
from quantum_agent.database import create_database_engine


def _require_live_stack() -> None:
    if os.environ.get("QA_LIVE_INFRA") != "1":
        pytest.skip("set QA_LIVE_INFRA=1 and run through the Compose live-test service")


@pytest.mark.live_infra
@pytest.mark.asyncio
async def test_compose_dependencies_are_real_healthy_and_migrated() -> None:
    _require_live_stack()
    settings = Settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.neo4j_password is not None

    engine = create_database_engine(settings)
    try:
        async with engine.connect() as connection:
            vector_version = await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            migration = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            checkpoint_tables = set(
                (
                    await connection.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name IN "
                            "('checkpoints', 'checkpoint_blobs', 'checkpoint_writes', "
                            "'checkpoint_migrations')"
                        )
                    )
                ).scalars()
            )
            published_sources = int(
                await connection.scalar(
                    text("SELECT count(*) FROM document_publications WHERE status = 'published'")
                )
                or 0
            )
            visible_chunks = int(
                await connection.scalar(text("SELECT count(*) FROM student_visible_chunks")) or 0
            )
        assert vector_version is not None
        assert migration == "0007"
        assert checkpoint_tables == {
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
        }
        if os.environ.get("QA_LIVE_REQUIRE_CORPUS") == "1":
            assert published_sources == 5
            assert visible_chunks == 1971
    finally:
        await engine.dispose()

    graph_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        await graph_driver.verify_connectivity()
        records, _, _ = await graph_driver.execute_query(
            "MATCH (n) OPTIONAL MATCH ()-[r]->() "
            "RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS relations",
            database_=settings.neo4j_database,
        )
        assert records and int(records[0]["nodes"]) >= 0
        if os.environ.get("QA_LIVE_REQUIRE_CORPUS") == "1":
            assert int(records[0]["nodes"]) > 0
    finally:
        await graph_driver.close()

    redis = Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ["REDIS_PASSWORD"],
        decode_responses=True,
    )
    redis_key = f"quantum-agent:live-regression:{uuid4()}"
    try:
        assert await cast(Awaitable[bool], redis.ping()) is True
        assert await redis.set(redis_key, "ok", ex=30, nx=True) is True
        assert await redis.get(redis_key) == "ok"
    finally:
        await redis.delete(redis_key)
        await redis.aclose()

    api_base_url = os.environ.get("QUANTUM_API_BASE_URL", "http://api:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{api_base_url}/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "components": {"postgresql": "ok"}}
