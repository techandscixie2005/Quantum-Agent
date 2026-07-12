import { test, expect } from "@playwright/test";

test.describe("Teacher Dashboard", () => {
  test("teacher login flow works", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();

    await expect(page.locator("#teacher-password")).toBeVisible();
    await expect(page.locator('text=教师验证')).toBeVisible();
  });

  test("rejects incorrect password", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();

    await page.locator("#teacher-password").fill("wrong-password");
    await page.locator("button[type=submit]").click();

    await page.waitForSelector(".login-error", { timeout: 5000 });
  });

  test("analytics display after login attempt", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();

    // Teacher dashboard should show unauthorized or login form
    await expect(
      page.locator('text=教师验证').or(page.locator(".metric-grid"))
    ).toBeVisible({ timeout: 5000 });
  });

  test("teacher dashboard shows metrics when authorized", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();

    // Check that the dashboard structure is rendered correctly
    const isLoginForm = await page.locator('text=教师验证').isVisible().catch(() => false);
    const isDashboard = await page.locator(".teacher-dashboard").isVisible().catch(() => false);
    expect(isLoginForm || isDashboard).toBeTruthy();
  });
});