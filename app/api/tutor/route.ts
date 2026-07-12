import { DEFAULT_COURSE_ID } from "../../../lib/course-knowledge";
import { providerConfigForCapability } from "../../../lib/providers";
import { loadPublishedKnowledge, persistTutorExchange } from "../../../lib/repository";
import { requestUser } from "../../../lib/request-user";
import { runtimeStrings } from "../../../lib/runtime-env";
import { checkRateLimit, validateAttachments } from "../../../lib/security";
import { runTutorWorkflow } from "../../../lib/tutor-engine";
import type { CapabilityId, TutorMode, TutorRequest } from "../../../lib/types";

const validModes = new Set<TutorMode>(["concept", "derivation", "experiment", "project"]);
const validCapabilities = new Set<CapabilityId>(["quick", "deep", "vision", "vision-reasoner", "code"]);

export async function POST(request: Request) {
  try {
    const body = await request.json() as Partial<TutorRequest>;
    const message = body.message?.trim() ?? "";
    if (!message || message.length > 12000) return Response.json({ error: "message must contain 1–12000 characters" }, { status: 400 });
    const identity = requestUser(request);
    const rate = checkRateLimit(identity.email);
    if (!rate.allowed) return Response.json({ error: "请求过于频繁，请稍后再试" }, { status: 429, headers: { "Retry-After": String(rate.retryAfterSeconds) } });
    const attachments = validateAttachments(body.attachments);
    const mode = validModes.has(body.mode as TutorMode) ? body.mode as TutorMode : "concept";
    const runtime = runtimeStrings();
    let capability = validCapabilities.has(body.capability as CapabilityId) ? body.capability as CapabilityId : "quick";
    if (attachments.length && capability !== "vision" && capability !== "vision-reasoner") capability = "vision";
    const provider = providerConfigForCapability(capability, runtime);
    const payload: TutorRequest = { message, mode, sessionId: body.sessionId, courseId: body.courseId ?? DEFAULT_COURSE_ID, attemptedWork: body.attemptedWork, requestedHintLevel: body.requestedHintLevel, capability, attachments };
    const dynamicKnowledge = await loadPublishedKnowledge(payload.courseId);
    const response = await runTutorWorkflow(payload, provider, dynamicKnowledge);
    let persisted = true;
    try { await persistTutorExchange(identity, payload, response, { provider: provider.provider, model: provider.model }); } catch { persisted = false; }
    return Response.json({ ...response, persisted });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown error";
    const clientError = /图片|附件|data URL|支持 PNG|image|最多上传|不能超过|编码无效/.test(detail);
    return Response.json({ error: clientError ? "提交内容不符合要求" : "Tutor workflow failed safely", detail }, { status: clientError ? 400 : 500 });
  }
}
