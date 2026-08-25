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

Docker is not installed in the implementation environment, so images were not
built, pulled, or executed here. A Docker-capable host must run
`make compose-config`, `make build`, `make up`, and the container health checks
before treating the stack as deployment-verified.

For a public deployment, additionally terminate TLS at a trusted reverse proxy,
replace loopback port publishing with the platform ingress, enforce database
backups and retention, pin images by digest after platform selection, and move
all secrets to managed secret storage.
