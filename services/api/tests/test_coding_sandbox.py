"""Tests for the Coding Agent subprocess sandbox (PRD V3.1 §6.2)."""

from __future__ import annotations

import pytest

from quantum_agent.coding.models import CodeArtifact, CodeLanguage
from quantum_agent.coding.safety import validate_code_safety
from quantum_agent.coding.sandbox import SandboxDisabled, SandboxError, SubprocessSandbox
from quantum_agent.science.models import SandboxLimits


def _artifact(code: str) -> CodeArtifact:
    return CodeArtifact(
        language=CodeLanguage.PYTHON,
        purpose="test program",
        code=code,
        expected_outputs=["value"],
    )


async def test_sandbox_runs_a_numpy_computation() -> None:
    sandbox = SubprocessSandbox()
    code = (
        "import numpy as np\n"
        "x = np.array([1.0, 2.0, 3.0])\n"
        "print('### METRICS_JSON: ' + '{\"value\": ' + str(float(np.sum(x))) + '}')\n"
    )
    run = await sandbox.execute_program_with_figure(_artifact(code), SandboxLimits())
    assert run.result.completed is True
    assert run.result.exit_code == 0
    assert run.metrics["value"] == 6.0


async def test_sandbox_kills_an_infinite_cpu_loop() -> None:
    sandbox = SubprocessSandbox()
    code = "while True:\n    pass\n"
    run = await sandbox.execute_program_with_figure(_artifact(code), SandboxLimits(wall_time_seconds=2.0))
    assert run.result.completed is False
    # Either timed out by the wall clock or killed by RLIMIT_CPU.
    assert run.result.timed_out is True or run.result.exit_code != 0


async def test_sandbox_kills_a_sleep_loop_via_wall_time() -> None:
    sandbox = SubprocessSandbox()
    code = "import time\ntime.sleep(30)\n"
    run = await sandbox.execute_program_with_figure(_artifact(code), SandboxLimits(wall_time_seconds=2.0))
    assert run.result.completed is False
    assert run.result.timed_out is True


async def test_sandbox_scrubs_env_so_no_secrets_leak() -> None:
    code = (
        "import os\n"
        # os is not in the allowlist, so this should be rejected by the AST gate
        # before any subprocess starts.  We assert the safety layer catches it.
        "print(os.environ.get('USTC_API', 'none'))\n"
    )
    report = validate_code_safety(code)
    assert report.ok is False
    assert any("os" in v for v in report.violations)


async def test_sandbox_rejects_open_call() -> None:
    code = "f = open('/etc/passwd')\nprint(f.read())\n"
    report = validate_code_safety(code)
    assert report.ok is False
    assert any("open" in v for v in report.violations)


async def test_sandbox_rejects_socket_import() -> None:
    code = "import socket\ns = socket.socket()\n"
    report = validate_code_safety(code)
    assert report.ok is False
    assert any("socket" in v for v in report.violations)


async def test_sandbox_bounds_stdout() -> None:
    sandbox = SubprocessSandbox()
    code = "print('A' * 20_000)\n"
    run = await sandbox.execute_program_with_figure(_artifact(code), SandboxLimits())
    assert run.result.completed is True
    assert run.result.truncated is True
    assert len(run.result.stdout_bounded) <= 8_000 + 50  # bounded + truncation marker


async def test_sandbox_captures_nonzero_exit() -> None:
    sandbox = SubprocessSandbox()
    code = "raise ValueError('boom')\n"
    run = await sandbox.execute_program_with_figure(_artifact(code), SandboxLimits())
    assert run.result.completed is False
    assert run.result.exit_code != 0
    assert "boom" in run.result.stderr_bounded or "ValueError" in run.result.stderr_bounded


async def test_sandbox_disabled_raises() -> None:
    sandbox = SandboxDisabled()
    with pytest.raises(SandboxError):
        await sandbox.execute_program(_artifact("print('hi')"), SandboxLimits())


async def test_sandbox_parses_metrics_json_line() -> None:
    sandbox = SubprocessSandbox()
    code = (
        "import math\n"
        "T = 0.3337\n"
        "R = 0.6663\n"
        "print('### METRICS_JSON: ' + '{\"T\": ' + str(T) + ', \"R\": ' + str(R) + '}')\n"
    )
    run = await sandbox.execute_program_with_figure(_artifact(code), SandboxLimits())
    assert run.metrics == {"T": 0.3337, "R": 0.6663}


async def test_sandbox_captures_matplotlib_figure() -> None:
    sandbox = SubprocessSandbox()
    code = (
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([0, 1, 2], [0, 1, 4])\n"
        "plt.savefig('figure.png')\nplt.close()\n"
        "print('### METRICS_JSON: {}')\n"
    )
    run = await sandbox.execute_program_with_figure(
        _artifact(code), SandboxLimits(wall_time_seconds=10.0)
    )
    assert run.result.completed is True
    assert run.figure_png_base64 is not None
    assert len(run.figure_png_base64) > 100
