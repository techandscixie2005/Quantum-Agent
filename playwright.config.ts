import { defineConfig, devices } from "@playwright/test";

const e2ePort = process.env.E2E_PORT ?? "3100";
const configuredBaseUrl = process.env.BASE_URL;
const baseURL = configuredBaseUrl ?? `http://127.0.0.1:${e2ePort}`;
const deterministicModelRoutes = JSON.stringify({
  quick: { provider: "demo", model: "e2e-deterministic" },
  deep: { provider: "demo", model: "e2e-deterministic" },
  vision: { provider: "demo", model: "e2e-deterministic" },
  "vision-reasoner": { provider: "demo", model: "e2e-deterministic" },
  code: { provider: "demo", model: "e2e-deterministic" },
});

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: "**/live/**",
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: "chromium" },
    },
  ],
  webServer: configuredBaseUrl
    ? undefined
    : {
        command: `npm run dev -- --host 127.0.0.1 --port ${e2ePort}`,
        env: {
          MODEL_ROUTES_JSON: deterministicModelRoutes,
          MODEL_TIMEOUT_MS: "3000",
        },
        url: baseURL,
        reuseExistingServer: false,
        timeout: 120000,
      },
});
