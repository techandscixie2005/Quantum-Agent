"""Create a fresh named synthetic PG database; never drop/reset an existing one."""

from __future__ import annotations

import asyncio
import os
import re

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    target = make_url(os.environ["BACKEND_LIVE_DATABASE_URL"])
    database = target.database or ""
    if "backend_live" not in database or re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database) is None:
        raise ValueError("Only a validated dedicated backend_live database may be created")
    if target.drivername != "postgresql+asyncpg":
        raise ValueError("Fixture database creation requires postgresql+asyncpg")
    engine = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            # Identifier is validated above; CREATE DATABASE cannot bind its name.
            await connection.execute(text(f'CREATE DATABASE "{database}"'))
        print("Created a new dedicated synthetic browser-test database; no existing data changed.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
