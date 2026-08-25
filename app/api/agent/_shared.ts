import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const TRACE_ID_PATTERN = /^[a-zA-Z0-9._:-]{1,128}$/;

export function agentError(
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

export function quantumApiBaseUrl(): URL | null {
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

export async function studentSessionToken(): Promise<string | null> {
  const token = (await cookies()).get("qa_session")?.value ?? null;
  return token && token.length <= 4_096 ? token : null;
}

export function safeAgentUpstreamMessage(status: number): string {
  if (status === 401) return "课程会话已失效，请重新登录。";
  if (status === 403) return "当前身份无权访问这项课程资源。";
  if (status === 404) return "课程资源不存在或尚未发布。";
  if (status === 409) return "资源状态已经变化，请刷新后重试。";
  if (status === 413) return "附件超过课程允许的大小。";
  if (status === 415) return "该文件格式未通过安全验证。";
  if (status >= 500) return "Quantum Agent 后端当前不可用。";
  return "Quantum Agent 后端拒绝了请求。";
}

