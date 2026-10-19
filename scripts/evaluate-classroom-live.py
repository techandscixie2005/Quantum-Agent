"""Opt-in synthetic model evaluation; never classroom or teacher-approval evidence.

From the repository root (PowerShell), without printing the key:
  $env:USTC_API = [Environment]::GetEnvironmentVariable('USTC_API', 'User')
  services/api/.venv/Scripts/python.exe scripts/evaluate-classroom-live.py --allow-live

Use --offline for fixture/science/projection checks with zero provider calls.
Only exact model alias deepseek-flash is requested; all text fallbacks resolve
to that same alias. At most 8 HTTP requests, 2048 output tokens per request,
64 KiB serialized request bodies, default 45 seconds per capability and 480
seconds total. Diagnostic overrides are bounded at 120 and 600 seconds;
--thinking-mode disabled explicitly asks the provider to disable thinking.
No DB/server, ingestion, publication, teacher approval, or user messaging occurs.
Outputs go into a new outputs/classroom-live-eval/<run UUID>/ directory. Source
hashes, synthetic answers, outputs, model outcomes, timing and available usage
are retained; credentials, HTTP error bodies and exception messages are not.
"""

from __future__ import annotations

# Source quotations retain their Chinese punctuation and mathematical primes.
# ruff: noqa: RUF001
import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx2

from quantum_agent.coding.agent import _verify_against_oracle
from quantum_agent.coding.models import CodeGenerationTask
from quantum_agent.config import Settings
from quantum_agent.db_models import AnswerReleaseLevel, TeachingMode
from quantum_agent.gateways import build_model_capability_registry
from quantum_agent.knowledge.evidence_packets import (
    EvidenceItem,
    EvidenceLocator,
    EvidencePacket,
    GraphContextEdge,
    GraphContextNode,
    RetrievalContribution,
)
from quantum_agent.knowledge.retrieval import RetrievalScope
from quantum_agent.llm.gateway import PydanticAIModelGateway
from quantum_agent.llm.observability import (
    failure_category,
    provider_request,
    provider_response,
    turn_scope,
)
from quantum_agent.llm.recording_budget import RecordingBudget
from quantum_agent.llm.routing import ModelProfile, ModelRouter, ModelTask
from quantum_agent.science import RectangularBarrierRequest, ScientificToolbox
from quantum_agent.teaching.agents import DiagnosisAgent, DiagnosisInput, EvidenceAgent
from quantum_agent.teaching.barrier_trend import evaluate_barrier_trend
from quantum_agent.teaching.course_packages import FINITE_BARRIERS
from quantum_agent.teaching.models import DiagnosisOutput, SoloFirstAttempt, TeachingTurnInput
from quantum_agent.teaching.solo_visibility import solo_visible_snapshot
from quantum_agent.teaching.state_machine import draft_response, interpret_turn
from quantum_agent.versioning import current_model_calls

ROOT = Path(__file__).resolve().parents[1]
MODEL = "deepseek-flash"
CASE: ContextVar[str] = ContextVar("evaluation_case", default="unassigned")
QUESTION = "无吸收、质量相同且0<E<V0的有限矩形势垒，固定E和V0只增大宽度，T如何变化？"
ANSWERS = {
    "correct": "透射率降低。E和V0不变使κ不变；更长禁阻区带来更长衰减距离，使透射振幅更小。",
    "incorrect": "因为E<V0，有限势垒里面波函数处处为零，所以透射率严格等于零，宽度没有影响。",
    "prerequisite_candidate": "我不知道概率流怎样由波函数和导数计算，也不知道边界处应匹配什么。",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identifier(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, "quantum-agent/synthetic-live-evaluation/" + name)


def bounded_seconds(value: str, *, maximum: float) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 < seconds <= maximum:
        raise argparse.ArgumentTypeError(f"seconds must be finite, positive and <= {maximum:g}")
    return seconds


def finalize_http_timing(calls: list[dict[str, Any]], case_name: str, ended: float) -> None:
    """Finalize at this case's exit, including cancellation, never at run end."""
    for entry in calls:
        if entry["case"] != case_name:
            continue
        started = entry.pop("started_monotonic", None)
        if isinstance(started, float):
            entry["elapsed_until_case_exit_ms"] = round((ended - started) * 1000, 3)
            entry["timing_basis"] = (
                "no_response_until_cancellation_or_case_exit"
                if entry["status"] == "no_response"
                else "response_headers_and_case_exit_recorded_separately"
            )


def fixture() -> tuple[EvidencePacket, dict[str, Any]]:
    path = ROOT / "content/barrier_demo/lecture.html"
    raw = path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    snippets = [
        "有限区间内两个指数项都应保留。右侧出射波的系数可能非零；",
        "概率流 j=(ℏ/m) Im(ψ*ψ′)。两侧波数相同，T=j透/j入=|F/A|²，R=|B/A|²。",
        "固定 E、V₀、m 时 κ 不变。a 增大使 κa 增大，"
        "sinh²(κa) 严格增大，因此有限势垒透射率 T 降低。",
    ]
    evidence = []
    for index, snippet in enumerate(snippets, 1):
        line, chunk = next((i, text) for i, text in enumerate(lines, 1) if snippet in text)
        evidence.append(
            EvidenceItem(
                evidence_id=identifier(f"evidence-{index}"),
                chunk_id=identifier(f"chunk-{index}"),
                document_id=identifier("document"),
                document_version_id=identifier("document-v1"),
                document_title="自编开发验收讲义；未获任课教师审核",
                document_version=1,
                source_file_name=path.name,
                source_file_sha256=sha(raw),
                source_chunk_sha256=sha(chunk.encode()),
                evidence_sha256=sha(snippet.encode()),
                curriculum_edition_id=identifier("edition"),
                chapter="有限矩形势垒",
                locator=EvidenceLocator(locator_type="text_lines", line_start=line, line_end=line),
                source_chunk=chunk,
                evidence_snippet=snippet,
                kind="course_material",
                authority_priority=0,
                contributions=[
                    RetrievalContribution(
                        channel="postgres_full_text", rank=index, fused_score=1 / index
                    )
                ],
            )
        )
    prerequisite = GraphContextNode(
        id=identifier("prerequisite"), node_type="Concept", name="概率流"
    )
    target = GraphContextNode(id=identifier("target"), node_type="Concept", name="有限势垒隧穿")
    packet = EvidencePacket(
        course_id=identifier("course"),
        curriculum_edition_id=identifier("edition"),
        query=QUESTION,
        coverage="sufficient",
        evidence=evidence,
        graph_nodes=[prerequisite, target],
        graph_edges=[
            GraphContextEdge(
                id=identifier("edge"),
                source_id=prerequisite.id,
                target_id=target.id,
                relation_type="PREREQUISITE_OF",
            )
        ],
    )
    return packet, {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha(raw),
        "publication": "offline fixture; no database publication",
        "graph": "synthetic directed prerequisite fixture",
        "teacher_approval": "not_performed",
        "packet": packet.model_dump(mode="json"),
    }


class FixtureRetriever:
    def __init__(self, packet: EvidencePacket) -> None:
        self.packet = packet

    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        return self.packet.model_copy(update={"query": query})


def deterministic_checks() -> dict[str, Any]:
    request = RectangularBarrierRequest(
        energy_eV=0.5,
        barrier_height_eV=20,
        barrier_width_m=0.5e-9,
        particle_mass_kg=9.1093837015e-31,
    )
    reference = ScientificToolbox().verify(request)
    task = CodeGenerationTask(
        student_question="Synthetic near-zero numeric comparison",
        known_variables={
            key: str(value) for key, value in request.model_dump().items() if key != "kind"
        },
        required_outputs=["T", "R", "conservation_error"],
        oracle_kind="rectangular_barrier_tunnelling",
    )
    transmission = float(reference.metrics.get("T", 0))
    comparisons = {
        str(factor): _verify_against_oracle(
            task,
            {
                "T": transmission * factor,
                "R": 1 - transmission * factor,
                "conservation_error": 0,
            },
        ).status.value
        for factor in (0, 1, 2)
    }
    first = SoloFirstAttempt(
        task_id=identifier("solo-task"),
        teaching_turn_id=identifier("solo-turn"),
        response="Synthetic original answer",
        submitted_at="2026-10-20T00:00:00+00:00",
    )
    snapshot = {
        "learning_native": {
            "phase": "solo_active",
            "solo_first_attempt": first.model_dump(mode="json"),
            "teacher_follow_up": {"probe": "withhold this help"},
        },
        "evidence_packet": {"evidence": ["withhold this source"]},
        "response": {},
    }
    visible = solo_visible_snapshot(snapshot)
    checks = {
        "finite_positive_tiny_reference": reference.status.value == "pass"
        and 0 < transmission < 1e-8,
        "zero_rejected": comparisons["0"] == "fail",
        "accurate_value_accepted": comparisons["1"] == "pass",
        "relative_error_rejected": comparisons["2"] == "fail",
        "solo_projection_hides_help": not visible["evidence_packet"]["evidence"]
        and visible["learning_native"]["teacher_follow_up"] is None,
        "solo_projection_preserves_initial_answer": visible["learning_native"]["solo_first_attempt"]
        == first.model_dump(mode="json"),
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "reference": reference.model_dump(mode="json"),
        "comparisons": comparisons,
        "limitation": "Projection only; database isolation/retry persistence are offline tests.",
    }


async def evaluate(
    report: dict[str, Any],
    output: Path,
    run_id: UUID,
    *,
    extended: bool,
    thinking_mode: Literal["enabled", "disabled"] | None,
    capability_seconds: float,
    total_seconds: float,
) -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USTC_TEXT_MODEL_OVERRIDE=MODEL,
        USTC_TEXT_THINKING_MODE=thinking_mode,
    )
    if settings.ustc_api is None:
        raise ValueError("credential_unavailable")
    registry = build_model_capability_registry(settings)
    for task in (ModelTask.REASONING, ModelTask.DIAGNOSIS, ModelTask.LIGHTWEIGHT):
        if [profile.provider_model for profile in registry.profiles_for(task)] != [MODEL]:
            raise ValueError("route_override_rejected")
    RecordingBudget.provision(
        output / "budget.sqlite",
        str(run_id),
        requests=8 if extended else 3,
        seconds=total_seconds,
        output_tokens=2048,
        request_bytes=65536,
    )
    os.environ["QUANTUM_AGENT_RECORDING_RUN_ID"] = str(run_id)
    os.environ["QUANTUM_AGENT_RECORDING_LEDGER"] = str(output / "budget.sqlite")
    http_calls: list[dict[str, Any]] = report["http_calls"]

    async def sent(request: httpx2.Request) -> None:
        requested = json.loads(request.content).get("model")
        if requested != MODEL:
            raise ValueError("unexpected_model_blocked")
        entry = {
            "case": CASE.get(),
            "requested_model": requested,
            "status": "no_response",
            "started_monotonic": time.monotonic(),
        }
        request.extensions["evaluation_entry"] = entry
        http_calls.append(entry)

    async def received(response: httpx2.Response) -> None:
        entry = response.request.extensions["evaluation_entry"]
        entry.update(
            status=response.status_code,
            response_headers_ms=round((time.monotonic() - entry["started_monotonic"]) * 1000, 3),
        )
        await response.aread()
        if response.status_code < 400:
            payload = response.json()
            entry["returned_model"] = str(payload.get("model", "unknown"))[:160]
            usage = payload.get("usage")
            entry["usage"] = {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if isinstance(usage, dict) and type(usage.get(key)) is int
            }

    async with httpx2.AsyncClient(
        timeout=capability_seconds,
        event_hooks={
            "request": [provider_request, sent],
            "response": [provider_response, received],
        },
    ) as client:

        def gateway(profile: ModelProfile) -> PydanticAIModelGateway:
            assert settings.ustc_api is not None
            return PydanticAIModelGateway(
                api_key=settings.ustc_api,
                base_url=settings.ustc_base_url,
                default_model=profile.provider_model,
                small_model=profile.provider_model,
                thinking_mode=profile.thinking_mode,
                max_retries=0,
                transient_retry_attempts=1,
                timeout_seconds=capability_seconds,
                attempt_wall_seconds=capability_seconds,
                transient_retry_budget_seconds=capability_seconds,
                model_http_client=client,
            )

        router = ModelRouter(
            registry=registry,
            gateway_factory=gateway,
            fallback_budget_seconds=capability_seconds,
        )
        packet, _ = fixture()
        bundle = await EvidenceAgent(FixtureRetriever(packet)).gather(
            scope=RetrievalScope(
                course_id=packet.course_id, curriculum_edition_id=packet.curriculum_edition_id
            ),
            query=QUESTION,
        )
        diagnoses: dict[str, DiagnosisOutput] = {}

        async def case(name: str, operation: Callable[[], Awaitable[dict[str, Any]]]) -> None:
            token = CASE.set(name)
            start = time.monotonic()
            data: dict[str, Any] = {"passed": False, "failure_category": "cancelled"}
            try:
                with turn_scope(run_id, identifier(name)):
                    try:
                        data = await operation()
                        checks = data["checks"]
                        data["passed"] = bool(checks) and all(checks.values())
                    except Exception as exc:
                        data = {
                            "passed": False,
                            "failure_type": type(exc).__name__,
                            "failure_category": failure_category(exc),
                        }
                    finally:
                        ended = time.monotonic()
                        finalize_http_timing(http_calls, name, ended)
                        data.update(
                            name=name,
                            latency_ms=round((ended - start) * 1000, 3),
                            model_calls=current_model_calls(),
                        )
                        report["cases"].append(data)
            finally:
                CASE.reset(token)

        async def diagnose(name: str) -> dict[str, Any]:
            answer = ANSWERS.get(name)
            result, degraded = await DiagnosisAgent(router).diagnose(
                diagnosis_input=DiagnosisInput(
                    request=TeachingTurnInput(
                        mode=TeachingMode.LEARN_CONCEPTS, message=QUESTION, student_attempt=answer
                    ),
                    evidence_bundle=bundle,
                )
            )
            diagnoses[name] = result
            checks = {
                "not_degraded": not degraded,
                "supported_prerequisites_only": all(
                    item.student_quote in (answer or "") for item in result.prerequisite_support
                )
                and set(result.missing_prerequisites)
                == {item.prerequisite for item in result.prerequisite_support},
            }
            if name == "no_attempt":
                checks["no_unsupported_diagnosis_or_call"] = not current_model_calls() and (
                    not result.missing_prerequisites and result.first_error is None
                )
            else:
                checks["actual_model_success"] = any(
                    call["outcome"] == "completed" for call in current_model_calls()
                )
            if name == "correct":
                checks["correct_answer_not_marked_wrong"] = not result.likely_misconception and (
                    result.first_error is None or result.first_error.kind.value == "no_clear_error"
                )
            if name == "incorrect":
                checks["error_localized_as_inference"] = (
                    result.status.value == "model_inference"
                    and (
                        result.first_error is not None
                        and result.first_error.kind.value not in {"no_clear_error", "inconclusive"}
                    )
                )
            return {
                "checks": checks,
                "synthetic_answer": answer,
                "diagnosis": result.model_dump(mode="json"),
            }

        async def guide(name: str) -> dict[str, Any]:
            request = TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS, message=QUESTION, student_attempt=ANSWERS[name]
            )
            response, validation, degraded = await draft_response(
                request=request,
                packet=packet,
                diagnosis=diagnoses[name],
                release_level=AnswerReleaseLevel.HINT,
                scientific_results=[],
                model_gateway=router,
            )
            return {
                "checks": {
                    "actual_model_success": not degraded
                    and any(call["outcome"] == "completed" for call in current_model_calls()),
                    "evidence_validation": validation.passed,
                    "answer_grounded_probe": bool(response.student_answer_anchor)
                    and str(response.student_answer_anchor) in ANSWERS[name],
                },
                "response": response.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            }

        async def trend(name: str) -> dict[str, Any]:
            result = await evaluate_barrier_trend(ANSWERS[name], prompt=QUESTION, gateway=router)
            return {
                "checks": {
                    "structured_model_result": result is not None,
                    "expected_assessment": result is not None
                    and result.accepted(ANSWERS[name]) == (name == "correct"),
                },
                "evaluation": result.model_dump() if result else None,
            }

        async def interpret() -> dict[str, Any]:
            result, degraded = await interpret_turn(
                request=TeachingTurnInput(mode=TeachingMode.LEARN_CONCEPTS, message=QUESTION),
                model_gateway=router,
            )
            return {
                "checks": {"actual_model_success": not degraded and bool(current_model_calls())},
                "interpretation": result.model_dump(mode="json"),
            }

        async with asyncio.timeout(total_seconds):
            if extended:
                await case("interpret", interpret)
            for name in ("no_attempt", "correct", "incorrect"):
                await case("diagnosis_" + name, partial(diagnose, name))
            if extended:
                await case(
                    "diagnosis_prerequisite_candidate", partial(diagnose, "prerequisite_candidate")
                )
                await case("guidance_correct", partial(guide, "correct"))
                await case("trend_correct", partial(trend, "correct"))
                await case("trend_incorrect", partial(trend, "incorrect"))
            await case("guidance_incorrect", partial(guide, "incorrect"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--allow-live", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--extended", action="store_true", help="8 live calls instead of 3")
    parser.add_argument(
        "--thinking-mode",
        choices=("enabled", "disabled"),
        help="Explicit provider thinking mode; default leaves the provider default unchanged",
    )
    parser.add_argument(
        "--capability-seconds",
        type=partial(bounded_seconds, maximum=120),
        default=45,
        help="Per-capability wall limit in seconds, finite and >0, at most 120 (default 45)",
    )
    parser.add_argument(
        "--total-seconds",
        type=partial(bounded_seconds, maximum=600),
        default=480,
        help="Total run wall limit in seconds, finite and >0, at most 600 (default 480)",
    )
    parser.add_argument(
        "--source-snapshot",
        type=Path,
        default=ROOT / "docs/implementation/evidence/classroom-20261019/source-snapshot.json",
    )
    args = parser.parse_args()
    run_id = uuid4()
    output = ROOT / "outputs/classroom-live-eval" / str(run_id)
    output.mkdir(parents=True, exist_ok=False)
    _, source = fixture()
    snapshot = json.loads(args.source_snapshot.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "schema_version": "synthetic-live-classroom-evaluation/2",
        "label": "AUTOMATED SYNTHETIC EVALUATION; NOT CLASSROOM RESULTS OR TEACHER APPROVAL",
        "run_id": str(run_id),
        "started_at": datetime.now(UTC).isoformat(),
        "model_alias": MODEL,
        "thinking_mode": args.thinking_mode,
        "model_weights_version": "unknown; aliases/returned names are not weight attestations",
        "cost": "unknown; token usage is recorded when supplied by the provider",
        "python": platform.python_version(),
        "script_sha256": sha(Path(__file__).read_bytes()),
        "source_snapshot_sha256": sha(args.source_snapshot.read_bytes()),
        "base_revision": snapshot.get("base_revision", "unknown"),
        "dirty": snapshot.get("dirty"),
        "source_tree_sha256": snapshot.get("source_tree_sha256"),
        "fixture": source,
        "course_package": FINITE_BARRIERS.reference().model_dump(mode="json"),
        "budgets": {
            "http_requests": 8 if args.extended else 3,
            "output_tokens_each": 2048,
            "request_bytes_each": 65536,
            "capability_seconds": args.capability_seconds,
            "total_seconds": args.total_seconds,
        },
        "live_requested": args.allow_live,
        "extended": args.extended,
        "http_calls": [],
        "cases": [],
        "not_exercised": [
            "database/replica concurrency",
            "classroom outcomes",
            "teacher approvals",
            "external unaided behavior",
        ],
        "deterministic": deterministic_checks(),
    }
    if args.allow_live:
        try:
            asyncio.run(
                evaluate(
                    report,
                    output,
                    run_id,
                    extended=args.extended,
                    thinking_mode=args.thinking_mode,
                    capability_seconds=args.capability_seconds,
                    total_seconds=args.total_seconds,
                )
            )
        except Exception as exc:
            report["run_failure_type"] = type(exc).__name__
            report["run_failure_category"] = failure_category(exc)
    for call in report["http_calls"]:
        matching: dict[str, Any] = next(
            (item for item in report["cases"] if item["name"] == call["case"]), {}
        )
        routed = matching.get("model_calls", [])
        call["structured_outcome"] = routed[-1]["outcome"] if routed else "incomplete"
    report["passed"] = report["deterministic"]["passed"] and (
        not args.allow_live
        or (
            "run_failure_type" not in report
            and len(report["cases"]) == (9 if args.extended else 4)
            and all(case["passed"] for case in report["cases"])
        )
    )
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(output / "report.json"),
                "passed": report["passed"],
                "http_requests": len(report["http_calls"]),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
