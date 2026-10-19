"""Opt-in schema roundtrip on a newly created, disposable PostgreSQL database.

This does not downgrade the supplied classroom database or claim data-preserving
rollback: removing the new columns/tables deliberately discards their contents.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from quantum_agent.config import Settings

API_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live_infra
async def test_postgresql_new_database_upgrade_downgrade_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("QA_LIVE_INFRA") != "1":
        pytest.skip("requires isolated PostgreSQL with CREATE DATABASE permission")
    url = make_url(Settings().database_url)
    assert url.drivername == "postgresql+asyncpg" and "backend_live" in (url.database or "")
    database_name = "qa_migration_" + uuid4().hex
    admin = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port,
        database=url.database,
    )
    created = False
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        created = True
        test_url = url.set(database=database_name)
        monkeypatch.setenv("DATABASE_URL", test_url.render_as_string(hide_password=False))
        config = Config(str(API_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(API_ROOT / "alembic"))
        head = ScriptDirectory.from_config(config).get_current_head()

        async def assert_revision(expected: str | None, budget_column: bool) -> None:
            connection = await asyncpg.connect(
                user=url.username, password=url.password, host=url.host, port=url.port,
                database=database_name,
            )
            try:
                actual = await connection.fetchval("SELECT version_num FROM alembic_version")
                assert actual == expected
                assert await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='teaching_turns' "
                    "AND column_name='execution_budget_json')"
                ) is budget_column
                assert await connection.fetchval("SELECT extversion FROM pg_extension "
                                                 "WHERE extname='vector'") == "0.8.6"
            finally:
                await connection.close()

        await asyncio.to_thread(command.upgrade, config, "head")
        await assert_revision(head, True)
        await asyncio.to_thread(command.downgrade, config, "0008")
        await assert_revision("0008", False)
        await asyncio.to_thread(command.upgrade, config, "head")
        await assert_revision(head, True)
    finally:
        if created:
            # This exact random database was created above; never drop the input database.
            assert database_name.startswith("qa_migration_") and len(database_name) == 45
            await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        await admin.close()
