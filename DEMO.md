# DEMO — Competition Judge Entry Guide

**Audience:** USTC "107 Cup" Agent Track judges and first-time evaluators.

This document describes the tested, reproducible path to enter the Quantum
Agent `/agent` workspace as a student. No manual SQL, no manual cookie
injection — the path below is a real HTTP login exchange.

---

## Prerequisites

The Compose stack must be running (API + web + PostgreSQL + Neo4j + Redis)
and the course corpus must be ingested. The competition host runs this once:

```bash
make bootstrap        # up + migrate + ingest the real course manifest
make demo-bootstrap   # seed the competition demo student account
```

`make demo-bootstrap` runs `quantum-agent seed-demo-account` inside the API
container. It creates (or re-activates) the demo student
`demo-student@quantum-agent.local` with an active membership in the first
published course edition. It does **not** issue a session token — the
demo-login endpoint mints one on demand.

The API container must also have `DEMO_LOGIN_SECRET` set to a shared secret
the judge will type into the login form. The host sets it in the API
service's environment (`.env` or `compose.yaml`):

```bash
DEMO_LOGIN_SECRET=<a shared secret at least 8 characters long>
```

The secret is read only server-side; it never reaches the browser bundle
(verified by `npm run check:secrets`).

---

## Judge entry procedure

1. Open `https://<competition-host>/` in a browser.
2. The landing page redirects to `/agent`. Without a session, the agent BFF
   returns `AUTH_REQUIRED`. The page shows a login card.
3. Enter the `DEMO_LOGIN_SECRET` the competition host shared with you.
4. The browser POSTs `/api/auth/demo-login` with the secret; the BFF proxies
   to the authoritative Python `POST /api/v1/auth/demo-login`, which mints
   a short-lived (8-hour) opaque session token and returns it. The BFF sets
   the `qa_session` HttpOnly cookie on the response.
5. The page reloads `/agent` with the cookie. The agent BFF exchanges the
   cookie for the course context and the Learning Workspace renders.

You are now in the product as the demo student. The full Learning-Native
loop — commitment gate, teach-back, transfer, Solo Mode, Cognitive Mirror,
and the real rectangular-barrier tunnelling Golden Loop — is reachable.

---

## Why this is real, not a mock

- The `qa_session` cookie is an opaque bearer token hash-checked against the
  PostgreSQL `user_sessions` table by every authenticated API route
  (`quantum_agent.auth.bearer_credential` + `_active_actor_query`).
- The demo-login endpoint is fail-closed: it returns 404 when
  `DEMO_LOGIN_SECRET` is unset and 401 on a wrong secret, and it refuses to
  run in `production` environment.
- The BFF route is rate-limited (`checkRateLimit`) and never logs the
  secret.
- The session expires after 8 hours and is scoped to the demo student's
  active course membership.

---

## Programmatic entry (for automated evaluation)

If a judge prefers a scripted entry (e.g. for Playwright), the same HTTP
exchange works:

```bash
curl -fsS -X POST https://<competition-host>/api/auth/demo-login \
  -H 'Content-Type: application/json' \
  -d '{"secret":"<DEMO_LOGIN_SECRET>"}' \
  -c cookies.txt
# cookies.txt now contains qa_session; use it for /agent and /api/teaching/*
curl -fsS -b cookies.txt https://<competition-host>/agent
```

The `tests/e2e/live/golden-loop-live.spec.ts` test uses a related
`seed-live-e2e` flow (separate ephemeral credentials) for the live Golden
Loop; the demo-login flow above is the judge-facing entry path.

---

## Operational notes for the host

- Rotate `DEMO_LOGIN_SECRET` between competition days.
- `make demo-bootstrap` is idempotent — re-running it re-activates the demo
  account and its membership without creating duplicates.
- The demo-login endpoint is tagged `auth` in the FastAPI OpenAPI schema
  (`/api/docs` in non-production) for inspection.
- If the demo account has no active course membership, the endpoint returns
  409 with a message pointing to `make demo-bootstrap`.
