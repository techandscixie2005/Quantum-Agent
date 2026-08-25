import { parseReviewQueueResponse } from "@/app/components/knowledge/contracts";
import {
  forwardBackendJson,
  invalidRequest,
  parseScope,
} from "@/app/api/phase1/_shared";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = parseScope(params);
  if (!scope) return invalidRequest("course_id 与 curriculum_edition_id 必须是有效 UUID。" );

  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    "/knowledge/review-queue?limit=100&offset=0";
  return forwardBackendJson({ path, parse: parseReviewQueueResponse });
}
