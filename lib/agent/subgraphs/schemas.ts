import { StateSchema } from "@langchain/langgraph";
import { z } from "zod/v4";

/**
 * Subgraph: Concept clarification
 * Handles concept-mode questions with misconceptions diagnosis
 */
export const ConceptSubgraphSchema = new StateSchema({
  conceptId: z.string().optional(),
  clarificationLevel: z.number().min(1).max(5).default(1),
  physicalPicture: z.string().optional(),
  mathematicalExpression: z.string().optional(),
  comparisonExample: z.string().optional(),
  contextProvided: z.boolean().default(false),
});
export type ConceptSubgraphState = typeof ConceptSubgraphSchema.State;

/**
 * Subgraph: Derivation review
 * Step-by-step derivation checking with error localization
 */
export const DerivationSubgraphSchema = new StateSchema({
  derivationSteps: z.array(z.string()).default(() => []),
  firstErrorIndex: z.number().optional(),
  errorType: z.enum(["algebra", "sign", "substitution", "boundary", "conceptual"]).optional(),
  correctedStep: z.string().optional(),
  hintLevel: z.number().min(1).max(5).default(2),
});
export type DerivationSubgraphState = typeof DerivationSubgraphSchema.State;

/**
 * Subgraph: Image/handwriting interpretation
 */
export const VisionSubgraphSchema = new StateSchema({
  imageDescription: z.string().optional(),
  transcribedFormula: z.string().optional(),
  identifiedConcepts: z.array(z.string()).default(() => []),
  confidence: z.number().min(0).max(1).default(0),
  needsManualReview: z.boolean().default(false),
});
export type VisionSubgraphState = typeof VisionSubgraphSchema.State;

/**
 * Subgraph: Code assistance
 * Static analysis, code review, sandbox execution adapter
 */
export const CodeSubgraphSchema = new StateSchema({
  code: z.string().optional(),
  language: z.string().default("python"),
  staticAnalysisResult: z.string().optional(),
  executionResult: z.string().optional(),
  executionStatus: z.enum(["not_run", "passed", "failed", "rejected", "unavailable"]).default("not_run"),
  suggestedFix: z.string().optional(),
});
export type CodeSubgraphState = typeof CodeSubgraphSchema.State;

/**
 * Subgraph: Numerical experiment
 * Parameter setup, simulation run, result validation
 */
export const ExperimentSubgraphSchema = new StateSchema({
  parameters: z.record(z.string(), z.number()).default(() => ({})),
  simulationStatus: z.enum(["not_run", "running", "completed", "failed"]).default("not_run"),
  convergenceCheck: z.enum(["not_applicable", "passed", "failed", "inconclusive"]).default("not_applicable"),
  conservationCheck: z.enum(["not_applicable", "passed", "failed", "inconclusive"]).default("not_applicable"),
  resultData: z.string().optional(),
});
export type ExperimentSubgraphState = typeof ExperimentSubgraphSchema.State;

/**
 * Subgraph: Project coaching
 * Milestone tracking, validator checking, next-step guidance
 */
export const ProjectSubgraphSchema = new StateSchema({
  projectId: z.string(),
  currentMilestone: z.number().min(1).default(1),
  milestoneStatus: z.enum(["not_started", "in_progress", "completed", "blocked"]).default("not_started"),
  validatorsPassed: z.array(z.string()).default(() => []),
  validatorsFailed: z.array(z.string()).default(() => []),
  nextAction: z.string().optional(),
});
export type ProjectSubgraphState = typeof ProjectSubgraphSchema.State;