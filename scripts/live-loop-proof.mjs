/* Live Golden Loop driver (real FastAPI stack + real USTC model, persistent thread).
 *
 * Proves the ORIGINAL bug fix over the live stack: same conversation_id through
 *   gate → commitment(→ attempt_received → minimal-intervention) → revised attempt
 *   → awaiting_revision → scientific tunnelling turn (oracle + Coding Agent)
 *   → teach-back → transfer → Solo → complete.
 *
 * We drive FastAPI's turn/stream endpoint directly with a student bearer token so
 * the durable phase persists across turns (the browser resets conversation_id on
 * UI mode switch — a pre-existing frontend limitation, not a backend one).
 *
 * Usage: node scripts/live-loop-proof.mjs   (needs QA_E2E_AUTH_FILE + USTC_API)
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const BASE = process.env.QUANTUM_API_BASE_URL ?? "http://127.0.0.1:8000";
const apiKey = process.env.USTC_API?.trim();
if (!apiKey) throw new Error("USTC_API required");

const authFile = resolve(process.env.QA_E2E_AUTH_FILE || "");
const auth = JSON.parse(readFileSync(authFile, "utf8"));
const COURSE = auth.course_id;
const EDITION = auth.curriculum_edition_id;

async function login() {
  const res = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error(`login failed ${res.status}`);
  const body = await res.json();
  return body.session_token;
}

async function turn(token, payload) {
  const res = await fetch(
    `${BASE}/api/v1/courses/${COURSE}/editions/${EDITION}/teaching/turns/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        Accept: "text/event-stream",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`turn failed ${res.status}: ${text.slice(0, 300)}`);
  }
  const text = await res.text();
  const events = [];
  for (const block of text.split("\n\n")) {
    const m = /event: (\S+)/.exec(block);
    const d = m?.[1] === "workflow.completed" || m?.[1] === "workflow.interrupted";
    if (m && d) events.push({ event: m[1], data: JSON.parse(block.split("\n")[1].slice(5)) });
  }
  if (!events.length) throw new Error("no terminal event in stream");
  const terminal = events[events.length - 1];
  if (terminal.event !== "workflow.completed") throw new Error(`terminal ${terminal.event}`);
  return terminal.data;
}

function native(nativePart) {
  return {
    commitment: null,
    confidence: null,
    teach_back: null,
    transfer_attempt: null,
    solo_attempt: null,
    request_transfer: false,
    request_solo_exit: false,
    request_teach_back: false,
    request_transfer_task: false,
    ...nativePart,
  };
}

const BARRIER = {
  kind: "rectangular_barrier_tunnelling",
  energy_eV: 5.0,
  barrier_height_eV: 10.0,
  barrier_width_m: 1e-10,
  particle_mass_kg: 9.1093837015e-31,
  conservation_tolerance: 1e-9,
};

async function main() {
  const start = Date.now();
  const token = await login();
  console.log("[login] OK");
  let conversationId = null;
  const tract = [];

  const phase = (r) => r?.learning_native?.phase ?? "n/a";

  // 1. Open the loop (run_experiments: tunnelling + barrier request).
  let r = await turn(token, {
    conversation_id: null,
    mode: "run_experiments",
    message: "我想理解量子隧穿：为什么粒子能量 E 小于势垒高度 V0 时仍然可能出现在势垒右侧？",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: null,
    client_request_id: crypto.randomUUID(),
  });
  conversationId = r.conversation_id;
  tract.push({ t: 1, msg: "open", phase: phase(r), action: r?.learning_native?.required_action ?? "none", commit: r?.learning_native?.commitment?.accepted });
  console.log(`[1] open → phase=${phase(r)} action=${r?.learning_native?.required_action} cid=${conversationId}`);

  // 2. Submit the CommitmentCard.
  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "我预测：E<V0 时透射概率为零，粒子不可能穿越势垒。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: native({
      commitment: {
        gate_decision: "attempt_required",
        attempt_required: true,
        attempt_type: "prediction",
        candidate_prompt: "我预测：E<V0 时透射概率为零，粒子不可能穿越势垒。",
        reason_summary: "",
        accepted: false,
        confidence: null,
      },
      confidence: 0.7,
    }),
    client_request_id: crypto.randomUUID(),
  });
  tract.push({ t: 2, msg: "commit", phase: phase(r), action: r?.learning_native?.required_action ?? "none", commit: r?.learning_native?.commitment?.accepted, loopComplete: r.learning_loop_completed });
  console.log(`[2] commit → phase=${phase(r)} action=${r?.learning_native?.required_action} loopComplete=${r.learning_loop_completed}`);

  // 3. Answer the minimal-intervention probe (revised attempt).
  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "我修正：势垒右侧的波函数振幅很小但不为零，透射概率是一个很小的正数。",
    student_attempt: "波函数在势垒内指数衰减，右侧振幅非零，透射概率是一个很小的正数。",
    attachment_ids: [],
    scientific_request: null,
    learning_native: null,
    client_request_id: crypto.randomUUID(),
  });
  tract.push({ t: 3, msg: "revise", phase: phase(r), action: r?.learning_native?.required_action ?? "none" });
  console.log(`[3] revise → phase=${phase(r)} action=${r?.learning_native?.required_action}`);

  // 4. Scientific tunnelling turn (oracle + Coding Agent) — same thread.
  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "请用矩势垒散射工具计算 E=5eV, V0=10eV, a=1e-10m 的透射概率 T 和反射概率 R，并验证 R+T=1。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: BARRIER,
    learning_native: null,
    client_request_id: crypto.randomUUID(),
  });
  const tools = r.scientific_results ?? [];
  tract.push({ t: 4, msg: "scientific", phase: phase(r), tools: tools.map((x) => `${x.kind}:${x.status}`), codeArtifact: !!r.code_artifact });
  console.log(`[4] scientific → phase=${phase(r)} oracle=${tools.map((x) => x.status + "/" + (x.kind === "rectangular_barrier_tunnelling" ? "T=" + x.metrics?.T : "")).join(",")} codeArtifact=${!!r.code_artifact}`);

  // 5. Teach-back request → reconstruction → transfer → solo → complete.
  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "继续 Learning-Native 学习循环。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: native({ request_teach_back: true }),
    client_request_id: crypto.randomUUID(),
  });
  tract.push({ t: 5, msg: "teach-back-req", phase: phase(r), action: r?.learning_native?.required_action ?? "none" });
  console.log(`[5] teach-back-req → phase=${phase(r)} action=${r?.learning_native?.required_action}`);

  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "这是我的重构。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: native({
      teach_back: {
        reconstruction: "波函数在势垒内不是突变为零，而是指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
        target_concept_ids: [],
      },
    }),
    client_request_id: crypto.randomUUID(),
  });
  tract.push({ t: 6, msg: "teach-back-submit", phase: phase(r), action: r?.learning_native?.required_action ?? "none" });
  console.log(`[6] teach-back-submit → phase=${phase(r)} action=${r?.learning_native?.required_action}`);

  // 6b. Second teach-back submit from reconstruction_required →
  //     transfer_required (teach_back_verified), matching the live spec Stage 12.
  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "再次提交重构：波函数在势垒内指数衰减，右侧振幅非零，透射概率是一个很小的正数。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: native({
      teach_back: {
        reconstruction: "再次重构：波函数在势垒内指数衰减；衰减后的振幅在右侧仍然非零，因此透射概率是一个很小的正数。",
        target_concept_ids: [],
      },
    }),
    client_request_id: crypto.randomUUID(),
  });
  tract.push({ t: 6.5, msg: "teach-back-resubmit", phase: phase(r), action: r?.learning_native?.required_action ?? "none" });
  console.log(`[6.5] teach-back-resubmit → phase=${phase(r)} action=${r?.learning_native?.required_action}`);

  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "我想进入迁移任务。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: native({ request_transfer_task: true }),
    client_request_id: crypto.randomUUID(),
  });
  const transfer = r?.learning_native?.transfer;
  const transferT = transfer ? { id: transfer.task_id, verifiable: transfer.verifiable, prompt: (transfer.prompt || "").slice(0, 60) } : null;
  tract.push({ t: 7, msg: "transfer", phase: phase(r), action: r?.learning_native?.required_action ?? "none", transfer: transferT });
  console.log(`[7] transfer → phase=${phase(r)} action=${r?.learning_native?.required_action} transferVerifiable=${transfer?.verifiable}`);

  // 8. Correct Solo attempt — compute the changed-width oracle T client-side.
  const coop = (() => {
    const joulePerEV = 1.602176634e-19;
    const hbarJs = 1.054571817e-34;
    const m = 9.1093837015e-31;
    const width = 1.5e-10; // 1.5x original (per transfer contract)
    const E = 5.0 * joulePerEV;
    const V0 = 10.0 * joulePerEV;
    const k = Math.sqrt(2 * m * (V0 - E)) / hbarJs;
    const arg = k * width;
    const sinhSq = Math.sinh(arg) ** 2;
    return 1 / (1 + (V0 * V0 * sinhSq) / (4 * E * (V0 - E)));
  })();

  r = await turn(token, {
    conversation_id: conversationId,
    mode: "run_experiments",
    message: "这是我独立完成的迁移任务。",
    student_attempt: null,
    attachment_ids: [],
    scientific_request: null,
    learning_native: native({
      solo_attempt: { response: `透射系数 T = ${coop.toFixed(4)}（与数值验证一致：势垒更宽，透射率下降）`, confidence: 0.8 },
    }),
    client_request_id: crypto.randomUUID(),
  });
  const done = phase(r) === "complete" || r.learning_loop_completed === true;
  tract.push({ t: 8, msg: "solo", phase: phase(r), loopComplete: r.learning_loop_completed, soloStatus: r?.learning_native?.solo?.status });
  console.log(`[8] solo → phase=${phase(r)} loopComplete=${r.learning_loop_completed} solo=${r?.learning_native?.solo?.status} DONE=${done}`);

  console.log("\n=== PHASE TRANSCRIPT ===");
  for (const row of tract) console.log(JSON.stringify(row));
  console.log(`\n=== RESULT: ${done ? "LOOP REACHED COMPLETE ✔" : "NOT COMPLETE ✘"} (${((Date.now() - start) / 1000).toFixed(0)}s) ===`);
  process.exit(done ? 0 : 1);
}

main().catch((err) => {
  console.error("LIVE PROOF FAILED:", err.message);
  process.exit(2);
});
