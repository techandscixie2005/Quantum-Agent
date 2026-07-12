# Quantum Agent — CLAUDE.md

Quantum Agent is a workflow-first, evidence-grounded quantum-physics teaching agent for the USTC "107 Cup" Agent Track competition. It is **not** a generic chatbot. The LLM writes explanations; deterministic code controls teaching policy, evidence, model routing, scientific validation, and persistence.

## Quick reference

```bash
npm run install:ci          # install dependencies (uses sites-env.sh wrapper)
npm run dev                 # start dev server (vite)
npm run build               # production build (vinext build + validate-artifact.sh)
npm start                   # start production server (vinext start)
npm test                    # full test suite
npm run lint                # eslint
npx tsc --noEmit            # typecheck
node scripts/build-courseware-index.mjs  # rebuild courseware index
```

## Architecture

- **Framework**: Next.js 16 on Vite via `vinext` (v0.0.50), deployed to Cloudflare Workers via `@cloudflare/vite-plugin`.
- **Database**: Cloudflare D1 (binding name `DB`), accessed via Drizzle ORM.
- **Auth**: ChatGPT Sign-In headers (`oai-authenticated-user-*`) in the worker environment; teacher dashboard uses a server-side password gate (`lib/teacher-auth.ts`).
- **Frontend**: Single-page React app (`app/page.tsx`) with three-column teaching workbench, capability-based model selection.

## Key directories

| Path | Purpose |
|---|---|
| `app/page.tsx` | Full frontend (student workspace + teacher dashboard) |
| `app/api/*/route.ts` | API routes (tutor, capabilities, verify, teacher/analytics, etc.) |
| `lib/tutor-engine.ts` | Deterministic orchestration pipeline (16-step workflow) |
| `lib/providers.ts` | Server-side model routing, capability catalog, USTC adapter |
| `lib/verifiers.ts` | Deterministic scientific validators (11 tools) |
| `lib/retrieval.ts` | Hybrid lexical retrieval over 726 page-aware chunks |
| `lib/policy.ts` | Misconception taxonomy, hint policy, escalation rules |
| `lib/security.ts` | Attachment validation, in-memory rate limiting |
| `lib/repository.ts` | D1 persistence for sessions, turns, states, projects, escalations |
| `lib/citation-allowlist.ts` | Post-processing strip of fabricated citations |
| `lib/teacher-auth.ts` | HMAC-signed cookie sessions for teacher access |
| `db/schema.ts` | Drizzle schema (11 tables) |
| `worker/index.ts` | Cloudflare Worker entry point |
| `scripts/build-courseware-index.mjs` | Reproducible page-aware courseware ingestion |

## Model routing

The browser sends only a capability ID (`quick`, `deep`, `vision`, `vision-reasoner`, `code`). `lib/providers.ts` resolves it server-side to a USTC model. Public APIs expose only Chinese labels (快速问答, 深度讲解, etc.). Real model names are never sent to the frontend.

## Testing

Tests are deterministic and use demo/mock providers (no real API tokens). The golden eval set (`tests/golden/eval.json`) covers 12 scenarios with invariant assertions. Run with:

```bash
node --import tsx/esm --test tests/backend.test.ts tests/validators-citations-auth.test.ts tests/golden/eval.test.ts
```

## Deployment

`vinext deploy` to Cloudflare Workers. Requires `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and the D1 database binding. Set `USTC_API` as a Cloudflare Worker secret and `TEACHER_PASSWORD` as a Worker secret for teacher dashboard access. See `docs/DEPLOYMENT.md`.

## Security notes

- Never commit `.env*` files (except `.env.example`).
- Never hardcode `USTC_API`, model names, or endpoint URLs in the frontend.
- The client build must not contain `deepseek`, `qwen`, `glm`, `api.llm.ustc.edu.cn`, or `sk-` patterns.
- Teacher analytics require a server-side password cookie; the frontend role toggle is a view switch, not an auth mechanism.
- Image attachments: ≤3 files, ≤5 MB each, ≤10 MB total, allowed MIME types only, validated base64, never persisted.