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
      },
    );
  });
});
