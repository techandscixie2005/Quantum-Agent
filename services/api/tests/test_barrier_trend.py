"""Real numerical checks and explicitly mocked semantic assessment contracts."""
from typing import Any

import pytest

from quantum_agent.llm.gateway import GatewayError
from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest
from quantum_agent.teaching.barrier_trend import BarrierTrendEvaluation, evaluate_barrier_trend
from quantum_agent.teaching.models import TransferVerificationSpec
from quantum_agent.tutor.nodes import _attempt_verified
from quantum_agent.tutor.state import TutorState


def test_numeric_answer_requires_current_task_and_label() -> None:
    request = RectangularBarrierRequest(
        energy_eV=5, barrier_height_eV=10, barrier_width_m=.25e-9,
        particle_mass_kg=9.1093837015e-31,
    )
    result = ScientificToolbox().verify(request)
    expected = float(result.metrics["T"])
    spec = TransferVerificationSpec(
        scientific_request=request.model_dump(mode="json"), metric_name="T",
        expected_value=expected, absolute_tolerance=1e-8,
    )
    state: TutorState = {"scientific_results": [result]}
    assert _attempt_verified(state, f"T={expected}", spec)
    assert _attempt_verified(state, f"按精确式算得T={expected}, 宽度增加使透射降低。", spec)
    assert not _attempt_verified(state, f"unrelatedT={expected}", spec)
    assert _attempt_verified(state, str(expected), spec)
    assert _attempt_verified(state, f"透射率约为 {expected * 100}%", spec)
    assert not _attempt_verified(state, f"a={expected} nm,T=0", spec)
    assert not _attempt_verified(state, f"T={expected},T=0", spec)
    other = ScientificToolbox().verify(request.model_copy(update={"barrier_width_m": .13e-9}))
    assert not _attempt_verified({"scientific_results": [other]}, f"T={expected}", spec)
    assert not _attempt_verified(state, f"T={expected}", spec.model_copy(
        update={"scientific_request": {}},
    ))


@pytest.mark.parametrize("update", [
    {"trend": "uncertain"}, {"trend": "increases"}, {"mechanism": "missing"},
    {"mechanism": "incorrect"}, {"contradictions": ["声称波函数恒为零"]},
    {"trend_quote": "捏造学生原文"}, {"mechanism_quote": ""},
])
def test_partial_wrong_unknown_and_ungrounded_evaluations_do_not_pass(
    update: dict[str, Any],
) -> None:
    evaluation = BarrierTrendEvaluation(
        trend="decreases", trend_quote="透射率降低", mechanism="evanescent_width_dependence",
        mechanism_quote="衰减距离变长", contradictions=[], rationale="有明确因果关系。",
    )
    answer = "透射率降低,因为衰减距离变长。"
    assert evaluation.accepted(answer)
    assert not evaluation.model_copy(update=update).accepted(answer)


@pytest.mark.asyncio
async def test_unavailable_model_is_inconclusive() -> None:
    assert await evaluate_barrier_trend("不知道", prompt="趋势题", gateway=None) is None

    class FailingGateway:
        async def structured_generate(self, **kwargs: Any) -> Any:
            raise GatewayError("unavailable")

    assert await evaluate_barrier_trend(
        "降低", prompt="趋势题", gateway=FailingGateway(),  # type: ignore[arg-type]
    ) is None
