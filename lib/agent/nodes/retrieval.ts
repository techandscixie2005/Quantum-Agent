import type { GraphNode } from "@langchain/langgraph";
import { TutorStateSchema } from "../state";
import { retrieveKnowledge } from "../../retrieval";
import { buildCitationAllowlist } from "../../citation-allowlist";
import { seedKnowledge } from "../../course-knowledge";

export const retrieveEvidenceNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const citations = retrieveKnowledge(state.message, [...seedKnowledge]);
  const allowlist = buildCitationAllowlist(citations);

  if (citations.length === 0) {
    return {
      citations,
      citationAllowlist: [...allowlist],
      retrievedCount: 0,
      escalationReason: "未能在课件中找到相关课程证据",
    };
  }

  return {
    citations,
    citationAllowlist: [...allowlist],
    retrievedCount: citations.length,
  };
};