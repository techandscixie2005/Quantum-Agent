# Model Routing

## Authoritative runtime

Quantum Agent V2.1 routes models only in the Python backend. The implementation is in
`services/api/quantum_agent/llm/routing.py` and is constructed by
`services/api/quantum_agent/gateways.py`. The Next.js browser application sends a teaching mode,
student content, and attachment IDs; it cannot select a provider, endpoint, or concrete model.

The server boundary is:

```text
typed task -> ModelCapabilityRegistry -> ModelRouter -> ModelGateway
           -> Pydantic-validated result -> deterministic workflow/policy/verifier
```

`ModelRouter` tries only the ordered candidates for the requested task, validates every structured
result again at the router boundary, and temporarily cools down failing profiles. It does not call
every model. RBAC, evidence visibility, citation validity, answer release, verification, sandbox
permissions, and learning-state writes remain deterministic.

## Task routes

The defaults below are backend configuration, not a student-facing catalog.

| Task | Primary alias and default | Bounded fallbacks | Transport | Runtime use |
|---|---|---|---|---|
| `reasoning` | `USTC_MODEL=deepseek-v4-pro` | `USTC_MODEL_VISION_REASONER`, `qwen-reasoner`, `USTC_MODEL_CODE` | chat completions | Grounded tutoring and difficult reasoning |
| `diagnosis` | `USTC_MODEL=deepseek-v4-pro` | `USTC_MODEL_VISION_REASONER`, `qwen-reasoner` | chat completions | Diagnosis Agent |
| `lightweight` | `USTC_MODEL_QUICK=deepseek-v4-flash-ascend1` | `deepseek-v4-flash` | chat completions | Intent/routing and small structured tasks |
| `vision` | `USTC_VISION_MODEL=qwen3.8-chat` | `qwen-chat` | chat completions with image input | Screenshots, handwriting, figures, and plots |
| `document_reasoning` | `USTC_MODEL=deepseek-v4-pro` | `USTC_MODEL_CODE`, `glm-5.2-107` | chat completions | Long-context course/project extraction |
| `embedding` | `USTC_MODEL_EMBEDDING=qwen3-embedding` | none | embeddings | Registry declaration; see independent gateway below |
| `rerank` | `USTC_MODEL_RERANK=qwen3-reranker` | none | rerank | Registry declaration; no unprobed adapter call |
| `document_parsing` | `USTC_MODEL_MINERU=mineru` | `USTC_MODEL_OCR=unlimited-ocr` | document parser | Registry declaration; requires an injected, probed file transport |

Known operations map to stable tasks: `interpret_teaching_turn` uses `lightweight`,
`diagnose_student_progress` uses `diagnosis`, `compose_grounded_teaching_response` uses
`reasoning`, and `quantum_course_knowledge_extraction` uses `document_reasoning`. Unknown internal
operations resolve by the server-selected model tier, never by an arbitrary model string supplied
by a client.

## Exact Python settings

| Setting | Meaning |
|---|---|
| `USTC_API` | Backend-only bearer token |
| `USTC_BASE_URL` | OpenAI-compatible base URL; default `https://api.llm.ustc.edu.cn/v1` |
| `USTC_MODEL` | Primary reasoning and diagnosis model |
| `USTC_MODEL_QUICK` | Lightweight structured-task model |
| `USTC_VISION_MODEL` | Vision model |
| `USTC_MODEL_VISION_REASONER` | Difficult second-pass reasoning model |
| `USTC_MODEL_CODE` | Long-context document/code model |
| `USTC_MODEL_EMBEDDING` | Registry alias for the embedding capability |
| `USTC_MODEL_RERANK` | Registry alias for the reranking capability |
| `USTC_MODEL_MINERU` | Registry alias for structured document parsing |
| `USTC_MODEL_OCR` | Registry alias for document OCR fallback |

`USTC_MODEL_DEEP`, `USTC_MODEL_VISION`, `MODEL_ROUTES_JSON`, and `MODEL_TIMEOUT_MS` belong to the
older TypeScript provider implementation and are not Python V2.1 routing settings. Do not put them
in the authoritative deployment configuration.

## Embeddings and retrieval

Chat compatibility never implies embedding compatibility. The active retrieval embedding gateway
is configured independently with:

```env
EMBEDDING_PROVIDER=local_hashing
EMBEDDING_DIMENSION=384
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
```

Allowed providers are `disabled`, `local_hashing`, and `openai_compatible`. The production schema
is fixed at 384 dimensions. `local_hashing` is a deterministic development/degraded signal, not a
learned semantic embedding. An `openai_compatible` route is usable only after its URL, key, model,
and returned 384-dimensional vectors have been verified. Merely setting
`USTC_MODEL_EMBEDDING` does not activate that gateway.

PostgreSQL FTS, pgvector, and approved Neo4j graph candidates are fused deterministically. The
`qwen3-reranker` profile is registered for a future validated transport; the current workflow does
not reinterpret it as chat or call an undocumented endpoint.

## Document parser transport status

The USTC public documentation describes the OpenAI-compatible chat and embeddings surface:

- [API usage](https://llm.ustc.edu.cn/guide/api-usage/)
- [Protocol compatibility](https://llm.ustc.edu.cn/guide/protocol/)

Those public pages do not define a file-upload/document-parser protocol for `mineru` or
`unlimited-ocr`. Consequently, these names remain server-side capability aliases only. The
registry adapters fail closed as `unavailable` until an operator injects a
`DocumentCapabilityTransport` whose typed startup probe explicitly passes and whose byte/page
limits cover the request. A parser alias is never sent to the chat endpoint as an assumption.

Native parsing remains active for validated PDF, PPTX, DOCX, TXT, and Markdown uploads. Scanned PDF
fallback can use the existing vision gateway and remains confirmation-gated. Legacy DOC/PPT needs
an explicitly supplied isolated converter. Native or model extraction is student evidence, not
automatically published course authority.

## Failure and verification status

When `USTC_API` is absent outside Compose, model-backed branches are unavailable and deterministic
retrieval, policy, and verification remain authoritative. When a configured model fails, the router
makes only its bounded fallbacks and reports failure without inventing vision, citations, or tool
results.

The latest USTC connectivity check from this environment (2026-08-24) did **not** pass: attempts
ended in a connection timeout or TLS connection failure before a valid provider response. Do not
record a live-model pass until `quantum-agent probe-model` and the live multimodal test complete
against the real gateway.

## Browser confidentiality

The browser sees course-safe capability behavior, not registry bindings. It must never receive:

- `USTC_API` or `EMBEDDING_API_KEY`;
- concrete provider model names or fallback order;
- the USTC base URL;
- database, Neo4j, or Redis credentials.

Run `npm run build` followed by `npm run check:secrets` before release. Do not add a model selector
to `/agent` or `/teacher/traces`.
