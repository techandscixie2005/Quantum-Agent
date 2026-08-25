import { parseAgentTracePage } from "@/app/components/teacher-traces/contracts";
import {
  fetchStaffJson,
  parseTraceScope,
  privateTraceJson,
  staffBackendContext,
  teacherTracePath,
  traceError,
} from "@/app/api/teacher/traces/_shared";

export const dynamic = "force-dynamic";

function boundedInteger(value: string | null, fallback: number, minimum: number, maximum: number) {
  if (value === null || value.trim() === "") return fallback;
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

export async function GET(request: Request): Promise<Response> {
  const search = new URL(request.url).searchParams;
  const scope = parseTraceScope(search);
  const limit = boundedInteger(search.get("limit"), 25, 1, 100);
  const offset = boundedInteger(search.get("offset"), 0, 0, 100_000);
  if (!scope || limit === null || offset === null) {
    return traceError(
      400,
      "INVALID_TRACE_QUERY",
      "course_id、curriculum_edition_id、limit 或 offset 无效。",
    );
  }

  const context = await staffBackendContext();
  if (!context.ok) return context.response;
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const upstream = await fetchStaffJson(
    context.value,
    `${teacherTracePath(scope)}?${query.toString()}`,
  );
  if (!upstream.ok) return upstream.response;

  try {
    const page = parseAgentTracePage(upstream.payload, scope);
    return privateTraceJson(page, upstream.status, upstream.traceId);
  } catch {
    return traceError(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      "Agent trace 队列未通过课程范围与字段校验，本页已拒绝显示。",
      upstream.traceId,
    );
  }
}
