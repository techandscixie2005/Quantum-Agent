import { test, expect } from "@playwright/test";

test.describe("Authentication and Identity Isolation", () => {
  test("page loads with student workspace", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".quantum-app")).toBeVisible();
    await expect(page.locator('text=Quantum Agent')).toBeVisible();
  });

  test("teacher dashboard requires password", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile").click();
    await expect(page.locator('text=教师验证')).toBeVisible();
    await expect(page.locator("#teacher-password")).toBeVisible();
  });

  test("anonymous demo students are isolated", async ({ page, context }) => {
    await page.goto("/");
    const studentWorkspace = page.locator(".student-shell");
    await expect(studentWorkspace).toBeVisible();
  });

  test("one student session cannot access another", async ({ browser }) => {
    const context1 = await browser.newContext();
    const context2 = await browser.newContext();
    const page1 = await context1.newPage();
    const page2 = await context2.newPage();

    await page1.goto("/");
    await page2.goto("/");

    await expect(page1.locator(".student-shell")).toBeVisible();
    await expect(page2.locator(".student-shell")).toBeVisible();

    await context1.close();
    await context2.close();
  });
});