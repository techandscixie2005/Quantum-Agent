import type { GraphNode } from "@langchain/langgraph";
import { interrupt } from "@langchain/langgraph";
import { TutorStateSchema } from "../state";

export const escalateToTeacherNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const newEvidence = [
    ...(state.evidence ?? []),
    ...(state.citations ?? []).slice(0, 2).map((c) => ({
      type: "course" as const,
      label: `${c.chapter} · ${c.pages}页`,
      status: "passed" as const,
      detail: c.excerpt,
    })),
    {
      type: "teacher" as const,
      label: "教学升级",
      status: "passed" as const,
      detail: `原因：${state.escalationReason ?? "需要人工介入"}`,
    },
  ];

  return {
    escalated: true,
    needsTeacherReview: true,
    riskLevel: "high" as const,
    evidence: newEvidence,
    answer: state.answer ?? {
      conclusion: "当前问题需要教师或助教介入。",
      physicalPicture: "课程引擎已记录完整轨迹，教师将收到通知。",
      mathematics: "请等待教师查看，无需重复提交。",
      misconception: state.misconceptionLabel ?? "不确定",
      checkQuestion: "教师将在审查后提供进一步指导。",
      suggestedAction: "你可以继续其他知识点或等待回复。",
    },
  };
};

export const interruptForReviewNode: GraphNode<typeof TutorStateSchema> = (_state) => {
  const _approved = interrupt({
    type: "teacher_review",
    sessionId: _state.sessionId,
    reason: _state.escalationReason ?? "高风险响应需要教师确认",
    riskLevel: _state.riskLevel,
    confidence: _state.confidence,
  });

  return {
    needsTeacherReview: false,
  };
};

export const applyFallbackNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const answer = {
    conclusion: "Quantum Agent 已安全回退：当前请求无法由课程模型完成。",
    physicalPicture: "回退不伪造任何物理图像或工具输出。",
    mathematics: (state.citations ?? [])[0]
      ? `证据定位：${(state.citations ?? [])[0].title}，${(state.citations ?? [])[0].pages}页`
      : "暂无可核验的课件证据。",
    misconception: state.misconceptionLabel ?? "需要确认理解障碍。",
    checkQuestion: "请用一句话描述你正在解决的具体问题。",
    suggestedAction: "重新以学生角色提问，或联系助教。",
  };

  return {
    answer,
    fallbackApplied: true,
    modelSource: "deterministic-fallback" as const,
    escalated: true,
    needsTeacherReview: true,
  };
};