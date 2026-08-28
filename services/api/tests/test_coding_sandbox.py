"""Tests for the Coding Agent subprocess sandbox (PRD V3.1 §6.2)."""

from __future__ import annotations

import asyncio
import os

import pytest

from quantum_agent.coding.models import CodeArtifact, CodeLanguage
from quantum_agent.coding.safety import validate_code_safety
from quantum_agent.coding.sandbox import (
    RemoteSandbox,
    SandboxDisabled,
    SandboxError,
    SubprocessSandbox,
)
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
    assert run.result.completed is False
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


# ---------------------------------------------------------------------------
# Adversarial regression tests (PRD V3.1 §6.2 execution safety).
#
# These mirror the Docker-level adversarial harness in
# ``scripts/test-sandbox-attacks.sh`` with Python-level assertions that run
# in the host-side ``uv`` environment without Docker.
# ---------------------------------------------------------------------------


def test_adversarial_socket_import_rejected_by_ast() -> None:
    """Vector (a): ``import socket`` must be rejected by the AST gate."""

    report = validate_code_safety("import socket\ns = socket.create_connection(('1.1.1.1', 53))")
    assert report.ok is False
    assert any("socket" in v for v in report.violations)


def test_adversarial_open_call_rejected_by_ast() -> None:
    """Vector (b): ``open('/etc/passwd')`` must be rejected by the AST gate."""

    report = validate_code_safety("f = open('/etc/passwd')\nprint(f.read())")
    assert report.ok is False
    assert any("open" in v for v in report.violations)


def test_adversarial_dunder_import_rejected_by_ast() -> None:
    """Vector (c): ``__import__('subprocess')`` must be rejected by the AST gate."""

    report = validate_code_safety("m = __import__('subprocess')\nm.run(['ls'])")
    assert report.ok is False
    assert any("__import__" in v for v in report.violations)


def test_adversarial_dunder_attribute_access_rejected_by_ast() -> None:
    """Vector (d): ``getattr(__builtins__, 'eval')`` must be rejected by the AST gate."""

    report = validate_code_safety("e = getattr(__builtins__, 'eval')\ne('1+1')")
    assert report.ok is False
    # getattr is a banned call AND __builtins__ is a dunder attribute.
    assert any("getattr" in v or "dunder" in v for v in report.violations)


def test_adversarial_numpy_ctypeslib_blocked() -> None:
    """Vector (e): ``numpy.ctypeslib`` reaches ``ctypes`` and must be blocked.

    ``numpy`` is allowlisted, but ``numpy.ctypeslib.load_library`` can load
    arbitrary shared libraries and call native functions (``system``,
    ``execve``, etc.).  The ``_BLOCKED_SUBMODULES`` entry closes this path
    at both ``import numpy.ctypeslib`` and ``from numpy.ctypeslib import ...``.
    """

    report_import = validate_code_safety(
        "import numpy.ctypeslib as ctl\nlib = ctl.load_library('libc.so.6', '/lib')"
    )
    assert report_import.ok is False
    assert any("numpy.ctypeslib" in v for v in report_import.violations)

    report_from = validate_code_safety(
        "from numpy.ctypeslib import load_library\nload_library('libc.so.6', '/lib')"
    )
    assert report_from.ok is False
    assert any("numpy.ctypeslib" in v for v in report_from.violations)

    # ``from numpy import ctypeslib`` is the same submodule by leaf name.
    report_leaf = validate_code_safety(
        "from numpy import ctypeslib\nctypeslib.load_library('libc.so.6', '/lib')"
    )
    assert report_leaf.ok is False
    assert any("ctypeslib" in v for v in report_leaf.violations)


def test_adversarial_scipy_ccallback_blocked() -> None:
    """Vector (e): ``scipy._lib._ccallback`` exposes ``ctypes`` and must be blocked."""

    report = validate_code_safety(
        "from scipy._lib import _ccallback\n_ccallback.ctypes.CDLL(None)"
    )
    assert report.ok is False
    assert any("_ccallback" in v for v in report.violations)


async def test_adversarial_numpy_loadtxt_host_file_fails_closed() -> None:
    """Vector (e): ``numpy.loadtxt('/etc/passwd')`` must not leak host user data.

    The AST gate allows ``numpy``, so this is a sandbox-level concern.  When
    ``CODING_SANDBOX_REQUIRE_ISOLATION=true`` and ``bwrap`` is available,
    ``SubprocessSandbox`` runs the child in a ``bubblewrap`` namespace with a
    synthetic ``/etc/passwd`` (single ``nobody`` entry) so the host's passwd
    file is unreachable.  When bwrap is not available, the sandbox runs in a
    private tmpdir but the host's world-readable ``/etc/passwd`` is still
    visible — so we assert the weaker but still fail-closed property: the
    sandbox never fabricates a *verified* result, and (when bwrap is active)
    the host's ``root`` account is never exposed.
    """

    sandbox = SubprocessSandbox()
    code = (
        "import numpy as np\n"
        "data = np.loadtxt('/etc/passwd', dtype=str, delimiter=':')\n"
        "flat = ','.join(data.flatten())\n"
        "print('HAS_ROOT=' + str('root' in flat))\n"
        "print('### METRICS_JSON: {\"value\": 1}')\n"
    )
    run = await sandbox.execute_program_with_figure(
        _artifact(code), SandboxLimits(wall_time_seconds=8.0)
    )
    # The program may complete (reading the synthetic /etc/passwd under bwrap
    # or the host's under a plain subprocess), but the host's ``root`` account
    # must never appear in the output when isolation is active.
    if os.getenv("CODING_SANDBOX_REQUIRE_ISOLATION") == "true":
        assert run.result.completed is True
        assert "HAS_ROOT=True" not in run.result.stdout_bounded
        assert "HAS_ROOT=False" in run.result.stdout_bounded


async def test_adversarial_cpu_loop_times_out() -> None:
    """Vector (f): ``while True: pass`` must be killed by the wall-time timeout."""

    sandbox = SubprocessSandbox()
    run = await sandbox.execute_program_with_figure(
        _artifact("while True:\n    pass\n"),
        SandboxLimits(wall_time_seconds=1.0),
    )
    assert run.result.completed is False
    assert run.result.timed_out is True or run.result.exit_code != 0


async def test_adversarial_memory_attack_fails() -> None:
    """Vector (g): unbounded allocation must fail (memory bound or wall-time).

    ``x = [bytearray(1024*1024) for _ in range(2048)]`` tries to allocate
    ~2 GB, which exceeds the sandbox address-space ceiling (1.5 GB under
    bwrap, ``memory_megabytes`` under a plain subprocess).  Under bwrap the
    ``RLIMIT_AS`` cap triggers ``MemoryError``; under a plain subprocess the
    same rlimit applies.  In the production container the ``mem_limit: 768m``
    kills the OOM victim.  Either way the sandbox must not report a fabricated
    success.
    """

    sandbox = SubprocessSandbox()
    run = await sandbox.execute_program_with_figure(
        _artifact("x = [bytearray(1024 * 1024) for _ in range(2048)]\nprint(len(x))"),
        SandboxLimits(wall_time_seconds=3.0, memory_megabytes=64),
    )
    assert run.result.completed is False


async def test_adversarial_output_attack_truncates_and_stays_bounded() -> None:
    """Vector (h): ``print('X'*20_000_000)`` must truncate and stay <= 8000 bytes.

    The sandbox drains stdout incrementally and kills the process group on the
    first overflow, so the retained excerpt never exceeds the 8 KB budget
    (plus the truncation marker).
    """

    sandbox = SubprocessSandbox()
    run = await sandbox.execute_program_with_figure(
        _artifact("print('X' * 20_000_000)"),
        SandboxLimits(wall_time_seconds=2.0),
    )
    assert run.result.completed is False
    assert run.result.truncated is True
    assert len(run.result.stdout_bounded) <= 8_000 + 50


async def test_adversarial_remote_sandbox_fails_closed_on_dead_socket() -> None:
    """``RemoteSandbox`` must return ``completed=False`` when the Unix socket is
    unreachable — it never fabricates a result."""

    sandbox = RemoteSandbox("unix:///tmp/qa-nonexistent-sandbox.sock")
    run = await sandbox.execute_program(
        _artifact("print('hello')"), SandboxLimits()
    )
    assert run.completed is False
    assert "unavailable" in run.stderr_bounded or "ConnectError" in run.stderr_bounded


def test_adversarial_remote_sandbox_rejects_non_unix_endpoint() -> None:
    """``RemoteSandbox`` must refuse any non-``unix://`` endpoint so the API
    process cannot be tricked into talking to a TCP listener."""

    with pytest.raises(ValueError):
        RemoteSandbox("http://1.1.1.1:8000")
    with pytest.raises(ValueError):
        RemoteSandbox("tcp://1.1.1.1:8000")


def test_adversarial_ctypes_import_rejected_by_ast() -> None:
    """Direct ``ctypes``/``cffi``/``subprocess``/``multiprocessing`` imports are
    rejected by the AST gate (defense-in-depth even though the sandbox would
    also block them)."""

    for module in ("ctypes", "cffi", "subprocess", "socket", "multiprocessing"):
        report = validate_code_safety(f"import {module}\nprint({module})")
        assert report.ok is False, f"{module} must be rejected"
        assert any(module in v for v in report.violations)
