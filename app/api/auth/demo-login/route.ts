import { checkRateLimit } from "../../../../lib/security";

/**
 * PRD V3.0 P1-4: competition demo-account login.
 *
 * Proxies the authoritative Python ``/api/v1/auth/demo-login`` endpoint and
 * sets the ``qa_session`` cookie the /agent BFF requires.  A judge POSTs the
 * shared ``DEMO_LOGIN_SECRET``; the backend mints a short-lived opaque
 * session token for the seeded demo student.  The secret is never read in
 * the browser — it is sent server-to-server via the BFF.  Rate-limited to
 * block brute force.  Fail-closed when the backend is unconfigured or the
 * secret is wrong.
 */

const SESSION_DURATION_SECONDS = 8 * 60 * 60;

function backendBaseUrl(): URL | null {
  const configured = process.env.QUANTUM_API_BASE_URL?.trim();
  if (!configured) return null;
  try {
    const parsed = new URL(configured.endsWith("/") ? configured : `${configured}/`);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (parsed.username || parsed.password) return null;
    return parsed;
  } catch {
    return null;
  }
}

function setQaSessionCookie(value: string): string {
  const secure = true;
  const sameSite = "Lax";
  return `qa_session=${encodeURIComponent(value)}; HttpOnly; Max-Age=${SESSION_DURATION_SECONDS}; Path=/; SameSite=${sameSite}${secure ? "; Secure" : ""}`;
}

export async function POST(request: Request) {
  const rate = checkRateLimit(
    `demo-login:${request.headers.get("cf-connecting-ip") ?? "local"}`,
    10,
    300_000,
  );
  if (!rate.allowed) {
    return Response.json(
      { error: "登录尝试过于频繁，请稍后再试" },
      { status: 429, headers: { "Retry-After": String(rate.retryAfterSeconds) } },
    );
  }
  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return Response.json(
      { error: "教学服务地址尚未配置；请联系竞赛组织者获取 demo 登录支持。" },
      { status: 503 },
    );
  }
  let body: { secret?: string; course_id?: string };
  try {
    body = (await request.json()) as { secret?: string; course_id?: string };
  } catch {
    return Response.json({ error: "请求正文必须是 JSON 对象。" }, { status: 400 });
  }
  const secret = (body.secret ?? "").trim();
  if (!secret || secret.length < 8 || secret.length > 256) {
    return Response.json({ error: "请提供有效的 demo 密钥。" }, { status: 400 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(new URL("/api/v1/auth/demo-login", baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret, course_id: body.course_id ?? null }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return Response.json(
      { error: "无法连接教学服务；请稍后重试。" },
      { status: 503 },
    );
  }
  if (!upstream.ok) {
    const detail = await upstream.text().catch(() => "");
    return Response.json(
      { error: "Demo 登录被拒绝。", detail: detail.slice(0, 200) },
      { status: upstream.status },
    );
  }
  const data = (await upstream.json()) as { session_token?: string };
  if (!data.session_token) {
    return Response.json({ error: "教学服务未返回会话凭证。" }, { status: 502 });
  }
  return Response.json(
    { ok: true, course_id: body.course_id ?? null },
    { status: 200, headers: { "Set-Cookie": setQaSessionCookie(data.session_token) } },
  );
}
