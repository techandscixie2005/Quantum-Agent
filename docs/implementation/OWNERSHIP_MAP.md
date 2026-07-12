# Ownership Map

**Date**: 2026-07-12

## Workstream assignment

| Workstream | Primary files | Owner |
|-----------|---------------|-------|
| WS1: LangGraph runtime | `lib/agent/`, `lib/tutor-engine.ts`, `app/api/tutor/route.ts` | Lead |
| WS2: Cloudflare, persistence, identity | `db/`, `worker/`, `wrangler.toml`, `lib/repository.ts`, `lib/teacher-auth.ts`, `lib/request-user.ts` | Lead |
| WS3: Real product UI and E2E | `app/page.tsx`, `tests/e2e/` | Lead |
| WS4: Teaching integrity, scientific tools, evaluation | `lib/policy.ts`, `lib/verifiers.ts`, `lib/projects.ts`, `lib/citation-allowlist.ts` | Lead |

## File inventory

```
lib/
├── tutor-engine.ts        # WS1: Convert to LangGraph StateGraph
├── types.ts               # WS1: Extend with graph state/action types
├── providers.ts           # WS1/WS2: Fix USTC_API naming
├── policy.ts              # WS4: H0-H5 code enforcement
├── verifiers.ts           # WS4: Consolidate VerifierId type
├── retrieval.ts           # WS4: Already working, preserve
├── citation-allowlist.ts  # WS4: Already working, integrate into graph
├── repository.ts          # WS2: D1 persistence
├── teacher-auth.ts        # WS2: Fix secure cookie
├── request-user.ts        # WS2: Identity hardening
├── security.ts            # WS2: Already working
├── sandbox.ts             # WS4: Adapter interface exists
├── projects.ts            # WS4: Complete project implementations
├── runtime-env.ts         # WS2: Runtime bindings
└── course-knowledge.ts    # WS4: Generated from PDFs

app/
├── page.tsx               # WS3: Split into components, connect to real APIs
└── api/*/route.ts         # All: Fix auth, add routes

tests/
├── backend.test.ts        # All: Preserve, extend
├── validators-citations-auth.test.ts  # WS4: Preserve, extend
├── golden/eval.test.ts    # WS4: Preserve, extend
└── e2e/                   # WS3: Create from scratch

worker/
└── index.ts               # WS2: Verify LangGraph compatibility
```