import { defineConfig, devices } from "@playwright/test";

const external = process.env.BACKEND_LIVE_WEB_URL;
export default defineConfig({
  testDir: "./tests/e2e/backend-live",
  testMatch: "**/*.spec.ts",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "test-results/backend-live/results.json" }]],
  outputDir: "test-results/backend-live/browser",
  use: { baseURL: external ?? `http://localhost:${process.env.BACKEND_LIVE_WEB_PORT ?? "3310"}`,
    trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "real-backend-chromium", use: { ...devices["Desktop Chrome"], channel: "chromium" } }],
  webServer: external ? undefined : {
    command: "node tests/e2e/backend-live/stack.mjs",
    url: `http://localhost:${process.env.BACKEND_LIVE_WEB_PORT ?? "3310"}/agent`,
    timeout: 180_000,
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
  },
});
