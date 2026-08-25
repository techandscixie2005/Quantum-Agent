import { UUID_PATTERN } from "@/app/components/knowledge/contracts";
import {
  agentError,
  quantumApiBaseUrl,
  safeAgentUpstreamMessage,
  studentSessionToken,
} from "@/app/api/agent/_shared";

export const dynamic = "force-dynamic";

type RouteContext = Readonly<{ params: Promise<{ documentVersionId: string }> }>;

async function proxyOriginal(request: Request, context: RouteContext): Promise<Response> {
  const { documentVersionId } = await context.params;
  const search = new URL(request.url).searchParams;
  const courseId = search.get("course_id")?.trim() ?? "";
  const editionId = search.get("curriculum_edition_id")?.trim() ?? "";
  if (
    !UUID_PATTERN.test(documentVersionId) ||
    !UUID_PATTERN.test(courseId) ||
    !UUID_PATTERN.test(editionId)
  ) {
    return agentError(400, "INVALID_SOURCE_SCOPE", "课程来源定位参数无效。");
  }
  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能打开来源原文。");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) return agentError(503, "BACKEND_NOT_CONFIGURED", "来源服务尚未配置。");

  const path =
    `/api/v1/courses/${courseId}/editions/${editionId}/sources/` +
    `${documentVersionId}/original`;
  const headers = new Headers({
    Accept: request.headers.get("accept") ?? "application/pdf,*/*;q=0.8",
    Authorization: `Bearer ${token}`,
  });
  const range = request.headers.get("range");
  if (range && range.length <= 200 && !range.includes(",")) headers.set("Range", range);

  let upstream: Response;
  try {
    upstream = await fetch(new URL(path, baseUrl), {
      method: request.method,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return agentError(503, "SOURCE_UNAVAILABLE", "无法连接课程来源服务。");
  }
  if (!upstream.ok) {
    return agentError(
      upstream.status,
      `UPSTREAM_${upstream.status}`,
      safeAgentUpstreamMessage(upstream.status),
      upstream.headers.get("x-trace-id"),
    );
  }

  const responseHeaders = new Headers({
    "Cache-Control": "private, no-store",
    "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
    "X-Content-Type-Options": "nosniff",
  });
  for (const name of [
    "accept-ranges",
    "content-disposition",
    "content-length",
    "content-range",
    "etag",
    "last-modified",
  ]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(request.method === "HEAD" ? null : upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  return proxyOriginal(request, context);
}

export async function HEAD(request: Request, context: RouteContext): Promise<Response> {
  return proxyOriginal(request, context);
}

