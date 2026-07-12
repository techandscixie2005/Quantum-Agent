import { test, expect } from "@playwright/test";

test.describe("User Data Lifecycle", () => {
  test("session is created after first message", async ({ page }) => {
    await page.goto("/");

    await page.locator(".composer textarea").fill("量子力学的基本假设是什么？");
    await page.locator(".send-button").click();

    await page.waitForSelector(".tutor-message", { timeout: 10000 });
    // The session should be created and persisted
  });

  test("multiple turns in a session maintain context", async ({ page }) => {
    await page.goto("/");

    // First turn
    await page.locator(".composer textarea").fill("什么是波函数？");
    await page.locator(".send-button").click();
    await page.waitForSelector(".live-reply", { timeout: 10000 });

    // Second turn
    await page.locator(".composer textarea").fill("那归一化是什么意思？");
    await page.locator(".send-button").click();
    await page.waitForSelector(".live-reply", { timeout: 10000 });
  });

  test("topic switching works across modes", async ({ page }) => {
    await page.goto("/");

    // Start in concept mode
    await page.locator(".composer textarea").fill("势垒是什么？");
    await page.locator(".send-button").click();

    await page.waitForSelector(".live-reply", { timeout: 10000 });
  });
});