"""Local protocol/SSE/secret-redaction checks; these never contact a provider."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/investigate-model-latency.py"


@pytest.fixture
def protocol() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT))


def test_abba_protocol_changes_one_factor_only(protocol: dict[str, Any]) -> None:
    cases = protocol["plan"]()
    assert len(cases) == 8
    assert [case["condition"] for case in cases[:4]] == [
        "default",
        "disabled",
        "disabled",
        "default",
    ]
    assert [case["stream"] for case in cases[4:]] == [False, True, True, False]
    for case in cases:
        body = protocol["payload"](case)
        assert body["model"] == "deepseek-flash" and body["max_tokens"] == 64
        assert body["temperature"] == 0 and "seed" not in body
        assert body["messages"] == [{"role": "user", "content": protocol["PROMPT"]}]
    default = protocol["payload"](cases[0])
    disabled = protocol["payload"](cases[1])
    assert {
        key for key in default.keys() | disabled.keys() if default.get(key) != disabled.get(key)
    } == {"thinking"}
    normal = protocol["payload"](cases[4])
    streamed = protocol["payload"](cases[5])
    assert {key for key in normal if normal[key] != streamed[key]} == {"stream"}


async def test_trace_callback_ignores_sensitive_info_and_sse_tracks_split_frames(
    protocol: dict[str, Any],
) -> None:
    class Unsafe:
        def __repr__(self) -> str:
            raise AssertionError("trace info must not be inspected")

    ticks = [0.0]
    case: dict[str, Any] = {}
    probe = protocol["Probe"](case, clock=lambda: ticks[0])
    ticks[0] = 0.1
    await probe.trace("connection.connect_tcp.started", {"authorization": Unsafe()})
    assert case["trace"] == [{"event": "connection.connect_tcp.started", "at_ms": 100}]
    for chunk in (
        b'data: {"model":"deepseek-flash","choices":[{"delta":{"reasoning_content":"private',
        b' reasoning not persisted"}}]}\r\n\r\n',
        b'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"true}"},"finish_reason":"stop"}],',
        b'"usage":{"prompt_tokens":5,"completion_tokens":4,"total_tokens":9}}\n\n',
        b"data: [DONE]\n\n",
    ):
        ticks[0] += 0.1
        probe.sse(chunk)
    probe.complete(b"", stream=True)
    encoded = json.dumps(case)
    assert "private reasoning" not in encoded and "authorization" not in encoded
    assert case["structured_result"] == {"ok": True}
    assert case["returned_model"] == "deepseek-flash"
    assert case["usage"]["total_tokens"] == 9
    assert case["first_reasoning_chunk_ms"] < case["first_content_chunk_ms"]
    assert case["sse_done"]


async def test_full_eight_case_protocol_has_fresh_clients_and_no_retry_or_raw_secrets(
    protocol: dict[str, Any],
    tmp_path: Path,
) -> None:
    clients: list[httpx2.AsyncClient] = []
    seen: list[dict[str, Any]] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        seen.append(body)
        await request.extensions["trace"](
            "http11.send_request_body.complete", {"headers": "synthetic-secret-key"}
        )
        if body["stream"]:
            return httpx2.Response(
                200,
                content=(
                    b'data: {"model":"deepseek-flash","choices":[{"delta":'
                    b'{"content":"{\\"ok\\":true}"},"finish_reason":"stop"}]}\n\n'
                    b"data: [DONE]\n\n"
                ),
            )
        return httpx2.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        )

    def client() -> httpx2.AsyncClient:
        result = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        clients.append(result)
        return result

    report = {
        "cases": [
            {**case, "status": "not_started", "http_attempts": 0} for case in protocol["plan"]()
        ]
    }
    path = tmp_path / "report.json"
    await protocol["run_protocol"](report, path, key="synthetic-secret-key", client_factory=client)
    assert len(clients) == len(seen) == 8
    assert all(item.is_closed for item in clients)
    assert all(case["status"] == "completed" for case in report["cases"])
    assert all(item["max_tokens"] == 64 for item in seen)
    assert "synthetic-secret-key" not in path.read_text()
    assert sum(case["http_attempts"] for case in report["cases"]) == 8


async def test_timeout_is_incrementally_saved_as_unknown_usage_without_retry(
    protocol: dict[str, Any],
    tmp_path: Path,
) -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("synthetic-secret-key must not appear", request=request)

    report = {
        "cases": [
            {**case, "status": "not_started", "http_attempts": 0} for case in protocol["plan"]()
        ]
    }
    path = tmp_path / "report.json"
    await protocol["run_protocol"](
        report,
        path,
        key="synthetic-secret-key",
        client_factory=lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    assert all(case["status"] == "timeout" and case["usage"] is None for case in report["cases"])
    assert all(case["http_attempts"] == 1 for case in report["cases"])
    assert "synthetic-secret-key" not in path.read_text()
    assert all(summary["n_completed"] == 0 for summary in report["summary"])


async def test_total_deadline_prevents_later_requests(
    protocol: dict[str, Any],
    tmp_path: Path,
) -> None:
    sent = 0
    ticks = [0.0]
    # Replace only this script's time binding. Never patch asyncio's shared
    # monotonic clock: Windows scheduler granularity can wake a tiny timer early.
    protocol["run_protocol"].__globals__["time"] = SimpleNamespace(monotonic=lambda: ticks[0])

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sent
        sent += 1
        ticks[0] = 1.0
        raise httpx2.ReadTimeout("synthetic deadline", request=request)

    report = {
        "cases": [
            {**case, "status": "not_started", "http_attempts": 0} for case in protocol["plan"]()
        ]
    }
    await protocol["run_protocol"](
        report,
        tmp_path / "report.json",
        key="synthetic-secret-key",
        total_seconds=0.02,
        capability_seconds=0.02,
        client_factory=lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    assert sent == 1
    assert all(case["http_attempts"] == 0 for case in report["cases"][1:])
