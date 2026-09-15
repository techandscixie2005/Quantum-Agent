import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * ONE-SHOT DIAGNOSIS: load the forward-cue storageState (conversation
 * 2f6aaef4 at awaiting_revision), switch to run_experiments, send the
 * tunnelling request the way the demo driver does, and observe whether the
 * fetch reaches the backend / what the page shows.  Used to root-cause the
 * stage-5 network error.
 */

test.describe.configure({ mode: "serial" });
test("stage5 tunnelling turn against the persisted conversation", async ({ page, context }) => {
  test.setTimeout(420_000);

  const fwd = process.env.QA_DEMO_FWDR_STATE_OUT;
  if (!fwd) throw new Error("QA_DEMO_FWDR_STATE_OUT required");
  const state = JSON.parse(readFileSync(fwd, "utf8"));
  await context.addCookies(state.cookies);

  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on("requestfailed", (req) => {
    const url = req.url();
    if (url.includes("/api/teaching/turns/stream")) {
      console.log(`[diag] REQUEST FAILED: ${url} :: ${req.failure()?.errorText ?? "?"}`);
    }
  });
  page.on("response", (resp) => {
    const url = resp.url();
    if (url.includes("/api/teaching/turns/stream")) {
      console.log(`[diag] stream response: ${resp.status()} ${url}`);
    }
  });

  await page.goto("/agent", { waitUntil: "domcontentloaded" });
  await page.getByTestId("agent-experience").waitFor({ state: "visible", timeout: 60_000 });

  // Restore the conversation via localStorage BEFORE the app reads it.
  const stored = state.origins?.[0]?.localStorage?.find((x: { name: string }) => x.name === "qa_conversation_id");
  if (stored) {
    await page.evaluate((cid) => window.localStorage.setItem("qa_conversation_id", cid as string), stored.value);
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByTestId("agent-experience").waitFor({ state: "visible", timeout: 60_000 });
  }

  console.log(`[diag] phase marker: ${await page.locator('[data-testid="learning-phase"]').getAttribute("data-phase").catch(() => "absent")}`);
  await page.getByRole("button", { name: /^实验/ }).click();
  await page
    .getByText(/矩势垒散射|NUMERICAL INPUT/)
    .first()
    .waitFor({ state: "visible", timeout: 30_000 });
  console.log(`[diag] experiment workspace rendered`);

  const tunnellingToggle = page.getByLabel(/量子隧穿/);
  if (await tunnellingToggle.isVisible().catch(() => false)) {
    if (!(await tunnellingToggle.isChecked())) await tunnellingToggle.check();
  }
  await page.getByLabel("给 Quantum Agent 的问题").fill(
    "请用矩势垒散射工具计算 E=5eV, V0=10eV, a=1e-10m 的透射概率 T 和反射概率 R，并验证 R+T=1。",
  );
  await expect(page.getByRole("button", { name: /发送|运行/ })).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("button", { name: /发送|运行/ }).click();
  console.log(`[diag] tunnelling request clicked, awaiting outcome...`);

  const outcome = await Promise.race([
    page.getByTestId("coding-artifact").waitFor({ state: "visible", timeout: 360_000 }).then(() => "coding-artifact"),
    page.getByText(/网络错误|network error|无法|失败/).first().waitFor({ state: "visible", timeout: 360_000 }).then(() => "failure-banner"),
  ]);
  console.log(`[diag] OUTCOME=${outcome}`);
  if (outcome === "failure-banner") {
    console.log(`[diag] console errors:\n${consoleErrors.slice(0, 10).join("\n")}`);
    console.log(`[diag] body snippet:\n${(await page.locator("body").innerText().catch(() => "")).slice(-600)}`);
  }
  expect(outcome).toBe("coding-artifact");
});
