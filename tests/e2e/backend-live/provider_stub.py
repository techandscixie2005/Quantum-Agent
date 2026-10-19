"""Local HTTP model-provider double; all app, BFF and database logic stays real.

Only synthetic responses are emitted. Control endpoints belong to this test
provider process, never to the production API. Prompt/credential text is not logged.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_release = threading.Event()
_release.set()
_lock = threading.Lock()
_counts: dict[str, int] = {}


def _response(text: str) -> tuple[str, object]:
    if '"trend_quote"' in text or "trend, trend_quote, mechanism" in text:
        return "barrier_trend", {
            "trend": "uncertain",
            "trend_quote": "",
            "mechanism": "missing",
            "mechanism_quote": "",
            "contradictions": [],
            "rationale": "Synthetic fixture: numeric-only answers do not establish understanding.",
        }
    if '"attempt_type"' in text and '"candidate_prompt"' in text:
        return "commitment", {
            "attempt_type": "prediction",
            "candidate_prompt": "请先预测有限势垒的透射并给出理由。",
            "reason_summary": "Scripted provider fixture; not classroom evidence.",
        }
    if '"task_kind"' in text and '"relevant_concepts"' in text:
        return "interpretation", {
            "task_kind": "concept_question",
            "relevant_concepts": ["概率流"],
            "needs_scientific_verification": False,
            "confidence": 0.8,
        }
    if '"covered_relations"' in text:
        return "teach_back", {
            "covered_relations": [],
            "missing_relations": [],
            "contradictions": [],
            "unsupported_claims": [],
            "recommended_probe": "请解释概率流的含义。",
        }
    if '"observation_basis"' in text and '"summary"' in text:
        return "diagnosis", {
            "status": "observed",
            "summary": "Synthetic provider observed the submitted answer.",
            "observation_basis": ["student_attempt"],
            "reason": "Scripted fixture, no deficit inferred.",
        }
    if '"transfer_type"' in text and '"key_parameters"' in text:
        return "transfer", {
            "transfer_type": "conceptual",
            "prompt": "独立解释有限势垒宽度变化的影响。",
            "key_parameters": ["fixed E<V0"],
            "expected_observable": "qualitative width trend",
        }
    if '"orientation"' in text and '"next_question"' in text:
        return "teaching_response", {
            "orientation": "Synthetic HTTP provider response; not an educational outcome.",
            "claims": [],
            "next_question": "请说明你当前答案的依据。",
            "derivation_bridge": None,
        }
    return "probe", {"ok": True}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, value: object) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"fixture": "HTTP model provider double"})
        elif self.path == "/__test__/counts":
            with _lock:
                self._json(200, dict(_counts))
        else:
            self._json(404, {})

    def do_POST(self) -> None:
        size = min(int(self.headers.get("Content-Length", "0")), 2_000_000)
        body: dict[str, Any] = json.loads(self.rfile.read(size) or b"{}")
        if self.path == "/__test__/hold":
            _release.clear()
            self._json(200, {"holding": True})
            return
        if self.path == "/__test__/release":
            _release.set()
            self._json(200, {"holding": False})
            return
        if self.path != "/v1/chat/completions":
            self._json(404, {})
            return
        text = "\n".join(str(item.get("content", "")) for item in body.get("messages", []))
        task, result = _response(text)
        with _lock:
            _counts[task] = _counts.get(task, 0) + 1
        if "[hold-provider]" in text:
            with _lock:
                _counts["held"] = _counts.get("held", 0) + 1
            _release.wait(timeout=30)
        content = json.dumps(result, ensure_ascii=False)
        self._json(
            200,
            {
                "id": "synthetic-provider-fixture",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "fixture-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8312)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
