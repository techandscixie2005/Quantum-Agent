# Implementation tasks

This file tracks verifiable work against the PRD. A checked item means its tests
and acceptance condition passed; documentation alone is not completion.

## Phase 0 — safe additive foundation

- [x] Audit the repository, PRD and every `/knowledge` file.
- [x] Record the six-chapter/ eight-root curriculum-version conflict.
- [x] Protect the local `.dev.vars` secret file from accidental staging.
- [ ] Add Python 3.12 packaging, configuration and dependency lock.
- [ ] Add PostgreSQL/pgvector, Neo4j, API and worker Compose services.
- [ ] Apply and downgrade the Alembic baseline against PostgreSQL.

Acceptance: backend unit tests, migration smoke test and dependency health
checks pass without using a live LLM.

## Phase 1A — ingestion and provenance

- [ ] Discover and verify all manifest sources by SHA-256.
- [ ] Extract PDF physical pages and page labels without crossing page bounds.
- [ ] Extract PPTX slides, DOCX sections/paragraphs, XLSX sheets/rows and text.
- [ ] Flag image-only or low-quality extraction as `REVIEW_REQUIRED`.
- [ ] Import the XLSX taxonomy/prerequisites as reviewed candidates.
- [ ] Import the 2026 syllabus as its own curriculum edition.

Tests: deterministic IDs/checksums, locator accuracy, no invented page labels,
real-file smoke pages, OCR-required Griffiths regression.

Acceptance: all 12 files produce traceable document records; the 1,750 PDF-page
inventory reconciles exactly; every chunk resolves to an immutable source.

## Phase 1B — explicit ontology and review

- [ ] Enforce node, relation and allowed-triple whitelists.
- [ ] Validate evidence quotes against immutable chunks.
- [ ] Add teacher queue/detail/approve/reject/edit/merge endpoints.
- [ ] Record revisions, reviewer identity, reason and immutable audit events.
- [ ] Project only approved graph versions to Neo4j through an outbox.

Tests: invalid types/patterns rejected, unsupported extraction retained for
review, student queries exclude unapproved/rejected records, idempotent sync,
merge lineage preserved.

Acceptance: a teacher can take a real XLSX/deck candidate through every review
action and open its original evidence.

## Phase 1C — retrieval and product surfaces

- [ ] Add Chinese-tokenized PostgreSQL full-text retrieval.
- [ ] Add a separately configured and probed pgvector embedding channel.
- [ ] Add approved-only Neo4j search, subgraph and prerequisite paths.
- [ ] Fuse channels into validated `EvidencePacket`s.
- [ ] Add student graph explorer and teacher knowledge-review pages.
- [ ] Display physical page/label/slide/block citations and source text.

Tests: per-channel ranking, RRF determinism, publication/approval filters,
evidence-packet provenance, API authorization, UI keyboard/mobile smoke tests.

Acceptance: a real concept search returns graph context and course evidence;
unpublished or unapproved knowledge is absent from every student surface.

## Phase 2 — deterministic teaching system

Blocked until all Phase 1 acceptance conditions pass.

- [ ] Implement the Python tutor state machine and typed trace events.
- [ ] Apply backend RBAC, course policy and H0–H5 answer-release gates.
- [ ] Ground Q&A and diagnosis in Phase 1 `EvidencePacket`s.
- [ ] Add progressive hints, misconception evidence and transfer checks.
- [ ] Add symbolic/numeric verification and scientifically labeled claims.
- [ ] Add corrected wave-packet simulation and four project workflows.
- [ ] Add fail-closed restricted Docker sandbox integration.
- [ ] Add teacher traces, TA queue and student-model-lite evidence.

Acceptance: the tunneling misconception -> prediction -> real simulation ->
probability check -> explanation -> transfer question -> teacher trace loop
passes end to end, with policy and citation red-team tests.

## Release verification

- [ ] `make lint`, `make typecheck`, `make test`, `make e2e`, `make build` pass.
- [ ] Compose starts from a clean machine and health checks become ready.
- [ ] Secret scanner inspects the real client artifact and fails on a fixture.
- [ ] No citation support failure is presented as course-grounded.
- [ ] No `inconclusive` tool result is presented as verified.
- [ ] Known limitations and real-material test evidence are documented.
