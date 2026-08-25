import { parseReviewCandidateDetail } from "@/app/components/knowledge/contracts";
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
  const kind = params.get("kind");
  if (!scope) return invalidRequest("course_id 与 curriculum_edition_id 必须是有效 UUID。" );
  if (!selectedCandidateId) return invalidRequest("candidate_id 必须是有效 UUID。" );
  if (kind !== "node" && kind !== "relation") {
    return invalidRequest("kind 必须为 node 或 relation。" );
  }

  const collection = kind === "node" ? "nodes" : "relations";
  const path =
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/knowledge/${collection}/${selectedCandidateId}`;
  return forwardBackendJson({
    path,
    parse: parseReviewCandidateDetail,
    assertValue: (value) => {
      if (value.item.candidate_id !== selectedCandidateId || value.item.kind !== kind) {
        throw new Error("review detail does not match request");
      }
    },
  });
}
