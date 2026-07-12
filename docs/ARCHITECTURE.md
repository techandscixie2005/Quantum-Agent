# Architecture

Quantum Agent follows one rule: **the model writes explanations; the workflow controls teaching and evidence**.

## Tutor Turn

1. `TASK_CLASSIFIER` combines the pedagogical workspace and capability mode.
2. `MISCONCEPTION_DIAGNOSER` matches a teacher-reviewable misconception taxonomy.
3. `COURSE_RETRIEVAL` runs hybrid lexical retrieval over 726 page-aware chunks plus published teacher additions.
4. `POLICY_GATE` caps answer release at the course hint ceiling.
5. `HUMAN_ESCALATION` activates on missing evidence, policy conflict, or injection-like requests.
6. `MODEL_GENERATION` calls a server-selected capability route and requires a six-field JSON teaching response.
7. Invalid JSON, timeout, missing key, or provider failure activates deterministic fallback.
8. `RESPONSE_ASSEMBLER` separates course evidence, deterministic tool output, model inference, and teacher evidence.
9. D1 stores the session, turns, actual internal model audit fields, trace, student state, project state and escalation.

## Two independent mode axes

- Pedagogical workspaces: concept, derivation, experiment, project.
- Compute capabilities: quick, deep, vision, vision-reasoner, code.

The browser sends only a capability ID. `lib/providers.ts` resolves that ID to a server-side provider, endpoint, model and token budget. The public response returns only the capability label and whether an API or deterministic fallback was used.

## Course grounding

`scripts/build-courseware-index.mjs` converts page-preserving `pdftotext -layout` output into `lib/courseware.generated.json`. Each chunk records source ID, chapter, PDF page, source URL, keywords and checksum-backed manifest identity. `public/courseware/` contains the exact PDFs referenced by the citations.

The retriever requires a meaningful lexical match. An uncovered topic returns zero citations and triggers escalation; it does not manufacture a nearby page reference.

## Scientific verification

`POST /api/verify` exposes bounded deterministic checks for Hermiticity, normalization, probability conservation, commutators and boundary continuity. LLM text never changes their pass/fail result.

Arbitrary Python is outside the web worker. `/api/sandbox` performs a deny-list preflight and delegates only to an independently isolated, network-disabled execution service. If that service is absent, the endpoint fails closed.

## Data ownership

- Source and public artifacts contain no secrets.
- Hosted secrets are runtime variables.
- D1 stores structured learning records.
- Image attachments are validated, sent to the selected model for the current turn, and are not persisted by the application.
- Teacher analytics are learning-intervention signals, not student ranking.
