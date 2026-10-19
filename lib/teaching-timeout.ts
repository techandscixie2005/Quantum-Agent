/** Server-only timing configuration shared by teaching BFF routes. */
export function teachingProxyTimeoutMs(
  env: Readonly<Record<string, string | undefined>> = process.env,
): number {
  const active = Number(env.TEACHING_EXECUTION_SECONDS ?? "180");
  const proxy = Number(env.TEACHING_PROXY_TIMEOUT_SECONDS ?? String(active + 30));
  if (!Number.isFinite(active) || active <= 0 || active > 600 ||
      !Number.isFinite(proxy) || proxy < active + 15 || proxy > 660) {
    throw new Error("Invalid teaching timeout configuration");
  }
  return Math.ceil(proxy * 1_000);
}
