import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vinext from "vinext";

// Real Vinext/React/BFF routes, using its supported local Node runtime.
// Hosting-only Cloudflare/Sites packaging is checked separately by build tests.
export default defineConfig({
  root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../.."),
  plugins: [vinext()],
  server: { allowedHosts: ["localhost"], watch: { ignored: ["**/outputs/**", "**/.venv/**"] } },
});
