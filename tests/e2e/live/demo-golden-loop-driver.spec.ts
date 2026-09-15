import { readFileSync, writeFileSync } from "node:fs";

import { expect, request as playwrightRequest, test, type Page } from "@playwright/test";

/**
 * DEMO GOLDEN LOOP DRIVER — not a test.
 *
 * Drives the REAL full-stack Golden Loop (quantum tunnelling) through every
 * durable LearningPhase to ``complete``, using the live USTC model, then saves
 * the browser ``storageState`` (qa_session cookie + qa_conversation_id in
 * localStorage) so the SAME conversation can be reloaded later and the
 * finished loop is immediately visible again for demo recording.
 *
 * Mirrors tests/e2e/live/golden-loop-deterministic.spec.ts stage-for-stage
 * (commitment → attempt → revision → coding+tunnelling tool → teach-back →
 * transfer → solo → complete), but asserts only what is needed to know a stage
 * finished, and stores state instead of expecting a clean environment.
 */

const STATE_OUT = process.env.QA_DEMO_STATE_OUT ?? ".demo/qa_demo_state.json";
const FWDR_STATE_OUT = process.env.QA_DEMO_FWDR_STATE_OUT ?? (STATE_OUT.replace(/\.json$/, ".forward.json"));

type LiveAuth = {
  course_id: string;
  curriculum_edition_id: string;
  ta_token: string;
  ta_user_id?: string;
};

function liveAuth(): LiveAuth {
  const file = process.env.QA_E2E_AUTH_FILE?.trim();
  if (!file) throw new Error("QA_E2E_AUTH_FILE is required for the live Golden Loop");
  const value: unknown = JSON.parse(readFileSync(file, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("auth file invalid");
  return value as LiveAuth;
}

function liveApiKey(): string {
  const key = process.env.USTC_API?.trim();
  if (!key || key.length < 16) throw new Error("USTC_API is required for the live login path");
  return key;
}

/**
 * Wait for the current workflow turn to reach its terminal state.  The
 * composer's send button returns to its enabled "发送 / 运行" state after the
 * terminal SSE event is consumed; HITL renders a separate interrupt card.
 */
async function waitForWorkflowTerminal(page: Page): Promise<"completed" | "interrupted"> {
  // The composer's send button enters its pending "执行工作流" state while the
  // workflow streams and returns to the enabled "发送 / 运行" state after the
  // terminal SSE event is consumed — that enabled state is the terminal cue.
  await page
    .getByRole("button", { name: /执行工作流|先完成上方复核/ })
    .first()
    .waitFor({ state: "visible", timeout: 30_000 });
  await expect(page.getByRole("button", { name: /发送|运行/ }).first()).toBeEnabled({
    timeout: 600_000,
  });
  return (await page.getByTestId("hitl-interrupt").isVisible().catch(() => false))
    ? "interrupted"
    : "completed";
}

async function expectPhase(page: Page, expected: string, timeout = 30_000): Promise<void> {
  await page
    .locator('[data-testid="learning-phase"]')
    .waitFor({ state: "visible", timeout });
  await page
    .locator(`[data-testid="learning-phase"][data-phase="${expected}"]`)
    .waitFor({ state: "visible", timeout });
}

async function loginThroughProduct(page: Page): Promise<void> {
  await page.goto("/agent", { waitUntil: "domcontentloaded" });
  await page.getByRole("form", { name: "API Key 登录表单" }).waitFor({ state: "visible", timeout: 30_000 });
  await page.getByLabel("USTC API Key").fill(liveApiKey());
  await page.getByRole("button", { name: "连接并进入学习空间" }).click();
  await page.getByTestId("agent-experience").waitFor({ state: "visible", timeout: 90_000 });
}

async function sendStudentMessage(
  page: Page,
  message: string,
  attempt: string | null = null,
): Promise<void> {
  const streamResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/teaching/turns/stream" &&
      response.request().method() === "POST",
    { timeout: 300_000 },
  );
  await page.getByLabel("给 Quantum Agent 的问题").fill(message);
  if (attempt !== null) {
    const attemptBox = page.getByLabel("学生当前尝试");
    if (await attemptBox.isVisible().catch(() => false)) {
      await attemptBox.fill(attempt);
    }
  }
  const sendButton = page.getByRole("button", { name: /发送|运行/ });
  await expect(sendButton).toBeEnabled();
  await sendButton.click();
  const response = await streamResponse;
  if (!response.ok()) throw new Error(`stream response ${response.status()}`);
}

async function sendExpectJsonRequest(
  page: Page,
  action: (page: Page) => Promise<void>,
): Promise<void> {
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 300_000 },
  );
  await action(page);
  const response = await streamResponse;
  if (!response.ok()) throw new Error(`stream response ${response.status()}`);
  await waitForWorkflowTerminal(page);
}

function computeTransmissionT(
  energyEV: number,
  barrierHeightEV: number,
  barrierWidthM: number,
  particleMassKg: number,
): number {
  const joulePerEV = 1.602176634e-19;
  const hbarJs = 1.054571817e-34;
  const energyJ = energyEV * joulePerEV;
  const v0J = barrierHeightEV * joulePerEV;
  const deltaEJ = v0J - energyJ;
  if (deltaEJ <= 0) throw new Error("computeTransmissionT expects the tunnelling regime E < V0");
  const kInside = Math.sqrt(2.0 * particleMassKg * deltaEJ) / hbarJs;
  const arg = kInside * barrierWidthM;
  if (arg > 700.0) {
    const exponent = -2.0 * arg;
    if (exponent < -745.0) return 0.0;
    const preFactor = (16.0 * energyJ * (v0J - energyJ)) / (v0J * v0J);
    return preFactor * Math.exp(exponent);
  }
  const sinhSq = Math.sinh(arg) ** 2;
  const denominator = 1.0 + (v0J * v0J * sinhSq) / (4.0 * energyJ * (v0J - energyJ));
  return 1.0 / denominator;
}

async function fetchLearningStatistics(auth: LiveAuth): Promise<Record<string, unknown>> {
  const api = await playwrightRequest.newContext({
    baseURL: process.env.QUANTUM_API_BASE_URL ?? "http://127.0.0.1:8000",
    extraHTTPHeaders: { Authorization: `Bearer ${auth.ta_token}` },
  });
  try {
    const path =
      `/api/v1/courses/${auth.course_id}/editions/${auth.curriculum_edition_id}` +
      "/teacher/learning-statistics";
    const response = await api.get(path);
    if (response.status() !== 200) throw new Error(`learning-statistics ${response.status()}`);
    return (await response.json()) as Record<string, unknown>;
  } finally {
    await api.dispose();
  }
}

test.describe.configure({ mode: "serial" });
test.describe("DEMO golden-loop state saver (tunnelling)", () => {
  test("drives the full loop and saves browser storageState", async ({ page }) => {
    test.setTimeout(2_100_000); // 35 minutes for the full live loop
    const auth = liveAuth();

    // ── Stage 1: Login through the real product ──
    await loginThroughProduct(page);
    await page.getByRole("button", { name: /^概念/ }).click();

    const beforeStats = await fetchLearningStatistics(auth);
    const beforeTotal = Number(beforeStats.total_recorded_events ?? 0);
    const beforeKinds = (beforeStats.events_by_kind ?? {}) as Record<string, { event_count?: number }>;
    const beforeTransferVerified = Number(beforeKinds.transfer_verified?.event_count ?? 0);

    console.log(`[demo-driver] login ok, evidence before=${beforeTotal}`);
    const stepLog: string[] = [];

    // ── Stage 2: Tunnelling question triggers the commitment gate ──
    await sendStudentMessage(
      page,
      "我想理解量子隧穿：为什么粒子能量 E 小于势垒高度 V0 时仍然可能出现在势垒右侧？",
    );
    await waitForWorkflowTerminal(page);
    await expectPhase(page, "commitment_required");
    await page.getByTestId("commitment-card").waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("commitment_required reached");
    console.log(`[demo-driver] stage2 commitment gate ok`);

    // ── Stage 3: Commitment submitted → attempt_received ──
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByRole("textbox", { name: "认知承诺文本" }).fill("我预测：E<V0 时透射概率为零，粒子不可能穿越势垒。");
      await p.getByRole("button", { name: /提交承诺/ }).click();
    });
    await expectPhase(page, "attempt_received");
    await page
      .getByTestId("minimal-intervention-card")
      .waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("attempt_received reached");
    console.log(`[demo-driver] stage3 commitment ok`);

    // ── Stage 4: Revised attempt → awaiting_revision ──
    await sendStudentMessage(
      page,
      "我修正：势垒右侧的波函数振幅应该很小但不为零，透射概率可能是一个很小的正数。",
      "波函数在势垒内指数衰减，右侧振幅非零，透射概率是一个很小的正数。",
    );
    await waitForWorkflowTerminal(page);
    await expectPhase(page, "awaiting_revision");
    await page.getByTestId("agent-tutor-result").waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("awaiting_revision reached");
    console.log(`[demo-driver] stage4 revision ok`);

    // ── Stage 4.5: save state mid-loop so even a crash leaves a recoverable cue ──
    const storedCidNav = await page.evaluate(() => window.localStorage.getItem("qa_conversation_id"));
    if (storedCidNav) {
      const state = await page.context().storageState({ path: FWDR_STATE_OUT });
      writeFileSync(
        FWDR_STATE_OUT,
        JSON.stringify({ ...state, note: "forward-cue save (awaiting_revision)" }, null, 2),
      );
      console.log(`[demo-driver] forward-cue storageState saved: ${storedCidNav}`);
    }

    // ── Stage 5: Coding Agent + sandbox + tunnelling tool (run_experiments) ──
    await page.getByRole("button", { name: /^实验/ }).click();
    // Wait for the experiments workspace's numerical input zone to finish
    // rendering (mode switch re-renders the main surface; clicking send too
    // early can abort the fetch before it reaches the BFF).
    await page
      .getByText(/矩势垒散射|NUMERICAL INPUT/)
      .first()
      .waitFor({ state: "visible", timeout: 30_000 });
    const tunnellingToggle = page.getByLabel(/量子隧穿/);
    if (await tunnellingToggle.isVisible().catch(() => false)) {
      if (!(await tunnellingToggle.isChecked())) {
        await tunnellingToggle.check();
      }
    }
    // Fill the composer first; the send button is disabled on an empty input.
    await page.getByLabel("给 Quantum Agent 的问题").fill(
      "请用矩势垒散射工具计算 E=5eV, V0=10eV, a=1e-10m 的透射概率 T 和反射概率 R，并验证 R+T=1。",
    );
    await expect(page.getByRole("button", { name: /发送|运行/ })).toBeEnabled({ timeout: 30_000 });
    // Poll for the observable outcome instead of a racing waitForResponse:
    // coding-artifact + tunnelling-metrics, or an explicit failure banner.
    await Promise.race([
      page.getByTestId("coding-artifact").waitFor({ state: "visible", timeout: 360_000 }),
      page.getByText(/网络错误|network error|无法|失败/).first().waitFor({ state: "visible", timeout: 360_000 }).then(async () => {
        const bannerText = await page.locator("body").innerText().catch(() => "");
        throw new Error(`stage5 observed a failure banner: ${bannerText}`);
      }),
    ]);
    await page
      .locator('[data-testid="coding-verification-status"]')
      .waitFor({ state: "visible", timeout: 60_000 });
    const verifyText = (await page.getByTestId("coding-verification-status").textContent()) ?? "";
    if (!verifyText.includes("PASS")) {
      console.warn(`[demo-driver] coding verification status: ${verifyText.trim()} (continuing)`);
    }
    await page.getByTestId("tunnelling-metrics").waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("coding agent + tunnelling tool ran");
    console.log(`[demo-driver] stage5 coding+tunnelling ok`);

    // ── Stage 6: Teach-back request + reconstruction → reconstruction_required ──
    await page.getByRole("button", { name: /^概念/ }).click();
    await expectPhase(page, "awaiting_revision");
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByTestId("request-teach-back-button").click();
    });
    await page.getByTestId("teach-back-card").waitFor({ state: "visible", timeout: 60_000 });
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByRole("textbox", { name: "teach-back 重构" }).fill(
        "波函数在势垒内不是突变为零，而是指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
      );
      await p.getByRole("button", { name: /提交重构/ }).click();
    });
    await expectPhase(page, "reconstruction_required");
    stepLog.push("reconstruction_required reached");
    console.log(`[demo-driver] stage6 teach-back 1 ok`);

    // ── Stage 7: Re-submit reconstruction → transfer_required ──
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByRole("textbox", { name: "teach-back 重构" }).fill(
        "波函数在势垒内不是突变为零，而是指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
      );
      await p.getByRole("button", { name: /提交重构/ }).click();
    });
    await expectPhase(page, "transfer_required");
    await page.getByTestId("transfer-card").waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("transfer_required reached");
    console.log(`[demo-driver] stage7 teach-back 2 ok`);

    // ── Stage 8: Request transfer → solo_active ──
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByTestId("request-transfer-button").click();
    });
    await expectPhase(page, "solo_active");
    await page.getByTestId("transfer-card").waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("solo_active reached");
    console.log(`[demo-driver] stage8 solo armed ok`);

    // ── Stage 9: WRONG solo attempt — phase stays solo_active (demonstrated) ──
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByRole("textbox", { name: "迁移尝试" }).fill("透射系数 T = 0.999（几乎全透）");
      await p.getByRole("button", { name: /提交迁移尝试/ }).click();
    });
    await expectPhase(page, "solo_active");
    stepLog.push("wrong solo attempt rejected (solo_active preserved)");
    console.log(`[demo-driver] stage9 wrong solo rejected ok`);

    // ── Stage 10: CORRECT solo attempt → complete ──
    const transferExpectedT = computeTransmissionT(5, 10, 1.5e-10, 9.1093837015e-31);
    const correctResponse = `透射系数 T = ${transferExpectedT.toFixed(4)}（与数值验证一致：势垒更宽，透射率下降）`;
    await sendExpectJsonRequest(page, async (p) => {
      await p.getByRole("textbox", { name: "迁移尝试" }).fill(correctResponse);
      await p.getByRole("button", { name: /提交迁移尝试/ }).click();
    });
    await expectPhase(page, "complete");
    await page
      .locator('[data-testid="learning-phase"][data-loop-completed="true"]')
      .waitFor({ state: "visible", timeout: 30_000 });
    await page.getByTestId("learning-loop-complete").waitFor({ state: "visible", timeout: 60_000 });
    stepLog.push("complete + loop-completed reached");
    console.log(`[demo-driver] stage10 complete ok (T=${transferExpectedT.toFixed(4)})`);

    // ── Stage 11: LearningJourney all 5 segments done ──
    for (const stage of ["predict", "diagnose", "verify", "explain", "transfer"] as const) {
      await page
        .locator(`[data-testid="learning-journey"] li[data-stage="${stage}"][data-state="done"]`)
        .waitFor({ state: "visible", timeout: 30_000 });
    }
    stepLog.push("course journey all 5 segments done");

    // ── Save the browser state: this is the durable cue for demo recording ──
    const storedCid = await page.evaluate(() => window.localStorage.getItem("qa_conversation_id"));
    if (!storedCid) throw new Error("no qa_conversation_id in localStorage after the loop");
    await page.context().storageState({ path: STATE_OUT });
    writeFileSync(
      STATE_OUT,
      JSON.stringify(
        {
          ...JSON.parse(readFileSync(STATE_OUT, "utf8")),
          conversation_id: storedCid,
          course_id: auth.course_id,
          curriculum_edition_id: auth.curriculum_edition_id,
          note: "Complete Golden Loop state for demo recording. Load with --load-storage-state.",
        },
        null,
        2,
      ),
    );

    // ── Persistence verification ──
    const afterStats = await fetchLearningStatistics(auth);
    const afterTotal = Number(afterStats.total_recorded_events ?? 0);
    const afterKinds = (afterStats.events_by_kind ?? {}) as Record<string, { event_count?: number }>;
    const afterTransferVerified = Number(afterKinds.transfer_verified?.event_count ?? 0);
    if (afterTotal <= beforeTotal) {
      throw new Error(`learning-statistics did not increase (before=${beforeTotal}, after=${afterTotal})`);
    }
    if (beforeTransferVerified === 0 && afterTransferVerified === 0) {
      throw new Error("no transfer_verified evidence recorded after the solo attempt");
    }

    console.log(
      `[demo-driver] DONE persistence: events ${beforeTotal}→${afterTotal}, ` +
        `transfer_verified ${beforeTransferVerified}→${afterTransferVerified}, ` +
        `conversation=${storedCid}`,
    );
    console.log(`[demo-driver] storageState saved to ${STATE_OUT}`);
    for (const line of stepLog) console.log(`[demo-driver]   * ${line}`);
  });
});
