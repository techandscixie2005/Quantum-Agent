/** Real web/BFF + FastAPI + dedicated DB; only the HTTP model provider is doubled. */
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const apiRoot = path.join(root, "services/api");
const here = path.join(root, "tests/e2e/backend-live");
const output = path.join(root, "test-results/backend-live");
mkdirSync(output, { recursive: true });
const python = process.env.BACKEND_LIVE_PYTHON ?? path.join(apiRoot,
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const apiPort = process.env.BACKEND_LIVE_API_PORT ?? "8311";
const providerPort = process.env.BACKEND_LIVE_PROVIDER_PORT ?? "8312";
const webPort = process.env.BACKEND_LIVE_WEB_PORT ?? "3310";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const providerUrl = `http://127.0.0.1:${providerPort}`;
const webUrl = `http://localhost:${webPort}`;
const databaseUrl = process.env.BACKEND_LIVE_DATABASE_URL ??
  `sqlite+aiosqlite:///${path.join(output, "baseline.sqlite3").replaceAll("\\", "/")}`;
const workers = Number(process.env.BACKEND_LIVE_API_WORKERS ?? "1");
if (!databaseUrl.startsWith("sqlite") && !new URL(databaseUrl).pathname.includes("backend_live")) {
  throw new Error("Use a dedicated database whose name contains backend_live.");
}
if (databaseUrl.startsWith("sqlite") && workers > 1) throw new Error("Multiworker tests require PostgreSQL.");
const env = { ...process.env,
  ENVIRONMENT: "test", DATABASE_URL: databaseUrl, EMBEDDING_PROVIDER: "disabled",
  USTC_BASE_URL: `${providerUrl}/v1`, USTC_API: "backend-live-provider-fixture-key",
  USTC_TEXT_MODEL_OVERRIDE: "backend-live-fixture", ALLOW_SHARED_DEMO_LOGIN: "false",
  CODING_SANDBOX_ENABLED: "false", QUANTUM_API_BASE_URL: apiUrl,
  PYTHONPATH: [apiRoot, here].join(path.delimiter), PYTHONUTF8: "1",
};
for (const key of ["NEO4J_PASSWORD", "REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD", "SESSION_VAULT_KEY", "SESSION_SECRET",
  "QUANTUM_AGENT_BARRIER_REVIEWS", "QUANTUM_AGENT_BARRIER_REVIEWS_SHA256",
  "EMBEDDING_API_KEY", "EMBEDDING_BASE_URL"]) delete env[key];
// Public test-only key: synthetic provider credentials, never classroom secrets.
env.SESSION_VAULT_KEY = Buffer.from(Array.from({ length: 32 }, (_, i) => i)).toString("base64");
if (process.env.BACKEND_LIVE_REDIS_URL) {
  env.REDIS_URL = process.env.BACKEND_LIVE_REDIS_URL;
}

function run(command, args, cwd = apiRoot) {
  const result = spawnSync(command, args, { cwd, env, encoding: "utf8", windowsHide: true });
  if (result.status !== 0) throw new Error(`${path.basename(command)} failed: ${result.stderr || result.stdout}`);
  return result.stdout;
}

let stopping = false;
const children = new Set();
function start(name, command, args, cwd = apiRoot) {
  const child = spawn(command, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true, detached: process.platform !== "win32" });
  children.add(child);
  for (const stream of [child.stdout, child.stderr]) stream.on("data", data =>
    appendFileSync(path.join(output, `${name}.log`), data));
  child.on("exit", code => {
    children.delete(child);
    if (!stopping && code !== null && code !== 0 && !child.expectedStop) {
      console.error(`${name} exited (${code}); inspect test-results/backend-live/${name}.log`);
    }
  });
  child.on("error", error => console.error(`${name} could not start: ${error.message}`));
  return child;
}

async function waitFor(url, milliseconds = 120000) {
  const until = Date.now() + milliseconds;
  while (Date.now() < until) {
    try { if ((await fetch(url, { signal: AbortSignal.timeout(2000) })).ok) return; }
    catch { /* bounded startup polling */ }
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Service did not become ready: ${url}; inspect fixture logs.`);
}

async function stop(child) {
  if (!child || child.exitCode !== null) return;
  child.expectedStop = true;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true });
  } else {
    try { process.kill(-child.pid, "SIGKILL"); } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
  await new Promise(resolve => child.once("exit", resolve));
}

let api;
let apiStarts = 0;
async function launchApi() {
  api = start("api", python, ["-m", "uvicorn", "api_app:app", "--app-dir", here,
    "--host", "127.0.0.1", "--port", apiPort, "--workers", String(workers)]);
  apiStarts++;
  await waitFor(`${apiUrl}/health/live`);
  // A worker may report healthy while a sibling fails startup. Do not launch
  // the browser against a parent process that is already shutting them down.
  for (let check = 0; check < 6; check++) {
    await new Promise(resolve => setTimeout(resolve, 300));
    if (api.exitCode !== null) throw new Error("API worker startup failed; inspect api.log");
    await waitFor(`${apiUrl}/health/ready`, 5000);
  }
}

try {
  run(python, ["-m", "alembic", "upgrade", "head"]);
  run(python, [path.join(here, "seed.py"), "seed", "--manifest", path.join(output, "manifest.json")]);
  const manifest = JSON.parse(readFileSync(path.join(output, "manifest.json"), "utf8"));
  const reviews = JSON.stringify({ schema_version: 1, test_double: true, reviews: manifest.source_reviews });
  env.BACKEND_LIVE_SOURCE_REVIEWS = path.join(output, "source-reviews.json");
  env.BACKEND_LIVE_SOURCE_REVIEWS_SHA256 = createHash("sha256").update(reviews).digest("hex");
  writeFileSync(env.BACKEND_LIVE_SOURCE_REVIEWS, reviews);
  Object.assign(manifest, { api_url: apiUrl, provider_url: providerUrl, web_url: webUrl,
    python, api_workers: workers, credential_vault: env.REDIS_URL ? "shared_redis" : "in_memory_fixture" });
  writeFileSync(path.join(output, "manifest.json"), JSON.stringify(manifest));
  start("provider", python, [path.join(here, "provider_stub.py"), "--port", providerPort]);
  await waitFor(`${providerUrl}/health`);
  await launchApi();
  start("web", process.execPath, [path.join(root, "node_modules/vite/bin/vite.js"),
    "--config", path.join(here, "vite.config.ts"),
    "--host", "127.0.0.1", "--port", webPort, "--strictPort"], root);
  await waitFor(`${webUrl}/agent`);
  writeFileSync(path.join(output, "ready.json"), JSON.stringify({ ready: true, fixture: true, apiStarts }));
  console.log(`Synthetic backend/browser integration stack ready (${manifest.database_mode}, ${workers} API worker(s)).`);
  // Ignore an earlier run's IPC file; only commands submitted after readiness count.
  let lastCommand = "";
  try { lastCommand = JSON.parse(readFileSync(path.join(output, "control-request.json"), "utf8")).nonce ?? ""; }
  catch { /* no previous fixture command */ }
  let processing = false;
  const timer = setInterval(async () => {
    const commandPath = path.join(output, "control-request.json");
    if (processing || !existsSync(commandPath)) return;
    let command;
    try { command = JSON.parse(readFileSync(commandPath, "utf8")); } catch { return; }
    if (!command.nonce || command.nonce === lastCommand) return;
    lastCommand = command.nonce;
    processing = true;
    try {
      if (command.action !== "restart_api") throw new Error("Unknown fixture supervisor action");
      await stop(api);
      await launchApi();
      writeFileSync(path.join(output, "control-response.json"), JSON.stringify({
        nonce: command.nonce, ok: true, apiStarts,
      }));
    } catch (error) {
      writeFileSync(path.join(output, "control-response.json"), JSON.stringify({
        nonce: command.nonce, ok: false, message: String(error),
      }));
    } finally { processing = false; }
  }, 100);
  const finish = async () => {
    stopping = true;
    clearInterval(timer);
    await Promise.all([...children].map(stop));
    process.exit(0);
  };
  process.on("SIGTERM", finish);
  process.on("SIGINT", finish);
  await new Promise(() => {});
} catch (error) {
  stopping = true;
  await Promise.all([...children].map(stop));
  console.error(String(error));
  process.exit(1);
}
