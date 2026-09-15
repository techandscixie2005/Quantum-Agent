import { test, expect } from "@playwright/test";

for (const outcome of ["success", "failure"]) {
  test(`DRY RUN recording pipeline ${outcome}`, async ({ page }) => {
    if (outcome === "failure") test.fail(true, "故意失败，仅验证失败原片保留");
    await page.route("**/*", (route) => route.abort());
    await page.setContent(`<html lang="zh"><body style="font:32px sans-serif;padding:80px">
      <h1>仅录制管线试验</h1><p>不是产品运行，没有模型调用，没有科学结果。</p>
      <p>分支：${outcome}；成功与失败原片均保留。</p></body></html>`);
    await page.screenshot({ path: test.info().outputPath("pipeline-only.png") });
    await expect(page.locator("h1")).toHaveText(outcome === "success" ? "仅录制管线试验" : "故意不匹配", { timeout: 1000 });
  });
}
