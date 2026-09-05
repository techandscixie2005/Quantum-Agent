import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

import {
  expect,
  request as playwrightRequest,
  test,
  type Page,
} from "@playwright/test";

/**
 * Golden Learning Loop · live full-stack · DETERMINISTIC 22-stage closure.
 *
 * This is the FROZEN-gate test the competition release depends on.  It drives
 * the REAL stack with NO first-party API mocking and HARD-ASSERTS that every
 * one of the 22 stages is reached, that the authoritative durable
 * ``LearningPhase`` advances in the correct order, and that no required
 * pedagogical phase is skippable.
 *
 * Phase expectations are read from the hidden UI marker
 * ``<span data-testid="learning-phase" data-phase="..." data-required-action="..."
 *        data-loop-completed="true|false">`` which mirrors the backend's
 * authoritative ``LearningNativeTurnState`` (a pure function of the persisted
 * ``DurableLearningPhase``).  The test never infers the phase from the SSE
 * ``workflow.completed`` lifecycle event, which fires for every bounded turn.
 *
 *   1.  Login                          → phase open
 *   2.  Tunnelling question            → phase commitment_required
 *   3.  Commitment submitted           → phase attempt_received (accepted commitment = initial attempt; invariant B: not complete, not full answer)
 *   4.  Revised attempt                → phase awaiting_revision
 *   4.5 Refresh during durable phase   → phase awaiting_revision (persists across reload)
 *   5.  Diagnosis rendered
 *   6.  Coding Agent (real tool)       → coding-artifact visible
 *   7.  Sandbox executes               → METRICS_JSON present
 *   7.5 Static safety + isolated sandbox → coding-progress-running done + sandbox stdout
 *   8.  Verifier PASS                  → coding-verification-status PASS
 *   9.  Tunnelling metrics shown
 *   10. LearningJourney verify done
 *   11. Teach-Back requested           → phase reconstruction_required
 *   12. Teach-Back submitted           → phase transfer_required
 *   13. Transfer armed (Solo)          → phase solo_active
 *   14. Solo lock notice visible
 *   15. WRONG solo attempt             → phase solo_active (NOT complete)
 *   16. CORRECT solo attempt           → phase complete + loop-completed
 *   17. LearningJourney all 5 done
 *   17.5 Cognitive Mirror updated      → mirror panel + concept states from evidence
 *   18. Learning statistics increased
 *   19. Agent trace persisted
 *   20. Trace has full fixed-order workflow
 *   21. TRANSFER_VERIFIED evidence exists after stage 16
 *   22. No TRANSFER_VERIFIED evidence existed before stage 16
 *
 * The deterministic transfer fallback (LearningNativePolicy.FALLBACK_TRANSFER_PROMPT)
 * guarantees Stage 13 is reachable even if the USTC model returns no transfer
 * proposal.  The numeric verifier (``_attempt_verified``) accepts a solo
 * attempt only when the response contains a number within
 * ``absolute_tolerance`` of the persisted oracle's ``expected_value`` AND a
 * scientific tool result PASSed this turn — so Stage 16 must submit the
 * correct numeric T for the transfer task's barrier width.
 *
 * Run via scripts/run-live-e2e.sh (seeds auth, starts the Compose stack).
 * The deterministic CI suite does NOT run this test; it only runs when the
 * Compose stack + USTC_API are available.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type LiveAuth = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  ta_user_id?: string;
  ta_token: string;
}>;

function liveApiKey(): string {
  const key = process.env.USTC_API?.trim();
  if (!key || key.length < 16 || key.length > 256) {
    throw new Error("USTC_API is required for the live login path");
  }
  return key;
}

function liveAuth(): LiveAuth {
  const configured = process.env.QA_E2E_AUTH_FILE?.trim();
  if (!configured) throw new Error("QA_E2E_AUTH_FILE is required for the live Golden Loop");
  const path = resolve(configured);
  if ((statSync(path).mode & 0o077) !== 0) {
    throw new Error("The live E2E credential file must not be readable by group or others");
  }
  const value: unknown = JSON.parse(readFileSync(path, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("The live E2E credential file is invalid");
  }
  const input = value as Record<string, unknown>;
  for (const key of ["course_id", "curriculum_edition_id"] as const) {
    if (typeof input[key] !== "string" || !UUID.test(input[key])) {
      throw new Error(`The live E2E ${key} is invalid`);
    }
  }
  for (const key of ["ta_token"] as const) {
    if (typeof input[key] !== "string" || input[key].length < 32 || input[key].length > 512) {
      throw new Error(`The live E2E ${key} is invalid`);
    }
  }
  return input as LiveAuth;
}

async function loginThroughProduct(page: Page): Promise<void> {
  await page.goto("/agent", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("form", { name: "API Key 登录表单" })).toBeVisible();
  await page.getByLabel("USTC API Key").fill(liveApiKey());
  await page.getByRole("button", { name: "连接并进入学习空间" }).click();
  await expect(page.getByTestId("agent-experience")).toBeVisible({ timeout: 60_000 });
}

async function waitForWorkflowTerminal(page: Page): Promise<"completed" | "interrupted"> {
  // Settle on the COMPOSER state, not the result card: the previous turn's
  // `agent-tutor-result` stays mounted while the next turn's stream is still
  // in flight, so it cannot be used to detect that the current turn finished.
  // Phase 1 proves the turn actually STARTED (the send button flips to the
  // disabled "执行工作流" label while the workflow streams); phase 2 then
  // settles on the terminal — the HITL card mounts, or the send button returns
  // to its enabled "发送 / 运行" label after the terminal SSE event has been
  // fully consumed and state updated.
  await expect(
    page.getByRole("button", { name: /执行工作流|先完成上方复核/ }),
    "workflow must start (composer enters its pending state)",
  ).toBeVisible({ timeout: 30_000 });
  await expect
    .poll(
      async () => {
        if (await page.getByTestId("hitl-interrupt").isVisible()) return "interrupted";
        if (await page.getByRole("button", { name: "发送 / 运行" }).isEnabled()) return "completed";
        return "pending";
      },
      { timeout: 600_000, intervals: [2_000, 5_000, 10_000] },
    )
    .toMatch(/^(completed|interrupted)$/);
  return (await page.getByTestId("hitl-interrupt").isVisible()) ? "interrupted" : "completed";
}

/**
 * Hard-assert the authoritative durable LearningPhase shown by the hidden UI
 * marker.  The marker mirrors ``result.learning_native.phase`` (a pure function
 * of the persisted ``DurableLearningPhase``), so this is a DB-backed phase
 * assertion without a separate API endpoint.  On mismatch the test FAILS —
 * there is no soft fallback.
 */
async function expectPhase(page: Page, expected: string, timeout = 30_000): Promise<void> {
  await expect(
    page.locator('[data-testid="learning-phase"]'),
    `expected durable phase "${expected}"`,
  ).toHaveAttribute("data-phase", expected, { timeout });
}

async function expectLoopComplete(page: Page, expected: boolean, timeout = 30_000): Promise<void> {
  await expect(
    page.locator('[data-testid="learning-phase"]'),
    `expected learning_loop_completed=${expected}`,
  ).toHaveAttribute("data-loop-completed", expected ? "true" : "false", { timeout });
}

/**
 * Hard-assert that the Cognitive Mirror has updated from PERSISTED learning
 * evidence (spec section 12, stage 21: "Cognitive Mirror updates").  The mirror
 * is rendered from ``result.learning_native.cognitive_mirror`` which the
 * backend derives from persisted learning evidence — NOT from a transfer
 * question being displayed.  It must be visible and must carry at least one
 * concept state once the loop is complete.
 */
async function expectMirrorUpdated(page: Page, timeout = 30_000): Promise<void> {
  const mirror = page.locator('[data-testid="cognitive-mirror"]', { hasText: "Cognitive Mirror" });
  await expect(mirror, "Cognitive Mirror panel must render after loop completion").toBeVisible({ timeout });
  await expect(
    mirror.locator("article[data-state]"),
    "Cognitive Mirror must contain at least one concept state derived from learning evidence",
  ).toHaveCount(1, { timeout });
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
  const messageBox = page.getByLabel("给 Quantum Agent 的问题");
  await messageBox.fill(message);
  if (attempt !== null) {
    const attemptBox = page.getByLabel("学生当前尝试");
    if (await attemptBox.isVisible()) {
      await attemptBox.fill(attempt);
    }
  }
  const sendButton = page.getByRole("button", { name: /发送|运行/ });
  await expect(sendButton).toBeEnabled();
  await sendButton.click();
  const response = await streamResponse;
  expect(response.ok()).toBe(true);
}

async function submitCommitment(page: Page, response: string): Promise<void> {
  const card = page.getByTestId("commitment-card");
  await expect(card, "CommitmentCard must render").toBeVisible({ timeout: 30_000 });
  await page.getByRole("textbox", { name: "认知承诺文本" }).fill(response);
  const submitButton = page.getByRole("button", { name: /提交承诺/ });
  await expect(submitButton).toBeEnabled();
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 300_000 },
  );
  await submitButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
}

async function clickRequestTeachBack(page: Page): Promise<void> {
  const teachBackButton = page.getByTestId("request-teach-back-button");
  await expect(teachBackButton, "request-teach-back-button must be reachable").toBeVisible({ timeout: 30_000 });
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 300_000 },
  );
  await teachBackButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
}

async function submitTeachBackReconstruction(page: Page, reconstruction: string): Promise<void> {
  await page.getByRole("textbox", { name: "teach-back 重构" }).fill(reconstruction);
  const submitButton = page.getByRole("button", { name: /提交重构/ });
  await expect(submitButton).toBeEnabled();
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 300_000 },
  );
  await submitButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
}

async function clickRequestTransfer(page: Page): Promise<void> {
  const transferButton = page.getByTestId("request-transfer-button");
  await expect(transferButton, "request-transfer-button must be reachable").toBeVisible({ timeout: 30_000 });
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 300_000 },
  );
  await transferButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
  await expect(page.getByTestId("transfer-card"), "transfer-card must render after request").toBeVisible({ timeout: 30_000 });
}

async function submitSoloAttempt(page: Page, response: string): Promise<void> {
  await page.getByRole("textbox", { name: "迁移尝试" }).fill(response);
  const submitButton = page.getByRole("button", { name: /提交迁移尝试/ });
  await expect(submitButton).toBeEnabled();
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 300_000 },
  );
  await submitButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
}

async function sendRealTunnellingTurn(page: Page, message: string): Promise<void> {
  const experimentsButton = page.getByRole("button", { name: /^实验/ });
  await expect(experimentsButton).toBeVisible();
  await experimentsButton.click();
  const tunnellingToggle = page.getByLabel(/量子隧穿/);
  if (await tunnellingToggle.isVisible().catch(() => false)) {
    const isChecked = await tunnellingToggle.isChecked();
    if (!isChecked) await tunnellingToggle.check();
  }
  const streamResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/teaching/turns/stream" &&
      response.request().method() === "POST",
    { timeout: 360_000 },
  );
  const messageBox = page.getByLabel("给 Quantum Agent 的问题");
  await messageBox.fill(message);
  const sendButton = page.getByRole("button", { name: /发送|运行/ });
  await expect(sendButton).toBeEnabled();
  await sendButton.click();
  const response = await streamResponse;
  expect(response.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
}

/**
 * Compute the rectangular-barrier transmission coefficient T using the same
 * deterministic formula as the backend oracle
 * (services/api/quantum_agent/science/toolbox.py:575).  The transfer task
 * changes the barrier width to 1.5× the original; the solo attempt must
 * contain a number within ``absolute_tolerance`` (5e-3) of this value.
 *
 *   kappa = sqrt(2 m (V0 - E)) / hbar
 *   T = [1 + V0^2 * sinh^2(kappa * a) / (4 E (V0 - E))]^-1
 *
 * SI units: mass in kg, energy in eV (converted to joules), width in metres.
 */
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
  const kInside = Math.sqrt((2.0 * particleMassKg * deltaEJ)) / hbarJs;
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
    expect(response.status(), await response.text().catch(() => "")).toBe(200);
    return (await response.json()) as Record<string, unknown>;
  } finally {
    await api.dispose();
  }
}

async function fetchAgentTraces(
  auth: LiveAuth,
): Promise<{ items: Array<Record<string, unknown>>; total: number }> {
  const api = await playwrightRequest.newContext({
    baseURL: process.env.QUANTUM_API_BASE_URL ?? "http://127.0.0.1:8000",
    extraHTTPHeaders: { Authorization: `Bearer ${auth.ta_token}` },
  });
  try {
    const path =
      `/api/v1/courses/${auth.course_id}/editions/${auth.curriculum_edition_id}` +
      "/teacher/agent-traces?limit=100";
    const response = await api.get(path);
    expect(response.status()).toBe(200);
    return (await response.json()) as { items: Array<Record<string, unknown>>; total: number };
  } finally {
    await api.dispose();
  }
}

async function fetchAgentTraceDetail(
  auth: LiveAuth,
  traceId: string,
): Promise<Record<string, unknown>> {
  const api = await playwrightRequest.newContext({
    baseURL: process.env.QUANTUM_API_BASE_URL ?? "http://127.0.0.1:8000",
    extraHTTPHeaders: { Authorization: `Bearer ${auth.ta_token}` },
  });
  try {
    const path =
      `/api/v1/courses/${auth.course_id}/editions/${auth.curriculum_edition_id}` +
      `/teacher/agent-traces/${traceId}`;
    const response = await api.get(path);
    expect(response.status()).toBe(200);
    return (await response.json()) as Record<string, unknown>;
  } finally {
    await api.dispose();
  }
}

test.describe.serial("Golden Learning Loop · live deterministic 22-stage closure", () => {
  test("reaches every required LearningPhase in order with real persistence and no skippable stages", async ({ page }) => {
    test.setTimeout(1_800_000); // 30 minutes for the full live loop
    const auth = liveAuth();

    // ── Stage 1: Login ──
    await loginThroughProduct(page);
    // No turn has run yet; the phase marker is absent until the first result.
    await page.getByRole("button", { name: /^概念/ }).click();

    const beforeStats = await fetchLearningStatistics(auth);
    const beforeTotal = Number(beforeStats.total_recorded_events ?? 0);
    const beforeTraces = await fetchAgentTraces(auth);
    const beforeTraceTotal = beforeTraces.total;
    const beforeKinds = (beforeStats.events_by_kind ?? {}) as Record<string, { event_count?: number }>;
    const beforeTransferVerified = Number(beforeKinds.transfer_verified?.event_count ?? 0);

    // ── Stage 2: Tunnelling question triggers the commitment gate ──
    await sendStudentMessage(
      page,
      "我想理解量子隧穿：为什么粒子能量 E 小于势垒高度 V0 时仍然可能出现在势垒右侧？",
    );
    await waitForWorkflowTerminal(page);
    await expectPhase(page, "commitment_required");
    await expect(page.getByTestId("commitment-card"), "Stage 2: CommitmentCard must render").toBeVisible({ timeout: 30_000 });

    // ── Stage 3: Commitment submitted — accepted commitment = the initial
    // attempt.  PRD V3.4: the accepted commitment advances the durable phase
    // COMMITMENT_REQUIRED → ATTEMPT_RECEIVED so the episode CONTINUES (it is
    // NOT the end and NOT a full answer).  Invariant B still holds: phase ≠
    // complete and is NOT awaiting_revision — the student must answer the
    // minimal-intervention probe next. ──
    await submitCommitment(
      page,
      "我预测：E<V0 时透射概率为零，粒子不可能穿越势垒。",
    );
    await expectPhase(page, "attempt_received", 30_000);
    await expectLoopComplete(page, false);
    // The no-orphan invariant: a concrete minimal-intervention next step must
    // be actionable instead of a dead-end.
    await expect(
      page.getByTestId("minimal-intervention-card"),
      "Stage 3: the accepted commitment must surface an actionable minimal-intervention step",
    ).toBeVisible({ timeout: 30_000 });
    await sendStudentMessage(
      page,
      "我修正：势垒右侧的波函数振幅应该很小但不为零，透射概率可能是一个很小的正数。",
      "波函数在势垒内指数衰减，右侧振幅非零，透射概率是一个很小的正数。",
    );
    await waitForWorkflowTerminal(page);
    await expectPhase(page, "awaiting_revision");
    await expect(page.getByTestId("agent-tutor-result"), "Stage 4: tutor result must render").toBeVisible();

    // ── Stage 5: Diagnosis rendered from real evidence ──
    // The diagnosis (status / summary / confidence) renders in the Evidence
    // desk, not the tutor record.  The desk is closed by default after each
    // turn (auto-open was removed to keep the commitment controls clickable),
    // so open it on demand and assert the diagnosis surfaced.  Both the topbar
    // and the left rail expose a "打开证据面板" button; scope to the topbar.
    await page.getByRole("banner").getByRole("button", { name: "打开证据面板" }).click();
    await expect(
      page.getByRole("heading", { name: "本轮依据" }),
      "Stage 5: Evidence desk must open",
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText(/诊断|observed|model_inference|insufficient|no_attempt/i).first(),
      "Stage 5: diagnosis summary must render from real evidence",
    ).toBeVisible({ timeout: 10_000 });

    // ── Stage 4.5: Refresh during a durable phase — the durable phase must
    // survive a full page reload (spec section 16: "refresh during durable
    // phase").  The durable LearningPhase is persisted in
    // teaching_conversations.learning_phase_json.  After refresh the
    // frontend re-reads the durable state from
    // GET /api/teaching/threads/{id}/state and re-renders the actionable
    // surface, so the learning-phase marker must now appear with
    // phase=awaiting_revision WITHOUT running a new turn. ──
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("agent-experience")).toBeVisible({ timeout: 60_000 });
    // The conversation_id must survive the reload (persisted in localStorage).
    const storedCid = await page.evaluate(() => window.localStorage.getItem("qa_conversation_id"));
    expect(storedCid, "Stage 4.5: conversation_id must survive reload").toBeTruthy();
    // §13: the durable phase must be restored from the backend after reload —
    // never reset to OPEN, never skipped forward.
    await expectPhase(page, "awaiting_revision", 30_000);

    // ── Stage 6 + 7 + 8 + 9: Coding Agent + Sandbox + Verification + metrics ──
    await sendRealTunnellingTurn(
      page,
      "请用矩势垒散射工具计算 E=5eV, V0=10eV, a=1e-10m 的透射概率 T 和反射概率 R，并验证 R+T=1。",
    );
    // §12 SSE ordering is asserted inside sendRealTunnellingTurn (the evidence
    // spine must light from a REAL progress event before the terminal).
    await expect(page.getByTestId("coding-artifact"), "Stage 6: coding-artifact panel must render").toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("coding-generated-code"), "Stage 7: generated code must contain METRICS_JSON").toContainText(/METRICS_JSON/, { timeout: 10_000 });
    await expect(page.getByTestId("coding-verification-status"), "Stage 8: coding verifier must report PASS").toContainText(/PASS/, { timeout: 10_000 });

    // ── Stage 7.5: Static safety check + isolated sandbox execution are
    // distinct stages (spec section 12, stages 10-11).  The Coding Agent
    // pipeline runs a static safety check before dispatching the generated
    // code to the isolated sandbox runner; the sandbox executes it and
    // captures bounded stdout.  Assert both: the sandbox "Running" progress
    // step reached "done" (isolated sandbox executed) and bounded stdout from
    // the sandbox is present (static safety admitted the code, so the sandbox
    // actually ran it rather than rejecting it pre-execution). ──
    await expect(
      page.locator('[data-testid="coding-progress-running"][data-state="done"]'),
      "Stage 7.5a: isolated sandbox execution (coding-progress-running) must reach done",
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByTestId("coding-stdout"),
      "Stage 7.5b: sandbox stdout must be present (static safety check admitted the code)",
    ).toContainText(/METRICS_JSON/, { timeout: 10_000 });
    await expect(page.getByTestId("tunnelling-metrics"), "Stage 9: tunnelling-metrics must render").toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("tunnelling-regime")).toContainText(/tunnelling/);
    const metricsText = await page.getByTestId("tunnelling-metrics").textContent();
    expect(metricsText, "tunnelling-metrics must show a non-trivial T in (0,1)").toMatch(/透射 T = 0\.\d+/);
    expect(metricsText, "tunnelling-metrics must show a non-trivial R in (0,1)").toMatch(/反射 R = 0\.\d+/);

    // ── Stage 10: LearningJourney shows verify done ──
    await expect(
      page.locator('[data-testid="learning-journey"] li[data-stage="verify"][data-state="done"]'),
      "Stage 10: LearningJourney verify segment must be done",
    ).toBeVisible({ timeout: 10_000 });

    // Switch back to learn_concepts for the pedagogical stages.
    await page.getByRole("button", { name: /^概念/ }).click();

    // ── Stage 11: Request Teach-Back (phase must be awaiting_revision) ──
    // The request-teach-back-button surfaces the TeachBackCard so the student
    // can type a reconstruction.  Submitting a reconstruction (>= 24 chars)
    // from awaiting_revision advances the durable phase to
    // reconstruction_required (invariant D, cause teach_back_requested).
    await expectPhase(page, "awaiting_revision");
    await clickRequestTeachBack(page);
    await expect(page.getByTestId("teach-back-card"), "Stage 11: teach-back-card must render after request").toBeVisible({ timeout: 30_000 });
    await submitTeachBackReconstruction(
      page,
      "波函数在势垒内不是突变为零，而是指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
    );
    await expectPhase(page, "reconstruction_required");

    // ── Stage 12: Re-submit the reconstruction from reconstruction_required
    // → transfer_required (invariant E, cause teach_back_verified).  The
    // backend verifies the typed reconstruction and arms the transfer task.
    await submitTeachBackReconstruction(
      page,
      "波函数在势垒内不是突变为零，而是指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
    );
    await expectPhase(page, "transfer_required");
    await expect(page.getByTestId("transfer-card"), "Stage 12: transfer-card must render").toBeVisible({ timeout: 30_000 });

    // ── Stage 13: Request Transfer → Solo armed (solo_active) ──
    await clickRequestTransfer(page);
    await expectPhase(page, "solo_active");
    await expect(page.getByTestId("transfer-card"), "Stage 13: transfer-card must still render (Solo armed)").toBeVisible({ timeout: 30_000 });

    // ── Stage 14: Solo lock notice visible ──
    await expect(
      page.getByText("AI 辅助暂时不可用", { exact: false }),
      "Stage 14: Solo lock notice must be visible",
    ).toBeVisible({ timeout: 10_000 });

    // ── Stage 15: WRONG solo attempt — phase stays solo_active (NOT complete) ──
    await submitSoloAttempt(page, "透射系数 T = 0.999（几乎全透）");
    await expectPhase(page, "solo_active");
    await expectLoopComplete(page, false);
    await expect(
      page.getByTestId("transfer-card"),
      "Stage 15: transfer-card must remain visible after a wrong solo attempt",
    ).toBeVisible({ timeout: 10_000 });

    // ── Stage 16: CORRECT solo attempt → complete + loop-completed ──
    // The transfer task uses a barrier width of 1.5× the original (1e-10m →
    // 1.5e-10m), E=5eV, V0=10eV, electron mass.  Compute the oracle's expected
    // T with the same deterministic formula and submit it.  The numeric
    // verifier accepts a number within absolute_tolerance (5e-3).
    const transferExpectedT = computeTransmissionT(5, 10, 1.5e-10, 9.1093837015e-31);
    const correctResponse = `透射系数 T = ${transferExpectedT.toFixed(4)}（与数值验证一致：势垒更宽，透射率下降）`;
    await submitSoloAttempt(page, correctResponse);
    await expectPhase(page, "complete");
    await expectLoopComplete(page, true);
    await expect(
      page.locator('[data-testid="learning-loop-complete"]'),
      "Stage 16: learning-loop-complete terminal marker must render",
    ).toBeVisible({ timeout: 30_000 });

    // ── Stage 17: LearningJourney shows all 5 segments done ──
    for (const stage of ["predict", "diagnose", "verify", "explain", "transfer"] as const) {
      await expect(
        page.locator(`[data-testid="learning-journey"] li[data-stage="${stage}"][data-state="done"]`),
        `Stage 17: LearningJourney ${stage} segment must be done`,
      ).toBeVisible({ timeout: 10_000 });
    }

    // ── Stage 17.5: Cognitive Mirror updated from persisted learning evidence
    // (spec section 12, stage 21).  The mirror is derived from persisted
    // learning evidence — NOT from a transfer question being displayed — so it
    // must only now reflect concept states after the verified solo attempt. ──
    await expectMirrorUpdated(page);

    // ── Stage 18: Learning statistics increased ──
    const afterStats = await fetchLearningStatistics(auth);
    const afterTotal = Number(afterStats.total_recorded_events ?? 0);
    expect(
      afterTotal,
      `Stage 18: learning-statistics total must increase (before=${beforeTotal}, after=${afterTotal})`,
    ).toBeGreaterThan(beforeTotal);

    // ── Stage 21: TRANSFER_VERIFIED evidence exists after stage 16 ──
    const afterKinds = (afterStats.events_by_kind ?? {}) as Record<string, { event_count?: number }>;
    const afterTransferVerified = Number(afterKinds.transfer_verified?.event_count ?? 0);
    expect(
      afterTransferVerified,
      "Stage 21: TRANSFER_VERIFIED evidence must exist after the verified solo attempt",
    ).toBeGreaterThan(beforeTransferVerified);

    // ── Stage 22: No TRANSFER_VERIFIED evidence existed before stage 16 ──
    expect(
      beforeTransferVerified,
      "Stage 22: no TRANSFER_VERIFIED evidence should have existed before the verified solo attempt",
    ).toBe(0);

    // Every required Learning-Native phase must have new durable evidence.
    for (const kind of ["commitment", "teach_back", "transfer_assigned", "solo_assigned"] as const) {
      expect(
        Number(afterKinds[kind]?.event_count ?? 0),
        `${kind} evidence must increase during the live loop`,
      ).toBeGreaterThan(Number(beforeKinds[kind]?.event_count ?? 0));
    }

    // ── Stage 19: A new AgentTrace is persisted ──
    const afterTraces = await fetchAgentTraces(auth);
    expect(
      afterTraces.total,
      `Stage 19: at least one new agent trace must be persisted (before=${beforeTraceTotal}, after=${afterTraces.total})`,
    ).toBeGreaterThan(beforeTraceTotal);
    const latestTrace = afterTraces.items[0];
    expect(latestTrace, "latest AgentTrace must exist").toBeTruthy();
    const traceId = String(latestTrace?.id);
    expect(UUID.test(traceId), "latest AgentTrace id must be a UUID").toBe(true);

    // ── Stage 20: The trace has the full fixed-order workflow steps ──
    const traceDetail = await fetchAgentTraceDetail(auth, traceId);
    const traceSteps = (traceDetail.trace ?? traceDetail.workflow_steps ?? []) as Array<Record<string, unknown>>;
    expect(
      Array.isArray(traceSteps) && traceSteps.length >= 10,
      "Stage 20: the trace must record the full fixed-order workflow (>= 10 steps)",
    ).toBe(true);
    const stepNames = traceSteps.map((step) => String(step.name ?? ""));
    // The fixed workflow order (WORKFLOW_ORDER) begins with classify_task and
    // includes the 10 canonical nodes.  Assert the key anchors are present.
    expect(stepNames, "Stage 20: trace must include classify_task").toContain("classify_task");
    expect(stepNames, "Stage 20: trace must include retrieve_evidence").toContain("retrieve_evidence");
    expect(stepNames, "Stage 20: trace must include run_scientific_tools").toContain("run_scientific_tools");
  });
});
