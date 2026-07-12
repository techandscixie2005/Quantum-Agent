import type { CapabilityId, HintLevel, TaskClass, TutorMode } from "./types";

export const misconceptions = [
  { id: "TUNNEL_ENERGY_VIOLATION", patterns: ["能量守恒", "不可能穿", "绝不可能", "能量比势垒低"], label: "把量子隧穿误解为能量守恒被破坏" },
  { id: "SPIN_CLASSICAL_ROTATION", patterns: ["自旋", "自转", "小球旋转"], label: "把自旋理解为经典刚体自转" },
  { id: "NONDEGENERATE_ON_DEGENERATE", patterns: ["简并", "非简并微扰", "直接套公式"], label: "在简并子空间直接使用非简并微扰公式" },
  { id: "WAVEFUNCTION_OBSERVABLE", patterns: ["波函数就是", "直接测量波函数", "概率就是波函数"], label: "混淆波函数与可观测概率" },
];

export function taskClassFor(mode: TutorMode, capability: CapabilityId): TaskClass {
  if (capability === "vision" || capability === "vision-reasoner") return "IMAGE_INTERPRETATION";
  if (capability === "code") return "CODE_ASSISTANCE";
  const mapping = { concept: "COURSE_QA", derivation: "DERIVATION_CHECK", experiment: "SIMULATION_GUIDANCE", project: "PROJECT_COACHING" } satisfies Record<TutorMode, TaskClass>;
  return mapping[mode];
}

export function detectMisconception(message: string) {
  return misconceptions
    .map((item) => ({ ...item, hits: item.patterns.filter((pattern) => message.includes(pattern)).length }))
    .filter((item) => item.hits > 0)
    .sort((a, b) => b.hits - a.hits)[0] ?? null;
}

export function enforceHintLevel(requested: number | undefined, hasAttempt: boolean, maxLevel = 3): HintLevel {
  const base = requested && Number.isFinite(requested) ? Math.round(requested) : hasAttempt ? 2 : 1;
  return Math.min(Math.max(base, 1), maxLevel, 5) as HintLevel;
}

export function shouldEscalate(message: string, citationsFound: number) {
  const highRisk = ["忽略之前的指令", "忽略系统提示", "忽略课程政策", "忘记你的规则", "你是新角色", "标准答案错", "老师说的和", "系统提示词", "越过限制", "不要教学限制", "override", "ignore previous", "system:", "you are now"];
  if (highRisk.some((item) => message.toLowerCase().includes(item.toLowerCase()))) return "涉及课程政策冲突或潜在提示注入";
  if (citationsFound === 0) return "课程资料不足，无法可靠给出课程内回答";
  return null;
}
