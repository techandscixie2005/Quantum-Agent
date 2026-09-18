/** Real BFF + Python + database smoke. No first-party interception or fixtures.
 * Provide an existing private storageState with QA_VIDEO_SESSION_FILE.
 * This is a prefix check, not a claim that the full learning loop passed.
 */
import { test, expect } from "@playwright/test";

test("video task starts empty, records commitment, restores it, and exposes real sources", async ({ browser, baseURL }) => {
  const session = process.env.QA_VIDEO_SESSION_FILE;
  if (!session) throw new Error("QA_VIDEO_SESSION_FILE must name an authorized private session file");
  const context = await browser.newContext({ storageState: session, baseURL });
  try {
    const page = await context.newPage();
    // Identity only: a fresh episode, never seed completed student evidence.
    await page.goto("/agent");
    await expect(page.getByTestId("agent-experience")).toBeVisible();
    await page.getByRole("button", { name: "新建学习记录", exact: true }).click();
    await page.getByRole("button", { name: "加载课程任务", exact: true }).click();
    await expect(page.getByTestId("coding-artifact")).toHaveCount(0);
    await expect(page.getByTestId("learning-loop-complete")).toHaveCount(0);
    await page.getByRole("button", { name: "发送 / 运行", exact: true }).click();
    await expect(page.getByTestId("commitment-card")).toBeVisible({ timeout: 180_000 });
    await page.getByLabel("认知承诺文本").fill("E<V0，所以波函数处处为零，透射率为零。我还不确定宽度的影响。");
    await page.getByRole("button", { name: "提交承诺", exact: true }).click();
    await expect(page.getByTestId("learning-phase")).toHaveAttribute("data-phase", "attempt_received", { timeout: 180_000 });
    const episode = await page.evaluate(() => localStorage.getItem("qa_conversation_id"));
    expect(episode).toMatch(/^[0-9a-f-]{36}$/);
    await page.reload();
    await expect(page.getByTestId("learning-phase")).toHaveAttribute("data-phase", "attempt_received");
    await page.getByRole("button", { name: "打开证据面板", exact: true }).first().click();
    // Missing/unpublished source fails this acceptance; never skip this assertion.
    await expect(page.getByTestId("agent-citation").first()).toBeVisible();
    await page.getByTestId("agent-citation").first().click();
    await expect(page.getByTestId("source-preview")).toBeVisible();
  } finally {
    await context.close();
  }
});
