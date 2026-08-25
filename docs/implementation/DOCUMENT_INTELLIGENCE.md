# Student document intelligence

The authoritative API uses this bounded cascade for student uploads:

1. deterministic native parsing for PDF, PPTX, DOCX, UTF-8 text, and Markdown;
2. the server-only `document_parser_primary` capability (MinerU route);
3. the server-only `document_parser_ocr_fallback` capability (`unlimited-ocr` route);
4. the already-probed Qwen vision page OCR fallback, when configured.

The registry entries in steps 2 and 3 are routing aliases, not proof that the public USTC
OpenAI-compatible API exposes a file-parser endpoint. The repository deliberately has no guessed
HTTP path or chat-completions emulation for those aliases. `build_attachment_runtime` binds both
profiles to validated adapters, but without an injected `DocumentCapabilityTransport` each attempt
is recorded as `unavailable` in `DocumentEvidence.fallback_chain`. Native parsing continues to work.

A real transport can be enabled only by implementing the typed
`DocumentCapabilityTransport.parse_document` boundary after its request/response contract has been
capability-probed. The adapter enforces a 25 MiB request maximum, a configured page limit, SHA-256
binding, server-selected profiles, and strict Pydantic validation of page/slide units, reading order,
headings, formulas, tables, figures, captions, and bounding boxes. No environment variable is
provided for an undocumented endpoint.

OCR is not called merely because MinerU requested confirmation. A MinerU result with meaningful
structured content at or above the confidence threshold is retained, and its ambiguities go to the
student/HITL confirmation path. OCR runs only when earlier output is missing or below the usable
threshold.

## Legacy `.doc` and `.ppt`

This API image does not contain a secure legacy Office converter. Consequently the production
student UI does not advertise `.doc` or `.ppt`, and upload validation returns the explicit
`LEGACY_OFFICE_CONVERTER_UNAVAILABLE` response (HTTP 415) by default.

The backend includes a typed `LegacyOfficeConverter` boundary for deployments that operate an
isolated conversion service. When one is injected into `build_attachment_runtime`:

- upload validation enables legacy formats and validates CFB magic, allocation tables, directory
  bounds, the Word/PowerPoint stream type, declared MIME, and active/encrypted/embedded content;
- the converter must return a checksum-bound DOCX or PPTX artifact through
  `LegacyOfficeConversionResult`;
- the converted archive is revalidated with the same ZIP bomb, traversal, encryption, active
  content, size, and MIME checks as a direct modern Office upload;
- the existing deterministic DOCX/PPTX parser then produces normalized provenance, with
  `extraction_method=legacy_conversion` and converter/parser versions retained.

An operational converter must run out of process as a non-root user, without network access, with a
read-only source, a private temporary directory, process/time/memory/output limits, and deletion of
all temporary artifacts. After that dependency is installed and exercised in live E2E, the `/agent`
file picker/help can add `.doc,.ppt`; it must not advertise them before then.
