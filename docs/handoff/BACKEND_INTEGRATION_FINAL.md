# Backend Integration — Final Handoff (Golden Loop V3.4)

**Date:** 2026-09-05
**Branch:** `main`
**Status:** See each section. LIVE E2E result and adversarial findings are appended at
the end once those runs complete.

---

## ROOT CAUSE

The user-reported bug — **"the frontend ends after I answer the first question"** —
was reproduced against the REAL `TutorGraph` (no mocks). The reproducible failure:

```
Turn 1  phase=commitment_required   commitment.gate_decision=attempt_required  accepted=false  required_action=commitment
Turn 2  (student submits a valid CommitmentCard)
        phase=commitment_required   commitment.accepted=true                    gate_decision=attempt_required
        required_action=commitment  learning_loop_completed=false               => NO visible control
```

Three backend/contract defects composed into this orphan state:

1. **Encoded dead-end phase hold** — `learning_native.py` allowed
   `COMMITMENT_REQUIRED → COMMITMENT_REQUIRED (commitment_accepted_but_phase_holds)`.
   So an accepted commitment never advanced the durable phase.
2. **Gate never disarmed after acceptance** — `decide_commitment` force-set
   `gate_decision=ATTEMPT_REQUIRED` even for an accepted commitment. The
   pre-generation node computed `withhold = (gate_decision is ATTEMPT_REQUIRED)`,
   so `answer_withheld_by_gate=True` routing the graph back through
   `prepare_commitment_gate` (skipping retrieve/diagnose/tools) again.
3. **Frontend hides the only card when accepted** — `LearningNativeSurface`
   renders the CommitmentCard only when `commitment.accepted===false`. The exact
   combination `phase=commitment_required + accepted=true + required_action=commitment`
   is therefore a machine state with **zero actionable UI**.

The old regression test `test_commitment_does_not_imply_episode_complete` **codified
the orphan** — it asserted the phase held at `commitment_required` with
`commitment.accepted=true`. It has been rewritten to assert the correct contract.

---

## FIX

The invariant the design intent required (accepting a commitment ≠ mastery, ≠ full
answer, ≠ episode complete) was being implemented as "hold forever + withhold".
The correct semantics: **an accepted commitment IS the student's initial
Attempt/Prediction** — the episode continues into Evidence → Diagnosis → Minimal
Intervention, with the student's commitment fed to Diagnosis as the attempt.

### Backend (`services/api/quantum_agent/`)

- `teaching/learning_native.py`
  - Removed `COMMITMENT_REQUIRED → COMMITMENT_REQUIRED (commitment_accepted_but_phase_holds)`
    from `_ALLOWED_PHASE_TRANSITIONS`.
  - Added `COMMITMENT_REQUIRED → ATTEMPT_RECEIVED (commitment_processed)`.
  - `_PHASE_TO_STAGE`/`_PHASE_TO_REQUIRED_ACTION` now map `ATTEMPT_RECEIVED` and
    `INTERVENTION` → `explain` / `revision`.
  - `decide_commitment`: an ACCEPTED submission now sets `gate_decision=PROCEED`
    (was ATTEMPT_REQUIRED) so the turn routes into real teaching work. The release
    engine still caps the envelope (the commitment becomes this turn's
    `student_attempt`; `commitment_eligibility` short-circuits on `has_current_attempt`).
  - New deterministic helpers `phase_is_actionable_next_step` and
    `suppress_gated_commitment_evidence`.
- `teaching/models.py`: added `minimal_intervention_prompt` to
  `LearningNativeTurnState` (the concrete probe the student must act on while the
  episode holds at `attempt_received`/`intervention`).
- `tutor/nodes.py`
  - `_COMMITMENT_SATISFIED_PHASES` now includes `ATTEMPT_RECEIVED` + `INTERVENTION`
    so the gate cannot re-arm on the next revision turn.
  - `learning_native_pre_node`: message→`student_attempt` promotion now covers the
    revision-bearing phases (`ATTEMPT_RECEIVED`/`INTERVENTION`/`AWAITING_REVISION`).
  - `learning_native_node`: adds the `commitment_processed` advance (phase →
    ATTEMPT_RECEIVED, completed_stages+PREDICT/DIAGNOSE/EXPLORE), disallows a bare
    `passed_verification` from advancing the phase on the commitment turn (invariant B),
    applies `suppress_gated_commitment_evidence`, and populates
    `minimal_intervention_prompt`.
  - `prepare_commitment_gate_node` / `generate_response_node`: an accepted
    commitment routed through the gate node now yields a deterministic
    acknowledgment + minimal-intervention next step (never re-asks for an invisible
    second commitment).
  - `assemble_result_node`: **NO-ORPHAN GUARD**. Every loop-required, incomplete,
    non-aborted turn must satisfy `phase_is_actionable_next_step`; otherwise the turn
    raises (fails closed) instead of returning an orphan result.

### Frontend (visual design preserved)

- `app/components/teaching/contracts.ts`: `LearningNativeTurnState` now parses
  `minimal_intervention_prompt`.
- `app/components/agent/LearningNative.tsx`: new `MinimalInterventionCard`
  (testid `minimal-intervention-card`) renders for `attempt_received`/`intervention`
  — a real free-text input for the next step. `hasLearningNativeAction` accepts it.
- `app/components/agent/AgentExperience.tsx`: `attempt_received`/`intervention`
  get an orienting stage title; `coding`/`sandbox`/`verification` progress labels
  added to the real SSE stage spine.
- `tests/e2e/golden-loop.spec.ts` + `tests/e2e/live/golden-loop-deterministic.spec.ts`:
  the mocked and live golden-loop sequences now reflect the REAL transcript
  (`commitment_required → attempt_received → awaiting_revision → …`), and the live
  spec asserts the accepted-commitment card, the no-orphan minimal intervention, and
  the real SSE ordering.

### Same-conversation mode switch (Golden Loop §6)

The durable phase sequence must run on ONE `conversation_id`. Two defects broke
this when the UI switched mode mid-loop (e.g. `learn_concepts → run_experiments`
for a Coding turn):

1. **Backend** — `TeachingRepository.start_turn` filtered the existing-conversation
   lookup by `mode == request.mode`, so a cross-mode turn raised
   `TeachingConversationConflictError` and the client re-created the conversation
   (re-firing the commitment gate, orphaning the durable phase).
2. **Frontend** — `AgentExperience` called `setConversationId(null)` on every mode
   switch, throwing away the live thread.

Fix (wiring only, no visual change):

- `services/api/quantum_agent/teaching/repository.py`: the existing-conversation
  lookup no longer filters by mode; ownership / course / edition / ACTIVE-status
  isolation is unchanged. When the request mode differs, `conversation.mode` is
  updated to the latest turn's mode (teacher trace summaries read
  `conversation.mode`).
- `app/components/agent/AgentExperience.tsx`: mode-rail buttons and command-palette
  mode items no longer clear `conversation_id`. Explicit new-thread actions
  (新建学习记录, command-palette new-record, course switch, 启动黄金学习循环) still
  clear it — starting a new thread is intentional.
- Regression: `tests/test_golden_loop_phase_sequence.py::test_mode_switch_continues_same_conversation`
  (a conversation seeded `awaiting_revision` under `LEARN_CONCEPTS` continues under
  a `RUN_EXPERIMENTS` turn; the gate does not re-arm; persisted mode follows the
  latest turn). `assertTeachingScope` still passes after continuation because
  `result.policy.mode` follows `request.mode`.

### Durable state restoration after refresh (§13)

After a page reload the frontend previously restored only `conversation_id` from
localStorage; the actionable surface (phase card, learning-native state) was absent
until the next turn ran. The backend is authoritative, so restoration reads from it:

- **Backend** — new `GET /api/v1/courses/{course_id}/editions/{id}/teaching/threads/{conversation_id}/state`
  (`services/api/quantum_agent/api/teaching.py`). Returns the conversation's
  current `mode`/`status`, the durable `LearningPhase`
  (`teaching_conversations.learning_phase_json`), and the last completed turn's
  persisted `__result_snapshot` (the full `TeachingTurnResult`, including
  `learning_native`). 404 for a conversation not owned by this
  course/edition/student — never a synthetic default that would let a stale
  client skip forward.
- **BFF** — new `app/api/teaching/threads/[conversationId]/state/route.ts`,
  mirroring the interrupt route: same-origin check, UUID scope, student session
  token, bounded payload, result snapshot parsed with `parseTeachingTurnResult`
  + evidence-digest verification + conversation-id stability before it reaches
  the browser.
- **Frontend** — `AgentExperience` re-reads the state endpoint once per restored
  conversation (after the `conversation_id` is restored from localStorage) and
  re-renders `result` (including the phase card) and the conversation's mode.
  A restore never overrides a result already rendered in the session; a 404
  simply means the thread no longer exists.
- **Tests** — `tests/test_teaching_api.py::test_conversation_state_restores_durable_phase_after_refresh`
  asserts the endpoint returns the durable phase (`commitment_required` after the
  gate fires) and a snapshot identical to the live turn's response/policy; 404 for
  unknown conversations; 401 unauthenticated. The live spec's Stage 4.5 now
  asserts `[data-testid="learning-phase"]` shows `awaiting_revision` after
  `page.reload()` without a new turn.

---

## AUTHORITATIVE PHASE MACHINE

```
OPEN
 → COMMITMENT_REQUIRED               gate_fired
 → ATTEMPT_RECEIVED                  commitment_processed   (accepted commitment = initial attempt)
 → AWAITING_REVISION                 verified_attempt        (revised attempt / verified signal / advance)
 → RECONSTRUCTION_REQUIRED           teach_back_requested
 → TRANSFER_REQUIRED                 teach_back_verified
 → SOLO_ACTIVE                       transfer_armed
 → COMPLETE                          solo_verified
 (→ ABORTED                          student_exit)
```

Legal same-phase holds: `teach_back_rejected` (reconstruction), `transfer_rearmed`,
and generic `blocked`. The old `commitment_accepted_but_phase_holds` edge is **gone**.

No-orphan invariant (enforced in `assemble_result_node`):
> For every `TeachingTurnResult`, if `learning_native.loop_required == true` and
> `learning_loop_completed == false` and `phase != aborted`, the result MUST expose
> exactly one valid next student action (commitment card / minimal-intervention card /
> teach-back / transfer / solo / revision composer).

---

## ROUTING MATRIX (representative USTC course questions)

| # | Question type | Mode | Gate? | Evidence | Tools/Coding | Release | Result |
|---|---|---|---|---|---|---|---|
| A | "什么是厄米算符？" factual | learn_concepts | bypassed (factual marker) | retrieved | no | full_explanation | grounded claim |
| B | conceptual "为什么基态平均动量为零？" | learn_concepts | gate → commitment | after commit | no | minimal | continues |
| B | misconception "波函数是不是概率？" | learn_concepts | satisfied by attempt | retrieved | no | scaffold | diagnosis + hints |
| C | derivation (student supplies steps with error) | review_derivations | satisfied (attempt) | retrieved | symbolic | scaffold | first-error localization |
| D | skipped-step derivation | learn_concepts | gate → after commit | retrieved | no | scaffold | prerequisite bridge |
| E | scientific tunnelling T | run_experiments | gate → after commit | retrieved | oracle + coding | scaffold | T/R + verifier PASS |
| E | two-level/Rabi | run_experiments | gate → after commit | retrieved | oracle only | scaffold | plot + conservation |
| F | insufficient evidence | learn_concepts | satisfied (attempt) | NOT_FOUND | no | question_only | INSUFFICIENT_COURSE_EVIDENCE, zero claims |
| G | multimodal handwritten derivation | review_derivations | deferred until HITL confirm | retrieved after | symbolic | per policy | same-thread confirmation |

General model: the workflow adapts to the task; the Golden-Loop full sequence runs
only when the durable phase + mode require it. A definition lookup never forces the
commitment card.

---

## TEST RESULTS

| Gate | Result |
|---|---|
| Backend pytest (full) | **358 passed, 2 skipped (live-gated), 0 failed** |
| `tests/test_contract_v34.py` (new no-orphan + generalization matrix) | **14 passed** |
| `tests/test_golden_loop_phase_sequence.py` | **24 passed** (incl. cross-mode continuation + degenerate teach-back analysis) |
| `tests/test_teaching_api.py` | **4 passed** (incl. state-endpoint refresh restoration + transfer-oracle redaction) |
| ruff | **All checks passed** |
| mypy | **Success: no issues in 73 source files** |
| `npx tsc --noEmit` | **clean** |
| `npm run test:unit` | **70 passed** |
| `npm run lint` | **0 errors** (6 pre-existing warnings) |
| `npm run build` (+ validate-artifact) | **passes** |
| Mocked Playwright `golden-loop.spec.ts` + `learning-native.spec.ts` | **4 passed** |
| BFF SSE validator tests | **12 passed** |

### REAL (live, full-stack) Golden Loop

*Stack:* Docker Compose (postgres/pgvector, neo4j, redis, api :8000, sandbox-runner,
web :3000) + real USTC model gateway + real published course corpus.
*Proof:* the run reaches `phase=complete` with `learning_loop_completed=true` through
normal UI interaction and persists every durable phase between turns (same
`conversation_id`).

**Deterministic live phase transcript — REAL stack, REAL USTC model, ONE conversation
(`scripts/live-loop-proof.mjs`, ~641s):**
```
[1] open      → phase=commitment_required     action=commitment
[2] commit    → phase=attempt_received        action=revision   loopComplete=false   ← THE FIX
[3] revise    → phase=awaiting_revision       action=revision
[4] scientific→ phase=awaiting_revision       codeArtifact=true                     ← real Coding Agent + sandbox
[5] tb-req    → phase=awaiting_revision       action=revision
[6] tb-sub    → phase=reconstruction_required action=teach_back
[6.5] tb-resub→ phase=transfer_required       (teach_back_verified)
[7] transfer  → phase=solo_active             action=solo_attempt  transfer verifiable=true
[8] solo      → phase=complete                loopComplete=true    solo=exited        ← LOOP CLOSED
```

### Live E2E result (DONE)

The backend Golden Loop reaches `phase=complete` with `learning_loop_completed=true`
through the real FastAPI → TutorGraph → PostgreSQL → Coding Agent → Sandbox →
Scientific Verifier path, every turn on the same `conversation_id`, with the real
USTC `glm-5.2` model, in ~641s for the full 8-turn loop (`scripts/live-loop-proof.mjs`).

The in-browser live Playwright suite (`tests/e2e/live/`, real stack + real USTC model)
drives the same loop through the frozen UI. Two earlier run failures were diagnosed
against the persisted DB trace and fixed:

1. **Stage 4.5 refresh restore silently aborted** — the §13 state-restore effect in
   `AgentExperience.tsx` depended on the `scope` object, which is a NEW identity
   every render, so the effect cleanup's `AbortController.abort()` killed the
   in-flight `GET /teaching/threads/{id}/state` fetch before its response was
   applied (the server logged the 200; the browser never re-rendered the phase
   card). Both restore effects (state + HITL interrupt recovery) now capture the
   scope primitives and do not abort on scope re-identity; the once-per-
   conversation ref makes re-entry impossible, and the apply is a functional
   `setResult((current) => current ?? restored)` so an in-flight fetch can never
   overwrite a fresher turn.
2. **golden-loop-live teach-back sequence** — the spec submitted the reconstruction
   once (advancing `reconstruction_required`, cause `teach_back_requested`) and then
   expected the transfer button. The durable phase only reaches
   `transfer_required` when the reconstruction is RE-SUBMITTED from
   `RECONSTRUCTION_REQUIRED` and verified (`teach_back_verified`) — the same
   two-step contract the deterministic spec asserts at its Stages 11-12. The spec
   now re-submits and waits for the transfer button, and the stale
   `agent-live` assertions (the old workspace title `推导工作台` and the
   `model-service-status` chip, both removed by the frozen-UI commits a81d4c4 +
   7b4113f) were updated to the frozen UI's actual contract (stage heading
   `首错定位` + `evidence-spine`).
3. **Teach-back degenerate model analysis deadlocked the loop** — a live USTC
   round-trip produced an entirely empty analysis (covered=0/missing=0/
   contradictions=0/unsupported=0) on a 50-char reconstruction; the gate failed
   closed and the fallback only covered `proposal is None` (model unavailable) —
   and the old 120-char fallback bar meant a 50-char reconstruction could never
   qualify even then. Fixed in `tutor/nodes.py`: the degenerate-empty analysis on a
   substantial reconstruction (>= 24 chars, the analysis-entry bar) now advances
   deterministically, exactly like the model-unavailable fallback — a model outage
   or degeneration cannot deadlock the Golden Loop. Two regression tests added
   (`test_degenerate_empty_analysis_does_not_deadlock_the_loop`,
   `test_degenerate_empty_analysis_short_reconstruction_still_holds`).
4. **agent-live strict-mode violation** — `getByRole('button', {name: '打开证据面板'})`
   resolves to 2 elements in the frozen UI (topbar + left rail); the spec now scopes
   to `page.getByRole("banner")`.

---

## KNOWN LIMITATIONS / REMAINING RISKS

- **Live full-loop run duration**: each real USTC model turn takes ~1-3 min; the full
  22-stage live loop takes ~20-30 min. It is not part of the default CI because the
  live stack + `USTC_API` are required (matching the repo's frozen design).
- **Refresh mid-phase UI**: FIXED (§13). After a page reload during ANY durable
  phase, the frontend re-reads the durable state from
  `GET /teaching/threads/{id}/state` and re-renders the actionable surface. See the
  "Durable state restoration after refresh" section above.
- **Coding Agent SSE granularity**: the `scientific_tools` stage label is emitted by
  the real SSE stream; finer `coding.started / sandbox.started / verification.*`
  sub-stages are NOT emitted as separate SSE events (the honest run detail is in the
  `RUN_SCIENTIFIC_TOOLS` trace step and the `code_artifact`), matching the guidance
  "no fake timers / no frontend-invented progress."
- **`_attempt_verified` tolerance**: the numeric Solo verifier accepts any number in
  the free text within `absolute_tolerance` (5e-3) plus a correlated oracle PASS; this
  is the documented, by-design most-permissive link (an independent computation
  matching the changed-parameter oracle).
- **Malformed scientific_request**: survives API pydantic validation only as a
  typed-union member; a kind-mismatched dict in a stale `pending_scientific_request`
  would raise in `validate_request` (fails the turn rather than degrading). No
  path produces it via the UI.

## ADVERSARIAL REVIEW

Two independent fresh review agents probed the fixed loop. Findings and disposition:

### Round 1

1. **P0 claim (skip teach-back/transfer via `request_transfer_task`)** — narrowed:
   reaching `TRANSFER_REQUIRED` still requires `teach_back_verified`, and the branch-1
   `verified_attempt` advance still requires a meaningful student attempt. To harden,
   `explicit_advance` is now gated to the pedagogically legal phase for each flag
   (`request_teach_back` only from `AWAITING_REVISION`, `request_transfer_task` only
   from `TRANSFER_REQUIRED`) — applied in `nodes.py`.
2. **P0 claim (unsound no-orphan guard)** — rejected: at `AWAITING_REVISION` the
   teach-back button always renders (there is no completed-stage path where
   `teach_back` is in `completed_stages` while the phase is still `awaiting_revision`),
   and the composer is always an actionable fallback.
3. **P1 (release counting on commit turn)** — acceptable by design: the accepted
   commitment becomes this turn's attempt and the release stays at the
   minimal-intervention envelope.
4. **P2 (refresh loses UI card)** — FIXED. The §13 restore effect silently
   aborted its fetch on scope re-identity (see the Live E2E result section,
   failure 1); both restore effects no longer abort and the apply is
   conflict-safe.

### Round 2 (final, merge-blocking finding fixed)

1. **P0 — transfer-oracle answer leaked via `durable_phase` in the state
   endpoint. CONFIRMED + FIXED (merge blocker).**
   `GET /teaching/threads/{id}/state` returned `durable_phase.model_dump()`
   verbatim, including `transfer_verification.expected_value` — the numerically
   correct transmission coefficient the student must derive themselves during
   Solo Mode. A student reading the raw payload (browser devtools) could copy it
   into the solo attempt and close the loop with zero physics done. The streaming
   path never exposed this field. Fix: the state endpoint redacts
   `transfer_verification` from the student-facing payload
   (`api/teaching.py`, `student_durable_phase`), the BFF strips it again as
   defense-in-depth (`app/api/teaching/threads/[conversationId]/state/route.ts`),
   and a regression test asserts the redacted payload
   (`test_conversation_state_redacts_transfer_oracle`).
2. **P1 — restore effect aborted by dependency instability. CONFIRMED + already
   fixed** by the Live-E2E failure-1 fix (no AbortController, primitive capture,
   once-per-conversation ref, functional `setResult` guard).
3. **P1 — stale `result` closure lets the restore overwrite a newer in-session
   result. CONFIRMED + already fixed** by the same functional guard.
4. **P2 — BFF state route validates less than the interrupt route. CONFIRMED +
   FIXED**: the BFF now scope-asserts the embedded result
   (`assertTeachingScope`) exactly like the streaming terminal path, and strips
   the transfer oracle at the edge.
5. **P2 — tautological mode check on restore.** CONFIRMED, acceptable: it mirrors
   the pre-existing interrupt pattern; the course/edition assertions remain
   meaningful.
6. **P2 — historical trace mislabeling after mid-loop mode switch.** CONFIRMED,
   accepted as a known limitation: `TeachingTurn` stores no per-turn mode; fixing
   it requires a schema migration and does not affect any gate or invariant
   (labels only).
7. **P2 — idempotent replay silently rewrites `conversation.mode`. CONFIRMED +
   FIXED**: the mode mutation in `TeachingRepository.start_turn` now happens only
   after the `client_request_id` replay check, so a replay returns the turn in
   the state it was stored and can never commit a mode change.

**Verified non-issues (round 2):** cross-student/course/edition isolation on
`start_turn` and the state endpoint; policy resolution fail-closed safe default;
commitment/teach-back/Solo gates phase-driven; SSE `CONVERSATION_CONFLICT`
contract reachable; `is not` enum identity works for Pydantic-parsed and
SQLAlchemy-hydrated members; no credentials or chain-of-thought in the snapshot.

## COMMIT SHA

`19e8726` (fix(backend): accepted commitment continues the Golden Loop, no orphan state)
— updated below after the final commit.
