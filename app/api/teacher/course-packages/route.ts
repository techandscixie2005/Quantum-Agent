import { requireSameOrigin } from "@/app/api/phase1/_shared";
import { parseTraceScope, privateTraceJson, staffBackendContext, fetchStaffJson, traceError } from "@/app/api/teacher/traces/_shared";

export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;
  const scope = parseTraceScope(new URL(request.url).searchParams);
  if (!scope) return traceError(400, "INVALID_SCOPE", "课程范围无效。");
  const backend = await staffBackendContext();
  if (!backend.ok) return backend.response;
  const result = await fetchStaffJson(backend.value,
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}/teacher/course-packages`);
  return result.ok ? privateTraceJson(result.payload, result.status, result.traceId) : result.response;
}
