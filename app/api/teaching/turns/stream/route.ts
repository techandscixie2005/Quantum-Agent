import { proxyTeachingTurn } from "@/app/api/teaching/_shared";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return proxyTeachingTurn(request);
}

