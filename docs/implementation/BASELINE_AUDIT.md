# Baseline Audit

**Date**: 2026-07-12
**Baseline commit**: 9f3b5e349aa286e701b74abd1f21aa9ad6a9b267
**Branch**: main

## Repository state

- 20 source files in `lib/`, 18 API routes, 11 Drizzle tables
- All existing tests pass (npm test: 19 unit/backend tests, 1 rendered HTML test)
- Production build succeeds (vinext build + validate-artifact)
- TypeScript compiles cleanly

## What works (real)

| Subsystem | Status | Evidence |
|-----------|--------|----------|
| Scientific validators | REAL (11 tools) | tests pass on Hermiticity, normalization, probability conservation, commutators, boundary continuity, orthogonality, matrix symmetry, eigenvalue residual, dimensional consistency, numerical convergence, shape consistency |
| Citation allowlist | REAL | buildCitationAllowlist, enforceCitationAllowlist, detectFabricatedCitations all tested |
| USTC model routing | REAL (server-side) | providerConfigForCapability routes 5 capability IDs to USTC models; public API exposes only Chinese labels |
| Retrieval | REAL (lexical/BM25) | 726 page-aware chunks from 7 PDFs; Franck-Condon test passes |
| Policy enforcement | REAL (H0-H5) | enforceHintLevel caps at 3; misconceptions detected |
| Teacher auth | REAL | HMAC-signed cookies; session verify/issue tested |
| D1 persistence | REAL (Drizzle ORM) | 11 tables; persistTutorExchange writes sessions, turns, states, escalations |
| Sandbox preflight | REAL | Static inspection rejects network/FS access; executeInSandbox requires config |
| Rate limiting | REAL | In-memory sliding window; tested at 30 req/min |
| Attachment validation | REAL | MIME type, size, base64 validation; tested |

## What is fake/mocked/hardcoded

| Issue | Location | Severity |
|-------|----------|----------|
| Frontend: static "演示数据" tags | `app/page.tsx`:121,421 | HIGH |
| Frontend: hardcoded R/T values | `app/page.tsx`:336 `(0.81 + width * .02)` | HIGH |
| Frontend: hardcoded misconception list | `app/page.tsx`:428-429 | MEDIUM |
| Frontend: hardcoded TA queue | `app/page.tsx`:431 | MEDIUM |
| Frontend: static "58%" progress | `app/page.tsx`:355 | MEDIUM |
| Frontend: static "12" history count | `app/page.tsx`:114 | LOW |
| DerivationWorkspace: static steps | `app/page.tsx`:282-303 | HIGH |
| ExperimentWorkspace: fake probability array | `app/page.tsx`:314 `Math.max(0.00008, width * 0.00004)` | HIGH |
| ExperimentWorkspace: no real simulation | No Crank-Nicolson/diffeq solver | CRITICAL |
| ProjectWorkspace: static completion state | `app/page.tsx`:345-348 | MEDIUM |
| Tutor API: no real derivation/experiment/project backends | Only concept mode calls /api/tutor | HIGH |
| USTC credential: uses USTC_API_KEY not USTC_API | `lib/providers.ts:108` | HIGH |
| Identity: trusts oai-authenticated-user-* headers | `lib/request-user.ts` | HIGH |
| Teacher cookie: `secure = false` hardcoded | `lib/teacher-auth.ts:79` | MEDIUM |
| No LangGraph: workflow is a single async function | `lib/tutor-engine.ts` | CRITICAL |
| No streaming | `lib/providers.ts` | MEDIUM |
| No interrupt/resume | No implementation | MEDIUM |
| No checkpointing | No implementation | MEDIUM |
| No simulated student evaluation | No implementation | CRITICAL |
| Projects 2-4: definitions only, no computation | `lib/projects.ts` | HIGH |
| No E2E tests | No Playwright tests | CRITICAL |

## Key architectural issues

1. **Monolithic tutor engine**: `runTutorWorkflow` is a single function, not a graph
2. **USTC_API_KEY vs USTC_API**: PRD requires `USTC_API` as sole credential; code uses `USTC_API_KEY`
3. **No LangGraph.js**: Zero LangGraph dependency or graph-based orchestration
4. **Frontend disconnected**: Most workspaces show static content, not real API data
5. **No E2E tests**: Zero Playwright tests exist
6. **Identity insecure**: Trusts arbitrary `oai-authenticated-user-*` headers
7. **No real tunneling simulation**: Wave-packet values are fabricated