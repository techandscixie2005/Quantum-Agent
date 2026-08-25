import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type RuntimeBindings = Record<string, unknown> & { DB?: D1Database };

declare global {
  var __QUANTUM_AGENT_RUNTIME__: RuntimeBindings | undefined;
}

export function setRuntimeBindings(bindings: RuntimeBindings) {
  globalThis.__QUANTUM_AGENT_RUNTIME__ = bindings;
}

function loadDevVars(): Record<string, string | undefined> {
  try {
    const devVarsPath = resolve(process.cwd(), ".dev.vars");
    const content = readFileSync(devVarsPath, "utf-8");
    const vars: Record<string, string | undefined> = {};
    for (const line of content.split("\n")) {
      const eqIdx = line.indexOf("=");
      if (eqIdx > 0 && !line.trimStart().startsWith("#")) {
        const key = line.slice(0, eqIdx).trim();
        const value = line.slice(eqIdx + 1).trim();
        if (key) vars[key] = value || undefined;
      }
    }
    return vars;
  } catch {
    return {};
  }
}

export function runtimeBindings(): RuntimeBindings {
  if (globalThis.__QUANTUM_AGENT_RUNTIME__) return globalThis.__QUANTUM_AGENT_RUNTIME__;
  if (typeof process !== "undefined" && process.env) return process.env as RuntimeBindings;
  return {};
}

export function runtimeStrings(): Record<string, string | undefined> {
  const bindings = runtimeBindings();
  // In local dev, .dev.vars values override process.env
  const devVars = typeof process !== "undefined" && process.env.NODE_ENV !== "production"
    ? loadDevVars()
    : {};

  return new Proxy({} as Record<string, string | undefined>, {
    get: (_target, property: string) => {
      const key = String(property);
      // Check .dev.vars first (dev mode), then bindings
      if (key in devVars && devVars[key]) return devVars[key];
      return typeof bindings[key] === "string" ? bindings[key] as string : undefined;
    },
  });
}