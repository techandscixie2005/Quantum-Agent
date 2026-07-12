import { executeInSandbox } from "../../../lib/sandbox";

export async function POST(request: Request) {
  try {
    const body = await request.json() as { code?: string; timeoutMs?: number; files?: Array<{ name: string; content: string }> };
    if (typeof body.code !== "string") return Response.json({ error: "code is required" }, { status: 400 });
    const result = await executeInSandbox({ code: body.code, timeoutMs: body.timeoutMs, files: body.files });
    return Response.json(result, { status: result.status === "rejected" ? 400 : result.status === "unavailable" ? 503 : 200 });
  } catch (error) { return Response.json({ error: "Sandbox request failed", detail: error instanceof Error ? error.message : "Unknown error" }, { status: 500 }); }
}

