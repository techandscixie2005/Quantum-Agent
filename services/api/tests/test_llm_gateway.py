from __future__ import annotations

import json
from typing import Any

import httpx
import httpx2
import pytest
from pydantic import BaseModel, ConfigDict, SecretStr

from quantum_agent.llm.gateway import (
    GatewayError,
    Message,
    PermanentGatewayError,
    PydanticAIModelGateway,
    _is_transient_exception,
    _retry_transient,
)


class StructuredProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: int


def _chat_response(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
    }


async def test_structured_generation_is_validated_through_current_pydantic_ai() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer backend-test-token"
        return httpx2.Response(200, json=_chat_response('{"value": 7}'))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    gateway = PydanticAIModelGateway(
        api_key=SecretStr("backend-test-token"),
        model_http_client=client,
        max_retries=0,
    )
    try:
        result = await gateway.structured_generate(
            task="structured_probe",
            messages=[
                Message(role="system", content="Return grounded structured data."),
                Message(role="user", content="Use value seven."),
            ],
            output_type=StructuredProbe,
        )
    finally:
        await client.aclose()

    assert result == StructuredProbe(value=7)


async def test_capability_probe_records_only_observed_features() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload.get("tools"):
            body = _chat_response("")
            body["choices"][0]["message"]["content"] = None
            body["choices"][0]["message"]["tool_calls"] = [
                {
                    "id": "call-test",
                    "type": "function",
                    "function": {"name": "return_probe", "arguments": '{"ok":true}'},
                }
            ]
            return httpx.Response(200, json=body)
        return httpx.Response(200, json=_chat_response('{"ok": true}'))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = PydanticAIModelGateway(
        api_key=SecretStr("backend-test-token"),
        probe_http_client=client,
    )
    try:
        capabilities = await gateway.probe()
    finally:
        await client.aclose()

    assert capabilities.chat_completions is True
    assert capabilities.prompted_json is True
    assert capabilities.native_json_object is True
    assert capabilities.native_json_schema is True
    assert capabilities.tool_calling is True


# ---------------------------------------------------------------------------
# Transient retry / backoff (PRD V3.0 §18: bounded resilient retries for
# timeout, 429, transient 5xx; no retry on auth/config 4xx).
# ---------------------------------------------------------------------------


def test_is_transient_exception_classifies_timeout_and_rate_limit() -> None:
    assert _is_transient_exception(httpx.TimeoutException("slow")) is True
    assert _is_transient_exception(httpx.ConnectError("nope")) is True
    transient_status = httpx.HTTPStatusError(
        "rate limited",
        request=httpx.Request("POST", "https://x"),
        response=httpx.Response(429),
    )
    assert _is_transient_exception(transient_status) is True
    server_error = httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("POST", "https://x"),
        response=httpx.Response(503),
    )
    assert _is_transient_exception(server_error) is True


def test_is_transient_exception_does_not_retry_auth_4xx() -> None:
    auth_error = httpx.HTTPStatusError(
        "forbidden",
        request=httpx.Request("POST", "https://x"),
        response=httpx.Response(401),
    )
    assert _is_transient_exception(auth_error) is False
    config_error = httpx.HTTPStatusError(
        "bad request",
        request=httpx.Request("POST", "https://x"),
        response=httpx.Response(400),
    )
    assert _is_transient_exception(config_error) is False


async def test_retry_transient_retries_on_transient_then_succeeds() -> None:
    calls = {"n": 0}

    async def op() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.TimeoutException("transient")
        return "ok"

    result = await _retry_transient(
        op,
        max_attempts=5,
        base_delay=0.001,
        max_delay=0.01,
        label="test",
    )
    assert result == "ok"
    assert calls["n"] == 3


async def test_retry_transient_does_not_retry_non_transient() -> None:
    calls = {"n": 0}

    async def op() -> str:
        calls["n"] += 1
        raise ValueError("non-transient config error")

    with pytest.raises(ValueError):
        await _retry_transient(
            op,
            max_attempts=5,
            base_delay=0.001,
            max_delay=0.01,
            label="test",
        )
    assert calls["n"] == 1


async def test_retry_transient_gives_up_after_max_attempts() -> None:
    calls = {"n": 0}

    async def op() -> str:
        calls["n"] += 1
        raise httpx.TimeoutException("always transient")

    with pytest.raises(httpx.TimeoutException):
        await _retry_transient(
            op,
            max_attempts=3,
            base_delay=0.001,
            max_delay=0.01,
            label="test",
        )
    assert calls["n"] == 3


async def test_structured_generate_retries_transient_429_then_succeeds() -> None:
    """End-to-end: the gateway retries a 429 then succeeds without surfacing it."""

    calls = {"n": 0}

    async def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx2.Response(429, json={"error": "rate limited"})
        return httpx2.Response(200, json=_chat_response('{"value": 11}'))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    gateway = PydanticAIModelGateway(
        api_key=SecretStr("backend-test-token"),
        model_http_client=client,
        max_retries=0,
        transient_retry_attempts=5,
        transient_retry_base_delay=0.001,
        transient_retry_max_delay=0.01,
    )
    try:
        result = await gateway.structured_generate(
            task="structured_probe",
            messages=[Message(role="user", content="Return value 11.")],
            output_type=StructuredProbe,
        )
    finally:
        await client.aclose()
    assert result.value == 11
    assert calls["n"] == 3


async def test_structured_generate_does_not_retry_auth_401() -> None:
    """Auth failures are configuration errors; retrying cannot fix them."""

    calls = {"n": 0}

    async def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(401, json={"error": "invalid api key"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    gateway = PydanticAIModelGateway(
        api_key=SecretStr("backend-test-token"),
        model_http_client=client,
        max_retries=0,
        transient_retry_attempts=5,
        transient_retry_base_delay=0.001,
        transient_retry_max_delay=0.01,
    )
    with pytest.raises(GatewayError):
        try:
            await gateway.structured_generate(
                task="structured_probe",
                messages=[Message(role="user", content="x")],
                output_type=StructuredProbe,
            )
        finally:
            await client.aclose()
    assert calls["n"] == 1, "auth 401 must not be retried"


async def test_retry_transient_deadline_caps_total_retry_budget() -> None:
    """PRD V3.1 P1-2: the retry deadline caps the total retry budget.

    When the next sleep would cross the deadline, the retry loop truncates
    the sleep to the remaining budget and surfaces the last transient
    error after the next attempt.  This keeps a single gateway call from
    burning the entire 240s proxy budget (without the deadline, the loop
    would sleep 10s between each of 5 attempts).
    """

    import time as _time

    calls = {"n": 0}

    async def op() -> str:
        calls["n"] += 1
        raise httpx.TimeoutException("always transient")

    start = _time.monotonic()
    with pytest.raises(httpx.TimeoutException):
        await _retry_transient(
            op,
            max_attempts=5,
            base_delay=10.0,
            max_delay=10.0,
            label="test",
            deadline=start + 0.05,
        )
    # The first attempt runs immediately and fails.  The retry loop
    # truncates the 10s sleep to the remaining ~0.05s budget, runs the
    # second attempt, and then stops because the deadline has passed.
    # Without the deadline, the loop would sleep 10s five times.
    assert calls["n"] == 2
    elapsed = _time.monotonic() - start
    assert elapsed < 1.0, "deadline must prevent the full 10s sleep"


async def test_structured_generate_classifies_401_as_permanent() -> None:
    """PRD V3.1 P1-2: 401/403/400 must raise PermanentGatewayError.

    The router relies on this distinct type to short-circuit across
    profiles instead of retrying a permanent error against every fallback.
    """

    calls = {"n": 0}

    async def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(401, json={"error": "invalid api key"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    gateway = PydanticAIModelGateway(
        api_key=SecretStr("backend-test-token"),
        model_http_client=client,
        max_retries=0,
        transient_retry_attempts=5,
        transient_retry_base_delay=0.001,
        transient_retry_max_delay=0.01,
    )
    with pytest.raises(PermanentGatewayError):
        try:
            await gateway.structured_generate(
                task="structured_probe",
                messages=[Message(role="user", content="x")],
                output_type=StructuredProbe,
            )
        finally:
            await client.aclose()
    assert calls["n"] == 1
