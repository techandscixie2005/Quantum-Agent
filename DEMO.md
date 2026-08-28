# DEMO — Competition Judge & Student Entry Guide

**Audience:** USTC "107 Cup" Agent Track judges and first-time evaluators.

This document describes the tested, reproducible path to enter the Quantum
Agent `/agent` workspace. No manual SQL, no manual cookie injection — the
path below is a real HTTP login exchange against the USTC model service.

---

## Prerequisites

The Compose stack must be running (API + web + PostgreSQL + Neo4j + Redis)
and the course corpus must be ingested. The competition host runs this once:

```bash
make bootstrap        # up + migrate + ingest the real course manifest
make demo-bootstrap   # seed the competition login student account
```

`make demo-bootstrap` runs `quantum-agent seed-login-account` (alias
`seed-demo-account`) inside the API container. It creates (or re-activates)
the login student `demo-student@quantum-agent.local` with an active
membership in the first published course edition. It does **not** issue a
session token — the login endpoint mints one on demand.

The API container must also have `SESSION_VAULT_KEY` set to a Fernet key
used to encrypt user-supplied API keys at rest. Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set it in the API service's environment (`.env` or `compose.yaml`):

```bash
SESSION_VAULT_KEY=<fernet key>
```

When `SESSION_VAULT_KEY` is unset, the vault falls back to `SESSION_SECRET`,
and when neither is set the vault is disabled and the startup `USTC_API` env
key is used for all sessions (dev/deploy fallback per PRD §3.3).

Each judge or student also needs their own 词元计划/一〇七杯 API key from the
USTC model service (`https://api.llm.ustc.edu.cn/v1/chat/completions`).

---

## Entry procedure

1. Open `https://<competition-host>/` in a browser.
2. The landing page redirects to `/agent`. Without a session, the agent BFF
   returns `AUTH_REQUIRED`. The page shows the login card: "连接中国科大 /
   词元计划 · 一〇七杯 / [API Key input] / [连接并进入学习空间]".
3. Enter your API key. The browser POSTs `/api/auth/login` with the key;
   the BFF proxies to the authoritative Python `POST /api/v1/auth/login`,
   which probes the USTC model service to validate the key, mints a
   short-lived (8-hour) opaque session token, stores the Fernet-encrypted
   key in the session vault keyed by `session_id`, and returns the token.
   The BFF sets the `qa_session` HttpOnly cookie on the response.
4. The page reloads `/agent` with the cookie. The header shows
   "● 模型服务已连接". The agent BFF exchanges the cookie for the course
   context and the Learning Workspace renders.

You are now in the product as the login student. The full Learning-Native
loop — commitment gate, teach-back, transfer, Solo Mode, Cognitive Mirror,
the real rectangular-barrier tunnelling Golden Loop, and the Coding Agent —
is reachable. All agent calls use your session's API key through the central
`ModelGateway`.

---

## Why this is real, not a mock

- The `qa_session` cookie is an opaque bearer token hash-checked against the
  PostgreSQL `user_sessions` table by every authenticated API route
  (`quantum_agent.auth.bearer_credential` + `_active_actor_query`).
- The login endpoint is fail-closed: it returns 401 when the USTC model
  service rejects the key, 429 on rate-limit, and 500 when the vault is
  unavailable in production.
- The API key is encrypted at rest with Fernet; only the ciphertext is
  stored in the vault (Redis in production, in-memory in dev). The plaintext
  key never enters PostgreSQL, logs, agent traces, or the response body.
- The BFF route is rate-limited (`checkRateLimit`, 10 attempts / 5 min / IP)
  and never logs or echoes the key.
- The `ModelGateway` resolves the per-session credential from the vault at
  request time (LRU-cached by key digest); the startup `USTC_API` env key is
  the dev/deploy fallback.
- The session expires after 8 hours and is scoped to the login student's
  active course membership. Logout revokes the session and forgets the
  vault entry.

---

## Programmatic entry (for automated evaluation)

If a judge prefers a scripted entry (e.g. for Playwright), the same HTTP
exchange works:

```bash
curl -fsS -X POST https://<competition-host>/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"api_key":"<your USTC API key>"}' \
  -c cookies.txt
# cookies.txt now contains qa_session; use it for /agent and /api/teaching/*
curl -fsS -b cookies.txt https://<competition-host>/agent
```

The `tests/e2e/live/golden-loop-live.spec.ts` test uses a related
`seed-live-e2e` flow (separate ephemeral credentials) for the live Golden
Loop; the login flow above is the judge/student-facing entry path.

---

## Operational notes for the host

- Rotate `SESSION_VAULT_KEY` between competition days (re-encrypts the vault;
  existing sessions must re-login).
- `make demo-bootstrap` is idempotent — re-running it re-activates the login
  account and its membership without creating duplicates.
- The login endpoint is tagged `auth` in the FastAPI OpenAPI schema
  (`/api/docs` in non-production) for inspection.
- If the login account has no active course membership, the endpoint returns
  409 with a message pointing to `make demo-bootstrap`.
- Set `CODING_SANDBOX_ENABLED=false` to disable the Coding Agent sandbox
  (the agent then degrades to `INCONCLUSIVE` rather than executing code).
