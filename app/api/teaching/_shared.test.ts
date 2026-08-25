import assert from "node:assert/strict";
import test from "node:test";

import { TeachingContractError } from "@/app/components/teaching/contracts";
import { parseSseDocument } from "./_shared";

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
