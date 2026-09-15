"""Explicitly provisioned, durable recording request ledger; never auto-refills."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class RecordingBudgetError(RuntimeError):
    """Terminal recording stop, never a recoverable provider failure."""


class RecordingBudget:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id

    @classmethod
    def provision(cls, path: Path, run_id: str, *, requests: int, seconds: float,
                  output_tokens: int, request_bytes: int) -> RecordingBudget:
        if not (1 <= requests <= 41 and 0 < seconds <= 600
                and 1 <= output_tokens <= 2048 and 1 <= request_bytes <= 65536):
            raise ValueError("outside recording envelope")
        # Exclusive creation: an existing recording can never be refilled.
        with path.open("xb"):
            pass
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE budget (run TEXT PRIMARY KEY, remaining INTEGER, "
                       "deadline REAL, output INTEGER, bytes INTEGER)")
            db.execute("INSERT INTO budget VALUES (?, ?, ?, ?, ?)",
                       (run_id, requests, time.time() + seconds, output_tokens, request_bytes))
        return cls(path, run_id)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True)

    def limits(self) -> tuple[float, int]:
        try:
            with self._connect() as db:
                row = db.execute("SELECT deadline, output FROM budget WHERE run=?",
                                 (self.run_id,)).fetchone()
            if row is None or row[0] <= time.time():
                raise RecordingBudgetError("recording deadline or identity rejected")
            return float(row[0]) - time.time(), int(row[1])
        except (sqlite3.Error, OSError) as exc:
            raise RecordingBudgetError("recording ledger unavailable") from exc

    def reserve(self, body: bytes) -> None:
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise RecordingBudgetError("invalid recording request body")
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT remaining, deadline, output, bytes FROM budget "
                                 "WHERE run=?", (self.run_id,)).fetchone()
                if row is None or row[0] <= 0 or row[1] <= time.time():
                    raise RecordingBudgetError("recording request or time limit reached")
                caps = [payload[key] for key in ("max_completion_tokens", "max_tokens")
                        if key in payload]
                if (not caps or any(type(cap) is not int or not 0 < cap <= row[2]
                                    for cap in caps) or len(body) > row[3]):
                    raise RecordingBudgetError("serialized request exceeds recording envelope")
                db.execute("UPDATE budget SET remaining=remaining-1 WHERE run=?", (self.run_id,))
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            raise RecordingBudgetError("recording reservation failed") from exc


def active_budget() -> RecordingBudget | None:
    run = os.environ.get("QUANTUM_AGENT_RECORDING_RUN_ID")
    path = os.environ.get("QUANTUM_AGENT_RECORDING_LEDGER")
    if not run and not path:
        return None
    if not run or not path:
        raise RecordingBudgetError("recording requires run ID and durable ledger")
    budget = RecordingBudget(Path(path), run)
    budget.limits()
    return budget


async def bounded(operation: Any, budget: RecordingBudget) -> Any:
    remaining, _ = budget.limits()
    timeout = asyncio.timeout(remaining)
    try:
        async with timeout:
            return await operation()
    except TimeoutError as exc:
        if timeout.expired():
            raise RecordingBudgetError(
                "recording deadline reached; in-flight task cancelled"
            ) from exc
        raise
