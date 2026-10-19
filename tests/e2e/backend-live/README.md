# Real backend browser integration (synthetic fixtures)

This suite runs Chromium → the real React web app and BFF → the real FastAPI
workflow → a dedicated SQL database. Only the HTTP model provider is doubled.
Neither teaching endpoints nor their responses are mocked. Network faults discard
an **actual committed** response. Process faults kill the supervisor's owned API
process tree, including Uvicorn workers, then start it again.

Every roster, content passage, publication/review status and seeded learning phase
is a **synthetic test fixture**, not a real teacher approval or classroom result.
The hash-pinned applicability registry has `test_double: true`; the test-only API
entry point explicitly loads it. The production loader rejects that registry.
The real retriever still enforces publication, course/edition, source hashes,
energy regime, mass and width scope. A synthetic numerical answer never proves
physics mastery or teaching efficacy.

## Run

Install the repository web dependencies, the API development environment and
Playwright Chromium first. From the repository root:

```powershell
node node_modules/@playwright/test/cli.js test --config playwright.backend-live.config.ts
```

`npm run test:e2e:backend-live` is the equivalent package script. For the isolated
trial compose stack, `python scripts/with-trial-environment.py --private-env
PATH_TO_PRIVATE_ENV -- node node_modules/@playwright/test/cli.js test --config
playwright.backend-live.config.ts` injects the dedicated PostgreSQL/Redis settings
without putting credentials in command arguments or output.

The default is a **SQLite baseline**, with a real encrypted in-memory credential
vault and process-local LangGraph checkpoints. The PostgreSQL restart case is
explicitly skipped. SQLite results do not establish PostgreSQL, multiworker,
Redis or restart correctness.

To test the required durable path, provide dedicated PostgreSQL and Redis
instances and run the same suite:

```bash
export BACKEND_LIVE_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@HOST:PORT/quantum_backend_live'
export BACKEND_LIVE_REDIS_URL='redis://HOST:PORT/ISOLATED_DATABASE'
export BACKEND_LIVE_API_WORKERS=2
node node_modules/@playwright/test/cli.js test --config playwright.backend-live.config.ts
```

Use environment configuration, not committed secrets. The database name must
contain `backend_live`; SQLite paths must remain under `test-results/backend-live`.
The seeder adds a fresh uniquely named synthetic course on each launch. Use a
disposable database/Redis database; no classroom database should be used. The
public fixture Fernet key encrypts only the local synthetic provider key.
`BACKEND_LIVE_PYTHON` can select an absolute Python executable; otherwise the
suite uses `services/api/.venv`. Ports default to web 3310, API 8311, provider
8312 and can be overridden using `BACKEND_LIVE_WEB_PORT`,
`BACKEND_LIVE_API_PORT`, `BACKEND_LIVE_PROVIDER_PORT`.

The supervisor migrates the database to the current Alembic head, seeds the
synthetic records, launches the stub/API/web and waits for their real readiness.
The dedicated Vite configuration uses the actual vinext app/BFF runtime and
omits hosting-only Cloudflare/Sites development machinery. This tests browser
and service contracts; it does not claim to test a Cloudflare deployment.

For local debugging, start `node tests/e2e/backend-live/stack.mjs`, then set
`BACKEND_LIVE_WEB_URL=http://localhost:3310` before invoking Playwright. This
reuses that supervisor. Invitations are single use: restart the supervisor to
seed fresh actors before rerunning the suite. The API restart command uses
filesystem IPC under the ignored output directory, never a production route.

## Assertions and evidence

- A real first-turn response is lost after commit; the UI retry retains its
  client request ID and replays the same turn, with one SQL turn/trace.
- The browser can inspect saved request status and restore a completed turn or
  first-turn HITL pause after delivery is lost, without another submission or
  provider call. The safe status response contains identifiers/budgets, no answer.
- A teacher's recorded reason and specific probe change the next real teaching
  action. A student cannot write that decision; another student cannot read the
  conversation state, interrupt or export despite sharing the fixture model key.
- The first correlated Solo answer is immutable across tabs and revisions.
  Mismatched task IDs reveal no oracle. Solo prevents help in another conversation.
- A held real HTTP provider request races with Solo arming through the actual
  database serialization boundary; subsequent help is denied.
- A first-turn HITL pause appears in the actual staff pending queue even though
  no completed `AgentTrace` exists. Losing the committed approval response and
  retrying it does not duplicate the turn/trace.
- With PostgreSQL and Redis, the same checkpoint and authenticated identities
  survive an API process-tree restart; run with two workers to exercise a shared
  checkpoint/vault deployment.

Reports, retained failure traces/screenshots, logs, fixture metadata and SQL
snapshots are written under ignored `test-results/backend-live/`. The manifest
contains runtime invitations and a dedicated test database URL; do not publish it.
Per-test evidence attachments identify the database mode, worker count and
credential vault, and explicitly state that there are no actual classroom
results or teacher approvals. An authored/skipped test is not a passing result.
Use `collect_evidence.py --source TEST_RESULTS --destination SAFE_OUTPUT
--source-manifest SOURCE_STAGE_JSON` to collect a shareable allowlist. It excludes
private manifests, browser/network trace archives and error-context documents,
checks text for runtime credentials, and records exclusions. Private raw traces
remain available for local debugging. `stage_source.py` creates the exact source
archive and canonical SHA256 manifest used by the Linux trial; this digest is a
source snapshot identifier, not a Git commit.
Real classroom evaluation still requires the people and procedures in
`docs/implementation/CLASSROOM_EVALUATION_PROTOCOL.md`.

## Compiled production Compose smoke

The smaller five-check smoke uses the actual compiled web/API containers and
PostgreSQL/Redis, with only the internal HTTP provider fixture. It does not load
the applicability-review test registry. It covers login, first-turn replay/status,
identity isolation, a teacher follow-up, pending-review UI/replay and export.
The eight-case suite above separately covers Solo and API process crashes.

Use a newly provisioned, disposable trial stack and private environment from
`scripts/provision-trial-secrets.py`; never point this at a classroom database.
After installing Python/web dependencies and Chromium:

```bash
export BUILD_REVISION="$(git rev-parse HEAD)"
docker compose -p qa-classroom-trial -f compose.yaml -f compose.registry.yaml \
  -f compose.trial.yaml -f compose.trial-provider.yaml \
  --env-file /PRIVATE/qa-trial/private.env up --build -d --wait
umask 077
mkdir -p /PRIVATE/qa-trial/production-smoke
PYTHONPATH=services/api python scripts/with-trial-environment.py \
  --private-env /PRIVATE/qa-trial/private.env -- \
  python tests/e2e/backend-live/seed.py seed \
  --manifest /PRIVATE/qa-trial/production-smoke/manifest.json
node tests/e2e/backend-live/production_smoke.mjs \
  --manifest /PRIVATE/qa-trial/production-smoke/manifest.json \
  --output outputs/production-smoke --base-url http://127.0.0.1:3000
```

Run the seeder again for a fresh roster before each retry: invitations are single
use. Preserve the prior output separately. The provider override disables external
embeddings and uses `synthetic-production-smoke-provider`; remove that override
before configuring actual teaching. Synthetic publication statuses are test setup,
not actual source-applicability approvals. Raw private manifests contain DSNs and
invitations and must stay out of shared evidence. The smoke's generic possible
unknown-version note must be checked against actual persisted turn provenance;
setting an environment variable alone does not prove that recorded version.
