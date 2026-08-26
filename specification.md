## VERDICT: DO NOT FREEZE

### 1. Executive assessment

The repository is clean at `806de6d58b2680ca86493396d6ab569a01ab649c`, and `HEAD`, `main`, and `origin/main` all match. The expected remote is configured. I made no repository changes.

The claimed LangGraph ordering is substantially accurate. `learning_native_pre` executes before `scientific_tools` and `generate_response`; when `answer_withheld_by_gate=True`, the response-composition LLM is genuinely skipped and zero claims are returned.

That guarantee applies only to a narrow branch. Ordinary `learn_concepts` questions are classified as concept questions and receive `FULL_EXPLANATION` without a commitment. Gate enforcement also fails open if the commitment-prompt model is unavailable. Even where the gate fires, the response still contains targeted retrieved excerpts which the frontend immediately displays.

The broader Learning-Native loop is not an implemented pedagogical state machine. Teach-Back and Transfer exist as backend submission types and UI cards, but the production UI never initiates them. Solo Mode is restored after response generation, can be exited explicitly without completion, and is lost by the frontend on refresh/new thread.

The advertised tunnelling Golden Loop is not scientifically implemented. The authoritative Python toolbox has no barrier/tunnelling simulation. The experiment UI always submits a two-level Rabi simulation. The deterministic E2E fabricates tunnelling values, while the live test sends no scientific request and never asserts a scientific result.

The live Golden test contains no `page.route`, `page.fulfill`, HAR, or first-party interception, so it is genuinely non-mocked at the transport level. Its pedagogical assertions, however, are adaptive or absent. It proves real requests and some PostgreSQL writes, not the stated full loop.

Fresh checks passed: 215 Python tests with 2 live skips, Ruff, strict mypy, strict TypeScript, and 57 frontend unit tests. Those results support confidence in contracts, schema validation, authorization, and several deterministic tools, but not the competition-critical Learning-Native or tunnelling claims.

### 2. Confirmed strengths

- The graph topology is fixed in code and not model-directed: [graph.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/graph.py:106), lines 106–145.
- The narrow commitment-withheld branch genuinely skips `compose_grounded_teaching_response`: [nodes.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/nodes.py:375), lines 375–463.
- The answer-release engine is deterministic once its inputs have been selected.
- Authoritative FastAPI endpoints use opaque, hashed sessions with active user and course-membership checks: [auth.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/auth.py:66), lines 66–145.
- Teaching conversations, trace access, HITL inspection, and attachment access are scoped by user/course/edition. I found no IDOR in the authoritative Python routes.
- Turn completion, `AgentTrace`, and `LearningEvidence` writes occur in one SQL transaction, with per-turn duplicate protection: [repository.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/repository.py:389), lines 389–568.
- Hybrid retrieval uses deterministic reciprocal-rank fusion and records degraded channels: [retrieval.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/knowledge/retrieval.py:997), lines 997–1134; [fusion.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/knowledge/fusion.py:42), lines 42–94.
- Symbolic equivalence/residual, normalization, unitarity, and two-level QuTiP simulation paths are deterministic and typed.
- The desktop and mobile presentation is visually polished and distinctly resembles a scientific learning workspace rather than a generic chat interface.
- PostgreSQL, Neo4j, Redis, API, and web containers were healthy during review. The API readiness endpoint reported PostgreSQL ready.
- The bundle secret scan passed, no source maps or Playwright trace archives were present, and a filename-only history scan found no matching high-entropy bearer/key patterns.

### 3. Findings

#### P0 — Freeze blockers

**P0-1 — The Commitment Gate is not authoritative for normal concept learning, and withheld content can leak through evidence.**

- **Affected behavior:** A student can directly ask a normal concept question without attempting it and receive a full explanation. Gate availability also depends on a successful model-generated prompt. When the gate does fire, exact retrieved excerpts remain visible.
- **Files and symbols:**
  - `AnswerReleaseEngine.decide`: [policy.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/policy.py:83), lines 83–111.
  - `_deterministic_task_kind` and `interpret_turn`: [state_machine.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/state_machine.py:54), lines 54–64 and 208–244.
  - `LearningNativePolicy.decide_commitment` and `propose_commitment`: [learning_native.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/learning_native.py:168), lines 168–223 and 720–758.
  - Pre-gate and response generation: [nodes.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/nodes.py:316), lines 316–463.
  - Unredacted result assembly: [nodes.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/nodes.py:702), lines 702–715.
  - Evidence carries full chunks and snippets: [retrieval.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/knowledge/retrieval.py:172), lines 172–238.
  - Frontend displays them unconditionally: [AgentExperience.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/AgentExperience.tsx:681), lines 681–688 and 938–959.
- **Why it matters:** This contradicts the principal competition claim that suitable questions require learner generation before AI completion. The model-generated task class is also an input to release policy: choosing `CONCEPT_QUESTION` rather than `EXERCISE_HELP` materially changes answer release.
- **Evidence:** `LEARN_CONCEPTS + CONCEPT_QUESTION` unconditionally returns `FULL_EXPLANATION`. A missing commitment proposal returns `PROCEED`. A submitted attempt of any non-empty length satisfies the pre-gate. Retrieved exact snippets survive in the serialized student result.
- **Minimal fix:** Make commitment eligibility a deterministic pedagogical decision independent of the release level or model availability. Supply a deterministic fallback prompt. Redact snippets/full chunks from the student response while withholding is active. Require a minimally meaningful, typed commitment rather than merely non-null input.
- **Should a test have caught it?** Yes. The zero-compose test covers only `RUN_EXPERIMENTS` with a successful proposal: [test_learning_native.py](/home/xiangyu_xie/QuantumAgent/services/api/tests/test_learning_native.py:787), lines 787–854. Another test explicitly confirms that an ordinary concept question proceeds without a model: lines 522–554.

**P0-2 — Teach-Back, Transfer, and Solo do not form an enforceable end-to-end learning loop.**

- **Affected behavior:** The normal UI cannot initiate Teach-Back or Transfer; natural-language requests do not populate their structured submissions. Once Solo is active, a second normal request can receive an LLM response before the backend restores the Solo lock. Refreshing or starting a new thread escapes the lock. Any non-empty attempt, or an explicit exit, ends Solo regardless of correctness.
- **Files and symbols:**
  - Declared but unused phase actions: [models.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/models.py:565), lines 565–575.
  - Backend only reacts to already-structured submissions: [nodes.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/nodes.py:852), lines 852–927.
  - Solo restoration occurs post-generation: [nodes.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/nodes.py:871), lines 871–902.
  - Solo exits after any non-empty response: [learning_native.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/learning_native.py:458), lines 458–522.
  - All UI submissions set `request_transfer:false`; none set it true: [LearningNative.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/LearningNative.tsx:73), lines 73–91, 179–190, and 263–286.
  - Cards only render after the corresponding state already exists: [LearningNative.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/LearningNative.tsx:437), lines 437–508.
  - Conversation and Solo continuity are component-local; the normal composer remains enabled: [AgentExperience.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/AgentExperience.tsx:393), lines 393–400 and 871–925.
- **Why it matters:** The product is currently an answer pipeline with optional structured API features, not the claimed `COMMIT → … → TRANSFER` state machine. Solo Mode does not satisfy the PRD’s “no hint, no answer, no Ask AI until completion” requirement.
- **Evidence:** Only `ASK_COMMITMENT`, `GIVE_CUE`, and `GIVE_HINT` are produced by `LearningNativePolicy`; `START_TEACH_BACK`, `START_TRANSFER`, and `ENTER_SOLO` are never selected. The live test’s natural-language requests cannot create those states.
- **Minimal fix:** Introduce a durable, deterministic pedagogical phase/transition record loaded before generation. Add real UI actions for starting Teach-Back and Transfer. Enforce Solo at the API/generation boundary, associate attempts with the active task, require completion/verification semantics for exit, and persist the conversation identifier across refresh.
- **Should a test have caught it?** Yes. Current unit tests directly manufacture `request_transfer=True`; deterministic E2E mocks the resulting states; live E2E conditionally skips missing cards. None sends an assistance request during active Solo or refreshes the thread.

**P0-3 — The claimed tunnelling simulation and `R + T ≈ 1` verification do not exist in the authoritative path.**

- **Affected behavior:** The competition Golden Loop can describe tunnelling fluently without performing a tunnelling calculation.
- **Files and symbols:**
  - Scientific kinds contain no tunnelling/barrier request: [models.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/science/models.py:33), lines 33–41.
  - Scientific dispatch only supports the listed tools: [toolbox.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/science/toolbox.py:571), lines 571–607.
  - The implemented simulation is a closed two-level Rabi system: [toolbox.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/science/toolbox.py:464), lines 464–568.
  - Every experiment-mode frontend request is hardcoded to `two_level_simulation`: [AgentExperience.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/AgentExperience.tsx:595), lines 595–633.
  - The tunnelling CTA only changes the message and mode: [AgentExperience.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/AgentExperience.tsx:650), lines 650–658.
  - Deterministic E2E fabricates `T=0.0821`, `R=0.9179` as a mocked “unitarity” result: [golden-loop.spec.ts](/home/xiangyu_xie/QuantumAgent/tests/e2e/golden-loop.spec.ts:291), lines 291–325.
  - Live E2E sends natural language in `learn_concepts` and never supplies or asserts `scientific_request`: [golden-loop-live.spec.ts](/home/xiangyu_xie/QuantumAgent/tests/e2e/live/golden-loop-live.spec.ts:337), lines 337–344.
- **Why it matters:** Scientific verification is central to the submission and to the exact PRD Golden Loop. No numeric `R+T` tolerance is evaluated for tunnelling, and no displayed tunnelling value is derived from an authoritative tool.
- **Evidence:** The authoritative result union cannot represent a tunnelling simulation. The live test never inspects `scientific_results`.
- **Minimal fix:** Add a typed rectangular-barrier or wave-packet request/result to the Python toolbox, with bounded parameters, units, finite-value guards, convergence/separation conditions, and explicit norm plus `|R+T-1|≤tolerance` assertions. Wire the Golden CTA to it and make the live test hard-assert the result kind, pass status, metrics, and UI values.
- **Should a test have caught it?** Yes. The mocked test should not call fabricated values “real simulation”; the live test should fail if no tunnelling scientific result is persisted or displayed.

#### P1 — Important before competition if feasible

**P1-1 — Cognitive Mirror labels overstate the persisted evidence.**

- **Affected behavior:** Generating a transfer task counts as transfer evidence; combining that with any Teach-Back can yield `TRANSFER_READY`. `unaided_retrieval` is set without proven unaided performance, and verification is ignored for readiness.
- **Files and symbols:** [learning_native.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/learning_native.py:524), lines 524–663; [nodes.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/tutor/nodes.py:929), lines 929–941.
- **Why it matters:** The PRD explicitly defines learning using unaided performance, transfer, and delayed retrieval. The current mirror can promote a learner based on task generation and unverified text.
- **Evidence:** `has_transfer` includes both `TRANSFER` and `SOLO_ATTEMPT`; `TRANSFER_READY` requires only `has_transfer && has_teach_back`; `unaided_retrieval=has_transfer`. Untagged evidence receives a new random UUID on each build. The mirror is built before current-turn evidence is persisted.
- **Minimal fix:** Separate task-issued from attempt-submitted and verified-transfer evidence; record hint/assistance exposure; require a verified attempt associated with the active transfer task; use a stable untagged bucket; merge current-turn evidence or compute the mirror after the evidence flush.
- **Should a test have caught it?** Yes. Current tests primarily check the no-personality disclaimer and mocked labels, not the evidence required for each label.

**P1-2 — The 240-second timeout masks an unbounded latency/retry and replay problem.**

- **Affected behavior:** The “SSE” proxy buffers the entire upstream response, shows no heartbeat or progress, does not propagate browser cancellation, and can duplicate a completed turn after a lost response/retry.
- **Files and symbols:**
  - Bounded full-buffer read and 240-second timeout: [_shared.ts](/home/xiangyu_xie/QuantumAgent/app/api/teaching/_shared.ts:132), lines 132–149 and 218–265.
  - Re-encodes only after terminal completion: [_shared.ts](/home/xiangyu_xie/QuantumAgent/app/api/teaching/_shared.ts:267), lines 267–342.
  - Browser calls `response.text()`: [AgentExperience.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/AgentExperience.tsx:429), lines 429–453.
  - Backend emits only start and terminal events: [teaching.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/api/teaching.py:186), lines 186–234.
  - Retry configuration: [gateway.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/llm/gateway.py:155), lines 155–182 and 224–267.
  - Multi-profile fallback: [routing.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/llm/routing.py:486), lines 486–532.
  - Idempotency only recognizes a currently running HITL turn: [repository.py](/home/xiangyu_xie/QuantumAgent/services/api/quantum_agent/teaching/repository.py:124), lines 124–159.
- **Why it matters:** Four 60-second transient attempts for one profile already exceed the proxy deadline before profile fallback or later graph model calls. A normal turn performs multiple sequential model operations. Permanent 400/401/403 failures are not retried inside one gateway, but become generic `GatewayError`s and are tried again against every router profile.
- **Minimal fix:** Establish one end-to-end turn deadline below the proxy limit, one retry budget across gateway and router, and fail-fast classification that preserves permanent status. Forward request cancellation, emit heartbeats/progress, and require a client idempotency key that can replay completed results.
- **Should a test have caught it?** Partly. Gateway tests prove a single gateway does not retry 401, but no router-level auth test exists. Live E2E covers only successful 60–90-second calls.

**P1-3 — Non-authoritative legacy routes leave a public, conflicting attack surface.**

- **Affected behavior:** If the old D1 binding is enabled, anyone knowing a session ID can retrieve old turns and traces, and anyone can insert a published knowledge source. The public simulation route accepts unbounded grid/step values. The optional sandbox relay has no authentication, rate limit, or file-size bound.
- **Files and symbols:** [trace route](/home/xiangyu_xie/QuantumAgent/app/api/trace/route.ts:5), lines 5–12; [knowledge route](/home/xiangyu_xie/QuantumAgent/app/api/knowledge/route.ts:6), lines 6–19; [simulate route](/home/xiangyu_xie/QuantumAgent/app/api/simulate/route.ts:3), lines 3–16; [simulation.ts](/home/xiangyu_xie/QuantumAgent/lib/simulation.ts:137), lines 137–267; [sandbox route](/home/xiangyu_xie/QuantumAgent/app/api/sandbox/route.ts:3), lines 3–9.
- **Why it matters:** These routes are built into the production web artifact and contradict the claim that all data access is authenticated and that Python is authoritative. The Compose deployment lacks D1/sandbox bindings, limiting present exploitability, but the stale Cloudflare deployment documentation explicitly configures D1.
- **Minimal fix:** Remove non-authoritative stateful routes from the production build. If any must remain, apply `qa_session` authentication, ownership/RBAC, same-origin enforcement, rate limits, and strict numeric/body bounds.
- **Should a test have caught it?** Yes. Existing security tests cover teacher cookies and a regex sandbox preflight, not unauthenticated route access, cross-user trace reads, or simulation resource exhaustion.

**P1-4 — The production UI has no repository-supported student session bootstrap.**

- **Affected behavior:** `/agent` requires a `qa_session` cookie, but no active login/SSO route exchanges an identity for that session. The live test succeeds by seeding a database session and installing the cookie directly.
- **Files and symbols:** [agent BFF](/home/xiangyu_xie/QuantumAgent/app/api/agent/_shared.ts:46); [golden-loop-live.spec.ts](/home/xiangyu_xie/QuantumAgent/tests/e2e/live/golden-loop-live.spec.ts:87), lines 87–97; [run-live-e2e.sh](/home/xiangyu_xie/QuantumAgent/scripts/run-live-e2e.sh:16), lines 16–24. `app/chatgpt-auth.ts` is unused.
- **Why it matters:** A pre-seeded private demo works, but a judge or first-time user cannot enter the product without an external, undocumented cookie-issuing component.
- **Minimal fix:** Implement the intended login/SSO-to-backend-session exchange, or make pre-provisioned competition accounts an explicit, tested deployment step.
- **Should a test have caught it?** The live test deliberately bypasses this boundary, so no.

#### P2 — Post-competition improvements

**P2-1 — Repository documentation still describes the removed D1/TypeScript runtime as deployable.**

- **Affected behavior:** Maintainers can follow incompatible architecture, API, and security instructions.
- **Files:** [CLAUDE.md](/home/xiangyu_xie/QuantumAgent/CLAUDE.md:9), lines 9–14 and 118–127; [DEPLOYMENT.md](/home/xiangyu_xie/QuantumAgent/docs/DEPLOYMENT.md:1), lines 1–120; `docs/API.md`, `docs/ARCHITECTURE.md`, and `docs/SCIENTIFIC_VALIDATION.md`.
- **Evidence:** They still describe D1, `/api/tutor`, pure TypeScript scientific authority, and Cloudflare deployment.
- **Minimal fix:** Archive legacy documents and make Compose/FastAPI documentation canonical.
- **Should a test have caught it?** A documentation/link consistency check could.

**P2-2 — Minor accessibility and async-status gaps remain.**

- **Affected behavior:** The mobile drawer close buttons have no accessible names, errors are not announced through a live region, and long model calls expose only a spinner.
- **Files:** [AgentExperience.tsx](/home/xiangyu_xie/QuantumAgent/app/components/agent/AgentExperience.tsx:727), lines 727–733, 927, and 932–934.
- **Evidence:** Against the current [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md), the icon-only close controls lack `aria-label`, and composer errors lack `aria-live`.
- **Minimal fix:** Add accessible names/live regions and meaningful workflow progress.
- **Should a test have caught it?** Add an automated accessibility smoke test.

### 4. Learning-Native semantic audit

**A. Commitment-before-generation:** Structurally yes; semantically no. When the narrow gate fires, the tutor composer is not called. However, ordinary concept questions do not enter that gate, model failure disables it, trivial attempts satisfy it, and exact evidence snippets remain exposed. A direct API client cannot set the release level directly, but can exploit these normal inputs and can bypass frontend affordances.

**B. Policy ownership:** The release decision itself is code-owned. Nevertheless, model-selected `task_kind` feeds directly into release policy, and commitment enforcement depends on a model proposal existing. An LLM cannot write an explicit override, but model output and availability can change whether the learner is gated.

**C. Productive struggle:** Not consistently protected. The current default concept path remains explanation-centric, while the richer Learning-Native stages are optional structured submissions rather than enforced transitions.

**D. Pre/post split:** The split is not semantically clean. Solo restoration and assistance locking belong before generation. Teach-Back analysis should occur before composing the response to a reconstruction. Transfer phase selection should precede tutor response generation. The mirror may be assembled post-turn, but only after incorporating the current evidence.

**E. Cross-turn state:** Backend ownership scoping is sound and concurrent same-thread turns are serialized with a row lock. Completed-turn replay lacks an idempotency key. Solo is restored only within the same conversation; frontend refresh loses that conversation ID. No accidental cross-user persistence was found in the authoritative backend.

#### Compact PRD traceability

| Requirement | Implemented? | Evidence | Confidence | Gap |
|---|---:|---|---:|---|
| Commitment before completion | Partial | Pre-node and skip branch | High | Normal concepts bypass; model-dependent; evidence leak |
| Confidence capture | Partial | Commitment/transfer schemas and rows | High | Not collected for generic attempts; no calibration gap |
| Diagnosis Agent | Yes, bounded | Attempt-only diagnosis; inference labelled | High | Live Golden does not prove intended misconception |
| Minimal intervention | Partial | Release levels and claim caps | High | Concept mode defaults to full explanation |
| Predict → simulate → compare | No for Golden Loop | Only two-level simulation wired | High | No tunnelling request, calculation, or comparison UI |
| Scientific verification | Partial | Symbolic/norm/unitarity/two-level tools | High | No tunnelling `R+T` verification |
| Teach-Back | Backend-only partial | Submission and analysis contract | High | No production UI initiation or automatic phase |
| Transfer / Solo | Backend-only partial | Direct structured submission | High | No UI start; pre-generation lock absent; refresh/exit bypass |
| Cognitive Mirror | Partial | PostgreSQL aggregation | High | Readiness and unaided labels are not evidentially sound |
| LearningEvidence persistence | Yes, structurally | Atomic per-turn SQL writes | High | Assisted/unaided/task identity semantics incomplete |
| Multimodal + HITL | Implemented in code | Scoped upload, checkpoint and resume tests | Medium | Live checks were not rerun in this review |
| True SSE | No | Full upstream/body buffering | High | Only two terminal document events reach browser |
| Hybrid retrieval | Yes | FTS/vector/graph RRF | High | Reranker is registered but unused |
| Premium responsive frontend | Partially | Desktop/mobile inspection | High | Visual quality good; core Learning-Native journey not reachable |

### 5. Golden Loop evidence matrix

| Stage | Deterministic mocked E2E | Live non-mocked E2E |
|---|---|---|
| 1. Prediction / Commitment | **HARD ASSERTION** — scripted card/UI only | **SOFT / ADAPTIVE ASSERTION** — generic attempt is sent; formal card optional; confidence absent |
| 2. Diagnosis | **HARD ASSERTION** — scripted diagnosis UI | **ONLY INDIRECTLY TESTED** — a latest trace has some diagnosis |
| 3. Minimal intervention | **HARD ASSERTION** — scripted hint text | **NOT ACTUALLY TESTED** — no release-level or hint-size assertion |
| 4. Revised attempt | **ONLY INDIRECTLY TESTED** — message sent to mock | **HARD ASSERTION** for submission/terminal only |
| 5. Simulation | **HARD ASSERTION** — fabricated UI result | **NOT ACTUALLY TESTED** |
| 6. Scientific verification | **HARD ASSERTION** — mocked “pass” object only | **NOT ACTUALLY TESTED** |
| 7. Prediction-vs-result comparison | **ONLY INDIRECTLY TESTED** | **NOT ACTUALLY TESTED** |
| 8. Explanation | **ONLY INDIRECTLY TESTED** | **ONLY INDIRECTLY TESTED** — text is sent, not evaluated |
| 9. Teach-Back | **HARD ASSERTION** — mocked card/analysis | **SOFT / ADAPTIVE ASSERTION** — helper silently continues if absent |
| 10. Transfer | **HARD ASSERTION** — mocked card | **SOFT / ADAPTIVE ASSERTION** — helper silently continues if absent |
| 11. Solo Mode | **HARD ASSERTION** — mocked lock text only | **SOFT / ADAPTIVE ASSERTION** — no assistance-blocking request; contains a tautological conditional |
| 12. Cognitive Mirror update | **HARD ASSERTION** — mocked panel/label | **SOFT / ADAPTIVE ASSERTION** — visibility optional; update semantics unasserted |

The deterministic test explicitly intercepts and fulfills both first-party APIs: [golden-loop.spec.ts](/home/xiangyu_xie/QuantumAgent/tests/e2e/golden-loop.spec.ts:509), lines 509–541. It is a UI contract test.

The live test has no first-party mock or HAR. Its database assertions prove that total events, total traces, and generic attempt counts increased. They do not prove that the new rows are commitment, confidence, diagnosis inference, Teach-Back, Transfer, Solo, or verified scientific evidence. Its comment claiming a persisted `DIAGNOSIS_INFERENCE` is not backed by an assertion.

### 6. Security assessment

The authoritative FastAPI surface has credible session, membership, course/edition, thread-owner, attachment-owner, and staff-role controls. A second student should receive an authorization/not-found result when accessing another student’s authoritative trace, evidence, attachment, or HITL thread.

Actionable security work is the legacy web-route surface described in P1-3. `/api/trace` lacks ownership checks; `/api/knowledge` lacks teacher authorization; `/api/simulate` is an unbounded CPU/memory target; and `/api/sandbox` would expose a configured execution service to unauthenticated callers.

Uploaded/OCR text is consistently marked as data in model prompts. Model output cannot change membership, persistence ownership, answer policy directly, or scientific pass/fail status. I found no concrete prompt-injection path that forges authoritative evidence or extracts backend secrets.

The current official secret scan is limited to the built client bundle. It passed. No tracked `.env`, HAR, trace archive, source map, or obvious historical high-entropy bearer/key match was found. Local ignored `.env` and test/build artifacts exist but are not part of the commit.

The authoritative Python code-test tool returns `INCONCLUSIVE` when no external restricted executor is configured; it does not execute student code on the API host. The separate legacy sandbox relay should be removed or authenticated and rate-limited.

### 7. Scientific-verification assessment

Genuinely deterministic/tool-verified:

- symbolic equivalence and residual checks;
- vector normalization;
- matrix unitarity;
- two-level QuTiP evolution with norm and population conservation;
- bounded line-visualization data generation;
- external code-test results when the restricted executor is configured.

The normal response path constructs claims from deterministic tool observations. Model-written inference is separately labelled. Inconclusive results remain inconclusive, and transfer verification only considers `PASS` results.

Not genuinely verified:

- rectangular-barrier tunnelling;
- wave-packet propagation through a barrier;
- transmission/reflection values;
- `R+T≈1` for the Golden Loop;
- comparison of a learner’s prediction with an actual tunnelling result.

The retained TypeScript `runSimulation` is disconnected from the authoritative tutor and has no tests. It also cannot rescue the claim: its Crank–Nicolson left-hand matrix is real despite the required complex `iHΔt/(2ħ)` factor, its kinetic coefficient omits division by `ħ`, and its `R/T` calculation excludes probability inside the barrier. It should not be presented as validated physics.

### 8. Frontend/product assessment

At 1440×900, the three-panel scientific-workbench layout, serif/monospace typography, restrained green palette, evidence rail, and mode-specific workspaces look competition-quality. At 390×844, the layout remains legible and appropriately collapses navigation and evidence. See the reviewed [desktop screenshot](/home/xiangyu_xie/QuantumAgent/test-results/visual-qa/desktop-1440x900.png) and [mobile screenshot](/home/xiangyu_xie/QuantumAgent/test-results/visual-qa/mobile-390x844.png).

The first impression is not “ChatGPT clone.” It communicates evidence grounding and specialist workflow well.

It does not yet make the Learning-Native philosophy reliably perceptible through behavior. The Commitment card is rarely reached in normal concept mode; Teach-Back and Transfer cannot be started from the real UI; normal Ask AI remains available during Solo; there is no actual Prediction-vs-Reality tunnelling presentation; and refreshing loses the active thread.

Loading, empty, and error states exist, but a 60–240-second request displays a spinner rather than meaningful streamed progress.

### 9. Test-quality assessment

Fresh results:

- Python: **215 passed, 2 skipped** in 148.73 seconds.
- Ruff: **pass**.
- mypy strict: **pass**, 64 source files.
- TypeScript strict: **pass**.
- Frontend unit tests: **57 passed**.
- Existing client bundle secret scan: **pass**.

I did not rerun the production build because that would rewrite `dist` during a read-only review. The existing web/API containers and artifact were healthy. I also did not spend additional live USTC calls.

The Python suite is generally strong on schema constraints, authorization, evidence integrity, HITL ownership, deterministic scientific utilities, and transaction behavior. Its green status deserves confidence in those areas.

It is weak precisely where the competition claim is strongest:

- the commitment test covers one favorable mode and mocked proposal;
- another test codifies the concept-mode bypass;
- Teach-Back/Transfer tests directly construct inputs the UI cannot emit;
- Solo enforcement is never adversarially tested;
- no authoritative tunnelling test exists;
- deterministic Golden Loop values are mocked;
- live Golden Loop branches adaptively around missing stages;
- `test_learning_native.py:620–626` contains an `or True` assertion, although later string assertions preserve part of that test’s value;
- live trace detail uses the latest course trace rather than correlating it to the newly created conversation.

A green suite therefore proves a stable implementation, but not that the PRD Golden Learning Loop is complete.

### 10. Freeze recommendation

> If this were your own competition submission, would you freeze this commit today?

**NO.**

I would not freeze a Learning-Native submission when the normal commitment path can release full explanations, the core post-explanation stages are not reachable from the product UI, Solo is not an enforceable pre-generation state, and the centerpiece scientific demonstration does not perform the claimed physics. Those are product-definition failures, not optional architectural preferences.

### 11. Minimal remediation plan

1. Move durable pedagogical phase and Solo restoration into the pre-generation boundary. Make commitment enforcement deterministic and fail-closed to a fixed prompt.
2. Redact targeted evidence content while an answer/commitment is withheld; expose only safe provenance until the gate is satisfied.
3. Wire real Teach-Back and Transfer initiation into the UI and backend transition policy. Require an active-task-correlated attempt before Solo unlock.
4. Implement one authoritative Python tunnelling simulation and verifier with hard `R/T`, conservation, units, and convergence assertions.
5. Replace the adaptive Golden test with hard assertions for every required stage, exact new evidence kinds, conversation-correlated traces, and the tunnelling scientific result.
6. Before the demo, bound the end-to-end retry/latency budget, add completed-turn idempotency, and remove or secure the legacy public routes.
7. Provide a tested student session bootstrap or a documented, rehearsed competition-account provisioning path.