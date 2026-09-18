/** Read-only readiness. Never prints runtime configuration or response bodies. */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const reports = [];
try {
  const { stdout } = await promisify(execFile)('docker', ['info', '--format', '{{.ServerVersion}}'], { timeout: 8000 });
  reports.push({ service: 'docker', ok: true, version: stdout.trim() });
} catch {
  reports.push({ service: 'docker', ok: false, reason: 'daemon unavailable within 8 seconds' });
}
for (const [service, url] of [
  ['api', new URL('/health/ready', process.env.QUANTUM_API_BASE_URL ?? 'http://127.0.0.1:8000')],
  ['web', new URL('/agent', process.env.BASE_URL ?? 'http://127.0.0.1:3000')],
]) {
  const start = performance.now();
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(8000), redirect: 'error' });
    reports.push({ service, ok: response.ok, status: response.status, milliseconds: performance.now() - start });
    await response.body?.cancel();
  } catch {
    reports.push({ service, ok: false, reason: 'unreachable or timed out', milliseconds: performance.now() - start });
  }
}
console.log(JSON.stringify({ checkedAt: new Date().toISOString(), reports }, null, 2));
if (reports.some(report => !report.ok)) process.exitCode = 1;
