import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { studentStates, tutorSessions, tutorTurns } from "../../../../db/schema";
import { ensureUser } from "../../../../lib/repository";
import { requestUser } from "../../../../lib/request-user";

export async function GET(request: Request) {
  try {
    const identity = requestUser(request);
    const user = await ensureUser(identity.email, identity.displayName);
    const db = getDb();
    const sessions = await db.select().from(tutorSessions).where(eq(tutorSessions.userId, user.id)).limit(200);
    const turns: typeof tutorTurns.$inferSelect[] = [];
    for (const session of sessions) {
      const sessionTurns = await db.select().from(tutorTurns).where(eq(tutorTurns.sessionId, session.id));
      turns.push(...sessionTurns);
    }
    const states = await db.select().from(studentStates).where(eq(studentStates.userId, user.id)).limit(200);
    return Response.json({
      user: { email: identity.email, displayName: identity.displayName },
      sessions,
      turns: turns.map((turn) => ({
        id: turn.id,
        sessionId: turn.sessionId,
        role: turn.role,
        content: turn.content,
        taskClass: turn.taskClass,
        hintLevel: turn.hintLevel,
        modelProvider: turn.modelProvider === "deterministic" ? null : turn.modelProvider,
        createdAt: turn.createdAt,
      })),
      masteryStates: states.map((state) => ({
        conceptId: state.conceptId,
        mastery: state.mastery,
        status: state.status,
        updatedAt: state.updatedAt,
      })),
      exportedAt: new Date().toISOString(),
    });
  } catch (error) {
    return Response.json({ error: "无法导出数据", detail: error instanceof Error ? error.message : "未知错误" }, { status: 500 });
  }
}