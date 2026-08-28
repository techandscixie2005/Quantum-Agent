"""Execution clients for the isolated Coding-Agent runtime (PRD V3.1 §6.2).

``RemoteSandbox`` is the only release-mode boundary: it sends a bounded
program to a separate, network-disabled container over a Unix-domain socket.
The API process never executes generated code.  ``SubprocessSandbox`` is the
runner-internal executor (and a unit-test seam); it executes a
:class:`CodeArtifact` program in a child Python process with:

* an import/call allowlist enforced upstream by :func:`validate_code_safety`
  (the AST gate runs before the subprocess starts);
* ``resource.setrlimit`` caps on CPU seconds, address space, file size, open
  files, and child processes — applied in the child via ``preexec_fn`` so the
  API host's own limits are untouched;
* a scrubbed environment (no ``USTC_API``, no ``PATH`` tricks, ``PYTHONPATH``
  blanked, ``MPLBACKEND=Agg`` so matplotlib never opens a window);
* a private tmpdir as ``cwd``/``HOME`` so the program cannot read the host
  filesystem;
* a wall-time timeout that kills the whole process group;
* incrementally drained stdout/stderr (8 KB / 4 KB retained) so a runaway
  program cannot exhaust runner memory or disk.

The sandbox never fabricates success: a timeout, non-zero exit, or signal
yields ``completed=False``.  Raw process output beyond the bounded excerpt is
discarded.

``SubprocessSandbox`` implements the :class:`SandboxExecutor` protocol from
:mod:`quantum_agent.science.toolbox` so ``ScientificToolbox`` can dispatch
``CodeTestRequest`` through it, and also exposes
:meth:`execute_program` for the Coding Agent's own :class:`CodeArtifact`
output (richer contract: stdout/stderr excerpts + parsed JSON metrics +
optional figure).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import resource
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import httpx

from quantum_agent.coding.models import CodeArtifact, CodeExecutionResult
from quantum_agent.coding.safety import validate_code_safety
from quantum_agent.science.models import (
    CodeTestRequest,
    SandboxExecutionOutcome,
    SandboxLimits,
)

logger = logging.getLogger(__name__)

_MAX_STDOUT_BYTES = 8_000
_MAX_STDERR_BYTES = 4_000
_MAX_FIGURE_BYTES = 200_000
_METRICS_MARKER = "### METRICS_JSON:"
_FIGURE_PATH = "figure.png"


@dataclass(frozen=True, slots=True)
class _SandboxRun:
    """Internal result bundling the execution outcome with the figure + metrics."""

    result: CodeExecutionResult
    figure_png_base64: str | None
    metrics: dict[str, str | int | float | bool]


class SandboxError(RuntimeError):
    """Sanitized sandbox failure; never carries the program's raw output."""


class SandboxDisabled:
    """No-op sandbox used when ``CODING_SANDBOX_ENABLED=false``.

    Every call raises so the Coding Agent degrades transparently to
    ``INCONCLUSIVE`` rather than silently executing on the API host.
    """

    async def execute_program(
        self,
        artifact: CodeArtifact,
        limits: SandboxLimits | None = None,
    ) -> CodeExecutionResult:
        raise SandboxError("coding sandbox is disabled")

    def execute(
        self,
        request: CodeTestRequest,
        limits: SandboxLimits,
    ) -> SandboxExecutionOutcome:
        raise SandboxError("coding sandbox is disabled")


def _rlimit_settings(limits: SandboxLimits) -> tuple[tuple[int, tuple[int, int]], ...]:
    """Translate SandboxLimits into (resource, (soft, hard)) pairs.

    CPU is in seconds; file size in bytes; open files and child processes
    are capped.  ``RLIMIT_AS`` (address space) uses a generous 1.5 GB ceiling
    so numpy/OpenBLAS/matplotlib can mmap their large virtual regions without
    hitting MemoryError, while a ~2 GB resident-allocation attack (e.g.
    ``[bytearray(1<<20) for _ in range(2048)]``) still fails.  The wall-time
    timeout is the primary CPU bound; the production container's
    ``mem_limit: 768m`` is the primary memory bound.  All hard limits equal
    the soft limit so the program cannot raise them.
    """

    cpu_seconds = max(1, int(limits.wall_time_seconds) + 1)
    fsize_bytes = 16 * 1024 * 1024
    nofile = 32
    nproc = 1
    # 1.5 GB: enough for numpy/scipy/matplotlib virtual mappings, still catches
    # a 2 GB resident-allocation attack.  The ``memory_megabytes`` field (max
    # 512) is too tight for the interpreter's virtual footprint under load.
    address_space = 1536 * 1024 * 1024
    return (
        (resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds)),
        (resource.RLIMIT_AS, (address_space, address_space)),
        (resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes)),
        (resource.RLIMIT_NOFILE, (nofile, nofile)),
        (resource.RLIMIT_NPROC, (nproc, nproc)),
    )


def _apply_rlimits(limits: SandboxLimits) -> None:
    """``preexec_fn`` target: apply rlimits in the child after fork."""

    for which, (soft, hard) in _rlimit_settings(limits):
        try:
            resource.setrlimit(which, (soft, hard))
        except (ValueError, OSError):
            # Some platforms (e.g. macOS) reject RLIMIT_AS; skip rather than
            # fail the exec.  The wall-time timeout + bounded output still
            # bound the run.
            pass


def _bwrap_rlimit_settings(limits: SandboxLimits) -> tuple[tuple[int, tuple[int, int]], ...]:
    """Rlimits compatible with ``bubblewrap`` namespace creation.

    ``RLIMIT_NPROC`` is excluded: bwrap needs to fork/clone to create the
    sandbox namespace, and a 1-process cap breaks that with
    ``Resource temporarily unavailable``.  PID isolation is handled by
    ``--unshare-pid`` and the container's ``pids_limit``.

    ``RLIMIT_AS`` uses a generous 1.5 GB ceiling so numpy/OpenBLAS can mmap
    their large virtual regions, while a ~1 GB resident allocation attack
    (e.g. ``[bytearray(1<<20) for _ in range(1024)]``) still hits MemoryError.
    The wall-time timeout is the primary CPU bound.
    """

    cpu_seconds = max(1, int(limits.wall_time_seconds) + 1)
    fsize_bytes = 16 * 1024 * 1024
    nofile = 64
    # 1.5 GB: enough for numpy/scipy/matplotlib virtual mappings, still catches
    # a 1 GB resident-allocation attack.
    address_space = 1536 * 1024 * 1024
    return (
        (resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds)),
        (resource.RLIMIT_AS, (address_space, address_space)),
        (resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes)),
        (resource.RLIMIT_NOFILE, (nofile, nofile)),
    )


def _apply_bwrap_rlimits(limits: SandboxLimits) -> None:
    """``preexec_fn`` target for the bwrap parent: apply bwrap-safe rlimits."""

    for which, (soft, hard) in _bwrap_rlimit_settings(limits):
        try:
            resource.setrlimit(which, (soft, hard))
        except (ValueError, OSError):
            pass


def _scrubbed_env(tmpdir: str) -> dict[str, str]:
    """Build a minimal env with no secrets and no inherited PATH tricks."""

    env: dict[str, str] = {
        "PATH": os.path.dirname(sys.executable) + ":/usr/bin:/bin",
        "HOME": tmpdir,
        "PYTHONPATH": "",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLBACKEND": "Agg",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # Pin BLAS to a single thread so OpenBLAS does not emit thread-init
        # warnings or oversubscribe inside the sandbox.
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    # Explicitly never forward USTC_API, database URLs, or any secret.
    return env


def _bounded(data: bytes, limit: int) -> tuple[str, bool]:
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace"), False
    # Leave room for the truncation marker so the result stays within the
    # Pydantic field's max_length.
    marker = "\n[output truncated]"
    budget = max(0, limit - len(marker))
    return data[:budget].decode("utf-8", errors="replace") + marker, True


def _bwrap_command(bwrap: str, python_executable: str, tmpdir: str) -> list[str]:
    """Build a ``bubblewrap`` command that isolates the sandbox child from the
    host filesystem while still allowing the Python interpreter and its
    scientific libraries (numpy/scipy/sympy/matplotlib/qutip) to import.

    Binding the host root (``--ro-bind / /``) would expose the host's
    ``/etc/passwd`` and other world-readable files, so ``numpy.loadtxt`` could
    read them.  This build instead binds only the interpreter's own directory
    tree (``/usr``, ``/lib``, ``/lib64``, and the venv if present) read-only,
    creates a minimal synthetic ``/etc`` with no host user data, and unshares
    the network + PID namespaces.  Host files like ``/etc/passwd`` are
    therefore unreachable from inside the sandbox.
    """

    # Determine the venv root that owns the Python executable so we can bind
    # it read-only (numpy/scipy/matplotlib live in the venv site-packages).
    # Do NOT resolve the symlink: a venv ``bin/python`` often points at the
    # system interpreter, but the site-packages we need live under the venv
    # itself.  Walk up from the literal executable path to find the venv root.
    python_path = Path(python_executable)
    venv_root: Path | None = None
    if python_path.parent.name == "bin":
        candidate = python_path.parent.parent
        if (candidate / "lib").exists() or (candidate / "Lib").exists():
            venv_root = candidate
    bind_targets: list[tuple[str, str]] = []
    for host_path in ("/usr", "/lib", "/lib64"):
        if Path(host_path).exists():
            bind_targets.append((host_path, host_path))
    if venv_root is not None and venv_root.exists():
        bind_targets.append((str(venv_root), str(venv_root)))
        # Inside the sandbox, invoke the interpreter via its venv path so the
        # child sees ``sys.prefix`` pointing at the venv (not the system
        # Python that ``bin/python`` symlinks to).
        python_executable = str(venv_root / "bin" / python_path.name)
    else:
        # No venv detected: use the resolved interpreter path but make sure
        # its directory tree is bound.
        resolved = python_path.resolve()
        if resolved.parent.name == "bin":
            venv_root = resolved.parent.parent
            if venv_root.exists():
                bind_targets.append((str(venv_root), str(venv_root)))

    command: list[str] = [
        bwrap,
        "--die-with-parent",
        "--unshare-user-try",
        "--unshare-net",
        "--unshare-pid",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/etc",
        "--bind",
        tmpdir,
        "/work",
        "--chdir",
        "/work",
        "--setenv",
        "HOME",
        "/work",
        "--setenv",
        "MPLBACKEND",
        "Agg",
    ]
    # Minimal /etc so locale/nss libraries initialize without host user data.
    etc_files = {
        "/etc/passwd": "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n",
        "/etc/group": "nobody:x:65534:\n",
        "/etc/nsswitch.conf": "passwd: files\ngroup: files\nhosts: files\n",
        "/etc/hosts": "127.0.0.1 localhost\n",
        "/etc/hostname": "qa-sandbox\n",
    }
    etc_tmpdir = Path(tmpdir) / ".etc"
    etc_tmpdir.mkdir(parents=True, exist_ok=True)
    for filename, content in etc_files.items():
        (etc_tmpdir / Path(filename).name).write_text(content, encoding="utf-8")
    for filename in etc_files:
        command.extend(
            ["--ro-bind", str(etc_tmpdir / Path(filename).name), filename]
        )
    for src, dst in bind_targets:
        command.extend(["--ro-bind", src, dst])
    # Inside the sandbox the tmpdir is mounted at /work, so the program is at
    # /work/program.py (not the host absolute path).
    command.extend(
        [python_executable, "-X", "faulthandler", "-I", "/work/program.py"]
    )
    return command


async def _read_stream_bounded(
    stream: asyncio.StreamReader,
    limit: int,
    output_exceeded: asyncio.Event,
) -> tuple[bytes, bool]:
    """Drain a pipe incrementally while retaining at most ``limit`` bytes.

    Draining continues after the retained limit so the child cannot deadlock
    on a full pipe.  The first overflow signals the supervisor, which kills
    the whole process group.  At no point is unbounded child output held in
    the runner process.
    """

    retained = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        remaining = max(0, limit - len(retained))
        if remaining:
            retained.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
            output_exceeded.set()
    return bytes(retained), truncated


def _parse_metrics(stdout_bounded: str) -> dict[str, str | int | float | bool]:
    """Extract the final ``### METRICS_JSON: {...}`` line from stdout."""

    for line in reversed(stdout_bounded.splitlines()):
        stripped = line.strip()
        if stripped.startswith(_METRICS_MARKER):
            payload = stripped[len(_METRICS_MARKER):].strip()
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return {
                    key: value
                    for key, value in parsed.items()
                    if isinstance(value, str | int | float | bool)
                }
    return {}


class SubprocessSandbox:
    """Async subprocess sandbox implementing ``SandboxExecutor`` + ``execute_program``."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        default_limits: SandboxLimits | None = None,
    ) -> None:
        self._python = python_executable or sys.executable
        self._default_limits = default_limits or SandboxLimits()

    async def execute_program(
        self,
        artifact: CodeArtifact,
        limits: SandboxLimits | None = None,
    ) -> CodeExecutionResult:
        """Run the artifact's program and return a bounded, sanitized result."""

        report = validate_code_safety(artifact.code)
        if not report.ok:
            return CodeExecutionResult(
                completed=False,
                exit_code=None,
                timed_out=False,
                stdout_bounded="",
                stderr_bounded="static safety validation rejected the program: "
                + "; ".join(report.violations)[: _MAX_STDERR_BYTES],
                duration_seconds=0.0,
            )
        bound = limits or self._default_limits
        run = await self._run(artifact.code, bound)
        return run.result

    async def execute_program_with_figure(
        self,
        artifact: CodeArtifact,
        limits: SandboxLimits | None = None,
    ) -> _SandboxRun:
        """Like :meth:`execute_program` but also returns the captured figure."""

        report = validate_code_safety(artifact.code)
        if not report.ok:
            return _SandboxRun(
                result=CodeExecutionResult(
                    completed=False,
                    exit_code=None,
                    timed_out=False,
                    stdout_bounded="",
                    stderr_bounded="static safety validation rejected the program: "
                    + "; ".join(report.violations)[: _MAX_STDERR_BYTES],
                    duration_seconds=0.0,
                ),
                figure_png_base64=None,
                metrics={},
            )
        bound = limits or self._default_limits
        return await self._run(artifact.code, bound)


    def execute(
        self,
        request: CodeTestRequest,
        limits: SandboxLimits,
    ) -> SandboxExecutionOutcome:
        """Synchronous ``SandboxExecutor`` protocol method for ``CodeTestRequest``.

        Runs the asyncio loop inline so ``ScientificToolbox.verify`` (which is
        sync and called via ``asyncio.to_thread`` from the tutor node) can use
        this sandbox for ``CodeTestRequest``.
        """

        return asyncio.run(self._execute_sync(request, limits))

    async def _execute_sync(
        self,
        request: CodeTestRequest,
        limits: SandboxLimits,
    ) -> SandboxExecutionOutcome:
        runner = "\n".join(
            [
                "import sys, json, traceback",
                "tests = " + json.dumps(request.tests),
                "results = []",
                "for i, test in enumerate(tests):",
                "    try:",
                "        exec(compile(test, f'<test-{i}>', 'exec'), {})",
                "        results.append(True)",
                "    except BaseException:",
                "        results.append(False)",
                "        traceback.print_exc(file=sys.stderr)",
                "print('### TESTS_JSON: ' + json.dumps({'ran': len(results), "
                "'failed': sum(1 for r in results if not r)}))",
            ]
        )
        program = request.code + "\n\n" + runner
        report = validate_code_safety(program)
        if not report.ok:
            return SandboxExecutionOutcome(
                completed=False,
                exit_code=None,
                timed_out=False,
                tests_run=0,
                tests_failed=0,
            )
        result = await self._run(program, limits, capture_figure=False)
        run_result = result.result
        if not run_result.completed:
            return SandboxExecutionOutcome(
                completed=False,
                exit_code=run_result.exit_code,
                timed_out=run_result.timed_out,
                tests_run=0,
                tests_failed=0,
            )
        # Parse the tests-json line from stdout.
        ran, failed = 0, 0
        for line in reversed(run_result.stdout_bounded.splitlines()):
            stripped = line.strip()
            if stripped.startswith("### TESTS_JSON:"):
                try:
                    payload = json.loads(stripped[len("### TESTS_JSON:"):].strip())
                    ran = int(payload.get("ran", 0))
                    failed = int(payload.get("failed", 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                break
        return SandboxExecutionOutcome(
            completed=True,
            exit_code=run_result.exit_code,
            timed_out=False,
            tests_run=ran,
            tests_failed=failed,
        )

    async def _run(
        self,
        code: str,
        limits: SandboxLimits,
        *,
        capture_figure: bool = True,
    ) -> _SandboxRun:
        """Spawn the child Python process with rlimits + scrubbed env + timeout."""

        tmpdir = tempfile.mkdtemp(prefix="qa-sandbox-")
        program_path = Path(tmpdir) / "program.py"
        try:
            program_path.write_text(code, encoding="utf-8")
            env = _scrubbed_env(tmpdir)
            started = time.monotonic()
            try:
                bwrap = (
                    shutil.which("bwrap")
                    if os.getenv("CODING_SANDBOX_REQUIRE_ISOLATION") == "true"
                    else None
                )
                if bwrap:
                    command = _bwrap_command(bwrap, self._python, tmpdir)
                    # bwrap itself creates namespaces via clone/unshare; applying
                    # ``RLIMIT_NPROC`` in preexec_fn (run after fork in the bwrap
                    # parent) breaks namespace creation with
                    # ``Resource temporarily unavailable``.  Use the bwrap-safe
                    # rlimit set (no NPROC, generous RLIMIT_AS) instead.
                    preexec: Callable[[], None] | None = partial(
                        _apply_bwrap_rlimits, limits
                    )
                else:
                    command = [self._python, "-X", "faulthandler", "-I", str(program_path)]
                    preexec = lambda: _apply_rlimits(limits)  # noqa: E731
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=tmpdir,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    preexec_fn=preexec,
                    start_new_session=True,
                )
            except OSError as exc:
                raise SandboxError(
                    f"failed to start sandbox process: {type(exc).__name__}"
                ) from exc

            wall = max(0.5, float(limits.wall_time_seconds))
            timed_out = False
            output_exceeded = asyncio.Event()
            assert process.stdout is not None
            assert process.stderr is not None
            stdout_task = asyncio.create_task(
                _read_stream_bounded(process.stdout, _MAX_STDOUT_BYTES, output_exceeded)
            )
            stderr_task = asyncio.create_task(
                _read_stream_bounded(process.stderr, _MAX_STDERR_BYTES, output_exceeded)
            )
            overflow_task = asyncio.create_task(output_exceeded.wait())
            wait_task = asyncio.create_task(process.wait())
            try:
                done, _pending = await asyncio.wait(
                    {wait_task, overflow_task},
                    timeout=wall,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if overflow_task in done and output_exceeded.is_set():
                    await self._kill_group(process)
                    await process.wait()
                elif wait_task not in done:
                    timed_out = True
                    await self._kill_group(process)
                    await process.wait()
            finally:
                overflow_task.cancel()
                with suppress(asyncio.CancelledError):
                    await overflow_task
            if process.returncode is None:
                timed_out = True
                await self._kill_group(process)
                await process.wait()

            stdout_bytes, stdout_truncated = await stdout_task
            stderr_bytes, stderr_truncated = await stderr_task

            elapsed = max(0.0, time.monotonic() - started)
            stdout_text, _ = _bounded(stdout_bytes, _MAX_STDOUT_BYTES)
            stderr_text, _ = _bounded(stderr_bytes, _MAX_STDERR_BYTES)
            if stdout_truncated:
                stdout_text = _bounded(stdout_bytes + b"x", _MAX_STDOUT_BYTES)[0]
            if stderr_truncated:
                stderr_text = _bounded(stderr_bytes + b"x", _MAX_STDERR_BYTES)[0]

            figure_b64: str | None = None
            if capture_figure and not timed_out:
                figure_path = Path(tmpdir) / _FIGURE_PATH
                if figure_path.exists():
                    figure_bytes = figure_path.read_bytes()
                    if 0 < len(figure_bytes) <= _MAX_FIGURE_BYTES:
                        figure_b64 = base64.b64encode(figure_bytes).decode("ascii")

            exit_code = process.returncode
            completed = (not timed_out) and exit_code == 0
            result = CodeExecutionResult(
                completed=completed,
                exit_code=exit_code,
                timed_out=timed_out,
                truncated=stdout_truncated or stderr_truncated,
                stdout_bounded=stdout_text,
                stderr_bounded=stderr_text,
                duration_seconds=elapsed,
            )
            metrics = _parse_metrics(stdout_text) if completed else {}
            return _SandboxRun(
                result=result,
                figure_png_base64=figure_b64,
                metrics=metrics,
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    async def _kill_group(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, 9)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except ProcessLookupError:
                pass

class RemoteSandbox:
    """HTTP client for the dedicated no-secret sandbox runner."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 15.0) -> None:
        if not endpoint.startswith("unix://"):
            raise ValueError("the isolated sandbox endpoint must be a Unix-domain socket")
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout_seconds

    async def execute_program(
        self, artifact: CodeArtifact, limits: SandboxLimits | None = None
    ) -> CodeExecutionResult:
        report = validate_code_safety(artifact.code)
        if not report.ok:
            return CodeExecutionResult(
                completed=False, stderr_bounded="static safety validation rejected the program"
            )
        try:
            transport = None
            base = self._endpoint
            if base.startswith("unix://"):
                transport = httpx.AsyncHTTPTransport(uds=base.removeprefix("unix://"))
                base = "http://sandbox"
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=transport, base_url=base
            ) as client:
                response = await client.post(
                    "/execute",
                    json={
                        "code": artifact.code,
                        "limits": (limits or SandboxLimits()).model_dump(),
                    },
                )
                response.raise_for_status()
                return CodeExecutionResult.model_validate(response.json())
        except Exception as exc:
            return CodeExecutionResult(
                completed=False,
                stderr_bounded=f"isolated runner unavailable: {type(exc).__name__}",
            )

    async def execute_program_with_figure(
        self, artifact: CodeArtifact, limits: SandboxLimits | None = None
    ) -> _SandboxRun:
        result = await self.execute_program(artifact, limits)
        return _SandboxRun(
            result=result, figure_png_base64=None, metrics=_parse_metrics(result.stdout_bounded)
        )


__all__ = [
    "RemoteSandbox",
    "SandboxDisabled",
    "SandboxError",
    "SubprocessSandbox",
]
