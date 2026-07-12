import { test, expect } from "@playwright/test";

test.describe("Mobile Responsive", () => {
  test("mobile viewport shows hamburger menu", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");

    await expect(page.locator(".mobile-nav")).toBeVisible();
    await expect(page.locator(".quantum-app")).toBeVisible();
  });

  test("mobile sidebar toggles open and closed", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");

    // Sidebar should be initially hidden
    await expect(page.locator(".left-sidebar.mobile-open")).not.toBeVisible();

    // Open sidebar
    await page.locator(".mobile-nav").click();
    await expect(page.locator(".left-sidebar.mobile-open")).toBeVisible();

    // Close by clicking backdrop
    await page.locator(".mobile-backdrop").click();
    await expect(page.locator(".left-sidebar.mobile-open")).not.toBeVisible();
  });

  test("composer fits mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");

    const composer = page.locator(".composer");
    await expect(composer).toBeVisible();
    const box = await composer.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(375);
  });

  test("capability modal works on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");

    await page.locator(".gateway-button").click();
    await expect(page.locator(".model-modal")).toBeVisible();
    await page.locator('[aria-label="关闭能力设置"]').click();
    await expect(page.locator(".model-modal")).not.toBeVisible();
  });
});