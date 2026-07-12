import { persistToolRun } from "../../../lib/repository";
import { runVerifier } from "../../../lib/verifiers";

export async function POST(request: Request) {
  const started = Date.now();
  try {
    const body = await request.json() as { tool?: string; input?: Record<string, unknown>; sessionId?: string };
    if (!body.tool || !body.input) return Response.json({ error: "tool and input are required" }, { status: 400 });
    const result = runVerifier(body.tool, body.input);
    let persisted = true; try { await persistToolRun(body.sessionId, body.input, result, Date.now() - started); } catch { persisted = false; }
    return Response.json({ ...result, persisted, durationMs: Date.now() - started });
  } catch (error) { return Response.json({ error: "Verification failed", detail: error instanceof Error ? error.message : "Unknown error" }, { status: 500 }); }
}

