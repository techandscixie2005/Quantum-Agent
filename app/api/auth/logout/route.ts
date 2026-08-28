import { cookies } from "next/headers";

/**
 * PRD V3.1 §3: logout BFF route.  Clears the ``qa_session`` cookie and
 * asks the backend to revoke the session + forget the vault entry.
 */

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

function clearQaSessionCookie(): string {
  const secure = true;
  const sameSite = "Lax";
  return `qa_session=; HttpOnly; Max-Age=0; Path=/; SameSite=${sameSite}${secure ? "; Secure" : ""}`;
}

export async function POST() {
  const token = (await cookies()).get("qa_session")?.value ?? null;
  const baseUrl = backendBaseUrl();
  if (token && baseUrl) {
    try {
      await fetch(new URL("/api/v1/auth/logout", baseUrl), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: "{}",
        cache: "no-store",
        signal: AbortSignal.timeout(8_000),
      });
    } catch {
      // Best-effort: the cookie is cleared regardless.
    }
  }
  return new Response(null, {
    status: 204,
    headers: { "Set-Cookie": clearQaSessionCookie() },
  });
}
