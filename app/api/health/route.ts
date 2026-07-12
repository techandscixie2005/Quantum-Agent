import { publicCapabilities } from "../../../lib/providers";
import { runtimeStrings } from "../../../lib/runtime-env";

export async function GET() {
  const runtime = runtimeStrings();
  return Response.json({ status: "ok", service: "quantum-agent", version: "0.5.0", time: new Date().toISOString(), capabilities: publicCapabilities(runtime).map(({ id, configured }) => ({ id, configured })) });
}
