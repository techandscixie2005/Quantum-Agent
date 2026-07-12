# LangGraph Decisions

**Date**: 2026-07-12
**Status**: Implemented

## Overview

The Quantum Agent tutor orchestration has been migrated from a monolithic `runTutorWorkflow()` function to a LangGraph.js `StateGraph`. This document records every consequential design decision.

## Decisions

### D1: StateGraph API choice

**Question**: Use StateGraph (Graph API) or entrypoint/task (Functional API)?

**Docs consulted**: `@langchain/langgraph` docs — Graph API section, Functional API section

**Decision**: Use StateGraph (Graph API) with `StateSchema` + Zod.

**Rationale**: The Graph API provides explicit edge-based routing, which matches the pedagogical workflow's need for separate authenticate → diagnose → policy → retrieve → generate → enforce → response stages. The Functional API is better for simpler task pipelines, not for the complex conditional branching required by H0-H5 policy enforcement.

**Rejected**: Functional API (`entrypoint`/`task`) — too constrained for pedagogical conditional routing with multiple branch points.

**Files**: `lib/agent/graph.ts`, `lib/agent/state.ts`

**Tests**: Existing backend tests pass; graph compilation succeeds in TypeScript.

---

### D2: State definition approach

**Question**: `StateSchema` vs `Annotation.Root`?

**Decision**: Use `StateSchema` with Zod v4 schemas.

**Rationale**: `StateSchema` supports `ReducedValue` (custom reducers for append-only traces and evidence arrays), `MessagesValue` for chat messages, and `UntrackedValue` for transient state. `Annotation.Root` is a simpler alternative but lacks `ReducedValue` reducer support needed for accumulating evidence and trace steps.

**Rejected**: `Annotation.Root` — insufficient reducer customization.

**Files**: `lib/agent/state.ts`

**Tests**: Graph compilation verifies schema validity.

---

### D3: Checkpointer strategy

**Question**: Custom D1 `BaseCheckpointSaver` or explicit D1 persistence at node boundaries?

**Decision**: Use `MemorySaver` for development + explicit D1 persistence via `repository.ts` at node boundaries.

**Rationale**: The current LangGraph.js `BaseCheckpointSaver` interface requires implementing:
- `.getTuple(config)` — fetch checkpoint by thread_id
- `.put(config, checkpoint, metadata)` — store checkpoint
- `.putWrites(config, writes)` — store pending writes
- `.list(config, filter)` — list checkpoints

Building a production D1 implementation that correctly handles concurrent writes, checkpoint versioning, and Cloudflare Worker request lifecycle constraints is non-trivial. The existing `persistTutorExchange()` in `repository.ts` already handles D1 persistence reliably.

**Decision**: Explicit persistence at the `assembleResponse` node boundary. Thread state for resume is maintained via `sessionId` + explicit DB lookup, not via `getState()` replay.

**Rejected**: Custom D1 `BaseCheckpointSaver` — would need thorough testing of concurrent-write semantics; deferred.

**Files**: `lib/agent/graph.ts`, `lib/repository.ts`, `app/api/tutor/route.ts`

**Tests**: Existing persistence tests pass.

---

### D4: Routing strategy

**Question**: `Command`-based routing in nodes vs `addConditionalEdges`?

**Decision**: Use `addConditionalEdges` with dedicated route functions.

**Rationale**: Separation of concerns — nodes handle state transformation, routing functions handle control flow. This makes the graph structure visible in `graph.ts` and easier to audit. `Command`-based routing mixes control flow with business logic inside nodes.

**Rejected**: `Command`-based routing — less auditable, harder to verify pedagogically correct routing.

**Files**: `lib/agent/routing.ts`, `lib/agent/graph.ts`

**Tests**: TypeScript typecheck verifies route function return types match graph nodes.

---

### D5: Interrupt for teacher review

**Question**: Use LangGraph `interrupt()` or separate API-based review flow?

**Decision**: Use LangGraph `interrupt()` for the teacher review gate.

**Rationale**: `interrupt()` integrates with LangGraph's checkpointing and resume mechanism. When a response is high-risk, the graph pauses and waits for a `Command({ resume: ... })` call. The teacher dashboard can issue this resume via the existing teacher API.

**Rejected**: Separate API flow — would duplicate state management outside the graph.

**Files**: `lib/agent/nodes/escalation.ts`

**Tests**: Pending interrupt/resume integration test.

---

### D6: Subgraphs

**Question**: Subgraphs for each pedagogical mode?

**Decision**: Define subgraph schemas for concept clarification, derivation review, image interpretation, code assistance, numerical experiment, and project coaching. Currently connected as lightweight wrappers; full implementation will deepen each subgraph.

**Rationale**: LangGraph subgraphs isolate mode-specific state and logic, preventing leakage between modes.

**Files**: `lib/agent/subgraphs/schemas.ts`, `lib/agent/subgraphs/index.ts`

**Tests**: Subgraph compilation succeeds.

---

### D7: Cloudflare Workers compatibility

**Question**: Does LangGraph.js work in a Workers runtime?

**Decision**: Verified compatible. LangGraph.js core has no Node.js-specific dependencies.

**Files**: `worker/index.ts` (unchanged), `vite.config.ts` (unchanged)

**Tests**: Production build succeeds via vinext + @cloudflare/vite-plugin.

---

### D8: Zod version

**Question**: Zod v3 or v4?

**Decision**: Use Zod v4 (installed as `zod` v4.4.3).

**Rationale**: Zod v4 is the current major version with better tree-shaking and TypeScript inference. The `zod/v4` import path provides `z.enum()`, `z.string()`, etc.

**Rejected**: Zod v3 — v4 is current and LangGraph docs use v4-style `StateSchema` with Zod.

**Files**: `lib/agent/state.ts`, `lib/agent/subgraphs/schemas.ts`

**Tests**: TypeScript compilation succeeds.