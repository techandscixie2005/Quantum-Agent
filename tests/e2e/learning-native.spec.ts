import { test, expect, type Page } from "@playwright/test";

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";
const TURN_ID = "44444444-4444-4444-8444-444444444444";
const EVIDENCE_ID = "55555555-5555-4555-8555-555555555555";

const STUDENT_CONTEXT = {
  user_id: "66666666-6666-4666-8666-666666666666",
  display_name: "学 quantum",
  courses: [
    {
      course_id: COURSE_ID,
      course_code: "PHYS-301",
      course_title: "量子物理",
      institution: "USTC",
      role: "student",
      curriculum_edition_id: EDITION_ID,
      edition_title: "2026 秋",
      academic_year: "2026",
      term: "秋",
      chapters: [
        {
          id: "77777777-7777-4777-8777-777777777777",
          ordinal: 1,
          title: "量子隧穿",
          canonical_path: "Ch. 2 / Tunneling",
        },
      ],
    },
  ],
};

function baseResult(overrides: Record<string, unknown> = {}) {
  return {
    conversation_id: CONVERSATION_ID,
    turn_id: TURN_ID,
    workflow_version: "teaching-state-machine/1.0.0",
    interpretation: {
      task_kind: "concept_question",
      relevant_concepts: ["量子隧穿"],
      needs_scientific_verification: false,
      confidence: 0.9,
    },
    diagnosis: {
      status: "model_inference",
      summary: "学生可能用经典直觉判断隧穿不可能。",
      likely_misconception: "认为 E<V0 时粒子完全不可能出现在势垒右侧。",
      observation_basis: ["student_message", "student_attempt"],
      target_concepts: ["量子隧穿"],
      first_error: null,
      misconception_candidates: [
        { statement: "经典粒子不能穿越势垒", confidence: 0.7 },
      ],
      missing_prerequisites: [],
      progress_state: "started",
      confidence: 0.6,
      verification_needed: false,
      reason: "Diagnosis derived from the student message and attempt.",
    },
    policy: {
      policy_id: null,
      source: "safe_default",
      mode: "run_experiments",
      allow_full_solution: false,
      minimum_attempts_for_scaffold: 0,
      minimum_attempts_for_full_solution: 3,
      max_hint_level: 2,
    },
    release: {
      action: "ask_diagnostic_question",
      release_level: "question_only",
      attempts_observed: 0,
      reason_code: "first_attempt_question_only",
    },
    evidence_packet: {
      id: "88888888-8888-4888-8888-888888888888",
      course_id: COURSE_ID,
      curriculum_edition_id: EDITION_ID,
      query: "tunneling",
      created_at: "2026-08-26T00:00:00Z",
      coverage: "sufficient",
      evidence: [
        {
          evidence_id: EVIDENCE_ID,
          chunk_id: "99999999-9999-4999-8999-999999999999",
          document_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          document_version_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          document_title: "Quantum Physics",
          document_version: 1,
          source_file_name: "quantum.pdf",
          source_file_sha256: "a".repeat(64),
          source_chunk_sha256: "b".repeat(64),
          evidence_sha256: "c".repeat(64),
          curriculum_edition_id: EDITION_ID,
          chapter: "Ch. 2",
          section_path: ["Tunneling"],
          locator: {
            locator_type: "pdf_page",
            physical_page: 42,
            printed_page_label: null,
            slide_number: null,
            paragraph_start: null,
            paragraph_end: null,
            sheet_name: null,
            row_start: null,
            row_end: null,
            line_start: null,
            line_end: null,
          },
          source_chunk: "Tunneling through a rectangular barrier.",
          evidence_snippet: "Tunneling through a rectangular barrier.",
          kind: "course_material",
          authority_priority: 10,
          contributions: [
            {
              channel: "postgres_full_text",
              rank: 1,
              raw_score: 1.0,
              fused_score: 1.0,
            },
          ],
        },
      ],
      graph_nodes: [
        {
          id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          node_type: "Concept",
          name: "量子隧穿",
          aliases: ["tunneling"],
        },
      ],
      graph_edges: [],
      degraded_channels: [],
      warnings: [],
    },
    response: {
      orientation: "先做一个判断。",
      claims: [],
      next_question: "你预测透射概率会是多少？",
      status: "grounded",
      limitations: [],
    },
    validation: {
      passed: true,
      citation_ids_valid: true,
      literal_course_claims_valid: true,
      scientific_references_valid: true,
      warnings: [],
    },
    scientific_results: [],
    trace: [
      "classify_task",
      "identify_concepts",
      "retrieve_evidence",
      "diagnose_progress",
      "choose_teaching_action",
      "apply_answer_policy",
      "run_scientific_tools",
      "generate_response",
      "validate_response",
      "record_learning_evidence",
    ].map((name) => ({
      name,
      status: name === "run_scientific_tools" ? "skipped" : "completed",
      detail: `${name} done`,
    })),
    learning_native: null,
    turn_completed: true,
    learning_loop_completed: false,
    ...overrides,
  };
}

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

async function interceptAgentApis(page: Page, result: Record<string, unknown>) {
  await page.route("**/api/agent/context", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STUDENT_CONTEXT) });
  });
  await page.route("**/api/teaching/turns/stream**", async (route) => {
    // Read the request body to echo the mode the frontend selected, so the
    // teaching-result scope check (policy.mode === request.mode) passes.
    let requestMode = "learn_concepts";
    try {
      const requestBody = route.request().postDataJSON() as { mode?: string } | null;
      if (requestBody?.mode) requestMode = requestBody.mode;
    } catch {
      // ignore parse errors; fall back to learn_concepts
    }
    const adaptedResult = {
      ...result,
      policy: { ...(result.policy as Record<string, unknown>), mode: requestMode },
      release: { ...(result.release as Record<string, unknown>) },
    };
    const body = sse("workflow.started", { workflow_version: "teaching-state-machine/1.0.0" }) +
      sse("workflow.completed", adaptedResult);
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-store" },
      body,
    });
  });
}

async function submitAndAssertCard(
  page: Page,
  message: string,
  cardTestid: string,
  assertExtra: () => Promise<void>,
) {
  await page.goto("/agent", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("agent-experience")).toBeVisible({ timeout: 20000 });

  // Wait for the teaching-stream response (mocked) after clicking send.
  const streamResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/teaching/turns/stream" &&
      response.request().method() === "POST",
    { timeout: 20000 },
  );

  const messageBox = page.getByLabel("给 Quantum Agent 的问题");
  await messageBox.fill(message);
  const sendButton = page.getByRole("button", { name: /发送/ });
  await expect(sendButton).toBeEnabled();
  await sendButton.click();

  const response = await streamResponse;
  expect(response.ok(), `teaching stream returned ${response.status()}`).toBe(true);

  await expect(page.getByTestId(cardTestid)).toBeVisible({ timeout: 15000 });
  await assertExtra();
}

test.describe("Golden Learning Loop · /agent", () => {
  test("renders the Cognitive Commitment gate before explanation", async ({ page }) => {
    const result = baseResult({
      learning_native: {
        commitment: {
          gate_decision: "attempt_required",
          attempt_required: true,
          attempt_type: "prediction",
          candidate_prompt: "你的预测是什么？增加势垒宽度，透射概率如何变化？",
          reason_summary: "先预测再解释。",
          accepted: false,
          confidence: null,
        },
        learning_action: "ask_commitment",
        teach_back: null,
        transfer: null,
        solo: null,
        cognitive_mirror: null,
        evidence_persisted: [],
        phase: "commitment_required",
        current_stage: "predict",
        completed_stages: [],
        required_action: "commitment",
        loop_required: true,
      },
    });
    await interceptAgentApis(page, result);
    await submitAndAssertCard(
      page,
      "为什么 E<V0 时仍可能透射？",
      "commitment-card",
      async () => {
        await expect(page.getByText(/增加势垒宽度/)).toBeVisible();
      },
    );
  });

  test("renders the Cognitive Mirror without a personality profile", async ({ page }) => {
    const result = baseResult({
      learning_native: {
        commitment: null,
        learning_action: null,
        teach_back: null,
        transfer: null,
        solo: null,
        cognitive_mirror: {
          current_concept_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          concept_states: [
            {
              concept_candidate_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
              label: "developing",
              evidence_summary: ["学生提交了预测。"],
              confidence_history: [[0.8, true]],
              calibration_gap: null,
              unaided_retrieval: null,
              transfer_evidence: [],
              hint_dependency: [],
              misconception_candidates: [],
              last_demonstrated_at: null,
            },
          ],
          summary: "本轮诊断状态：model_inference。镜像是观察记录，不是掌握度分数。",
          no_personality_profile: true,
        },
        evidence_persisted: [],
        phase: "awaiting_revision",
        current_stage: "explain",
        completed_stages: ["predict", "diagnose"],
        required_action: "revision",
        loop_required: true,
      },
    });
    await interceptAgentApis(page, result);
    await submitAndAssertCard(
      page,
      "继续讨论隧穿。",
      "cognitive-mirror",
      async () => {
        await expect(page.getByText(/不进行人格/)).toBeVisible();
      },
    );
  });

  test("renders Solo Mode transfer task with assistance lock", async ({ page }) => {
    const transfer = {
      task_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      transfer_type: "representation",
      prompt: "画出不同势垒宽度下的透射率曲线并解释趋势。",
      source_concept_ids: [],
      key_parameters: ["barrier_width"],
      expected_observable: "",
      verifiable: false,
    };
    const result = baseResult({
      learning_native: {
        commitment: null,
        learning_action: "enter_solo",
        teach_back: null,
        transfer,
        solo: {
          status: "active",
          active_transfer: transfer,
          started_at: "2026-08-26T00:00:00Z",
          assistance_locked: true,
          unlock_reason: "",
        },
        cognitive_mirror: null,
        evidence_persisted: ["transfer"],
        phase: "solo_active",
        current_stage: "solo",
        completed_stages: ["predict", "diagnose", "explore", "verify", "explain", "teach_back", "transfer"],
        required_action: "solo_attempt",
        loop_required: true,
      },
    });
    await interceptAgentApis(page, result);
    await submitAndAssertCard(
      page,
      "我想挑战一个迁移任务。",
      "transfer-card",
      async () => {
        await expect(page.getByText(/AI 辅助暂时不可用/)).toBeVisible();
        await page.getByLabel("迁移尝试", { exact: true }).fill("Synthetic independent answer");
        const submission = page.waitForRequest(request => request.url().includes("/api/teaching/turns/stream")
          && request.method() === "POST");
        await page.getByRole("button", { name: "提交迁移尝试", exact: true }).click();
        expect((await submission).postDataJSON().learning_native.solo_attempt.transfer_task_id).toBe(transfer.task_id);
      },
    );
  });
});

test("minimal intervention sends the student's actual reply", async ({ page }) => {
  await interceptAgentApis(page, baseResult({
    learning_native: {
      commitment: null, learning_action: "give_hint", teach_back: null,
      transfer: null, solo: null, cognitive_mirror: null, evidence_persisted: [],
      phase: "attempt_received", current_stage: "explain", completed_stages: ["predict"],
      required_action: "revision", loop_required: true,
      minimal_intervention_prompt: "二阶导数与波函数有什么关系？",
    },
  }));
  await submitAndAssertCard(page, "为什么会隧穿？", "minimal-intervention-card", async () => {
    const submit = page.getByRole("button", { name: "提交下一步", exact: true });
    await expect(submit).toBeDisabled();
    const response = "我仍不知道负号怎么处理，请只提示移项这一步。";
    await page.getByLabel("最小干预回复").fill(response);
    const sent = page.waitForRequest(request => request.url().includes("/api/teaching/turns/stream")
      && request.method() === "POST");
    await submit.click();
    const payload = (await sent).postDataJSON();
    expect(payload.message).toBe(response);
    expect(payload.student_attempt).toBe(response);
  });
});

test("completed teach-back feedback does not hide the assigned transfer task", async ({ page }) => {
  await interceptAgentApis(page, baseResult({ learning_native: {
    commitment: null, learning_action: "give_hint",
    teach_back: { covered_relations: [], missing_relations: [], contradictions: [],
      unsupported_claims: [], recommended_probe: "", verified: false, is_model_inference: true },
    transfer: { task_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", transfer_type: "parameter",
      prompt: "保持能量与高度，宽度改为 0.15 nm，求透射率并说明理由。",
      source_concept_ids: [], key_parameters: ["a=0.15 nm"],
      expected_observable: "transmission coefficient T", verifiable: true },
    solo: null, cognitive_mirror: null, evidence_persisted: ["teach_back"],
    phase: "transfer_required", current_stage: "transfer",
    completed_stages: ["predict", "diagnose", "explore", "verify", "explain", "teach_back"],
    required_action: "none", loop_required: true,
  }}));
  await submitAndAssertCard(page, "提交我的回讲。", "transfer-card", async () => {
    await expect(page.getByLabel("迁移尝试")).toBeVisible();
    await expect(page.getByTestId("teach-back-card")).toHaveCount(0);
  });
});

// Explicit API mock: presentation regression, not live model acceptance.
test("model degradation is visible and retains the student's input", async ({ page }) => {
  const result = baseResult({
    response: {
      orientation: "只显示当前可用的课程材料。",
      claims: [], next_question: "请稍后重试。", status: "model_degraded",
      limitations: ["模型生成不可用或未通过证据校验；仅展示课程材料原文。"],
    },
  });
  await interceptAgentApis(page, result);
  await submitAndAssertCard(page, "请帮我连接这两步推导", "model-degraded-notice", async () => {
    await expect(page.getByTestId("model-degraded-notice")).toContainText("未返回的诊断、推导桥不计为完成");
    await expect(page.getByLabel("给 Quantum Agent 的问题")).toHaveValue("请帮我连接这两步推导");
    await expect(page.getByTestId("learning-loop-complete")).toHaveCount(0);
    await expect(page.getByTestId("derivation-bridge")).toHaveCount(0);
  });
});

// Scripted browser regressions. These use synthetic API fixtures, not teachers,
// students, live model results, or measured classroom learning outcomes.
test("a delayed restore cannot reopen an episode after starting a new record", async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let requested!: () => void;
  const started = new Promise<void>(resolve => { requested = resolve; });
  await page.addInitScript(({ course, edition, conversation }) => {
    localStorage.setItem("qa_course_key", `${course}:${edition}`);
    localStorage.setItem("qa_conversation_id", conversation);
  }, { course: COURSE_ID, edition: EDITION_ID, conversation: CONVERSATION_ID });
  await interceptAgentApis(page, baseResult());
  await page.route("**/api/teaching/threads/*/interrupt?**", route => route.fulfill({ status: 404, body: "{}" }));
  await page.route("**/api/teaching/threads/*/state?**", async route => {
    requested(); await held;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      conversation_id: CONVERSATION_ID, mode: "learn_concepts", result: baseResult({ response: {
        orientation: "STALE_RESTORED_ANSWER", claims: [], next_question: "STALE_PROBE", status: "grounded", limitations: [],
      } }),
    }) }).catch(() => undefined);
  });
  await page.goto("/agent");
  await started;
  await page.getByRole("button", { name: "新建学习记录", exact: true }).click();
  release();
  await expect(page.getByText("STALE_RESTORED_ANSWER", { exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("qa_conversation_id"))).toBeNull();
});

test("late teaching response cannot populate a different selected course", async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const secondCourse = { ...STUDENT_CONTEXT.courses[0], course_id: "abababab-abab-4bab-8bab-abababababab", edition_title: "隔离课程 B" };
  await page.route("**/api/agent/context", route => route.fulfill({ contentType: "application/json",
    body: JSON.stringify({ ...STUDENT_CONTEXT, courses: [...STUDENT_CONTEXT.courses, secondCourse] }) }));
  await page.route("**/api/teaching/turns/stream**", async route => {
    const requestMode = route.request().postDataJSON().mode;
    await held;
    await route.fulfill({ contentType: "text/event-stream", body: sse("workflow.completed", baseResult({
      policy: { ...baseResult().policy, mode: requestMode }, response: {
        orientation: "WRONG_COURSE_ANSWER", claims: [], next_question: "WRONG_COURSE_PROBE", status: "grounded", limitations: [],
      },
    })) });
  });
  await page.goto("/agent");
  await page.getByLabel("给 Quantum Agent 的问题").fill("Synthetic delayed question");
  const sent = page.waitForRequest("**/api/teaching/turns/stream**");
  await page.getByRole("button", { name: /发送 \/ 运行/ }).click();
  await sent;
  await page.getByRole("button", { name: "打开命令面板", exact: true }).click();
  await page.getByRole("button", { name: /隔离课程 B/ }).click();
  release();
  await expect(page.getByText("隔离课程 B", { exact: true })).toBeVisible();
  await expect(page.getByLabel("给 Quantum Agent 的问题")).toHaveValue("");
  await expect(page.getByText("WRONG_COURSE_ANSWER", { exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("qa_conversation_id"))).toBeNull();
});

test("retry after a lost first response preserves the original client request ID", async ({ page }) => {
  const ids: string[] = [];
  await page.route("**/api/agent/context", route => route.fulfill({ contentType: "application/json", body: JSON.stringify(STUDENT_CONTEXT) }));
  await page.route("**/api/teaching/turns/stream**", async route => {
    const input = route.request().postDataJSON();
    ids.push(input.client_request_id);
    if (ids.length === 1) { await route.abort("failed"); return; }
    await route.fulfill({ contentType: "text/event-stream", body: sse("workflow.completed", baseResult({ policy: { ...baseResult().policy, mode: input.mode } })) });
  });
  await page.goto("/agent");
  await page.getByLabel("给 Quantum Agent 的问题").fill("Synthetic retry question");
  await page.getByRole("button", { name: /发送 \/ 运行/ }).click();
  await page.getByRole("button", { name: "重试同一次提交", exact: true }).click();
  await expect.poll(() => ids.length).toBe(2);
  expect(ids[1]).toBe(ids[0]);
  expect(ids[0]).toMatch(/^[a-f0-9-]{36}$/);
});

test("teacher review requires reasons and sends the selected next teaching action", async ({ page }) => {
  const result = baseResult();
  const traceId = "ffffffff-ffff-4fff-8fff-ffffffffffff";
  const summary = { id: traceId, teaching_turn_id: TURN_ID, conversation_id: CONVERSATION_ID,
    student_user_id: STUDENT_CONTEXT.user_id, mode: "run_experiments", sequence_number: 1,
    task_kind: "concept_question", teaching_action: "ask_diagnostic_question", release_level: "question_only",
    turn_status: "completed", workflow_version: result.workflow_version, model_gateway_status: "completed",
    citation_validation_status: "passed", created_at: "2026-10-19T00:00:00Z", completed_at: "2026-10-19T00:00:01Z" };
  await page.route("**/api/teacher/traces?**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    course_id: COURSE_ID, curriculum_edition_id: EDITION_ID, items: [summary], total: 1, limit: 25, offset: 0, has_more: false,
  }) }));
  await page.route(`**/api/teacher/traces/${traceId}?**`, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    ...summary, user_message: "Synthetic question", student_attempt: "Synthetic initial answer",
    workflow_steps: result.trace, policy_snapshot: result.policy, evidence_packet: result.evidence_packet,
    evidence_bundle: null, diagnosis: result.diagnosis, release_decision: result.release,
    response: result.response, scientific_results: [], validation: result.validation, hitl_events: [], failure_code: null,
  }) }));
  await page.route("**/api/teacher/course-packages?**", route => route.fulfill({ contentType: "application/json", body: "[]" }));
  let saved: Record<string, unknown> | null = null;
  await page.route("**/api/teacher/conversations/*/reviews?**", async route => {
    if (route.request().method() === "POST") saved = route.request().postDataJSON();
    const record = saved ? {
      ...saved, review_id: traceId, conversation_id: CONVERSATION_ID, reviewer_user_id: STUDENT_CONTEXT.user_id, created_at: "2026-10-19T00:00:02Z",
    } : null;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().method() === "POST" ? record : record ? [record] : []) });
  });
  await page.goto(`/teacher/traces?course_id=${COURSE_ID}&curriculum_edition_id=${EDITION_ID}`);
  const panel = page.getByTestId("classroom-review");
  await expect(panel).toBeVisible();
  const submit = panel.getByRole("button", { name: "记录教师决定", exact: true });
  await expect(submit).toBeDisabled();
  await panel.getByLabel("教师判断依据", { exact: true }).fill("Synthetic review: the boundary condition was omitted.");
  await panel.getByLabel("后续教学动作", { exact: true }).selectOption("revisit_prerequisite");
  await panel.getByLabel("下一轮具体追问", { exact: true }).fill("State which derivative is continuous and why.");
  await submit.click();
  await expect(panel.getByRole("status")).toContainText("教师决定已记录");
  expect(saved).toMatchObject({ source_turn_id: TURN_ID, follow_up: "revisit_prerequisite",
    reason: "Synthetic review: the boundary condition was omitted.", probe: "State which derivative is continuous and why." });
  await panel.getByText("2026-10-19T00:00:02Z · needs_follow_up", { exact: true }).click();
  await expect(panel.getByText("Synthetic review: the boundary condition was omitted.", { exact: true })).toBeVisible();
  if (process.env.QA_CAPTURE_CLASSROOM_SCREENSHOT === "1") {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ fullPage: true, path: "docs/implementation/evidence/classroom-20261019/teacher-review-scripted.png" });
  }
});

test("failed request cannot be retried into a new record or a different course", async ({ page }) => {
  const second = { ...STUDENT_CONTEXT.courses[0], course_id: "abababab-abab-4bab-8bab-abababababab", edition_title: "隔离课程 B" };
  await page.route("**/api/agent/context", route => route.fulfill({ contentType: "application/json",
    body: JSON.stringify({ ...STUDENT_CONTEXT, courses: [...STUDENT_CONTEXT.courses, second] }) }));
  let calls = 0;
  await page.route("**/api/teaching/turns/stream**", async route => { calls += 1; await route.abort("failed"); });
  await page.goto("/agent");
  await page.getByLabel("给 Quantum Agent 的问题").fill("Synthetic private first-course answer");
  await page.getByRole("button", { name: /发送 \/ 运行/ }).click();
  await expect(page.getByRole("button", { name: "重试同一次提交" })).toBeVisible();
  await page.getByRole("button", { name: "新建学习记录", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试同一次提交" })).toHaveCount(0);
  await page.getByLabel("给 Quantum Agent 的问题").fill("Another synthetic private answer");
  await page.getByRole("button", { name: /发送 \/ 运行/ }).click();
  await expect(page.getByRole("button", { name: "重试同一次提交" })).toBeVisible();
  await page.getByRole("button", { name: "打开命令面板", exact: true }).click();
  await page.getByRole("button", { name: /隔离课程 B/ }).click();
  await expect(page.getByRole("button", { name: "重试同一次提交" })).toHaveCount(0);
  expect(calls).toBe(2);
});

test("versioned course and the preserved Solo first answer survive the browser contract", async ({ page }) => {
  await interceptAgentApis(page, baseResult({ learning_loop_completed: true, learning_native: {
    course_package: { package_id: "finite-barriers", version: "1.0.0", content_sha256: "a".repeat(64),
      objective_ids: ["FB-O1", "FB-O4"], rubric_ids: ["FB-R1", "FB-R4"] },
    solo_first_attempt: { task_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", teaching_turn_id: TURN_ID,
      response: "Synthetic initial answer: T is zero.", confidence: 0.8,
      submitted_at: "2026-10-19T00:00:00Z", assistance_locked: true },
    teacher_follow_up: null, commitment: null, learning_action: "give_hint", teach_back: null,
    transfer: null, solo: null, cognitive_mirror: null, evidence_persisted: ["solo_attempt"],
    phase: "complete", current_stage: "solo", completed_stages: ["solo"],
    required_action: "none", loop_required: true,
  } }));
  await submitAndAssertCard(page, "Synthetic completed classroom episode", "preserved-first-attempt", async () => {
    await expect(page.getByTestId("course-package-version")).toContainText("finite-barriers · v1.0.0");
    await page.getByText("Solo 首次独立作答（提交后保留）", { exact: true }).click();
    await expect(page.getByText("Synthetic initial answer: T is zero.", { exact: true })).toBeVisible();
  });
});
