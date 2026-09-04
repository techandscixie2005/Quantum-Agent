import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = "/home/xiangyu_xie/QuantumAgent/test-results/phase1-baseline";
mkdirSync(OUT, { recursive: true });

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";
const TURN_ID = "44444444-4444-4444-8444-444444444444";
const EVIDENCE_ID = "55555555-5555-4555-8555-555555555555";

const STUDENT_CONTEXT = {
  user_id: "66666666-6666-4666-8666-666666666666",
  display_name: "学量子",
  courses: [{
    course_id: COURSE_ID, course_code: "PHYS-301", course_title: "量子物理",
    institution: "USTC", role: "student", curriculum_edition_id: EDITION_ID,
    edition_title: "2026 秋", academic_year: "2026", term: "秋",
    chapters: [{ id: "77777777-7777-4777-8777-777777777777", ordinal: 1, title: "量子隧穿", canonical_path: "Ch. 2 / Tunneling" }],
  }],
};

function baseResult(overrides = {}) {
  return {
    conversation_id: CONVERSATION_ID, turn_id: TURN_ID,
    workflow_version: "teaching-state-machine/1.0.0",
    interpretation: { task_kind: "experiment_help", relevant_concepts: ["量子隧穿"], needs_scientific_verification: true, confidence: 0.9 },
    diagnosis: { status: "model_inference", summary: "学生用经典直觉判断隧穿不可能。", likely_misconception: "认为 E<V0 时粒子完全不可能出现在势垒右侧。", observation_basis: ["student_message","student_attempt"], target_concepts: ["量子隧穿"], first_error: null, misconception_candidates: [{ statement: "经典粒子不能穿越势垒", confidence: 0.7 }], missing_prerequisites: [], progress_state: "started", confidence: 0.6, verification_needed: true, reason: "Diagnosis." },
    policy: { policy_id: null, source: "safe_default", mode: "run_experiments", allow_full_solution: false, minimum_attempts_for_scaffold: 0, minimum_attempts_for_full_solution: 3, max_hint_level: 2 },
    release: { action: "predict_then_simulate", release_level: "question_only", attempts_observed: 0, reason_code: "prediction_required" },
    evidence_packet: { id: "88888888-8888-4888-8888-888888888888", course_id: COURSE_ID, curriculum_edition_id: EDITION_ID, query: "tunneling", created_at: "2026-08-26T00:00:00Z", coverage: "sufficient",
      evidence: [{ evidence_id: EVIDENCE_ID, chunk_id: "99999999-9999-4999-8999-999999999999", document_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", document_version_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", document_title: "Quantum Physics", document_version: 1, source_file_name: "quantum.pdf", source_file_sha256: "a".repeat(64), source_chunk_sha256: "b".repeat(64), evidence_sha256: "c".repeat(64), curriculum_edition_id: EDITION_ID, chapter: "Ch. 2", section_path: ["Tunneling"], locator: { locator_type: "pdf_page", physical_page: 42, printed_page_label: null, slide_number: null, paragraph_start: null, paragraph_end: null, sheet_name: null, row_start: null, row_end: null, line_start: null, line_end: null }, source_chunk: "Tunneling through a rectangular barrier.", evidence_snippet: "Tunneling through a rectangular barrier.", kind: "course_material", authority_priority: 10, contributions: [{ channel: "postgres_full_text", rank: 1, raw_score: 1.0, fused_score: 1.0 }] }],
      graph_nodes: [{ id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", node_type: "Concept", name: "量子隧穿", aliases: ["tunneling"] }],
      graph_edges: [], degraded_channels: [], warnings: [] },
    response: { orientation: "先做一个判断。", claims: [], next_question: "你预测透射概率会是多少？", status: "grounded", limitations: [] },
    validation: { passed: true, citation_ids_valid: true, literal_course_claims_valid: true, scientific_references_valid: true, warnings: [] },
    scientific_results: [],
    trace: ["classify_task","identify_concepts","retrieve_evidence","diagnose_progress","choose_teaching_action","apply_answer_policy","run_scientific_tools","generate_response","validate_response","record_learning_evidence"].map((name) => ({ name, status: name === "run_scientific_tools" ? "skipped" : "completed", detail: `${name} done` })),
    code_artifact: null, learning_native: null, turn_completed: true, learning_loop_completed: false,
    ...overrides,
  };
}

const sse = (e, d) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`;

function buildStage(name, extra) {
  return baseResult({
    learning_native: {
      commitment: null, learning_action: null, teach_back: null, transfer: null, solo: null, cognitive_mirror: null,
      evidence_persisted: [], phase: "awaiting_revision", current_stage: "explain", completed_stages: ["predict","diagnose"], required_action: "revision", loop_required: true,
      ...extra,
    },
  });
}

const STAGES = {
  commitment: buildStage("commitment", {
    commitment: { gate_decision: "attempt_required", attempt_required: true, attempt_type: "prediction", candidate_prompt: "增加势垒宽度，透射概率如何变化？给出你的预测。", reason_summary: "先预测再解释。", accepted: false, confidence: null },
    learning_action: "ask_commitment", phase: "commitment_required", current_stage: "predict", completed_stages: [], required_action: "commitment",
  }),
  diagnosis: baseResult({
    release: { action: "ask_diagnostic_question", release_level: "hint", attempts_observed: 1, reason_code: "first_attempt_hint_only" },
    response: { orientation: "你的预测用了经典图像；量子力学中 E<V0 时波函数在势垒内指数衰减但不为零。", claims: [], next_question: "势垒右侧的波函数振幅会是什么量级？", status: "grounded", limitations: ["hint-only"] },
    learning_native: { commitment: null, learning_action: "give_hint", teach_back: null, transfer: null, solo: null, cognitive_mirror: null, evidence_persisted: ["commitment"], phase: "awaiting_revision", current_stage: "explain", completed_stages: ["predict","diagnose"], required_action: "revision", loop_required: true },
  }),
  experiment: baseResult({
    release: { action: "predict_then_simulate", release_level: "scaffold", attempts_observed: 2, reason_code: "prediction_submitted" },
    response: { orientation: "现在运行真实模拟，对比你的预测。", claims: [{ text: "透射概率 T = 0.3337，反射概率 R = 0.6663，R+T=1 守恒。", support_basis: "numerical_verification", evidence_ids: [], scientific_result_ids: [`rectangular_barrier_tunnelling:${"a".repeat(64)}`] }], next_question: "哪一个原先假设与你看到的结果冲突？", status: "grounded", limitations: [] },
    scientific_results: [{ kind: "rectangular_barrier_tunnelling", method: "numerical", status: "pass", tool: { name: "NumPy", version: "2.0" }, inputs_sha256: "a".repeat(64), observations: ["Rectangular barrier: E=5 eV, V0=10 eV, a=1e-10 m.","Transmission T=0.333682287217, reflection R=0.666317712783, |R+T-1|=0.000e+00."], limitations: [], metrics: { T: 0.333682287217, R: 0.666317712783, conservation_error: 0.0, conservation_tolerance: 1e-9, energy_eV: 5.0, barrier_height_eV: 10.0, barrier_width_m: 1e-10, particle_mass_kg: 9.1093837015e-31, regime: "tunnelling" }, visualization: null, error_code: null }],
    code_artifact: { artifact: { language: "python", purpose: "rectangular barrier tunnelling T/R", code: "import math\njoule_per_eV = 1.602176634e-19\nhbar = 1.054571817e-34\nm = 9.1093837015e-31\nE=5.0; V0=10.0; a=1e-10\nkappa = math.sqrt(2*m*(V0-E)*joule_per_eV)/hbar\nT = 1.0/(1.0 + (V0**2*math.sinh(kappa*a)**2)/(4*E*(V0-E)))\nprint('### METRICS_JSON: ' + str({'T': T, 'R': 1-T}))", expected_outputs: ["T","R","conservation_error"], verification_plan: "match oracle within 1e-6" }, execution: { completed: true, exit_code: 0, timed_out: false, truncated: false, stdout_bounded: '### METRICS_JSON: {"T": 0.333682, "R": 0.666318, "conservation_error": 0.0}', stderr_bounded: "", duration_seconds: 0.8 }, verification: { status: "pass", oracle_kind: "rectangular_barrier_tunnelling", agent_metrics: { T: 0.333682287217, R: 0.666317712783, conservation_error: 0.0 }, oracle_metrics: { T: 0.333682287217, R: 0.666317712783, conservation_error: 0.0 }, observations: ["Agent metrics match the oracle within tolerance."], tolerance: 1e-6 }, repairs: [], progress: "result", figure_png_base64: null },
    learning_native: { commitment: null, learning_action: "start_simulation", teach_back: null, transfer: null, solo: null, cognitive_mirror: null, evidence_persisted: ["tool_observation"], phase: "awaiting_revision", current_stage: "verify", completed_stages: ["predict","diagnose","explore","verify"], required_action: "revision", loop_required: true },
  }),
  teachback: buildStage("teachback", {
    teach_back: { covered_relations: [{ relation: "covered", description: "已说明势垒内波函数指数衰减。", target_concept_id: null }], missing_relations: [{ relation: "missing", description: "尚未连接到非零透射概率。", target_concept_id: null }], contradictions: [], unsupported_claims: [], recommended_probe: "势垒右侧的振幅为什么不等于零？", verified: false, is_model_inference: true },
    learning_action: "start_teach_back", phase: "reconstruction_required", current_stage: "teach_back", completed_stages: ["predict","diagnose","explore","verify","explain"], required_action: "teach_back",
  }),
  transfer: buildStage("transfer", {
    transfer: { task_id: EVIDENCE_ID, transfer_type: "representation", prompt: "画出不同势垒宽度下的透射率曲线并解释趋势。", source_concept_ids: [], key_parameters: ["barrier_width"], expected_observable: "", verifiable: false },
    solo: { status: "active", active_transfer: { task_id: EVIDENCE_ID, transfer_type: "representation", prompt: "画出不同势垒宽度下的透射率曲线并解释趋势。", source_concept_ids: [], key_parameters: ["barrier_width"], expected_observable: "", verifiable: false }, started_at: "2026-08-26T00:00:00Z", assistance_locked: true, unlock_reason: "" },
    learning_action: "enter_solo", phase: "solo_active", current_stage: "solo", completed_stages: ["predict","diagnose","explore","verify","explain","teach_back","transfer"], required_action: "solo_attempt",
  }),
  mirror: baseResult({
    learning_loop_completed: true,
    learning_native: { commitment: null, learning_action: null, teach_back: null, transfer: null, solo: { status: "exited", active_transfer: null, started_at: "2026-08-26T00:00:00Z", assistance_locked: false, unlock_reason: "学生已提交迁移尝试，恢复 AI 辅助。" }, cognitive_mirror: { current_concept_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", concept_states: [{ concept_candidate_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", label: "transfer_ready", evidence_summary: ["学生提交了 prediction 类型承诺。","学生 teach-back 覆盖 1 条关系，遗漏 1 条。","学生在 Solo Mode 下提交迁移尝试。"], confidence_history: [[0.8,true],[0.6,true]], calibration_gap: null, unaided_retrieval: true, transfer_evidence: ["学生在 Solo Mode 下提交迁移尝试。"], hint_dependency: ["学生在解释前提交了承诺。"], misconception_candidates: ["认为 E<V0 时粒子完全不可能出现在势垒右侧。"], last_demonstrated_at: "2026-08-26T00:00:00Z" }], summary: "当前聚焦概念：量子隧穿。镜像是观察记录，不是掌握度分数。", no_personality_profile: true }, evidence_persisted: ["solo_attempt","confidence"], phase: "complete", current_stage: null, completed_stages: ["predict","diagnose","explore","verify","explain","teach_back","transfer","solo"], required_action: "none", loop_required: true },
  }),
};

async function setupRoutes(page, result) {
  await page.route("**/api/agent/context", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STUDENT_CONTEXT) });
  });
  await page.route("**/api/teaching/turns/stream**", async (route) => {
    let requestMode = "run_experiments";
    try { const b = route.request().postDataJSON(); if (b?.mode) requestMode = b.mode; } catch {}
    const adapted = { ...result, policy: { ...result.policy, mode: requestMode } };
    const body = sse("workflow.started", { workflow_version: "teaching-state-machine/1.0.0" }) + sse("workflow.completed", adapted);
    await route.fulfill({ status: 200, contentType: "text/event-stream", headers: { "Cache-Control": "no-store" }, body });
  });
}

async function send(page, msg) {
  const messageBox = page.getByLabel("给 Quantum Agent 的问题");
  await messageBox.fill(msg);
  const sendButton = page.getByRole("button", { name: /发送/ });
  await sendButton.click();
}

const browser = await chromium.launch();
for (const [w, h] of [[1440, 900], [1920, 1080]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();

  // initial empty stage
  await page.route("**/api/agent/context", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STUDENT_CONTEXT) }));
  await page.goto("http://127.0.0.1:5173/agent", { waitUntil: "domcontentloaded" });
  await page.getByTestId("agent-experience").waitFor({ timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/${w}x${h}-00-initial.png` });

  // each stage
  for (const [name, result] of Object.entries(STAGES)) {
    const p2 = await ctx.newPage();
    await setupRoutes(p2, result);
    await p2.goto("http://127.0.0.1:5173/agent", { waitUntil: "domcontentloaded" });
    await p2.getByTestId("agent-experience").waitFor({ timeout: 30000 });
    await send(p2, "为什么 E<V0 时仍可能透射？");
    // wait for the stage's signature element
    const sig = { commitment: "commitment-card", diagnosis: "agent-tutor-result", experiment: "tunnelling-metrics", teachback: "teach-back-card", transfer: "transfer-card", mirror: "cognitive-mirror" }[name];
    await p2.getByTestId(sig).waitFor({ timeout: 15000 });
    await p2.waitForTimeout(1200);
    await p2.screenshot({ path: `${OUT}/${w}x${h}-${name}.png`, fullPage: false });
    await p2.close();
  }
  await ctx.close();
}
await browser.close();
console.log("done");
