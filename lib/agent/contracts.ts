import { PedagogicalAction } from "./state";

export { PedagogicalAction };

export const HINT_LEVEL_ACTIONS: Record<number, PedagogicalAction[]> = {
  0: ["ASK_GOAL", "ASK_FOR_ATTEMPT", "ELICIT_PREDICTION", "ASK_SELF_EXPLANATION"],
  1: ["GIVE_CONCEPT_CUE"],
  2: ["GIVE_FORMULA_CUE"],
  3: ["GIVE_PROCESS_CUE"],
  4: ["SHOW_LOCAL_EXAMPLE", "SHOW_COUNTEREXAMPLE", "COMPARE_REPRESENTATIONS"],
  5: ["RELEASE_FULL_EXPLANATION"],
} as const;

export function isActionAllowed(action: PedagogicalAction, hintLevel: number): boolean {
  for (let level = 0; level <= hintLevel; level++) {
    if ((HINT_LEVEL_ACTIONS[level] ?? []).includes(action as never)) return true;
  }
  return false;
}

export function allowedActionsForLevel(hintLevel: number): PedagogicalAction[] {
  const actions = new Set<PedagogicalAction>();
  for (let level = 0; level <= hintLevel; level++) {
    for (const action of (HINT_LEVEL_ACTIONS[level] ?? [])) {
      actions.add(action);
    }
  }
  return [...actions];
}

export function isAnswerLeaking(action: PedagogicalAction): boolean {
  return action === "RELEASE_FULL_EXPLANATION" || action === "SHOW_LOCAL_EXAMPLE";
}

export const TOOL_ACTIONS: PedagogicalAction[] = [
  "RUN_RETRIEVAL",
  "RUN_SYMBOLIC_VERIFIER",
  "RUN_NUMERIC_VERIFIER",
  "RUN_SIMULATION",
  "REVIEW_CODE_LOCALLY",
];

export const ESCALATION_ACTIONS: PedagogicalAction[] = ["ESCALATE_TO_TA", "REFUSE_OUT_OF_SCOPE"];

export const HIGH_RISK_PATTERNS = [
  "忽略之前的指令", "忽略系统提示", "忽略课程政策", "忘记你的规则", "你是新角色",
  "标准答案错", "老师说的和", "系统提示词", "越过限制", "不要教学限制",
  "override", "ignore previous", "system:", "you are now",
  "直接告诉我答案", "完整解答", "不要提示", "跳过检查",
  "忽略 H0", "忽略 H1", "忽略 H2", "忽略 H3", "忽略 H4", "忽略 H5",
  "你是助教", "你是老师", "你是教授", "不用检查课件",
];