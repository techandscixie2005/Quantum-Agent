import {
  assertResponseScope,
  parsePrerequisitePathsResponse,
} from "@/app/components/knowledge/contracts";
import {
  candidateId,
  forwardBackendJson,
  invalidRequest,
  parseScope,
} from "@/app/api/phase1/_shared";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = parseScope(params);
  const selectedCandidateId = candidateId(params);
  if (!scope) return invalidRequest("course_id 与 curriculum_edition_id 必须是有效 UUID。" );
  if (!selectedCandidateId) return invalidRequest("candidate_id 必须是有效 UUID。" );

  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/graph/nodes/${selectedCandidateId}/prerequisites?max_depth=4&limit=12`;
  return forwardBackendJson({
    path,
    parse: parsePrerequisitePathsResponse,
    scope,
    assertScope: assertResponseScope,
    assertValue: (value) => {
      if (value.target_candidate_id !== selectedCandidateId) {
        throw new Error("prerequisite target does not match request");
      }
    },
  });
}
