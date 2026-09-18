import type { CodeArtifactRun } from "../teaching/contracts";

type Step = Readonly<{
  key: string;
  label: string;
  state: "done" | "active" | "pending" | "failed";
}>;

/** Terminal results are not a successful history of every possible agent step. */
export function codingExecutionSteps(run: CodeArtifactRun): readonly Step[] {
  const finished = run.progress === "result";
  const executed = run.execution.completed;
  const verified = run.verification.status === "pass";
  return [
    { key: "running", label: executed ? "Sandbox · 已执行" : finished ? "Sandbox · 未完成" : "Sandbox · 等待执行",
      state: executed ? "done" : finished ? "failed" : run.progress === "running" ? "active" : "pending" },
    { key: "verifying", label: `Verifier · ${run.verification.status.toUpperCase()}`,
      state: verified ? "done" : finished ? "failed" : run.progress === "verifying" ? "active" : "pending" },
    { key: "result", label: verified ? "核验通过" : finished ? "未获得核验通过的产物" : "等待结果",
      state: finished && verified ? "done" : finished ? "failed" : "pending" },
  ];
}
