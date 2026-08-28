"""The Coding Agent: writes task-specific Python, runs it, verifies it (PRD V3.1 §6).

The agent is NOT a wrapper around a prewritten domain solver.  For each
:class:`CodeGenerationTask` it asks the model to write a fresh program that
computes the requested outputs, validates the program with the AST safety
gate, executes it in the sandbox, and cross-checks the program's numeric
output against the deterministic oracle in :mod:`quantum_agent.science.toolbox`.

The repair loop is bounded to ``max_repairs`` (default 2).  When the sandbox
reports an execution failure, the structured error is fed back to the model
as a :class:`CodeRepairAttempt`.  After the budget is exhausted the agent
returns the last result with ``CodeVerificationStatus.INCONCLUSIVE`` and a
transparent failure note — it never fabricates a successful computation and
never relabels ``FAIL`` as ``PASS``.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from pydantic import ValidationError

from quantum_agent.coding.models import (
    CodeArtifact,
    CodeArtifactRun,
    CodeExecutionResult,
    CodeGenerationTask,
    CodeRepairAttempt,
    CodeVerificationResult,
    CodeVerificationStatus,
    CodingProgress,
)
from quantum_agent.coding.safety import CodeSafetyError, validate_code_safety
from quantum_agent.coding.sandbox import (
    RemoteSandbox,
    SandboxDisabled,
    SandboxError,
    SubprocessSandbox,
)
from quantum_agent.llm.gateway import GatewayError, Message, ModelGateway
from quantum_agent.science.models import (
    RectangularBarrierRequest,
    SandboxLimits,
)
from quantum_agent.science.toolbox import ScientificToolbox

logger = logging.getLogger(__name__)

_MAX_REPAIRS = 2

_SYSTEM_PROMPT = """You are the Coding Agent for a quantum-physics teaching system.
Write a fresh, self-contained Python program that computes the requested
physical quantity for the student's task.  You may import only from this
allowlist: math, cmath, json, re, itertools, collections, typing, functools,
statistics, decimal, fractions, numbers, numpy, scipy, sympy, matplotlib,
qutip.  Do NOT import os, sys, socket, subprocess, or any project module.
Do NOT call open, eval, exec, compile, or access dunder attributes.

The program must print its numeric results as a single final line in this
exact format (no other JSON line, no trailing prose):
### METRICS_JSON: {"T": <float>, "R": <float>, "conservation_error": <float>}

If a matplotlib figure is appropriate, save it to the file "figure.png" in
the current directory using matplotlib.pyplot.savefig("figure.png") then
close the figure; do not call plt.show().

Return ONLY a JSON object with the schema {"purpose": string, "code": string,
"expected_outputs": [string], "verification_plan": string}.  The "code" field
holds the program text.  Never invent a result you did not compute.
"""

_REPAIR_SYSTEM_PROMPT = """You are repairing a Python program that the Coding
Agent wrote for a quantum-physics task.  The previous version failed.  Use
the failure summary and stderr excerpt to produce a corrected, self-contained
program that still obeys the import and call allowlist and still prints the
final ### METRICS_JSON: {...} line.  Return ONLY the same JSON schema.
"""


class CodingAgentError(RuntimeError):
    """Sanitized Coding Agent failure; never carries the model's raw output."""


def _user_brief(task: CodeGenerationTask) -> str:
    lines = [
        f"Student question: {task.student_question}",
    ]
    if task.learning_goal:
        lines.append(f"Learning goal: {task.learning_goal}")
    if task.known_variables:
        kv = ", ".join(f"{k}={v}" for k, v in task.known_variables.items())
        lines.append(f"Known variables: {kv}")
    lines.append("Required outputs: " + ", ".join(task.required_outputs))
    if task.allowed_libraries:
        lines.append("Allowed libraries: " + ", ".join(task.allowed_libraries))
    if task.execution_constraints:
        lines.append(f"Execution constraints: {task.execution_constraints}")
    if task.oracle_kind:
        lines.append(
            f"Verification oracle: {task.oracle_kind}. Your numeric output "
            "must match the deterministic reference within 1e-6."
        )
    return "\n".join(lines)


def _repair_brief(task: CodeGenerationTask, repair: CodeRepairAttempt) -> str:
    return (
        _user_brief(task)
        + f"\n\nPrevious attempt #{repair.attempt_number} failed:\n"
        + repair.failure_summary
        + (f"\nstderr excerpt:\n{repair.stderr_excerpt}" if repair.stderr_excerpt else "")
    )


def _build_oracle_request(
    task: CodeGenerationTask,
) -> RectangularBarrierRequest | None:
    """Construct the deterministic oracle request from the task's known variables.

    Only ``rectangular_barrier_tunnelling`` has a Coding Agent oracle: it is
    the Golden Loop demo computation (PRD §6, §9) where the agent must write
    fresh code that reproduces the deterministic transmission/reflection
    result.  Other scientific requests (e.g. ``two_level_simulation`` in
    ``run_experiments`` mode) are student-requested simulations whose
    deterministic tool is the authoritative result; the Coding Agent does
    not run for them, so the deterministic oracle remains the sole result.
    """

    if task.oracle_kind != "rectangular_barrier_tunnelling":
        return None
    kv = task.known_variables
    try:
        return RectangularBarrierRequest(
            energy_eV=float(kv["energy_eV"]),
            barrier_height_eV=float(kv["barrier_height_eV"]),
            barrier_width_m=float(kv["barrier_width_m"]),
            particle_mass_kg=float(kv["particle_mass_kg"]),
            conservation_tolerance=float(kv.get("conservation_tolerance", 1e-9)),
        )
    except (KeyError, ValueError, TypeError):
        logger.warning("could not build barrier oracle request from %s", kv)
        return None


def _domain_error(
    task: CodeGenerationTask,
    metrics: dict[str, str | int | float | bool],
    *,
    tolerance: float,
) -> str | None:
    """Return a deterministic physical-domain/conservation failure, if any."""

    if task.oracle_kind != "rectangular_barrier_tunnelling":
        return None
    numeric = {key: float(metrics[key]) for key in task.required_outputs}
    transmission = numeric["T"]
    reflection = numeric["R"]
    reported_error = numeric["conservation_error"]
    actual_error = abs(transmission + reflection - 1.0)
    if not 0.0 <= transmission <= 1.0 or not 0.0 <= reflection <= 1.0:
        return "Transmission and reflection must both lie within [0, 1]."
    if reported_error < 0.0:
        return "The reported conservation error must be non-negative."
    if actual_error > tolerance or reported_error > tolerance:
        return "Generated metrics violate probability conservation."
    if abs(reported_error - actual_error) > tolerance:
        return "The reported conservation error disagrees with generated T and R."
    return None


def _verify_against_oracle(
    task: CodeGenerationTask,
    agent_metrics: dict[str, str | int | float | bool],
) -> CodeVerificationResult:
    oracle_request = _build_oracle_request(task)
    if oracle_request is None:
        return CodeVerificationResult(
            status=CodeVerificationStatus.NO_ORACLE,
            oracle_kind=task.oracle_kind,
            agent_metrics=agent_metrics,
            observations=["No deterministic oracle is configured for this task kind."],
        )
    oracle_result = ScientificToolbox().verify(oracle_request)
    oracle_metrics: dict[str, str | int | float | bool] = {
        key: value
        for key, value in oracle_result.metrics.items()
        if isinstance(value, str | int | float | bool)
    }
    observations = [
        f"Oracle status: {oracle_result.status.value}.",
        f"Oracle metrics: {json.dumps(oracle_metrics, sort_keys=True)}.",
        f"Agent metrics: {json.dumps(agent_metrics, sort_keys=True)}.",
    ]
    if oracle_result.status.value != "pass":
        return CodeVerificationResult(
            status=CodeVerificationStatus.INCONCLUSIVE,
            oracle_kind=task.oracle_kind,
            agent_metrics=agent_metrics,
            oracle_metrics=oracle_metrics,
            observations=[*observations, "Oracle itself did not pass; refusing to verify."],
        )
    # Every task-declared output is mandatory.  Missing, non-numeric, boolean,
    # non-finite, or out-of-domain values are never a passing computation.
    required = tuple(task.required_outputs)
    for key in required:
        if key not in agent_metrics or isinstance(agent_metrics[key], bool):
            return CodeVerificationResult(
                status=CodeVerificationStatus.INCONCLUSIVE, oracle_kind=task.oracle_kind,
                agent_metrics=agent_metrics, oracle_metrics=oracle_metrics,
                observations=[*observations, f"Required metric {key!r} is missing."],
            )
        try:
            value = float(agent_metrics[key])
        except (TypeError, ValueError):
            value = float("nan")
        if not math.isfinite(value):
            return CodeVerificationResult(
                status=CodeVerificationStatus.FAIL, oracle_kind=task.oracle_kind,
                agent_metrics=agent_metrics, oracle_metrics=oracle_metrics,
                observations=[*observations, f"Required metric {key!r} is not finite."],
            )
    tolerance = 1e-6
    domain_error = _domain_error(task, agent_metrics, tolerance=tolerance)
    if domain_error is not None:
        return CodeVerificationResult(
            status=CodeVerificationStatus.FAIL,
            oracle_kind=task.oracle_kind,
            agent_metrics=agent_metrics,
            oracle_metrics=oracle_metrics,
            observations=[*observations, domain_error],
            tolerance=tolerance,
        )
    # Compare all oracle-provided required values within tolerance.
    for key in required:
        if key not in oracle_metrics:
            return CodeVerificationResult(
                status=CodeVerificationStatus.INCONCLUSIVE, oracle_kind=task.oracle_kind,
                agent_metrics=agent_metrics, oracle_metrics=oracle_metrics,
                observations=[*observations, f"Oracle did not provide required metric {key!r}."],
            )
        try:
            agent_val = float(agent_metrics[key])
            oracle_val = float(oracle_metrics[key])
        except (TypeError, ValueError):
            continue
        if abs(agent_val - oracle_val) > tolerance:
            return CodeVerificationResult(
                status=CodeVerificationStatus.FAIL,
                oracle_kind=task.oracle_kind,
                agent_metrics=agent_metrics,
                oracle_metrics=oracle_metrics,
                observations=[
                    *observations,
                    f"Agent {key}={agent_val!r} differs from oracle {key}={oracle_val!r} "
                    f"beyond tolerance {tolerance}.",
                ],
                tolerance=tolerance,
            )
    return CodeVerificationResult(
        status=CodeVerificationStatus.PASS,
        oracle_kind=task.oracle_kind,
        agent_metrics=agent_metrics,
        oracle_metrics=oracle_metrics,
        observations=[*observations, "Agent metrics match the oracle within tolerance."],
        tolerance=tolerance,
    )


class CodingAgent:
    """Writes, runs, and verifies task-specific Python for one pedagogical task."""

    def __init__(
        self,
        *,
        sandbox: SubprocessSandbox | RemoteSandbox | SandboxDisabled,
        toolbox: ScientificToolbox | None = None,
        max_repairs: int = _MAX_REPAIRS,
        default_limits: SandboxLimits | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._toolbox = toolbox or ScientificToolbox()
        self._max_repairs = max(0, min(2, max_repairs))
        # Default to the 10s ceiling so real scientific computations (numpy,
        # scipy, matplotlib) have enough time to import and run.  The wall-time
        # cap + bounded output keep the run bounded.
        self._default_limits = default_limits or SandboxLimits(wall_time_seconds=10.0)

    async def solve(
        self,
        task: CodeGenerationTask,
        *,
        gateway: ModelGateway,
    ) -> CodeArtifactRun:
        """Run the generate → safety → execute → verify loop with bounded repair."""

        repairs: list[CodeRepairAttempt] = []
        limits = self._default_limits
        last_artifact: CodeArtifact | None = None
        last_execution: CodeExecutionResult | None = None
        last_figure: str | None = None
        last_metrics: dict[str, str | int | float | bool] = {}

        for attempt in range(self._max_repairs + 1):
            attempt_number = attempt + 1
            is_final_attempt = attempt == self._max_repairs

            def record_repair(
                summary: str,
                stderr: str,
                *,
                _final: bool = is_final_attempt,
                _attempt: int = attempt_number,
            ) -> None:
                """Append a repair only if a next attempt will consume it."""
                if not _final:
                    repairs.append(
                        CodeRepairAttempt(
                            attempt_number=_attempt,
                            failure_summary=summary,
                            stderr_excerpt=stderr,
                        )
                    )

            if attempt == 0:
                messages = [
                    Message(role="system", content=_SYSTEM_PROMPT),
                    Message(role="user", content=_user_brief(task)),
                ]
                operation = "generate_coding_artifact"
            else:
                repair = repairs[-1]
                messages = [
                    Message(role="system", content=_REPAIR_SYSTEM_PROMPT),
                    Message(role="user", content=_repair_brief(task, repair)),
                ]
                operation = "repair_coding_artifact"

            try:
                artifact = await gateway.structured_generate(
                    task=operation,
                    messages=messages,
                    output_type=CodeArtifact,
                )
            except (GatewayError, ValidationError) as exc:
                logger.warning(
                    "coding agent generation failed at attempt %d: %s",
                    attempt_number,
                    type(exc).__name__,
                )
                return self._fail_run(
                    task=task,
                    artifact=last_artifact,
                    execution=last_execution,
                    figure=last_figure,
                    repairs=repairs,
                    reason=f"model generation failed: {type(exc).__name__}",
                )

            last_artifact = artifact

            # Static safety gate before any subprocess.
            try:
                report = validate_code_safety(artifact.code)
            except CodeSafetyError as exc:
                record_repair(f"safety validation raised: {exc}", "")
                last_execution = CodeExecutionResult(
                    completed=False,
                    exit_code=None,
                    stderr_bounded=f"safety error: {exc}"[:4000],
                    duration_seconds=0.0,
                )
                continue
            if not report.ok:
                record_repair(
                    "static safety validation rejected the program",
                    "; ".join(report.violations)[:1000],
                )
                last_execution = CodeExecutionResult(
                    completed=False,
                    exit_code=None,
                    stderr_bounded="; ".join(report.violations)[:4000],
                    duration_seconds=0.0,
                )
                continue

            # Sandbox execution.
            try:
                if isinstance(self._sandbox, SandboxDisabled):
                    run = await self._disabled_run(artifact)
                else:
                    run = await self._sandbox.execute_program_with_figure(artifact, limits)
            except SandboxError as exc:
                record_repair(f"sandbox error: {exc}", "")
                last_execution = CodeExecutionResult(
                    completed=False,
                    exit_code=None,
                    stderr_bounded=f"sandbox error: {type(exc).__name__}"[:4000],
                    duration_seconds=0.0,
                )
                continue

            last_execution = run.result
            last_figure = run.figure_png_base64
            last_metrics = run.metrics

            if not run.result.completed:
                record_repair(
                    "execution did not complete"
                    + (" (timed out)" if run.result.timed_out else "")
                    + f", exit_code={run.result.exit_code}",
                    run.result.stderr_bounded[:1000],
                )
                continue

            # Execution succeeded; verify against the oracle.
            verification = _verify_against_oracle(task, run.metrics)
            return CodeArtifactRun(
                artifact=artifact,
                execution=run.result,
                verification=verification,
                repairs=repairs,
                progress=CodingProgress.RESULT,
                figure_png_base64=last_figure,
            )

        # Repair budget exhausted.
        return self._fail_run(
            task=task,
            artifact=last_artifact,
            execution=last_execution,
            figure=last_figure,
            repairs=repairs,
            reason=f"exhausted {self._max_repairs} repair attempts",
            metrics=last_metrics,
        )

    async def _disabled_run(self, artifact: CodeArtifact) -> Any:
        raise SandboxError("coding sandbox is disabled")

    def _fail_run(
        self,
        *,
        task: CodeGenerationTask,
        artifact: CodeArtifact | None,
        execution: CodeExecutionResult | None,
        figure: str | None,
        repairs: list[CodeRepairAttempt],
        reason: str,
        metrics: dict[str, str | int | float | bool] | None = None,
    ) -> CodeArtifactRun:
        if artifact is None:
            artifact = CodeArtifact(
                purpose="coding agent failed before producing a program",
                code="# no program generated",
                expected_outputs=list(task.required_outputs),
                verification_plan=reason,
            )
        if execution is None:
            execution = CodeExecutionResult(
                completed=False,
                exit_code=None,
                stderr_bounded=reason[:4000],
                duration_seconds=0.0,
            )
        verification = CodeVerificationResult(
            status=CodeVerificationStatus.INCONCLUSIVE,
            oracle_kind=task.oracle_kind,
            agent_metrics=metrics or {},
            observations=[f"Coding Agent did not produce a verified result: {reason}."],
        )
        return CodeArtifactRun(
            artifact=artifact,
            execution=execution,
            verification=verification,
            repairs=repairs,
            progress=CodingProgress.RESULT,
            figure_png_base64=figure,
        )


__all__ = ["CodingAgent", "CodingAgentError"]
