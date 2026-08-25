import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  traceScopeSchema,
  type TraceScope,
} from "@/app/components/teacher-traces/contracts";

const TRACE_ID_PATTERN = /^[a-zA-Z0-9._:-]{1,128}$/;
const MAX_JSON_BYTES = 4_000_000;

type StaffBackendContext = Readonly<{ baseUrl: URL; token: string }>;

export type StaffContextResult =
  | Readonly<{ ok: true; value: StaffBackendContext }>
  | Readonly<{ ok: false; response: NextResponse }>;

export type StaffFetchResult =
  | Readonly<{ ok: true; payload: unknown; status: number; traceId: string | null }>
  | Readonly<{ ok: false; response: NextResponse }>;

export function traceError(
  status: number,
  code: string,
  message: string,
  traceId?: string | null,
): NextResponse {
  return NextResponse.json(
    {
      error: {
        code,
        message,
        ...(traceId && TRACE_ID_PATTERN.test(traceId) ? { trace_id: traceId } : {}),
      },
    },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

export function privateTraceJson(
  payload: unknown,
  status = 200,
  traceId?: string | null,
): NextResponse {
  return NextResponse.json(payload, {
    status,
    headers: {
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
      ...(traceId && TRACE_ID_PATTERN.test(traceId) ? { "X-Trace-Id": traceId } : {}),
    },
  });
}

export function parseTraceScope(params: URLSearchParams): TraceScope | null {
  const parsed = traceScopeSchema.safeParse({
    courseId: params.get("course_id")?.trim() ?? "",
    curriculumEditionId: params.get("curriculum_edition_id")?.trim() ?? "",
  });
  return parsed.success ? parsed.data : null;
}

export function teacherTracePath(scope: TraceScope, suffix = ""): string {
  return (
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/teacher/agent-traces${suffix}`
  );
}

export function teachingThreadPath(
  scope: TraceScope,
  conversationId: string,
  operation: "interrupt" | "resume",
): string {
  return (
    `/api/v1/courses/${scope.courseId}/editions/${scope.curriculumEditionId}` +
    `/teaching/threads/${conversationId}/${operation}`
  );
}

export async function staffBackendContext(): Promise<StaffContextResult> {
  const token = (await cookies()).get("qa_session")?.value;
  if (!token) {
    return {
      ok: false,
      response: traceError(
        401,
        "AUTH_REQUIRED",
        "需要已登录的教学团队课程会话才能检查 Agent trace。",
      ),
    };
  }
  if (token.length > 4_096) {
    return {
      ok: false,
      response: traceError(401, "INVALID_SESSION", "课程会话格式无效，请重新登录。"),
    };
  }

  const configured = process.env.QUANTUM_API_BASE_URL?.trim();
  if (!configured) {
    return {
      ok: false,
      response: traceError(
        503,
        "BACKEND_NOT_CONFIGURED",
        "教学治理服务地址尚未配置；本页不会显示模拟 trace。",
      ),
    };
  }
  try {
    const baseUrl = new URL(configured.endsWith("/") ? configured : `${configured}/`);
    if (!(["http:", "https:"] as const).includes(baseUrl.protocol as "http:" | "https:")) {
      throw new Error("unsupported protocol");
    }
    if (baseUrl.username || baseUrl.password) throw new Error("embedded credentials");
    return { ok: true, value: { baseUrl, token } };
  } catch {
    return {
      ok: false,
      response: traceError(
        503,
        "BACKEND_NOT_CONFIGURED",
        "教学治理服务地址无效；本页不会显示模拟 trace。",
      ),
    };
  }
}

function safeUpstreamMessage(status: number): string {
  if (status === 401) return "课程会话已失效，请重新登录后再试。";
  if (status === 403) return "当前课程身份不属于教学团队，无法检查或裁决 trace。";
  if (status === 404) return "请求的 trace 或当前人工复核状态不存在。";
  if (status === 409) return "该复核状态已经变化；请刷新后基于最新 checkpoint 决策。";
  if (status === 422) return "复核决定未通过后端约束校验。";
  if (status >= 500) return "教学治理服务当前不可用；本页不会以生成内容替代。";
  return "教学治理服务拒绝了该请求。";
}

async function boundedJson(response: Response): Promise<unknown> {
  const declared = Number(response.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > MAX_JSON_BYTES) {
    throw new Error("upstream payload is too large");
  }
  if (!response.body) throw new Error("upstream payload is missing");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let total = 0;
  let serialized = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_JSON_BYTES) {
      await reader.cancel("trace payload exceeded the bounded response size");
      throw new Error("upstream payload is too large");
    }
    serialized += decoder.decode(value, { stream: true });
  }
  serialized += decoder.decode();
  return JSON.parse(serialized) as unknown;
}

export async function fetchStaffJson(
  context: StaffBackendContext,
  path: string,
  options: Readonly<{ method?: "GET" | "POST"; body?: unknown; timeoutMs?: number }> = {},
): Promise<StaffFetchResult> {
  const headers = new Headers({
    Accept: "application/json",
    Authorization: `Bearer ${context.token}`,
  });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");

  let upstream: Response;
  try {
    upstream = await fetch(new URL(path, context.baseUrl), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: AbortSignal.timeout(options.timeoutMs ?? 20_000),
    });
  } catch {
    return {
      ok: false,
      response: traceError(
        503,
        "BACKEND_UNAVAILABLE",
        "无法连接教学治理服务；当前选择与复核意见仍保留在浏览器中。",
      ),
    };
  }

  const traceId = upstream.headers.get("x-trace-id");
  let payload: unknown;
  try {
    payload = await boundedJson(upstream);
  } catch {
    return {
      ok: false,
      response: traceError(
        502,
        "INVALID_UPSTREAM_RESPONSE",
        "教学治理服务返回了无法解析的响应；本页已拒绝显示。",
        traceId,
      ),
    };
  }
  if (!upstream.ok) {
    return {
      ok: false,
      response: traceError(
        upstream.status,
        `UPSTREAM_${upstream.status}`,
        safeUpstreamMessage(upstream.status),
        traceId,
      ),
    };
  }
  return { ok: true, payload, status: upstream.status, traceId };
}
