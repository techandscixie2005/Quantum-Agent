import { StateGraph, MemorySaver, START, END } from "@langchain/langgraph";
import { TutorStateSchema } from "./state";

import { authenticateNode, loadCourseNode, classifyTaskNode, diagnoseNode } from "./nodes/preprocessing";
import { applyPolicyNode, refuseOutOfScopeNode } from "./nodes/policy";
import { retrieveEvidenceNode } from "./nodes/retrieval";
import { runToolsNode } from "./nodes/tools";
import { generateDraftNode } from "./nodes/generation";
import { enforceCitationsNode, verifyScientificNode, assessRiskNode } from "./nodes/verification";
import { escalateToTeacherNode, interruptForReviewNode, applyFallbackNode } from "./nodes/escalation";
import { assembleResponseNode } from "./nodes/output";

import {
  routeAfterAuthenticate,
  routeAfterDiagnose,
  routeAfterPolicy,
  routeAfterDraft,
  routeAfterEnforce,
  routeAfterRisk,
} from "./routing";

// ── Build the parent tutor graph ──
const builder = new StateGraph(TutorStateSchema)
  .addNode("authenticate", authenticateNode)
  .addNode("refuseRequest", (_state) => ({
    authenticated: false,
    fallbackApplied: true,
    error: "未认证的请求被拒绝",
    answer: {
      conclusion: "需要有效的身份才能使用教学服务。",
      physicalPicture: "教学代理需要确认你的身份才能记录学习轨迹。",
      mathematics: "",
      misconception: "",
      checkQuestion: "",
      suggestedAction: "请通过认证流程访问。",
    },
    escalated: true,
  }))
  .addNode("loadCourse", loadCourseNode)
  .addNode("classifyTask", classifyTaskNode)
  .addNode("diagnose", diagnoseNode)
  .addNode("applyPolicy", applyPolicyNode)
  .addNode("refuseOutOfScope", refuseOutOfScopeNode)
  .addNode("retrieveEvidence", retrieveEvidenceNode)
  .addNode("runTools", runToolsNode)
  .addNode("verifyScientific", verifyScientificNode)
  .addNode("generateDraft", generateDraftNode)
  .addNode("enforceCitations", enforceCitationsNode)
  .addNode("assessRisk", assessRiskNode)
  .addNode("interruptForReview", interruptForReviewNode)
  .addNode("applyFallback", applyFallbackNode)
  .addNode("escalateToTeacher", escalateToTeacherNode)
  .addNode("assembleResponse", assembleResponseNode)
  .addNode("persistAndFinish", assembleResponseNode)

  // Edges
  .addEdge(START, "authenticate")
  .addConditionalEdges("authenticate", routeAfterAuthenticate)
  .addEdge("refuseRequest", "assembleResponse")
  .addEdge("refuseOutOfScope", "assembleResponse")
  .addEdge("escalateToTeacher", "assembleResponse")
  .addEdge("applyFallback", "assembleResponse")
  .addEdge("loadCourse", "classifyTask")
  .addEdge("classifyTask", "diagnose")
  .addConditionalEdges("diagnose", routeAfterDiagnose)
  .addConditionalEdges("applyPolicy", routeAfterPolicy)
  .addEdge("retrieveEvidence", "generateDraft")
  .addConditionalEdges("generateDraft", routeAfterDraft)
  .addEdge("runTools", "verifyScientific")
  .addEdge("verifyScientific", "enforceCitations")
  .addConditionalEdges("enforceCitations", routeAfterEnforce)
  .addConditionalEdges("assessRisk", routeAfterRisk)
  .addEdge("interruptForReview", "assembleResponse")
  .addEdge("assembleResponse", END)
  .addEdge("persistAndFinish", END);

const checkpointer = new MemorySaver();

export const tutorGraph = builder.compile({
  checkpointer,
  name: "quantum-agent-tutor",
});

export { builder as tutorGraphBuilder };