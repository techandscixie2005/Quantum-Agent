import { asc, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { tutorSessions, tutorTurns } from "../../../db/schema";

export async function GET(request: Request) {
  const sessionId = new URL(request.url).searchParams.get("sessionId");
  if (!sessionId) return Response.json({ error: "sessionId is required" }, { status: 400 });
  try {
    const session = (await getDb().select().from(tutorSessions).where(eq(tutorSessions.id, sessionId)).limit(1))[0];
    const turns = await getDb().select().from(tutorTurns).where(eq(tutorTurns.sessionId, sessionId)).orderBy(asc(tutorTurns.createdAt));
    return Response.json({ session, turns: turns.map((turn) => ({ ...turn, evidence: JSON.parse(turn.evidenceJson), trace: JSON.parse(turn.traceJson) })) });
  } catch (error) { return Response.json({ error: "Trace unavailable", detail: error instanceof Error ? error.message : "Unknown error" }, { status: 500 }); }
}

