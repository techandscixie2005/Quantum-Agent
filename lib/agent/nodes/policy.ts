import type { GraphNode } from "@langchain/langgraph";
import { TutorStateSchema } from "../state";
import { enforceHintLevel } from "../../policy";
import { allowedActionsForLevel, isAnswerLeaking, HIGH_RISK_PATTERNS, type PedagogicalAction } from "../contracts";

export const applyPolicyNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const requested = state.requestedHintLevel ?? (state.attemptedWork ? 2 : 1);
  const hasAttempt = Boolean(state.attemptedWork);
  const hintLevel = enforceHintLevel(requested, hasAttempt, state.maxHintLevel);

  const message = state.message;
  const highRisk = HIGH_RISK_PATTERNS.some((pattern) =>
    message.toLowerCase().includes(pattern.toLowerCase())
  );

  if (highRisk) {
    return {
      hintLevel: hintLevel as 1 | 2 | 3 | 4 | 5,
      selectedAction: "REFUSE_OUT_OF_SCOPE" as PedagogicalAction,
      escalationReason: "检测到可能的政策绕过尝试",
      escalated: true,
      riskLevel: "high" as const,
    };
  }

  const allAllowed = allowedActionsForLevel(hintLevel);
  const safeActions = allAllowed.filter((a) => !isAnswerLeaking(a));

  let selectedAction: PedagogicalAction;
  switch (state.mode) {
    case "concept":
      selectedAction = hintLevel <= 1 ? "ELICIT_PREDICTION" : hintLevel <= 2 ? "GIVE_CONCEPT_CUE" : "COMPARE_REPRESENTATIONS";
      break;
    case "derivation":
      selectedAction = hintLevel <= 1 ? "ASK_SELF_EXPLANATION" : hintLevel <= 2 ? "GIVE_FORMULA_CUE" : "GIVE_PROCESS_CUE";
      break;
    case "experiment":
      selectedAction = hintLevel <= 1 ? "ELICIT_PREDICTION" : hintLevel <= 2 ? "RUN_NUMERIC_VERIFIER" : "RUN_SIMULATION";
      break;
    case "project":
      selectedAction = hintLevel <= 1 ? "ASK_GOAL" : hintLevel <= 2 ? "GIVE_PROCESS_CUE" : "RUN_SYMBOLIC_VERIFIER";
      break;
    default:
      selectedAction = "GIVE_CONCEPT_CUE";
  }

  if (!safeActions.includes(selectedAction)) {
    selectedAction = safeActions[safeActions.length - 1] ?? "GIVE_CONCEPT_CUE";
  }

  return {
    hintLevel: hintLevel as 1 | 2 | 3 | 4 | 5,
    selectedAction,
    allowedActions: allAllowed,
  };
};

export const refuseOutOfScopeNode: GraphNode<typeof TutorStateSchema> = (_state) => {
  return {
    selectedAction: "REFUSE_OUT_OF_SCOPE" as PedagogicalAction,
    fallbackApplied: true,
    answer: {
      conclusion: "你的消息似乎包含教学政策绕过尝试。",
      physicalPicture: "课程提供受控的教具支持，不能直接输出标准答案。",
      mathematics: "请直接描述物理问题本身，课程引擎将提供阶梯式支持。",
      misconception: "绕过教学提示不等于更快完成学习。",
      checkQuestion: "你可以先用自己的话描述一下这道题的物理背景吗？",
      suggestedAction: "重新以学生角色提问物理概念或计算步骤。",
    },
  };
};