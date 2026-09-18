import { test, expect } from "@playwright/test";

// Real authenticated page. This read-only check sends no teaching/model requests.
for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
  test(`new task keeps its primary action in view at ${viewport.width}`, async ({ browser, baseURL }) => {
    expect(process.env.QA_VIDEO_SESSION_FILE).toBeTruthy();
    const context = await browser.newContext({
      storageState: process.env.QA_VIDEO_SESSION_FILE,
      viewport,
    });
    try {
      await context.addInitScript(() => {
        localStorage.setItem("qa_course_key", "7c33796f-8d45-5fd7-93b9-13ae8c7572eb:5dd085cb-831c-5ed1-ae01-327f700dc12a");
        localStorage.removeItem("qa_conversation_id");
      });
      const page = await context.newPage();
      await page.goto(`${baseURL}/agent`);
      await page.getByRole("button", { name: "新建学习记录", exact: true }).click();
      await page.getByRole("button", { name: "加载课程任务", exact: true }).click();
      const send = page.getByRole("button", { name: "发送 / 运行", exact: true });
      await expect(send).toBeInViewport({ ratio: 1 });
      // Do not let Playwright's automatic scrolling conceal an off-screen action.
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      await expect(page.getByTestId("learning-loop-complete")).toHaveCount(0);
      await expect(page.getByTestId("coding-artifact")).toHaveCount(0);
      await page.screenshot({ path: `docs/implementation/artifacts/recheck-${viewport.width}-new-task.png` });
    } finally {
      await context.close();
    }
  });
}
