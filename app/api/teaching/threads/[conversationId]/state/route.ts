import {
  parseTeachingTurnResult,
  assertTeachingScope,
  type TeachingScope,
} from "@/app/components/teaching/contracts";
import { UUID_PATTERN } from "@/app/components/knowledge/contracts";
import {
  agentError,
  quantumApiBaseUrl,
  safeAgentUpstreamMessage,
  studentSessionToken,
} from "@/app/api/agent/_shared";
import { assertEvidenceDigests } from "@/app/api/teaching/_shared";
import { parseScope, requireSameOrigin } from "@/app/api/phase1/_shared";

export const dynamic = "force-dynamic";

type RouteContext = Readonly<{ params: Promise<{ conversationId: string }> }>;

const MAX_STATE_BYTES = 4_000_000;

async function boundedJson(response: Response, maxBytes = MAX_STATE_BYTES): Promise<unknown> {
  const declared = Number(response.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new Error("upstream payload is too large");
  }
  if (!response.body) throw new Error("upstream payload is missing");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let total = 0;
  let text = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel("conversation state exceeded the bounded payload size");
      throw new Error("upstream payload is too large");
    }
    text += decoder.decode(value, { stream: true });
  }
  text += decoder.decode();
  return JSON.parse(text) as unknown;
}

/**
 * §13 refresh restoration: after a page reload the frontend restores only
 * ``conversation_id`` from localStorage; this route re-reads the durable
 * learning state from the authoritative backend so the actionable surface
 * (phase card, learning-native state) is restored instead of disappearing
 * until the next turn.  The embedded result snapshot is parsed and
 * scope-checked exactly like the streaming terminal path before it reaches
 * the browser.  A 404 upstream is forwarded as-is (unknown conversation).
 */
export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const { conversationId } = await context.params;
  const scope = parseScope(new URL(request.url).searchParams) as TeachingScope | null;
  if (!scope || !UUID_PATTERN.test(conversationId)) {
    return agentError(400, "INVALID_STATE_SCOPE", "学习状态线程的课程范围无效。");
  }

  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能读取学习状态。");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) return agentError(503, "BACKEND_NOT_CONFIGURED", "学习状态服务尚未配置。");

  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/teaching/threads/${conversationId}/state`;
  let upstream: Response;
  try {
    upstream = await fetch(new URL(path, baseUrl), {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    return agentError(503, "STATE_UNAVAILABLE", "无法读取当前学习状态。");
  }
  const traceId = upstream.headers.get("x-trace-id");
  if (!upstream.ok) {
    return agentError(
      upstream.status,
      `UPSTREAM_${upstream.status}`,
      safeAgentUpstreamMessage(upstream.status),
      traceId,
    );
  }

  let payload: unknown;
  try {
    payload = await boundedJson(upstream);
  } catch {
    return agentError(502, "INVALID_UPSTREAM_RESPONSE", "学习状态无法解析。", traceId);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload) ||
    (payload as Record<string, unknown>).conversation_id !== conversationId
  ) {
    return agentError(502, "INVALID_UPSTREAM_CONTRACT", "学习状态线程标识不匹配。", traceId);
  }
  const body = payload as Record<string, unknown>;
  if (body.result !== null && body.result !== undefined) {
    try {
      const result = parseTeachingTurnResult(body.result);
      if (result.conversation_id !== conversationId) {
        throw new Error("state result belongs to a different conversation");
      }
      assertTeachingScope(result, scope, result.policy.mode);
      await assertEvidenceDigests(result.evidence_packet);
    } catch {
      return agentError(
        502,
        "INVALID_UPSTREAM_CONTRACT",
        "学习状态快照未通过课程范围与证据校验。",
        traceId,
      );
    }
  }
  // Defense-in-depth: the transfer oracle (expected_value — the numerically
  // correct answer the student must derive themselves) never reaches the
  // browser.  The backend already redacts it; strip it here too so a
  // future backend regression cannot reintroduce the leak.
  const durablePhase = body.durable_phase;
  if (
    typeof durablePhase === "object" &&
    durablePhase !== null &&
    !Array.isArray(durablePhase) &&
    (durablePhase as Record<string, unknown>).transfer_verification !== null &&
    (durablePhase as Record<string, unknown>).transfer_verification !== undefined
  ) {
    body.durable_phase = {
      ...(durablePhase as Record<string, unknown>),
      transfer_verification: null,
    };
  }
  return Response.json(payload, {
    status: 200,
    headers: {
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
