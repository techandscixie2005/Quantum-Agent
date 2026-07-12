import type { GraphNode } from "@langchain/langgraph";
import { TutorStateSchema, type TutorState } from "../state";
import { detectMisconception, shouldEscalate, taskClassFor } from "../../policy";
import type { TaskClass } from "../../types";

export const authenticateNode: GraphNode<typeof TutorStateSchema> = (_state) => {
  const email = _state.userEmail;
  const isAnonymous = email.startsWith("anonymous@");
  const isDemo = email.endsWith("@quantum-agent.local");
  if (isAnonymous && process.env.NODE_ENV === "production") {
    return { authenticated: false, error: "需要身份验证" };
  }
  return { authenticated: !isAnonymous || isDemo };
};

export const loadCourseNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const mode = state.mode;
  const capability = state.capability;
  const taskClass: TaskClass = taskClassFor(mode, capability);
  return {
    taskClass,
    maxHintLevel: 3,
    startedAt: new Date().toISOString(),
  };
};

export const classifyTaskNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const taskClass = state.taskClass ?? "COURSE_QA";
  return { taskClass };
};

export const diagnoseNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const message = `${state.message} ${state.attemptedWork ?? ""}`;
  const misconception = detectMisconception(message);
  const escalationReason = shouldEscalate(state.message, state.retrievedCount);
  return {
    misconceptionId: misconception?.id ?? undefined,
    misconceptionLabel: misconception?.label ?? undefined,
    misconceptionDetail: misconception?.id ?? undefined,
    escalationReason: escalationReason ?? undefined,
  };
};