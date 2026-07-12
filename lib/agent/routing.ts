import { END } from "@langchain/langgraph";
import { TutorStateSchema, type TutorState } from "./state";

export function routeAfterAuthenticate(state: TutorState): "loadCourse" | "refuseRequest" | typeof END {
  if (!state.authenticated) return "refuseRequest";
  return "loadCourse";
}

export function routeAfterDiagnose(state: TutorState): "applyPolicy" | "escalateToTeacher" | typeof END {
  if (state.escalationReason) return "escalateToTeacher";
  return "applyPolicy";
}

export function routeAfterPolicy(state: TutorState): "retrieveEvidence" | "refuseOutOfScope" | typeof END {
  if (state.selectedAction === "REFUSE_OUT_OF_SCOPE") return "refuseOutOfScope";
  return "retrieveEvidence";
}

export function routeAfterRetrieval(state: TutorState): "runTools" | "generateDraft" | "escalateToTeacher" | typeof END {
  if (state.escalationReason) return "escalateToTeacher";
  if (state.selectedAction && ["RUN_RETRIEVAL", "RUN_SYMBOLIC_VERIFIER", "RUN_NUMERIC_VERIFIER", "RUN_SIMULATION", "REVIEW_CODE_LOCALLY"].includes(state.selectedAction)) return "runTools";
  return "generateDraft";
}

export function routeAfterTools(state: TutorState): "verifyScientific" | "generateDraft" | typeof END {
  if (state.verifierResults && state.verifierResults.length > 0) return "verifyScientific";
  return "generateDraft";
}

export function routeAfterDraft(state: TutorState): "enforceCitations" | "applyFallback" | typeof END {
  if (state.fallbackApplied) return "applyFallback";
  return "enforceCitations";
}

export function routeAfterEnforce(state: TutorState): "assessRisk" | "applyFallback" | typeof END {
  if (state.fallbackApplied) return "applyFallback";
  return "assessRisk";
}

export function routeAfterRisk(state: TutorState): "interruptForReview" | "persistAndFinish" | typeof END {
  if (state.needsTeacherReview || state.riskLevel === "high") return "interruptForReview";
  return "persistAndFinish";
}