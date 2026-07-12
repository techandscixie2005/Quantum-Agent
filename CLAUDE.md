# Quantum Agent — CLAUDE.md

Quantum Agent is a workflow-first, evidence-grounded quantum-physics teaching agent for the USTC "107 Cup" Agent Track competition. It is **not** a generic chatbot. The LLM writes explanations; deterministic code controls teaching policy, evidence, model routing, scientific validation, and persistence.

Orchestration is now managed by **LangGraph.js** with a multi-node `StateGraph`.

## Quick reference

```bash
npm run install:ci          # install dependencies (uses sites-env.sh wrapper)
npm run dev                 # start dev server (vite)
npm run build               # production build (vinext build + validate-artifact.sh)
npm start                   # start production server (vinext start)
npm test                    # full test suite (unit + golden eval + integ + build)
npm run test:unit           # unit + golden eval tests only
npm run test:e2e            # Playwright E2E tests
npm run test:security       # security tests
npm run lint                # eslint
npx tsc --noEmit            # typecheck
npm run eval:simulated-students  # simulated student evaluation
npm run check:secrets       # check client bundle for leaked secrets
node scripts/build-courseware-index.mjs  # rebuild courseware index
```

## Architecture

- **Orchestration**: LangGraph.js `StateGraph` (`lib/agent/`) with 18 nodes, conditional routing, subgraphs for pedagogical modes, and `interrupt()` for teacher review.
- **Framework**: Next.js 16 on Vite via `vinext` (v0.0.50), deployed to Cloudflare Workers via `@cloudflare/vite-plugin`.
- **Database**: Cloudflare D1 (binding name `DB`), accessed via Drizzle ORM.
- **Auth**: Cloudflare Access in production (`Cf-Access-Authenticated-User-Email`); isolated local dev identity. Teacher dashboard uses HMAC-signed cookies (`lib/teacher-auth.ts`).
- **Frontend**: Single-page React app (`app/page.tsx`) with three-column teaching workbench, capability-based model selection, and real API connections.
- **Scientific computation**: Crank-Nicolson wavepacket simulation (`lib/simulation.ts`), hydrogen orbitals (`lib/hydrogen.ts`), helium variational (`lib/helium.ts`), diatomic MO (`lib/diatomic.ts`).

## Key directories

| Path | Purpose |
|---|---|
| `app/page.tsx` | Full frontend (student workspace + teacher dashboard) |
| `app/api/*/route.ts` | 20 API routes (tutor, capabilities, verify, simulate, projects, evaluation, etc.) |
| `lib/agent/` | **LangGraph.js StateGraph** — state, graph, contracts, routing, nodes, subgraphs |
| `lib/agent/state.ts` | TutorStateSchema with Zod v4 |
| `lib/agent/graph.ts` | Compiled `tutorGraph` with 18 nodes + conditional routing |
| `lib/agent/nodes/` | Node implementations (preprocessing, policy, retrieval, tools, generation, verification, escalation, output) |
| `lib/agent/subgraphs/` | Pedagogical subgraphs (concept, derivation, vision, code, experiment, project) |
| `lib/agent/routing.ts` | Conditional edge routing functions |
| `lib/agent/contracts.ts` | Pedagogical actions, HINT_LEVEL_ACTIONS, policy constants |
| `lib/providers.ts` | Server-side model routing, capability catalog, USTC adapter |
| `lib/verifiers.ts` | Deterministic scientific validators (11 tools) |
| `lib/retrieval.ts` | Hybrid lexical retrieval over 726 page-aware chunks |
| `lib/policy.ts` | Misconception taxonomy, hint policy, escalation rules |
| `lib/security.ts` | Attachment validation, in-memory rate limiting |
| `lib/repository.ts` | D1 persistence for sessions, turns, states, projects, escalations |
| `lib/citation-allowlist.ts` | Post-processing strip of fabricated citations |
| `lib/teacher-auth.ts` | HMAC-signed cookie sessions for teacher access |
| `lib/simulation.ts` | Crank-Nicolson wavepacket tunneling simulation |
| `lib/evaluation.ts` | Simulated student personas, mentor rubric, episode runner |
| `db/schema.ts` | Drizzle schema (11 tables) |
| `worker/index.ts` | Cloudflare Worker entry point |
| `tests/e2e/` | 8 Playwright E2E test specs |
| `scripts/evaluate.ts` | Simulated student evaluation CLI |
| `scripts/check-secrets.sh` | Client bundle secret scanner |
| `scripts/build-courseware-index.mjs` | Reproducible page-aware courseware ingestion |

## LangGraph tutor graph

```
START → authenticate → loadCourse → classifyTask → diagnose
         ↓ (conditional)
    applyPolicy → retrieveEvidence → generateDraft
         ↓ (conditional)              ↓ (conditional)
    runTools → verifyScientific → enforceCitations → assessRisk
                                                        ↓ (conditional)
                                              interruptForReview → assembleResponse → END
```

See `docs/implementation/LANGGRAPH_DECISIONS.md` for all design decisions.

## Model routing

The browser sends only a capability ID (`quick`, `deep`, `vision`, `vision-reasoner`, `code`). `lib/providers.ts` resolves it server-side to a USTC model. Public APIs expose only Chinese labels (快速问答, 深度讲解, etc.). Real model names are never sent to the frontend.

Single credential: `USTC_API` — loaded from Worker secrets or `.env.local`.

## Testing

```bash
npm run test:unit     # 28 unit/golden eval tests (deterministic, no API tokens)
npm run test:e2e      # Playwright E2E tests (requires dev server)
npm run test:security # Security-focused tests
npm run build         # Production build (includes validate-artifact.sh)
npm run check:secrets # Check client bundle for leaked secrets
```

The golden eval set (`tests/golden/eval.json`) covers 12 scenarios with invariant assertions.

## Deployment

`vinext deploy` to Cloudflare Workers. Requires `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and the D1 database binding. Set `USTC_API` as a Cloudflare Worker secret and `TEACHER_PASSWORD` as a Worker secret for teacher dashboard access. See `docs/DEPLOYMENT.md`.

## Security notes

- Never commit `.env*` files (except `.env.example`).
- Never hardcode `USTC_API`, model names, or endpoint URLs in the frontend.
- The client build must not contain `deepseek`, `qwen`, `glm`, `api.llm.ustc.edu.cn`, or `sk-` patterns.
- Production identity uses `Cf-Access-Authenticated-User-Email` from Cloudflare Access, not raw `oai-authenticated-user-*` headers.
- Teacher analytics require a server-side password cookie (`Secure; HttpOnly; SameSite=Strict`); the frontend role toggle is a view switch, not an auth mechanism.
- Image attachments: ≤3 files, ≤5 MB each, ≤10 MB total, allowed MIME types only, validated base64, never persisted.
- Run `npm run check:secrets` after every build to verify no secrets leaked into the client bundle.