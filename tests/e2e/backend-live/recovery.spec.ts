import { expect, test } from "@playwright/test";
import { parseHitlInterruptResponse, parseTeachingTurnResult } from "../../../app/components/teaching/contracts";
import { browserHttp, dbSnapshot, evidence, login, manifest, restartApi, scope, terminal, turnInput } from "./helpers";

for (const restart of [false, true]) {
  test(`first-turn HITL queue and lost approval replay${restart ? " survive a PostgreSQL process restart" : " use real persisted records"}`, async ({ browser }, info) => {
    const m = await manifest();
    test.skip(restart && m.database_mode !== "postgresql", "SQLite checkpoints are process-local; this is not restart evidence.");
    test.skip(restart && m.credential_vault !== "shared_redis", "Restart identity/credential continuity requires the real shared Redis vault.");
    const index = restart ? 3 : 6;
    const student = await login(browser, m, "student", index);
    const teacher = await login(browser, m, "teacher", index);
    const request = turnInput("什么是量子隧穿？本轮需要 teacher approval。");
    const paused = await browserHttp(student.page, `/api/teaching/turns/stream?${scope(m)}`, request);
    expect(paused.status, paused.text).toBe(200);
    const event = terminal(paused.text);
    expect(event.event, paused.text).toBe("workflow.interrupted");
    const interrupt = parseHitlInterruptResponse(event.data);
    expect(interrupt.interrupt.reasons).toContain("teacher_approval_required");
    const before = await dbSnapshot(m, interrupt.conversation_id);
    expect(before.turns).toHaveLength(1);
    expect(before.turns[0].status).toBe("running");
    expect(before.traces).toBe(0); // A first-turn pause has no completed AgentTrace.
    const queuePath = `/api/teacher/pending-reviews?${scope(m)}`;
    expect((await browserHttp(student.page, queuePath)).status).toBe(403);
    const queue = await browserHttp(teacher.page, queuePath);
    expect(queue.status, queue.text).toBe(200);
    const item = (queue.body as { items: { turn_id: string; interrupt_id: string; student_user_id: string }[] }).items
      .find(item => item.turn_id === interrupt.turn_id);
    expect(item?.interrupt_id).toBe(interrupt.interrupt.interrupt_id);
    expect(item?.student_user_id).toBe(m.actors.student[index].user_id);
    if (restart) await restartApi(); // Kills the actual owned API process group, including workers.
    const base = `/api/teacher/conversations/${interrupt.conversation_id}`;
    const restored = await browserHttp(teacher.page, `${base}/interrupt?${scope(m)}`);
    expect(restored.status, restored.text).toBe(200);
    expect(parseHitlInterruptResponse(restored.body).interrupt.interrupt_id).toBe(interrupt.interrupt.interrupt_id);
    const resumePath = `${base}/resume?${scope(m)}`;
    const decision = { interrupt_id: interrupt.interrupt.interrupt_id, action: "approve",
      note: "SYNTHETIC integration review action; not actual teacher approval or classroom evidence." };
    expect((await browserHttp(student.page, resumePath, decision)).status).toBe(403);
    let committedText = "";
    let replayText = "";
    const decisions: unknown[] = [];
    await teacher.page.route(`**/api/teacher/conversations/${interrupt.conversation_id}/resume?**`, async route => {
      decisions.push(route.request().postDataJSON());
      const actual = await route.fetch();
      expect(actual.status(), await actual.text()).toBe(200);
      if (!committedText) {
        committedText = await actual.text();
        await route.abort("failed");
      } else {
        replayText = await actual.text();
        await route.fulfill({ response: actual });
      }
    });
    await teacher.page.goto(`/teacher/traces?${scope(m)}`);
    const pendingPanel = teacher.page.getByRole("region", { name: "待人工复核队列" });
    await pendingPanel.getByRole("button", { name: new RegExp(interrupt.turn_id.slice(0, 8)) }).click();
    await pendingPanel.getByLabel("复核理由").fill(decision.note);
    await pendingPanel.getByRole("button", { name: "批准并恢复执行", exact: true }).click();
    await expect(pendingPanel.getByRole("button", { name: "重试同一复核决定" })).toBeVisible();
    const committed = parseTeachingTurnResult(JSON.parse(committedText));
    const afterCommit = await dbSnapshot(m, interrupt.conversation_id);
    await pendingPanel.getByRole("button", { name: "重试同一复核决定" }).click();
    await expect(pendingPanel.getByRole("status")).toContainText("复核决定已保存");
    await expect.poll(() => replayText).not.toBe("");
    const replay = parseTeachingTurnResult(JSON.parse(replayText));
    expect(decisions).toEqual([decision, decision]);
    expect(replay.turn_id).toBe(committed.turn_id);
    expect(replay.turn_id).toBe(interrupt.turn_id);
    expect(replay.conversation_id).toBe(interrupt.conversation_id);
    const after = await dbSnapshot(m, interrupt.conversation_id);
    expect(after.turns).toHaveLength(1);
    expect(after.traces).toBe(1);
    expect(after.turns[0].hitl_decision_count).toBe(1);
    expect(after.learning_events).toEqual(afterCommit.learning_events);
    expect(after.turns[0].client_request_id).toBe(request.client_request_id);
    const queueAfter = await browserHttp(teacher.page, queuePath);
    expect(queueAfter.status, queueAfter.text).toBe(200);
    expect((queueAfter.body as { items: { turn_id: string }[] }).items.some(item => item.turn_id === interrupt.turn_id)).toBe(false);
    const ownState = await browserHttp(student.page, `/api/teaching/threads/${interrupt.conversation_id}/state?${scope(m)}`);
    expect(ownState.status, ownState.text).toBe(200);
    await evidence(info, m, { scenario: "hitl_lost_approval_replay", api_process_restarted: restart,
      conversation_id: interrupt.conversation_id, interrupt_id: interrupt.interrupt.interrupt_id, before, after });
    await Promise.all([student.context.close(), teacher.context.close()]);
  });
}
