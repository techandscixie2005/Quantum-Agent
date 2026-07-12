export type RuntimeBindings = Record<string, unknown> & { DB?: D1Database };

declare global {
  var __QUANTUM_AGENT_RUNTIME__: RuntimeBindings | undefined;
}

export function setRuntimeBindings(bindings: RuntimeBindings) {
  globalThis.__QUANTUM_AGENT_RUNTIME__ = bindings;
}

export function runtimeBindings(): RuntimeBindings {
  if (globalThis.__QUANTUM_AGENT_RUNTIME__) return globalThis.__QUANTUM_AGENT_RUNTIME__;
  if (typeof process !== "undefined" && process.env) return process.env as RuntimeBindings;
  return {};
}

export function runtimeStrings(): Record<string, string | undefined> {
  const bindings = runtimeBindings();
  return new Proxy({} as Record<string, string | undefined>, {
    get: (_target, property: string) => typeof bindings[property] === "string" ? bindings[property] as string : undefined,
  });
}

