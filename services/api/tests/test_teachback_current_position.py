from typing import cast
from unittest.mock import AsyncMock

import pytest

from quantum_agent.llm.gateway import GatewayError, ModelGateway
from quantum_agent.teaching.learning_native import TeachBackProposal, propose_teach_back_analysis


def proposal(*, covered: bool = False, missing: bool = False,
             contradiction: bool = False) -> TeachBackProposal:
    return TeachBackProposal.model_validate({
        "covered_relations": [{"relation": "covered", "description": "当前因果解释"}]
        if covered else [],
        "missing_relations": [{"relation": "missing", "description": "仍缺少依据"}]
        if missing else [],
        "contradictions": [{"relation": "contradictory", "description": "当前物理错误"}]
        if contradiction else [],
    })


@pytest.mark.parametrize("current", [proposal(covered=True),
                                    proposal(covered=True, contradiction=True),
                                    proposal(missing=True)])
async def test_complete_wrong_and_unknown_current_positions_do_not_inherit_history(
    current: TeachBackProposal,
) -> None:
    gateway = AsyncMock()
    gateway.structured_generate.return_value = current
    result = await propose_teach_back_analysis(
        reconstruction="current student statement", target_concept_names=[],
        model_gateway=cast(ModelGateway, gateway), initial_reconstruction="old withdrawn statement",
    )
    assert result == current
    gateway.structured_generate.assert_awaited_once()
    assert "old withdrawn statement" not in str(gateway.structured_generate.call_args)


async def test_partial_clarification_requires_contextual_evaluation() -> None:
    gateway = AsyncMock()
    partial, contextual = proposal(covered=True, missing=True), proposal(covered=True)
    gateway.structured_generate.side_effect = [partial, contextual]
    result = await propose_teach_back_analysis(
        reconstruction="valid partial clarification", target_concept_names=[],
        model_gateway=cast(ModelGateway, gateway), initial_reconstruction="prior derivation",
    )
    assert result == contextual
    assert gateway.structured_generate.await_count == 2
    assert "prior derivation" in str(gateway.structured_generate.call_args)


async def test_failed_current_evaluation_cannot_borrow_prior_success() -> None:
    gateway = AsyncMock()
    gateway.structured_generate.side_effect = GatewayError("unavailable")
    result = await propose_teach_back_analysis(
        reconstruction="current student statement", target_concept_names=[],
        model_gateway=cast(ModelGateway, gateway), initial_reconstruction="old complete answer",
    )
    assert result is None
    gateway.structured_generate.assert_awaited_once()
