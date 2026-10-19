"""Durable per-turn resource admission; human review is outside active time.

Reservations are committed before provider I/O. A crashed active lease is never
refunded: after expiry its remaining reservation is charged conservatively. Token
units bound serialized UTF-8 input bytes plus framing and admitted output tokens;
they are an admission envelope, not a tokenizer or a claim about provider billing.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.config import Settings
from quantum_agent.db_models import TeachingTurn, TeachingTurnStatus


class ExecutionBudgetError(RuntimeError):
    code = "EXECUTION_BUDGET_EXHAUSTED"

    def __init__(self, turn_id: UUID, reason: str) -> None:
        self.turn_id = turn_id
        self.reason = reason
        super().__init__(self.code)


class ExecutionBudgetBusyError(RuntimeError):
    code = "EXECUTION_BUDGET_BUSY"

    def __init__(self, turn_id: UUID) -> None:
        self.turn_id = turn_id
        super().__init__(self.code)


class ExecutionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    active_seconds: float = Field(default=180, gt=0, le=600)
    provider_requests: int = Field(default=12, ge=1, le=64)
    token_units: int = Field(default=131_072, ge=1024, le=2_000_000)
    output_tokens: int = Field(default=2048, ge=1, le=8192)
    request_bytes: int = Field(default=65_536, ge=1024, le=262_144)

    @classmethod
    def from_settings(cls, settings: Settings) -> ExecutionLimits:
        return cls(
            active_seconds=settings.teaching_execution_seconds,
            provider_requests=settings.teaching_execution_provider_requests,
            token_units=settings.teaching_execution_token_units,
            output_tokens=settings.teaching_execution_output_tokens,
            request_bytes=settings.teaching_execution_request_bytes,
        )


class _Lease(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    lease_id: UUID
    started_at: float
    seconds: float = Field(gt=0)


class _Ledger(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal[1] = 1
    limits: ExecutionLimits
    state: Literal["ready", "running", "waiting", "finished", "cancelled", "failed", "exhausted"]
    active_used_seconds: float = Field(default=0, ge=0)
    human_wait_seconds: float = Field(default=0, ge=0)
    wait_started_at: float | None = None
    lease: _Lease | None = None
    provider_requests: int = Field(default=0, ge=0)
    reserved_token_units: int = Field(default=0, ge=0)
    reported_input_tokens: int = Field(default=0, ge=0)
    reported_output_tokens: int = Field(default=0, ge=0)
    reported_total_tokens: int = Field(default=0, ge=0)
    usage_reported_requests: int = Field(default=0, ge=0)
    reason: str | None = None
    stage_timings: dict[str, dict[str, float | int]] = Field(default_factory=dict, max_length=12)


def _load(turn: TeachingTurn) -> _Ledger | None:
    return _load_json(turn.execution_budget_json, turn.id)


def _load_json(raw: Any, turn_id: UUID) -> _Ledger | None:
    if raw == {}:
        return None
    try:
        return _Ledger.model_validate(raw)
    except ValidationError as exc:
        raise ExecutionBudgetError(turn_id, "invalid_ledger") from exc


def raise_if_execution_exhausted(turn: TeachingTurn) -> None:
    ledger = _load(turn)
    if ledger is not None and ledger.state == "exhausted":
        raise ExecutionBudgetError(turn.id, ledger.reason or "active_seconds")


def budget_status(turn: TeachingTurn, *, wall_time: float | None = None) -> dict[str, Any]:
    """Safe status projection; no credentials, content, or private lease identity."""
    return budget_status_json(turn.execution_budget_json, turn.id, wall_time=wall_time)


def budget_status_json(
    raw: Any,
    turn_id: UUID,
    *,
    wall_time: float | None = None,
) -> dict[str, Any]:
    """Project a SQL-selected ledger without loading the turn's full snapshots."""
    ledger = _load_json(raw, turn_id)
    if ledger is None:
        return {"state": "not_initialized"}
    now = time.time() if wall_time is None else wall_time
    data = ledger.model_dump(mode="json", exclude={"lease", "wait_started_at"})
    data["token_accounting"] = "conservative_serialized_input_and_output_admission"
    data["usage_completeness"] = (
        "reported" if ledger.usage_reported_requests == ledger.provider_requests else "partial"
    )
    if ledger.lease is not None:
        data["active_used_seconds"] += min(
            ledger.lease.seconds,
            max(0, now - ledger.lease.started_at),
        )
    if ledger.wait_started_at is not None:
        data["human_wait_seconds"] += max(0, now - ledger.wait_started_at)
    data["active_remaining_seconds"] = max(
        0,
        ledger.limits.active_seconds - data["active_used_seconds"],
    )
    return data


_CURRENT: ContextVar[ExecutionBudget | None] = ContextVar("teaching_execution_budget", default=None)
_STAGES = frozenset(
    {
        "interpret",
        "learning_native_pre",
        "prepare_commitment_gate",
        "retrieve_evidence",
        "diagnose",
        "apply_policy",
        "scientific_tools",
        "generate_response",
        "learning_native",
        "hitl_gate",
        "reject_turn",
        "assemble_result",
    }
)


def current_execution_budget() -> ExecutionBudget | None:
    return _CURRENT.get()


class ExecutionBudget:
    def __init__(
        self,
        session: AsyncSession,
        turn: TeachingTurn,
        *,
        limits: ExecutionLimits,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.session, self.turn = session, turn
        self.turn_id = turn.id
        self.defaults = limits
        self.clock, self.wall_clock = clock, wall_clock
        self.ledger = _Ledger(limits=limits, state="ready")
        self.started = clock()
        self.lease_id = uuid4()
        self.closed = False
        self._lock = asyncio.Lock()
        self._stage: tuple[str, float] | None = None
        self._expected_lease: UUID | None = None

    async def _save(self) -> None:
        if self._expected_lease is not None:
            raw = await self.session.scalar(
                select(TeachingTurn.execution_budget_json)
                .where(
                    TeachingTurn.id == self.turn_id,
                )
                .with_for_update()
                .execution_options(autoflush=False)
            )
            stored = _load_json(raw, self.turn_id)
            if (
                stored is None
                or stored.lease is None
                or stored.lease.lease_id != self._expected_lease
            ):
                # A late worker cannot overwrite a newer lease or revive an
                # exhausted allowance after another process recovered it.
                self.closed = True
                await self.session.rollback()
                await self.session.refresh(self.turn)
                if stored is not None and stored.state == "exhausted":
                    raise ExecutionBudgetError(self.turn_id, stored.reason or "active_seconds")
                raise ExecutionBudgetBusyError(self.turn_id)
        self.turn.execution_budget_json = self.ledger.model_dump(mode="json")
        await self.session.flush()
        # Deliberately persist the original input/phase before spending work.
        # Request failure or disconnect cannot refund provider reservations.
        await self.session.commit()
        self._expected_lease = self.ledger.lease.lease_id if self.ledger.lease is not None else None

    async def start(self) -> float:
        await self.session.refresh(
            self.turn,
            attribute_names=["id", "status", "execution_budget_json"],
            with_for_update=True,
        )
        self.ledger = _load(self.turn) or self.ledger
        now = self.wall_clock()
        if self.ledger.lease is not None:
            lease = self.ledger.lease
            if now < lease.started_at + lease.seconds:
                raise ExecutionBudgetBusyError(self.turn.id)
            # Missing clean completion means no evidence for refunding time.
            self.ledger.active_used_seconds += lease.seconds
            self.ledger.lease = None
            await self.exhaust("active_seconds")
        if self.ledger.state == "exhausted":
            raise ExecutionBudgetError(self.turn.id, self.ledger.reason or "active_seconds")
        remaining = self.ledger.limits.active_seconds - self.ledger.active_used_seconds
        if remaining <= 0:
            await self.exhaust("active_seconds")
        if self.ledger.wait_started_at is not None:
            self.ledger.human_wait_seconds += max(0, now - self.ledger.wait_started_at)
            self.ledger.wait_started_at = None
        self.started = self.clock()
        self.ledger.lease = _Lease(
            lease_id=self.lease_id,
            started_at=now,
            seconds=remaining,
        )
        self.ledger.state = "running"
        await self._save()
        remaining = self.remaining_seconds()
        if remaining <= 0:
            await self.exhaust("active_seconds")
        return remaining

    def remaining_seconds(self) -> float:
        return max(
            0,
            self.ledger.limits.active_seconds
            - self.ledger.active_used_seconds
            - (self.clock() - self.started),
        )

    async def exhaust(self, reason: str) -> None:
        self.ledger.reason = reason
        await self.finish("exhausted")
        # A stable terminal turn prevents checkpoint/retry from restarting it.
        if self.turn.status is TeachingTurnStatus.RUNNING:
            self.turn.status = TeachingTurnStatus.FAILED
            self.turn.failure_code = "execution_budget_" + reason
            self.turn.completed_at = datetime.now(UTC)
            await self._save()
        raise ExecutionBudgetError(self.turn.id, reason)

    async def finish(
        self,
        state: Literal["waiting", "finished", "cancelled", "failed", "exhausted"],
    ) -> None:
        if self.closed:
            return
        self._end_stage("interrupted" if state == "waiting" else state)
        if self.ledger.lease is not None:
            self.ledger.active_used_seconds += min(
                self.ledger.lease.seconds,
                max(0, self.clock() - self.started),
            )
        self.ledger.lease = None
        self.ledger.state = state
        self.ledger.wait_started_at = self.wall_clock() if state == "waiting" else None
        await self._save()
        self.closed = True

    def _end_stage(self, outcome: str) -> None:
        if self._stage is None:
            return
        name, started = self._stage
        timing = self.ledger.stage_timings[name]
        timing["active_seconds"] += max(0, self.clock() - started)
        timing[outcome] = timing.get(outcome, 0) + 1
        self._stage = None

    async def switch_stage(self, name: str) -> None:
        if name not in _STAGES:
            raise ValueError("unknown teaching execution stage")
        if self.closed or self.remaining_seconds() <= 0:
            await self.exhaust("active_seconds")
        self._end_stage("completed")
        self._stage = (name, self.clock())
        timing = self.ledger.stage_timings.setdefault(name, {"active_seconds": 0, "invocations": 0})
        timing["invocations"] += 1
        await self._save()

    @asynccontextmanager
    async def stage(self, name: str) -> AsyncIterator[None]:
        await self.switch_stage(name)
        outcome = "completed"
        try:
            yield
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except BaseException:
            outcome = "failed"
            raise
        finally:
            if not self.closed:
                self._end_stage(outcome)
                await self._save()

    async def abort(self, state: Literal["cancelled", "failed"]) -> None:
        # Discard any unvalidated work since the last committed reservation;
        # that reservation itself survives cancellation and request rollback.
        await self.session.rollback()
        await self.session.refresh(self.turn)
        resumable_pause = isinstance(self.turn.validation_json.get("hitl"), dict)
        if (
            not self.closed
            and self.turn.status is TeachingTurnStatus.RUNNING
            and not resumable_pause
        ):
            self.turn.status = TeachingTurnStatus.FAILED
            self.turn.failure_code = "execution_" + state
            self.turn.completed_at = datetime.now(UTC)
        await self.finish(state)

    async def reserve_provider(self, request: Any) -> None:
        """Called once per actual HTTP send, including SDK-internal retries."""
        if request.extensions.get("teaching_budget_request_id") is not None:
            return
        async with self._lock:
            if self.closed or self.remaining_seconds() <= 0:
                await self.exhaust("active_seconds")
            limits = self.ledger.limits
            raw = request.content
            if len(raw) > limits.request_bytes:
                await self.exhaust("request_bytes")
            payload = json.loads(raw)
            caps = [
                payload[key] for key in ("max_tokens", "max_completion_tokens") if key in payload
            ]
            chat = "/chat/completions" in request.url.path
            if chat and (
                not caps
                or any(type(cap) is not int or not 0 < cap <= limits.output_tokens for cap in caps)
            ):
                await self.exhaust("output_tokens")
            units = len(raw) + 1024 + (max(caps) if caps else 0)
            if self.ledger.provider_requests >= limits.provider_requests:
                await self.exhaust("provider_requests")
            if self.ledger.reserved_token_units + units > limits.token_units:
                await self.exhaust("reserved_tokens")
            self.ledger.provider_requests += 1
            self.ledger.reserved_token_units += units
            await self._save()
            request.extensions["teaching_budget_request_id"] = str(uuid4())

    async def record_usage(self, response: Any) -> None:
        if response.request.extensions.get("teaching_budget_request_id") is None:
            return
        if response.request.extensions.get("teaching_budget_usage_recorded"):
            return
        await response.aread()
        try:
            usage = response.json().get("usage")
        except (ValueError, AttributeError):
            return
        if not isinstance(usage, dict):
            return
        values = {key: value for key, value in usage.items() if type(value) is int and value >= 0}
        if not any(key in values for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            return
        async with self._lock:
            self.ledger.reported_input_tokens += values.get("prompt_tokens", 0)
            self.ledger.reported_output_tokens += values.get("completion_tokens", 0)
            self.ledger.reported_total_tokens += values.get(
                "total_tokens",
                values.get("prompt_tokens", 0) + values.get("completion_tokens", 0),
            )
            self.ledger.usage_reported_requests += 1
            await self._save()
            response.request.extensions["teaching_budget_usage_recorded"] = True
            if self.ledger.reported_total_tokens > self.ledger.limits.token_units:
                await self.exhaust("reported_tokens")


@asynccontextmanager
async def execution_budget_scope(
    session: AsyncSession,
    turn: TeachingTurn,
    limits: ExecutionLimits,
) -> AsyncIterator[ExecutionBudget]:
    budget = ExecutionBudget(session, turn, limits=limits)
    remaining = await budget.start()
    token = _CURRENT.set(budget)
    timeout = asyncio.timeout(remaining)
    try:
        async with timeout:
            yield budget
    except TimeoutError:
        if timeout.expired():
            await budget.exhaust("active_seconds")
        await budget.abort("failed")
        raise
    except asyncio.CancelledError:
        await budget.abort("cancelled")
        raise
    except BaseException:
        await budget.abort("failed")
        raise
    else:
        await budget.finish("finished")
    finally:
        _CURRENT.reset(token)
