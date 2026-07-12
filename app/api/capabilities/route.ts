import { publicCapabilities } from "../../../lib/providers";
import { runtimeStrings } from "../../../lib/runtime-env";

export async function GET() {
  return Response.json({ capabilities: publicCapabilities(runtimeStrings()), routing: "server-controlled" });
}
