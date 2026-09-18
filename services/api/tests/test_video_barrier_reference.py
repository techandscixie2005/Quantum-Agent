"""Real deterministic physics tests; no gateway or numerical API mocks."""
import pytest

from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest


@pytest.mark.parametrize("energy,height,width_nm,expected", [
    (5, 10, .10, .3336822872), (5, 10, .20, .04010058292),
    (5, 10, .25, .01293164168), (4, 12, .12, .1046605190),
    (4, 12, .18, .01912986602),
])
def test_reference_checkpoints(energy: float, height: float, width_nm: float,
                               expected: float) -> None:
    result = ScientificToolbox().verify(RectangularBarrierRequest(
        particle_mass_kg=9.1093837015e-31,
        energy_eV=energy, barrier_height_eV=height, barrier_width_m=width_nm * 1e-9,
    ))
    assert result.status.value == "pass"
    assert result.metrics["T"] == pytest.approx(expected, abs=5e-11)
    assert result.metrics["reference_T"] == pytest.approx(expected, abs=5e-11)
    assert result.metrics["reference_method"] == "independent_boundary_matching_v1"


@pytest.mark.parametrize("energy,height,width", [(3.7, 9.2, .137), (6.1, 11.3, .213),
                                                 (8.4, 7.2, .173)])
def test_nonpreset_parameters(energy: float, height: float, width: float) -> None:
    result = ScientificToolbox().verify(RectangularBarrierRequest(
        particle_mass_kg=9.1093837015e-31,
        energy_eV=energy, barrier_height_eV=height, barrier_width_m=width * 1e-9,
    ))
    assert result.status.value == "pass"
    assert float(result.metrics["reference_error"]) < 1e-12
    assert result.visualization is not None


def test_opaque_range_is_not_fabricated_zero() -> None:
    result = ScientificToolbox().verify(RectangularBarrierRequest(
        particle_mass_kg=9.1093837015e-31,
        energy_eV=5, barrier_height_eV=10, barrier_width_m=1e-4,
    ))
    assert result.status.value == "inconclusive"
    assert result.visualization is None
    assert "T" not in result.metrics


def test_conserving_but_wrong_formula_cannot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    # A mutated analytic path must fail despite apparently valid T/R bounds.
    monkeypatch.setattr("quantum_agent.science.toolbox.math.sinh", lambda value: 0.5)
    result = ScientificToolbox().verify(RectangularBarrierRequest(
        particle_mass_kg=9.1093837015e-31,
        energy_eV=5, barrier_height_eV=10, barrier_width_m=1e-10,
    ))
    assert result.status.value == "fail"
    assert float(result.metrics["reference_error"]) > .1


@pytest.mark.parametrize("updates", [
    {"barrier_width_m": -1e-10}, {"energy_eV": float("nan")},
    {"energy_eV": 10}, {"energy_eV": 10 + 1e-10},
])
def test_invalid_or_degenerate_contract_is_rejected(updates: dict[str, float]) -> None:
    from pydantic import ValidationError

    values = dict(energy_eV=5, barrier_height_eV=10, barrier_width_m=1e-10,
                  particle_mass_kg=9.1093837015e-31)
    with pytest.raises(ValidationError):
        RectangularBarrierRequest(**(values | updates))


def test_generated_code_cannot_import_reference() -> None:
    from quantum_agent.coding.safety import validate_code_safety

    result = validate_code_safety(
        "from quantum_agent.science.barrier_reference import boundary_probabilities\n"
    )
    assert not result.ok
