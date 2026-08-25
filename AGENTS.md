# Repository Guidelines

## Project Structure & Module Organization

The authoritative backend lives in `services/api/quantum_agent/` and uses FastAPI, LangGraph, SQLAlchemy, and Alembic; its tests are in `services/api/tests/`. The still-supported TypeScript web stack uses `app/` for pages and routes, `lib/` for domain and agent logic, and `worker/` for runtime code. Root `tests/` contains Node tests, Playwright specs in `tests/e2e/`, and golden data in `tests/golden/`. Course sources belong in `knowledge/` and `courseware-source/`; public assets in `public/`; design and operations notes in `docs/`.

## Build, Test, and Development Commands

- `cd services/api && uv sync --frozen --extra dev`: install the locked Python environment.
- `make test-api` / `make lint-api`: run pytest or Ruff for the backend.
- `npm ci && npm run dev`: install web dependencies and start the Vite/vinext development server.
- `npm test`: run web unit/golden tests, build, and rendered-HTML checks.
- `npm run test:e2e`: run Playwright browser tests (requires a running app).
- `make test` / `make lint`: check both stacks.
- `make up`: start databases, API, and web services; required secrets must be set.

## Coding Style & Naming Conventions

TypeScript follows ESLint's Next.js rules: use two spaces, `PascalCase` components, `camelCase` functions, and `route.ts` route files. Python targets 3.12, uses four spaces and a 100-character limit, with Ruff and strict mypy. Use `snake_case` for Python modules/functions and `PascalCase` for classes. Deterministic code—not model output—must control evidence, policy, validation, and persistence.

## Testing Guidelines

Add tests with behavior changes. Python files follow `test_<feature>.py`; TypeScript tests use `*.test.ts` or `*.test.mjs`; browser scenarios use `*.spec.ts`. Run the narrowest relevant test, then `make test`. No coverage threshold is configured; prioritize regressions, authorization boundaries, citation provenance, and scientific validation.

## Commit & Pull Request Guidelines

History uses Conventional Commit-style subjects such as `feat: ...`; use concise imperative prefixes (`feat:`, `fix:`, `test:`, `docs:`) and keep commits focused. Pull requests should explain the change, identify the affected stack, list verification commands, link relevant issues, and include screenshots for UI changes. Call out migrations, new environment variables, and operational impact.

## Security & Configuration

Copy `.env.example` locally; never commit credentials or generated environment files. Run `npm run check:secrets` before changes involving providers or deployment. Browser code must send capability IDs only and must never expose model names, API keys, or database passwords.
