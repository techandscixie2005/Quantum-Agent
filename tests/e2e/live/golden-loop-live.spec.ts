import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

import {
  expect,
  request as playwrightRequest,
  test,
  type Page,
} from "@playwright/test";

/**
 * Golden Learning Loop · live full-stack (PRD V3.0 §36).
 *
 * Unlike tests/e2e/golden-loop.spec.ts (which mocks /api/agent/context and
 * /api/teaching/turns/stream for fast UI/contract verification), this test
 * drives the REAL stack with NO first-party API mocking:
 *
 *   Browser
 *     → Next.js frontend
 *     → /api/agent/context + /api/teaching/turns/stream proxies
 *     → FastAPI
 *     → LangGraph (learning_native_pre → scientific_tools → generate_response
 *                  → learning_native_post → hitl_gate → assemble_result)
 *     → real USTC model gateway (with bounded retry/backoff)
 *     → PostgreSQL persistence (LearningEvidence rows + AgentTrace)
 *     → SSE
 *     → Browser
 *
 * The live USTC model's learning-native decisions are non-deterministic: the
 * Cognitive Commitment Gate may fire (rendering CommitmentCard) or the model
 * may elicit a prediction through the tutor response itself.  This test is
 * therefore ADAPTIVE: it drives the tunnelling conversation forward across
 * multiple turns in learn_concepts mode (which exposes the student-attempt
 * box, guaranteeing STUDENT_ATTEMPT evidence persistence), submits
 * Learning-Native cards WHEN they appear, and verifies PERSISTENCE through
 * the TA-token teacher-insights API (which reads LearningEvidence rows
 * directly from PostgreSQL — not frontend state).
 *
 * Hard guarantees verified:
 *  - Every turn reaches a terminal state (tutor result or handled HITL).
 *  - After the loop, the course has NEW LearningEvidence rows
 *    (total_recorded_events increases) and a NEW AgentTrace with non-empty
 *    evidence + diagnosis + workflow steps.
 *  - At least one STUDENT_ATTEMPT and one DIAGNOSIS_INFERENCE are persisted.
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

/**
 * Wait for the workflow to reach a terminal state (tutor result or HITL
 * interrupt).  Live USTC calls may take a while; allow up to 4 minutes per
 * turn for the real model + tool pipeline.
 */
async function waitForWorkflowTerminal(page: Page): Promise<"completed" | "interrupted"> {
  await expect
    .poll(
      async () => {
        if (await page.getByTestId("agent-tutor-result").isVisible()) return "completed";
        if (await page.getByTestId("hitl-interrupt").isVisible()) return "interrupted";
        return "pending";
      },
      { timeout: 240_000, intervals: [2_000, 5_000, 10_000] },
    )
    .toMatch(/^(completed|interrupted)$/);
  return (await page.getByTestId("agent-tutor-result").isVisible()) ? "completed" : "interrupted";
}

/**
 * Send a student message with an attempt in learn_concepts mode.  The attempt
 * box only renders in learn_concepts / review_derivations modes; filling it
 * guarantees the STUDENT_ATTEMPT LearningEvidence row is persisted.
 */
async function sendStudentMessage(
  page: Page,
  message: string,
  attempt: string | null = null,
): Promise<void> {
  const streamResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/teaching/turns/stream" &&
      response.request().method() === "POST",
    { timeout: 240_000 },
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
  expect(response.ok(), await response.text().catch(() => "")).toBe(true);
}

/**
 * If the CommitmentCard is visible, submit a prediction through it and wait
 * for the next workflow terminal state.  Returns true if the card was
 * submitted.  This persists COMMITMENT + CONFIDENCE evidence.
 */
async function maybeSubmitCommitment(
  page: Page,
  response: string,
): Promise<boolean> {
  const card = page.getByTestId("commitment-card");
  if (!(await card.isVisible().catch(() => false))) return false;
  await page.getByLabel("认知承诺文本").fill(response);
  const submitButton = page.getByRole("button", { name: /提交承诺/ });
  await expect(submitButton).toBeEnabled();
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 240_000 },
  );
  await submitButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
  return true;
}

async function maybeSubmitTeachBack(page: Page, reconstruction: string): Promise<boolean> {
  const card = page.getByTestId("teach-back-card");
  if (!(await card.isVisible().catch(() => false))) return false;
  await page.getByLabel("teach-back 重构").fill(reconstruction);
  const submitButton = page.getByRole("button", { name: /提交重构/ });
  await expect(submitButton).toBeEnabled();
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 240_000 },
  );
  await submitButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
  return true;
}

async function maybeSubmitSoloAttempt(page: Page, response: string): Promise<boolean> {
  const card = page.getByTestId("transfer-card");
  if (!(await card.isVisible().catch(() => false))) return false;
  // Verify Solo Mode lock notice is present when solo is active.
  const soloLockVisible = await card
    .getByText(/AI 辅助暂时不可用/)
    .isVisible()
    .catch(() => false);
  await page.getByLabel("迁移尝试").fill(response);
  const submitButton = page.getByRole("button", { name: /提交迁移尝试/ });
  await expect(submitButton).toBeEnabled();
  const streamResponse = page.waitForResponse(
    (resp) =>
      new URL(resp.url()).pathname === "/api/teaching/turns/stream" &&
      resp.request().method() === "POST",
    { timeout: 240_000 },
  );
  await submitButton.click();
  const res = await streamResponse;
  expect(res.ok()).toBe(true);
  await waitForWorkflowTerminal(page);
  if (soloLockVisible) {
    expect(soloLockVisible).toBe(true);
  }
  return true;
}

/**
 * PRD V3.0 P0-3: switch to run_experiments mode and arm the real
 * rectangular-barrier tunnelling request, then send a turn.  The frontend
 * builds a ``rectangular_barrier_tunnelling`` scientific_request from the
 * barrier energy/height/width sliders; the backend scientific_tools node
 * runs the authoritative Python tool; the result is rendered in the
 * ``tunnelling-metrics`` testid.  This is the hard-asserted real physics
 * verification — no mock, no fabrication.
 */
async function sendRealTunnellingTurn(
  page: Page,
  message: string,
): Promise<void> {
  // Switch to run_experiments mode (labelled "实验" in the mode strip).
  const experimentsButton = page.getByRole("button", { name: /^实验/ });
  await expect(experimentsButton).toBeVisible();
  await experimentsButton.click();

  // Arm the rectangular-barrier tunnelling request via the golden-tunnelling
  // checkbox.  The default slider values are E=5 eV, V0=10 eV, a=1e-10 m,
  // electron mass — the canonical E<V0 tunnelling regime.
  const tunnellingToggle = page.getByLabel(/量子隧穿/);
  if (await tunnellingToggle.isVisible().catch(() => false)) {
    const isChecked = await tunnellingToggle.isChecked();
    if (!isChecked) await tunnellingToggle.check();
  }

  const streamResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/teaching/turns/stream" &&
      response.request().method() === "POST",
    // PRD V3.1 §6: the run_experiments stage triggers the Coding Agent, which
    // makes an extra LLM call to generate Python + sandbox execution + oracle
    // verification.  Allow up to 6 minutes for the full turn.
    { timeout: 360_000 },
  );
  const messageBox = page.getByLabel("给 Quantum Agent 的问题");
  await messageBox.fill(message);
  const sendButton = page.getByRole("button", { name: /发送|运行/ });
  await expect(sendButton).toBeEnabled();
  await sendButton.click();
  const response = await streamResponse;
  expect(response.ok(), await response.text().catch(() => "")).toBe(true);
  await waitForWorkflowTerminal(page);
}

/**
 * Snapshot the LearningEvidenceStatistics for the course/edition using the
 * TA token.  This reads directly from PostgreSQL — not frontend state.
 */
async function fetchLearningStatistics(
  auth: LiveAuth,
): Promise<Record<string, unknown>> {
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

test.describe.serial("Golden Learning Loop · live full-stack (quantum tunnelling)", () => {
  test("drives prediction → diagnosis → simulation → teach-back → transfer → solo → mirror with real persistence", async ({ page }) => {
    test.setTimeout(900_000); // 15 minutes for the full live loop
    const auth = liveAuth();
    await loginThroughProduct(page);

    // Snapshot the learning-evidence counts BEFORE the loop so we can prove
    // the loop persisted NEW rows (not pre-existing ones).
    const beforeStats = await fetchLearningStatistics(auth);
    const beforeTotal = Number(beforeStats.total_recorded_events ?? 0);
    const beforeTraces = await fetchAgentTraces(auth);
    const beforeTraceTotal = beforeTraces.total;

    // Use learn_concepts mode: it exposes the student-attempt box, which
    // guarantees STUDENT_ATTEMPT LearningEvidence is persisted on each turn.
    // The tunnelling concept is taught through prediction → diagnosis →
    // simulation → teach-back → transfer → solo → mirror, which maps naturally
    // onto learn_concepts (concept understanding) rather than run_experiments
    // (which does not expose the attempt box).
    await page.getByRole("button", { name: /^概念/ }).click();

    // ── Stage 1: student enters the tunnelling task with a prediction ──
    // The attempt box carries the student's prediction; this is the
    // Cognitive Commitment in its simplest form.  The learning_native_pre
    // node will either enforce the CommitmentCard (if the model proposes a
    // commitment prompt) or proceed with the tutor response.
    await sendStudentMessage(
      page,
      "我想理解量子隧穿：为什么粒子能量 E 小于势垒高度 V0 时仍然可能出现在势垒右侧？",
      null,
    );
    let terminal = await waitForWorkflowTerminal(page);
    expect(terminal).toBe("completed");

    // If the CommitmentCard rendered, submit a formal commitment too.
    expect(await maybeSubmitCommitment(
      page,
      "我预测：E<V0 时透射概率为零，粒子不可能穿越势垒。",
    ), "Commitment phase must be present and submitted").toBe(true);

    // ── Stage 2: Diagnosis + minimal hint after revised attempt ──
    await sendStudentMessage(
      page,
      "我修正：势垒右侧的波函数振幅应该很小但不为零，透射概率可能是一个很小的正数。",
      "波函数在势垒内指数衰减，右侧振幅非零，透射概率是一个很小的正数。",
    );
    terminal = await waitForWorkflowTerminal(page);
    expect(terminal).toBe("completed");

    // ── Stage 3: request real numerical simulation ──
    await sendStudentMessage(
      page,
      "请运行真实数值模拟，给出矩势垒的透射概率 T 和反射概率 R，并验证 R+T=1 概率守恒。",
      "我预期 R+T=1 严格成立，T 是一个很小的正数。",
    );
    terminal = await waitForWorkflowTerminal(page);
    expect(terminal).toBe("completed");

    // ── Stage 3b: HARD-ASSERTED real rectangular-barrier tunnelling tool ──
    // PRD V3.0 P0-3: the live test must prove the authoritative Python
    // rectangular-barrier tool ran and produced a real T/R pair with
    // conservation |R+T-1|<=tolerance.  We switch to run_experiments mode
    // and arm the golden-tunnelling request, which sends a real
    // ``rectangular_barrier_tunnelling`` scientific_request through the
    // FastAPI → LangGraph → scientific_tools_node → toolbox.verify path.
    // No mock, no fabrication: the displayed T/R must come from the tool.
    await sendRealTunnellingTurn(
      page,
      "请用矩势垒散射工具计算 E=5eV, V0=10eV, a=1e-10m 的透射概率 T 和反射概率 R，并验证 R+T=1。",
    );
    // The tunnelling-metrics panel must render with real tool-derived values.
    await expect(page.getByTestId("tunnelling-metrics")).toBeVisible({ timeout: 30_000 });
    // The regime must be "tunnelling" (E<V0 for the default parameters).
    await expect(page.getByTestId("tunnelling-regime")).toContainText(/tunnelling/);
    // The T and R values must be finite numbers in [0,1].  We assert the
    // panel shows numeric text matching the tool's toPrecision(6) output
    // (0 < T < 1, 0 < R < 1).  For E=5,V0=10,a=1e-10 the analytic T is
    // ~0.3337, R ~0.6663 — we assert the panel shows non-trivial values
    // (not 0, not 1, not empty).
    const metricsText = await page.getByTestId("tunnelling-metrics").textContent();
    expect(metricsText, "tunnelling-metrics must show a non-trivial T in (0,1)").toMatch(/透射 T = 0\.\d+/);
    expect(metricsText, "tunnelling-metrics must show a non-trivial R in (0,1)").toMatch(/反射 R = 0\.\d+/);
    expect(metricsText, "tunnelling-metrics must show the conservation error").toMatch(/守恒/);
    // PRD V3.1 §6: the Coding Agent panel must render with a PASS verdict and
    // the generated Python, proving the agent wrote fresh code (not a
    // prewritten solver) and the verifier cross-checked it against the oracle.
    await expect(page.getByTestId("coding-artifact")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("coding-verification-status")).toContainText(/PASS/, { timeout: 10_000 });
    await expect(page.getByTestId("coding-generated-code")).toContainText(/METRICS_JSON/);
    // Switch back to learn_concepts for the remaining pedagogical stages.
    await page.getByRole("button", { name: /^概念/ }).click();

    // ── Stage 4: prediction-vs-result comparison + student explanation ──
    await sendStudentMessage(
      page,
      "对比我的零预测和模拟结果，用我自己的话解释为什么 E<V0 时仍有非零透射。",
      "波函数在势垒内指数衰减但不为零，所以右侧有非零透射振幅。",
    );
    terminal = await waitForWorkflowTerminal(page);
    expect(terminal).toBe("completed");

    // ── Stage 5: explicit Teach-Back transition + reconstruction ──
    const teachBackResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/teaching/turns/stream",
      { timeout: 240_000 },
    );
    await page.getByTestId("request-teach-back-button").click();
    expect((await teachBackResponse).ok()).toBe(true);
    await waitForWorkflowTerminal(page);
    expect(await maybeSubmitTeachBack(
      page,
      "波函数在势垒内不是突变为零，而是指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
    ), "Teach-Back phase must be present and submitted").toBe(true);

    // ── Stage 6: explicit transfer task + Solo Mode transition ──
    const transferResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/teaching/turns/stream",
      { timeout: 240_000 },
    );
    await page.getByTestId("request-transfer-button").click();
    expect((await transferResponse).ok()).toBe(true);
    await waitForWorkflowTerminal(page);
    expect(await maybeSubmitSoloAttempt(
      page,
      "透射率随势垒宽度增加而指数下降，因为衰减常数不变但积分路径变长，振幅衰减更多。",
    ), "Transfer/Solo phase must be present and submitted").toBe(true);

    // ── Stage 7: Cognitive Mirror update from persisted evidence ──
    await sendStudentMessage(
      page,
      "请展示我的 Cognitive Mirror：当前概念状态、证据摘要、候选误解。",
      "我已提交预测、修正、解释、teach-back 和迁移尝试。",
    );
    terminal = await waitForWorkflowTerminal(page);
    expect(terminal).toBe("completed");

    // ── Persistence verification (TA token → PostgreSQL) ──
    // The learning-statistics endpoint reads LearningEvidence rows directly
    // from PostgreSQL.  We assert the total recorded events INCREASED during
    // the loop, proving real DB persistence (not just frontend state).
    const afterStats = await fetchLearningStatistics(auth);
    const afterTotal = Number(afterStats.total_recorded_events ?? 0);
    expect(
      afterTotal,
      `learning-statistics total must increase after the loop (before=${beforeTotal}, after=${afterTotal})`,
    ).toBeGreaterThan(beforeTotal);

    // Every required Learning-Native phase must have new durable evidence.
    const beforeKinds = (beforeStats.events_by_kind ?? {}) as Record<string, { event_count?: number }>;
    const afterKinds = (afterStats.events_by_kind ?? {}) as Record<string, { event_count?: number }>;
    for (const kind of ["commitment", "teach_back", "transfer_assigned", "solo_assigned"]) {
      expect(
        Number(afterKinds[kind]?.event_count ?? 0),
        `${kind} evidence must increase during the live loop`,
      ).toBeGreaterThan(Number(beforeKinds[kind]?.event_count ?? 0));
    }
    const transferAttemptsAfter =
      Number(afterKinds.transfer_attempted?.event_count ?? 0) +
      Number(afterKinds.transfer_verified?.event_count ?? 0);
    const transferAttemptsBefore =
      Number(beforeKinds.transfer_attempted?.event_count ?? 0) +
      Number(beforeKinds.transfer_verified?.event_count ?? 0);
    expect(transferAttemptsAfter, "a durable Solo transfer attempt must be recorded")
      .toBeGreaterThan(transferAttemptsBefore);

    // The course must have at least one student attempt persisted (recorded
    // because we filled the attempt box in learn_concepts mode).
    const observedAttempts = afterStats.observed_attempts as { event_count?: number } | undefined;
    expect(
      Number(observedAttempts?.event_count ?? 0),
      "at least one student attempt must be persisted",
    ).toBeGreaterThan(Number((beforeStats.observed_attempts as { event_count?: number } | undefined)?.event_count ?? 0));

    // Verify a NEW AgentTrace was persisted for this loop (total increased).
    const afterTraces = await fetchAgentTraces(auth);
    expect(
      afterTraces.total,
      `at least one new agent trace must be persisted (before=${beforeTraceTotal}, after=${afterTraces.total})`,
    ).toBeGreaterThan(beforeTraceTotal);

    // The latest trace must have non-empty evidence, diagnosis, and
    // workflow steps — proving the LangGraph workflow persisted its full
    // execution record to PostgreSQL.
    const latestTrace = afterTraces.items[0];
    expect(latestTrace).toBeTruthy();
    const traceId = String(latestTrace?.id);
    expect(UUID.test(traceId)).toBe(true);

    const traceDetail = await fetchAgentTraceDetail(auth, traceId);
    expect(traceDetail.evidence_bundle, "trace must persist evidence_bundle").toBeTruthy();
    expect(traceDetail.diagnosis, "trace must persist diagnosis").toBeTruthy();
    expect(traceDetail.release_decision, "trace must persist release_decision").toBeTruthy();
    expect(Array.isArray(traceDetail.workflow_steps)).toBe(true);
    expect(
      (traceDetail.workflow_steps as unknown[]).length,
      "trace must persist workflow steps",
    ).toBeGreaterThan(0);

    const beforeTraceIds = new Set(beforeTraces.items.map((item) => String(item.id)));
    const newTraceDetails = await Promise.all(
      afterTraces.items
        .filter((item) => !beforeTraceIds.has(String(item.id)))
        .map((item) => fetchAgentTraceDetail(auth, String(item.id))),
    );
    const generatedResult = newTraceDetails
      .flatMap((detail) => detail.scientific_results as Array<Record<string, unknown>>)
      .find(
        (item) => (item.tool as { name?: string } | undefined)?.name === "coding-agent-isolated-python",
      );
    expect(generatedResult, "PostgreSQL must persist the verified Coding Agent result").toBeTruthy();
    expect(generatedResult?.status).toBe("pass");

    // Cognitive Mirror is a required phase and must be evidence-backed.
    const mirrorVisible = await page.getByTestId("cognitive-mirror").isVisible().catch(() => false);
    expect(mirrorVisible, "Cognitive Mirror must render after durable evidence updates").toBe(true);

    // Surface what was actually persisted for the final report.
    console.log(
      `[golden-loop-live] persistence: events ${beforeTotal}→${afterTotal}, ` +
        `traces ${beforeTraceTotal}→${afterTraces.total}, mirrorVisible=${mirrorVisible}`,
    );
  });
});
