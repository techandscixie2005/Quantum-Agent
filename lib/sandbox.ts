// Deterministic static preflight for student-submitted Python code.
//
// PRD V3.0 P1-3: the unauthenticated /api/sandbox route that exposed
// ``executeInSandbox`` (a stateful external execution relay) has been
// removed from the production build.  The authoritative Python backend
// exposes a fail-closed code-test verifier (science/toolbox.py) that does
// not execute student code on the API host.  This module keeps only the
// deterministic ``inspectSandboxCode`` preflight, which is a pure function
// with no network, no secrets, and no side effects; it is retained for
// client-side validation and unit tests.

const forbidden = [/\b(socket|requests|urllib|subprocess|os\.system|eval|exec|open\s*\(|__import__)\b/i, /https?:\/\//i];

export function inspectSandboxCode(code: string) {
  if (!code.trim()) return { safe: false, reason: "代码为空" };
  if (code.length > 30000) return { safe: false, reason: "代码超过 30,000 字符限制" };
  const hit = forbidden.find((pattern) => pattern.test(code));
  if (hit) return { safe: false, reason: "检测到网络、文件系统或动态执行相关操作" };
  return { safe: true, reason: "静态安全检查通过" };
}
