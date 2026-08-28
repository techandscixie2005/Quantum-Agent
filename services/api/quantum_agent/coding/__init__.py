"""Agentic scientific computation: a Coding Agent writes task-specific Python,
a bounded sandbox executes it, and the existing deterministic scientific tools
serve as verification oracles for the agent's output.

This package implements the PRD's "Verification outranks fluent language"
axiom for the agentic-computation path.  The Coding Agent is NOT a wrapper
around a prewritten domain solver; it writes fresh code for each task.  The
deterministic solvers in :mod:`quantum_agent.science.toolbox` are demoted to
verification oracles that check the agent's numeric output.
"""

from quantum_agent.coding.agent import CodingAgent, CodingAgentError
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

__all__ = [
    "CodeArtifact",
    "CodeArtifactRun",
    "CodeExecutionResult",
    "CodeGenerationTask",
    "CodeRepairAttempt",
    "CodeSafetyError",
    "CodeVerificationResult",
    "CodeVerificationStatus",
    "CodingAgent",
    "CodingAgentError",
    "CodingProgress",
    "RemoteSandbox",
    "SandboxDisabled",
    "SandboxError",
    "SubprocessSandbox",
    "validate_code_safety",
]
