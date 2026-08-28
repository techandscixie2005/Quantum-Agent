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

// PRD V3.1 P1-2: total upstream response size guard.  The BFF streams
// incrementally but still caps the total bytes to prevent a runaway
// upstream from consuming the browser connection indefinitely.  5MB is
// well above any legitimate teaching turn (the terminal event is the
// largest chunk and is bounded by the evidence packet size).
const MAX_STREAM_BYTES = 5_000_000;

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
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      else if (line && !line.startsWith(":")) {
        throw new TeachingContractError("SSE response contains an unsupported field");
      }
    }
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

// PRD V3.1 P1-2: incremental SSE stream parser.  The BFF forwards upstream
// events to the browser as they arrive instead of buffering the entire
// body.  ``progress`` events and ``: keepalive`` comment lines are passed
// through unchanged.  ``workflow.started`` is validated and re-emitted to
// the browser immediately.  Terminal events (``workflow.completed``,
// ``workflow.interrupted``, ``workflow.failed``) are buffered, validated
// against the teaching contract (scope, evidence digests, HITL redaction),
// and only then re-emitted to the browser.  If validation fails, the BFF
// emits a synthetic ``workflow.failed`` event so the browser sees a
// well-formed stream ending in a terminal event.
type ForwardedEvent =
  | Readonly<{ kind: "comment"; text: string }>
  | Readonly<{ kind: "progress"; raw: string }>
  | Readonly<{ kind: "started"; data: Readonly<{ workflow_version: string }> }>
  | Readonly<{ kind: "terminal"; raw: string; event: string; data: unknown }>
  | Readonly<{ kind: "unknown"; raw: string }> ;

type ParsedBlock =
  | Readonly<{ kind: "comment" }>
  | Readonly<{ kind: "event"; event: string; data: unknown; raw: string }>;

function parseSseBlock(block: string): ParsedBlock | null {
  if (!block.trim()) return null;
  // A comment-only block (``: keepalive``) is emitted as a kind so the
  // BFF can forward it without parsing.  Comment lines do not carry an
  // ``event:`` field.
  let isComment = true;
  for (const line of block.split("\n")) {
    if (line && !line.startsWith(":")) {
      isComment = false;
      break;
    }
  }
  if (isComment) return { kind: "comment" };
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    else if (line && !line.startsWith(":")) {
      throw new TeachingContractError("SSE response contains an unsupported field");
    }
  }
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    throw new TeachingContractError("SSE response contains invalid JSON");
  }
  return { kind: "event", event, data, raw: block + "\n\n" };
}

function classifyBlock(block: ParsedBlock): ForwardedEvent | null {
  if (block.kind === "comment") {
    return { kind: "comment", text: ": keepalive\n\n" };
  }
  if (block.event === "progress") {
    return { kind: "progress", raw: block.raw };
  }
  if (block.event === "workflow.started") {
    if (typeof block.data !== "object" || block.data === null || Array.isArray(block.data)) {
      throw new TeachingContractError("workflow.started payload is invalid");
    }
    const workflowVersion = (block.data as Record<string, unknown>).workflow_version;
    if (
      typeof workflowVersion !== "string" ||
      workflowVersion.length < 1 ||
      workflowVersion.length > 160
    ) {
      throw new TeachingContractError("workflow.started version is invalid");
    }
    return { kind: "started", data: { workflow_version: workflowVersion } };
  }
  if (
    block.event === "workflow.completed" ||
    block.event === "workflow.interrupted" ||
    block.event === "workflow.failed"
  ) {
    return { kind: "terminal", raw: block.raw, event: block.event, data: block.data };
  }
  // Unknown events are dropped (the upstream contract only allows the
  // events listed above).  We do NOT forward them to the browser.
  return { kind: "unknown", raw: block.raw };
}

async function validateTerminal(
  event: string,
  data: unknown,
  scope: TeachingScope,
  body: { mode: TeachingMode; conversation_id?: string | null },
): Promise<string> {
  if (event === "workflow.completed") {
    let result: TeachingTurnResult;
    try {
      result = parseTeachingTurnResult(data);
      assertTeachingScope(result, scope, body.mode);
      await assertEvidenceDigests(result.evidence_packet);
      if (body.conversation_id && result.conversation_id !== body.conversation_id) {
        throw new TeachingContractError("conversation id changed across the turn");
      }
    } catch {
      throw new TeachingContractError("completed event failed contract validation");
    }
    return encodeSse("workflow.completed", result);
  }
  if (event === "workflow.interrupted") {
    let pause: HitlInterruptResponse;
    try {
      pause = redactHitlProposedResponse(parseHitlInterruptResponse(data));
      assertHitlScope(pause, scope, body.mode);
      await assertEvidenceDigests(pause.artifacts.evidence_packet);
      if (body.conversation_id && pause.conversation_id !== body.conversation_id) {
        throw new TeachingContractError("conversation id changed at the HITL boundary");
      }
    } catch {
      throw new TeachingContractError("interrupted event failed contract validation");
    }
    return encodeSse("workflow.interrupted", pause);
  }
  if (event === "workflow.failed") {
    if (typeof data !== "object" || data === null || Array.isArray(data)) {
      throw new TeachingContractError("workflow.failed payload is invalid");
    }
    const code = (data as Record<string, unknown>).code;
    if (typeof code !== "string" || !SAFE_WORKFLOW_FAILURES.has(code)) {
      throw new TeachingContractError("workflow.failed code is invalid");
    }
    return encodeSse("workflow.failed", { code });
  }
  throw new TeachingContractError("unknown terminal event");
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
    // PRD V3.0 P1-2 + V3.1 P1-2: forward browser cancellation to the
    // backend so a user who navigates away or cancels the request does
    // not keep a long model call running.  We combine the incoming
    // request signal (browser cancellation) with a 240s timeout using
    // AbortSignal.any.  The 240s ceiling matches the proxy limit; the
    // backend's heartbeat + bounded retry budget keeps the perceived
    // latency well under this for normal turns.
    const timeoutSignal = AbortSignal.timeout(240_000);
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
      "INVALID_UPSTREAM_RESPONSE",
      "教学服务未返回事件流主体；本页已拒绝显示。",
      traceId,
    );
  }

  // PRD V3.1 P1-2: stream the upstream body through a TransformStream
  // that parses SSE blocks incrementally and forwards them to the
  // browser as they arrive.  ``progress`` and ``: keepalive`` comment
  // lines pass through unchanged; ``workflow.started`` is validated and
  // re-emitted; terminal events are buffered, validated, and re-emitted.
  // A bounded total size guard cancels upstream if the stream exceeds
  // MAX_STREAM_BYTES.
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = upstream.body!.getReader();
      let buffer = "";
      let totalBytes = 0;
      let startedEmitted = false;
      let terminalEmitted = false;
      let upstreamClosed = false;

      const failClosed = (code: string) => {
        if (!terminalEmitted) {
          controller.enqueue(encoder.encode(encodeSse("workflow.failed", { code })));
          terminalEmitted = true;
        }
      };

      try {
        while (true) {
          if (terminalEmitted) {
            // We already emitted the terminal event; drain any remaining
            // upstream bytes without forwarding them to the browser.
            await reader.cancel("terminal event already emitted");
            break;
          }
          const { done, value } = await reader.read();
          if (done) {
            upstreamClosed = true;
            break;
          }
          totalBytes += value.byteLength;
          if (totalBytes > MAX_STREAM_BYTES) {
            await reader.cancel("teaching stream exceeded the bounded payload size");
            failClosed("RETRIEVAL_UNAVAILABLE");
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          // Split on ``\n\n`` boundaries; keep the trailing partial block
          // in the buffer for the next chunk.
          let boundary: number;
          while ((boundary = buffer.indexOf("\n\n")) !== -1) {
            const blockText = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            let parsed: ParsedBlock | null;
            try {
              parsed = parseSseBlock(blockText);
            } catch {
              failClosed("RETRIEVAL_UNAVAILABLE");
              break;
            }
            if (parsed === null) continue;
            let forwarded: ForwardedEvent | null;
            try {
              forwarded = classifyBlock(parsed);
            } catch {
              failClosed("RETRIEVAL_UNAVAILABLE");
              break;
            }
            if (forwarded === null) continue;
            if (forwarded.kind === "comment") {
              controller.enqueue(encoder.encode(forwarded.text));
            } else if (forwarded.kind === "progress") {
              controller.enqueue(encoder.encode(forwarded.raw));
            } else if (forwarded.kind === "started") {
              if (!startedEmitted) {
                controller.enqueue(
                  encoder.encode(encodeSse("workflow.started", forwarded.data)),
                );
                startedEmitted = true;
              }
            } else if (forwarded.kind === "terminal") {
              if (terminalEmitted) continue;
              let terminalPayload: string;
              try {
                terminalPayload = await validateTerminal(
                  forwarded.event,
                  forwarded.data,
                  scope as TeachingScope,
                  { mode: body.mode, conversation_id: body.conversation_id },
                );
              } catch {
                failClosed("RETRIEVAL_UNAVAILABLE");
                break;
              }
              controller.enqueue(encoder.encode(terminalPayload));
              terminalEmitted = true;
            }
            // ``unknown`` events are dropped (not forwarded).
          }
        }
        if (!terminalEmitted && upstreamClosed) {
          // Upstream closed without a terminal event; emit a synthetic
          // failure so the browser sees a well-formed stream ending.
          failClosed("RETRIEVAL_UNAVAILABLE");
        }
      } catch {
        failClosed("RETRIEVAL_UNAVAILABLE");
      } finally {
        try {
          reader.releaseLock();
        } catch {
          // Already released; ignore.
        }
        controller.close();
      }
    },
    cancel(reason) {
      // Browser cancelled the stream; propagate cancellation to upstream.
      try {
        upstream.body?.cancel(reason);
      } catch {
        // Best-effort; the upstream may already be closed.
      }
    },
  });

  return new Response(stream, {
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
