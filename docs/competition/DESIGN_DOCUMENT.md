# Quantum Agent — Design Document

**Competition**: USTC "107 Cup" Computing and Agent Development Competition (Agent Track)
**Entry name**: Quantum Agent
**Product category**: Workflow-first, evidence-grounded quantum-physics teaching agent

## 1. Problem

Existing AI education tools are generic chatbots. When a student asks a quantum physics question, a chatbot may produce a fluent-sounding answer, but:
- It cannot cite a specific lecture slide or page.
- It may fabricate formulas, experimental values, or "standard results."
- It has no pedagogical policy — it either gives away the full solution or speaks too vaguely.
- It cannot verify whether a student's derivation or numerical result satisfies physical constraints.
- It offers no visibility for the teacher into what students are struggling with.

Quantum Agent solves this by making the LLM a **component** of a teaching workflow, not the workflow itself.

## 2. Architecture principle: workflow-first

The LLM writes explanations. Deterministic code controls:
- Which course pages the LLM may reference (`lib/retrieval.ts`)
- What hint level is appropriate (`lib/policy.ts`)
- Whether a model output cites a real lecture page (`lib/citation-allowlist.ts`)
- Whether a submitted matrix is Hermitian (`lib/verifiers.ts`)
- What model is called, with what key, with what timeout (`lib/providers.ts`)

The deterministic pipeline has 16 steps (`lib/tutor-engine.ts` `runTutorWorkflow`):
1. Input validation & safety checks
2. Capability and task classification
3. Conversation-state loading
4. Courseware retrieval
5. Citation allowlist construction
6. Misconception hypothesis generation
7. Pedagogical strategy selection (H1–H5)
8. Escalation check (injection, missing evidence)
9. Model generation (or deterministic fallback)
10. Scientific verification (when applicable)
11. Citation validation against allowlist
12. Answer-release policy gate
13. Response composition
14. Student-state update
15. Teacher trajectory recording
16. Analytics event recording

## 3. Evidence grounding

Every course citation resolves to a real PDF page. The system indexes 7 USTC lecture PDFs (737 pages, 726 page-level chunks) via a reproducible `pdftotext -layout` → `scripts/build-courseware-index.mjs` pipeline. Citations display chapter, page number, and the original PDF URL.

Three evidence categories are labeled in the UI:
- **课件依据** (courseware evidence) — from retrieved lecture pages
- **计算验证** (computational verification) — from deterministic validators
- **模型解释** (model explanation) — from the LLM, clearly distinguished

The model is **never** allowed to fabricate a citation. A post-processing allowlist (`lib/citation-allowlist.ts`) strips any model-generated citation whose ID is not in the retrieval results.

## 4. Pedagogical policy

- **H1–H5 hint levels**: H1 = minimal nudge, H5 = near-complete explanation. Course default cap: H3.
- **Answer-release policy gate**: The student's requested hint level is compared against course policy, prior attempts, and the answer-release ceiling.
- **Misconception diagnosis**: Keyword-based matching against a teacher-reviewable taxonomy (tunneling energy conservation, spin as classical rotation, non-degenerate perturbation on degenerate subspace, wavefunction as observable).
- **Escalation**: Prompt injection, policy conflicts, and missing evidence trigger automatic escalation to the TA queue.

The policy is enforced by deterministic code (`lib/policy.ts`), not by system prompts. The system prompt can advise; the gate code **enforces**.

## 5. Scientific verification

11 deterministic validators (`lib/verifiers.ts`): Hermiticity, normalization, probability conservation, commutator, boundary continuity, matrix symmetry, eigenvalue residual, dimensional consistency, numerical convergence, shape consistency, orthogonality.

Each result includes: tool name, pass/fail/inconclusive status, human-readable summary, machine-readable details, tolerance, inputs, timestamp, and `provenance: "deterministic"`. Results are persisted to D1 for audit.

## 6. Model routing (capability-based, not model-based)

Students choose **capabilities**, not models:
- 快速问答, 深度讲解, 图片识别, 图片深度推理, 编程实验

The server maps each capability to a USTC model (`lib/providers.ts`). The browser never sees model names, provider identities, API keys, or base URLs. This is verified by grep-checking the production bundle.

## 7. Teacher experience

- Aggregate misconception map, concept mastery overview, hint-level distribution, escalations queue
- Per-session trajectory replay with all trace nodes
- Server-side password gate (`lib/teacher-auth.ts`) — the frontend role toggle is a view switch, not an auth mechanism
- Anonymized data export

## 8. Distinctive design choices

| Generic chatbot | Quantum Agent |
|---|---|
| Model is the product | Model is a component of the workflow |
| No citation provenance | Every citation resolves to a real PDF page |
| No scientific checking | 11 deterministic validators |
| No pedagogical policy | H1–H5 hint levels enforced by code |
| Model selector exposed to user | Capability selector; models are server-only |
| Teacher has no visibility | Full trajectory replay, misconception map, escalation queue |
| Fallback is "sorry, an error occurred" | Deterministic fallback engine with full teaching structure |