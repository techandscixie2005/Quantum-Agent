# Local Quantum Agent stack

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

Both image build contexts have dedicated `.dockerignore` rules. Local virtual
environments, `node_modules`, course-source files, Git history, generated
artifacts, and ignored environment files are not sent to the Docker daemon or
a remote builder.

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

Host-side locked environments:

```bash
make test-api
make lint-api
make test-web
make lint-web
```

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
