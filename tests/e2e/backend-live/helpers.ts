import { execFile } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { expect, type Browser, type Page, type TestInfo } from "@playwright/test";
import { parseTeachingTurnResult, type TeachingTurnResult } from "../../../app/components/teaching/contracts";

const exec = promisify(execFile);
export const output = path.resolve("test-results/backend-live");
export type Actor = { user_id: string; classroom_access_token: string; solo_ready_conversation_id: string };
export type Manifest = {
  fixture_label: string; run_id: string; course_id: string; edition_id: string;
  database_mode: "sqlite" | "postgresql"; python: string; web_url: string; provider_url: string;
  api_workers: number; credential_vault: string; actors: Record<"student" | "teacher" | "ta", Actor[]>;
};
export type HttpResult = { status: number; text: string; body: unknown };

export async function manifest(): Promise<Manifest> {
  return JSON.parse(await readFile(path.join(output, "manifest.json"), "utf8")) as Manifest;
}
export function scope(m: Manifest): string {
  return `course_id=${m.course_id}&curriculum_edition_id=${m.edition_id}`;
}
export async function login(browser: Browser, m: Manifest, role: "student" | "teacher" | "ta", index: number) {
  const context = await browser.newContext({ baseURL: m.web_url });
  const page = await context.newPage();
  await page.goto("/agent");
  await page.getByLabel("个人课堂访问凭证").fill(m.actors[role][index].classroom_access_token);
  await page.getByLabel("USTC API Key").fill("backend-live-provider-fixture-key");
  const loginResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/auth/login");
  await page.getByRole("button", { name: "连接并进入学习空间" }).click();
  const authenticated = await loginResponse;
  expect(authenticated.status(), await authenticated.text()).toBe(200);
  await expect(page.getByLabel("给 Quantum Agent 的问题")).toBeVisible();
  const identity = await browserHttp(page, "/api/agent/context");
  expect(identity.status).toBe(200);
  expect((identity.body as { user_id: string }).user_id).toBe(m.actors[role][index].user_id);
  return { context, page };
}

/** Real same-origin fetch in the authenticated browser, including the real BFF. */
export async function browserHttp(page: Page, url: string, body?: object): Promise<HttpResult> {
  return page.evaluate(async ({ url, body }) => {
    const response = await fetch(url, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const text = await response.text();
    let parsed: unknown = null;
    try { parsed = JSON.parse(text); } catch { /* SSE is decoded by terminal(). */ }
    return { status: response.status, text, body: parsed };
  }, { url, body });
}

export function terminal(raw: string): { event: string; data: unknown } {
  const events = raw.replaceAll("\r\n", "\n").split("\n\n").map(block => ({
    event: block.split("\n").find(line => line.startsWith("event:"))?.slice(6).trim(),
    data: block.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n"),
  }));
  const item = events.findLast(item => ["workflow.completed", "workflow.interrupted", "workflow.failed"].includes(item.event ?? ""));
  if (!item?.event || !item.data) throw new Error(`No real terminal event: ${raw.slice(0, 1000)}`);
  return { event: item.event, data: JSON.parse(item.data) as unknown };
}
export function expectConflict(response: HttpResult): void {
  if (response.status === 409) return;
  expect(response.status, response.text).toBe(200); // SSE headers precede workflow admission.
  expect(terminal(response.text), response.text).toEqual({ event: "workflow.failed", data: { code: "CONVERSATION_CONFLICT" } });
}
export function turnInput(message: string, overrides: object = {}) {
  return { conversation_id: null, mode: "learn_concepts", message, student_attempt: null,
    attachment_ids: [], scientific_request: null, learning_native: null,
    client_request_id: crypto.randomUUID(),
    course_package: { package_id: "finite-barriers", version: "1.0.0" }, ...overrides };
}
export async function turn(page: Page, m: Manifest, input: object): Promise<TeachingTurnResult> {
  const response = await browserHttp(page, `/api/teaching/turns/stream?${scope(m)}`, input);
  expect(response.status, response.text).toBe(200);
  const event = terminal(response.text);
  expect(event.event, response.text).toBe("workflow.completed");
  return parseTeachingTurnResult(event.data);
}
export async function dbSnapshot(m: Manifest, conversationId: string) {
  const root = process.cwd();
  const { stdout } = await exec(m.python, [path.join(root, "tests/e2e/backend-live/seed.py"),
    "snapshot", "--manifest", path.join(output, "manifest.json"), "--conversation-id", conversationId], {
    cwd: path.join(root, "services/api"),
    env: { ...process.env, PYTHONPATH: path.join(root, "services/api"), PYTHONUTF8: "1" },
  });
  return JSON.parse(stdout) as {
    turns: { id: string; conversation_id: string; status: string; client_request_id: string; sequence: number; hitl_decision_count: number }[];
    traces: number; evidence: number; reviews: number;
    learning_events: { turn_id: string; kind: string; observation: string; payload: Record<string, unknown> }[];
  };
}
export async function restartApi(): Promise<void> {
  const nonce = crypto.randomUUID();
  await writeFile(path.join(output, "control-request.json"), JSON.stringify({ nonce, action: "restart_api" }));
  await expect.poll(async () => {
    try {
      const result = JSON.parse(await readFile(path.join(output, "control-response.json"), "utf8")) as { nonce: string; ok: boolean };
      return result.nonce === nonce && result.ok;
    } catch { return false; }
  }, { timeout: 60_000 }).toBe(true);
}
export async function evidence(info: TestInfo, m: Manifest, detail: object) {
  await info.attach("synthetic-integration-evidence", { contentType: "application/json", body: JSON.stringify({
    label: m.fixture_label, actual_classroom_results: false, actual_teacher_approval: false,
    database_mode: m.database_mode, api_workers: m.api_workers, credential_vault: m.credential_vault,
    run_id: m.run_id, ...detail,
  }, null, 2) });
}
