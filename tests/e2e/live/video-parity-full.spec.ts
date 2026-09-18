import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { test, expect } from "@playwright/test";

/** Real product driver. Requires existing auth, published course and bounded model budget.
 * No retries, API interception, seeded answers, or automatic budget allocation.
 */
test("fresh video journey persists every required scene in the same episode", async ({ baseURL }) => {
  test.setTimeout(930_000);
  expect(process.env.QA_VIDEO_SESSION_FILE, "Private authorized session is required").toBeTruthy();
  const { stdout } = await promisify(execFile)(process.execPath, ["scripts/video-parity/live.mjs"], {
    env: { ...process.env, BASE_URL: baseURL, QA_VIDEO_FULL_ACCEPTANCE: "1",
      QA_VIDEO_RESUME: "", QA_VIDEO_CORRECT_ONLY: "" },
    timeout: 900_000,
    maxBuffer: 1024 * 1024,
  });
  // The child fails on any missing scene, failed source, lock, oracle or persistence assertion.
  expect(stdout).toContain('"name":"11-solo-answer"');
});
