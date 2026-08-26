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
    RectangularBarrierRequest,
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


# ---------------------------------------------------------------------------
# Rectangular-barrier tunnelling (P0-3): authoritative physics verification.
# ---------------------------------------------------------------------------

_ELECTRON_MASS_KG = 9.1093837015e-31


def _barrier_request(
    *,
    energy_eV: float = 5.0,
    barrier_height_eV: float = 10.0,
    barrier_width_m: float = 1e-10,
    particle_mass_kg: float = _ELECTRON_MASS_KG,
) -> RectangularBarrierRequest:
    return RectangularBarrierRequest(
        energy_eV=energy_eV,
        barrier_height_eV=barrier_height_eV,
        barrier_width_m=barrier_width_m,
        particle_mass_kg=particle_mass_kg,
    )


def test_rectangular_barrier_tunnelling_passes_conservation_and_bounds() -> None:
    result = ScientificToolbox().verify(_barrier_request())

    assert result.kind is ScientificVerificationKind.RECTANGULAR_BARRIER_TUNNELLING
    assert result.method is ScientificVerificationMethod.NUMERICAL
    assert result.status is ScientificVerificationStatus.PASS
    t = float(result.metrics["T"])
    r = float(result.metrics["R"])
    assert 0.0 <= t <= 1.0
    assert 0.0 <= r <= 1.0
    assert abs(r + t - 1.0) <= float(result.metrics["conservation_tolerance"])
    assert result.metrics["regime"] == "tunnelling"
    assert result.visualization is not None
    assert result.visualization.kind == "line"
    assert len(result.visualization.x) == 32


def test_rectangular_barrier_known_reference_value_for_electron_tunnelling() -> None:
    # For E=5 eV, V0=10 eV, a=1e-10 m, electron mass:
    # kappa = sqrt(2 * m_e * (V0-E)_J) / hbar_J_s
    # This is a deterministic textbook reference; the verifier must reproduce it.
    request = _barrier_request()
    result = ScientificToolbox().verify(request)
    t = float(result.metrics["T"])
    # The analytic T for these parameters is a small positive number (order 1e-2).
    assert 0.0 < t < 0.5
    # Manually recompute the expected T to confirm the tool matches the formula.
    import math as _math

    joule_per_eV = 1.602176634e-19
    hbar_j_s = 1.054571817e-34
    energy_j = 5.0 * joule_per_eV
    v0_j = 10.0 * joule_per_eV
    mass = _ELECTRON_MASS_KG
    width = 1e-10
    kappa = _math.sqrt(2.0 * mass * (v0_j - energy_j)) / hbar_j_s
    sinh_sq = _math.sinh(kappa * width) ** 2
    expected_t = 1.0 / (
        1.0 + (v0_j * v0_j * sinh_sq) / (4.0 * energy_j * (v0_j - energy_j))
    )
    assert t == pytest.approx(expected_t, rel=1e-9, abs=1e-12)


def test_rectangular_barrier_increasing_width_decreases_transmission() -> None:
    narrow = ScientificToolbox().verify(
        _barrier_request(barrier_width_m=5e-11)
    )
    wide = ScientificToolbox().verify(
        _barrier_request(barrier_width_m=2e-10)
    )
    t_narrow = float(narrow.metrics["T"])
    t_wide = float(wide.metrics["T"])
    assert t_wide < t_narrow, (
        f"wider barrier should reduce T: narrow={t_narrow}, wide={t_wide}"
    )


def test_rectangular_barrier_increasing_height_decreases_transmission() -> None:
    low = ScientificToolbox().verify(
        _barrier_request(barrier_height_eV=7.5)
    )
    high = ScientificToolbox().verify(
        _barrier_request(barrier_height_eV=15.0)
    )
    t_low = float(low.metrics["T"])
    t_high = float(high.metrics["T"])
    assert t_high < t_low, (
        f"higher barrier should reduce T: low={t_low}, high={t_high}"
    )


def test_rectangular_barrier_opaque_barrier_does_not_overflow() -> None:
    # A very wide / tall barrier drives sinh(kappa*a) toward overflow; the
    # verifier must fall back to the asymptotic form and still return a finite
    # T in [0, 1] with R+T=1.
    request = _barrier_request(
        barrier_height_eV=20.0,
        barrier_width_m=5e-9,
    )
    result = ScientificToolbox().verify(request)
    assert result.status is ScientificVerificationStatus.PASS
    t = float(result.metrics["T"])
    r = float(result.metrics["R"])
    assert math.isfinite(t)
    assert 0.0 <= t <= 1.0
    assert abs(r + t - 1.0) <= float(result.metrics["conservation_tolerance"])


def test_rectangular_barrier_free_propagation_regime_passes() -> None:
    # E > V0: the sin-based formula must also conserve probability.
    request = _barrier_request(
        energy_eV=12.0,
        barrier_height_eV=10.0,
        barrier_width_m=1e-10,
    )
    result = ScientificToolbox().verify(request)
    assert result.status is ScientificVerificationStatus.PASS
    assert result.metrics["regime"] == "free_propagation"
    t = float(result.metrics["T"])
    r = float(result.metrics["R"])
    assert 0.0 <= t <= 1.0
    assert abs(r + t - 1.0) <= float(result.metrics["conservation_tolerance"])


def test_rectangular_barrier_rejects_non_positive_energy() -> None:
    with pytest.raises(ValidationError):
        RectangularBarrierRequest(
            energy_eV=0.0,
            barrier_height_eV=10.0,
            barrier_width_m=1e-10,
            particle_mass_kg=_ELECTRON_MASS_KG,
        )


def test_rectangular_barrier_rejects_non_positive_barrier() -> None:
    with pytest.raises(ValidationError):
        RectangularBarrierRequest(
            energy_eV=5.0,
            barrier_height_eV=0.0,
            barrier_width_m=1e-10,
            particle_mass_kg=_ELECTRON_MASS_KG,
        )


def test_rectangular_barrier_rejects_degenerate_energy_equals_barrier() -> None:
    with pytest.raises(ValidationError, match="degenerate case"):
        RectangularBarrierRequest(
            energy_eV=10.0,
            barrier_height_eV=10.0,
            barrier_width_m=1e-10,
            particle_mass_kg=_ELECTRON_MASS_KG,
        )


def test_rectangular_barrier_displayed_metrics_equal_tool_metrics() -> None:
    # The frontend must display the same T/R the verifier computed; the result
    # contract carries them in `metrics` so there is one source of truth.
    result = ScientificToolbox().verify(_barrier_request())
    assert "T" in result.metrics
    assert "R" in result.metrics
    assert "conservation_error" in result.metrics
    assert "regime" in result.metrics
    observations_text = " ".join(result.observations)
    assert "T=" in observations_text
    assert "R=" in observations_text


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
