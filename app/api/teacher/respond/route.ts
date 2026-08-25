import { extractTeacherCookie, verifyTeacherSession } from "../../../../lib/teacher-auth";

export async function POST(request: Request) {
  const token = extractTeacherCookie(request);
  if (!token || !(await verifyTeacherSession(token))) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    const body = await request.json() as {
      escalationId?: string;
      message?: string;
      action?: "approve" | "reject" | "respond";
    };
    const response = {
      id: crypto.randomUUID(),
      escalationId: body.escalationId ?? "unknown",
      message: body.message ?? "",
      action: body.action ?? "respond",
      createdAt: new Date().toISOString(),
    };
    return Response.json({ response, status: "sent" });
  } catch (error) {
    return Response.json({
      error: "Response failed",
      detail: error instanceof Error ? error.message : "Unknown error",
    }, { status: 500 });
  }
}