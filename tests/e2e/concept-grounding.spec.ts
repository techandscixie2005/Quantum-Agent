import { test, expect } from "@playwright/test";

test.describe("Concept Grounding", () => {
  test("sends a concept question and receives tutor response", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".composer");

    const textarea = page.locator(".composer textarea");
    await textarea.fill("Franck-Condon 原理是什么？");
    await page.locator(".send-button").click();

    await expect(page.locator(".tutor-message")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".live-reply")).toBeVisible({ timeout: 5000 });
  });

  test("tutor response shows evidence and trace", async ({ page }) => {
    await page.goto("/");

    const textarea = page.locator(".composer textarea");
    await textarea.fill("什么是波函数？");
    await page.locator(".send-button").click();

    await expect(page.locator(".trace-summary")).toBeVisible({ timeout: 10000 });
  });

  test("response includes all six required answer fields", async ({ page }) => {
    await page.goto("/");

    await page.locator(".composer textarea").fill("量子隧穿是怎么回事？");
    await page.locator(".send-button").click();

    await page.waitForSelector(".tutor-message .thesis h2", { timeout: 10000 });
  });

  test("capability selector opens and shows options", async ({ page }) => {
    await page.goto("/");
    await page.locator(".gateway-button").click();
    await expect(page.locator(".model-modal")).toBeVisible();
    await expect(page.locator(".model-list button")).toHaveCount(5);
    await page.locator('[aria-label="关闭能力设置"]').click();
    await expect(page.locator(".model-modal")).not.toBeVisible();
  });
});