# Knowledge graph architecture

Status: implementation decision record, 2026-08-22.

## Evidence from the repository

The authoritative `/knowledge` corpus contains 12 files: ten PDFs (1,750
physical pages), one DOCX syllabus and one teacher-curated XLSX taxonomy. Seven
lecture decks contribute 737 pages. The existing application indexes only those
seven decks into a flat JSON file; it has no graph, review lifecycle, embeddings,
PostgreSQL or Neo4j.

The current Fall 2026 syllabus has six chapters. The 2022 decks and XLSX have
eight roots. Chapter numbers therefore identify nodes only inside a
`CurriculumEdition`; cross-edition alignment is a reviewed semantic relation,
never an automatic numeric join.

## Authority and storage boundaries

- Original files and immutable source chunks are the authority for physical and
  scientific claims.
- PostgreSQL is the authority for document lifecycle, extracted candidates,
  provenance, teacher decisions, revisions and the graph-sync outbox.
- Neo4j is a derived, rebuildable course semantic index. It is not original
  evidence.
- pgvector embeddings are derived retrieval indexes. A missing or failed
  embedding provider degrades readiness and never silently becomes “semantic
  retrieval.”
- Only chunks from published document versions and graph knowledge with an
  approved review version are visible to students.

## Phase 1 data flow

```text
/knowledge file
  -> immutable DocumentVersion (SHA-256)
  -> page/slide/block-aware SourceChunks
  -> explicit-ontology extraction candidates
  -> exact evidence-quote validation
  -> REVIEW_REQUIRED
  -> teacher approve / reject / edit / merge
  -> transactional PostgreSQL decision + graph-sync outbox
  -> idempotent Neo4j projection
  -> PostgreSQL FTS + pgvector + Neo4j retrieval
  -> fused EvidencePacket with original text and provenance
```

The image-only Griffiths PDF remains `REVIEW_REQUIRED`/`OCR_REQUIRED` until an
OCR artifact, confidence and page crop are reviewed. PPT-exported formulas keep
extracted text and block coordinates because glyph order and superscripts are
often lossy.

## Neo4j GraphRAG decision

The official `neo4j-graphrag` `SimpleKGPipeline` supports an explicit schema
with `additional_node_types = false`. Its default pipeline writes extraction
results directly to Neo4j, which would bypass the required teacher review and
the PostgreSQL provenance authority. Quantum Agent therefore exports the same
strict schema for interoperability but does not enable direct production
writes. Approved records are projected through the graph outbox instead.

## Retrieval contract

Every retrieval channel returns stable chunk/evidence identifiers. Reciprocal
rank fusion combines PostgreSQL full-text, pgvector and Neo4j neighborhood
results after course, curriculum, publication and approval filters. An
`EvidencePacket` includes the actual source text, evidence snippet, document
title and version, source SHA-256, section path, physical page, printed page
label or slide/block locator, retrieval channels and graph context. Generated
explanations never enter the authority corpus.

## Failure rules

- No reliable evidence: return no course claim and state the coverage gap.
- Quote not found in its source chunk: retain candidate as `REVIEW_REQUIRED`.
- PostgreSQL commit succeeds but Neo4j sync fails: retain/retry the outbox event;
  never expose the unsynchronized graph record.
- Neo4j unavailable: serve FTS/vector evidence with an explicit degraded flag.
- Embedding endpoint unverified: disable semantic channel and report degraded
  readiness.
