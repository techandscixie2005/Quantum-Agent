import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { browserHttp, dbSnapshot, evidence, expectConflict, login, manifest, scope, terminal, turn, turnInput } from "./helpers";

test("a real Solo lock spans browser tabs and preserves the first correlated unaided answer", async ({ browser }, info) => {
  const m = await manifest();
  const student = await login(browser, m, "student", 4);
  const otherTab = await student.context.newPage();
  await otherTab.goto("/agent");
  const conversationId = m.actors.student[4].solo_ready_conversation_id;
  const armed = await turn(student.page, m, turnInput("进入独立评估。", {
    conversation_id: conversationId, learning_native: { request_transfer_task: true },
  }));
  expect(armed.learning_native?.phase).toBe("solo_active");
  expect(armed.learning_native?.solo?.assistance_locked).toBe(true);
  const taskId = armed.learning_native?.transfer?.task_id;
  expect(taskId).toBeTruthy();
  const mismatch = await turn(otherTab, m, turnInput("旧标签页的独立提交。", {
    conversation_id: conversationId,
    learning_native: { solo_attempt: { transfer_task_id: randomUUID(), response: "T=0", confidence: 0.9 } },
  }));
  expect(mismatch.scientific_results).toEqual([]);
  expect(mismatch.response.claims).toEqual([]);
  expect(mismatch.learning_native?.solo_first_attempt).toBeNull();
  const first = await turn(otherTab, m, turnInput("提交自己的第一个数值答案。", {
    conversation_id: conversationId,
    learning_native: { solo_attempt: { transfer_task_id: taskId, response: "T=0", confidence: 0.9 } },
  }));
  expect(first.scientific_results).toEqual([]);
  expect(first.learning_native?.solo_first_attempt?.response).toBe("T=0");
  const retry = await turn(student.page, m, turnInput("修订数值答案。", {
    conversation_id: conversationId,
    learning_native: { solo_attempt: { transfer_task_id: taskId, response: "T=0.5", confidence: 0.5 } },
  }));
  expect(retry.learning_native?.solo_first_attempt?.response).toBe("T=0");
  const forbidden = await browserHttp(otherTab, `/api/teaching/turns/stream?${scope(m)}`,
    turnInput("什么是量子隧穿？请给答案。"));
  expectConflict(forbidden);
  const blocked = await turn(otherTab, m, turnInput("什么是量子隧穿？请给答案。", { conversation_id: conversationId }));
  expect(blocked.scientific_results).toEqual([]);
  expect(blocked.response.claims).toEqual([]);
  expect(blocked.learning_native?.solo?.assistance_locked).toBe(true);
  const exportPath = `/api/teaching/threads/${conversationId}/export?${scope(m)}`;
  const shieldedExport = await browserHttp(student.page, exportPath);
  expect(shieldedExport.status, shieldedExport.text).toBe(409);
  expect(shieldedExport.text).not.toContain("expected_value");
  const exited = await turn(student.page, m, turnInput("主动结束本轮独立作答。", {
    conversation_id: conversationId, learning_native: { request_solo_exit: true },
  }));
  expect(exited.learning_native?.solo?.assistance_locked).toBe(false);
  const exported = await browserHttp(student.page, exportPath);
  expect(exported.status, exported.text).toBe(200);
  expect(exported.text).toContain("T=0");
  expect(exported.text).toContain("T=0.5");
  const persisted = await dbSnapshot(m, conversationId);
  await evidence(info, m, { scenario: "solo_cross_tab_immutable_attempt", conversation_id: conversationId,
    task_id: taskId, persisted });
  await student.context.close();
});

test("in-flight help and a concurrent Solo arm use the real database serialization boundary", async ({ browser }, info) => {
  const m = await manifest();
  const student = await login(browser, m, "student", 5);
  const otherTab = await student.context.newPage();
  await otherTab.goto("/agent");
  const before = await (await fetch(`${m.provider_url}/__test__/counts`)).json() as { held?: number };
  await fetch(`${m.provider_url}/__test__/hold`, { method: "POST" });
  let helpFinishedAt = 0;
  const help = browserHttp(student.page, `/api/teaching/turns/stream?${scope(m)}`,
    turnInput("[hold-provider] 什么是量子隧穿？")).then(value => {
      helpFinishedAt = Date.now(); return value;
    });
  await expect.poll(async () => {
    const counts = await (await fetch(`${m.provider_url}/__test__/counts`)).json() as { held?: number };
    return counts.held ?? 0;
  }).toBeGreaterThan(before.held ?? 0);
  const conversationId = m.actors.student[5].solo_ready_conversation_id;
  let armFinishedAt = 0;
  const arm = browserHttp(otherTab, `/api/teaching/turns/stream?${scope(m)}`,
    turnInput("进入独立评估。", { conversation_id: conversationId,
      learning_native: { request_transfer_task: true } })).then(value => {
        armFinishedAt = Date.now(); return value;
      });
  // Fault is local to the provider double; neither app nor database is mocked.
  await fetch(`${m.provider_url}/__test__/release`, { method: "POST" });
  const [helpResult, armResult] = await Promise.all([help, arm]);
  expect(helpResult.status, helpResult.text).toBe(200);
  expect(armResult.status, armResult.text).toBe(200);
  const arming = terminal(armResult.text);
  expect(arming.event, armResult.text).toBe("workflow.completed");
  const state = await browserHttp(otherTab, `/api/teaching/threads/${conversationId}/state?${scope(m)}`);
  expect(state.status, state.text).toBe(200);
  expect(state.text).toContain('"solo_active"');
  const subsequentHelp = await browserHttp(student.page, `/api/teaching/turns/stream?${scope(m)}`,
    turnInput("请替我完成独立评估。"));
  expectConflict(subsequentHelp);
  await evidence(info, m, { scenario: "provider_held_help_concurrent_solo", help_terminal: terminal(helpResult.text).event,
    arm_terminal: arming.event, help_finished_at: helpFinishedAt, solo_arm_finished_at: armFinishedAt,
    note: "Checks actual DB race and later assistance denial; fixture responses establish no educational efficacy." });
  await student.context.close();
});
