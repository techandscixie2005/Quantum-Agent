import { parseTeachingTurnResult } from "../../teaching/contracts";
import fixtures from "./fixtures.json";

export const samples = [
  "为什么 E<V0 时仍可能透射？",
  "我预测透射概率为零，粒子不可能穿过。",
  "势垒右侧振幅应该很小但不为零。运行模拟看看。",
  "势垒内波函数指数衰减。",
  "边界连续使右侧振幅非零，透射概率不为零。我想挑战迁移任务。",
  "宽度增加到0.15 nm，T=0.120783，透射概率下降。",
];
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const event = (name: string, value: unknown) => `event: ${name}\ndata: ${JSON.stringify(value)}\n\n`;
const key = "qa_offline_v1";
// Explicitly injected into the offline route only; never patches global fetch.
export function createDemoAdapter() {
  let index = -1;
  let conversation = crypto.randomUUID();
  let last: (typeof fixtures.stages)[number] | null = null;
  const replays = new Map<string, string>();
  try { const saved = JSON.parse(sessionStorage.getItem(key) ?? "null"); if (saved) { index = saved.index; conversation = saved.conversation; last = saved.last; } } catch { /* fresh isolated session */ }
  const adapter: typeof fetch = async (input, init) => {
    const url = new URL(String(input), window.location.origin);
    if (url.pathname === "/api/agent/context") return json(fixtures.context);
    if (url.pathname.includes("/interrupt")) return new Response(null, { status: 204 });
    if (url.pathname.includes("/state")) return json({ mode: last?.policy.mode, result: last });
    if (url.pathname === "/api/teaching/turns/stream") {
      const body = JSON.parse(String(init?.body));
      if (body.client_request_id && replays.has(body.client_request_id)) return new Response(replays.get(body.client_request_id), {headers:{"Content-Type":"text/event-stream"}});
      const native = body.learning_native;
      const message = (native?.commitment?.candidate_prompt ?? native?.teach_back?.reconstruction ?? native?.solo_attempt?.response ?? body.message).trim();
      const requested = samples.indexOf(message);
      if (requested < 0 || requested > index + 1 || requested < index) return json({error: {code:"OFFLINE_SAMPLE_REQUIRED", message:"离线演示只支持当前阶段的教学样例；自由输入未判定正确。Solo 阶段请独立输入迁移答案。"}}, 422);
      if (requested === index && last) return new Response(event("workflow.completed", last), {headers:{"Content-Type":"text/event-stream"}});
      const next = structuredClone(fixtures.stages[requested]);
      next.conversation_id = conversation;
      next.policy.mode = body.mode;
      parseTeachingTurnResult(next);
      index = requested;
      last = next;
      last.conversation_id = conversation;
      last.turn_id = crypto.randomUUID();
      last.policy.mode = body.mode;
      sessionStorage.setItem(key, JSON.stringify({ index, conversation, last }));
      if (typeof window.dispatchEvent === "function") window.dispatchEvent(new Event("qa-offline-stage"));
      const stream = event("workflow.started", {workflow_version:last.workflow_version}) + event("progress", {step:"assemble",status:"completed",detail:"离线预设事件流 · 样例规则已匹配",elapsed_seconds:0}) + event("workflow.completed",last);
      if(body.client_request_id) replays.set(body.client_request_id,stream);
      return new Response(stream, {headers:{"Content-Type":"text/event-stream"}});
    }
    return json({detail:"离线入口未实现此接口；请使用离线实验室的附件与来源样例。"}, 501);
  };
  return { fetch: adapter, next: () => samples[Math.min(index + 1, samples.length - 1)], reset: () => { sessionStorage.removeItem(key); sessionStorage.removeItem("qa_offline_course_key"); sessionStorage.removeItem("qa_offline_conversation_id"); } };
}
