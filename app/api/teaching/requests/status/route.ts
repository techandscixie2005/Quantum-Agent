import { agentError, quantumApiBaseUrl, safeAgentUpstreamMessage, studentSessionToken } from "@/app/api/agent/_shared";
import { parseScope, requireSameOrigin } from "@/app/api/phase1/_shared";
import { boundedStatusJson, parseTeachingRequestStatus } from "@/lib/teaching-request-status";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const query = new URL(request.url).searchParams;
  const scope = parseScope(query);
  const requestId = query.get("client_request_id");
  if (!scope || !requestId || requestId.length > 128 || requestId.trim() !== requestId || /[\u0000-\u001f]/.test(requestId)) {
    return agentError(400, "INVALID_REQUEST_SCOPE", "请求标识或课程范围无效。");
  }
  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能检查保存状态。");
  const base = quantumApiBaseUrl();
  if (!base) return agentError(503, "BACKEND_NOT_CONFIGURED", "学习服务尚未配置。");
  const path = `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}/teaching/requests/status`;
  const url = new URL(path, base);
  url.searchParams.set("client_request_id", requestId);
  try {
    const upstream = await fetch(url, { headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
      cache: "no-store", signal: AbortSignal.timeout(20_000) });
    if (!upstream.ok) return agentError(upstream.status, `UPSTREAM_${upstream.status}`,
      upstream.status === 404 ? "当前账号和课程中尚未找到这次提交。可使用原提交标识重试。" : safeAgentUpstreamMessage(upstream.status));
    const result = parseTeachingRequestStatus(await boundedStatusJson(upstream), requestId);
    return Response.json(result, { headers: { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } });
  } catch {
    return agentError(502, "REQUEST_STATUS_UNAVAILABLE", "暂时无法确认保存状态。请保留输入和原提交标识，再次检查。");
  }
}
