from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from quantum_agent.science import (
    CodeTestRequest,
    ComplexValue,
    LineVisualizationRequest,
    NumericalNormalizationRequest,
    NumericalUnitarityRequest,
    PlotSeries,
    ScientificToolbox,
    ScientificVerificationKind,
    ScientificVerificationMethod,
    ScientificVerificationStatus,
    SymbolicEquivalenceRequest,
    SymbolicResidualRequest,
    TwoLevelSimulationRequest,
    UnverifiedRequest,
)


def _complex(real: float = 0.0, imag: float = 0.0) -> ComplexValue:
    return ComplexValue(real=real, imag=imag)


def test_symbolic_equivalence_known_good_and_bad() -> None:
    toolbox = ScientificToolbox()
    good = toolbox.verify(
        SymbolicEquivalenceRequest(
            left="sin(theta)**2 + cos(theta)**2",
            right="1",
            symbols=("theta",),
        )
    )
    bad = toolbox.verify(SymbolicEquivalenceRequest(left="x + 1", right="x + 2", symbols=("x",)))

    assert good.method is ScientificVerificationMethod.SYMBOLIC
    assert good.status is ScientificVerificationStatus.PASS
    assert good.passed is True
    assert bad.status is ScientificVerificationStatus.FAIL
    assert bad.passed is False
    assert len(good.inputs_sha256) == 64
    assert good.observations and good.limitations


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "x.__class__",
        "(lambda: 1)()",
        "[x for x in (1, 2)]",
        "Matrix([[1]])",
        "x**999999",
        "undeclared + 1",
    ],
)
def test_symbolic_parser_rejects_adversarial_expressions(expression: str) -> None:
    result = ScientificToolbox().verify(
        SymbolicResidualRequest(expression=expression, symbols=("x",))
    )

    assert result.status is ScientificVerificationStatus.INCONCLUSIVE
    assert result.error_code == "UNSAFE_EXPRESSION_REJECTED"
    assert expression not in " ".join(result.observations + result.limitations)


def test_symbolic_request_bounds_symbol_names() -> None:
    with pytest.raises(ValidationError, match="safe identifier"):
        SymbolicResidualRequest(expression="x", symbols=("x;rm",))


def test_numerical_normalization_known_good_and_bad() -> None:
    toolbox = ScientificToolbox()
    amplitude = 1 / math.sqrt(2)
    good = toolbox.verify(
        NumericalNormalizationRequest(state=[_complex(amplitude), _complex(amplitude)])
    )
    bad = toolbox.verify(NumericalNormalizationRequest(state=[_complex(1.0), _complex(1.0)]))

    assert good.status is ScientificVerificationStatus.PASS
    assert good.tool.name == "numpy"
    assert bad.status is ScientificVerificationStatus.FAIL
    assert bad.metrics["norm_squared"] == pytest.approx(2.0)


def test_numerical_unitarity_known_good_and_bad() -> None:
    amplitude = 1 / math.sqrt(2)
    hadamard = [
        [_complex(amplitude), _complex(amplitude)],
        [_complex(amplitude), _complex(-amplitude)],
    ]
    nonunitary = [[_complex(1), _complex(1)], [_complex(), _complex(1)]]

    good = ScientificToolbox().verify(NumericalUnitarityRequest(matrix=hadamard))
    bad = ScientificToolbox().verify(NumericalUnitarityRequest(matrix=nonunitary))

    assert good.status is ScientificVerificationStatus.PASS
    assert good.tool.name == "numpy/scipy"
    assert bad.status is ScientificVerificationStatus.FAIL


def test_unitarity_rejects_non_square_input_before_computation() -> None:
    with pytest.raises(ValidationError, match="square matrix"):
        NumericalUnitarityRequest(matrix=[[_complex(1), _complex()]])


def test_qutip_two_level_rabi_simulation_conserves_probability() -> None:
    result = ScientificToolbox().verify(
        TwoLevelSimulationRequest(rabi_frequency=1.0, detuning=0.0, duration=math.pi, steps=81)
    )

    assert result.method is ScientificVerificationMethod.SIMULATION
    assert result.status is ScientificVerificationStatus.PASS
    assert result.tool.name == "qutip"
    assert result.metrics["final_excited_population"] == pytest.approx(1.0, abs=2e-6)
    assert result.visualization is not None
    assert result.visualization.kind == "line"
    assert len(result.visualization.x) == 81


def test_two_level_simulation_fails_closed_for_unnormalized_state() -> None:
    result = ScientificToolbox().verify(
        TwoLevelSimulationRequest(initial_state=[_complex(1), _complex(1)])
    )

    assert result.status is ScientificVerificationStatus.FAIL
    assert result.error_code == "INITIAL_STATE_NOT_NORMALIZED"


def test_two_level_simulation_rejects_excessive_evolution_work() -> None:
    with pytest.raises(ValidationError, match="evolution-work guard"):
        TwoLevelSimulationRequest(rabi_frequency=1e6, duration=1e4)


def test_matplotlib_visualization_returns_data_spec_not_file(tmp_path: object) -> None:
    del tmp_path  # The API intentionally has no output-path argument.
    request = LineVisualizationRequest(
        title="Probability",
        x_label="t",
        y_label="P",
        x=[0.0, 1.0, 2.0],
        series=[PlotSeries(label="P0", y=[1.0, 0.5, 0.0])],
    )
    first = ScientificToolbox().verify(request)
    second = ScientificToolbox().verify(request)

    assert first.status is ScientificVerificationStatus.PASS
    assert first.visualization is not None
    assert second.visualization is not None
    assert first.visualization.rendering_sha256 == second.visualization.rendering_sha256
    serialized = first.visualization.model_dump()
    assert "path" not in serialized and "file" not in serialized


def test_code_execution_is_fail_closed_without_external_sandbox() -> None:
    result = ScientificToolbox().verify(
        CodeTestRequest(code="print('must not run on host')", tests=["assert True"])
    )

    assert result.method is ScientificVerificationMethod.CODE_TEST
    assert result.status is ScientificVerificationStatus.INCONCLUSIVE
    assert result.error_code == "SANDBOX_UNAVAILABLE"


def test_unverified_claim_is_explicit_and_discriminated_payload_parses() -> None:
    toolbox = ScientificToolbox()
    request = toolbox.validate_request(
        {
            "kind": ScientificVerificationKind.UNVERIFIED,
            "claim": "A model-generated physical interpretation",
            "reason": "No course evidence or deterministic verification was available.",
        }
    )
    assert isinstance(request, UnverifiedRequest)

    result = toolbox.verify(request)
    assert result.method is ScientificVerificationMethod.UNVERIFIED
    assert result.status is ScientificVerificationStatus.INCONCLUSIVE
    assert result.tool.name == "none"
