import { runtimeStrings } from "../../../lib/runtime-env";
import { capabilityCatalog } from "../../../lib/providers";

export async function GET() {
  try {
    const runtime = runtimeStrings();
    const now = new Date().toISOString();

    return Response.json({
      status: "healthy",
      uptime: process.uptime(),
      timestamp: now,
      environment: process.env.NODE_ENV ?? "production",
      models: capabilityCatalog.map((c) => ({
        id: c.id,
        label: c.label,
        configured: Boolean(runtime[c.modelEnv as keyof typeof runtime] ?? runtime.USTC_API),
      })),
      memory: process.memoryUsage ? {
        heapUsed: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
        heapTotal: Math.round(process.memoryUsage().heapTotal / 1024 / 1024),
        rss: Math.round(process.memoryUsage().rss / 1024 / 1024),
      } : null,
    });
  } catch (error) {
    return Response.json({
      status: "degraded",
      error: error instanceof Error ? error.message : "Unknown error",
    }, { status: 500 });
  }
}