# Quantum Agent

**可信量子物理教学智能体** — A workflow-first, evidence-grounded teaching agent for USTC quantum physics.

## What makes Quantum Agent different from ChatGPT

| ChatGPT | Quantum Agent |
|---|---|
| Model is the product | Model is a **component** of the teaching workflow |
| No citation provenance | Every citation resolves to a **real lecture PDF page** |
| No scientific checking | **11 deterministic validators** (Hermiticity, normalization, commutators, etc.) |
| No pedagogical policy | **H1–H5 hint levels** enforced by code, not prompts |
| Model selector exposed | **Capability selector** — students choose what they want to do, server chooses model |
| Teacher has no visibility | **Full trajectory replay**, misconception map, escalation queue |
| "Sorry, an error occurred" | **Deterministic fallback engine** with full teaching structure |

The LLM writes explanations. Deterministic code controls: teaching policy, evidence citations,
model routing, scientific validation, and persistence.

## What's included

- 7 lecture PDFs, 737 pages, 726 page-level retrieval chunks — each citation links to the original PDF page
- 5 teaching capabilities: 快速问答, 深度讲解, 图片识别, 图片深度推理, 编程实验
- Server-side USTC model routing — browser never sees API keys, base URLs, or real model names
- Misconception diagnosis, H1–H5 hint policy, course evidence vs. model explanation separation
- 11 deterministic scientific validators (Hermiticity, normalization, probability conservation, commutators, boundary continuity, matrix symmetry, eigenvalue residual, dimensional consistency, numerical convergence, shape consistency, orthogonality)
- 4 course projects with milestones, validators, and progress persistence
- Teacher dashboard with misconception map, TA queue, trajectory replay (password-protected)
- Deterministic fallback engine — works without any API key
- Privacy controls: data export, data deletion, minimal retention
- Image validation, rate limiting, prompt-injection boundaries, citation integrity checks

## Local development

```bash
npm ci
cp .env.example .env.local
npm run dev
```

Without `USTC_API_KEY`, the system uses the deterministic fallback engine — all teaching workflows still function with course-grounded responses.

## Test

```bash
npx tsc --noEmit          # typecheck
npm test                  # 28 tests (unit + golden eval + integration)
npm run lint              # eslint
npm run build             # production build
```

## API

See `docs/API.md` for the full API reference. Key endpoints:

- `POST /api/tutor` — Main teaching interaction
- `GET /api/capabilities` — Capability list (labels only, no model names)
- `POST /api/verify` — Scientific validators
- `GET /api/teacher/analytics` — Teacher dashboard (cookie-authenticated)
- `GET /api/health`, `GET /api/ready` — Health and readiness checks

## Deployment

See `docs/DEPLOYMENT.md`. Deploy to Cloudflare Workers: `npx vinext deploy`. Requires `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, D1 database binding, and `USTC_API` Worker secret.

## Privacy & security

- No API keys, base URLs, or model names in the frontend bundle
- Teacher data is password-protected (HMAC-signed cookies), not a frontend toggle
- Uploaded images are validated and forwarded only — never persisted
- Data export and deletion endpoints available
- Rate limiting, parameterized queries, attachment validation, prompt-injection boundaries
- See `docs/SECURITY.md` and `docs/PRIVACY.md`

## Documentation

| Document | Description |
|---|---|
| `docs/ARCHITECTURE.md` | Tutor turn pipeline, mode axes, course grounding |
| `docs/DEPLOYMENT.md` | Deploy instructions, secrets, smoke tests |
| `docs/SECURITY.md` | Security checklist |
| `docs/PRIVACY.md` | Data handling, retention, user rights |
| `docs/MODEL_ROUTING.md` | Capability-based model routing |
| `docs/SCIENTIFIC_VALIDATION.md` | 11 validators specification |
| `docs/TEACHING_POLICY.md` | Hint levels, misconception diagnosis, escalation |
| `docs/API.md` | Full API reference |
| `docs/REQUIREMENTS_TRACEABILITY.md` | PRD requirement mapping |
| `docs/OPERATIONS_RUNBOOK.md` | Health checks, incident response, maintenance |
| `docs/competition/DESIGN_DOCUMENT.md` | Competition design document |
| `docs/competition/JUDGING_CRITERIA_MAPPING.md` | Judging dimension mapping |
| `docs/competition/DEMO_SCRIPT_5MIN.md` | 5-minute live demo script |
| `docs/competition/KNOWN_LIMITATIONS.md` | Honest limitations |

## Competition

USTC "107 Cup" Computing and Agent Development Competition — Agent Track.

## License

No license. The 7 USTC courseware PDFs are private; publication rights have not been confirmed.
The GitHub repository is private.