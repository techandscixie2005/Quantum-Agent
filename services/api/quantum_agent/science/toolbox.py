"""Bounded deterministic scientific tools used by the teaching state machine."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import multiprocessing
from collections.abc import Mapping
from multiprocessing.queues import Queue
from typing import Any, Protocol, cast

from pydantic import TypeAdapter

from quantum_agent.science.models import (
    CodeTestRequest,
    LineVisualizationRequest,
    NumericalNormalizationRequest,
    NumericalUnitarityRequest,
    PlotSeries,
    SandboxExecutionOutcome,
    SandboxLimits,
    ScientificVerificationMethod,
    ScientificVerificationRequest,
    ScientificVerificationResult,
    ScientificVerificationStatus,
    SymbolicEquivalenceRequest,
    SymbolicResidualRequest,
    ToolIdentity,
    TwoLevelSimulationRequest,
    UnverifiedRequest,
    VisualizationSpec,
)

_REQUEST_ADAPTER: TypeAdapter[ScientificVerificationRequest] = TypeAdapter(
    ScientificVerificationRequest
)
_MAX_AST_NODES = 128
_MAX_AST_DEPTH = 20
_MAX_FUNCTION_CALLS = 24
_MAX_RESULT_OPERATIONS = 512


class UnsafeExpressionError(ValueError):
    """The input falls outside the deliberately small mathematical grammar."""


class SandboxExecutor(Protocol):
    """Protocol for a separately deployed, restricted container executor.

    The API process never executes submitted code itself.  Implementations must
    enforce the supplied limits outside the API host and return only the
    sanitized outcome contract.
    """

    def execute(
        self,
        request: CodeTestRequest,
        limits: SandboxLimits,
    ) -> SandboxExecutionOutcome: ...


def _digest_request(request: ScientificVerificationRequest) -> str:
    payload = request.model_dump(mode="json")
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _tool(name: str, version: str) -> ToolIdentity:
    return ToolIdentity(name=name, version=version)


def _result(
    request: ScientificVerificationRequest,
    *,
    method: ScientificVerificationMethod,
    status: ScientificVerificationStatus,
    tool: ToolIdentity,
    observations: list[str],
    limitations: list[str],
    metrics: dict[str, float | int | str | bool] | None = None,
    visualization: VisualizationSpec | None = None,
    error_code: str | None = None,
) -> ScientificVerificationResult:
    return ScientificVerificationResult(
        kind=request.kind,
        method=method,
        status=status,
        tool=tool,
        inputs_sha256=_digest_request(request),
        observations=observations,
        limitations=limitations,
        metrics=metrics or {},
        visualization=visualization,
        error_code=error_code,
    )


class _SafeSympyBuilder:
    """Convert a Python expression AST to SymPy without eval or sympify."""

    def __init__(self, symbol_names: tuple[str, ...]) -> None:
        import sympy as sp  # type: ignore[import-untyped]

        self._sp = sp
        self._symbols = {name: sp.Symbol(name) for name in symbol_names}
        self._node_count = 0
        self._function_calls = 0

    def parse(self, source: str) -> Any:
        try:
            parsed = ast.parse(source, mode="eval")
        except (SyntaxError, ValueError, MemoryError) as exc:
            raise UnsafeExpressionError("expression syntax is invalid") from exc
        return self._build(parsed.body, depth=1)

    def _visit_guard(self, depth: int) -> None:
        self._node_count += 1
        if self._node_count > _MAX_AST_NODES or depth > _MAX_AST_DEPTH:
            raise UnsafeExpressionError("expression exceeds the structural budget")

    def _build(self, node: ast.AST, *, depth: int) -> Any:
        self._visit_guard(depth)
        sp = self._sp

        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise UnsafeExpressionError("only real numeric literals are allowed")
            if isinstance(value, int):
                if abs(value) > 10**12:
                    raise UnsafeExpressionError("integer literal exceeds the magnitude guard")
                return sp.Integer(value)
            if not math.isfinite(value) or abs(value) > 10**12:
                raise UnsafeExpressionError("float literal exceeds the magnitude guard")
            return sp.Float(value)

        if isinstance(node, ast.Name):
            if node.id in self._symbols:
                return self._symbols[node.id]
            constants = {"pi": sp.pi, "E": sp.E, "I": sp.I}
            if node.id in constants:
                return constants[node.id]
            raise UnsafeExpressionError("expression uses an undeclared name")

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = self._build(node.operand, depth=depth + 1)
            return operand if isinstance(node.op, ast.UAdd) else -operand

        if isinstance(node, ast.BinOp):
            left = self._build(node.left, depth=depth + 1)
            right = self._build(node.right, depth=depth + 1)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                if not isinstance(right, sp.Integer) or not (-12 <= int(right) <= 12):
                    raise UnsafeExpressionError("powers require a bounded integer exponent")
                return left**right
            raise UnsafeExpressionError("operator is not in the mathematical allowlist")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise UnsafeExpressionError("only direct allowlisted function calls are allowed")
            self._function_calls += 1
            if self._function_calls > _MAX_FUNCTION_CALLS:
                raise UnsafeExpressionError("expression exceeds the function-call budget")
            functions = {
                "Abs": sp.Abs,
                "acos": sp.acos,
                "asin": sp.asin,
                "atan": sp.atan,
                "conjugate": sp.conjugate,
                "cos": sp.cos,
                "cosh": sp.cosh,
                "exp": sp.exp,
                "im": sp.im,
                "log": sp.log,
                "re": sp.re,
                "sin": sp.sin,
                "sinh": sp.sinh,
                "sqrt": sp.sqrt,
                "tan": sp.tan,
                "tanh": sp.tanh,
            }
            function = functions.get(node.func.id)
            if function is None or len(node.args) != 1:
                raise UnsafeExpressionError("function is not in the unary-function allowlist")
            return function(self._build(node.args[0], depth=depth + 1))

        raise UnsafeExpressionError("expression contains a prohibited syntax form")


def _symbolic_worker(
    payload: Mapping[str, object],
    output: Queue[dict[str, object]],
) -> None:
    """Isolated SymPy worker.  Its parent enforces the wall-time limit."""

    try:
        import sympy as sp

        raw_symbols = payload["symbols"]
        if not isinstance(raw_symbols, (list, tuple)) or not all(
            isinstance(item, str) for item in raw_symbols
        ):
            raise UnsafeExpressionError("symbol declaration is invalid")
        symbols = tuple(cast(list[str] | tuple[str, ...], raw_symbols))
        builder = _SafeSympyBuilder(symbols)
        expression = builder.parse(cast(str, payload["left"]))
        if "right" in payload:
            expression -= builder.parse(cast(str, payload["right"]))
        residual = sp.trigsimp(sp.cancel(sp.together(expression)))
        operation_count = int(sp.count_ops(residual))
        if operation_count > _MAX_RESULT_OPERATIONS:
            output.put({"outcome": "budget_exceeded"})
            return
        residual_text = str(residual)
        if len(residual_text) > 240:
            output.put({"outcome": "budget_exceeded"})
            return
        if residual == 0 or residual.is_zero is True:
            outcome = "zero"
        elif residual.is_zero is False or not residual.free_symbols:
            outcome = "nonzero"
        else:
            outcome = "unknown"
        output.put(
            {
                "outcome": outcome,
                "operations": operation_count,
                "residual": residual_text,
            }
        )
    except UnsafeExpressionError:
        output.put({"outcome": "rejected"})
    except Exception:
        output.put({"outcome": "tool_error"})


def _verify_symbolic(
    request: SymbolicEquivalenceRequest | SymbolicResidualRequest,
) -> ScientificVerificationResult:
    import sympy as sp

    payload: dict[str, object] = {"symbols": request.symbols}
    if isinstance(request, SymbolicEquivalenceRequest):
        payload.update(left=request.left, right=request.right)
    else:
        payload.update(left=request.expression)

    context = multiprocessing.get_context("spawn")
    output: Queue[dict[str, object]] = context.Queue(maxsize=1)
    process = context.Process(target=_symbolic_worker, args=(payload, output), daemon=True)
    process.start()
    process.join(request.timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1.0)
        output.close()
        return _result(
            request,
            method=ScientificVerificationMethod.SYMBOLIC,
            status=ScientificVerificationStatus.INCONCLUSIVE,
            tool=_tool("sympy", sp.__version__),
            observations=["Symbolic verification exceeded its isolated wall-time budget."],
            limitations=["No mathematical conclusion was drawn after the timeout."],
            error_code="SYMBOLIC_TIMEOUT",
        )

    try:
        message = output.get_nowait()
    except Exception:
        message = {"outcome": "tool_error"}
    finally:
        output.close()

    outcome = message.get("outcome")
    if outcome == "rejected":
        return _result(
            request,
            method=ScientificVerificationMethod.SYMBOLIC,
            status=ScientificVerificationStatus.INCONCLUSIVE,
            tool=_tool("sympy", sp.__version__),
            observations=["The expression was rejected by the safe mathematical parser."],
            limitations=[
                "Only declared symbols and the bounded operator/function allowlist are accepted."
            ],
            error_code="UNSAFE_EXPRESSION_REJECTED",
        )
    if outcome in {"budget_exceeded", "tool_error"}:
        code = "SYMBOLIC_SIZE_LIMIT" if outcome == "budget_exceeded" else "SYMBOLIC_TOOL_ERROR"
        return _result(
            request,
            method=ScientificVerificationMethod.SYMBOLIC,
            status=ScientificVerificationStatus.INCONCLUSIVE,
            tool=_tool("sympy", sp.__version__),
            observations=["The bounded symbolic tool did not produce a conclusive residual."],
            limitations=["The result-size guard or symbolic backend prevented a conclusion."],
            error_code=code,
        )

    residual = cast(str, message.get("residual", "unknown"))
    operations = cast(int, message.get("operations", 0))
    if outcome == "zero":
        status = ScientificVerificationStatus.PASS
        observation = "The bounded symbolic residual reduced exactly to zero."
    elif outcome == "nonzero":
        status = ScientificVerificationStatus.FAIL
        observation = "The bounded symbolic residual is nonzero."
    else:
        status = ScientificVerificationStatus.INCONCLUSIVE
        observation = "The symbolic residual could not be proven zero or nonzero."
    return _result(
        request,
        method=ScientificVerificationMethod.SYMBOLIC,
        status=status,
        tool=_tool("sympy", sp.__version__),
        observations=[observation],
        limitations=[
            "Equivalence is evaluated on the common domain where both expressions are defined.",
            "This algebraic verification is not a physical proof.",
        ],
        metrics={"residual": residual, "operation_count": operations},
    )


def _verify_normalization(
    request: NumericalNormalizationRequest,
) -> ScientificVerificationResult:
    import numpy as np

    state = np.asarray([value.as_complex() for value in request.state], dtype=np.complex128)
    norm = float(np.vdot(state, state).real)
    residual = abs(norm - request.target_norm_squared)
    status = (
        ScientificVerificationStatus.PASS
        if residual <= request.absolute_tolerance
        else ScientificVerificationStatus.FAIL
    )
    return _result(
        request,
        method=ScientificVerificationMethod.NUMERICAL,
        status=status,
        tool=_tool("numpy", np.__version__),
        observations=[f"Computed inner-product norm squared: {norm:.16g}."],
        limitations=["Finite-precision complex128 arithmetic was used."],
        metrics={
            "dimension": len(request.state),
            "norm_squared": norm,
            "absolute_residual": residual,
            "absolute_tolerance": request.absolute_tolerance,
        },
    )


def _verify_unitarity(request: NumericalUnitarityRequest) -> ScientificVerificationResult:
    import numpy as np
    import scipy  # type: ignore[import-untyped]
    from scipy import linalg

    matrix = np.asarray(
        [[value.as_complex() for value in row] for row in request.matrix],
        dtype=np.complex128,
    )
    identity = np.eye(matrix.shape[0], dtype=np.complex128)
    residual_matrix = matrix.conjugate().T @ matrix - identity
    residual = float(linalg.norm(residual_matrix, ord=2))
    status = (
        ScientificVerificationStatus.PASS
        if residual <= request.absolute_tolerance
        else ScientificVerificationStatus.FAIL
    )
    return _result(
        request,
        method=ScientificVerificationMethod.NUMERICAL,
        status=status,
        tool=_tool("numpy/scipy", f"{np.__version__}/{scipy.__version__}"),
        observations=[f"Computed spectral norm of U†U - I: {residual:.16g}."],
        limitations=["Finite-precision complex128 arithmetic and an absolute tolerance were used."],
        metrics={
            "dimension": matrix.shape[0],
            "spectral_residual": residual,
            "absolute_tolerance": request.absolute_tolerance,
        },
    )


def _render_line_spec(request: LineVisualizationRequest) -> VisualizationSpec:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    figure, axes = plt.subplots(figsize=(6.0, 3.5), dpi=100)
    colors = ("#173F5F", "#A64B2A", "#40755C", "#755C91", "#8A6A12", "#3E6D73")
    try:
        for index, series in enumerate(request.series):
            axes.plot(
                request.x,
                series.y,
                color=colors[index % len(colors)],
                linewidth=1.6,
                label=series.label,
            )
        axes.set_title(request.title)
        axes.set_xlabel(request.x_label)
        axes.set_ylabel(request.y_label)
        axes.grid(visible=True, linewidth=0.5, alpha=0.3)
        axes.legend(loc="best", frameon=False)
        figure.tight_layout()
        figure.canvas.draw()
        canvas = cast(Any, figure.canvas)
        rendering_digest = hashlib.sha256(bytes(canvas.buffer_rgba())).hexdigest()
    finally:
        plt.close(figure)

    return VisualizationSpec(
        renderer=_tool("matplotlib", matplotlib.__version__),
        title=request.title,
        x_label=request.x_label,
        y_label=request.y_label,
        x=request.x,
        series=request.series,
        rendering_sha256=rendering_digest,
    )


def _verify_visualization(request: LineVisualizationRequest) -> ScientificVerificationResult:
    import matplotlib

    try:
        spec = _render_line_spec(request)
    except Exception:
        return _result(
            request,
            method=ScientificVerificationMethod.NUMERICAL,
            status=ScientificVerificationStatus.INCONCLUSIVE,
            tool=_tool("matplotlib", matplotlib.__version__),
            observations=["The deterministic renderer did not produce a visualization spec."],
            limitations=["No file or encoded image fallback is emitted by this tool."],
            error_code="VISUALIZATION_TOOL_ERROR",
        )
    return _result(
        request,
        method=ScientificVerificationMethod.NUMERICAL,
        status=ScientificVerificationStatus.PASS,
        tool=_tool("matplotlib", matplotlib.__version__),
        observations=["A deterministic line-plot data specification was rendered in memory."],
        limitations=[
            "The specification visualizes supplied data; it does not validate the data's physics."
        ],
        metrics={"point_count": len(request.x), "series_count": len(request.series)},
        visualization=spec,
    )


def _verify_two_level(request: TwoLevelSimulationRequest) -> ScientificVerificationResult:
    import numpy as np
    import qutip as qt  # type: ignore[import-untyped]

    initial_values = np.asarray(
        [value.as_complex() for value in request.initial_state], dtype=np.complex128
    )
    initial_norm = float(np.vdot(initial_values, initial_values).real)
    if abs(initial_norm - 1.0) > request.absolute_tolerance:
        return _result(
            request,
            method=ScientificVerificationMethod.SIMULATION,
            status=ScientificVerificationStatus.FAIL,
            tool=_tool("qutip", qt.__version__),
            observations=[f"Initial-state norm squared is {initial_norm:.16g}, not one."],
            limitations=["Evolution was not run for a state outside the normalization tolerance."],
            metrics={"initial_norm_squared": initial_norm},
            error_code="INITIAL_STATE_NOT_NORMALIZED",
        )

    try:
        state = qt.Qobj(initial_values, dims=[[2], [1]])
        hamiltonian = (
            0.5 * request.detuning * qt.sigmaz() + 0.5 * request.rabi_frequency * qt.sigmax()
        )
        times = np.linspace(0.0, request.duration, request.steps)
        ground_projector = qt.basis(2, 0).proj()
        excited_projector = qt.basis(2, 1).proj()
        evolution = qt.sesolve(
            hamiltonian,
            state,
            times,
            e_ops=[ground_projector, excited_projector],
            options={
                "atol": min(1e-12, request.absolute_tolerance / 100),
                "rtol": min(1e-12, request.absolute_tolerance / 100),
                "nsteps": 10_000,
                "normalize_output": False,
                "store_states": True,
            },
        )
        probabilities_0 = np.real(np.asarray(evolution.expect[0], dtype=float))
        probabilities_1 = np.real(np.asarray(evolution.expect[1], dtype=float))
        norms = np.asarray([float(item.norm() ** 2) for item in evolution.states])
    except Exception:
        return _result(
            request,
            method=ScientificVerificationMethod.SIMULATION,
            status=ScientificVerificationStatus.INCONCLUSIVE,
            tool=_tool("qutip", qt.__version__),
            observations=["The bounded two-level solver did not complete."],
            limitations=["No simulation conclusion was retained after the sanitized tool error."],
            error_code="SIMULATION_TOOL_ERROR",
        )

    max_norm_drift = float(np.max(np.abs(norms - 1.0)))
    probability_residual = float(np.max(np.abs(probabilities_0 + probabilities_1 - 1.0)))
    verified = max(max_norm_drift, probability_residual) <= request.absolute_tolerance
    plot_request = LineVisualizationRequest(
        title="Two-level state populations",
        x_label="time",
        y_label="population",
        x=[float(value) for value in times],
        series=[
            PlotSeries(label="|0⟩", y=[float(value) for value in probabilities_0]),
            PlotSeries(label="|1⟩", y=[float(value) for value in probabilities_1]),
        ],
    )
    try:
        spec = _render_line_spec(plot_request)
    except Exception:
        spec = None

    return _result(
        request,
        method=ScientificVerificationMethod.SIMULATION,
        status=(
            ScientificVerificationStatus.PASS if verified else ScientificVerificationStatus.FAIL
        ),
        tool=_tool("qutip", qt.__version__),
        observations=[
            (
                "QuTiP evolved a closed two-level Hamiltonian and checked norm and "
                "population conservation."
            ),
            (
                f"Final populations are P(0)={probabilities_0[-1]:.10g} and "
                f"P(1)={probabilities_1[-1]:.10g}."
            ),
        ],
        limitations=[
            (
                "This ideal two-level model omits decoherence, measurement back-action, "
                "and laboratory noise."
            )
        ],
        metrics={
            "steps": request.steps,
            "max_norm_drift": max_norm_drift,
            "max_probability_residual": probability_residual,
            "final_ground_population": float(probabilities_0[-1]),
            "final_excited_population": float(probabilities_1[-1]),
        },
        visualization=spec,
    )


class ScientificToolbox:
    """Single deterministic dispatch surface for the teaching state machine."""

    def __init__(self, *, sandbox_executor: SandboxExecutor | None = None) -> None:
        self._sandbox_executor = sandbox_executor

    @staticmethod
    def validate_request(payload: object) -> ScientificVerificationRequest:
        return _REQUEST_ADAPTER.validate_python(payload)

    def verify(
        self,
        request: ScientificVerificationRequest,
    ) -> ScientificVerificationResult:
        if isinstance(request, (SymbolicEquivalenceRequest, SymbolicResidualRequest)):
            return _verify_symbolic(request)
        if isinstance(request, NumericalNormalizationRequest):
            return _verify_normalization(request)
        if isinstance(request, NumericalUnitarityRequest):
            return _verify_unitarity(request)
        if isinstance(request, TwoLevelSimulationRequest):
            return _verify_two_level(request)
        if isinstance(request, LineVisualizationRequest):
            return _verify_visualization(request)
        if isinstance(request, CodeTestRequest):
            return self._verify_code(request)
        if isinstance(request, UnverifiedRequest):
            return _result(
                request,
                method=ScientificVerificationMethod.UNVERIFIED,
                status=ScientificVerificationStatus.INCONCLUSIVE,
                tool=_tool("none", "not-run"),
                observations=["The claim was explicitly retained as unverified model inference."],
                limitations=[request.reason],
                error_code="VERIFICATION_NOT_REQUESTED",
            )
        raise TypeError("Unsupported scientific verification request")

    def _verify_code(self, request: CodeTestRequest) -> ScientificVerificationResult:
        if self._sandbox_executor is None:
            return _result(
                request,
                method=ScientificVerificationMethod.CODE_TEST,
                status=ScientificVerificationStatus.INCONCLUSIVE,
                tool=_tool("restricted-container", "unavailable"),
                observations=["Submitted code was not executed on the API host."],
                limitations=["A separately deployed, restricted sandbox executor is required."],
                error_code="SANDBOX_UNAVAILABLE",
            )
        try:
            outcome = self._sandbox_executor.execute(request, SandboxLimits())
        except Exception:
            return _result(
                request,
                method=ScientificVerificationMethod.CODE_TEST,
                status=ScientificVerificationStatus.INCONCLUSIVE,
                tool=_tool("restricted-container", "external"),
                observations=["The external sandbox did not return a valid test outcome."],
                limitations=["Raw executor errors and process output are not exposed."],
                error_code="SANDBOX_TOOL_ERROR",
            )
        if outcome.timed_out or not outcome.completed:
            status = ScientificVerificationStatus.INCONCLUSIVE
        elif outcome.exit_code == 0 and outcome.tests_run > 0 and outcome.tests_failed == 0:
            status = ScientificVerificationStatus.PASS
        else:
            status = ScientificVerificationStatus.FAIL
        return _result(
            request,
            method=ScientificVerificationMethod.CODE_TEST,
            status=status,
            tool=_tool("restricted-container", "external"),
            observations=[
                f"The isolated executor ran {outcome.tests_run} tests; "
                f"{outcome.tests_failed} failed."
            ],
            limitations=[
                "A passing test suite establishes only the properties encoded by those tests."
            ],
            metrics={
                "tests_run": outcome.tests_run,
                "tests_failed": outcome.tests_failed,
                "timed_out": outcome.timed_out,
                "exit_code": (
                    outcome.exit_code if outcome.exit_code is not None else "not_available"
                ),
            },
            error_code="SANDBOX_TIMEOUT" if outcome.timed_out else None,
        )
