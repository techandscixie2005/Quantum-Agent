import { expect, test } from "@playwright/test";
import { browserHttp, dbSnapshot, evidence, login, manifest, scope, terminal } from "./helpers";

for (const pending of [false, true]) {
  test(`saved-request recovery UI restores a real ${pending ? "first-turn pause" : "completed first turn"} without another model run`, async ({ browser }, info) => {
    const m = await manifest();
    const index = pending ? 8 : 7;
    const student = await login(browser, m, "student", index);
    await student.page.getByRole("button", { name: "概念模式 · 解释与迁移", exact: true }).click();
    let requestId = "";
    let actualText = "";
    let submitted = 0;
    await student.page.route("**/api/teaching/turns/stream?**", async route => {
      submitted++;
      requestId = (route.request().postDataJSON() as { client_request_id: string }).client_request_id;
      const actual = await route.fetch();
      expect(actual.status()).toBe(200);
      actualText = await actual.text();
      await route.abort("failed");
    });
    await student.page.getByLabel("给 Quantum Agent 的问题").fill(pending
      ? "什么是概率流？本轮需要 teacher approval。"
      : "解释概率流的依据，并先检查我的判断。");
    await student.page.getByRole("button", { name: "发送 / 运行", exact: true }).click();
    await expect(student.page.getByRole("button", { name: "检查并恢复保存状态" })).toBeVisible();
    const actual = terminal(actualText);
    expect(actual.event, actualText).toBe(pending ? "workflow.interrupted" : "workflow.completed");
    const ids = actual.data as { conversation_id: string; turn_id: string };
    const before = await dbSnapshot(m, ids.conversation_id);
    const countsBefore = await (await fetch(`${m.provider_url}/__test__/counts`)).json() as object;
    await student.page.getByRole("button", { name: "检查并恢复保存状态" }).click();
    await expect(student.page.getByTestId("request-recovery-status")).toContainText(pending ? "等待复核" : "已完成");
    if (pending) await expect(student.page.getByRole("button", { name: "先完成上方复核" })).toBeDisabled();
    const saved = await browserHttp(student.page, `/api/teaching/requests/status?${scope(m)}&client_request_id=${requestId}`);
    expect(saved.status, saved.text).toBe(200);
    expect(saved.body).toMatchObject({ client_request_id: requestId, conversation_id: ids.conversation_id,
      turn_id: ids.turn_id, status: pending ? "running" : "completed",
      recovery_action: pending ? "review_required" : "replay_same_request" });
    expect(saved.text).not.toContain('"user_message"');
    expect(saved.text).not.toContain('"response"');
    const after = await dbSnapshot(m, ids.conversation_id);
    expect(after).toEqual(before);
    expect(submitted).toBe(1);
    const countsAfter = await (await fetch(`${m.provider_url}/__test__/counts`)).json() as object;
    expect(countsAfter).toEqual(countsBefore);
    await evidence(info, m, { scenario: "saved_request_status_ui", pending,
      conversation_id: ids.conversation_id, actual_status: saved.body, persisted: after });
    await student.context.close();
  });
}
