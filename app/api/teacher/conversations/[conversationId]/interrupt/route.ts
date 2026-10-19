import { UUID_PATTERN } from "@/app/components/knowledge/contracts";
import { assertEvidenceDigests } from "@/app/api/teaching/_shared";
import { assertHitlScope, parseHitlInterruptResponse } from "@/app/components/teaching/contracts";
import {
  fetchStaffJson, parseTraceScope, privateTraceJson, staffBackendContext,
  teachingThreadPath, traceError,
} from "@/app/api/teacher/traces/_shared";

export const dynamic = "force-dynamic";
type RouteContext = Readonly<{ params: Promise<{ conversationId: string }> }>;
export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const scope = parseTraceScope(new URL(request.url).searchParams);
  const { conversationId } = await context.params;
  if (!scope || !UUID_PATTERN.test(conversationId)) {
    return traceError(400, "INVALID_REVIEW_SCOPE", "课程范围或会话标识无效。");
  }
  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  const result = await fetchStaffJson(backend.value, teachingThreadPath(scope, conversationId, "interrupt"));
  if (!result.ok) return result.response;
  try {
    const current = parseHitlInterruptResponse(result.payload);
    assertHitlScope(current, scope, current.artifacts.policy.mode);
    if (current.conversation_id !== conversationId) throw new Error("Conversation changed");
    await assertEvidenceDigests(current.artifacts.evidence_packet);
    return privateTraceJson(current, 200, result.traceId);
  } catch {
    return traceError(502, "INVALID_UPSTREAM_CONTRACT", "人工复核未通过范围与证据校验。");
  }
}
