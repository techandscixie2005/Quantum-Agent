import { recentSessions } from "../../../lib/repository";
import { requestUser } from "../../../lib/request-user";

export async function GET(request: Request) {
  try { return Response.json({ sessions: await recentSessions(requestUser(request).email) }); }
  catch { return Response.json({ sessions: [], persisted: false }); }
}

