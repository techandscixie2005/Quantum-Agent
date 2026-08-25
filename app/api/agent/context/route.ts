import { parseStudentCourseContext } from "@/app/components/agent/contracts";
import {
  agentError,
  quantumApiBaseUrl,
  safeAgentUpstreamMessage,
  studentSessionToken,
} from "@/app/api/agent/_shared";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const token = await studentSessionToken();
  if (!token) return agentError(401, "AUTH_REQUIRED", "需要课程会话才能进入 Agent。 ");
  const baseUrl = quantumApiBaseUrl();
  if (!baseUrl) {
    return agentError(503, "BACKEND_NOT_CONFIGURED", "Quantum Agent 后端地址尚未配置。");
  }

  let upstream: Response;
  try {
    upstream = await fetch(new URL("/api/v1/me/course-context", baseUrl), {
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });
  } catch {
    return agentError(503, "BACKEND_UNAVAILABLE", "无法连接 Quantum Agent 后端。");
  }
  const traceId = upstream.headers.get("x-trace-id");
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return agentError(502, "INVALID_UPSTREAM_RESPONSE", "课程范围响应无法解析。", traceId);
  }
  if (!upstream.ok) {
    return agentError(
      upstream.status,
      `UPSTREAM_${upstream.status}`,
      safeAgentUpstreamMessage(upstream.status),
      traceId,
    );
  }
  try {
    return Response.json(parseStudentCourseContext(payload), {
      headers: {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return agentError(502, "INVALID_UPSTREAM_CONTRACT", "课程范围响应未通过契约校验。", traceId);
  }
}

