import { defineConfig, devices } from "@playwright/test";

const dry = process.env.BARRIER_RECORDING_DRY_RUN === "1";
if (!dry && process.env.BARRIER_REAL_RUN_AUTHORIZED !== "1") {
  throw new Error("真实录制尚未授权；本轮仅可设置 BARRIER_RECORDING_DRY_RUN=1。");
}
const runId = process.env.QUANTUM_AGENT_RECORDING_RUN_ID;
if (!runId || !/^[0-9a-f-]{36}$/i.test(runId)) {
  throw new Error("必须提供本轮唯一 UUID: QUANTUM_AGENT_RECORDING_RUN_ID");
}
export default defineConfig({
  testDir: dry ? "./defense/barrier-patch" : "./tests/e2e/live",
  testMatch: dry ? "recording-pipeline.spec.ts" : "golden-loop-deterministic.spec.ts",
  outputDir: `./defense/barrier-patch/recordings/${dry ? "DRY" : "REAL"}-${runId}`,
  timeout: dry ? 30_000 : 600_000,
  globalTimeout: dry ? 60_000 : 660_000,
  retries: 0,
  workers: 1,
  fullyParallel: false,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: dry ? undefined : (process.env.BASE_URL ?? "http://127.0.0.1:3000"),
    offline: dry,
    video: "on",
    screenshot: "on",
    trace: "off",
  },
});
