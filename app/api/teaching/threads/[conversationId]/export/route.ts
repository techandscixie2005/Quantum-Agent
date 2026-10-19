import { agentError, quantumApiBaseUrl, studentSessionToken } from "@/app/api/agent/_shared";
import { parseScope, requireSameOrigin } from "@/app/api/phase1/_shared";
import { UUID_PATTERN } from "@/app/components/knowledge/contracts";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ conversationId: string }> }) {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const { conversationId } = await context.params;
  const scope = parseScope(new URL(request.url).searchParams);
  if (!scope || !UUID_PATTERN.test(conversationId)) return agentError(400, "INVALID_SCOPE", "学习记录范围无效。");
  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "请先登录课程。");
  const base = quantumApiBaseUrl();
  if (!base) return agentError(503, "BACKEND_NOT_CONFIGURED", "学习记录服务尚未配置。");
  try {
    const upstream = await fetch(new URL(
      `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}/learning-records/${conversationId}/export`, base,
    ), { headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal: AbortSignal.timeout(20_000) });
    if (!upstream.ok) return agentError(upstream.status, "EXPORT_REFUSED", "无法导出。请确认课程权限，或完成当前 Solo 独立作答。");
    if (!upstream.body) throw new Error("empty export");
    const reader = upstream.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 8_000_000) { await reader.cancel(); throw new Error("export exceeds budget"); }
      chunks.push(value);
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length; }
    const payload = JSON.parse(new TextDecoder().decode(body));
    if (payload.record?.conversation_id !== conversationId || payload.record?.course_id !== scope.courseId ||
        payload.record?.curriculum_edition_id !== scope.curriculumEditionId ||
        !/^[a-f0-9]{64}$/.test(payload.record_sha256 ?? "")) throw new Error("invalid export scope");
    return new Response(body, { headers: {
      "Content-Type": "application/json; charset=utf-8", "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Disposition": `attachment; filename="learning-${conversationId}.json"`,
    } });
  } catch { return agentError(502, "EXPORT_UNAVAILABLE", "学习证据导出失败，请重试。"); }
}
