import { checkRateLimit } from "../../../../lib/security";

/**
 * PRD V3.1 §3: API-key login BFF route.
 *
 * Proxies the authoritative Python ``/api/v1/auth/login`` endpoint.  The
 * student enters their 词元计划/一〇七杯 API key; the backend probes the USTC
 * model service, mints an opaque session, stores the Fernet-encrypted key in
 * the session vault, and returns a session token.  This route sets the
 * ``qa_session`` cookie the /agent BFF requires.
 *
 * The API key is NEVER written to a cookie, localStorage, or a log.  It
 * travels Browser → HTTPS POST → this BFF → Python → vault, and is forgotten
 * by the BFF the moment the upstream response arrives.  Rate-limited to block
 * key enumeration.  Fail-closed when the backend is unconfigured or the key
 * is rejected.
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

function clearQaSessionCookie(): string {
  const secure = true;
  const sameSite = "Lax";
  return `qa_session=; HttpOnly; Max-Age=0; Path=/; SameSite=${sameSite}${secure ? "; Secure" : ""}`;
}

export async function POST(request: Request) {
  const rate = checkRateLimit(
    `login:${request.headers.get("cf-connecting-ip") ?? "local"}`,
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
      { error: "教学服务地址尚未配置；请联系竞赛组织者。" },
      { status: 503 },
    );
  }
  let body: { api_key?: string; course_id?: string };
  try {
    body = (await request.json()) as { api_key?: string; course_id?: string };
  } catch {
    return Response.json({ error: "请求正文必须是 JSON 对象。" }, { status: 400 });
  }
  const apiKey = (body.api_key ?? "").trim();
  if (!apiKey || apiKey.length < 16 || apiKey.length > 256) {
    return Response.json({ error: "请提供有效的 API Key。" }, { status: 400 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(new URL("/api/v1/auth/login", baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, course_id: body.course_id ?? null }),
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    return Response.json(
      { error: "无法连接教学服务；请稍后重试。" },
      { status: 503 },
    );
  }
  if (!upstream.ok) {
    const message =
      upstream.status === 401
        ? "API Key 被模型服务拒绝或模型服务不可用。"
        : upstream.status === 429
          ? "登录尝试过于频繁，请稍后再试。"
          : "登录被拒绝。";
    return Response.json(
      { error: message },
      { status: upstream.status },
    );
  }
  const data = (await upstream.json()) as { session_token?: string };
  if (!data.session_token) {
    return Response.json({ error: "教学服务未返回会话凭证。" }, { status: 502 });
  }
  return Response.json(
    { ok: true },
    { status: 200, headers: { "Set-Cookie": setQaSessionCookie(data.session_token) } },
  );
}

export async function DELETE() {
  return new Response(null, {
    status: 204,
    headers: { "Set-Cookie": clearQaSessionCookie() },
  });
}
