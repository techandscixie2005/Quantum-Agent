import { runtimeStrings } from "./runtime-env";

const forbidden = [/\b(socket|requests|urllib|subprocess|os\.system|eval|exec|open\s*\(|__import__)\b/i, /https?:\/\//i];

export type SandboxRequest = { code: string; timeoutMs?: number; files?: Array<{ name: string; content: string }> };

export function inspectSandboxCode(code: string) {
  if (!code.trim()) return { safe: false, reason: "代码为空" };
  if (code.length > 30000) return { safe: false, reason: "代码超过 30,000 字符限制" };
  const hit = forbidden.find((pattern) => pattern.test(code));
  if (hit) return { safe: false, reason: "检测到网络、文件系统或动态执行相关操作" };
  return { safe: true, reason: "静态安全检查通过" };
}

export async function executeInSandbox(payload: SandboxRequest) {
  const inspection = inspectSandboxCode(payload.code);
  if (!inspection.safe) return { status: "rejected", inspection, stdout: "", stderr: inspection.reason, tests: [] };
  const runtime = runtimeStrings();
  if (!runtime.SANDBOX_BASE_URL || !runtime.SANDBOX_API_KEY) {
    return { status: "unavailable", inspection, stdout: "", stderr: "尚未配置隔离 Python 执行服务。代码和 API Key 均未发送到外部。", tests: [], setup: "Set SANDBOX_BASE_URL and SANDBOX_API_KEY on the server." };
  }
  const response = await fetch(`${runtime.SANDBOX_BASE_URL.replace(/\/$/, "")}/execute`, {
    method: "POST",
    signal: AbortSignal.timeout(Math.min(Math.max(payload.timeoutMs ?? 15000, 1000), 30000)),
    headers: { Authorization: `Bearer ${runtime.SANDBOX_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ language: "python", code: payload.code, files: payload.files ?? [], network: false, timeout_ms: Math.min(payload.timeoutMs ?? 15000, 30000), memory_mb: 256 }),
  });
  if (!response.ok) return { status: "failed", inspection, stdout: "", stderr: `Sandbox HTTP ${response.status}`, tests: [] };
  return { status: "completed", inspection, ...(await response.json() as Record<string, unknown>) };
}

