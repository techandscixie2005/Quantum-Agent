import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  TeachingContractError,
  assertHitlScope,
  assertTeachingScope,
  parseHitlInterruptResponse,
  parseTeachingTurnRequest,
  parseTeachingTurnResult,
  redactHitlProposedResponse,
  type EvidencePacket,
  type HitlInterruptResponse,
  type TeachingScope,
  type TeachingTurnResult,
} from "@/app/components/teaching/contracts";
import {
  parseScope,
  readJsonObject,
  requireSameOrigin,
} from "@/app/api/phase1/_shared";

const TRACE_ID_PATTERN = /^[a-zA-Z0-9._:-]{1,128}$/;
const SAFE_WORKFLOW_FAILURES = new Set([
  "CONVERSATION_CONFLICT",
  "RETRIEVAL_UNAVAILABLE",
]);

export function teachingError(
  status: number,
  code: string,
  message: string,
  traceId?: string | null,
): NextResponse {
  return NextResponse.json(
    {
      error: {
        code,
        message,
        ...(traceId && TRACE_ID_PATTERN.test(traceId) ? { trace_id: traceId } : {}),
      },
    },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

function backendBaseUrl(): URL | null {
  const configured = process.env.QUANTUM_API_BASE_URL?.trim();
  if (!configured) return null;
  try {
    const parsed = new URL(configured.endsWith("/") ? configured : `${configured}/`);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (parsed.username || parsed.password) return null;
    return parsed;
  } catch {
    return null;
  }
}

function safeUpstreamMessage(status: number): string {
  if (status === 401) return "课程会话已失效，请重新登录后再试。";
  if (status === 403) return "当前身份不是这门课程的有效成员。";
  if (status === 404) return "请求的课程版本不存在或尚未开放。";
  if (status === 409) return "学习记录已由另一次请求更新；请保留输入并重试。";
  if (status === 422) return "教学请求未通过后端校验，请检查输入范围。";
  if (status >= 500) return "教学工作流当前不可用；页面不会用生成内容替代结果。";
  return "教学服务拒绝了该请求。";
}

type ParsedSse =
  | Readonly<{ event: "workflow.started"; data: Readonly<{ workflow_version: string }> }>
  | Readonly<{ event: "workflow.completed"; data: unknown }>
  | Readonly<{ event: "workflow.interrupted"; data: unknown }>
  | Readonly<{ event: "workflow.failed"; data: Readonly<{ code: string }> }>;

export function parseSseDocument(value: string): readonly ParsedSse[] {
  const events: ParsedSse[] = [];
  for (const block of value.replace(/\r\n/g, "\n").split("\n\n")) {
    if (!block.trim()) continue;
    let event = "message";
    const dataLines: string[] = [];
    let isCommentOnly = true;
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
        isCommentOnly = false;
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
        isCommentOnly = false;
      } else if (line && !line.startsWith(":")) {
        throw new TeachingContractError("SSE response contains an unsupported field");
      }
    }
    // PRD V3.1 P1-2: comment-only blocks (``: keepalive``) and ``progress``
    // events are emitted by the backend between ``workflow.started`` and the
    // terminal event to keep the connection alive and report step progress.
    // They carry no terminal contract; skip them so the buffered parser only
    // considers the workflow lifecycle events.
    if (isCommentOnly || event === "progress") continue;
    let data: unknown;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      throw new TeachingContractError("SSE response contains invalid JSON");
    }
    if (event === "workflow.started") {
      if (typeof data !== "object" || data === null || Array.isArray(data)) {
        throw new TeachingContractError("workflow.started payload is invalid");
      }
      const workflowVersion = (data as Record<string, unknown>).workflow_version;
      if (typeof workflowVersion !== "string" || workflowVersion.length < 1 || workflowVersion.length > 160) {
        throw new TeachingContractError("workflow.started version is invalid");
      }
      events.push({ event, data: { workflow_version: workflowVersion } });
    } else if (event === "workflow.completed" || event === "workflow.interrupted") {
      events.push({ event, data });
    } else if (event === "workflow.failed") {
      if (typeof data !== "object" || data === null || Array.isArray(data)) {
        throw new TeachingContractError("workflow.failed payload is invalid");
      }
      const code = (data as Record<string, unknown>).code;
      if (typeof code !== "string" || !SAFE_WORKFLOW_FAILURES.has(code)) {
        throw new TeachingContractError("workflow.failed code is invalid");
      }
      events.push({ event, data: { code } });
    } else {
      throw new TeachingContractError("SSE response contains an unknown event");
    }
  }
  return events;
}

function encodeSse(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

async function readBoundedText(response: Response, maxBytes = 2_000_000): Promise<string> {
  if (!response.body) throw new TeachingContractError("SSE response body is missing");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let total = 0;
  let output = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel("teaching response exceeded the bounded payload size");
      throw new TeachingContractError("SSE response exceeds the bounded payload size");
    }
    output += decoder.decode(value, { stream: true });
  }
  return output + decoder.decode();
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function assertEvidenceDigests(packet: EvidencePacket): Promise<void> {
  await Promise.all(
    packet.evidence.map(async (evidence, index) => {
      const [chunkDigest, evidenceDigest] = await Promise.all([
        sha256Hex(evidence.source_chunk),
        sha256Hex(evidence.evidence_snippet),
      ]);
      if (
        chunkDigest !== evidence.source_chunk_sha256 ||
        evidenceDigest !== evidence.evidence_sha256
      ) {
        throw new TeachingContractError(`evidence[${index}] digest does not match its text`);
      }
    }),
  );
}

export async function proxyTeachingTurn(request: Request): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const scope = parseScope(new URL(request.url).searchParams);
  if (!scope) {
    return teachingError(400, "INVALID_SCOPE", "course_id 与 curriculum_edition_id 必须是有效 UUID。");
  }

  const rawBody = await readJsonObject(request);
  if (!rawBody) {
    return teachingError(400, "INVALID_REQUEST", "请求正文必须是 JSON 对象。");
  }

  let body;
  try {
    body = parseTeachingTurnRequest(rawBody);
  } catch {
    return teachingError(400, "INVALID_REQUEST", "教学请求字段无效或超出允许范围。");
  }

  const sessionToken = (await cookies()).get("qa_session")?.value;
  if (!sessionToken) {
    return teachingError(401, "AUTH_REQUIRED", "需要已登录的课程会话才能进入教学工作流。");
  }
  if (sessionToken.length > 4_096) {
    return teachingError(401, "INVALID_SESSION", "课程会话格式无效，请重新登录。");
  }

  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return teachingError(
      503,
      "BACKEND_NOT_CONFIGURED",
      "教学服务地址尚未配置；页面不会显示示例答案或推测结果。",
    );
  }

  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    "/teaching/turns/stream";
  let upstream: Response;
  try {
    // PRD V3.0 P1-2: forward browser cancellation to the backend so a user
    // who navigates away or cancels the request does not keep a long model
    // call running.  We combine the incoming request signal (browser
    // cancellation) with a 300s timeout using AbortSignal.any.  The 300s
    // ceiling gives the real model room for deep-reasoning fallback (the
    // Coding Agent may fall back from code_primary to reasoning_primary).
    const timeoutSignal = AbortSignal.timeout(300_000);
    const combinedSignal = request.signal
      ? AbortSignal.any([request.signal, timeoutSignal])
      : timeoutSignal;
    upstream = await fetch(new URL(path, baseUrl), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${sessionToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: combinedSignal,
    });
  } catch {
    return teachingError(
      503,
      "BACKEND_UNAVAILABLE",
      "无法连接教学工作流；当前输入仍保留在页面中，可以稍后重试。",
    );
  }

  const traceId = upstream.headers.get("x-trace-id");
  if (!upstream.ok) {
    return teachingError(
      upstream.status,
      `UPSTREAM_${upstream.status}`,
      safeUpstreamMessage(upstream.status),
      traceId,
    );
  }
  if (!(upstream.headers.get("content-type") ?? "").toLowerCase().startsWith("text/event-stream")) {
    return teachingError(
      502,
      "INVALID_UPSTREAM_RESPONSE",
      "教学服务未返回可验证的事件流；本页已拒绝显示。",
      traceId,
    );
  }

  let events: readonly ParsedSse[];
  try {
    events = parseSseDocument(await readBoundedText(upstream));
  } catch {
    return teachingError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "教学事件流不符合固定工作流契约；本页已拒绝显示未经验证的数据。",
      traceId,
    );
  }

  const started = events.filter((event) => event.event === "workflow.started");
  const completed = events.filter((event) => event.event === "workflow.completed");
  const interrupted = events.filter((event) => event.event === "workflow.interrupted");
  const failed = events.filter((event) => event.event === "workflow.failed");
  if (
    started.length !== 1 ||
    completed.length + interrupted.length + failed.length !== 1 ||
    events.length !== 2
  ) {
    return teachingError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "教学事件流缺少唯一的开始或结束事件；本页已拒绝显示。",
      traceId,
    );
  }

  let responseBody: string;
  if (completed.length === 1) {
    let result: TeachingTurnResult;
    try {
      result = parseTeachingTurnResult(completed[0]?.data);
      assertTeachingScope(result, scope as TeachingScope, body.mode);
      await assertEvidenceDigests(result.evidence_packet);
      if (body.conversation_id && result.conversation_id !== body.conversation_id) {
        throw new TeachingContractError("conversation id changed across the turn");
      }
    } catch {
      return teachingError(
        502,
        "INVALID_UPSTREAM_CONTRACT",
        "教学结果未通过范围、证据或科学结果校验；本页已拒绝显示。",
        traceId,
      );
    }
    responseBody =
      encodeSse("workflow.started", started[0]?.data) +
      encodeSse("workflow.completed", result);
  } else if (interrupted.length === 1) {
    let pause: HitlInterruptResponse;
    try {
      pause = redactHitlProposedResponse(
        parseHitlInterruptResponse(interrupted[0]?.data),
      );
      assertHitlScope(pause, scope as TeachingScope, body.mode);
      await assertEvidenceDigests(pause.artifacts.evidence_packet);
      if (body.conversation_id && pause.conversation_id !== body.conversation_id) {
        throw new TeachingContractError("conversation id changed at the HITL boundary");
      }
    } catch {
      return teachingError(
        502,
        "INVALID_UPSTREAM_CONTRACT",
        "人工复核状态未通过范围、证据或权限契约；本页已拒绝显示。",
        traceId,
      );
    }
    responseBody =
      encodeSse("workflow.started", started[0]?.data) +
      encodeSse("workflow.interrupted", pause);
  } else {
    responseBody =
      encodeSse("workflow.started", started[0]?.data) +
      encodeSse("workflow.failed", failed[0]?.data);
  }

  return new Response(responseBody, {
    status: 200,
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": "text/event-stream; charset=utf-8",
      "X-Accel-Buffering": "no",
      "X-Content-Type-Options": "nosniff",
      ...(traceId && TRACE_ID_PATTERN.test(traceId) ? { "X-Trace-Id": traceId } : {}),
    },
  });
}
