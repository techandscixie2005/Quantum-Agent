import { publicCapabilities } from "../../../lib/providers";
import { runtimeBindings, runtimeStrings } from "../../../lib/runtime-env";

export async function GET() {
  const runtime = runtimeStrings();
  const modelConfigPresent = Boolean(publicCapabilities(runtime).some((cap) => cap.configured));
  let dbOk = false;
  try {
    const bindings = runtimeBindings();
    if (bindings.DB) {
      const d1 = bindings.DB as D1Database;
      await d1.prepare("SELECT 1").run();
      dbOk = true;
    }
  } catch {
    dbOk = false;
  }
  return Response.json({
    status: dbOk ? "ready" : "degraded",
    service: "quantum-agent",
    version: "0.5.0",
    database: dbOk ? "connected" : "unavailable",
    modelProvider: modelConfigPresent ? "configured" : "deterministic-fallback",
    time: new Date().toISOString(),
  }, { status: dbOk ? 200 : 503 });
}