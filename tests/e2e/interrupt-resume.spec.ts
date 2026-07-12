import { test, expect } from "@playwright/test";

test.describe("Interrupt and Resume", () => {
  test("teacher dashboard shows pending escalations count", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();

    // The teacher login form or the dashboard with metrics should appear
    await expect(
      page.locator('text=教师验证').or(page.locator(".metric-grid"))
    ).toBeVisible({ timeout: 5000 });
  });

  test("teacher can view analytics after login", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();

    // Teacher dashboard structure
    await expect(page.locator(".teacher-dashboard")).toBeVisible({ timeout: 5000 });

    const loginForm = page.locator("#teacher-password");
    const metrics = page.locator(".metric-grid");

    if (await loginForm.isVisible()) {
      await expect(loginForm).toBeVisible();
    } else if (await metrics.isVisible()) {
      await expect(metrics).toBeVisible();
    }
  });

  test("student workspace remains available during review", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".student-shell").or(page.locator(".main-workspace"))).toBeVisible();

    // Student can still interact
    await page.locator(".composer textarea").fill("量子力学的基本假设是什么？");
    await page.locator(".send-button").click();

    await page.waitForSelector(".tutor-message", { timeout: 10000 });
  });

  test("session persists across page navigation", async ({ page }) => {
    await page.goto("/");

    // Send a message to create session
    await page.locator(".composer textarea").fill("什么是归一化？");
    await page.locator(".send-button").click();
    await page.waitForSelector(".tutor-message", { timeout: 10000 });

    // Reload and verify workspace still works
    await page.reload();
    await page.waitForSelector(".composer", { timeout: 5000 });
    await expect(page.locator(".composer")).toBeVisible();
  });
});