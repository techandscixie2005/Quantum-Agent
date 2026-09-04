import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = "/home/xiangyu_xie/QuantumAgent/test-results/phase1-qa";
mkdirSync(OUT, { recursive: true });

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";
const TURN_ID = "44444444-4444-4444-8444-444444444444";
const EVIDENCE_ID = "55555555-5555-4555-8555-555555555555";

const STUDENT_CONTEXT = {
  user_id: "66666666-6666-4666-8666-666666666666", display_name: "学量子",
  courses: [{ course_id: COURSE_ID, course_code: "PHYS-301", course_title: "量子物理", institution: "USTC", role: "student", curriculum_edition_id: EDITION_ID, edition_title: "2026 秋", academic_year: "2026", term: "秋", chapters: [{ id: "77777777-7777-4777-8777-777777777777", ordinal: 1, title: "量子隧穿", canonical_path: "Ch. 2 / Tunneling" }] }],
};

function baseResult(overrides = {}) {
  return {
    conversation_id: CONVERSATION_ID, turn_id: TURN_ID, workflow_version: "teaching-state-machine/1.0.0",
    interpretation: { task_kind: "experiment_help", relevant_concepts: ["量子隧穿"], needs_scientific_verification: true, confidence: 0.9 },
    diagnosis: { status: "model_inference", summary: "学生用经典直觉判断隧穿不可能。", likely_misconception: "认为 E<V0 时粒子完全不可能出现在势垒右侧。", observation_basis: ["student_message","student_attempt"], target_concepts: ["量子隧穿"], first_error: null, misconception_candidates: [{ statement: "经典粒子不能穿越势垒", confidence: 0.7 }], missing_prerequisites: [], progress_state: "started", confidence: 0.6, verification_needed: true, reason: "Diagnosis." },
    policy: { policy_id: null, source: "safe_default", mode: "run_experiments", allow_full_solution: false, minimum_attempts_for_scaffold: 0, minimum_attempts_for_full_solution: 3, max_hint_level: 2 },
    release: { action: "predict_then_simulate", release_level: "scaffold", attempts_observed: 2, reason_code: "prediction_submitted" },
    evidence_packet: { id: "88888888-8888-4888-8888-888888888888", course_id: COURSE_ID, curriculum_edition_id: EDITION_ID, query: "tunneling", created_at: "2026-08-26T00:00:00Z", coverage: "sufficient",
      evidence: [{ evidence_id: EVIDENCE_ID, chunk_id: "99999999-9999-4999-8999-999999999999", document_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", document_version_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", document_title: "Quantum Physics", document_version: 1, source_file_name: "quantum.pdf", source_file_sha256: "a".repeat(64), source_chunk_sha256: "b".repeat(64), evidence_sha256: "c".repeat(64), curriculum_edition_id: EDITION_ID, chapter: "Ch. 2", section_path: ["Tunneling"], locator: { locator_type: "pdf_page", physical_page: 42, printed_page_label: null, slide_number: null, paragraph_start: null, paragraph_end: null, sheet_name: null, row_start: null, row_end: null, line_start: null, line_end: null }, source_chunk: "Tunneling through a rectangular barrier.", evidence_snippet: "Tunneling through a rectangular barrier.", kind: "course_material", authority_priority: 10, contributions: [{ channel: "postgres_full_text", rank: 1, raw_score: 1.0, fused_score: 1.0 }] }],
      graph_nodes: [{ id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", node_type: "Concept", name: "量子隧穿", aliases: ["tunneling"] }],
      graph_edges: [], degraded_channels: [], warnings: [] },
    response: { orientation: "现在运行真实模拟，对比你的预测。", claims: [{ text: "透射概率 T = 0.3337，反射概率 R = 0.6663，R+T=1 守恒。", support_basis: "numerical_verification", evidence_ids: [], scientific_result_ids: [`rectangular_barrier_tunnelling:${"a".repeat(64)}`] }], next_question: "哪一个原先假设与你看到的结果冲突？", status: "grounded", limitations: [] },
    validation: { passed: true, citation_ids_valid: true, literal_course_claims_valid: true, scientific_references_valid: true, warnings: [] },
    scientific_results: [{ kind: "rectangular_barrier_tunnelling", method: "numerical", status: "pass", tool: { name: "NumPy", version: "2.0" }, inputs_sha256: "a".repeat(64), observations: ["Rectangular barrier: E=5 eV, V0=10 eV, a=1e-10 m.","Transmission T=0.333682287217, reflection R=0.666317712783, |R+T-1|=0.000e+00."], limitations: [], metrics: { T: 0.333682287217, R: 0.666317712783, conservation_error: 0.0, conservation_tolerance: 1e-9, energy_eV: 5.0, barrier_height_eV: 10.0, barrier_width_m: 1e-10, particle_mass_kg: 9.1093837015e-31, regime: "tunnelling" }, visualization: null, error_code: null }],
    trace: ["classify_task","identify_concepts","retrieve_evidence","diagnose_progress","choose_teaching_action","apply_answer_policy","run_scientific_tools","generate_response","validate_response","record_learning_evidence"].map((name) => ({ name, status: name === "run_scientific_tools" ? "skipped" : "completed", detail: `${name} done` })),
    code_artifact: null, learning_native: { commitment: null, learning_action: "start_simulation", teach_back: null, transfer: null, solo: null, cognitive_mirror: null, evidence_persisted: ["tool_observation"], phase: "awaiting_revision", current_stage: "verify", completed_stages: ["predict","diagnose","explore","verify"], required_action: "revision", loop_required: true }, turn_completed: true, learning_loop_completed: false,
    ...overrides,
  };
}

const sse = (e, d) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`;

async function setupRoutes(page, result) {
  await page.route("**/api/agent/context", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STUDENT_CONTEXT) }));
  await page.route("**/api/teaching/turns/stream**", async (route) => {
    let m = "run_experiments"; try { const b = route.request().postDataJSON(); if (b?.mode) m = b.mode; } catch {}
    const adapted = { ...result, policy: { ...result.policy, mode: m } };
    const body = sse("workflow.started", { workflow_version: "teaching-state-machine/1.0.0" }) + sse("workflow.completed", adapted);
    await route.fulfill({ status: 200, contentType: "text/event-stream", headers: { "Cache-Control": "no-store" }, body });
  });
}

async function send(page, msg) {
  await page.getByLabel("给 Quantum Agent 的问题").fill(msg);
  await page.getByRole("button", { name: /发送/ }).click();
}

const checks = [];
function check(name, cond, detail = "") {
  checks.push({ name, pass: !!cond, detail });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  · " + detail : ""}`);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

await setupRoutes(page, baseResult());
await page.goto("http://127.0.0.1:5173/agent", { waitUntil: "domcontentloaded" });
await page.getByTestId("agent-experience").waitFor({ timeout: 30000 });
await send(page, "为什么 E<V0 时仍可能透射？");
await page.getByTestId("agent-tutor-result").waitFor({ timeout: 15000 });
await page.waitForTimeout(1200);

const overflowX = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
check("无横向溢出", overflowX <= 0, `overflowX=${overflowX}`);

const leftWidth = await page.locator('[class*="leftPanel"]').first().boundingBox().then(b => b?.width ?? 999);
check("左侧导航为窄图标栏 (<=72px)", leftWidth <= 72, `leftWidth=${leftWidth}`);

const rightBox = await page.locator('[class*="rightPanel"]').first().boundingBox();
check("无永久右侧证据栏 (默认移出视口)", rightBox && rightBox.x >= 1440, `rightX=${rightBox?.x}`);

const hasGiantTitle = await page.locator("h1", { hasText: /工作台|推导工作台|实验工作台/ }).count();
check("无大号工作台标题", hasGiantTitle === 0, `count=${hasGiantTitle}`);

const pipelineCount = await page.locator('[class*="pipeline"], [class*="Pipeline"]').count();
check("无永久工程管线组件", pipelineCount === 0, `pipelineEls=${pipelineCount}`);

const composerBox = await page.locator('[class*="composer"]').first().boundingBox();
check("紧凑浮动编辑器 (高度 <=160px)", composerBox && composerBox.height <= 160, `h=${composerBox?.height}`);

const mainBox = await page.locator("main").first().boundingBox();
check("主舞台占视觉中心 (宽>600px)", mainBox && mainBox.width > 600, `mainW=${mainBox?.width}`);

const metricsInStage = await page.getByTestId("tunnelling-metrics").isVisible();
check("科学验证结果在主舞台内可见 (无需打开右侧)", metricsInStage);

const metricsCount = await page.getByTestId("tunnelling-metrics").count();
check("验证结果无重复 testid", metricsCount === 1, `count=${metricsCount}`);

const cmdHint = await page.locator('[aria-label="打开命令面板"]').first().isVisible();
check("⌘K 命令面板入口可见", cmdHint);

await page.keyboard.press("ControlOrMeta+k");
await page.waitForTimeout(400);
const paletteVisible = await page.getByRole("dialog", { name: "命令面板" }).isVisible();
check("⌘K 打开命令面板", paletteVisible);
await page.keyboard.press("Escape");
await page.waitForTimeout(250);

await page.locator('[aria-label="打开证据面板"]').first().click();
await page.waitForTimeout(450);
const sheetVisible = await page.locator('[class*="rightPanel"][class*="panelOpen"]').isVisible();
check("证据 Sheet 可展开", sheetVisible);
const citationInSheet = await page.getByTestId("agent-citation").first().isVisible();
check("证据 Sheet 内有课程引文", citationInSheet);

await page.keyboard.press("Escape");
await page.waitForTimeout(300);
const whyToggle = await page.locator('[class*="whyToggle"]').first().isVisible();
check("渐进披露：claims 有 [为什么？] 开关", whyToggle);

await page.screenshot({ path: `${OUT}/1440x900-experiment.png`, fullPage: false });

await browser.close();

const failed = checks.filter(c => !c.pass);
console.log(`\n${checks.length - failed.length}/${checks.length} passed`);
if (failed.length) {
  console.log("FAILURES:");
  for (const f of failed) console.log("  - " + f.name + (f.detail ? " (" + f.detail + ")" : ""));
  process.exit(1);
}
