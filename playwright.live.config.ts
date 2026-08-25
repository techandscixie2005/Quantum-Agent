import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e/live",
  timeout: 600_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:3000",
    trace: "off",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium-live",
      use: { ...devices["Desktop Chrome"], channel: "chromium" },
    },
  ],
});
