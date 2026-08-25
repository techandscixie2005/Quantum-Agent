import {
  UUID_PATTERN,
  parseCandidateActionResponse,
} from "@/app/components/knowledge/contracts";
import {
  forwardBackendJson,
  invalidRequest,
  parseScope,
  readJsonObject,
  requireSameOrigin,
} from "@/app/api/phase1/_shared";

const BODY_KEYS = new Set(["candidate_id", "kind", "action", "rationale"]);

export async function POST(request: Request) {
  const crossSite = requireSameOrigin(request);
  if (crossSite) return crossSite;

  const params = new URL(request.url).searchParams;
  const scope = parseScope(params);
  if (!scope) return invalidRequest("course_id 与 curriculum_edition_id 必须是有效 UUID。" );

  const body = await readJsonObject(request);
  if (!body || Object.keys(body).some((key) => !BODY_KEYS.has(key))) {
    return invalidRequest("复核请求正文无效或包含未知字段。" );
  }
  const candidateId = typeof body.candidate_id === "string" ? body.candidate_id : "";
  const kind = body.kind;
  const action = body.action;
  const rationale = typeof body.rationale === "string" ? body.rationale.trim() : "";
  if (!UUID_PATTERN.test(candidateId)) return invalidRequest("candidate_id 必须是有效 UUID。" );
  if (kind !== "node" && kind !== "relation") return invalidRequest("kind 必须为 node 或 relation。" );
  if (action !== "approve" && action !== "reject") {
    return invalidRequest("action 必须为 approve 或 reject。" );
  }
  if (rationale.length < 1 || rationale.length > 4000) {
    return invalidRequest("复核理由长度必须为 1–4000 个字符。" );
  }

  const base = `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}/knowledge`;
  const path =
    action === "approve"
      ? `${base}/${kind === "node" ? "nodes" : "relations"}/${candidateId}/approve`
      : `${base}/candidates/${candidateId}/reject`;
  const upstreamBody = action === "approve" ? { rationale } : { rationale, kind };
  return forwardBackendJson({
    path,
    method: "POST",
    body: upstreamBody,
    parse: parseCandidateActionResponse,
    assertValue: (value) => {
      if (
        value.candidate_id !== candidateId ||
        value.kind !== kind ||
        value.action !== action
      ) {
        throw new Error("review decision does not match request");
      }
    },
  });
}
