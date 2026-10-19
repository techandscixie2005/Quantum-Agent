"""Bounded synthetic latency investigation, not a classroom/model-quality evaluation.

PowerShell from repository root, without printing the credential:
  $env:USTC_API = [Environment]::GetEnvironmentVariable('USTC_API', 'User')
  services/api/.venv/Scripts/python.exe scripts/investigate-model-latency.py --allow-live

Eight POSTs maximum, exact deepseek-flash, 64 output tokens, no retries, fresh
httpx2 clients, 120 seconds per request and 900 seconds total. Two ABBA blocks
compare default/disabled thinking, then nonstream/stream with thinking disabled.
Only the tested request fields differ. No held-out course/assessment keys are
loaded. Trace event names/times are saved; trace info, headers, provider error
bodies, credentials and private reasoning are never saved. n=2 per condition is
descriptive; queueing versus reasoning latency cannot be causally established.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx2
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
MODEL = "deepseek-flash"
PROMPT = 'Reply exactly with this JSON and nothing else: {"ok":true}'
MAX_BODY = 1024 * 1024


class TinyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ok: Literal[True]


def plan() -> list[dict[str, Any]]:
    return [
        {
            "case": f"thinking-{index}",
            "block": "thinking",
            "condition": condition,
            "thinking": None if condition == "default" else "disabled",
            "stream": False,
        }
        for index, condition in enumerate(("default", "disabled", "disabled", "default"), 1)
    ] + [
        {
            "case": f"stream-{index}",
            "block": "stream",
            "condition": condition,
            "thinking": "disabled",
            "stream": condition == "stream",
        }
        for index, condition in enumerate(("nonstream", "stream", "stream", "nonstream"), 1)
    ]


def payload(case: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "max_tokens": 64,
        "stream": case["stream"],
    }
    if case["thinking"] is not None:
        body["thinking"] = {"type": case["thinking"]}
    return body


def checkpoint(report: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(".pending")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


class Probe:
    def __init__(
        self, case: dict[str, Any], *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.case, self.clock = case, clock
        self.started = clock()
        self.content = ""
        self.buffer = b""
        self.frame: list[bytes] = []
        self.case.update(
            trace=[],
            usage=None,
            returned_model="unknown",
            response_bytes=0,
            trace_events_omitted=0,
            sse_events=0,
        )

    def elapsed(self) -> float:
        return round((self.clock() - self.started) * 1000, 3)

    async def trace(self, name: str, info: dict[str, Any]) -> None:
        # Do not inspect, copy, stringify, serialize, or log info: it may hold
        # authorization headers, response bodies, socket objects or exceptions.
        if len(self.case["trace"]) < 256:
            self.case["trace"].append({"event": name, "at_ms": self.elapsed()})
        else:
            self.case["trace_events_omitted"] += 1

    def usage(self, data: dict[str, Any]) -> None:
        usage = data.get("usage")
        if isinstance(usage, dict):
            filtered = {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if type(usage.get(key)) is int and usage[key] >= 0
            }
            if filtered:
                self.case["usage"] = filtered
        if isinstance(data.get("model"), str):
            self.case["returned_model"] = data["model"][:160]

    def sse(self, chunk: bytes) -> None:
        self.buffer += chunk
        while b"\n" in self.buffer:
            line, _, self.buffer = self.buffer.partition(b"\n")
            line = line.rstrip(b"\r")
            if line == b"":
                self.event()
            elif line.startswith(b"data:"):
                self.frame.append(line[5:].lstrip(b" "))

    def event(self) -> None:
        if not self.frame:
            return
        raw = b"\n".join(self.frame)
        self.frame = []
        self.case.setdefault("first_sse_event_ms", self.elapsed())
        self.case["sse_events"] += 1
        if raw == b"[DONE]":
            self.case["sse_done"] = True
            return
        started = self.clock()
        data = json.loads(raw)
        self.case["outer_json_parse_ms"] = (
            self.case.get("outer_json_parse_ms", 0) + (self.clock() - started) * 1000
        )
        if not isinstance(data, dict):
            raise ValueError("invalid_sse_object")
        self.usage(data)
        for choice in data.get("choices", []):
            delta = choice.get("delta", {})
            if isinstance(delta.get("content"), str) and delta["content"]:
                self.case.setdefault("first_content_chunk_ms", self.elapsed())
                self.content += delta["content"]
            if isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"]:
                self.case.setdefault("first_reasoning_chunk_ms", self.elapsed())
                self.case["reasoning_characters"] = self.case.get("reasoning_characters", 0) + len(
                    delta["reasoning_content"]
                )
            if choice.get("finish_reason") is not None:
                self.case["finish_reason"] = str(choice["finish_reason"])[:80]

    def complete(self, body: bytes, *, stream: bool) -> None:
        if stream:
            if self.buffer:
                self.sse(b"\n")
            self.event()
        else:
            started = self.clock()
            data = json.loads(body)
            self.case["outer_json_parse_ms"] = (self.clock() - started) * 1000
            self.usage(data)
            choice = data["choices"][0]
            self.content = choice["message"].get("content") or ""
            self.case["finish_reason"] = str(choice.get("finish_reason", "unknown"))[:80]
            # Nonstream token arrival is unobservable; completion arrives as a
            # single response. Never call the first body byte a first token.
        started = self.clock()
        result = TinyResult.model_validate_json(self.content)
        self.case["content_json_schema_ms"] = (self.clock() - started) * 1000
        self.case["structured_result"] = result.model_dump()
        self.case["content_characters"] = len(self.content)


async def run_case(
    case: dict[str, Any],
    *,
    key: str,
    capability_seconds: float = 120,
    client_factory: Callable[[], httpx2.AsyncClient] | None = None,
) -> None:
    probe = Probe(case)
    case["status"] = "running"
    body = json.dumps(payload(case), ensure_ascii=False, separators=(",", ":")).encode()
    case["request_sha256"] = hashlib.sha256(body).hexdigest()
    case["request_bytes"] = len(body)
    factory = client_factory or (lambda: httpx2.AsyncClient(timeout=120, follow_redirects=False))
    try:
        async with asyncio.timeout(capability_seconds), factory() as client:
            case["client_ready_ms"] = probe.elapsed()
            request = client.build_request(
                "POST",
                "https://api.llm.ustc.edu.cn/v1/chat/completions",
                content=body,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                extensions={"trace": probe.trace},
            )
            case["http_attempts"] = 1
            case["request_started_ms"] = probe.elapsed()
            response = await client.send(request, stream=True)
            try:
                case["response_headers_ms"] = probe.elapsed()
                case["http_status"] = response.status_code
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    case.setdefault("first_body_chunk_ms", probe.elapsed())
                    case["response_bytes"] += len(chunk)
                    if case["response_bytes"] > MAX_BODY:
                        raise ValueError("response_limit_exceeded")
                    if response.status_code < 400:
                        if case["stream"]:
                            probe.sse(chunk)
                        else:
                            content.extend(chunk)
                case["body_complete_ms"] = probe.elapsed()
                if response.status_code >= 400:
                    case["status"] = "http_error"
                    return
                probe.complete(bytes(content), stream=case["stream"])
                case["status"] = "completed"
            finally:
                await response.aclose()
    except Exception as exc:
        case["status"] = (
            "timeout" if isinstance(exc, (TimeoutError, httpx2.TimeoutException)) else "failed"
        )
        case["failure_type"] = type(exc).__name__
        # Unknown usage on no-response must never be represented as zero.
    finally:
        case["elapsed_until_case_exit_ms"] = probe.elapsed()
        token_chunks = [
            case[key]
            for key in ("first_content_chunk_ms", "first_reasoning_chunk_ms")
            if key in case
        ]
        case["first_observed_token_chunk_ms"] = min(token_chunks) if token_chunks else None
        if "response_headers_ms" not in case:
            case["timing_basis"] = "no_response_until_cancellation_or_case_exit"
        else:
            case["timing_basis"] = "observed_headers_body_and_case_exit"


def describe(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for block, conditions in (
        ("thinking", ("default", "disabled")),
        ("stream", ("nonstream", "stream")),
    ):
        for condition in conditions:
            items = [
                case for case in cases if case["block"] == block and case["condition"] == condition
            ]
            completed = [
                case["elapsed_until_case_exit_ms"]
                for case in items
                if case["status"] == "completed"
            ]
            summaries.append(
                {
                    "block": block,
                    "condition": condition,
                    "n_attempted": sum(case.get("http_attempts", 0) for case in items),
                    "n_completed": len(completed),
                    "completed_total_ms_median": statistics.median(completed)
                    if completed
                    else None,
                    "timeouts": sum(case["status"] == "timeout" for case in items),
                }
            )
    return summaries


async def run_protocol(
    report: dict[str, Any],
    path: Path,
    *,
    key: str,
    total_seconds: float = 900,
    capability_seconds: float = 120,
    client_factory: Callable[[], httpx2.AsyncClient] | None = None,
) -> None:
    started = time.monotonic()
    for case in report["cases"]:
        remaining = total_seconds - (time.monotonic() - started)
        if remaining <= 0:
            case["status"] = "not_started_total_deadline"
            checkpoint(report, path)
            continue
        case["started_at"] = datetime.now(UTC).isoformat()
        case["status"] = "running"
        checkpoint(report, path)
        await run_case(
            case,
            key=key,
            capability_seconds=min(capability_seconds, remaining),
            client_factory=client_factory,
        )
        report["summary"] = describe(report["cases"])
        checkpoint(report, path)
        print(
            json.dumps(
                {
                    "case": case["case"],
                    "status": case["status"],
                    "elapsed_ms": case["elapsed_until_case_exit_ms"],
                }
            ),
            flush=True,
        )
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", required=True)
    parser.parse_args()
    for logger in ("httpcore2", "httpx2", "httpcore", "httpx"):
        logging.getLogger(logger).setLevel(logging.WARNING)
    run_id = str(uuid4())
    directory = ROOT / "outputs/model-latency" / run_id
    directory.mkdir(parents=True)
    path = directory / "report.json"
    report: dict[str, Any] = {
        "schema_version": "synthetic-model-latency/1",
        "run_id": run_id,
        "label": "AUTOMATED SYNTHETIC LATENCY DIAGNOSTIC; NOT CLASSROOM OR QUALITY EVIDENCE",
        "started_at": datetime.now(UTC).isoformat(),
        "model_alias": MODEL,
        "model_weights_version": "unknown",
        "cost": "unknown",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in ("httpx2", "httpcore2")},
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "prompt": PROMPT,
        "endpoint": "https://api.llm.ustc.edu.cn/v1/chat/completions",
        "limits": {
            "http_posts": 8,
            "output_tokens_each": 64,
            "capability_seconds": 120,
            "total_seconds": 900,
            "response_bytes_each": MAX_BODY,
            "retries": 0,
        },
        "controls": {
            "fresh_client_each_case": True,
            "temperature": 0,
            "seed": "not_set; provider support unverified",
            "http2": False,
            "trust_env": True,
            "dns_preflight": "not_measured",
            "connect_tcp": "combined resolver/TCP phase; proxy may resolve target DNS",
        },
        "limitations": [
            "n=2 per condition; descriptive only",
            "queueing, reasoning and deployment load effects cannot be causally separated",
            "first observed SSE content/reasoning chunk is not individual-token timing",
            "nonstream first-token time is unobservable",
            "no held-out assessment key supplied",
        ],
        "cases": [{**case, "status": "not_started", "http_attempts": 0} for case in plan()],
    }
    checkpoint(report, path)
    key = os.environ.get("USTC_API")
    if not key:
        report["run_failure"] = "credential_unavailable"
    else:
        try:
            asyncio.run(run_protocol(report, path, key=key))
        except Exception as exc:
            report["run_failure_type"] = type(exc).__name__
    report["completed_at"] = datetime.now(UTC).isoformat()
    report["passed"] = all(case["status"] == "completed" for case in report["cases"])
    checkpoint(report, path)
    print(
        json.dumps(
            {
                "report": str(path),
                "passed": report["passed"],
                "http_posts": sum(case["http_attempts"] for case in report["cases"]),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
