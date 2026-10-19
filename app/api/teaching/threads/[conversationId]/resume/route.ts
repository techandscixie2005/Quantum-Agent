import {
  assertHitlScope,
  assertTeachingScope,
  parseStudentHitlResumeRequest,
  parseTeachingWorkflowOutcome,
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
import { teachingProxyTimeoutMs } from "@/lib/teaching-timeout";

export const dynamic = "force-dynamic";

type RouteContext = Readonly<{ params: Promise<{ conversationId: string }> }>;

async function readBoundedJsonObject(
  request: Request,
  maxBytes = 32_000,
): Promise<Record<string, unknown> | null> {
  if (!(request.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
    return null;
  }
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > maxBytes) return null;
  if (!request.body) return null;
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let total = 0;
  let text = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel("HITL request exceeded the bounded payload size");
      return null;
    }
    text += decoder.decode(value, { stream: true });
  }
  text += decoder.decode();
  try {
    const value: unknown = JSON.parse(text);
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

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
      await reader.cancel("HITL response exceeded the bounded payload size");
      throw new Error("upstream payload is too large");
    }
    text += decoder.decode(value, { stream: true });
  }
  text += decoder.decode();
  return JSON.parse(text) as unknown;
}

function scopedPath(scope: TeachingScope, conversationId: string, suffix: string): string {
  return (
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/teaching/threads/${conversationId}/${suffix}`
  );
}

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const { conversationId } = await context.params;
  const scope = parseScope(new URL(request.url).searchParams) as TeachingScope | null;
  if (!scope || !UUID_PATTERN.test(conversationId)) {
    return agentError(400, "INVALID_HITL_SCOPE", "人工复核线程的课程范围无效。");
  }
  const rawBody = await readBoundedJsonObject(request);
  if (!rawBody) {
    return agentError(400, "INVALID_HITL_CONFIRMATION", "确认请求必须是 JSON 对象。");
  }
  let body;
  try {
    body = parseStudentHitlResumeRequest(rawBody);
  } catch {
    return agentError(
      400,
      "INVALID_HITL_CONFIRMATION",
      "学生端只允许提交当前歧义转录的确认文本。",
    );
  }

  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能确认转录。");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) return agentError(503, "BACKEND_NOT_CONFIGURED", "人工复核服务尚未配置。");
  const headers = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  };
  let timeoutMs: number;
  try { timeoutMs = teachingProxyTimeoutMs(); } catch {
    return agentError(503, "INVALID_TIMEOUT_CONFIGURATION", "教学执行与代理时限配置无效。");
  }

  // The scoped backend authenticates ownership and binds this exact interrupt
  // identity to its durable decision. A preflight GET would reject a valid retry
  // after the original response was lost and the checkpoint already advanced.
  let upstream: Response;
  try {
    upstream = await fetch(new URL(scopedPath(scope, conversationId, "resume"), baseUrl), {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        interrupt_id: body.interrupt_id,
        action: body.action,
        confirmed_student_attempt: body.confirmed_student_attempt,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    return agentError(
      503,
      "HITL_RESUME_UNAVAILABLE",
      "确认文本已保留，但工作流暂时无法继续。",
    );
  }
  const traceId = upstream.headers.get("x-trace-id");
  let payload: unknown;
  try {
    payload = await boundedJson(upstream);
  } catch {
    return agentError(502, "INVALID_UPSTREAM_RESPONSE", "继续执行的结果无法解析。", traceId);
  }
  if (!upstream.ok) {
    return agentError(
      upstream.status,
      `UPSTREAM_${upstream.status}`,
      safeAgentUpstreamMessage(upstream.status),
      traceId,
    );
  }
  try {
    const outcome = parseTeachingWorkflowOutcome(payload);
    if ("interrupt" in outcome) {
      assertHitlScope(outcome, scope, body.mode);
      if (outcome.conversation_id !== conversationId) {
        throw new Error("conversation changed while resuming");
      }
      await assertEvidenceDigests(outcome.artifacts.evidence_packet);
      return Response.json(redactHitlProposedResponse(outcome), {
        status: 202,
        headers: {
          "Cache-Control": "private, no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    assertTeachingScope(outcome, scope, body.mode);
    if (outcome.conversation_id !== conversationId) {
      throw new Error("conversation changed while resuming");
    }
    await assertEvidenceDigests(outcome.evidence_packet);
    return Response.json(outcome, {
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
      "继续执行的结果未通过课程范围与证据校验。",
      traceId,
    );
  }
}
