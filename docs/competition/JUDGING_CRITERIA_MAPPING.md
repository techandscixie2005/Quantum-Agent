# Judging Criteria Mapping

## 1. Innovation

| Evidence | File reference |
|---|---|
| Workflow-first architecture: LLM writes explanations, deterministic code controls teaching policy, citations, validation, model routing | `lib/tutor-engine.ts` `runTutorWorkflow()` — 16-step pipeline |
| Capability-based model routing: students choose what they want to do, server chooses model | `lib/providers.ts` `providerConfigForCapability()` |
| Citation allowlist post-processing: model cannot invent a page reference | `lib/citation-allowlist.ts` `enforceCitationAllowlist()` |
| Scientific validators are deterministic, not LLM-decided: pass/fail is computed by pure functions | `lib/verifiers.ts` — 11 validators, all with `provenance: "deterministic"` |
| Teacher trajectory replay with full trace node audit: every teaching decision is observable | `app/api/trace/route.ts` + `lib/repository.ts` `analyticsSnapshot()` |

## 2. Practical Value

| Evidence | File reference |
|---|---|
| Covers a real USTC quantum physics course (7 lecture PDFs, 737 pages, 726 indexed chunks) | `lib/courseware.generated.json` + `public/courseware/*.pdf` |
| Three-column teaching workbench maps to actual student workflows: concept explanation, derivation debugging, numerical experiment, course project | `app/page.tsx` — ConceptWorkspace, DerivationWorkspace, ExperimentWorkspace, ProjectWorkspace |
| 4 course projects with milestones, validators, starter code, and reflection questions | `lib/projects.ts` `projectDefinitions[0-3]` |
| Teacher dashboard with misconception map, hint dependency tracking, escalation queue | `app/page.tsx` `TeacherDashboard` |
| Fallback teaching engine works without any API key — usable immediately in any classroom | `lib/tutor-engine.ts` `fallbackAnswer()` |

## 3. Technical Difficulty

| Evidence | File reference |
|---|---|
| Custom RAG: hybrid lexical retrieval with Chinese mathematical query normalization, symbol-aware expansion, deduplication, minimum evidence threshold | `lib/retrieval.ts` |
| 11 deterministic scientific validators handling complex matrices, eigenvectors, dimensional analysis | `lib/verifiers.ts` |
| Multi-provider model adapter (USTC, OpenAI, Anthropic, Google) with per-capability routing, timeout, retry, and fallback | `lib/providers.ts` |
| Full D1 schema with 11 tables, foreign keys, unique indexes, prepared statements via Drizzle | `db/schema.ts` + `drizzle/0000_happy_leper_queen.sql` |
| Server-side teacher auth with HMAC-signed cookies, constant-time password comparison | `lib/teacher-auth.ts` |
| Cloudflare Worker deployment with single-origin frontend + API + image optimization pipeline | `worker/index.ts` + `vite.config.ts` |

## 4. Completeness

| Evidence | File reference |
|---|---|
| 28 deterministic tests pass (11 original + 16 unit + 1 golden eval with 12 sub-cases, 39 invariants, 0 failures) | `tests/backend.test.ts` + `tests/validators-citations-auth.test.ts` + `tests/golden/eval.test.ts` |
| TypeScript typecheck clean | `npx tsc --noEmit` |
| Production build succeeds | `npx vinext build` |
| ESLint clean | `npm run lint` |
| Citation integrity tested: adversarial injection prompts trigger escalation and return zero fabricated citations | `tests/golden/eval.json` case 8 |
| Full documentation suite: README, CLAUDE.md, ARCHITECTURE, DEPLOYMENT, SECURITY, PRIVACY, MODEL_ROUTING, SCIENTIFIC_VALIDATION, TEACHING_POLICY, API, 4 competition docs, REQUIREMENTS_TRACEABILITY | `docs/` + `docs/competition/` |
| Privacy controls: data export, data deletion, retention documentation | `app/api/user/export/` + `app/api/user/delete/` + `docs/PRIVACY.md` |
| Requirements traceability: every PRD requirement mapped to implemented/incomplete/missing/out-of-scope | `docs/REQUIREMENTS_TRACEABILITY.md` |
| Production artifact: verified zip archive that extracts and builds in a fresh directory | `Quantum-Agent-production.zip` |
| GitHub repository with CI, dependabot, issue templates | `.github/` |