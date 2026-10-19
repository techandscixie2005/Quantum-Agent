import { parsePendingReviews } from "@/app/components/teacher-traces/pending-contracts";
import {
  fetchStaffJson, parseTraceScope, privateTraceJson, staffBackendContext, traceError,
} from "../traces/_shared";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const scope = parseTraceScope(params);
  const offset = Number(params.get("offset") ?? "0");
  if (!scope || !Number.isSafeInteger(offset) || offset < 0 || offset > 1_000_000) {
    return traceError(400, "INVALID_REVIEW_SCOPE", "课程范围或队列页码无效。");
  }
  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  const path = `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/teacher/pending-reviews?limit=25&offset=${offset}`;
  const fetched = await fetchStaffJson(backend.value, path);
  if (!fetched.ok) return fetched.response;
  try {
    return privateTraceJson(parsePendingReviews(fetched.payload, scope), 200, fetched.traceId);
  } catch {
    return traceError(502, "INVALID_UPSTREAM_CONTRACT", "待复核队列未通过课程范围校验。");
  }
}
