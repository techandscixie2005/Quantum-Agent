import type { GraphNode } from "@langchain/langgraph";
import { TutorStateSchema } from "../state";
import { enforceCitationAllowlist, detectFabricatedCitations } from "../../citation-allowlist";

export const enforceCitationsNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const allowlistSet = new Set<string>(state.citationAllowlist ?? []);
  const text = state.answer ? JSON.stringify(state.answer) : "";

  const fabricated = detectFabricatedCitations(text, allowlistSet);
  if (fabricated.length > 0) {
    return {
      riskLevel: "high" as const,
      fallbackApplied: false,
    };
  }

  return {
    riskLevel: "low" as const,
  };
};

export const verifyScientificNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const results = state.verifierResults ?? [];
  const allPassed = results.every((r) => r.status === "passed");
  const anyFailed = results.some((r) => r.status === "failed");

  return {
    confidence: allPassed ? 0.95 : anyFailed ? 0.3 : 0.5,
    riskLevel: anyFailed ? ("high" as const) : allPassed ? ("low" as const) : ("medium" as const),
  };
};

export const assessRiskNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const needsReview = state.riskLevel === "high" || state.escalated || (state.confidence ?? 0.5) < 0.4;
  return {
    needsTeacherReview: needsReview,
    confidence: state.confidence ?? 0.5,
  };
};