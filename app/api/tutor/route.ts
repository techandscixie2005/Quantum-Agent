import { DEFAULT_COURSE_ID } from "../../../lib/course-knowledge";
import { tutorGraph } from "../../../lib/agent";
import { loadPublishedKnowledge, persistTutorExchange } from "../../../lib/repository";
import { requestUser } from "../../../lib/request-user";
import { checkRateLimit, validateAttachments } from "../../../lib/security";
import type { CapabilityId, TutorAnswer, TutorMode, TutorResponse } from "../../../lib/types";

const validModes = new Set<TutorMode>(["concept", "derivation", "experiment", "project"]);
const validCapabilities = new Set<CapabilityId>(["quick", "deep", "vision", "vision-reasoner", "code"]);

export async function POST(request: Request) {
  try {
    const body = await request.json() as {
      message?: string;
      mode?: string;
      sessionId?: string;
      courseId?: string;
      attemptedWork?: string;
      requestedHintLevel?: number;
      capability?: string;
      attachments?: Array<{ name: string; mimeType: string; dataUrl: string }>;
    };

    const message = body.message?.trim() ?? "";
    if (!message || message.length > 12000) {
      return Response.json({ error: "message must contain 1–12000 characters" }, { status: 400 });
    }

    const identity = requestUser(request);
    const rate = checkRateLimit(identity.email);
    if (!rate.allowed) {
      return Response.json(
        { error: "请求过于频繁，请稍后再试" },
        { status: 429, headers: { "Retry-After": String(rate.retryAfterSeconds) } }
      );
    }

    const attachments = validateAttachments(body.attachments);
    const mode = validModes.has(body.mode as TutorMode) ? body.mode as TutorMode : "concept";
    let capability = validCapabilities.has(body.capability as CapabilityId)
      ? body.capability as CapabilityId
      : "quick";
    if (attachments.length && capability !== "vision" && capability !== "vision-reasoner") {
      capability = "vision";
    }

    const sessionId = body.sessionId ?? crypto.randomUUID();
    const threadId = `tutor-${sessionId}`;

    // Invoke the LangGraph tutor graph
    const result = await tutorGraph.invoke(
      {
        message,
        mode,
        sessionId,
        courseId: body.courseId ?? DEFAULT_COURSE_ID,
        attemptedWork: body.attemptedWork,
        requestedHintLevel: body.requestedHintLevel,
        capability,
        attachments,
        userEmail: identity.email,
        userDisplayName: identity.displayName,
      },
      {
        configurable: {
          thread_id: threadId,
        },
      }
    );

    // Build the API response from graph state
    const answer = (result.answer ?? {
      conclusion: "当前无法完成教学处理。",
      physicalPicture: "",
      mathematics: "",
      misconception: "",
      checkQuestion: "",
      suggestedAction: "请重试或联系教师。",
    }) as TutorAnswer;

    const response: TutorResponse = {
      sessionId,
      turnId: crypto.randomUUID(),
      taskClass: (result.taskClass as TutorResponse["taskClass"]) ?? "COURSE_QA",
      hintLevel: (Math.min(Math.max(result.hintLevel ?? 1, 1), 5) as 1 | 2 | 3 | 4 | 5),
      answer,
      citations: (result.citations ?? []) as TutorResponse["citations"],
      evidence: (result.evidence ?? []) as TutorResponse["evidence"],
      trace: (result.trace ?? []) as TutorResponse["trace"],
      misconceptionId: result.misconceptionId ?? null,
      model: {
        capability: (result.capability ?? "quick") as CapabilityId,
        label: result.modelCapability ?? "确定性教学回退",
        source: (result.modelSource as "api" | "deterministic-fallback") ?? "deterministic-fallback",
      },
      createdAt: result.completedAt ?? new Date().toISOString(),
    };

    // Persist the exchange
    let persisted = true;
    try {
      const payload = {
        message,
        mode,
        sessionId,
        courseId: body.courseId ?? DEFAULT_COURSE_ID,
        attemptedWork: body.attemptedWork,
        requestedHintLevel: body.requestedHintLevel,
        capability,
        attachments,
      };
      await persistTutorExchange(
        identity,
        payload,
        response,
        { provider: "ustc", model: result.modelCapability ?? "quantum-tutor" }
      );
    } catch {
      persisted = false;
    }

    return Response.json({ ...response, persisted });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown error";
    const clientError = /图片|附件|data URL|支持 PNG|image|最多上传|不能超过|编码无效/.test(detail);
    return Response.json(
      { error: clientError ? "提交内容不符合要求" : "Tutor workflow failed safely", detail },
      { status: clientError ? 400 : 500 }
    );
  }
}