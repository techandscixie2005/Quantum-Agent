import { requireSameOrigin } from "@/app/api/phase1/_shared";
import { parseTraceScope, privateTraceJson, staffBackendContext, fetchStaffJson, traceError } from "@/app/api/teacher/traces/_shared";
import { UUID_PATTERN } from "@/app/components/knowledge/contracts";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ conversationId: string }> };

async function proxy(request: Request, context: Context) {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const scope = parseTraceScope(new URL(request.url).searchParams);
  const { conversationId } = await context.params;
  if (!scope || !UUID_PATTERN.test(conversationId)) return traceError(400, "INVALID_SCOPE", "课程与学习过程范围无效。");
  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  let body: unknown;
  if (request.method === "POST") {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).length > 16_000) return traceError(413, "REVIEW_TOO_LARGE", "审阅说明过长。");
    try { body = JSON.parse(raw); }
    catch { return traceError(400, "INVALID_REVIEW", "审阅决定必须为 JSON。"); }
  }
  const result = await fetchStaffJson(backend.value,
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}/teacher/conversations/${conversationId}/reviews`,
    { method: request.method === "POST" ? "POST" : "GET", ...(body !== undefined ? { body } : {}) });
  return result.ok ? privateTraceJson(result.payload, result.status, result.traceId) : result.response;
}

export const GET = proxy;
export const POST = proxy;
