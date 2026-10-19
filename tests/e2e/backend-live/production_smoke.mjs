/** Actual hardened compose web/API smoke. Only the isolated HTTP provider is a fixture. */
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "@playwright/test";

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) =>
  index % 2 === 0 ? [...pairs, [value.replace(/^--/, ""), values[index + 1]]] : pairs, []));
if (!args.manifest || !args.output || !args["base-url"]) throw new Error("manifest/output/base-url required");
const m = JSON.parse(await readFile(args.manifest, "utf8")); // Private, never copied into evidence.
const output = path.resolve(args.output);
await mkdir(output, { recursive: true });
const scope = `course_id=${m.course_id}&curriculum_edition_id=${m.edition_id}`;
const checks = [];
const browser = await chromium.launch({ channel: "chromium", headless: true });
const contexts = [];

async function http(page, url, body) {
  return page.evaluate(async ({ url, body }) => {
    const response = await fetch(url, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const text = await response.text();
    let data = null;
    try { data = JSON.parse(text); } catch { /* SSE decoded separately. */ }
    return { status: response.status, text, data };
  }, { url, body });
}
function terminal(text) {
  const blocks = text.replaceAll("\r\n", "\n").split("\n\n");
  const block = blocks.findLast(value => /^event: workflow\.(completed|interrupted|failed)$/m.test(value));
  assert.ok(block, "Real production BFF must return a terminal workflow event");
  return { event: block.split("\n").find(line => line.startsWith("event:")).slice(6).trim(),
    data: JSON.parse(block.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n")) };
}
async function poll(operation, accept, label) {
  const end = Date.now() + 60_000;
  while (Date.now() < end) {
    const value = await operation();
    if (accept(value)) return value;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out: ${label}`);
}
async function login(role, index) {
  const context = await browser.newContext({ baseURL: args["base-url"] });
  contexts.push(context);
  const page = await context.newPage();
  await page.goto("/agent");
  await page.getByLabel("个人课堂访问凭证").fill(m.actors[role][index].classroom_access_token);
  await page.getByLabel("USTC API Key").fill("backend-live-provider-fixture-key");
  const receipt = page.waitForResponse(response => new URL(response.url()).pathname === "/api/auth/login");
  await page.getByRole("button", { name: "连接并进入学习空间" }).click();
  assert.equal((await receipt).status(), 200, "Actual production API login must succeed");
  await page.getByLabel("给 Quantum Agent 的问题").waitFor();
  const identity = await http(page, "/api/agent/context");
  assert.equal(identity.status, 200);
  assert.equal(identity.data.user_id, m.actors[role][index].user_id);
  return page;
}
function input(message, extra = {}) {
  return { conversation_id: null, mode: "learn_concepts", message, student_attempt: null,
    attachment_ids: [], scientific_request: null, learning_native: null,
    client_request_id: crypto.randomUUID(), ...extra };
}
async function complete(page, body) {
  const response = await http(page, `/api/teaching/turns/stream?${scope}`, body);
  assert.equal(response.status, 200);
  const event = terminal(response.text);
  assert.equal(event.event, "workflow.completed");
  return event.data;
}

try {
  const alice = await login("student", 0);
  await alice.getByRole("button", { name: "概念模式 · 解释与迁移", exact: true }).click();
  let submitted = null;
  alice.on("request", request => {
    if (!submitted && new URL(request.url()).pathname === "/api/teaching/turns/stream" && request.method() === "POST") submitted = request.postDataJSON();
  });
  await alice.getByLabel("给 Quantum Agent 的问题").fill("什么是概率流？");
  await alice.getByRole("button", { name: "发送 / 运行", exact: true }).click();
  await poll(async () => submitted, value => Boolean(value?.client_request_id), "real UI submit");
  const saved = await poll(() => http(alice, `/api/teaching/requests/status?${scope}&client_request_id=${submitted.client_request_id}`),
    value => value.status === 200 && value.data.status === "completed", "production persisted first turn");
  const state = await http(alice, `/api/teaching/threads/${saved.data.conversation_id}/state?${scope}`);
  assert.equal(state.status, 200);
  const first = state.data.result;
  assert.equal(first.turn_id, saved.data.turn_id);
  assert.equal(first.turn_completed, true);
  assert.ok(first.evidence_packet.evidence.length >= 1, "Real SQL published synthetic content was retrieved");
  const replay = await complete(alice, submitted);
  assert.equal(replay.turn_id, first.turn_id);
  assert.equal(replay.conversation_id, first.conversation_id);
  await alice.screenshot({ path: path.join(output, "student-production-first-turn.png"), fullPage: true });
  checks.push({ check: "compiled production UI login, scoped retrieval, saved status and exact replay", passed: true,
    conversation_id: first.conversation_id, turn_id: first.turn_id });

  const bob = await login("student", 1);
  for (const suffix of ["state", "export", "interrupt"]) {
    const denied = await http(bob, `/api/teaching/threads/${first.conversation_id}/${suffix}?${scope}`);
    assert.ok([403, 404].includes(denied.status), "Other student must not read the learning record");
    assert.ok(!denied.text.includes(first.turn_id));
  }
  checks.push({ check: "shared synthetic provider key does not share student identity/records", passed: true });

  const teacher = await login("teacher", 0);
  const probe = "请用自己的话定义概率流，并指出该定义中的物理量。";
  const reviewBody = { source_turn_id: first.turn_id, decision: "needs_follow_up",
    reason: "SYNTHETIC production-runtime smoke review; not actual teacher approval or classroom results.",
    follow_up: "request_revision", probe, criterion_ratings: {} };
  const reviewPath = `/api/teacher/conversations/${first.conversation_id}/reviews?${scope}`;
  assert.equal((await http(alice, reviewPath, reviewBody)).status, 403);
  assert.equal((await http(teacher, reviewPath, reviewBody)).status, 201);
  const next = await complete(alice, input("概率流的定义是什么？", { conversation_id: first.conversation_id }));
  assert.equal(next.release.release_level, "question_only");
  assert.equal(next.response.next_question, probe);
  checks.push({ check: "authenticated synthetic teacher reason changes subsequent teaching action", passed: true,
    conversation_id: next.conversation_id, turn_id: next.turn_id });

  const pendingBody = input("什么是概率流？本轮需要 teacher approval。");
  const pausedHttp = await http(alice, `/api/teaching/turns/stream?${scope}`, pendingBody);
  assert.equal(pausedHttp.status, 200);
  const paused = terminal(pausedHttp.text);
  assert.equal(paused.event, "workflow.interrupted");
  const pause = paused.data;
  const queue = await http(teacher, `/api/teacher/pending-reviews?${scope}`);
  assert.equal(queue.status, 200);
  assert.ok(queue.data.items.some(item => item.turn_id === pause.turn_id));
  await teacher.goto(`/teacher/traces?${scope}`);
  const panel = teacher.getByRole("region", { name: "待人工复核队列" });
  await panel.getByRole("button", { name: new RegExp(pause.turn_id.slice(0, 8)) }).click();
  const note = "SYNTHETIC production-runtime smoke action; not actual teacher approval.";
  await panel.getByLabel("复核理由").fill(note);
  await teacher.screenshot({ path: path.join(output, "teacher-production-pending-fixture.png"), fullPage: true });
  await panel.getByRole("button", { name: "批准并恢复执行", exact: true }).click();
  await poll(async () => panel.getByRole("status").textContent(), value => value?.includes("复核决定已保存"), "actual staff UI resume");
  const approvedReplay = await http(teacher, `/api/teacher/conversations/${pause.conversation_id}/resume?${scope}`,
    { interrupt_id: pause.interrupt.interrupt_id, action: "approve", note });
  assert.equal(approvedReplay.status, 200);
  assert.equal(approvedReplay.data.turn_id, pause.turn_id);
  const pauseStatus = await http(alice, `/api/teaching/requests/status?${scope}&client_request_id=${pendingBody.client_request_id}`);
  assert.equal(pauseStatus.status, 200);
  assert.equal(pauseStatus.data.status, "completed");
  checks.push({ check: "first-turn HITL pending queue, actual staff UI resume, same-decision replay and status", passed: true,
    conversation_id: pause.conversation_id, turn_id: pause.turn_id, interrupt_id: pause.interrupt.interrupt_id });
  const exported = await http(alice, `/api/teaching/threads/${first.conversation_id}/export?${scope}`);
  assert.equal(exported.status, 200);
  assert.ok(exported.text.includes(first.turn_id) && exported.text.includes(probe));
  checks.push({ check: "actual student export links initial turn, teacher reason and follow-up", passed: true });
  await writeFile(path.join(output, "smoke-results.json"), JSON.stringify({
    label: "synthetic production-compose smoke; no classroom results or actual teacher approvals",
    mock: "isolated HTTP model provider only", production_review_fixture_loaded: false,
    course_id: m.course_id, edition_id: m.edition_id, checks,
    limitations: ["No production-container crash or provider-outage injection in this smoke; see separate real backend eight-case suite.",
      "Synthetic roster and publication statuses; no actual teacher source-applicability approval.",
      "BUILD_REVISION may be unknown until final image build is bound to an actual commit."],
  }, null, 2));
  console.log(JSON.stringify({ passed: true, checks: checks.length, synthetic_only: true }));
} catch (error) {
  await writeFile(path.join(output, "smoke-failure.json"), JSON.stringify({
    passed: false, synthetic_only: true, completed_checks: checks,
    error: error instanceof Error ? error.message : String(error),
  }, null, 2));
  throw error;
} finally {
  for (const context of contexts) await context.close();
  await browser.close();
}
