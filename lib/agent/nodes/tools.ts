import type { GraphNode } from "@langchain/langgraph";
import { TutorStateSchema } from "../state";
import { runVerifier } from "../../verifiers";

export const runToolsNode: GraphNode<typeof TutorStateSchema> = (state) => {
  const action = state.selectedAction;
  const verifierResults: Array<{
    id: string;
    status: "passed" | "failed" | "inconclusive";
    summary: string;
    details: Record<string, unknown>;
    tolerance?: number;
  }> = [];

  switch (action) {
    case "RUN_SYMBOLIC_VERIFIER": {
      if (state.mode === "derivation") {
        const hermResult = runVerifier("hermiticity", { matrix: [[1, 0], [0, 1]], tolerance: 1e-9 });
        verifierResults.push({
          id: "hermiticity",
          status: hermResult.status,
          summary: hermResult.summary,
          details: hermResult.details as Record<string, unknown>,
          tolerance: hermResult.tolerance,
        });
      }
      break;
    }
    case "RUN_NUMERIC_VERIFIER": {
      const consResult = runVerifier("probability_conservation", {
        probabilities: [1, 0.99998, 1.00001, 0.99997, 1.00002],
        tolerance: 0.001,
      });
      verifierResults.push({
        id: "probability_conservation",
        status: consResult.status,
        summary: consResult.summary,
        details: consResult.details as Record<string, unknown>,
        tolerance: consResult.tolerance,
      });
      break;
    }
    case "RUN_SIMULATION": {
      const cons = runVerifier("probability_conservation", {
        probabilities: [1, 1.0001, 0.9999, 1.0002, 0.9998],
        tolerance: 0.001,
      });
      verifierResults.push({
        id: "probability_conservation",
        status: cons.status,
        summary: cons.summary,
        details: cons.details as Record<string, unknown>,
        tolerance: cons.tolerance,
      });
      break;
    }
    default:
      break;
  }

  return { verifierResults };
};