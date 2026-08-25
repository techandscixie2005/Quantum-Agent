import { UUID_PATTERN } from "@/app/components/knowledge/contracts";
import { parseAgentAttachment } from "@/app/components/agent/contracts";
import { requireSameOrigin } from "@/app/api/phase1/_shared";
import {
  agentError,
  quantumApiBaseUrl,
  safeAgentUpstreamMessage,
  studentSessionToken,
} from "@/app/api/agent/_shared";

export const dynamic = "force-dynamic";
const MAX_MULTIPART_BYTES = 26 * 1024 * 1024;

export async function POST(request: Request): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const search = new URL(request.url).searchParams;
  const courseId = search.get("course_id")?.trim() ?? "";
  const editionId = search.get("curriculum_edition_id")?.trim() ?? "";
  if (!UUID_PATTERN.test(courseId) || !UUID_PATTERN.test(editionId)) {
    return agentError(400, "INVALID_ATTACHMENT_SCOPE", "附件课程范围无效。");
  }
  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_MULTIPART_BYTES) {
    return agentError(413, "ATTACHMENT_TOO_LARGE", "附件超过 25 MiB 限制。");
  }
  if (!(request.headers.get("content-type") ?? "").toLowerCase().startsWith("multipart/form-data")) {
    return agentError(415, "MULTIPART_REQUIRED", "附件必须使用 multipart/form-data 上传。");
  }
  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return agentError(400, "INVALID_MULTIPART", "附件表单无法解析。");
  }
  const file = incoming.get("file");
  if (!(file instanceof File) || file.size < 1 || file.size > 25 * 1024 * 1024) {
    return agentError(413, "INVALID_ATTACHMENT_SIZE", "附件必须为 1 字节至 25 MiB。");
  }
  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能上传附件。");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) return agentError(503, "BACKEND_NOT_CONFIGURED", "附件服务尚未配置。");

  const body = new FormData();
  body.set("file", file, file.name);
  let upstream: Response;
  try {
    upstream = await fetch(
      new URL(
        `/api/v1/courses/${courseId}/editions/${editionId}/attachments`,
        baseUrl,
      ),
      {
        method: "POST",
        headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(120_000),
      },
    );
  } catch {
    return agentError(503, "ATTACHMENT_UNAVAILABLE", "附件处理服务当前不可用。");
  }
  const traceId = upstream.headers.get("x-trace-id");
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return agentError(502, "INVALID_UPSTREAM_RESPONSE", "附件服务响应无法解析。", traceId);
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
    return Response.json(parseAgentAttachment(payload), {
      status: upstream.status,
      headers: { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" },
    });
  } catch {
    return agentError(502, "INVALID_UPSTREAM_CONTRACT", "附件结果未通过契约校验。", traceId);
  }
}
