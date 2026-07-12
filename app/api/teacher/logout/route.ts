import { clearTeacherCookie } from "../../../../lib/teacher-auth";

export async function POST() {
  return Response.json({ ok: true }, {
    status: 200,
    headers: { "Set-Cookie": clearTeacherCookie() },
  });
}