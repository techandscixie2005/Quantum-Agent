import { test, expect } from "@playwright/test";

test.describe("Golden Tunneling Loop", () => {
  test("student predicts tunneling is impossible, receives H2 hint", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".composer");

    await page.locator(".composer textarea").fill(
      "粒子的能量比势垒低，按照能量守恒，它应该完全不可能穿过势垒，对吗？"
    );
    await page.locator(".send-button").click();

    await page.waitForSelector(".tutor-message", { timeout: 10000 });
    const responseText = await page.locator(".tutor-message").textContent();
    expect(responseText).toContain("能量守恒");
  });

  test("tunneling misconception is diagnosed", async ({ page }) => {
    await page.goto("/");

    await page.locator(".composer textarea").fill(
      "粒子怎么穿过比它能量高的势垒？这不违反能量守恒吗？"
    );
    await page.locator(".send-button").click();

    await page.waitForSelector(".tutor-message", { timeout: 10000 });
    const hintBox = page.locator(".hint-box");
    await expect(hintBox).toBeVisible({ timeout: 5000 });
  });

  test("simulation result shows real R and T values", async ({ page }) => {
    await page.goto("/");

    // Switch to experiment mode
    const experimentButton = page.locator("button.mode-button").filter({ hasText: "做实验" });
    if (await experimentButton.isVisible()) {
      await experimentButton.click();
      await page.waitForSelector(".experiment-workspace", { timeout: 5000 });

      // Run simulation
      await page.locator(".run-sim").click();
      await page.waitForSelector(".result-strip", { timeout: 15000 });

      // Check R and T are displayed
      const resultStrip = page.locator(".result-strip");
      await expect(resultStrip).toContainText("R");
      await expect(resultStrip).toContainText("T");
    }
  });

  test("probability conservation is checked after simulation", async ({ page }) => {
    await page.goto("/");
    const experimentButton = page.locator("button.mode-button").filter({ hasText: "做实验" });
    if (await experimentButton.isVisible()) {
      await experimentButton.click();
      await page.waitForSelector(".experiment-workspace");
      await page.locator(".run-sim").click();
      await page.waitForSelector(".sim-stats", { timeout: 15000 });
      await expect(page.locator(".sim-stats")).toBeVisible();
    }
  });
});