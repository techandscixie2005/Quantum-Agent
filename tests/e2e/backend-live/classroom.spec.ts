import { expect, test } from "@playwright/test";
import { parseTeachingTurnResult } from "../../../app/components/teaching/contracts";
import { browserHttp, dbSnapshot, evidence, login, manifest, scope, terminal, turn, turnInput } from "./helpers";

test("real BFF replays a committed first turn after its response is lost", async ({ browser }, info) => {
  const m = await manifest();
  const { context, page } = await login(browser, m, "student", 0);
  const keys: string[] = [];
  let committedText = "";
  let replayText = "";
  await page.route("**/api/teaching/turns/stream?**", async route => {
    const body = route.request().postDataJSON() as { client_request_id: string };
    keys.push(body.client_request_id);
    if (!committedText) {
      const actual = await route.fetch();
      expect(actual.status()).toBe(200);
      committedText = await actual.text(); // Commit really happened; only delivery is faulted.
      await route.abort("failed");
    } else {
      const actual = await route.fetch();
      replayText = await actual.text();
      await route.fulfill({ response: actual }); // Forward the actual replay, without inventing a result.
    }
  });
  await page.getByLabel("给 Quantum Agent 的问题").fill("解释量子隧穿的机制并说明依据。");
  await page.getByRole("button", { name: "发送 / 运行", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试同一次提交" })).toBeVisible();
  const committedEvent = terminal(committedText);
  expect(committedEvent.event, committedText).toBe("workflow.completed");
  const committed = parseTeachingTurnResult(committedEvent.data);
  const afterCommit = await dbSnapshot(m, committed.conversation_id);
  await page.getByRole("button", { name: "重试同一次提交" }).click();
  await expect.poll(() => replayText).not.toBe("");
  const replay = parseTeachingTurnResult(terminal(replayText).data);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  expect(replay.turn_id).toBe(committed.turn_id);
  expect(replay.conversation_id).toBe(committed.conversation_id);
  const persisted = await dbSnapshot(m, committed.conversation_id);
  expect(persisted.turns).toHaveLength(1);
  expect(persisted.traces).toBe(1);
  expect(persisted.turns[0].client_request_id).toBe(keys[0]);
  expect(persisted.evidence).toBe(afterCommit.evidence);
  expect(persisted.learning_events).toEqual(afterCommit.learning_events);
  await evidence(info, m, { scenario: "lost_first_response", conversation_id: committed.conversation_id, persisted });
  await context.close();
});

test("teacher reasons change the next real teaching action while student identities stay isolated", async ({ browser }, info) => {
  const m = await manifest();
  const alice = await login(browser, m, "student", 1);
  const teacher = await login(browser, m, "teacher", 1);
  const bob = await login(browser, m, "student", 2);
  const first = await turn(alice.page, m, turnInput("什么是概率流？"));
  const path = `/api/teacher/conversations/${first.conversation_id}/reviews?${scope(m)}`;
  const probe = "请用概率流解释你的透射率定义，并说明固定哪些物理量。";
  const decision = { source_turn_id: first.turn_id, decision: "needs_follow_up",
    reason: "SYNTHETIC integration review fixture; not actual teacher approval or classroom evidence.",
    follow_up: "request_revision", probe, criterion_ratings: { "FB-R1": "not_assessed" } };
  expect((await browserHttp(alice.page, path, decision)).status).toBe(403);
  const review = await browserHttp(teacher.page, path, decision);
  expect(review.status, review.text).toBe(201);
  const next = await turn(alice.page, m, turnInput("概率流的定义是什么？", { conversation_id: first.conversation_id }));
  expect(next.release.release_level).toBe("question_only");
  expect(next.response.next_question).toBe(probe);
  expect(next.learning_native?.teacher_follow_up?.review_id).toBe((review.body as { review_id: string }).review_id);
  for (const route of ["state", "export", "interrupt"]) {
    const denied = await browserHttp(bob.page, `/api/teaching/threads/${first.conversation_id}/${route}?${scope(m)}`);
    expect([403, 404], `${route}: ${denied.text}`).toContain(denied.status);
    expect(denied.text).not.toContain(first.turn_id);
  }
  const exported = await browserHttp(alice.page, `/api/teaching/threads/${first.conversation_id}/export?${scope(m)}`);
  expect(exported.status, exported.text).toBe(200);
  expect(exported.text).toContain(first.turn_id);
  expect(exported.text).toContain(probe);
  await teacher.page.goto(`/teacher/traces?${scope(m)}`);
  await expect(teacher.page.getByTestId("classroom-review")).toContainText("SYNTHETIC integration review fixture");
  const persisted = await dbSnapshot(m, first.conversation_id);
  expect(persisted.turns).toHaveLength(2);
  expect(persisted.traces).toBe(2);
  await evidence(info, m, { scenario: "teacher_followup_and_identity_isolation", conversation_id: first.conversation_id, persisted });
  await Promise.all([alice.context.close(), teacher.context.close(), bob.context.close()]);
});
