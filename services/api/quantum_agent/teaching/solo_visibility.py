"""Student-facing Solo projection, shared by streams, replay and recovery."""
from copy import deepcopy
from typing import Any

from quantum_agent.teaching.models import (
    DiagnosisOutput,
    DiagnosisStatus,
    LearningPhase,
    TeachingTurnResult,
)


def solo_visible_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    native = snapshot.get("learning_native")
    if not isinstance(native, dict) or native.get("phase") != LearningPhase.SOLO_ACTIVE:
        return snapshot
    visible = deepcopy(snapshot)
    # Only a recorded submitted attempt permits the current reference computation.
    submitted = "transfer_attempted" in native.get("evidence_persisted", [])
    visible["evidence_packet"].update({
        "query": "Solo task", "evidence": [], "graph_nodes": [], "graph_edges": [],
        "coverage": "not_found", "warnings": ["evidence_withheld_by_solo"],
    })
    visible["diagnosis"] = DiagnosisOutput(
        status=DiagnosisStatus.INSUFFICIENT_EVIDENCE,
        summary="Solo 期间不返回辅助诊断。提交后的任务评价见 Solo 反馈。",
    ).model_dump(mode="json")
    visible["response"].update({
        "claims": [], "derivation_bridge": None,
        "orientation": "Solo 独立任务。辅助解答已锁定。",
        "next_question": (visible["response"]["next_question"] if submitted
                          else "请独立提交当前任务的回答。或明确退出 Solo 请求帮助。"),
        "limitations": ["Solo 中不提供辅助解答。提交后才返回允许的任务评价。"],
    })
    visible["code_artifact"] = None
    if not submitted:
        visible["scientific_results"] = []
    visible["learning_native"].update({
        "cognitive_mirror": None, "teach_back": None, "minimal_intervention_prompt": "",
        "commitment": None,
    })
    return visible


def solo_visible_result(result: TeachingTurnResult) -> TeachingTurnResult:
    if (result.learning_native is None
            or result.learning_native.phase is not LearningPhase.SOLO_ACTIVE):
        return result
    return TeachingTurnResult.model_validate(solo_visible_snapshot(result.model_dump(mode="json")))
