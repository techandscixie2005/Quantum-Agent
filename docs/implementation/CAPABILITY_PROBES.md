# Capability probe record

Date: 2026-08-22 (Asia/Shanghai)

This record distinguishes observed behavior from assumed provider
compatibility. It contains no credentials.

## USTC model gateway

- Endpoint: `https://api.llm.ustc.edu.cn/v1`
- Configured default model: `deepseek-v4-pro`
- Probe command: `cd services/api && uv run quantum-agent probe-model`
- Result in this workspace: transport `ConnectError` for chat completion,
  JSON-object, JSON-schema, and tool-call probes.

This result means the endpoint was unreachable from the current execution
environment. It does **not** establish that any feature is unsupported. Until
a successful probe is recorded, production code uses PydanticAI
`PromptedOutput` with Pydantic validation and does not depend on native JSON
schema or tool calling.

The installed PydanticAI 2.33 provider path was independently exercised with
an OpenAI-compatible HTTP protocol double. Structured output validation and
capability parsing pass without a live token.

## Embeddings

- Chat compatibility is not treated as evidence of embedding support.
- No learned embedding endpoint/model was configured in this workspace.
- The configured `local_hashing` 384-dimensional provider passed its local
  probe and is labeled `lexical/degraded`; it must not be described as semantic
  retrieval.

## Data services

- No live PostgreSQL/pgvector or Neo4j process was available in the initial
  workspace, and Docker was not installed.
- PostgreSQL FTS/vector DDL and retrieval queries compile against the
  PostgreSQL dialect.
- SQLite migration tests exercise publication views and integrity triggers.
- Neo4j Cypher behavior is covered with driver doubles and the in-memory graph
  contract, including scope enforcement and provenance projection.

The Phase 1 production gate remains open until the Compose stack is run with
live PostgreSQL/pgvector and Neo4j and the real-material smoke workflow passes
there.
