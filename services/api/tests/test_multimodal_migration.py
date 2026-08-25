from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from quantum_agent.db_models import Base

API_ROOT = Path(__file__).resolve().parents[1]
P3_TABLES = {"user_attachments", "multimodal_extractions", "document_parse_runs"}


def test_0004_upgrade_and_downgrade_from_existing_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise only 0004; migration 0003 is outside this bounded change."""

    database_path = tmp_path / "migration-0004.sqlite3"
    database_url = f"sqlite:///{database_path}"
    async_database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", async_database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    engine = create_engine(database_url)
    existing_tables = [
        table for table in Base.metadata.sorted_tables if table.name not in P3_TABLES
    ]
    Base.metadata.create_all(engine, tables=existing_tables)
    engine.dispose()

    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "0003")
    command.upgrade(config, "0004")

    engine = create_engine(database_url)
    assert P3_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "0003")
    engine = create_engine(database_url)
    assert not P3_TABLES & set(inspect(engine).get_table_names())
    engine.dispose()
