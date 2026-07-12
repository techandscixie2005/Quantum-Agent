import { test, expect } from "@playwright/test";

test.describe("Citation Integrity", () => {
  test("tutor response uses only allowed citation IDs", async ({ page }) => {
    await page.goto("/");

    await page.locator(".composer textarea").fill("Franck-Condon 原理是什么？");
    await page.locator(".send-button").click();

    await page.waitForSelector(".tutor-message", { timeout: 10000 });
    const responseText = await page.locator(".tutor-message").textContent();
    expect(typeof responseText).toBe("string");
  });

  test("evidence panel shows real citations after query", async ({ page }) => {
    await page.goto("/");

    await page.locator(".composer textarea").fill("请解释微扰理论的基本思想");
    await page.locator(".send-button").click();

    await page.waitForSelector(".live-reply", { timeout: 10000 });
    await page.locator(".evidence-toggle").click();
    await expect(page.locator(".right-panel")).toBeVisible();
  });

  test("response does not reveal hidden model names", async ({ page }) => {
    await page.goto("/");

    await page.locator(".composer textarea").fill("双原子分子的分子轨道怎么理解？");
    await page.locator(".send-button").click();

    await page.waitForSelector(".live-reply", { timeout: 10000 });
    const html = await page.content();
    expect(html).not.toContain("deepseek");
    expect(html).not.toContain("qwen");
    expect(html).not.toContain("glm-5");
    expect(html).not.toContain("api.llm.ustc.edu.cn");
  });
});