# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Quantum Agent is an evidence-grounded quantum-physics teaching agent for the USTC "107 Cup" Agent Track competition. The guiding principle: **the LLM writes explanations; deterministic code controls teaching policy, evidence provenance, model routing, scientific validation, and persistence.** It is not a generic chatbot.

There are **two parallel stacks** in this repository, and it is important to know which one you are touching:

1. **Python backend (`services/api/`)** — the current, authoritative implementation. FastAPI + LangGraph, backed by PostgreSQL (+pgvector), Neo4j, and Redis, managed with `uv` and Docker Compose.
2. **TypeScript web app (root `app/`, `lib/`, `worker/`)** — the *legacy* implementation (Next.js 16 on Vite via `vinext`, Cloudflare Workers, D1 + Drizzle, LangGraph.js). Still present and still built by CI, but being superseded by the Python stack. Several new `app/api/*/route.ts` routes are thin proxies/adapters to the Python API.

Do not assume both stacks implement the same behavior — they are separate codebases with separate tests.

## Commands

### Python backend (authoritative)

The locked environment is Python 3.12+ (`requires-python = ">=3.12,<3.14"`, managed by `uv` against `services/api/uv.lock`). All commands run from `services/api`:

```bash
cd services/api
uv sync --frozen --extra dev          # install/test env
uv run pytest -q                      # run all API tests (asyncio_mode=auto)
uv run pytest tests/test_retrieval.py -q   # single test module
uv run ruff check quantum_agent tests alembic   # lint
uv run mypy quantum_agent             # type check (strict)
```

The `quantum-agent` CLI (entry `quantum_agent/cli.py`) is the operational entry point:

```bash
quantum-agent migrate                 # Alembic upgrade to head
quantum-agent ingest --manifest content/quantum_course/manifest.toml
quantum-agent sync-graph --limit 100  # drain approved Neo4j outbox (or --watch)
quantum-agent probe-model             # test USTC chat reachability
quantum-agent probe-embedding         # test embedding provider
quantum-agent probe-live-model        # spend one real USTC round-trip via the API stack
quantum-agent publish-documents ...   # teacher approve+publish governance
quantum-agent ocr-textbook ...        # OCR scanned sources via vision model
quantum-agent evaluate ...            # offline evaluation metrics/runner
quantum-agent seed-demo-account ...   # create/refresh the competition demo student (see DEMO.md)
```

Live tests are gated behind registered pytest markers (`live_infra`, `live_model`, declared in `services/api/pyproject.toml`). Run a single marked test with `uv run pytest -m live_infra tests/...::test_name`; the markers are *opt-in* — unmarked runs skip them. The full live paths are `make test-live-infra` / `make test-live-model` / `make test-live-e2e` (E2E runs `scripts/run-live-e2e.sh`).

### Docker Compose stack (databases + both services)

```bash
make doctor            # check docker/uv/node prereqs
make compose-schema    # static Compose-spec validation (no Docker needed)
make compose-config    # render interpolated config (secrets required)
make up                # postgres+neo4j+redis -> migrate -> api -> web
make bootstrap         # up + ingest the real manifest
make migrate           # one-shot Alembic migrate
make ingest            # verify + ingest the real course manifest
make graph-worker      # continuous approved-graph outbox worker
make down              # stop, keep named volumes
make test-api          # Python tests (host-side uv env)
make lint-api          # Ruff
make test-container    # Python tests in network-disabled test image
make test-live-infra   # exercise live postgres/pgvector/neo4j/redis + API (no model calls)
make test-live-model   # spend real USTC calls (upload/tutor/HITL/trace)
make test-live-e2e     # real multimodal browser workflow via scripts/run-live-e2e.sh
```

Web at `http://127.0.0.1:3000`; API readiness at `http://127.0.0.1:8000/health/ready`; API docs at `/api/docs` in non-production.

### TypeScript (legacy)

```bash
npm ci                                # or `npm run install:ci`
npm run dev                           # vite dev server
npm run build                         # vinext build + validate-artifact.sh
npm test                              # full suite (unit + golden eval + build + rendered-html)
npm run test:unit                     # unit + golden eval only
npm run test:e2e                      # Playwright (needs dev server)
npm run lint                          # eslint
npx tsc --noEmit                      # typecheck
npm run check:secrets                 # scan dist bundle for leaked secrets
npm run eval:simulated-students       # simulated-student evaluation
```

## Architecture

### Authority and storage boundaries (core invariant)

This is the single most important concept in the codebase, documented in `docs/implementation/KNOWLEDGE_GRAPH_ARCHITECTURE.md`:

- **`/knowledge`** (12 files: 10 PDFs, 1 DOCX syllabus, 1 XLSX taxonomy) is the original source of truth. Original files + immutable source chunks are the authority for physical/scientific claims.
- **PostgreSQL** is the authority for document lifecycle, extracted candidates, provenance, teacher decisions, revisions, and the graph-sync outbox.
- **Neo4j** is a *derived, rebuildable* semantic index — never original evidence.
- **pgvector** embeddings are derived retrieval indexes. `EMBEDDING_PROVIDER=local_hashing` is a deterministic *degraded/lexical* fallback, not semantic AI.
- Only chunks from **published** document versions and graph nodes with an **approved** review version are student-visible.

Ingestion creates `REVIEW_REQUIRED` candidates and does not approve/publish anything. Graph sync only projects PostgreSQL records already approved through the review workflow.

### Python backend layout (`services/api/quantum_agent/`)

| Package | Purpose |
|---|---|
| `main.py` | FastAPI app factory with dependency injection; health `/health/live` + `/health/ready` |
| `config.py` | Pydantic-settings `Settings` (env-driven, secrets as `SecretStr`; SQLite allowed for tests, PostgreSQL required in production) |
| `cli.py` | `quantum-agent` operational CLI (migrate/ingest/sync-graph/probe/publish/ocr/seed-demo-account) |
| `db_models.py` | ~2000-line SQLAlchemy async models (users, courses, memberships, document versions, source chunks, evidence, review candidates, outbox, teaching sessions) |
| `alembic/` | 7 migrations (knowledge graph foundation, teaching policy/learning evidence, parser-scoped versions, multimodal attachments/doc runs, extended evidence kinds, durable learning phase, separate transfer/solo evidence kinds) |
| `knowledge/` | ingestion, extraction, ontology, retrieval (hybrid FTS+pgvector+Neo4j fusion), evidence packets, graph sync outbox, review, structural import |
| `teaching/` | fixed-order `TeachingStateMachine` (interpret → diagnose → retrieve evidence → generate → scientific validation → assemble), policy/release engine, hitl, specialist agents, repository, `learning_native.py` (native learning-evidence path + deterministic cognitive policy: commitment gates, teach-back, transfer, Solo Mode) |
| `coding/` | V3.1 Coding Agent: `agent.py` (subprocess-driven coding specialist), `sandbox.py` + top-level `sandbox_runner.py` (isolated subprocess execution), `safety.py` (boundary checks), `models.py` |
| `credential_vault.py` | Fernet-encrypted per-session credential vault (API-key login → encrypted-at-rest USTC_API per session) |
| `credential_router.py` | `CredentialScopedRouterFactory` — builds a model/embedding router scoped to the session's unlocked credential, so per-credential routing keys never touch the global `Settings` |
| `multimodal/` | attachments + document-runs contracts, OCR-derived perception, capabilities, storage, runtime, security, teaching |
| `evaluation/` | offline evaluation metrics + runner (models, fixtures, `__main__` entry) |
| `tutor/` | LangGraph `StateGraph` re-expression of the state machine (nodes/state/graph), behavior-preserving (B1) |
| `science/` | deterministic scientific toolbox + models (Hermiticity, normalization, commutators, etc.) |
| `llm/` | USTC model gateway, vision gateway, embeddings |
| `api/` | FastAPI routers: `attachments`, `course_context`, `graph`, `retrieval`, `review`, `source_files`, `teacher_insights`, `teaching` |
| `gateways.py`, `database.py`, `auth.py` | model/embedding/graph-store builders (gateways wires the credential vault + scoped router into the USTC gateway); async engine/session factory; `CourseActor` auth |

The teaching data flow: fixed-order state machine (see `teaching/state_machine.py`) mirrors the legacy LangGraph.js 18-node graph, but reimplemented server-side in Python. `TutorGraph` (`tutor/`, the LangGraph re-expression) reads/writes the same `TutorState` fields and produces identical `TeachingTurnResult`.

### Golden Loop (V3.3) — durable learning-phase sequence

The current sprint implements a multi-turn **Golden Loop**: each `TeachingConversation` carries a durable `learning_phase_json` (migration `0006`) whose `phase` is a `LearningPhase` enum in `teaching/models.py` (`open → commitment_required → attempt_received → intervention → awaiting_revision → verifying → reconstruction_required → transfer_required → solo_active → complete`). The non-skipping invariants: every phase mutation must pass `assert_phase_transition` (`teaching/learning_native.py:184`), which rejects transitions outside `_ALLOWED_PHASE_TRANSITIONS` — students cannot bypass commitment, teach-back (reconstruction), transfer, or the Solo Mode durable lock. `learning_native.py` is the pure deterministic policy (no personality/mastery-score output): the LLM only proposes *content*; code enforces gates, persistence, and Solo arming. The TS frontend mirrors this in `app/components/teaching/contracts.ts` (`LearningPhase`, `LearningStage`, `LearningNativeTurnState`) and renders it via `app/components/agent/LearningJourney.tsx`.

### TypeScript layout (legacy, still in CI)

- `app/page.tsx` — full frontend (student workspace + teacher dashboard), single-page React.
- `app/api/*/route.ts` — ~25 API routes; the `phase1/` and `teaching/` subdirs are adapters into the new backend.
- `lib/agent/` — LangGraph.js `StateGraph` (18 nodes, conditional routing, subgraphs, `interrupt()` for teacher review).
- `lib/agent/teaching-agents.ts` — specialist teaching agents (concept, derivation, exercise, misconception) sharing one LangGraph infra; surfaced via `app/agent/page.tsx`.
- `lib/providers.ts` — server-side capability→model routing; browser sends only capability IDs (`quick`, `deep`, `vision`, `code`), never real model names/keys.
- `lib/verifiers.ts` — deterministic scientific validators (TS equivalents of `science/toolbox.py`).
- `lib/simulation.ts`, `hydrogen.ts`, `helium.ts`, `diatomic.ts` — Crank-Nicolson simulation and QM computations.
- `db/schema.ts` + Drizzle — D1 schema (legacy DB path).

### Model routing (both stacks share this contract)

The browser sends only a capability ID. Server resolves it to a USTC model. The client bundle must never contain `deepseek`, `qwen`, `glm`, `api.llm.ustc.edu.cn`, or `sk-` patterns — verified by `npm run check:secrets`.

Single chat credential `USTC_API`. Embeddings are configured **independently** (`EMBEDDING_*`) because the USTC chat endpoint does not serve embeddings.

**V3.1 per-session credentials (Python backend).** When the credential vault is enabled, the server-side `USTC_API` is *not* used directly for student sessions. Instead, the browser logs in with an API key (`/api/v1/auth/...`), the key is encrypted at rest in the Fernet vault (`credential_vault.py`), and each teaching session builds a `CredentialScopedRouterFactory` (`credential_router.py`) that routes model/embedding calls through *that session's* unlocked credential. `Settings.ustc_api` remains the fallback for teacher/admin paths and for sessions that predate the vault. Never log decrypted credential material; route through the scoped factory rather than reading `Settings.ustc_api` inside per-turn code.

## Secrets & environment

Required before `make up`/`make require-secrets`: `POSTGRES_PASSWORD`, `POSTGRES_PASSWORD_URLENCODED` (RFC 3986 form used in the async SQLAlchemy URL — identical to `POSTGRES_PASSWORD` for alphanumeric values), `NEO4J_PASSWORD`, `REDIS_PASSWORD`, `USTC_API`.

- Python config reads `.env` / `.env.local` via `pydantic-settings`; `case_insensitive=True`, `extra="ignore"`.
- Never commit `.env*` (only `.env.example`). The `web` container never receives `USTC_API` or DB passwords — it proxies to the API via `QUANTUM_API_BASE_URL` on the Docker edge network.
- CI (`check-secrets.sh` + GitHub `secret-scan` job) blocks `sk-`, `ghp_`, `gho_`, and non-empty `USTC_API`/`TEACHER_PASSWORD`/`SESSION_SECRET` in git history.

## Testing

- Python tests are pytest with `asyncio_mode=auto`, `testpaths=["tests"]`, strict config/markers. Cover ingestion, extraction, OCR, ontology, retrieval, evidence packets, gateways, graph store/sync, teaching state machine, tutor graph, scientific tools, API, auth, pipeline safety, and real E2E against the Docker stack (`test_phase1_real_e2e.py`, `test_phase2_real_e2e.py`). `test_golden_loop_phase_sequence.py` drives the real `TutorGraph` (with `_TunnelingRetriever` + `FakeModelGateway`, no tokens) through the durable `LearningPhase` sequence and asserts the anti-skip invariants.
- TS tests: `tests/backend.test.ts`, `tests/validators-citations-auth.test.ts`, `tests/golden/eval.test.ts` (deterministic, no tokens), `tests/rendered-html.test.mjs`, Playwright `tests/e2e/` (including `golden-loop.spec.ts` and live `tests/e2e/live/golden-loop-deterministic.spec.ts`).

## Key documents

| Doc | Purpose |
|---|---|
| `docs/implementation/KNOWLEDGE_GRAPH_ARCHITECTURE.md` | authority model, phase-1 data flow, retrieval contract, failure rules |
| `docs/implementation/LOCAL_STACK.md` | Compose stack services, secrets, operations |
| `docs/implementation/LANGGRAPH_DECISIONS.md` | LangGraph design decisions |
| `docs/implementation/OWNERSHIP_MAP.md` | ownership boundaries |
| `docs/implementation/COMPLETION_REPORT.md` | post-implementation scope/summary (LangGraph migration) |
| `docs/TEACHING_POLICY.md`, `docs/SCIENTIFIC_VALIDATION.md`, `docs/REQUIREMENTS_TRACEABILITY.md` | policy gates, validation rules, PRD traceability |
| `docs/evaluation/` | offline eval datasets + reports |
| `docs/competition/*` | design doc, judging criteria, demo script, known limitations |
| `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/API.md`, `docs/COURSEWARE.md` | TS-era architecture/deploy/security/privacy/API/courseware |
