import {
  assertHitlScope,
  parseHitlInterruptResponse,
  redactHitlProposedResponse,
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

async function boundedJson(response: Response, maxBytes = 2_000_000): Promise<unknown> {
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
      await reader.cancel("interrupt inspection exceeded the bounded payload size");
      throw new Error("upstream payload is too large");
    }
    text += decoder.decode(value, { stream: true });
  }
  text += decoder.decode();
  return JSON.parse(text) as unknown;
}

/**
 * Release-review P1 fix: recover a pending HITL pause after a page refresh.
 *
 * The durable interrupt is persisted server-side (``GET
 * /teaching/threads/{conversation_id}/interrupt``); this route exposes it to
 * the student workspace so a refreshed page can re-render the confirmation
 * card instead of silently losing the pause.  Non-2xx upstream statuses are
 * forwarded as-is — 404 simply means "no pending interrupt".  A 2xx payload
 * is parsed, scope-checked, digest-verified and redacted before reaching the
 * browser, exactly like the streaming terminal path.
 */
export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const { conversationId } = await context.params;
  const scope = parseScope(new URL(request.url).searchParams) as TeachingScope | null;
  if (!scope || !UUID_PATTERN.test(conversationId)) {
    return agentError(400, "INVALID_HITL_SCOPE", "人工复核线程的课程范围无效。");
  }

  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能读取暂停状态。");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) return agentError(503, "BACKEND_NOT_CONFIGURED", "人工复核服务尚未配置。");

  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/teaching/threads/${conversationId}/interrupt`;
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
    return agentError(503, "HITL_UNAVAILABLE", "无法读取当前暂停状态。");
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
    return agentError(502, "INVALID_UPSTREAM_RESPONSE", "暂停状态无法解析。", traceId);
  }
  try {
    const pause = redactHitlProposedResponse(parseHitlInterruptResponse(payload));
    assertHitlScope(pause, scope, pause.artifacts.policy.mode);
    if (pause.conversation_id !== conversationId) {
      throw new Error("interrupt belongs to a different conversation");
    }
    await assertEvidenceDigests(pause.artifacts.evidence_packet);
    return Response.json(pause, {
      status: 200,
      headers: {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return agentError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "暂停状态未通过课程范围与证据校验。",
      traceId,
    );
  }
}
