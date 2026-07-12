import { StateGraph, START, END } from "@langchain/langgraph";
import { ConceptSubgraphSchema, DerivationSubgraphSchema, VisionSubgraphSchema, CodeSubgraphSchema, ExperimentSubgraphSchema, ProjectSubgraphSchema } from "./schemas";
import type { GraphNode, ConditionalEdgeRouter } from "@langchain/langgraph";

// ── Concept clarification subgraph ──
const conceptStep1: GraphNode<typeof ConceptSubgraphSchema> = (state) => {
  return {
    contextProvided: true,
    clarificationLevel: Math.min(state.clarificationLevel + 1, 5) as 1 | 2 | 3 | 4 | 5,
  };
};

const conceptBuilder = new StateGraph(ConceptSubgraphSchema)
  .addNode("assessConcept", conceptStep1)
  .addEdge(START, "assessConcept")
  .addEdge("assessConcept", END);

export const conceptSubgraph = conceptBuilder.compile({ name: "concept-clarification" });

// ── Derivation review subgraph ──
const derivationReview: GraphNode<typeof DerivationSubgraphSchema> = (state) => {
  const steps = state.derivationSteps ?? [];
  return {
    firstErrorIndex: undefined,
    errorType: undefined,
  };
};

const derivationBuilder = new StateGraph(DerivationSubgraphSchema)
  .addNode("reviewDerivation", derivationReview)
  .addEdge(START, "reviewDerivation")
  .addEdge("reviewDerivation", END);

export const derivationSubgraph = derivationBuilder.compile({ name: "derivation-review" });

// ── Vision subgraph ──
const visionAnalyze: GraphNode<typeof VisionSubgraphSchema> = (state) => {
  return { needsManualReview: true };
};

const visionBuilder = new StateGraph(VisionSubgraphSchema)
  .addNode("analyzeImage", visionAnalyze)
  .addEdge(START, "analyzeImage")
  .addEdge("analyzeImage", END);

export const visionSubgraph = visionBuilder.compile({ name: "vision-interpretation" });

// ── Code subgraph ──
const codeAnalyze: GraphNode<typeof CodeSubgraphSchema> = (state) => {
  return { executionStatus: "not_run" as const };
};

const codeBuilder = new StateGraph(CodeSubgraphSchema)
  .addNode("analyzeCode", codeAnalyze)
  .addEdge(START, "analyzeCode")
  .addEdge("analyzeCode", END);

export const codeSubgraph = codeBuilder.compile({ name: "code-assistance" });

// ── Experiment subgraph ──
const experimentRun: GraphNode<typeof ExperimentSubgraphSchema> = (state) => {
  return {
    simulationStatus: "not_run" as const,
  };
};

const experimentBuilder = new StateGraph(ExperimentSubgraphSchema)
  .addNode("setupExperiment", experimentRun)
  .addEdge(START, "setupExperiment")
  .addEdge("setupExperiment", END);

export const experimentSubgraph = experimentBuilder.compile({ name: "numerical-experiment" });

// ── Project coaching subgraph ──
const projectCoach: GraphNode<typeof ProjectSubgraphSchema> = (state) => {
  return { milestoneStatus: "in_progress" as const };
};

const projectBuilder = new StateGraph(ProjectSubgraphSchema)
  .addNode("coachMilestone", projectCoach)
  .addEdge(START, "coachMilestone")
  .addEdge("coachMilestone", END);

export const projectSubgraph = projectBuilder.compile({ name: "project-coaching" });