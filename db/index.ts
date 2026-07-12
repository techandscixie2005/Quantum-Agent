import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";
import { runtimeBindings } from "../lib/runtime-env";

export function getDb() {
  const d1 = runtimeBindings().DB;
  if (!d1) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB` or let your control plane inject the real binding values before using the database."
    );
  }

  return drizzle(d1, { schema });
}
