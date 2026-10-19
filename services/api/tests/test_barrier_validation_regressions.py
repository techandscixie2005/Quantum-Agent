"""Offline numerical regressions; no model calls or classroom claims."""

from __future__ import annotations

import math

import pytest

from quantum_agent.coding.agent import _verify_against_oracle
from quantum_agent.coding.models import CodeVerificationStatus
from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest, ScientificVerificationStatus
from tests.test_coding_agent import _tunnelling_task


def _request(width: float = 2e-9) -> RectangularBarrierRequest:
    return RectangularBarrierRequest(
        energy_eV=5,
        barrier_height_eV=10,
        barrier_width_m=width,
        particle_mass_kg=9.1093837015e-31,
    )


@pytest.mark.parametrize("width", [1e-10, 1e-9, 2e-9, 5e-9, 1e-8])
def test_positive_transmission_agrees_relatively_over_many_orders(width: float) -> None:
    result = ScientificToolbox().verify(_request(width))
    assert result.status is ScientificVerificationStatus.PASS
    transmission = float(result.metrics["T"])
    reference = float(result.metrics["reference_T"])
    assert 0 < transmission <= 1
    assert math.isclose(transmission, reference, rel_tol=1e-8, abs_tol=0)
    assert float(result.metrics["reference_relative_error"]) <= 1e-8
    assert result.metrics["transmission_comparison"] == "positive_relative_v2"


@pytest.mark.parametrize("factor", [0.0, 0.5, 2.0])
def test_tiny_transmission_cannot_hide_wrong_formula_in_absolute_floor(
    monkeypatch: pytest.MonkeyPatch, factor: float,
) -> None:
    # Alter only the independent reference, preserving apparent conservation.
    # Old abs_tol=1e-12 accepted all three errors for T around 5e-20.
    correct = ScientificToolbox().verify(_request())
    transmission = float(correct.metrics["T"])
    monkeypatch.setattr(
        "quantum_agent.science.toolbox.boundary_probabilities",
        lambda *args: (transmission * factor, 1.0),
    )
    result = ScientificToolbox().verify(_request())
    assert result.status is ScientificVerificationStatus.FAIL
    assert float(result.metrics["conservation_error"]) < 1e-9


def test_analytic_zero_does_not_certify_a_finite_barrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("quantum_agent.science.toolbox.math.sinh", lambda value: math.inf)
    result = ScientificToolbox().verify(_request())
    assert result.metrics["T"] == 0
    assert float(result.metrics["reference_T"]) > 0
    assert result.status is ScientificVerificationStatus.FAIL


def test_optional_scan_failure_preserves_independently_valid_point() -> None:
    # kappa*a ~=229 is representable; the automatic scan to 2a exceeds300.
    # The unavailable visualization must not erase valid T/R evidence.
    result = ScientificToolbox().verify(_request(2e-8))
    assert result.status is ScientificVerificationStatus.PASS
    assert 0 < float(result.metrics["T"]) < 1e-190
    assert float(result.metrics["reference_relative_error"]) < 1e-8
    assert result.visualization is None
    assert result.metrics["visualization_status"] == "omitted_outside_verified_range"
    assert any("scan omitted" in observation for observation in result.observations)


def test_above_barrier_resonance_accepts_reference_roundoff_without_clipping() -> None:
    request = RectangularBarrierRequest(
        energy_eV=10.1, barrier_height_eV=5.6, barrier_width_m=2.890713722541106e-10,
        particle_mass_kg=9.1093837015e-31,
    )
    result = ScientificToolbox().verify(request)
    assert result.status is ScientificVerificationStatus.PASS
    assert result.metrics["T"] == 1
    assert math.isclose(float(result.metrics["reference_T"]), 1, rel_tol=0,
                        abs_tol=float(result.metrics["reference_probability_roundoff_tolerance"]))
    assert float(result.metrics["reference_relative_error"]) < 1e-14


@pytest.mark.parametrize("overshoot", [1e-10, 1e-4])
def test_probability_upper_bound_is_not_relaxed_by_user_conservation_tolerance(
    monkeypatch: pytest.MonkeyPatch, overshoot: float,
) -> None:
    request = RectangularBarrierRequest(
        energy_eV=10.1, barrier_height_eV=5.6, barrier_width_m=2.890713722541106e-10,
        particle_mass_kg=9.1093837015e-31, conservation_tolerance=1e-2,
    )
    monkeypatch.setattr("quantum_agent.science.toolbox.boundary_probabilities",
                        lambda *args: (1 + overshoot, 0))
    result = ScientificToolbox().verify(request)
    assert result.status is ScientificVerificationStatus.FAIL
    assert result.metrics["reference_T"] == 1 + overshoot


def test_underflow_range_is_inconclusive_and_never_returns_zero_evidence() -> None:
    result = ScientificToolbox().verify(_request(1e-4))
    assert result.status is ScientificVerificationStatus.INCONCLUSIVE
    assert "T" not in result.metrics
    assert result.visualization is None


@pytest.mark.parametrize("factor", [0.0, 0.5, 2.0, 1e9])
def test_coding_oracle_rejects_near_zero_absolute_tolerance_loophole(factor: float) -> None:
    task = _tunnelling_task()
    task = task.model_copy(
        update={"known_variables": task.known_variables | {"barrier_width_m": "2e-9"}},
    )
    reference = ScientificToolbox().verify(_request())
    transmission = float(reference.metrics["T"]) * factor
    result = _verify_against_oracle(
        task, {"T": transmission, "R": 1 - transmission, "conservation_error": 0.0},
    )
    assert result.status is CodeVerificationStatus.FAIL
    assert "relative tolerance" in result.observations[-1]


def test_coding_oracle_accepts_small_relative_roundoff_at_tiny_transmission() -> None:
    task = _tunnelling_task()
    task = task.model_copy(
        update={"known_variables": task.known_variables | {"barrier_width_m": "2e-9"}},
    )
    reference = ScientificToolbox().verify(_request())
    transmission = float(reference.metrics["T"]) * (1 + 1e-8)
    result = _verify_against_oracle(
        task, {"T": transmission, "R": 1 - transmission, "conservation_error": 0.0},
    )
    assert result.status is CodeVerificationStatus.PASS
