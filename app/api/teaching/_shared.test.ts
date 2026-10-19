import assert from "node:assert/strict";
import test from "node:test";

import { TeachingContractError } from "@/app/components/teaching/contracts";
import { makeStreamingValidator, parseSseDocument } from "./_shared";
import { teachingProxyTimeoutMs } from "@/lib/teaching-timeout";
import { boundedStatusJson, parseTeachingRequestStatus, recoveryMatchesView } from "@/lib/teaching-request-status";

const TEST_SCOPE = {
  courseId: "11111111-1111-1111-1111-111111111111",
  curriculumEditionId: "22222222-2222-2222-2222-222222222222",
} as const;

const TEST_CONTEXT = {
  scope: TEST_SCOPE as never,
  mode: "learn_concepts",
  conversationId: null,
} as const;

function startedBlock(): string {
  return 'event: workflow.started\ndata: {"workflow_version":"teaching-state-machine/1.0.0"}';
}

function progressBlock(step: string, elapsed: number): string {
  return `event: progress\ndata: ${JSON.stringify({ step, status: "stage_started", detail: `${step} started`, elapsed_seconds: elapsed })}`;
}

function keepaliveBlock(): string {
  return ": keepalive";
}

function failedBlock(code: string): string {
  return `event: workflow.failed\ndata: ${JSON.stringify({ code })}`;
}

test("SSE boundary recognizes the typed workflow interrupt event", () => {
  const events = parseSseDocument(
    [
      "event: workflow.started",
      'data: {"workflow_version":"quantum-agent-v2.1"}',
      "",
      "event: workflow.interrupted",
      'data: {"status":"interrupted"}',
      "",
    ].join("\n"),
  );

  assert.equal(events.length, 2);
  assert.equal(events[1]?.event, "workflow.interrupted");
});

test("SSE boundary rejects unknown events and unsupported fields", () => {
  assert.throws(
    () => parseSseDocument('event: workflow.paused\ndata: {}\n\n'),
    TeachingContractError,
  );
  assert.throws(
    () =>
      parseSseDocument(
        'event: workflow.interrupted\nid: attacker-controlled\ndata: {"status":"interrupted"}\n\n',
      ),
    TeachingContractError,
  );
});

test("SSE boundary skips comment-only keepalive blocks and progress events", () => {
  const events = parseSseDocument(
    [
      "event: workflow.started",
      'data: {"workflow_version":"quantum-agent-v2.1"}',
      "",
      ": keepalive",
      "",
      'event: progress',
      'data: {"step":"interpret","status":"stage_started","detail":"x","elapsed_seconds":0.4}',
      "",
      "event: workflow.completed",
      'data: {"status":"completed"}',
      "",
    ].join("\n"),
  );
  assert.equal(events.length, 2);
  assert.equal(events[0]?.event, "workflow.started");
  assert.equal(events[1]?.event, "workflow.completed");
});

test("streaming validator forwards workflow.started immediately", async () => {
  const v = makeStreamingValidator();
  const out = await v.handleBlock(startedBlock(), TEST_CONTEXT);
  assert.equal(out.kind, "forward");
  assert.match(out.chunk, /event: workflow\.started/);
  assert.equal(v.finished, false);
});

test("streaming validator forwards progress and keepalive blocks verbatim", async () => {
  const v = makeStreamingValidator();
  // started first (required before terminal)
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  // progress forwarded as-is
  const prog = await v.handleBlock(progressBlock("interpret", 0.4), TEST_CONTEXT);
  assert.equal(prog.kind, "forward");
  assert.match(prog.chunk, /event: progress/);
  assert.match(prog.chunk, /interpret/);
  // keepalive forwarded as-is
  const ka = await v.handleBlock(keepaliveBlock(), TEST_CONTEXT);
  assert.equal(ka.kind, "forward");
  assert.match(ka.chunk, /^: keepalive\n\n$/);
  assert.equal(v.finished, false);
});

test("streaming validator forwards a safe workflow.failed terminal and finishes", async () => {
  const v = makeStreamingValidator();
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  const out = await v.handleBlock(failedBlock("RETRIEVAL_UNAVAILABLE"), TEST_CONTEXT);
  assert.equal(out.kind, "terminal");
  assert.match(out.chunk, /event: workflow\.failed/);
  assert.match(out.chunk, /RETRIEVAL_UNAVAILABLE/);
  assert.equal(v.finished, true);
});

test("streaming validator rejects a workflow.failed with an unsafe code", async () => {
  const v = makeStreamingValidator();
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  const out = await v.handleBlock(failedBlock("ATTACKER_CODE"), TEST_CONTEXT);
  assert.equal(out.kind, "error");
  assert.match(out.chunk, /INVALID_UPSTREAM_CONTRACT/);
  assert.equal(v.finished, true);
});

test("streaming validator rejects a terminal before workflow.started", async () => {
  const v = makeStreamingValidator();
  const out = await v.handleBlock(failedBlock("RETRIEVAL_UNAVAILABLE"), TEST_CONTEXT);
  assert.equal(out.kind, "error");
  assert.match(out.chunk, /INVALID_UPSTREAM_CONTRACT/);
});

for (const code of ["ATTACHMENT_NOT_FOUND", "ATTACHMENT_NOT_READY", "WORKFLOW_UNAVAILABLE"]) {
  test(`stream preserves backend attachment failure ${code} without forwarding details`, async () => {
    const validator = makeStreamingValidator();
    await validator.handleBlock(startedBlock(), TEST_CONTEXT);
    const result = await validator.handleBlock(
      `event: workflow.failed\ndata: ${JSON.stringify({ code, detail: "private upstream detail" })}`,
      TEST_CONTEXT,
    );
    assert.equal(result.kind, "terminal");
    assert.match(result.chunk, new RegExp(code));
    assert.doesNotMatch(result.chunk, /private upstream detail/);
    assert.equal(validator.finished, true);
  });
}

test("a comment prefix cannot bypass terminal validation", async () => {
  const validator = makeStreamingValidator();
  await validator.handleBlock(startedBlock(), TEST_CONTEXT);
  const result = await validator.handleBlock(
    ': heartbeat\nevent: workflow.completed\ndata: {"status":"completed"}', TEST_CONTEXT,
  );
  assert.equal(result.kind, "error");
  assert.equal(validator.finished, true);
  const later = await validator.handleBlock(failedBlock("RETRIEVAL_UNAVAILABLE"), TEST_CONTEXT);
  assert.equal(later.chunk, "");
});

test("streaming validator rejects a second workflow.started", async () => {
  const v = makeStreamingValidator();
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  const out = await v.handleBlock(startedBlock(), TEST_CONTEXT);
  assert.equal(out.kind, "error");
  assert.match(out.chunk, /INVALID_UPSTREAM_CONTRACT/);
});

test("streaming validator drops a second terminal event silently (stream already closed)", async () => {
  const v = makeStreamingValidator();
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  const first = await v.handleBlock(failedBlock("RETRIEVAL_UNAVAILABLE"), TEST_CONTEXT);
  assert.equal(first.kind, "terminal");
  // After the terminal, the proxy closes the stream.  A second terminal
  // block (defensive) is a no-op forward so the browser never sees a second
  // terminal event.
  const second = await v.handleBlock(failedBlock("RETRIEVAL_UNAVAILABLE"), TEST_CONTEXT);
  assert.equal(second.kind, "forward");
  assert.equal(second.chunk, "");
});

test("streaming validator rejects an unknown event", async () => {
  const v = makeStreamingValidator();
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  const out = await v.handleBlock('event: workflow.paused\ndata: {}\n', TEST_CONTEXT);
  assert.equal(out.kind, "error");
  assert.match(out.chunk, /INVALID_UPSTREAM_CONTRACT/);
});

test("streaming validator rejects an invalid workflow.completed payload", async () => {
  const v = makeStreamingValidator();
  await v.handleBlock(startedBlock(), TEST_CONTEXT);
  // An incomplete completed payload fails parseTeachingTurnResult validation.
  const out = await v.handleBlock(
    'event: workflow.completed\ndata: {"status":"completed"}',
    TEST_CONTEXT,
  );
  assert.equal(out.kind, "error");
  assert.match(out.chunk, /INVALID_UPSTREAM_CONTRACT/);
});

test("streaming validator preserves a recording budget failure as the terminal", async () => {
  const validator = makeStreamingValidator();
  await validator.handleBlock(startedBlock(), TEST_CONTEXT);
  const output = await validator.handleBlock(failedBlock("RECORDING_BUDGET_UNAVAILABLE"), TEST_CONTEXT);
  assert.equal(output.kind, "terminal");
  assert.match(output.chunk, /RECORDING_BUDGET_UNAVAILABLE/);
  assert.doesNotMatch(output.chunk, /INVALID_UPSTREAM_CONTRACT/);
  assert.equal(validator.finished, true);
});

test("teaching proxy timeout follows active execution with bounded recovery margin", () => {
  assert.equal(teachingProxyTimeoutMs({}), 210_000);
  assert.equal(teachingProxyTimeoutMs({ TEACHING_EXECUTION_SECONDS: "120" }), 150_000);
  assert.equal(teachingProxyTimeoutMs({ TEACHING_EXECUTION_SECONDS: "600", TEACHING_PROXY_TIMEOUT_SECONDS: "630" }), 630_000);
  for (const env of [
    { TEACHING_EXECUTION_SECONDS: "NaN" }, { TEACHING_EXECUTION_SECONDS: "0" },
    { TEACHING_EXECUTION_SECONDS: "601" }, { TEACHING_PROXY_TIMEOUT_SECONDS: "190" },
    { TEACHING_PROXY_TIMEOUT_SECONDS: "661" },
  ]) assert.throws(() => teachingProxyTimeoutMs(env));
});

function requestStatus() {
  return { client_request_id: "same-request", conversation_id: "11111111-1111-4111-8111-111111111111",
    turn_id: "22222222-2222-4222-8222-222222222222", status: "failed",
    execution_budget: { state: "exhausted", active_used_seconds: 180, human_wait_seconds: 3600,
      provider_requests: 3, lease: { secret: "must-not-reach-browser" } },
    recovery_action: "new_explicit_turn", private_response: "must-not-reach-browser" };
}

test("saved request status rejects wrong identities and strips private data", () => {
  const parsed = parseTeachingRequestStatus(requestStatus(), "same-request");
  assert.equal(parsed.execution_budget.human_wait_seconds, 3600);
  assert.doesNotMatch(JSON.stringify(parsed), /must-not-reach-browser|lease|private_response/);
  assert.throws(() => parseTeachingRequestStatus(requestStatus(), "different-request"));
  assert.throws(() => parseTeachingRequestStatus({ ...requestStatus(), recovery_action: "replay_same_request" }, "same-request"));
  assert.throws(() => parseTeachingRequestStatus({ ...requestStatus(), execution_budget: { state: "running", active_used_seconds: -1 } }, "same-request"));
});

test("recovery response cannot update a newer view, account or course", () => {
  const requested = { epoch: 1, userId: "student-a", courseId: "course-a", editionId: "edition-a" };
  const current = { ...requested };
  assert.equal(recoveryMatchesView(requested, current), true);
  for (const changes of [{ epoch: 2 }, { userId: "student-b" }, { courseId: "course-b" }, { editionId: "edition-b" }]) {
    assert.equal(recoveryMatchesView(requested, { ...current, ...changes }), false);
  }
});

test("saved status response has an actual UTF8 byte cap and cancels oversized streams", async () => {
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new TextEncoder().encode("x".repeat(32_769)));
  }, cancel() { cancelled = true; } });
  await assert.rejects(boundedStatusJson(new Response(stream)), /exceeds limit/);
  assert.equal(cancelled, true);
  const parsed = await boundedStatusJson(Response.json({ safe: true }));
  assert.deepEqual(parsed, { safe: true });
});

test("stream preserves aggregate exhausted and busy failures for safe recovery", async () => {
  for (const code of ["EXECUTION_BUDGET_EXHAUSTED", "EXECUTION_BUDGET_BUSY"]) {
    const validator = makeStreamingValidator();
    await validator.handleBlock(startedBlock(), TEST_CONTEXT);
    const output = await validator.handleBlock(failedBlock(code), TEST_CONTEXT);
    assert.equal(output.kind, "terminal");
    assert.match(output.chunk, new RegExp(code));
  }
});
