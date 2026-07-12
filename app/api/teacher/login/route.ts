import { issueTeacherSession, setTeacherCookie, verifyTeacherPassword } from "../../../../lib/teacher-auth";
import { checkRateLimit } from "../../../../lib/security";

export async function POST(request: Request) {
  try {
    const body = await request.json() as { password?: string };
    const password = body.password ?? "";
    const rate = checkRateLimit(`teacher-login:${request.headers.get("cf-connecting-ip") ?? "local"}`, 5, 300_000);
    if (!rate.allowed) return Response.json({ error: "登录尝试过于频繁，请稍后再试" }, { status: 429, headers: { "Retry-After": String(rate.retryAfterSeconds) } });
    if (!password || password.length > 128) return Response.json({ error: "请输入密码" }, { status: 400 });
    const valid = await verifyTeacherPassword(password);
    if (!valid) return Response.json({ error: "密码错误" }, { status: 401 });
    const token = await issueTeacherSession();
    return Response.json({ ok: true }, {
      status: 200,
      headers: { "Set-Cookie": setTeacherCookie(token) },
    });
  } catch (error) {
    return Response.json({ error: "登录失败", detail: error instanceof Error ? error.message : "未知错误" }, { status: 500 });
  }
}