# Operations Runbook

## Runtime authority

Quantum Agent V2.1 is a Compose deployment with:

- FastAPI, LangGraph, SQLAlchemy, and Alembic in `services/api/quantum_agent/`;
- PostgreSQL with pgvector as the durable system of record and LangGraph checkpoint store;
- Neo4j as a rebuildable, approved-only knowledge-graph projection;
- authenticated Redis infrastructure;
- Next.js as the student and teaching-staff web boundary.

The production student experience is `/agent`. The course-scoped staff trace and HITL workspace is
`/teacher/traces?course_id=<uuid>&curriculum_edition_id=<uuid>`. The older TypeScript teaching
runtime is not authoritative for either route.

## Configure secrets

Create a private Compose environment file:

```bash
cp .env.example .env
chmod 0600 .env
```

Set unique values for `POSTGRES_PASSWORD`, its exact percent-encoded counterpart
`POSTGRES_PASSWORD_URLENCODED`, `NEO4J_PASSWORD`, `REDIS_PASSWORD`, and `USTC_API`. Never commit
`.env`; it is ignored by Git. `USTC_API` and `EMBEDDING_API_KEY` are backend-only bearer secrets.
They must not use `NEXT_PUBLIC_*`, enter browser logs, appear in API responses, or be included in
screenshots.

Compose maps `API_ENVIRONMENT` to the Python `ENVIRONMENT` setting and constructs the container
`DATABASE_URL` from the PostgreSQL values. The standalone Python settings `ENVIRONMENT` and
`DATABASE_URL` in `.env.example` are for a directly launched backend. The web server uses only
`QUANTUM_API_BASE_URL` to reach FastAPI; Compose sets it to `http://api:8000` inside the web
container.

Validate prerequisites and interpolation without printing values:

```bash
make doctor
make compose-config
```

`make require-secrets` is an implicit prerequisite of stack-start, migration, ingestion, and live
test commands. Do not use `docker compose config` output in public logs because rendered
environment values may contain secrets; `make compose-config` uses quiet validation.

## Build, start, and migrate

```bash
make build
make migrate
make up
make ps
```

`make up` starts PostgreSQL, Neo4j, Redis, the one-shot Alembic migration, FastAPI, and Next.js. It
waits on dependency health conditions. Services bind to loopback by default (`127.0.0.1:8000` and
`127.0.0.1:3000`); place an authenticated TLS reverse proxy in front for remote access.
`make migrate` is the explicit one-shot option; `make up` already runs the same migration service.

Migration `0004` adds the student multimodal persistence boundary:

- `user_attachments` for actor/course/edition-scoped upload metadata and storage keys;
- `multimodal_extractions` for structured evidence, confidence, ambiguity, and confirmation state;
- `document_parse_runs` for parser choice, fallback chain, provenance, and terminal status.

Confirm the applied revision and health from inside the private topology:

```bash
docker compose -f compose.yaml exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version;"'
curl --fail --silent http://127.0.0.1:8000/health/live
curl --fail --silent http://127.0.0.1:8000/health/ready
```

The revision query must report `0004`. Liveness confirms the API process. Readiness performs a real
PostgreSQL query and returns HTTP 503 when PostgreSQL is unavailable. Neo4j and Redis have
independent Compose health checks and are also exercised by `make test-live-infra`.

## Course content and graph projection

Use only the checksum-verified manifest and teacher governance flow:

```bash
make bootstrap
make graph-sync
make graph-worker
make graph-worker-stop
```

`make bootstrap` starts the stack and ingests `content/quantum_course/manifest.toml`. Ingestion does
not make OCR/model output authoritative. Publication and grounded evidence still require the
backend review policy. `graph-sync` drains a bounded approved outbox batch; `graph-worker` keeps the
rebuildable Neo4j projection current.

## Attachment storage and document intelligence

Compose stores validated upload bytes in the backend-only `attachment_data` volume mounted at
`/var/lib/quantum-agent/attachments`. PostgreSQL stores the owner/course/edition scope, SHA-256,
status, extraction contract, confirmation, parse run, and provenance. Storage keys are generated
below the configured root; filenames cannot select a path. Deleting an attachment removes its bytes
and marks the durable record deleted.

The default limits are 25 MiB per upload, 40 million image pixels, 16,384 pixels per image
dimension, 500 document pages/slides, 5,000 archive members, 250 MiB expanded archive data, and a
100:1 maximum archive compression ratio. Configure them only through the exact
`ATTACHMENT_MAX_*` names in `.env.example`; `ATTACHMENT_MAX_ARCHIVE_UNCOMPRESSED_BYTES` must be at
least `ATTACHMENT_MAX_BYTES`.

Native PDF/PPTX/DOCX/TXT/Markdown extraction is live. Image perception uses the configured vision
gateway, preserves uncertain OCR, and requires explicit confirmation when needed. Scanned PDF can
fall back to vision OCR. MinerU and unlimited-OCR remain unavailable until an explicitly probed
file-parser transport is injected; the public USTC API documentation does not publish such a
transport contract. Legacy DOC/PPT similarly requires an isolated converter and is rejected by the
default runtime. See [Model Routing](MODEL_ROUTING.md) for the exact status.

The `knowledge` directory is mounted read-only so a citation in `/agent` can open the original
published page or slide through the scoped source endpoint. Student uploads never enter published
course knowledge automatically.

## LangGraph checkpoints and HITL recovery

PostgreSQL deployments initialize `AsyncPostgresSaver` at FastAPI startup. The LangGraph
`conversation_id` is the durable thread ID. An interrupt commits an idempotent turn marker and a
checkpoint before waiting; resume uses `Command(resume=...)` on the same thread. Do not create a new
conversation to recover an interrupted turn.

Students may resolve only transcription confirmation interrupts. Course TA/teacher/admin sessions
may inspect the EvidenceBundle, Diagnosis, policy snapshot, scientific/tool results, response, and
HITL events in `/teacher/traces`; authorized staff can approve, reject, edit, take over, and resume
the current checkpoint. The BFF forwards the opaque `qa_session` cookie as a backend bearer token.
The legacy standalone teacher password is not accepted by this workspace.

Recovery procedure:

1. Keep PostgreSQL and its named volume intact; restart `api` and `web` with `make up`.
2. Open the same course/edition and conversation in `/teacher/traces`.
3. Inspect the current interrupt before acting. A 409 means another actor or retry changed it.
4. Submit one bounded resolution. The backend verifies interrupt ID, actor role, scope, and turn.
5. Confirm the resumed trace refers to the same conversation and has a terminal outcome.

Pre-interrupt writes and resume requests are idempotent. Never repair checkpoint tables manually
while the API is running.

## Test and release gates

Run deterministic checks first:

```bash
make test-api
make lint-api
make test-web
make lint-web
make test
make lint
```

Container and real-service checks require the configured secrets and a healthy stack:

```bash
make test-container
QA_LIVE_REQUIRE_CORPUS=1 make test-live-infra
make test-live-model
make test-live-e2e
```

The gates have different meanings:

- `test-live-infra` connects to real PostgreSQL/pgvector, checks Alembic `0004` and LangGraph
  checkpoint tables, talks to Neo4j and Redis, and probes the live API. With
  `QA_LIVE_REQUIRE_CORPUS=1`, it also asserts the published five-source/1,971-chunk corpus.
- `test-live-model` spends real USTC calls on image transcription, a handwritten derivation,
  diagnosis/verifier/citation flow, a native document, a plot plus numerical evidence, and same
  thread TA interrupt/resume/trace inspection.
- `test-live-e2e` runs the real `/agent` browser path and staff recovery. Its runner invokes the
  development-only `seed-live-e2e` command inside the API container, writes student and TA tokens to
  a mode-0600 temporary JSON file, never prints token contents, and deletes both host and container
  copies on exit. It refuses production and may activate the selected published course only through
  the runner's explicit `--activate-course` flag.

The live model and browser gates require `make up` first. Do not run them against production data.
The latest USTC provider probe from this environment (2026-08-24) did not pass because connectivity
ended in a timeout or TLS connection failure. This is an open external verification condition, not
a successful smoke test.

Before release, also run:

```bash
npm run build
npm run check:secrets
npm run test:e2e
```

Do not claim the release complete unless every required live gate finishes successfully against the
intended deployment.

## Monitoring and incident response

Use bounded server-side logs:

```bash
make logs
docker compose -f compose.yaml logs --tail=200 postgres neo4j redis
```

Never paste rendered environment configuration, authorization headers, cookies, attachment bytes,
raw student work, or unrestricted model payloads into an incident ticket.

| Signal | Check | Response |
|---|---|---|
| API readiness fails | PostgreSQL health, migration job, API traceback | Restore PostgreSQL first; do not switch production to SQLite |
| Checkpoint/HITL conflict | Same conversation and interrupt IDs, current trace | Re-inspect; do not replay a stale resolution |
| Citation/source preview fails | Publication scope, immutable source hash, read-only `knowledge` mount | Fail closed; do not substitute model text |
| Neo4j unavailable | Neo4j health and graph outbox | Continue only with explicitly degraded retrieval; rebuild from approved PostgreSQL state |
| Redis unavailable | Redis health/authentication | Restore the service and rerun live infrastructure tests |
| USTC unavailable | `probe-model`, bounded API logs, provider reachability | Keep deterministic policy/verifiers; do not invent multimodal results or mark the live gate passed |
| Upload rejected | HTTP code plus safe validation code | Check byte/image/page/archive bounds; never bypass content validation |
| Attachment volume full | Volume usage and failed storage writes | Stop uploads, expand or rotate storage under retention policy, then integrity-check hashes |
| Client secret scan fails | Files reported by `check:secrets` | Remove server identifiers/secrets from client code, rebuild, and scan again |

## Backup, shutdown, and rollback

Back up PostgreSQL before migrations and retain coordinated snapshots of `postgres_data` and
`attachment_data`; metadata without attachment bytes, or bytes without their scoped metadata, is an
incomplete restore. Neo4j can be rebuilt from approved PostgreSQL state. Preserve Redis only if its
operational use requires it.

`make down` stops services but preserves named volumes. Do not add `--volumes` unless destruction is
explicitly authorized and independently backed up.

For application rollback, select the prior immutable `QA_IMAGE_TAG`, rebuild or pull those images,
and restart. Database rollback is a separate reviewed operation: migration `0004` has a downgrade,
but downgrading drops attachment/extraction/parse-run tables and is destructive. Prefer restoring a
tested pre-migration PostgreSQL plus attachment-volume snapshot.

## Still-supported legacy web stack

Some older routes and tests still use the TypeScript teaching provider, `TEACHER_PASSWORD`,
`SESSION_SECRET`, and the optional legacy sandbox variables. They are compatibility-only. Do not
use their Cloudflare/D1 deployment notes, model routing, in-memory checkpoint behavior, or teacher
password flow as the V2.1 production runbook. `/agent` and `/teacher/traces` use the Python API,
course-scoped opaque sessions, PostgreSQL checkpoints, and the server-side registry documented
above.
