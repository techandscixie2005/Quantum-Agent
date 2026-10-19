# Local Quantum Agent stack

For the classroom increment, also read
[CLASSROOM_EVALUATION_PROTOCOL.md](CLASSROOM_EVALUATION_PROTOCOL.md) and
[CLASSROOM_IMPROVEMENTS.md](CLASSROOM_IMPROVEMENTS.md). Historical demonstration
credentials and shared demo identities are not classroom enrollment.

`compose.yaml` runs the Python knowledge and deterministic teaching stack beside
the existing Vinext web application. PostgreSQL remains authoritative; Neo4j is a rebuildable
approved-only projection, Redis is ephemeral coordination/cache infrastructure,
and `/knowledge` remains the original source of truth.

## Services

| Service | Image / build | Exposure | Purpose |
|---|---|---|---|
| `postgres` | PostgreSQL 15 + pgvector 0.8.6 | internal only | authoritative provenance, review, retrieval, and outbox data |
| `neo4j` | Neo4j 5.26 Community | internal only | approved graph projection |
| `redis` | Redis 7.4 | internal only | bounded cache/coordination hook |
| `migrate` | Python 3.12 API image | none; one-shot | Alembic upgrade required before API startup |
| `api` | Python 3.12, non-root | `127.0.0.1:8000` | FastAPI review and knowledge services |
| `web` | Node 22, non-root | `127.0.0.1:3000` | existing Next/Vinext experience |
| `ingest` | API image, `jobs` profile | none; one-shot | checksum-verifies and ingests the real course manifest |
| `graph-sync-*` | API image, job/worker profiles | none | dispatches approved PostgreSQL outbox records to Neo4j |

The database network is marked `internal`. `api` and the one-shot ingestion job
join both the internal and edge networks: the API can reach USTC and ingestion
can reach a separately configured external embedding service. The web
container never receives `USTC_API` or database passwords; its server-side
proxy reaches the API through `QUANTUM_API_BASE_URL` on the edge network.

The web context uses `.dockerignore`; the API uses the repository-root context
with the positive allowlist in `services/api/Dockerfile.dockerignore`. Backend
code and the test stage's exact offline packet/scripts are allowed. Runtime API
images contain only backend code; teacher keys are copied only into the test
stage. Original course files are read-only mounts, not image contents. Local
environments, dependencies, Git history, generated artifacts and credentials
remain outside the build contexts. A direct API build now uses
`docker build -f services/api/Dockerfile --target runtime .` from the root.

## Prerequisites and secrets

- Docker Engine with Docker Compose v2.20 or newer.
- `make`; `uv` is also needed for host-side Python checks.
- At least 8 GB available memory is recommended for the complete scientific
  Python and Neo4j stack.

Compose refuses to render until these values are supplied:

```text
POSTGRES_PASSWORD
POSTGRES_PASSWORD_URLENCODED
NEO4J_PASSWORD
REDIS_PASSWORD
USTC_API
SESSION_VAULT_KEY
```

`POSTGRES_PASSWORD_URLENCODED` is the RFC 3986 percent-encoded form used inside
the async SQLAlchemy URL. For an alphanumeric password it is identical to
`POSTGRES_PASSWORD`. Generate it without printing the raw value:

```bash
export POSTGRES_PASSWORD_URLENCODED="$(
  python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["POSTGRES_PASSWORD"], safe=""))'
)"
```

Keep values in the shell environment or an ignored, mode-`0600` `.env` file.
Do not pass secrets as Docker build arguments. For a shared deployment, replace
Compose environment variables with the platform's secret manager.

`SESSION_VAULT_KEY` must be a Fernet key; it encrypts user credentials stored by
the backend. Preserve it across restarts so existing session credentials remain
readable. The isolated sandbox runner receives neither this key nor provider
or database credentials.

Optional settings include `POSTGRES_DB`, `POSTGRES_USER`, `API_PORT`,
`WEB_PORT`, `API_ENVIRONMENT`, `EMBEDDING_PROVIDER`, the separate
`EMBEDDING_*` credential set, `QUANTUM_API_BASE_URL` outside Compose, and
`GRAPH_SYNC_BATCH_SIZE`. The default embedding mode is explicitly labeled
`local_hashing`; it is deterministic degraded retrieval, not a learned semantic
embedding service.

## Start and operate

```bash
make compose-schema   # static Compose-spec validation; Docker is not required
make compose-config   # Docker interpolation/config validation; secrets required
make up               # healthy databases -> migration -> API -> web
make ps
```

Once healthy:

- Web: `http://127.0.0.1:3000`
- API readiness: `http://127.0.0.1:8000/health/ready`
- API docs in non-production mode: `http://127.0.0.1:8000/api/docs`

Run operational jobs explicitly:

```bash
make migrate
make ingest
make graph-sync
make graph-worker       # optional continuous outbox worker
make graph-worker-stop
```

Run a selected real browser acceptance test against the healthy stack:

```bash
bash scripts/run-live-e2e.sh golden-loop-deterministic.spec.ts
```

The script creates temporary test credentials, removes them on exit, and forwards
Playwright arguments. It requires `USTC_API` in the shell and spends real model
calls. It seeds test accounts but does not start or rebuild the stack.

When the image registry is unavailable, an already-built test image can check
the running infrastructure without rebuilding dependencies:

```bash
docker compose --profile tools run --rm --no-deps api-live-test
```

This checks existing images; it does not establish that they match the working
tree. Rebuild API/web after source changes before accepting a release.

`make ingest` mounts `content/` and `knowledge/` read-only and executes:

```bash
quantum-agent ingest \
  --manifest /workspace/content/quantum_course/manifest.toml
```

The manifest hashes are verified before persistence. Ingestion creates
review-required candidates; it does not approve or publish knowledge. Graph
sync only handles records already approved through the PostgreSQL review
workflow.

Stop containers while retaining data:

```bash
make down
```

Named volumes are intentionally not deleted by any Make target. Back up
PostgreSQL and Neo4j volumes before manual destructive maintenance.

## Tests and lint

### Classroom enrollment and version provenance

Back up PostgreSQL, then run `make migrate` before starting the updated API.
Migration `0009` adds indexed immutable request identities and backfills keys
where retained in historic JSON. Missing historical inputs cannot be recreated.
Migration `0010` adds append-only teacher decisions. Verify migrations on the
deployment PostgreSQL instance; SQLite checks do not prove multi-worker locking.

Set `BUILD_REVISION` to the **full source commit used to build the image**, then
rebuild/restart the API. The runtime records that revision, workflow version,
package version/digest, evidence document/chunk digests, and observed model route
aliases in each new turn. Unset/invalid revisions remain `unknown`; provider
aliases do not identify immutable model weights. Paused/resumed turns preserve
execution segments when deployment versions change.

Classroom login requires a separate personal access token and a provider key.
Provider credentials grant model use, never a student identity or teacher role.
An authorized operator can provision named roster members for an active course:

```bash
quantum-agent issue-classroom-access \
  --course-id COURSE_UUID --email student@example.edu \
  --display-name 'Student name' --role student \
  --expires-hours 24 --output /private/classroom/student-access.json
```

Run this command in the API's configured environment with database access.
Use a private directory outside the repository and distribute the one-time token
through the institution's approved channel. The command never prints the token,
refuses to overwrite an existing file or silently change an existing role, and
requires neither a provider key nor a model call. `--role teacher` and `--role ta`
are explicit operator actions. Existing inactive/different-role memberships
require roster review. Unix files are created with mode 0600; on Windows, restrict
the directory's ACL because POSIX mode bits do not establish private access.

Enter the token in `/agent` with the user's provider key. The exchange requires
the encrypted vault, consumes the token once, and issues an opaque session.
Expired/used tokens require reissuance. Invitations cannot access teaching APIs
before exchange. Institutional SSO integration remains deployment work.

`ALLOW_SHARED_DEMO_LOGIN=false` is the default. For an explicitly labeled local
scripted demonstration only, operators may opt in outside production after
seeding the demo account. Production ignores that opt-in. Never use the shared
identity to collect individual classroom learning records. Existing automated
live tests using independently seeded opaque sessions remain separate.

Teacher/admin accounts can record reasoned follow-up decisions in
`/teacher/traces`; TAs can inspect records but cannot submit these decisions.
Student and staff views link the bounded JSON export. Exports include raw student
answers and reviewer IDs: store them privately, use pseudonymous IDs in analysis,
and apply the institution's retention and access process. Review records are
append-only; plan retention/erasure with the authoritative database's existing
evidence governance rather than ad hoc SQL deletion.

The Linux sandbox remains the supported execution environment. Windows imports
work, while local untrusted execution refuses to run without POSIX limits.
`CODING_SANDBOX_REQUIRE_ISOLATION=true` fails closed when namespace isolation is
unavailable. Do not disable isolation to make a classroom demonstration pass.

Optional evidence budgets are explicit: export at most 500 turns, 5,000 learning
events, 500 teacher decisions and 8 MB; oversized exports return 413 without
partial success. Plot caching retains at most 16 immutable JSON specifications
and bypasses keys above 64 KB. Model fallback deadlines cap each routed call.
Migration `0011` also persists an aggregate allowance per teaching turn across
stages/retries/recovery; it does not limit the number of deliberately new turns
in an episode. Keep provider quotas and recording budgets configured as well.

The secret scan is portable: `npm run check:secrets` uses Node and fails when
public build artifacts are missing. Other existing build wrapper scripts still
require Bash/GNU tools; on Windows the underlying build can be checked with
`node node_modules/vinext/dist/cli.js build`, followed by the artifact and HTML
checks documented in the classroom report.

Host-side locked environments:

```bash
make test-api
make lint-api
make test-web
make lint-web
```

## Teaching deadlines, recovery and worker limits

`API_WORKERS=2` is the Compose default. Checkpoint DDL is serialized across
workers using a dedicated PostgreSQL session and nonblocking advisory-lock
attempts; setup failure/cancellation closes that connection. PostgreSQL and a
shared Redis vault remain required for restart/multiworker evidence. Preserve
`SESSION_VAULT_KEY` across restarts. Readiness checks confirm connectivity, not
course completeness or model quality.

Runtime scientific libraries use one BLAS/OpenMP thread per process. This
prevents a 48-thread OpenBLAS startup from exhausting the sandbox's 32-PID
container allowance. The runner still has no network, credentials or API PID
visibility; resource failure remains visible. Do not increase privileges to
make a failed sandbox test pass.

| Setting | Default | Meaning |
|---|---:|---|
| `TEACHING_EXECUTION_SECONDS` | 180 | Cumulative active seconds per durable turn, at most 600 |
| `TEACHING_EXECUTION_PROVIDER_REQUESTS` | 12 | Actual provider HTTP attempts, including SDK retries |
| `TEACHING_EXECUTION_TOKEN_UNITS` | 131072 | Conservative serialized-input/output admission units |
| `TEACHING_EXECUTION_OUTPUT_TOKENS` | 2048 | Per-call admitted maximum output |
| `TEACHING_EXECUTION_REQUEST_BYTES` | 65536 | Maximum serialized provider request size |
| `TEACHING_PROXY_TIMEOUT_SECONDS` | 210 | BFF transport deadline, at least active limit + 15 seconds |

Persisted allowances do not refill when configuration changes or a worker
restarts. Human waiting is separate; a crashed lease is charged conservatively.
Reported provider tokens can be partial and are not inferred from admission
units. These are per-turn limits, not a school-wide monetary quota.

The BFF emits bounded terminal error codes for budget exhaustion/busy leases
and interrupted transport. On `/agent`, retain input and use **检查保存状态**.
It queries the original `client_request_id` within the current account/course,
restores completed results or an unresolved review, and can replay the original
submission without inventing another request identity. An exhausted failed
turn requires an explicit new submission after restoration. Its original raw
request remains auditable and gains no assessment credit merely by being saved.

For a reverse proxy, disable SSE buffering and compression/buffering that
delays events; set its overall request allowance above the BFF deadline and
its idle read timeout above the four-second heartbeat interval. Confirm the
actual hosting platform supports the chosen duration. The current local
deployment target is the Compose/Vinext Node server. The browser integration
harness uses Vite/Vinext without hosting-only Cloudflare machinery; it does not
certify a Cloudflare deployment. A smaller platform limit needs an asynchronous
job/polling deployment design before a classroom trial, not a larger hidden retry.

## Isolated reproducibility stack on Windows/WSL

The October 20 verification installed Ubuntu on D using:

```powershell
wsl --install Ubuntu-24.04 --no-launch --location D:\QuantumAgent\outputs\linux-runtime\Ubuntu
```

Its `ext4.vhdx`, Linux Docker data and downloaded runtime archives are on D.
The pre-existing Windows WSL launcher remains a Windows system component.
Virtual disks, image layers and private runtime secrets are excluded from source
snapshots; versions, digests, commands and test logs are captured separately.

For a new disposable Linux test stack (never a classroom database):

```bash
python3 scripts/provision-trial-secrets.py /PRIVATE/qa-trial
docker compose -p qa-classroom-trial -f compose.yaml -f compose.registry.yaml \
  -f compose.trial.yaml --env-file /PRIVATE/qa-trial/private.env config --quiet
docker compose -p qa-classroom-trial -f compose.yaml -f compose.registry.yaml \
  -f compose.trial.yaml --env-file /PRIVATE/qa-trial/private.env up --build -d
python3 scripts/with-trial-environment.py --private-env /PRIVATE/qa-trial/private.env \
  -- node node_modules/@playwright/test/cli.js test --config playwright.backend-live.config.ts
```

The generated provider value is a synthetic placeholder. The browser harness
routes all model traffic to its local HTTP double; this stack is not enrolled
for real teaching. `compose.trial.yaml` adds loopback database ports and a test
network attachment so host tests can connect. Production `compose.yaml` keeps
those databases internal. Never print interpolated Compose configuration:
use `config --quiet` because full rendering contains secrets.

The fresh-DB migration roundtrip is opt-in and requires CREATE DATABASE
permission. It creates/drops only its own UUID-named database; removing new
tables/columns is not a data-preserving rollback procedure. Back up actual
classroom data before any migration maintenance.

See [real-backend test instructions](../../tests/e2e/backend-live/README.md) and
[classroom protocol](CLASSROOM_EVALUATION_PROTOCOL.md). Provision actual personal
memberships, review/publish the real sources, and complete real teacher approval
before admitting students; synthetic fixture review registries are rejected by
the production loader.

The API also has a network-disabled test image:

```bash
make test-container
make lint-container
```

## Validation status

On 2026-08-22 this infrastructure was validated with:

- the upstream Compose JSON schema;
- YAML parsing with interpolation left opaque;
- availability of every versioned base/service image tag in its registry;
- `make -n` command expansion;
- Python Dockerfile parsing;
- existing non-Docker Python lint/tests.

Docker was not installed in that original implementation environment. A Docker-capable host must run
`make compose-config`, `make build`, `make up`, and the container health checks
before treating the stack as deployment-verified.

For a public deployment, additionally terminate TLS at a trusted reverse proxy,
replace loopback port publishing with the platform ingress, enforce database
backups and retention, pin images by digest after platform selection, and move
all secrets to managed secret storage.


## Docker Hub mirror 401 recovery (2026-09-15)

The Dockerfiles use the Docker daemon's bundled BuildKit frontend. They no
longer pull `docker/dockerfile:1.7` before resolving base images. If a daemon
mirror also rejects Python/Node/service images, use the checked-in official
ECR configuration:

```bash
make build-registry
make up-registry
```

Equivalent commands, including operational/test profiles:

```bash
docker compose -f compose.yaml -f compose.registry.yaml build --pull api web postgres
docker compose -f compose.yaml -f compose.registry.yaml up --no-build -d
docker compose -f compose.yaml -f compose.registry.yaml --profile tools build api-test
```

`compose.registry.yaml` uses the [Docker Official Images published to ECR](https://www.docker.com/blog/news-from-aws-reinvent-docker-official-images-on-amazon-ecr-public/)
for Python, Node, PostgreSQL, Neo4j and Redis. pgvector 0.8.6 is compiled from
[upstream source](https://github.com/pgvector/pgvector/tree/v0.8.6), with an
explicit SHA-256 check on the archive. Its PostgreSQL major version remains 15.
Existing database volumes are preserved. No daemon-wide proxy or DNS changes
are required. The uv image remains pinned to its existing GHCR digest.

To verify uncached package installation as well as image-layer rebuilding:

```bash
docker compose -f compose.yaml -f compose.registry.yaml build --pull --no-cache \
  --build-arg UV_CACHE_ID=quantum-agent-fresh-verification api web postgres
```

Use a new `UV_CACHE_ID` for each deliberate cold-cache verification. Registry
credentials, course documents and application secrets are never build arguments.

## Pedagogical graph candidates and review

Migration `0008` adds `DerivationStep`, `Assumption` and `ValidityCondition`.
It preserves existing graph decisions and supports both PostgreSQL and SQLite
fresh migrations, including dependent views and policy triggers.

Extract bounded candidates from already published course chunks:

```bash
docker compose exec -T api quantum-agent extract-pedagogy \
  --course-id COURSE_UUID --edition-id EDITION_UUID --query barrier --limit 5
```

This command spends model calls and only creates `review_required` candidates.
It checks exact source spans, aligns whitespace without changing symbols,
omits unsupported candidates/relations and reports omission counts. Successful
chunk runs replay without model calls; reruns never overwrite teacher decisions.
Failed runs remain auditable and can be retried. Use the teacher knowledge
workspace to inspect and approve candidates before graph synchronization.

The current review packet is [CORE_PLAN_TEACHER_REVIEW.md](CORE_PLAN_TEACHER_REVIEW.md).
Refresh its raw read-only audit with:

```bash
docker compose exec -T api python < scripts/audit-core-content.py > course-review.json
```

Coverage counts are lexical discovery evidence, not certification that all
chapters have complete teaching graphs or independently verified learning tasks.

## Retired TypeScript teaching APIs

`/api/verify`, `/api/evaluation`, `/api/sessions`, `/api/student/state`,
`/api/projects`, `/api/teacher/intervene`, `/api/teacher/respond` and
`/api/teacher/analytics` return HTTP 410. They previously maintained a separate
TypeScript verifier, simulated episodes or persistence. Use `/agent` and the
Python teaching/teacher-trace adapters for the competition runtime. Legacy
TypeScript libraries remain available to offline tests and evaluations.

### 真实验收的课程版本

最新发布版本可能只有教学大纲；它不能替代教材证据。用命令面板选择有已发布
教材正文的课程版本后再运行教学任务。不要通过跨版本检索或放宽证据门解决
`insufficient_coverage`。

真实浏览器脚本可用 `QA_LIVE_EDITION_ID=<已发布版本 UUID>` 指定课程；种子将
同一版本写入验收凭据，浏览器登录后通过产品的课程切换入口选择它。当前本机
教材版本为 `64077260-0470-5742-8424-c73697d9f399`，只适用于本机已导入的数据：

```bash
QA_LIVE_EDITION_ID=64077260-0470-5742-8424-c73697d9f399 \
  bash scripts/run-live-e2e.sh golden-loop-deterministic.spec.ts

docker compose --profile tools run --rm --no-deps \
  -e QA_LIVE_EDITION_ID=64077260-0470-5742-8424-c73697d9f399 \
  api-live-model-test
```

空库需先导入课程材料并完成教师审核/发布，不能直接套用上述 UUID。
