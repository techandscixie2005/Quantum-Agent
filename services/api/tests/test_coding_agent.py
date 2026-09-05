"""Tests for the Coding Agent loop (PRD V3.1 §6)."""

from __future__ import annotations

from quantum_agent.coding.agent import CodingAgent
from quantum_agent.coding.models import (
    CodeArtifact,
    CodeGenerationTask,
    CodeLanguage,
    CodeVerificationStatus,
)
from quantum_agent.coding.sandbox import SubprocessSandbox
from quantum_agent.llm.gateway import FakeModelGateway

_TUNNELLING_CODE = (
    "import math\n"
    "joule_per_eV = 1.602176634e-19\n"
    "hbar_j_s = 1.054571817e-34\n"
    "m_e = 9.1093837015e-31\n"
    "E = 5.0; V0 = 10.0; a = 1e-10\n"
    "E_j = E * joule_per_eV; V0_j = V0 * joule_per_eV\n"
    "kappa = math.sqrt(2.0 * m_e * (V0_j - E_j)) / hbar_j_s\n"
    "sinh_sq = math.sinh(kappa * a) ** 2\n"
    "T = 1.0 / (1.0 + (V0_j * V0_j * sinh_sq) / (4.0 * E_j * (V0_j - E_j)))\n"
    "R = 1.0 - T\n"
    "cons = abs(R + T - 1.0)\n"
    'print("### METRICS_JSON: " + \'{"T": \' + str(T) + \', "R": \' + str(R) + \', "conservation_error": \' + str(cons) + \'}\')\n'
)

# The exact sign bug a live USTC model produced: `4*E*(E-V0)` instead of
# `4*E*(V0-E)` — a negative denominator flips T to -1.003, and the
# deterministic verifier correctly FAILs it as out-of-domain.
_SIGN_BUG_CODE = (
    "import math\n"
    "joule_per_eV = 1.602176634e-19\n"
    "hbar_j_s = 1.054571817e-34\n"
    "m_e = 9.1093837015e-31\n"
    "E = 5.0; V0 = 10.0; a = 1e-10\n"
    "E_j = E * joule_per_eV; V0_j = V0 * joule_per_eV\n"
    "kappa = math.sqrt(2.0 * m_e * (V0_j - E_j)) / hbar_j_s\n"
    "sinh_sq = math.sinh(kappa * a) ** 2\n"
    "T = 1.0 / (1.0 + (V0_j * V0_j * sinh_sq) / (4.0 * E_j * (E_j - V0_j)))\n"
    "R = 1.0 - T\n"
    "cons = abs(R + T - 1.0)\n"
    'print("### METRICS_JSON: " + \'{"T": \' + str(T) + \', "R": \' + str(R) + \', "conservation_error": \' + str(cons) + \'}\')\n'
)


def _tunnelling_task() -> CodeGenerationTask:
    return CodeGenerationTask(
        student_question="compute T and R for an electron tunnelling through a rectangular barrier",
        known_variables={
            "energy_eV": "5.0",
            "barrier_height_eV": "10.0",
            "barrier_width_m": "1e-10",
            "particle_mass_kg": "9.1093837015e-31",
            "conservation_tolerance": "1e-9",
        },
        required_outputs=["T", "R", "conservation_error"],
        allowed_libraries=("numpy", "math", "cmath"),
        oracle_kind="rectangular_barrier_tunnelling",
    )


def _tunnelling_artifact() -> CodeArtifact:
    return CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="rectangular barrier tunnelling T/R",
        code=_TUNNELLING_CODE,
        expected_outputs=["T", "R", "conservation_error"],
        verification_plan="match oracle within 1e-6",
    )


async def test_coding_agent_passes_when_output_matches_oracle() -> None:
    artifact = _tunnelling_artifact()
    gateway = FakeModelGateway(
        {"generate_coding_artifact": artifact.model_dump(mode="json")}
    )
    agent = CodingAgent(sandbox=SubprocessSandbox())
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.PASS
    agent_t = float(run.verification.agent_metrics["T"])
    oracle_t = float(run.verification.oracle_metrics["T"])
    assert abs(agent_t - oracle_t) < 1e-6
    assert abs(agent_t - 0.333682) < 1e-4
    assert len(run.repairs) == 0


async def test_coding_agent_fails_when_output_disagrees_with_oracle() -> None:
    # The program prints a wrong T (0.5 instead of ~0.3337).  With the
    # default single repair the wrong program is retried once; the FINAL
    # attempt's honest FAIL verdict is what the run returns (never relabeled
    # PASS).  Use max_repairs=0 to assert the FAIL verdict itself.
    bad_code = (
        "import math\n"
        'print("### METRICS_JSON: " + \'{"T": 0.5, "R": 0.5, "conservation_error": 0.0}\')\n'
    )
    artifact = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="wrong tunnelling T",
        code=bad_code,
        expected_outputs=["T", "R"],
        verification_plan="match oracle",
    )
    gateway = FakeModelGateway(
        {"generate_coding_artifact": artifact.model_dump(mode="json")}
    )
    agent = CodingAgent(sandbox=SubprocessSandbox(), max_repairs=0)
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.FAIL


async def test_coding_agent_repairs_then_succeeds() -> None:
    # First attempt: syntax error.  Second attempt: correct program.
    broken = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="broken",
        code="import math\nprint('hello'",  # SyntaxError
        expected_outputs=["T"],
    )
    fixed = _tunnelling_artifact()
    gateway = FakeModelGateway(
        {
            "generate_coding_artifact": broken.model_dump(mode="json"),
            "repair_coding_artifact": fixed.model_dump(mode="json"),
        }
    )
    agent = CodingAgent(sandbox=SubprocessSandbox())
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.PASS
    assert len(run.repairs) == 1
    assert run.repairs[0].attempt_number == 1


async def test_coding_agent_verification_failure_is_repaired_not_returned() -> None:
    """A program whose metrics fail the deterministic oracle must feed the
    verifier's failure summary into the repair loop — not be returned as a
    FAIL run (a live USTC model produced exactly the sign bug in
    _SIGN_BUG_CODE; the verifier correctly failed T=-1.003 but the old
    code returned it immediately, wasting the repair budget).
    """
    bad = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="sign-bug tunnelling T",
        code=_SIGN_BUG_CODE,
        expected_outputs=["T", "R", "conservation_error"],
        verification_plan="match oracle",
    )
    fixed = _tunnelling_artifact()
    gateway = FakeModelGateway(
        {
            "generate_coding_artifact": bad.model_dump(mode="json"),
            "repair_coding_artifact": fixed.model_dump(mode="json"),
        }
    )
    agent = CodingAgent(sandbox=SubprocessSandbox())
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.PASS
    assert len(run.repairs) == 1
    assert "verification fail" in run.repairs[0].failure_summary
    # The returned artifact is the repaired program, not the sign-bug one.
    assert "E_j - V0_j" not in run.artifact.code


async def test_coding_agent_final_verification_failure_returns_honest_fail() -> None:
    """When the model's physics is wrong on every attempt the run returns the
    final attempt's honest FAIL verdict — never relabeled, never silently
    swallowed (the fail-closed invariant).  With max_repairs=1 the first
    (non-final) FAIL feeds one repair entry, then the final FAIL is
    returned as-is.
    """
    bad = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="sign-bug tunnelling T",
        code=_SIGN_BUG_CODE,
        expected_outputs=["T", "R", "conservation_error"],
        verification_plan="match oracle",
    )
    gateway = FakeModelGateway(
        {
            "generate_coding_artifact": bad.model_dump(mode="json"),
            "repair_coding_artifact": bad.model_dump(mode="json"),
        }
    )
    agent = CodingAgent(sandbox=SubprocessSandbox(), max_repairs=1)
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.FAIL
    assert len(run.repairs) == 1
    assert "verification fail" in run.repairs[0].failure_summary
    assert run.artifact.code == bad.code


async def test_coding_agent_generation_failure_retries_through_repair_loop() -> None:
    """A transient gateway failure on attempt 1 must consume the repair
    budget and retry — not fail the run immediately (two consecutive live
    runs lost the Stage-7 coding artifact to the old fast-fail).  The
    retried attempt goes through the same safety/sandbox/oracle path.
    """
    fixed = _tunnelling_artifact()
    gateway = FakeModelGateway(
        {
            # Attempt 1 raises GatewayError (no fake response configured for
            # the generate operation).  The repair operation returns the
            # correct program.
            "repair_coding_artifact": fixed.model_dump(mode="json"),
        }
    )
    agent = CodingAgent(sandbox=SubprocessSandbox())
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.PASS
    assert len(run.repairs) == 1
    assert run.repairs[0].attempt_number == 1
    assert "GatewayError" in run.repairs[0].failure_summary
    # The repaired program must be the one that executed, not a failure
    # placeholder.
    assert "# no program generated" not in run.artifact.code


async def test_coding_agent_generation_failure_exhausts_budget_and_fails_closed() -> None:
    """When the gateway fails on every attempt the run still fails closed
    with the honest INCONCLUSIVE verdict — the repair loop consumes the
    full budget first.
    """
    gateway = FakeModelGateway({})  # every operation raises GatewayError
    agent = CodingAgent(sandbox=SubprocessSandbox(), max_repairs=2)
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.INCONCLUSIVE
    assert "model generation failed: GatewayError" in (
        run.verification.observations[0]
    )
    assert "# no program generated" in run.artifact.code


async def test_coding_agent_exhausts_repairs_and_returns_inconclusive() -> None:
    broken = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="broken",
        code="import math\nprint('hello'",  # SyntaxError, always
        expected_outputs=["T"],
    )
    gateway = FakeModelGateway(
        {
            "generate_coding_artifact": broken.model_dump(mode="json"),
            "repair_coding_artifact": broken.model_dump(mode="json"),
        }
    )
    agent = CodingAgent(sandbox=SubprocessSandbox(), max_repairs=2)
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.INCONCLUSIVE
    assert len(run.repairs) == 2


async def test_coding_agent_no_oracle_when_kind_is_none() -> None:
    artifact = _tunnelling_artifact()
    gateway = FakeModelGateway(
        {"generate_coding_artifact": artifact.model_dump(mode="json")}
    )
    agent = CodingAgent(sandbox=SubprocessSandbox())
    task = CodeGenerationTask(
        student_question="compute something with no oracle",
        known_variables={},
        required_outputs=["T"],
        oracle_kind=None,
    )
    run = await agent.solve(task, gateway=gateway)
    assert run.verification.status is CodeVerificationStatus.NO_ORACLE


async def test_coding_agent_never_relabels_fail_as_pass() -> None:
    # The program raises immediately; the agent cannot verify.
    broken = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="raises",
        code="raise RuntimeError('cannot compute')",
        expected_outputs=["T"],
    )
    gateway = FakeModelGateway(
        {
            "generate_coding_artifact": broken.model_dump(mode="json"),
            "repair_coding_artifact": broken.model_dump(mode="json"),
        }
    )
    agent = CodingAgent(sandbox=SubprocessSandbox(), max_repairs=1)
    run = await agent.solve(_tunnelling_task(), gateway=gateway)
    # INCONCLUSIVE or FAIL, never PASS.
    assert run.verification.status is not CodeVerificationStatus.PASS


async def test_coding_agent_does_not_pass_when_required_metrics_are_missing() -> None:
    artifact = CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="exits without performing the requested computation",
        code="print('program exited without metrics')",
        expected_outputs=["T", "R", "conservation_error"],
        verification_plan="must not pass without metrics",
    )
    gateway = FakeModelGateway(
        {"generate_coding_artifact": artifact.model_dump(mode="json")}
    )

    run = await CodingAgent(sandbox=SubprocessSandbox()).solve(
        _tunnelling_task(), gateway=gateway
    )

    assert run.execution.completed is True
    assert run.verification.agent_metrics == {}
    assert run.verification.status is not CodeVerificationStatus.PASS
