import type { GraphNode } from "@langchain/langgraph";
import { TutorStateSchema } from "../state";
import type { Evidence } from "../../types";

export const assembleResponseNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const startedAt = state.startedAt ? new Date(state.startedAt).getTime() : Date.now();
  const completedAt = Date.now();
  const durationMs = completedAt - startedAt;

  const citations = state.citations ?? [];
  const evidence: Evidence[] = [
    ...citations.slice(0, 2).map((c): Evidence => ({
      type: "course",
      label: `${c.chapter} · ${c.pages}页`,
      status: "passed",
      detail: c.excerpt,
    })),
    {
      type: "model",
      label: state.modelSource === "api" ? (state.modelCapability ?? "模型解释") : "确定性教学回退",
      status: state.modelSource === "api" ? "inferred" : "passed",
      detail: state.modelSource === "api"
        ? "语言解释由能力路由生成；课程事实仍以引用为准。"
        : "未调用外部模型；未伪造识图、代码运行或工具结论。",
    },
    ...(state.escalated ? [{
      type: "teacher" as const,
      label: "升级至教师",
      status: "passed" as const,
      detail: state.escalationReason ?? "需要人工审查",
    }] : []),
  ];

  const trace = [
    { node: "TASK_CLASSIFIER", status: "passed" as const, detail: state.taskClass ?? "unknown" },
    { node: "MISCONCEPTION_DIAGNOSER", status: "passed" as const, detail: state.misconceptionLabel ?? "未命中已知误区" },
    { node: "COURSE_RETRIEVAL", status: "passed" as const, detail: `命中 ${citations.length} 个已发布知识块` },
    { node: "CITATION_ALLOWLIST", status: "passed" as const, detail: `允许 ${(state.citationAllowlist ?? []).length} 个引用 ID` },
    { node: "POLICY_GATE", status: "passed" as const, detail: `最终提示等级 H${state.hintLevel}，动作: ${state.selectedAction}` },
    ...(state.escalationReason ? [{ node: "HUMAN_ESCALATION" as const, status: "passed" as const, detail: state.escalationReason }] : []),
    { node: "MODEL_GENERATION", status: "passed" as const, detail: state.modelSource === "api" ? `${state.modelCapability}已完成` : "使用确定性回退" },
    { node: "RESPONSE_ASSEMBLER", status: "passed" as const, detail: `组装 ${evidence.length} 项证据`, durationMs },
  ];

  return {
    evidence: [...(state.evidence ?? []), ...evidence],
    trace: [...(state.trace ?? []), ...trace],
    completedAt: new Date().toISOString(),
  };
};