import { analyticsSnapshot } from "../../../../lib/repository";
import { extractTeacherCookie, verifyTeacherSession } from "../../../../lib/teacher-auth";

export async function GET(request: Request) {
  const token = extractTeacherCookie(request);
  if (!token || !(await verifyTeacherSession(token))) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  try { return Response.json({ ...(await analyticsSnapshot()), source: "database" }); }
  catch { return Response.json({ activeStudents: 0, pendingEscalations: 0, highHintDependency: 0, failedToolRuns: 0, misconceptionCounts: [], recentEscalations: [], source: "empty" }); }
}

