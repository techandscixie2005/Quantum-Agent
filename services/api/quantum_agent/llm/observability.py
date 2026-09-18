"""Content-free correlation for teaching calls and bounded retries."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

_SCOPE: ContextVar[dict[str, str] | None] = ContextVar("model_trace_scope", default=None)
_LOG = logging.getLogger("quantum_agent.capability_events")
_LOG.setLevel(logging.INFO)
if not _LOG.handlers:
    _LOG.addHandler(logging.StreamHandler())


def failure_category(exc: BaseException) -> str:
    from quantum_agent.llm.recording_budget import RecordingBudgetError

    chain: BaseException | None = exc
    while chain is not None:
        if isinstance(chain, RecordingBudgetError):
            return "recording_budget_exhausted"
        if isinstance(chain, TimeoutError) or "timeout" in type(chain).__name__.lower():
            return "timeout"
        if isinstance(chain, ValueError) or type(chain).__name__ in {
            "ValidationError", "UnexpectedModelBehavior",
        }:
            return "parse"
        chain = chain.__cause__
    return "upstream_failure"


def event(capability: str, reason: str, *, attempt: int = 0, elapsed: float = 0) -> None:
    # Never accept exception text, prompts, output, credentials, or URLs.
    _LOG.disabled = False  # Remain observable after application dictConfig setup.
    _LOG.info(json.dumps({
        **(_SCOPE.get() or {}), "capability": capability, "reason": reason,
        "attempt": attempt, "elapsed_seconds": round(elapsed, 6),
    }, sort_keys=True))


@contextmanager
def turn_scope(session_id: UUID, turn_id: UUID) -> Iterator[None]:
    configured = os.environ.get("QUANTUM_AGENT_RECORDING_RUN_ID")
    run_id = str(UUID(configured)) if configured else str(uuid4())
    token = _SCOPE.set({"run_id": run_id, "session_id": str(session_id),
                        "turn_id": str(turn_id)})
    event("turn", "started")
    try:
        yield
    finally:
        event("turn", "ended")
        _SCOPE.reset(token)


def traced_call[**P, T](
    function: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]:
    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        parent = _SCOPE.get() or {}
        token = _SCOPE.set({**parent, "parent_call_id": parent.get("call_id", ""),
                            "call_id": str(uuid4())})
        task = str(kwargs.get("task", function.__name__))
        start = monotonic()
        event(task, "started")
        try:
            result = await function(*args, **kwargs)
            event(task, "completed", elapsed=monotonic() - start)
            return result
        except Exception as exc:
            event(task, failure_category(exc), elapsed=monotonic() - start)
            # Diagnose schema failures without recording model content, input,
            # error messages (which may quote input), or private reasoning.
            cause: BaseException | None = exc
            seen: set[int] = set()
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                if isinstance(cause, ValidationError):
                    for error in cause.errors(include_url=False, include_input=False,
                                              include_context=False)[:8]:
                        event(task, "schema_" + error["type"])
                    break
                cause = cause.__cause__ or cause.__context__
            raise
        finally:
            _SCOPE.reset(token)
    return wrapped


async def provider_request(request: Any) -> None:
    """Runs for every HTTP request, including SDK-internal output retries."""
    from quantum_agent.llm.recording_budget import active_budget

    budget = active_budget()
    if budget is not None:
        budget.reserve(request.content)
    request_id = str(uuid4())
    request.extensions["qa_request_id"] = request_id
    token = _SCOPE.set({**(_SCOPE.get() or {}), "request_id": request_id})
    try:
        event("provider_http", "request_started")
    finally:
        _SCOPE.reset(token)


async def provider_response(response: Any) -> None:
    request_id = response.request.extensions.get("qa_request_id", "unknown")
    token = _SCOPE.set({**(_SCOPE.get() or {}), "request_id": request_id})
    try:
        event("provider_http", "response_received" if response.status_code < 400
              else "upstream_failure")
    finally:
        _SCOPE.reset(token)
