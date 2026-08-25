import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  ContractError,
  UUID_PATTERN,
  type PhaseOneScope,
} from "@/app/components/knowledge/contracts";

type RuntimeParser<T> = (value: unknown) => T;

type ForwardOptions<T> = Readonly<{
  path: string;
  method?: "GET" | "POST";
  body?: unknown;
  parse: RuntimeParser<T>;
  scope?: PhaseOneScope;
  assertScope?: (value: T, scope: PhaseOneScope) => void;
  assertValue?: (value: T) => void;
}>;

const TRACE_ID_PATTERN = /^[a-zA-Z0-9._:-]{1,128}$/;

function errorResponse(
  status: number,
  code: string,
  message: string,
  traceId?: string | null,
) {
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

function backendBaseUrl(): URL | null {
  const configured = process.env.QUANTUM_API_BASE_URL?.trim();
  if (!configured) return null;
  try {
    const parsed = new URL(configured.endsWith("/") ? configured : `${configured}/`);
    if (!(["http:", "https:"] as const).includes(parsed.protocol as "http:" | "https:")) {
      return null;
    }
    if (parsed.username || parsed.password) return null;
    return parsed;
  } catch {
    return null;
  }
}

function safeUpstreamMessage(status: number, value: unknown): string {
  if (status >= 500) return "知识服务当前不可用；本页未使用缓存或生成内容替代。";
  if (status === 401) return "课程会话已失效，请重新登录后再试。";
  if (status === 403) return "当前课程角色无权执行此操作。";

  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const detail = (value as Record<string, unknown>).detail;
    if (typeof detail === "string" && detail.length > 0 && detail.length <= 500) {
      return detail;
    }
  }
  if (status === 404) return "请求的课程知识记录不存在或尚未发布。";
  if (status === 409) return "复核记录已经变化；请刷新队列后重新决策。";
  return "知识服务拒绝了该请求。";
}

export function parseScope(params: URLSearchParams): PhaseOneScope | null {
  const courseId = params.get("course_id")?.trim() ?? "";
  const curriculumEditionId = params.get("curriculum_edition_id")?.trim() ?? "";
  if (!UUID_PATTERN.test(courseId) || !UUID_PATTERN.test(curriculumEditionId)) return null;
  return { courseId, curriculumEditionId };
}

export function normalizedSearchQuery(params: URLSearchParams): string | null {
  const query = params.get("q")?.trim().replace(/\s+/g, " ") ?? "";
  return query.length >= 1 && query.length <= 300 ? query : null;
}

export function candidateId(params: URLSearchParams): string | null {
  const value = params.get("candidate_id")?.trim() ?? "";
  return UUID_PATTERN.test(value) ? value : null;
}

export function invalidRequest(message: string) {
  return errorResponse(400, "INVALID_REQUEST", message);
}

export function requireSameOrigin(request: Request): NextResponse | null {
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return errorResponse(403, "CROSS_SITE_REQUEST_BLOCKED", "跨站复核请求已被拒绝。");
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return errorResponse(403, "ORIGIN_MISMATCH", "复核请求来源与当前站点不一致。");
  }
  return null;
}

export async function readJsonObject(request: Request): Promise<Record<string, unknown> | null> {
  const contentType = request.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.startsWith("application/json")) return null;
  try {
    const value: unknown = await request.json();
    if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
    return value as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function forwardBackendJson<T>(options: ForwardOptions<T>): Promise<NextResponse> {
  const sessionToken = (await cookies()).get("qa_session")?.value;
  if (!sessionToken) {
    return errorResponse(401, "AUTH_REQUIRED", "需要已登录的课程会话才能访问知识图谱。");
  }
  if (sessionToken.length > 4096) {
    return errorResponse(401, "INVALID_SESSION", "课程会话格式无效，请重新登录。" );
  }

  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return errorResponse(
      503,
      "BACKEND_NOT_CONFIGURED",
      "知识服务地址尚未配置；页面不会显示示例或推测数据。",
    );
  }

  const headers = new Headers({
    Accept: "application/json",
    Authorization: `Bearer ${sessionToken}`,
  });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");

  let upstream: Response;
  try {
    upstream = await fetch(new URL(options.path, baseUrl), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });
  } catch {
    return errorResponse(
      503,
      "BACKEND_UNAVAILABLE",
      "无法连接知识服务；已保留当前选择，可以稍后重试。",
    );
  }

  const traceId = upstream.headers.get("x-trace-id");
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return errorResponse(
      502,
      "INVALID_UPSTREAM_RESPONSE",
      "知识服务返回了无法验证的响应；本页已拒绝显示。",
      traceId,
    );
  }

  if (!upstream.ok) {
    return errorResponse(
      upstream.status,
      `UPSTREAM_${upstream.status}`,
      safeUpstreamMessage(upstream.status, payload),
      traceId,
    );
  }

  try {
    const parsed = options.parse(payload);
    if (options.scope && options.assertScope) options.assertScope(parsed, options.scope);
    options.assertValue?.(parsed);
    return NextResponse.json(parsed, {
      status: upstream.status,
      headers: {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        ...(traceId && TRACE_ID_PATTERN.test(traceId) ? { "X-Trace-Id": traceId } : {}),
      },
    });
  } catch (error) {
    const contractMessage =
      error instanceof ContractError ? "响应不符合课程知识契约。" : "响应验证失败。";
    return errorResponse(
      502,
      "INVALID_UPSTREAM_CONTRACT",
      `${contractMessage} 本页已拒绝显示未经验证的数据。`,
      traceId,
    );
  }
}
