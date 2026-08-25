import { z } from "zod";

import { assertEvidenceDigests } from "@/app/api/teaching/_shared";
import {
  fetchStaffJson,
  parseTraceScope,
  privateTraceJson,
  staffBackendContext,
  teacherTracePath,
  traceError,
} from "@/app/api/teacher/traces/_shared";
import { parseAgentTraceDetail } from "@/app/components/teacher-traces/contracts";

export const dynamic = "force-dynamic";

type RouteContext = Readonly<{ params: Promise<{ traceId: string }> }>;
const traceIdSchema = z.string().uuid();

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const scope = parseTraceScope(new URL(request.url).searchParams);
  const traceIdResult = traceIdSchema.safeParse((await context.params).traceId);
  if (!scope || !traceIdResult.success) {
    return traceError(400, "INVALID_TRACE_SCOPE", "课程范围或 trace 标识无效。");
  }

  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  const upstream = await fetchStaffJson(
    backend.value,
    teacherTracePath(scope, `/${traceIdResult.data}`),
  );
  if (!upstream.ok) return upstream.response;

  try {
    const detail = parseAgentTraceDetail(upstream.payload, scope, traceIdResult.data);
    if (detail.evidence_packet) await assertEvidenceDigests(detail.evidence_packet);
    return privateTraceJson(detail, upstream.status, upstream.traceId);
  } catch {
    return traceError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "Agent trace 未通过身份、范围、证据摘要或字段校验，本页已拒绝显示。",
      upstream.traceId,
    );
  }
}
