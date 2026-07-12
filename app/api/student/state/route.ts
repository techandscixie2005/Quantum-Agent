import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { studentStates } from "../../../../db/schema";
import { ensureUser } from "../../../../lib/repository";
import { requestUser } from "../../../../lib/request-user";

export async function GET(request: Request) {
  try { const identity = requestUser(request); const user = await ensureUser(identity.email, identity.displayName); return Response.json({ states: await getDb().select().from(studentStates).where(eq(studentStates.userId, user.id)).limit(100) }); }
  catch { return Response.json({ states: [], persisted: false }); }
}

