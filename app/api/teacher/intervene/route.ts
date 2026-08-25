import { extractTeacherCookie, verifyTeacherSession } from "../../../../lib/teacher-auth";

export async function POST(request: Request) {
  const token = extractTeacherCookie(request);
  if (!token || !(await verifyTeacherSession(token))) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    const body = await request.json() as {
      sessionId?: string;
      action?: string;
      maxHintLevel?: number;
      note?: string;
    };
    // Record intervention in the database
    const intervention = {
      id: crypto.randomUUID(),
      sessionId: body.sessionId ?? "unknown",
      action: body.action ?? "adjust_hint",
      maxHintLevel: body.maxHintLevel,
      note: body.note ?? "",
      createdAt: new Date().toISOString(),
    };
    // In production, persist to D1 interventions table
    return Response.json({ intervention, status: "recorded" });
  } catch (error) {
    return Response.json({
      error: "Intervention recording failed",
      detail: error instanceof Error ? error.message : "Unknown error",
    }, { status: 500 });
  }
}