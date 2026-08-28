"""Typed contracts for the Coding Agent, sandbox, and verification loop.

All models are Pydantic v2 with ``extra="forbid"`` and frozen where possible,
matching the style of :mod:`quantum_agent.science.models`.  Nothing here
carries executable callbacks or unbounded text.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CodeLanguage(StrEnum):
    PYTHON = "python"


class CodeGenerationTask(BaseModel):
    """The structured brief handed to the Coding Agent for one task.

    The agent writes a *fresh* program for this task.  It must not invoke a
    hidden project solver that already contains the answer; the deterministic
    solvers live in :mod:`quantum_agent.science.toolbox` and are used only as
    verification oracles after the agent's code runs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_question: str = Field(min_length=1, max_length=2_000)
    learning_goal: str = Field(default="", max_length=600)
    known_variables: dict[str, str] = Field(default_factory=dict, max_length=20)
    required_outputs: list[str] = Field(min_length=1, max_length=8)
    allowed_libraries: tuple[str, ...] = Field(default=(), max_length=12)
    execution_constraints: str = Field(default="", max_length=600)
    oracle_kind: str | None = Field(default=None, max_length=80)


class CodeArtifact(BaseModel):
    """A program the Coding Agent produced for a specific task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: CodeLanguage = CodeLanguage.PYTHON
    purpose: str = Field(min_length=1, max_length=600)
    code: str = Field(min_length=1, max_length=20_000)
    expected_outputs: list[str] = Field(default_factory=list, max_length=8)
    verification_plan: str = Field(default="", max_length=600)


class CodeRepairAttempt(BaseModel):
    """One round of the bounded repair loop.

    When the sandbox reports an execution failure, the structured error is fed
    back to the Coding Agent.  The loop is bounded to 2 repairs; after that
    the system fails transparently rather than burning unbounded tokens.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: int = Field(ge=1, le=3)
    failure_summary: str = Field(min_length=1, max_length=1_000)
    stderr_excerpt: str = Field(default="", max_length=1_000)


class CodeExecutionResult(BaseModel):
    """Bounded, sanitized execution outcome.

    stdout/stderr are truncated to ``max_output_bytes`` and never carry the
    raw process output beyond that bound.  The exit code and timed-out flag
    are the only execution-control signals the tutor consumes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    completed: bool
    exit_code: int | None = None
    timed_out: bool = False
    truncated: bool = False
    stdout_bounded: str = Field(default="", max_length=8_000)
    stderr_bounded: str = Field(default="", max_length=4_000)
    duration_seconds: float = Field(default=0.0, ge=0.0, le=600.0)


class CodeVerificationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NO_ORACLE = "no_oracle"


class CodeVerificationResult(BaseModel):
    """The oracle's verdict on the agent's numeric output.

    ``agent_metrics`` are parsed from the program's JSON stdout; ``oracle_metrics``
    come from the deterministic solver.  ``status`` is ``PASS`` only when the
    two agree within tolerance.  The tutor may NOT relabel ``FAIL`` as ``PASS``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CodeVerificationStatus
    oracle_kind: str | None = Field(default=None, max_length=80)
    agent_metrics: dict[str, str | int | float | bool] = Field(default_factory=dict)
    oracle_metrics: dict[str, str | int | float | bool] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list, max_length=12)
    tolerance: float = Field(default=1e-6, ge=0.0, le=1.0)


class CodingProgress(StrEnum):
    """Frontend-visible progress states for the Coding Agent panel.

    The trace workflow stays at the fixed 10-step ``WORKFLOW_ORDER``; this
    enum models the *artifact-level* progression the student sees in the
    Coding UX strip (PRD §8): Planning → Writing → Running → Verifying →
    Result.  It is reconstructed from the run's ``repairs`` and final
    ``verification`` rather than streamed live (the BFF fully buffers SSE).
    """

    PLANNING = "planning"
    WRITING = "writing"
    RUNNING = "running"
    VERIFYING = "verifying"
    RESULT = "result"


class CodeArtifactRun(BaseModel):
    """The complete outcome of one Coding Agent invocation.

    Aggregates the generated program, its sandbox execution, the oracle
    verification, and the bounded repair history.  Surfaced as
    ``TeachingTurnResult.code_artifact`` so the frontend can render the
    Coding UX strip and the generated code without touching the 10-step
    workflow trace.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: CodeArtifact
    execution: CodeExecutionResult
    verification: CodeVerificationResult
    repairs: list[CodeRepairAttempt] = Field(default_factory=list, max_length=3)
    progress: CodingProgress = CodingProgress.RESULT
    figure_png_base64: str | None = Field(default=None, max_length=200_000)


# Literal alias used by the discriminated scientific-request union so a
# ``CodeGenerationRequest`` carries its discriminator without a separate field.
type CodeGenerationDiscriminator = Literal["code_generation"]


__all__ = [
    "CodeArtifact",
    "CodeArtifactRun",
    "CodeExecutionResult",
    "CodeGenerationTask",
    "CodeLanguage",
    "CodeRepairAttempt",
    "CodeVerificationResult",
    "CodeVerificationStatus",
    "CodingProgress",
]
