"""Tests for the Coding Agent subprocess sandbox (PRD V3.1 §6.2)."""

from __future__ import annotations

import asyncio

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


async def test_sandbox_blocks_indirect_builtin_host_file_access() -> None:
    """An allowlisted import must not recover ``open`` and read host files."""

    sandbox = SubprocessSandbox()
    code = (
        "from numpy import __builtins__ as builtins_map\n"
        'data = builtins_map["open"]("/etc/hostname").read()\n'
        'print("HOST_FILE_READ=" + str(bool(data)))\n'
        'print(\'### METRICS_JSON: {"value": 1}\')\n'
    )
    report = validate_code_safety(code)
    run = await sandbox.execute_program_with_figure(
        _artifact(code), SandboxLimits(wall_time_seconds=3.0)
    )

    assert report.ok is False
    assert run.result.completed is False
    assert "HOST_FILE_READ=True" not in run.result.stdout_bounded


async def test_sandbox_blocks_indirect_builtin_network_access() -> None:
    """Generated code must not reach even a controlled local TCP listener."""

    reached = asyncio.Event()

    async def handle_connection(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await reader.read(4)
        reached.set()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_connection, "127.0.0.1", 0)
    try:
        socket_info = server.sockets[0].getsockname()
        port = int(socket_info[1])
        code = (
            "from numpy import __builtins__ as builtins_map\n"
            'socket_module = builtins_map["__import__"]("socket")\n'
            "client = socket_module.socket()\n"
            "client.settimeout(2)\n"
            f'client.connect(("127.0.0.1", {port}))\n'
            'client.sendall(b"PING")\n'
            "client.close()\n"
            'print(\'### METRICS_JSON: {"value": 1}\')\n'
        )
        report = validate_code_safety(code)
        run = await SubprocessSandbox().execute_program_with_figure(
            _artifact(code), SandboxLimits(wall_time_seconds=3.0)
        )
        try:
            await asyncio.wait_for(reached.wait(), timeout=0.5)
        except TimeoutError:
            pass
    finally:
        server.close()
        await server.wait_closed()

    assert report.ok is False
    assert reached.is_set() is False
    assert run.result.completed is False
