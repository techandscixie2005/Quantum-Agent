import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { projects, studentStates, tutorSessions, tutorTurns } from "../../../../db/schema";
import { ensureUser } from "../../../../lib/repository";
import { requestUser } from "../../../../lib/request-user";

export async function POST(request: Request) {
  try {
    const identity = requestUser(request);
    const user = await ensureUser(identity.email, identity.displayName);
    const db = getDb();
    const sessions = await db.select({ id: tutorSessions.id }).from(tutorSessions).where(eq(tutorSessions.userId, user.id));
    const sessionIds = sessions.map((s) => s.id);
    let deletedTurns = 0;
    for (const sessionId of sessionIds) {
      const result = await db.delete(tutorTurns).where(eq(tutorTurns.sessionId, sessionId));
      deletedTurns += (result.meta as { rows_written?: number } | undefined)?.rows_written ?? 0;
    }
    await db.delete(tutorSessions).where(eq(tutorSessions.userId, user.id));
    await db.delete(studentStates).where(eq(studentStates.userId, user.id));
    await db.delete(projects).where(eq(projects.userId, user.id));
    return Response.json({
      ok: true,
      detail: `${sessions.length} 个会话、${deletedTurns} 轮对话、学习状态与项目进度已被删除。`,
      deletedAt: new Date().toISOString(),
    });
  } catch (error) {
    return Response.json({ error: "无法删除数据", detail: error instanceof Error ? error.message : "未知错误" }, { status: 500 });
  }
}