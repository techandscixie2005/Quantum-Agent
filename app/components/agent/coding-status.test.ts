import assert from "node:assert/strict";
import test from "node:test";
import type { CodeArtifactRun } from "../teaching/contracts";
import { codingExecutionSteps } from "./coding-status";

function run(completed: boolean, status: CodeArtifactRun["verification"]["status"]): CodeArtifactRun {
  return {
    artifact: { language: "python", purpose: "test", code: "print(1)", expected_outputs: [], verification_plan: "" },
    execution: { completed, exit_code: completed ? 0 : null, timed_out: false, truncated: false,
      stdout_bounded: "", stderr_bounded: "", duration_seconds: 0 },
    verification: { status, oracle_kind: null, agent_metrics: {}, oracle_metrics: {}, observations: [], tolerance: 1e-6 },
    progress: "result", repairs: [], figure_png_base64: null,
  };
}

test("a terminal sandbox failure does not light up completed agent steps", () => {
  assert.ok(codingExecutionSteps(run(false, "inconclusive")).every(step => step.state === "failed"));
});

test("successful execution and failed numerical verification stay distinct", () => {
  assert.deepEqual(codingExecutionSteps(run(true, "fail")).map(step => step.state), ["done", "failed", "failed"]);
  assert.deepEqual(codingExecutionSteps(run(true, "no_oracle")).map(step => step.state), ["done", "failed", "failed"]);
  assert.ok(codingExecutionSteps(run(true, "pass")).every(step => step.state === "done"));
});
