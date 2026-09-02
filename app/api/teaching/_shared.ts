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
  type TeachingMode,
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

/**
 * Parse a fully-buffered SSE document into the typed lifecycle events.
 *
 * Kept for unit tests and as the reference parser.  The streaming proxy
 * (``proxyTeachingTurn``) uses ``parseSseBlock`` incrementally so the browser
 * sees ``workflow.started``, ``progress``, and heartbeat comments without
 * waiting for the terminal event.
 */
export function parseSseDocument(value: string): readonly ParsedSse[] {
  const events: ParsedSse[] = [];
  for (const block of value.replace(/\r\n/g, "\n").split("\n\n")) {
    if (!block.trim()) continue;
    const parsed = parseSseBlock(block);
    if (parsed === null) continue; // comment-only / progress: skip
    events.push(parsed);
  }
  return events;
}

/**
 * Parse a single SSE block (already split on ``\n\n`` boundaries) into a
 * typed lifecycle event, or return ``null`` for comment-only blocks and
 * ``progress`` events (which carry no terminal contract).
 *
 * Throws ``TeachingContractError`` for malformed blocks so the caller can
 * fail the stream with a 502-equivalent error rather than silently
 * swallowing the violation.
 */
function parseSseBlock(block: string): ParsedSse | null {
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
  // They carry no terminal contract; skip them.
  if (isCommentOnly || event === "progress") return null;
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
    return { event, data: { workflow_version: workflowVersion } };
  }
  if (event === "workflow.completed" || event === "workflow.interrupted") {
    return { event, data };
  }
  if (event === "workflow.failed") {
    if (typeof data !== "object" || data === null || Array.isArray(data)) {
      throw new TeachingContractError("workflow.failed payload is invalid");
    }
    const code = (data as Record<string, unknown>).code;
    if (typeof code !== "string" || !SAFE_WORKFLOW_FAILURES.has(code)) {
      throw new TeachingContractError("workflow.failed code is invalid");
    }
    return { event, data: { code } };
  }
  throw new TeachingContractError("SSE response contains an unknown event");
}

function encodeSse(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
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

/**
 * Streaming SSE validator state machine.
 *
 * The BFF reads the upstream SSE body incrementally, splits it on ``\n\n``
 * block boundaries, and forwards each block to the browser as it arrives.
 * This class enforces the terminal contract while streaming:
 *
 * - ``workflow.started`` must arrive first and exactly once; it is forwarded
 *   immediately.
 * - ``progress`` events and ``: keepalive`` comments are forwarded
 *   immediately (the browser shows a progress indicator).
 * - The terminal event (``workflow.completed`` / ``workflow.interrupted`` /
 *   ``workflow.failed``) is validated before forwarding: evidence digests,
 *   scope, conversation-id stability, and HITL scope are checked.  Exactly
 *   one terminal event is allowed; after it the stream closes.
 * - Any contract violation (unknown event, bad JSON, second terminal,
 *   missing ``workflow.started``, validation failure) terminates the stream
 *   with a ``workflow.failed`` SSE event carrying ``INVALID_UPSTREAM_CONTRACT``
 *   so the browser never displays an unverified result.
 */
interface StreamingValidator {
  /** Forward a raw SSE block verbatim, or return an error event to emit. */
  handleBlock(
    block: string,
    context: ValidationContext,
  ): Promise<{ kind: "forward"; chunk: string } | { kind: "terminal"; chunk: string } | { kind: "error"; chunk: string }>;
  /** True once the unique terminal event has been forwarded. */
  readonly finished: boolean;
}

interface ValidationContext {
  scope: TeachingScope;
  mode: TeachingMode;
  conversationId: string | null;
}

/**
 * Construct a streaming SSE validator.  Exported for unit tests so the
 * incremental forwarding logic (``workflow.started`` forwarded immediately,
 * ``progress`` and keepalive comments forwarded verbatim, terminal event
 * validated before forwarding, contract violations produce a
 * ``workflow.failed`` event) can be exercised without a live upstream.
 */
export function makeStreamingValidator(): StreamingValidator {
  let startedSeen = false;
  let terminalSeen = false;
  let finished = false;

  return {
    get finished() {
      return finished;
    },
    async handleBlock(block, context) {
      if (finished) return { kind: "forward", chunk: "" };
      const trimmed = block.trim();
      if (!trimmed) return { kind: "forward", chunk: "" };
      // Comment-only keepalive blocks: forward verbatim (browsers silently
      // consume ``:`` lines per the SSE spec; we still forward so any
      // non-browser client and the dev-tools network panel see activity).
      if (trimmed.startsWith(":")) {
        return { kind: "forward", chunk: `${block}\n\n` };
      }
      let parsed: ParsedSse | null;
      try {
        parsed = parseSseBlock(block);
      } catch {
        finished = true;
        return { kind: "error", chunk: encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" }) };
      }
      if (parsed === null) {
        // progress event: forward verbatim so the browser can render stage
        // progress without waiting for the terminal event.
        return { kind: "forward", chunk: `${block}\n\n` };
      }
      if (parsed.event === "workflow.started") {
        if (startedSeen) {
          finished = true;
          return { kind: "error", chunk: encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" }) };
        }
        startedSeen = true;
        return { kind: "forward", chunk: encodeSse("workflow.started", parsed.data) };
      }
      // Terminal event.
      if (!startedSeen) {
        finished = true;
        return { kind: "error", chunk: encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" }) };
      }
      if (terminalSeen) {
        finished = true;
        return { kind: "error", chunk: encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" }) };
      }
      terminalSeen = true;
      if (parsed.event === "workflow.completed") {
        let result: TeachingTurnResult;
        try {
          result = parseTeachingTurnResult(parsed.data);
          assertTeachingScope(result, context.scope, context.mode);
          await assertEvidenceDigests(result.evidence_packet);
          if (context.conversationId && result.conversation_id !== context.conversationId) {
            throw new TeachingContractError("conversation id changed across the turn");
          }
        } catch {
          return { kind: "error", chunk: encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" }) };
        }
        finished = true;
        return { kind: "terminal", chunk: encodeSse("workflow.completed", result) };
      }
      if (parsed.event === "workflow.interrupted") {
        let pause: HitlInterruptResponse;
        try {
          pause = redactHitlProposedResponse(parseHitlInterruptResponse(parsed.data));
          assertHitlScope(pause, context.scope, context.mode);
          await assertEvidenceDigests(pause.artifacts.evidence_packet);
          if (context.conversationId && pause.conversation_id !== context.conversationId) {
            throw new TeachingContractError("conversation id changed at the HITL boundary");
          }
        } catch {
          return { kind: "error", chunk: encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" }) };
        }
        finished = true;
        return { kind: "terminal", chunk: encodeSse("workflow.interrupted", pause) };
      }
      // workflow.failed: already validated by parseSseBlock (safe code).
      finished = true;
      return { kind: "terminal", chunk: encodeSse("workflow.failed", parsed.data) };
    },
  };
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
    // PRD V3.0 P1-2 + V3.2 streaming: forward browser cancellation to the
    // backend so a user who navigates away or cancels the request does not
    // keep a long model call running.  We combine the incoming request
    // signal (browser cancellation) with a 300s timeout using AbortSignal.any.
    // The 300s ceiling gives the real model room for deep-reasoning fallback
    // (the Coding Agent may fall back from code_primary to reasoning_primary).
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
  if (!upstream.body) {
    return teachingError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "教学事件流缺少响应体；本页已拒绝显示。",
      traceId,
    );
  }

  // PRD 3.2 One Stream: the backend emits ``workflow.started`` immediately,
  // then ``progress`` events + ``: keepalive`` heartbeats, then one terminal
  // event.  We stream each validated block to the browser as it arrives rather
  // than buffering the whole body, so intermediate LearningEvents reach the UI
  // before the workflow finishes.  The incremental validator reuses
  // ``makeStreamingValidator`` (state machine below); the streaming wrapper is
  // pull-based and backpressure-aware (each blocked block is enqueued from
  // ``pull``, which is only re-entered once the consumer has drained the
  // queue) — this fixes the V3.2 revert's root cause, which was a synchronous
  // ``controller.enqueue`` loop in ``start`` that ignored backpressure and
  // closed the controller before the reader drained.
  const context: ValidationContext = {
    scope: scope as TeachingScope,
    mode: body.mode,
    conversationId: body.conversation_id,
  };

  return new Response(
    streamValidatedUpstream(upstream, makeStreamingValidator(), context),
    {
      status: 200,
      headers: {
        "Cache-Control": "private, no-store",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
        "X-Content-Type-Options": "nosniff",
        ...(traceId && TRACE_ID_PATTERN.test(traceId) ? { "X-Trace-Id": traceId } : {}),
      },
    },
  );
}

const MAX_STREAM_BYTES = 2_000_000;

/**
 * Wrap an upstream SSE response in a validating, backpressure-aware stream.
 *
 * Exported for the timing regression test so a synthetic upstream stream can
 * prove an intermediate ``progress`` block is observable before the terminal
 * event resolves.
 */
export function streamValidatedUpstream(
  upstream: Response,
  validator: StreamingValidator,
  context: ValidationContext,
): ReadableStream<Uint8Array> {
  if (!upstream.body) throw new TeachingContractError("SSE response body is missing");
  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let pending = "";
  let total = 0;

  const failClosed = (controller: ReadableStreamDefaultController<Uint8Array>) => {
    controller.enqueue(
      encoder.encode(encodeSse("workflow.failed", { code: "INVALID_UPSTREAM_CONTRACT" })),
    );
    controller.close();
  };

  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (validator.finished) {
        controller.close();
        return;
      }

      let block: string;
      // Extend the pending buffer until we hold a complete ``\n\n``-terminated
      // SSE block, then validate and forward exactly one block per pull.
      for (;;) {
        const boundary = pending.indexOf("\n\n");
        if (boundary !== -1) {
          block = pending.slice(0, boundary + 2);
          pending = pending.slice(boundary + 2);
          break;
        }
        const { done, value } = await reader.read();
        if (done) {
          await reader.cancel();
          failClosed(controller);
          return;
        }
        total += value.byteLength;
        if (total > MAX_STREAM_BYTES) {
          await reader.cancel("teaching response exceeded the bounded payload size");
          failClosed(controller);
          return;
        }
        pending += decoder.decode(value, { stream: true });
      }

      const out = await validator.handleBlock(block, context);
      if (out.chunk) controller.enqueue(encoder.encode(out.chunk));
      if (out.kind === "terminal" || out.kind === "error") {
        await reader.cancel();
        controller.close();
      }
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });
}
