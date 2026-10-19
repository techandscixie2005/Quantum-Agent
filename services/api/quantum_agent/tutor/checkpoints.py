"""Serialize checkpoint DDL across API workers, using a dedicated connection."""

from __future__ import annotations

import asyncio
from typing import Protocol

from psycopg import AsyncConnection

# A session lock spans the saver's autocommitted/concurrent-index migrations.
# A transaction lock would be released before the other connection's DDL ends.
_SCHEMA_LOCK = 0x51414743504B5431


class CheckpointSetup(Protocol):
    async def setup(self) -> None: ...


async def setup_checkpoint_schema(saver: CheckpointSetup, connection_string: str) -> None:
    # This connection is never returned to an application pool. Its physical
    # close also releases the lock if setup/unlock fails or is cancelled.
    coordination = await AsyncConnection.connect(
        connection_string, autocommit=True, prepare_threshold=0
    )
    try:
        # A blocking lock SELECT retains a snapshot. That waiter can deadlock
        # the owner's CREATE INDEX CONCURRENTLY while waiting for its lock.
        # Finish each autocommitted try-lock statement before backing off.
        async with asyncio.timeout(120):
            while True:
                cursor = await coordination.execute(
                    "SELECT pg_try_advisory_lock(%s)", (_SCHEMA_LOCK,)
                )
                row = await cursor.fetchone()
                if row is not None and row[0]:
                    break
                await asyncio.sleep(0.1)
        try:
            await saver.setup()
        finally:
            await coordination.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_LOCK,))
    finally:
        await coordination.close()
