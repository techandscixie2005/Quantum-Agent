"""Reusable, validated LLM gateway for the USTC OpenAI-compatible service."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Protocol, TypeVar

import httpx
import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, ValidationError

T = TypeVar("T")


# Transient HTTP status codes that justify a bounded retry with backoff.
# Auth (401/403) and other 4xx configuration errors are NOT retried.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# Permanent HTTP status codes that must NOT be retried across router
# profiles.  401/403 are credential/authorization errors: the same key is
# used for every profile, so retrying against another profile cannot fix
# them and only burns the proxy deadline.  400 is NOT included here: a bad
# request may be profile-specific (e.g. a model that rejects a large
# prompt), so the router should still try the next profile.
_PERMANENT_STATUS_CODES: frozenset[int] = frozenset({401, 403})


class GatewayError(RuntimeError):
    """Sanitized provider failure safe to persist in an internal trace."""


class PermanentGatewayError(GatewayError):
    """A gateway failure that retrying cannot fix (401/403/400).

    The router treats this as a terminal signal: it must NOT attempt the
    next profile, because a permanent error on one credential/profile is
    almost certainly permanent on the others (same upstream auth, same
    request body).  Surfacing this distinct type lets the router fail
    fast and keep the total turn latency bounded.
    """


def _is_transient_exception(exc: BaseException) -> bool:
    """Classify whether an exception is a transient gateway failure.

    Retries cover timeouts, 429 (rate limit), and 5xx (server) responses.
    Auth (401/403), validation, and other 4xx configuration errors are NOT
    retried; they indicate a misconfiguration that retrying cannot fix.
    """

    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_STATUS_CODES
    # PydanticAI / OpenAI SDK wrap provider errors; inspect status_code attr.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS_CODES:
        return True
    return False


def _permanent_status(exc: BaseException) -> int | None:
    """Return the permanent HTTP status code carried by ``exc``, if any.

    Used by the router to decide whether to short-circuit across profiles.
    A permanent status (401/403/400) on one profile is almost certainly
    permanent on every other profile (same upstream auth, same request
    body), so retrying against the next profile only burns latency.
    """

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status if status in _PERMANENT_STATUS_CODES else None
    raw_status = getattr(exc, "status_code", None)
    if isinstance(raw_status, int) and raw_status in _PERMANENT_STATUS_CODES:
        return raw_status
    return None


async def _retry_transient(
    operation: Any,
    *,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    label: str,
    deadline: float | None = None,
    attempt_timeout: float | None = None,
    clock: Any = time.monotonic,
) -> Any:
    """Run ``operation`` with bounded exponential backoff + jitter on transient errors.

    Non-transient errors propagate immediately.  ``operation`` is a zero-arg
    coroutine factory.  The jitter is full jitter (random in [0, capped_delay])
    to decorrelate concurrent clients.

    PRD V3.1 P1-2: ``deadline`` caps the total retry budget for this gateway
    call.  When the next sleep would cross the deadline, we raise the last
    exception instead of sleeping.  This keeps a single gateway call from
    exhausting the proxy budget and leaves headroom for the router to try the
    next profile.

    Wall-time safety: each attempt is additionally wrapped in
    ``asyncio.wait_for`` bounded by ``attempt_timeout`` (and, tighter, by the
    remaining ``deadline``).  The HTTP client's own read timeout does not fire
    when an upstream keeps a connection open with periodic or no bytes; the
    wall-time cap is the backstop that guarantees every attempt — and thus the
    whole turn — terminates.  A wall-time expiry is treated as transient.
    """

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        budget = attempt_timeout
        if deadline is not None and budget is not None:
            # Clamp the wall cap by the remaining budget so a late attempt
            # cannot overshoot the deadline.  Without an explicit wall cap
            # the deadline keeps its legacy meaning: it bounds the backoff
            # sleeps, not the attempts themselves.
            budget = min(budget, max(deadline - clock(), 0.0))
        try:
            if budget is None:
                return await operation()
            return await asyncio.wait_for(operation(), timeout=budget)
        except TimeoutError as exc:
            last_exc = exc
            if attempt == max_attempts:
                raise GatewayError(
                    f"{label} exceeded its bounded wall-time budget"
                ) from exc
        except BaseException as exc:
            last_exc = exc
            if not _is_transient_exception(exc) or attempt == max_attempts:
                raise
        # Exponential backoff with full jitter, capped at max_delay.
        capped = min(max_delay, base_delay * (2 ** (attempt - 1)))
        delay = random.uniform(0.0, capped)
        if deadline is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                # Budget exhausted; surface the last transient error
                # rather than sleeping past the deadline.
                if last_exc is not None:
                    raise last_exc
                raise GatewayError(f"{label} retry budget exhausted")
            delay = min(delay, remaining)
            if delay <= 0:
                if last_exc is not None:
                    raise last_exc
                raise GatewayError(f"{label} retry budget exhausted")
        await asyncio.sleep(delay)
    # Unreachable, but keeps mypy happy.
    if last_exc is not None:
        raise last_exc
    raise GatewayError(f"{label} exhausted retries without an exception")


class ModelTier(StrEnum):
    DEFAULT = "default"
    SMALL = "small"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class GatewayCapabilities(BaseModel):
    """Capabilities observed from live probes, never assumed from API shape."""

    chat_completions: bool = False
    prompted_json: bool = False
    native_json_object: bool = False
    native_json_schema: bool = False
    tool_calling: bool = False
    detail: dict[str, str] = Field(default_factory=dict)


class ModelGateway(Protocol):
    async def structured_generate(
        self,
        *,
        task: str,
        messages: Sequence[Message],
        output_type: type[T],
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> T: ...

    async def probe(self) -> GatewayCapabilities: ...


class FakeModelGateway[T]:
    """Deterministic test double; unit tests never spend model tokens."""

    def __init__(self, responses: Mapping[str, Any] | None = None) -> None:
        self._responses = dict(responses or {})
        self.calls: list[dict[str, Any]] = []

    async def structured_generate(
        self,
        *,
        task: str,
        messages: Sequence[Message],
        output_type: type[T],
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> T:
        self.calls.append(
            {
                "task": task,
                "messages": [message.model_dump() for message in messages],
                "model_tier": model_tier.value,
            }
        )
        if task not in self._responses:
            raise GatewayError(f"No fake response configured for task {task!r}")
        return TypeAdapter(output_type).validate_python(self._responses[task])

    async def probe(self) -> GatewayCapabilities:
        return GatewayCapabilities(chat_completions=True, prompted_json=True)


class PydanticAIModelGateway:
    """PydanticAI-backed model gateway with prompt-based structured output.

    `PromptedOutput` is intentional: the USTC endpoint is OpenAI-compatible,
    but compatibility does not prove support for tool calls or native JSON
    schema.  PydanticAI still validates every response against `output_type`.
    A separate explicit probe records optional endpoint features.
    """

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://api.llm.ustc.edu.cn/v1",
        default_model: str = "deepseek-v4-pro",
        small_model: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        transient_retry_attempts: int = 4,
        transient_retry_base_delay: float = 0.8,
        transient_retry_max_delay: float = 12.0,
        # Hard wall-time cap for a single attempt.  Backstop for transports
        # that hold a connection open without completing: the HTTP read
        # timeout never fires if the upstream stalls after connect, but the
        # attempt must still terminate so the turn can degrade gracefully.
        attempt_wall_seconds: float = 90.0,
        # PRD V3.1 P1-2: cap the total retry budget per gateway call so a
        # single transient storm cannot exhaust the turn budget.  Widened
        # from 30s to 120s: slow-but-legitimate USTC generations (25-60s)
        # were being aborted before producing output; the per-attempt wall
        # cap above keeps termination deterministic either way.
        transient_retry_budget_seconds: float = 120.0,
        model_http_client: httpx2.AsyncClient | None = None,
        probe_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("A non-empty backend API key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._small_model = small_model or default_model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._transient_retry_attempts = max(1, transient_retry_attempts)
        self._transient_retry_base_delay = max(0.1, transient_retry_base_delay)
        self._transient_retry_max_delay = max(
            self._transient_retry_base_delay, transient_retry_max_delay
        )
        self._attempt_wall_seconds = max(1.0, attempt_wall_seconds)
        self._transient_retry_budget_seconds = max(1.0, transient_retry_budget_seconds)
        self._model_http_client = model_http_client
        self._probe_http_client = probe_http_client

    def _model_name(self, tier: ModelTier) -> str:
        return self._small_model if tier is ModelTier.SMALL else self._default_model

    async def structured_generate(
        self,
        *,
        task: str,
        messages: Sequence[Message],
        output_type: type[T],
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> T:
        if not messages:
            raise ValueError("At least one message is required")

        # Imports stay local so ingestion and deterministic tests can run when
        # the optional model client is deliberately not installed.
        try:
            from pydantic_ai import Agent, PromptedOutput
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
        except ImportError as exc:  # pragma: no cover - environment guard
            raise GatewayError("PydanticAI model dependencies are unavailable") from exc

        owned_client = self._model_http_client is None
        client = self._model_http_client or httpx2.AsyncClient(timeout=self._timeout_seconds)
        try:
            provider = OpenAIProvider(
                base_url=self._base_url,
                api_key=self._api_key.get_secret_value(),
                http_client=client,
            )
            model = OpenAIChatModel(self._model_name(model_tier), provider=provider)
            system_parts = [message.content for message in messages if message.role == "system"]
            conversation = "\n\n".join(
                f"{message.role.upper()}: {message.content}"
                for message in messages
                if message.role != "system"
            )
            agent: Agent[None, T] = Agent(
                model,
                output_type=PromptedOutput(
                    output_type,
                    name=task,
                    description=(
                        "Return only data supported by the supplied course evidence. "
                        "Use the exact requested schema."
                    ),
                ),
                system_prompt="\n\n".join(system_parts),
                retries=self._max_retries,
            )

            async def _run() -> Any:
                return await agent.run(conversation)

            # PRD V3.1 P1-2: enforce a per-call retry deadline so a single
            # gateway call cannot burn the turn budget.  The deadline is
            # relative to the start of this call; each attempt is additionally
            # capped by the hard per-attempt wall time.
            call_deadline = time.monotonic() + self._transient_retry_budget_seconds
            try:
                result = await _retry_transient(
                    _run,
                    max_attempts=self._transient_retry_attempts,
                    base_delay=self._transient_retry_base_delay,
                    max_delay=self._transient_retry_max_delay,
                    label=task,
                    deadline=call_deadline,
                    attempt_timeout=self._attempt_wall_seconds,
                )
            except GatewayError:
                raise
            except Exception as exc:
                permanent = _permanent_status(exc)
                if permanent is not None:
                    raise PermanentGatewayError(
                        f"Model provider returned permanent HTTP {permanent}"
                    ) from exc
                if _is_transient_exception(exc):
                    raise GatewayError(
                        f"Model provider transient failure exhausted retries: {type(exc).__name__}"
                    ) from exc
                raise
            return TypeAdapter(output_type).validate_python(result.output)
        except ValidationError as exc:
            raise GatewayError("Model output failed schema validation") from exc
        except httpx.TimeoutException as exc:
            raise GatewayError("Model provider timed out") from exc
        except httpx.HTTPError as exc:
            raise GatewayError("Model provider request failed") from exc
        except GatewayError:
            raise
        except Exception as exc:  # PydanticAI provider/model errors
            raise GatewayError(f"Structured generation failed: {type(exc).__name__}") from exc
        finally:
            if owned_client:
                await client.aclose()

    async def probe(self) -> GatewayCapabilities:
        """Probe small, non-sensitive requests and report observed behavior."""

        capabilities = GatewayCapabilities()
        owned_client = self._probe_http_client is None
        client = self._probe_http_client or httpx.AsyncClient(
            timeout=min(self._timeout_seconds, 20.0)
        )
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"

        async def attempt(name: str, extra: dict[str, Any]) -> bool:
            body: dict[str, Any] = {
                "model": self._default_model,
                "messages": [
                    {
                        "role": "user",
                        "content": 'Return the JSON object {"ok": true} and nothing else.',
                    }
                ],
                "max_tokens": 24,
                "temperature": 0,
                **extra,
            }
            try:
                response = await client.post(url, headers=headers, json=body)
                if not response.is_success:
                    capabilities.detail[name] = f"HTTP {response.status_code}"
                    return False
                payload = response.json()
                content = payload["choices"][0]["message"].get("content", "")
                if content:
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and parsed.get("ok") is True:
                            return True
                    except json.JSONDecodeError:
                        pass
                # Tool calls may legitimately have no text content.
                if name == "tool_calling":
                    calls = payload["choices"][0]["message"].get("tool_calls")
                    return isinstance(calls, list) and bool(calls)
                capabilities.detail[name] = "response did not match probe contract"
                return False
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                capabilities.detail[name] = type(exc).__name__
                return False

        try:
            capabilities.chat_completions = await attempt("chat_completions", {})
            capabilities.prompted_json = capabilities.chat_completions
            capabilities.native_json_object = await attempt(
                "native_json_object", {"response_format": {"type": "json_object"}}
            )
            capabilities.native_json_schema = await attempt(
                "native_json_schema",
                {
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "probe",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {"ok": {"type": "boolean"}},
                                "required": ["ok"],
                                "additionalProperties": False,
                            },
                        },
                    }
                },
            )
            capabilities.tool_calling = await attempt(
                "tool_calling",
                {
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "return_probe",
                                "description": "Return probe result",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"ok": {"type": "boolean"}},
                                    "required": ["ok"],
                                },
                            },
                        }
                    ],
                    "tool_choice": {
                        "type": "function",
                        "function": {"name": "return_probe"},
                    },
                },
            )
            return capabilities
        finally:
            if owned_client:
                await client.aclose()
