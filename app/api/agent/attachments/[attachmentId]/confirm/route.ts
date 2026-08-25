import { z } from "zod";

import { parseAgentAttachment } from "@/app/components/agent/contracts";
import { UUID_PATTERN } from "@/app/components/knowledge/contracts";
import { requireSameOrigin } from "@/app/api/phase1/_shared";
import {
  agentError,
  quantumApiBaseUrl,
  safeAgentUpstreamMessage,
  studentSessionToken,
} from "@/app/api/agent/_shared";

export const dynamic = "force-dynamic";
type RouteContext = Readonly<{ params: Promise<{ attachmentId: string }> }>;

const confirmationSchema = z
  .object({
    extraction_id: z.string().uuid(),
    decision: z.enum(["accept", "reject"]),
    ambiguity_resolutions: z.record(z.string().max(160), z.string().min(1).max(4_000)),
  })
  .strict();

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const { attachmentId } = await context.params;
  const search = new URL(request.url).searchParams;
  const courseId = search.get("course_id")?.trim() ?? "";
  const editionId = search.get("curriculum_edition_id")?.trim() ?? "";
  if (
    !UUID_PATTERN.test(attachmentId) ||
    !UUID_PATTERN.test(courseId) ||
    !UUID_PATTERN.test(editionId)
  ) {
    return agentError(400, "INVALID_CONFIRMATION_SCOPE", "转录确认范围无效。");
  }
  let body: z.infer<typeof confirmationSchema>;
  try {
    body = confirmationSchema.parse(await request.json());
  } catch {
    return agentError(400, "INVALID_CONFIRMATION", "转录确认内容无效。");
  }
  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能确认转录。");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) return agentError(503, "BACKEND_NOT_CONFIGURED", "转录服务尚未配置。");
  let upstream: Response;
  try {
    upstream = await fetch(
      new URL(
        `/api/v1/courses/${courseId}/editions/${editionId}/attachments/` +
          `${attachmentId}/confirm`,
        baseUrl,
      ),
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        cache: "no-store",
        signal: AbortSignal.timeout(30_000),
      },
    );
  } catch {
    return agentError(503, "CONFIRMATION_UNAVAILABLE", "无法连接转录确认服务。");
  }
  const traceId = upstream.headers.get("x-trace-id");
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return agentError(502, "INVALID_UPSTREAM_RESPONSE", "确认响应无法解析。", traceId);
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
      headers: { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" },
    });
  } catch {
    return agentError(502, "INVALID_UPSTREAM_CONTRACT", "确认结果未通过契约校验。", traceId);
  }
}
