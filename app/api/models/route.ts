import { publicCapabilities } from "../../../lib/providers";
import { runtimeStrings } from "../../../lib/runtime-env";

export async function GET() {
  const runtime = runtimeStrings();
  return Response.json({ deprecated: true, message: "Use /api/capabilities. Provider and model identities are server-only.", capabilities: publicCapabilities(runtime) });
}
