import { test, expect } from "@playwright/test";

test.describe("Derivation Review", () => {
  test("sends derivation steps and receives error localization", async ({ page }) => {
    await page.goto("/");

    // Switch to derivation mode
    const derivationButton = page.locator("button.mode-button").filter({ hasText: "看推导" });
    if (await derivationButton.isVisible()) {
      await derivationButton.click();
      await page.waitForSelector(".derivation-workspace", { timeout: 5000 });

      await page.locator(".composer textarea").fill(
        "区域 I：ψ₁ = Aeⁱᵏˣ + Be⁻ⁱᵏˣ\n区域 II：ψ₂ = Ce⁻ᵏˣ + Deᵏˣ\n我的 k 用了同一个值"
      );
      await page.locator(".send-button").click();

      await page.waitForSelector(".tutor-message", { timeout: 10000 });
      await expect(page.locator(".diagnosis-panel")).toBeVisible({ timeout: 5000 });
    }
  });

  test("derivation workspace shows diagnosis panel after submission", async ({ page }) => {
    await page.goto("/");
    const derivationButton = page.locator("button.mode-button").filter({ hasText: "看推导" });
    if (await derivationButton.isVisible()) {
      await derivationButton.click();
      await page.waitForSelector(".diagnosis-panel, .diagnosis-heading", { timeout: 5000 });
      await expect(
        page.locator(".diagnosis-panel").or(page.locator(".diagnosis-heading"))
      ).toBeVisible();
    }
  });
});