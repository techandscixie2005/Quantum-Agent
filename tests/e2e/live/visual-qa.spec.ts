import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { mkdirSync, writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

/**
 * Visual QA for the /agent workspace at desktop and mobile resolutions.
 * Captures screenshots and checks for horizontal overflow + console errors.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type LiveAuth = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  student_token: string;
  ta_token: string;
}>;

function liveAuth(): LiveAuth {
  const configured = process.env.QA_E2E_AUTH_FILE?.trim();
  if (!configured) throw new Error("QA_E2E_AUTH_FILE is required for visual QA");
  const path = resolve(configured);
  if ((statSync(path).mode & 0o077) !== 0) {
    throw new Error("The live E2E credential file must not be readable by group or others");
  }
  const value: unknown = JSON.parse(readFileSync(path, "utf8"));
  const input = value as Record<string, unknown>;
  return input as LiveAuth;
}

async function installStudentSession(page: Page, auth: LiveAuth): Promise<void> {
  const origin = process.env.BASE_URL ?? "http://127.0.0.1:3000";
  await page.context().addCookies([
    { name: "qa_session", value: auth.student_token, url: origin, httpOnly: true, sameSite: "Lax" },
  ]);
}

const SCREENSHOTS_DIR = "test-results/visual-qa";
mkdirSync(SCREENSHOTS_DIR, { recursive: true });

test.describe("Visual QA · /agent workspace", () => {
  test("desktop 1440×900 — no overflow, no severe console errors", async ({ page }) => {
    const auth = liveAuth();
    await installStudentSession(page, auth);
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/agent", { waitUntil: "domcontentloaded" });
    await page.getByTestId("agent-experience").waitFor({ timeout: 30_000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/desktop-1440x900.png`, fullPage: false });

    // Check horizontal overflow
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth - document.documentElement.clientWidth;
    });
    expect(overflow, "desktop should have no horizontal overflow").toBeLessThanOrEqual(0);

    // Surface console errors (filter out benign network/favicon errors)
    const severeErrors = errors.filter(
      (e) => !e.includes("favicon") && !e.includes("Failed to load resource"),
    );
    expect(severeErrors, `desktop console errors: ${severeErrors.join("; ")}`).toEqual([]);
  });

  test("mobile 390×844 — no overflow, panels responsive", async ({ page }) => {
    const auth = liveAuth();
    await installStudentSession(page, auth);
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/agent", { waitUntil: "domcontentloaded" });
    await page.getByTestId("agent-experience").waitFor({ timeout: 30_000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/mobile-390x844.png`, fullPage: false });

    // Check horizontal overflow
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth - document.documentElement.clientWidth;
    });
    expect(overflow, "mobile should have no horizontal overflow").toBeLessThanOrEqual(0);

    // Verify the mobile panel toggle buttons are present
    await expect(
      page.getByRole("button", { name: /打开课程导航|打开证据面板/ }).first(),
    ).toBeVisible();

    const severeErrors = errors.filter(
      (e) => !e.includes("favicon") && !e.includes("Failed to load resource"),
    );
    expect(severeErrors, `mobile console errors: ${severeErrors.join("; ")}`).toEqual([]);
  });
});
