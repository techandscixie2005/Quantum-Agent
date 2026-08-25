import { z } from "zod";

import { requireSameOrigin, readJsonObject } from "@/app/api/phase1/_shared";
import { assertEvidenceDigests } from "@/app/api/teaching/_shared";
import {
  fetchStaffJson,
  parseTraceScope,
  privateTraceJson,
  staffBackendContext,
  teacherTracePath,
  teachingThreadPath,
  traceError,
  type StaffContextResult,
} from "@/app/api/teacher/traces/_shared";
import {
  assertHitlScope,
  assertTeachingScope,
  parseHitlInterruptResponse,
  parseTeachingTurnResult,
  parseTeachingWorkflowOutcome,
  type HitlInterruptResponse,
} from "@/app/components/teaching/contracts";
import {
  assertEditedResponseAuthority,
  parseAgentTraceDetail,
  parseHitlRejectedResponse,
  parseReviewDecision,
  reviewResolutionSchema,
  teachingResponseSchema,
  type AgentTraceDetail,
  type TraceScope,
} from "@/app/components/teacher-traces/contracts";

export const dynamic = "force-dynamic";

type RouteContext = Readonly<{ params: Promise<{ traceId: string }> }>;
type ValidContext = Extract<StaffContextResult, { ok: true }>["value"];
type ReviewState = Readonly<{
  detail: AgentTraceDetail;
  current: HitlInterruptResponse;
  traceId: string | null;
}>;
type ReviewStateResult =
  | Readonly<{ ok: true; value: ReviewState }>
  | Readonly<{ ok: false; response: Response }>;

const traceIdSchema = z.string().uuid();

async function loadCurrentReview(
  backend: ValidContext,
  scope: TraceScope,
  traceId: string,
): Promise<ReviewStateResult> {
  const traceResponse = await fetchStaffJson(backend, teacherTracePath(scope, `/${traceId}`));
  if (!traceResponse.ok) return traceResponse;

  let detail: AgentTraceDetail;
  try {
    detail = parseAgentTraceDetail(traceResponse.payload, scope, traceId);
    if (detail.evidence_packet) await assertEvidenceDigests(detail.evidence_packet);
  } catch {
    return {
      ok: false,
      response: traceError(
        502,
        "INVALID_UPSTREAM_CONTRACT",
        "Agent trace 未通过课程范围或证据摘要校验。",
        traceResponse.traceId,
      ),
    };
  }

  const interruptResponse = await fetchStaffJson(
    backend,
    teachingThreadPath(scope, detail.conversation_id, "interrupt"),
  );
  if (!interruptResponse.ok) return interruptResponse;

  try {
    const current = parseHitlInterruptResponse(interruptResponse.payload);
    assertHitlScope(current, scope, detail.mode);
    await assertEvidenceDigests(current.artifacts.evidence_packet);
    const unresolved = [...detail.hitl_events]
      .reverse()
      .find((event) => event.resolution === null);
    if (
      !unresolved ||
      unresolved.interrupt.interrupt_id !== current.interrupt.interrupt_id ||
      current.conversation_id !== detail.conversation_id ||
      current.turn_id !== detail.teaching_turn_id
    ) {
      throw new Error("current checkpoint does not match the durable trace");
    }
    return {
      ok: true,
      value: {
        detail,
        current,
        traceId: interruptResponse.traceId ?? traceResponse.traceId,
      },
    };
  } catch {
    return {
      ok: false,
      response: traceError(
        409,
        "STALE_TRACE_REVIEW",
        "该 trace 与当前 LangGraph checkpoint 不一致；请刷新队列后重新检查。",
        interruptResponse.traceId,
      ),
    };
  }
}

async function parseRouteContext(
  request: Request,
  context: RouteContext,
): Promise<Readonly<{ scope: TraceScope; traceId: string }> | null> {
  const scope = parseTraceScope(new URL(request.url).searchParams);
  const traceId = traceIdSchema.safeParse((await context.params).traceId);
  return scope && traceId.success ? { scope, traceId: traceId.data } : null;
}

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const route = await parseRouteContext(request, context);
  if (!route) return traceError(400, "INVALID_REVIEW_SCOPE", "课程范围或 trace 标识无效。");

  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  const state = await loadCurrentReview(backend.value, route.scope, route.traceId);
  if (!state.ok) return state.response;
  return privateTraceJson(state.value.current, 200, state.value.traceId);
}

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const route = await parseRouteContext(request, context);
  if (!route) return traceError(400, "INVALID_REVIEW_SCOPE", "课程范围或 trace 标识无效。");
  const rawBody = await readJsonObject(request);
  if (!rawBody) return traceError(400, "INVALID_REVIEW", "复核决定必须是 JSON 对象。");

  let decision;
  try {
    decision = parseReviewDecision(rawBody);
  } catch {
    return traceError(
      400,
      "INVALID_REVIEW",
      "复核动作或字段无效；reject / take_over 必须附带说明，edit / take_over 必须包含受约束响应。",
    );
  }

  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  const state = await loadCurrentReview(backend.value, route.scope, route.traceId);
  if (!state.ok) return state.response;
  const { current, detail } = state.value;
  if (
    current.interrupt.interrupt_id !== decision.interrupt_id ||
    !current.interrupt.staff_allowed_actions.includes(decision.action)
  ) {
    return traceError(
      409,
      "STALE_REVIEW_DECISION",
      "当前 checkpoint 已变化，或该动作不在本次人工复核权限范围内。",
      state.value.traceId,
    );
  }

  if (decision.action === "edit" || decision.action === "take_over") {
    try {
      assertEditedResponseAuthority(
        decision.edited_response,
        teachingResponseSchema.parse(current.artifacts.proposed_response),
      );
      parseTeachingTurnResult({
        conversation_id: current.conversation_id,
        turn_id: current.turn_id,
        workflow_version: "staff-edited-proposal/1.0.0",
        interpretation: current.artifacts.interpretation,
        diagnosis: current.artifacts.diagnosis,
        policy: current.artifacts.policy,
        release: current.artifacts.release,
        evidence_packet: current.artifacts.evidence_packet,
        response: decision.edited_response,
        validation: current.artifacts.validation,
        scientific_results: current.artifacts.scientific_results,
        trace: current.artifacts.trace,
      });
    } catch {
      return traceError(
        400,
        "INVALID_EDITED_RESPONSE",
        "编辑后的响应改变了受锁定的引用/工具权限，或正文不再受原始证据支持。",
        state.value.traceId,
      );
    }
  }

  const resumeBody =
    decision.action === "edit" || decision.action === "take_over"
      ? {
          action: decision.action,
          note: decision.note,
          edited_response: decision.edited_response,
        }
      : { action: decision.action, note: decision.note };

  const resumed = await fetchStaffJson(
    backend.value,
    teachingThreadPath(route.scope, detail.conversation_id, "resume"),
    {
      method: "POST",
      body: resumeBody,
      timeoutMs: 120_000,
    },
  );
  if (!resumed.ok) return resumed.response;

  try {
    let outcome: "completed" | "rejected" | "interrupted";
    if (
      typeof resumed.payload === "object" &&
      resumed.payload !== null &&
      !Array.isArray(resumed.payload) &&
      (resumed.payload as Record<string, unknown>).status === "rejected"
    ) {
      const rejected = parseHitlRejectedResponse(resumed.payload);
      if (
        rejected.conversation_id !== detail.conversation_id ||
        rejected.turn_id !== detail.teaching_turn_id ||
        rejected.interrupt_id !== decision.interrupt_id
      ) {
        throw new Error("rejected outcome crossed the reviewed turn boundary");
      }
      outcome = "rejected";
    } else {
      const workflow = parseTeachingWorkflowOutcome(resumed.payload);
      if ("interrupt" in workflow) {
        assertHitlScope(workflow, route.scope, detail.mode);
        await assertEvidenceDigests(workflow.artifacts.evidence_packet);
        outcome = "interrupted";
      } else {
        assertTeachingScope(workflow, route.scope, detail.mode);
        await assertEvidenceDigests(workflow.evidence_packet);
        outcome = "completed";
      }
      if (
        workflow.conversation_id !== detail.conversation_id ||
        workflow.turn_id !== detail.teaching_turn_id
      ) {
        throw new Error("resume outcome crossed the reviewed turn boundary");
      }
    }

    const resolution = reviewResolutionSchema.parse({
      status: "resolved",
      action: decision.action,
      outcome,
      conversation_id: detail.conversation_id,
      turn_id: detail.teaching_turn_id,
    });
    return privateTraceJson(resolution, outcome === "interrupted" ? 202 : 200, resumed.traceId);
  } catch {
    return traceError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "恢复结果未通过课程范围、线程身份或证据摘要校验。",
      resumed.traceId,
    );
  }
}
