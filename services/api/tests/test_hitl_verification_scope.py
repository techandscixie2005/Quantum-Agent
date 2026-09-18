"""A solver certificate does not certify or refute a student's explanation."""
import pytest

from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import (
    ComplexValue,
    NumericalNormalizationRequest,
    RectangularBarrierRequest,
    ScientificVerificationStatus,
)
from quantum_agent.teaching.hitl import _verifier_disagrees
from quantum_agent.teaching.models import (
    DiagnosisErrorKind,
    DiagnosisOutput,
    DiagnosisStatus,
    FirstErrorLocalization,
)


def diagnosis(*, error: bool) -> DiagnosisOutput:
    return DiagnosisOutput(
        status=DiagnosisStatus.MODEL_INFERENCE,
        summary="Student predicts zero transmission" if error else "No clear error",
        observation_basis=["student_attempt"],
        verification_needed=True,
        first_error=FirstErrorLocalization(
            kind=(DiagnosisErrorKind.PHYSICAL_INTERPRETATION_ERROR if error
                  else DiagnosisErrorKind.NO_CLEAR_ERROR),
        ),
    )


@pytest.mark.parametrize("error", [True, False])
@pytest.mark.parametrize("status", list(ScientificVerificationStatus))
def test_reference_solver_does_not_judge_student(error: bool,
                                                status: ScientificVerificationStatus) -> None:
    result = ScientificToolbox().verify(RectangularBarrierRequest(
        particle_mass_kg=9.1093837015e-31,
        energy_eV=5, barrier_height_eV=10, barrier_width_m=1e-10,
    ))
    assert result.status is ScientificVerificationStatus.PASS
    # Include failed/inconclusive solver runs: neither judges student prose.
    result = result.model_copy(update={"status": status})
    assert not _verifier_disagrees(diagnosis(error=error), [result])


@pytest.mark.parametrize("error,should_pause", [(True, True), (False, False)])
def test_actual_assertion_disagreement_still_pauses(error: bool, should_pause: bool) -> None:
    result = ScientificToolbox().verify(NumericalNormalizationRequest(
        state=[ComplexValue(real=1)],
    ))
    assert result.status is ScientificVerificationStatus.PASS
    assert _verifier_disagrees(diagnosis(error=error), [result]) is should_pause
    failed = result.model_copy(update={"status": ScientificVerificationStatus.FAIL})
    assert _verifier_disagrees(diagnosis(error=error), [failed]) is not should_pause
