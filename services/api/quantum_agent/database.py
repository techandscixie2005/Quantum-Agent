"""Async SQLAlchemy engine and transaction helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from quantum_agent.config import Settings, get_settings


def create_database_engine(
    settings: Settings | None = None,
    **overrides: Any,
) -> AsyncEngine:
    """Build an async engine without connecting to the database.

    Pool sizing is deliberately omitted for SQLite because its test pools do
    not accept PostgreSQL's QueuePool arguments.
    """

    config = settings or get_settings()
    options: dict[str, Any] = {
        "echo": config.database_echo,
        "pool_pre_ping": True,
    }
    if not config.is_sqlite:
        options.update(
            pool_size=config.database_pool_size,
            max_overflow=config.database_max_overflow,
            pool_timeout=config.database_pool_timeout_seconds,
        )
    options.update(overrides)
    return create_async_engine(config.database_url, **options)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create sessions with explicit transaction and expiration behavior."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


@lru_cache(maxsize=1)
def get_database_engine() -> AsyncEngine:
    """Lazily construct the process-wide engine without connecting at import."""

    return create_database_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(get_database_engine())


async def dispose_database_engine() -> None:
    """Dispose the process engine during application shutdown, if initialized."""

    if get_database_engine.cache_info().currsize:
        await get_database_engine().dispose()
    get_session_factory.cache_clear()
    get_database_engine.cache_clear()


@asynccontextmanager
async def transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield one session and commit or roll back atomically."""

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI-compatible process-default session dependency.

    Application startup should normally construct and inject its own factory;
    this lazy default keeps CLI jobs and small workers ergonomic without opening
    a connection at import time.
    """

    async with get_session_factory()() as session:
        yield session
