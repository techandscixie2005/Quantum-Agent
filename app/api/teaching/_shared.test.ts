import assert from "node:assert/strict";
import test from "node:test";

import { TeachingContractError } from "@/app/components/teaching/contracts";
import { makeStreamingValidator, parseSseDocument } from "./_shared";

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
