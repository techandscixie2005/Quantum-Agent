import { UUID_PATTERN } from "@/app/components/knowledge/contracts";
import { requireSameOrigin, readJsonObject } from "@/app/api/phase1/_shared";
import { assertEvidenceDigests } from "@/app/api/teaching/_shared";
import {
  assertHitlScope, assertTeachingScope, parseTeachingWorkflowOutcome,
} from "@/app/components/teaching/contracts";
import { parseHitlRejectedResponse, parseReviewDecision } from "@/app/components/teacher-traces/contracts";
import { teachingProxyTimeoutMs } from "@/lib/teaching-timeout";
import {
  fetchStaffJson, parseTraceScope, privateTraceJson, staffBackendContext,
  teachingThreadPath, traceError,
} from "@/app/api/teacher/traces/_shared";

export const dynamic = "force-dynamic";
type RouteContext = Readonly<{ params: Promise<{ conversationId: string }> }>;
export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const scope = parseTraceScope(new URL(request.url).searchParams);
  const { conversationId } = await context.params;
  if (!scope || !UUID_PATTERN.test(conversationId)) {
    return traceError(400, "INVALID_REVIEW_SCOPE", "课程范围或会话标识无效。");
  }
  let decision;
  let timeoutMs: number;
  try {
    decision = parseReviewDecision(await readJsonObject(request));
    // The queue currently supports attributed approval/rejection. Backend gates
    // remain authoritative; the completed-trace workspace supports constrained edits.
    if (!["approve", "reject"].includes(decision.action) || !decision.note?.trim()) {
      throw new Error("A review reason is required");
    }
  } catch {
    return traceError(400, "INVALID_REVIEW", "请选择批准或拒绝，并填写复核理由。");
  }
  try { timeoutMs = teachingProxyTimeoutMs(); } catch {
    return traceError(503, "INVALID_TIMEOUT_CONFIGURATION", "教学执行与代理时限配置无效。");
  }
  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  // No preflight GET: a committed decision must replay after its response is lost.
  // The backend binds reviewer, interrupt identity and the full decision atomically.
  const result = await fetchStaffJson(backend.value, teachingThreadPath(scope, conversationId, "resume"), {
    method: "POST", body: decision, timeoutMs,
  });
  if (!result.ok) return result.response;
  try {
    const raw = result.payload as Record<string, unknown> | null;
    if (raw?.status === "rejected") {
      const rejected = parseHitlRejectedResponse(raw);
      if (rejected.conversation_id !== conversationId || rejected.interrupt_id !== decision.interrupt_id) {
        throw new Error("Rejected decision changed identity");
      }
      return privateTraceJson(rejected, 200, result.traceId);
    }
    const workflow = parseTeachingWorkflowOutcome(raw);
    if (workflow.conversation_id !== conversationId) throw new Error("Conversation changed");
    if ("interrupt" in workflow) {
      assertHitlScope(workflow, scope, workflow.artifacts.policy.mode);
      await assertEvidenceDigests(workflow.artifacts.evidence_packet);
    } else {
      assertTeachingScope(workflow, scope, workflow.policy.mode);
      await assertEvidenceDigests(workflow.evidence_packet);
    }
    return privateTraceJson(workflow, "interrupt" in workflow ? 202 : 200, result.traceId);
  } catch {
    return traceError(502, "INVALID_UPSTREAM_CONTRACT", "恢复结果未通过会话与证据校验。");
  }
}
