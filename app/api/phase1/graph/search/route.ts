import {
  assertResponseScope,
  parseConceptSearchResponse,
} from "@/app/components/knowledge/contracts";
import {
  forwardBackendJson,
  invalidRequest,
  normalizedSearchQuery,
  parseScope,
} from "@/app/api/phase1/_shared";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = parseScope(params);
  const query = normalizedSearchQuery(params);
  if (!scope) return invalidRequest("course_id 与 curriculum_edition_id 必须是有效 UUID。" );
  if (!query) return invalidRequest("搜索词长度必须为 1–300 个字符。" );

  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/graph/concepts/search?q=${encodeURIComponent(query)}&limit=20`;
  return forwardBackendJson({
    path,
    parse: parseConceptSearchResponse,
    scope,
    assertScope: assertResponseScope,
  });
}
