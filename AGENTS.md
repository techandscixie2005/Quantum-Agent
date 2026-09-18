# Repository Guidelines

## Project Structure & Module Organization

Quantum Agent teaches quantum physics using source-grounded explanations and deterministic teaching policy, scientific validation, routing, and persistence.

- `services/api/quantum_agent/`: authoritative Python FastAPI/LangGraph backend; domain packages include `knowledge/`, `teaching/`, `tutor/`, and `science/`. Migrations live in `services/api/alembic/`; tests in `services/api/tests/`.
- `app/`: React interface and API adapters. `lib/`, `worker/`, and `db/` retain legacy TypeScript backend logic, still checked by CI. Do not assume parity between stacks.
- `tests/`: Node tests, golden evaluations, and Playwright E2E tests. `public/` holds web assets; `knowledge/` contains original sources; `content/` holds ingestion manifests.
- `docs/implementation/`: architecture and operations, particularly [LOCAL_STACK.md](docs/implementation/LOCAL_STACK.md).

## Build, Test, and Development Commands

From the repository root:

- `make doctor` checks prerequisites; `make up` starts databases, migrations, API, and web after secrets are configured.
- `npm ci` installs web dependencies; `npm run dev` starts development.
- `npm test` runs unit/golden tests, builds, and checks rendered HTML.
- `npm run lint` and `npx tsc --noEmit` check TypeScript.

From `services/api/` (Python 3.12–3.13):

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run ruff check quantum_agent tests alembic
uv run mypy quantum_agent tests
```

## Coding Style & Naming Conventions

Use four-space Python indentation, type annotations, `snake_case` functions/modules, and `PascalCase` classes. Ruff enforces imports and a 100-character line limit; mypy uses strict mode. Match existing TypeScript style: two spaces, double quotes, semicolons, `camelCase` functions, and `PascalCase` components. ESLint uses Next.js/TypeScript rules.

## Testing Guidelines

Use pytest/pytest-asyncio (`test_*.py`), Node’s test runner (`*.test.ts`), and Playwright (`*.spec.ts`). Cover changed behavior and regressions; no numeric coverage threshold is configured. Run focused tests before relevant CI checks. Live tests are opt-in: `make test-live-infra` needs services; `make test-live-model` spends real model calls.

## Commit & Pull Request Guidelines

Follow history: `fix(backend): ...`, `feat(frontend): ...`, or `docs: ...`. Keep commits focused. PRs should explain behavior changes, reference relevant issues, report validation, and include screenshots for UI changes. Document configuration or migration requirements.

## Architecture & Security Boundaries

Original sources/chunks and PostgreSQL govern evidence and review; Neo4j/pgvector are derived indexes. Ingestion never publishes: expose only published chunks and approved graph versions. Preserve deterministic policy gates.

Never commit secrets or populated `.env*` files. Browsers send capability IDs; keep provider configuration server-side. Use `CredentialScopedRouterFactory` for session credentials; never log decrypted keys. Configure embeddings independently. Run `npm run check:secrets` before shipping.
