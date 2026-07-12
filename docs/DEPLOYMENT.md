# Deployment

Quantum Agent deploys as a Cloudflare Worker with D1 persistence.

## Architecture

```
GitHub (private) → GitHub Actions CI → vinext deploy → Cloudflare Worker
                                                       + Cloudflare D1
```

The Worker serves both static frontend assets and API routes from a single origin.

## Prerequisites

1. A Cloudflare account with Workers and D1 enabled
2. `wrangler` authenticated (`npx wrangler login`)
3. An existing D1 database bound as `DB` in the Worker
4. `USTC_API` API key for the USTC model gateway

## Secrets

### `USTC_API`

The USTC model gateway API key. Set directly as a Cloudflare Worker secret:

```bash
npx wrangler secret put USTC_API
```

Never commit this value or include it in `.env` files.

### `TEACHER_PASSWORD`

Password for the teacher dashboard access. Set as a Worker secret:

```bash
npx wrangler secret put TEACHER_PASSWORD
```

### Optional: `SESSION_SECRET`

Separate key for HMAC-signing teacher session cookies. Falls back to `TEACHER_PASSWORD` if unset.

### Non-secret environment variables

These are set in the Worker configuration, not as secrets:

- `USTC_BASE_URL` — defaults to `https://api.llm.ustc.edu.cn`
- `USTC_MODEL_QUICK` / `USTC_MODEL_DEEP` / `USTC_MODEL_VISION` / `USTC_MODEL_VISION_REASONER` / `USTC_MODEL_CODE` — per-capability model overrides
- `MODEL_ROUTES_JSON` — optional JSON to override entire route configurations
- `MODEL_TIMEOUT_MS` — API timeout in milliseconds (default 60000)
- `SANDBOX_BASE_URL` / `SANDBOX_API_KEY` — optional external Python sandbox

## Database

The D1 database must have the binding name `DB`. Apply the migration:

```bash
npx wrangler d1 execute <DATABASE_NAME> --file=drizzle/0000_happy_leper_queen.sql
```

Or use Drizzle Kit:

```bash
npx drizzle-kit push
```

## Deploy

### Option 1: vinext deploy (for OpenAI "sites" projects)

```bash
npx vinext deploy
```

The `.openai/hosting.json` contains the project ID (`appgprj_6a527eaf9b2c8191bdd429316fe79298`)
and D1 binding name (`DB`). `vinext deploy` reads this and deploys the Worker.

### Option 2: Manual wrangler deploy

Create a `wrangler.jsonc`:

```jsonc
{
  "name": "quantum-agent",
  "main": "worker/index.ts",
  "compatibility_flags": ["nodejs_compat"],
  "d1_databases": [
    { "binding": "DB", "database_name": "quantum-agent-d1", "database_id": "<YOUR_D1_ID>" }
  ],
  "compatibility_date": "2025-12-01"
}
```

Then:

```bash
npx wrangler deploy
```

## Post-deploy verification

1. `curl https://<your-worker>/api/health` → `{"status":"ok",...}`
2. `curl https://<your-worker>/api/ready` → `{"status":"ready","database":"connected",...}`
3. Open the frontend, send a fast concept question, verify a courseware citation appears in the right panel.
4. Verify `/api/capabilities` returns Chinese labels only, no model names.
5. Verify the built frontend bundle contains no `deepseek`, `qwen`, `glm`, `api.llm.ustc.edu.cn`, or `sk-` patterns.

## Smoke test script

```bash
# Health
curl -s https://<worker>/api/health | jq .status
# Capabilities (no model names exposed)
curl -s https://<worker>/api/capabilities | jq '.capabilities[].label'
# Tutor (deterministic fallback — works without USTC_API)
curl -s -X POST https://<worker>/api/tutor \
  -H 'Content-Type: application/json' \
  -d '{"mode":"concept","capability":"quick","message":"Franck-Condon原理是什么？"}' | jq .citations
# Teacher analytics (unauthorized without cookie)
curl -s https://<worker>/api/teacher/analytics | jq .error
# Ready
curl -s https://<worker>/api/ready | jq .status
```

## CI/CD

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR: install, typecheck, test, lint, build. Deployment from `main` requires Cloudflare credentials as GitHub repository secrets.

## Honest note

This deployment has not been verified against a live Cloudflare Worker in the current environment because `CF_API_TOKEN` and `CF_ACCOUNT_ID` are not configured. The build, tests, and local smoke verification are complete. Deploy is one `npx vinext deploy` away after setting the required credentials and secrets.