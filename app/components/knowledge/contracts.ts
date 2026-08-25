/**
 * Runtime contracts for the Phase 1 browser boundary.
 *
 * The FastAPI service is deliberately treated as an untrusted network peer at
 * this boundary. These parsers reject malformed, cross-scope, or partially
 * shaped payloads before React renders them. They are dependency-free so the
 * same checks run in route handlers and focused Node tests.
 */

export const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const SHA256_PATTERN = /^[a-f0-9]{64}$/;

export type PhaseOneScope = Readonly<{
  courseId: string;
  curriculumEditionId: string;
}>;

export type EvidenceLocator = Readonly<{
  locator_type: "pdf_page" | "slide" | "docx_paragraph" | "xlsx_row" | "text_lines";
  physical_page: number | null;
  printed_page_label: string | null;
  slide_number: number | null;
  paragraph_start: number | null;
  paragraph_end: number | null;
  sheet_name: string | null;
  row_start: number | null;
  row_end: number | null;
  line_start: number | null;
  line_end: number | null;
}>;

export type StudentCitation = Readonly<{
  evidence_id: string;
  source_chunk_id: string;
  source_document_id: string;
  document_version_id: string;
  document_title: string;
  document_version: number;
  source_file_name: string;
  source_file_sha256: string;
  source_chunk_sha256: string;
  evidence_sha256: string;
  chapter: string | null;
  section_path: readonly string[];
  locator: EvidenceLocator;
  source_chunk: string;
  evidence_snippet: string;
  evidence_char_start: number;
  evidence_char_end: number;
  kind: string;
}>;

export type StudentGraphNode = Readonly<{
  id: string;
  node_type: string;
  canonical_key: string;
  label: string;
  description: string | null;
  aliases: readonly string[];
  formula_latex: string | null;
  citations: readonly StudentCitation[];
}>;

export type StudentGraphEdge = Readonly<{
  id: string;
  source_id: string;
  target_id: string;
  relationship_type: string;
  citations: readonly StudentCitation[];
}>;

export type ConceptSearchResponse = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  query: string;
  results: readonly Readonly<{ node: StudentGraphNode; score: number }>[];
  degraded: boolean;
  warnings: readonly string[];
}>;

export type StudentSubgraphResponse = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  root_candidate_id: string;
  root_visible: boolean;
  nodes: readonly StudentGraphNode[];
  edges: readonly StudentGraphEdge[];
  degraded: boolean;
  warnings: readonly string[];
}>;

export type StudentPrerequisitePath = Readonly<{
  nodes: readonly StudentGraphNode[];
  edges: readonly StudentGraphEdge[];
}>;

export type PrerequisitePathsResponse = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  target_candidate_id: string;
  paths: readonly StudentPrerequisitePath[];
  degraded: boolean;
  warnings: readonly string[];
}>;

export type ReviewQueueItem = Readonly<{
  candidate_id: string;
  kind: "node" | "relation";
  status: "review_required" | "in_review" | "approved" | "rejected" | "superseded";
  type_name: string;
  label: string;
  confidence: number;
  revision_number: number;
  evidence_count: number;
  updated_at: string;
}>;

export type ReviewEvidence = Readonly<{
  evidence_id: string;
  source_document_id: string;
  source_document_title: string;
  source_file_name: string;
  document_version_id: string;
  source_file_sha256: string;
  source_chunk_id: string;
  source_chunk: string;
  evidence_snippet: string;
  char_start: number;
  char_end: number;
  locator: Readonly<Record<string, unknown>>;
  support_role: "primary" | "corroborating" | "qualifying" | "contradicting";
  confidence: number;
}>;

export type ReviewCandidateDetail = Readonly<{
  item: ReviewQueueItem;
  canonical_key: string;
  description: string | null;
  properties: Readonly<Record<string, unknown>>;
  formula_latex: string | null;
  source_candidate_id: string | null;
  target_candidate_id: string | null;
  evidence: readonly ReviewEvidence[];
}>;

export type CandidateActionResponse = Readonly<{
  candidate_id: string;
  kind: "node" | "relation";
  action: "approve" | "reject" | "edit" | "merge";
  decision_id: string;
  projection_state: "pending_upsert" | "pending_delete" | "not_published";
}>;

export type PhaseOneApiError = Readonly<{
  error: Readonly<{
    code: string;
    message: string;
    trace_id?: string;
  }>;
}>;

export class ContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractError";
  }
}

type UnknownRecord = Record<string, unknown>;

function fail(path: string, expected: string): never {
  throw new ContractError(`${path} must be ${expected}`);
}

function record(value: unknown, path: string): UnknownRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return fail(path, "an object");
  }
  return value as UnknownRecord;
}

function array(value: unknown, path: string): readonly unknown[] {
  if (!Array.isArray(value)) return fail(path, "an array");
  return value;
}

function string(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) {
    return fail(path, "a non-empty string");
  }
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : string(value, path, true);
}

function finiteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fail(path, "a finite number");
  }
  return value;
}

function nonNegativeInteger(value: unknown, path: string): number {
  const parsed = finiteNumber(value, path);
  if (!Number.isInteger(parsed) || parsed < 0) return fail(path, "a non-negative integer");
  return parsed;
}

function positiveInteger(value: unknown, path: string): number {
  const parsed = nonNegativeInteger(value, path);
  if (parsed === 0) return fail(path, "a positive integer");
  return parsed;
}

function nullablePositiveInteger(value: unknown, path: string): number | null {
  return value === null ? null : positiveInteger(value, path);
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "a boolean");
  return value;
}

function uuid(value: unknown, path: string): string {
  const parsed = string(value, path);
  if (!UUID_PATTERN.test(parsed)) return fail(path, "a UUID");
  return parsed;
}

function sha256(value: unknown, path: string): string {
  const parsed = string(value, path);
  if (!SHA256_PATTERN.test(parsed)) return fail(path, "a lowercase SHA-256 digest");
  return parsed;
}

function stringArray(value: unknown, path: string): readonly string[] {
  return array(value, path).map((item, index) => string(item, `${path}[${index}]`, true));
}

function enumValue<const T extends string>(
  value: unknown,
  values: readonly T[],
  path: string,
): T {
  const parsed = string(value, path);
  if (!values.includes(parsed as T)) return fail(path, values.join(" | "));
  return parsed as T;
}

function parseLocator(value: unknown, path: string): EvidenceLocator {
  const input = record(value, path);
  const locatorType = enumValue(
    input.locator_type,
    ["pdf_page", "slide", "docx_paragraph", "xlsx_row", "text_lines"] as const,
    `${path}.locator_type`,
  );
  const locator: EvidenceLocator = {
    locator_type: locatorType,
    physical_page: nullablePositiveInteger(input.physical_page, `${path}.physical_page`),
    printed_page_label: nullableString(input.printed_page_label, `${path}.printed_page_label`),
    slide_number: nullablePositiveInteger(input.slide_number, `${path}.slide_number`),
    paragraph_start: nullablePositiveInteger(input.paragraph_start, `${path}.paragraph_start`),
    paragraph_end: nullablePositiveInteger(input.paragraph_end, `${path}.paragraph_end`),
    sheet_name: nullableString(input.sheet_name, `${path}.sheet_name`),
    row_start: nullablePositiveInteger(input.row_start, `${path}.row_start`),
    row_end: nullablePositiveInteger(input.row_end, `${path}.row_end`),
    line_start: nullablePositiveInteger(input.line_start, `${path}.line_start`),
    line_end: nullablePositiveInteger(input.line_end, `${path}.line_end`),
  };

  const complete =
    (locatorType === "pdf_page" && locator.physical_page !== null) ||
    (locatorType === "slide" && locator.slide_number !== null) ||
    (locatorType === "docx_paragraph" && locator.paragraph_start !== null) ||
    (locatorType === "xlsx_row" && locator.sheet_name !== null && locator.row_start !== null) ||
    (locatorType === "text_lines" && locator.line_start !== null);
  if (!complete) fail(path, `a complete ${locatorType} locator`);
  return locator;
}

function parseCitation(value: unknown, path: string): StudentCitation {
  const input = record(value, path);
  const sourceChunk = string(input.source_chunk, `${path}.source_chunk`);
  const evidenceSnippet = string(input.evidence_snippet, `${path}.evidence_snippet`);
  const start = nonNegativeInteger(input.evidence_char_start, `${path}.evidence_char_start`);
  const end = positiveInteger(input.evidence_char_end, `${path}.evidence_char_end`);
  if (end > sourceChunk.length || sourceChunk.slice(start, end) !== evidenceSnippet) {
    fail(path, "an exact evidence span within source_chunk");
  }
  return {
    evidence_id: uuid(input.evidence_id, `${path}.evidence_id`),
    source_chunk_id: uuid(input.source_chunk_id, `${path}.source_chunk_id`),
    source_document_id: uuid(input.source_document_id, `${path}.source_document_id`),
    document_version_id: uuid(input.document_version_id, `${path}.document_version_id`),
    document_title: string(input.document_title, `${path}.document_title`),
    document_version: positiveInteger(input.document_version, `${path}.document_version`),
    source_file_name: string(input.source_file_name, `${path}.source_file_name`),
    source_file_sha256: sha256(input.source_file_sha256, `${path}.source_file_sha256`),
    source_chunk_sha256: sha256(input.source_chunk_sha256, `${path}.source_chunk_sha256`),
    evidence_sha256: sha256(input.evidence_sha256, `${path}.evidence_sha256`),
    chapter: nullableString(input.chapter, `${path}.chapter`),
    section_path: stringArray(input.section_path, `${path}.section_path`),
    locator: parseLocator(input.locator, `${path}.locator`),
    source_chunk: sourceChunk,
    evidence_snippet: evidenceSnippet,
    evidence_char_start: start,
    evidence_char_end: end,
    kind: string(input.kind, `${path}.kind`),
  };
}

function parseNode(value: unknown, path: string): StudentGraphNode {
  const input = record(value, path);
  const citations = array(input.citations, `${path}.citations`).map((item, index) =>
    parseCitation(item, `${path}.citations[${index}]`),
  );
  if (citations.length === 0) fail(`${path}.citations`, "a non-empty evidence array");
  return {
    id: uuid(input.id, `${path}.id`),
    node_type: string(input.node_type, `${path}.node_type`),
    canonical_key: string(input.canonical_key, `${path}.canonical_key`),
    label: string(input.label, `${path}.label`),
    description: nullableString(input.description, `${path}.description`),
    aliases: stringArray(input.aliases, `${path}.aliases`),
    formula_latex: nullableString(input.formula_latex, `${path}.formula_latex`),
    citations,
  };
}

function parseEdge(value: unknown, path: string): StudentGraphEdge {
  const input = record(value, path);
  const citations = array(input.citations, `${path}.citations`).map((item, index) =>
    parseCitation(item, `${path}.citations[${index}]`),
  );
  if (citations.length === 0) fail(`${path}.citations`, "a non-empty evidence array");
  return {
    id: uuid(input.id, `${path}.id`),
    source_id: uuid(input.source_id, `${path}.source_id`),
    target_id: uuid(input.target_id, `${path}.target_id`),
    relationship_type: string(input.relationship_type, `${path}.relationship_type`),
    citations,
  };
}

function parseScopedEnvelope(input: UnknownRecord, path: string) {
  return {
    course_id: uuid(input.course_id, `${path}.course_id`),
    curriculum_edition_id: uuid(
      input.curriculum_edition_id,
      `${path}.curriculum_edition_id`,
    ),
    degraded: boolean(input.degraded, `${path}.degraded`),
    warnings: stringArray(input.warnings, `${path}.warnings`),
  };
}

export function parseConceptSearchResponse(value: unknown): ConceptSearchResponse {
  const input = record(value, "conceptSearch");
  const scoped = parseScopedEnvelope(input, "conceptSearch");
  return {
    ...scoped,
    query: string(input.query, "conceptSearch.query"),
    results: array(input.results, "conceptSearch.results").map((item, index) => {
      const hit = record(item, `conceptSearch.results[${index}]`);
      const score = finiteNumber(hit.score, `conceptSearch.results[${index}].score`);
      if (score < 0) fail(`conceptSearch.results[${index}].score`, "non-negative");
      return {
        node: parseNode(hit.node, `conceptSearch.results[${index}].node`),
        score,
      };
    }),
  };
}

export function parseStudentSubgraphResponse(value: unknown): StudentSubgraphResponse {
  const input = record(value, "subgraph");
  const scoped = parseScopedEnvelope(input, "subgraph");
  const nodes = array(input.nodes, "subgraph.nodes").map((item, index) =>
    parseNode(item, `subgraph.nodes[${index}]`),
  );
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = array(input.edges, "subgraph.edges").map((item, index) =>
    parseEdge(item, `subgraph.edges[${index}]`),
  );
  for (const [index, edge] of edges.entries()) {
    if (!nodeIds.has(edge.source_id) || !nodeIds.has(edge.target_id)) {
      fail(`subgraph.edges[${index}]`, "an edge whose endpoints are visible nodes");
    }
  }
  const rootCandidateId = uuid(input.root_candidate_id, "subgraph.root_candidate_id");
  const rootVisible = boolean(input.root_visible, "subgraph.root_visible");
  if (rootVisible !== nodeIds.has(rootCandidateId)) {
    fail("subgraph.root_visible", "consistent with the returned node set");
  }
  return {
    ...scoped,
    root_candidate_id: rootCandidateId,
    root_visible: rootVisible,
    nodes,
    edges,
  };
}

export function parsePrerequisitePathsResponse(value: unknown): PrerequisitePathsResponse {
  const input = record(value, "prerequisites");
  const scoped = parseScopedEnvelope(input, "prerequisites");
  const paths = array(input.paths, "prerequisites.paths").map((item, pathIndex) => {
    const path = record(item, `prerequisites.paths[${pathIndex}]`);
    const nodes = array(path.nodes, `prerequisites.paths[${pathIndex}].nodes`).map(
      (node, index) => parseNode(node, `prerequisites.paths[${pathIndex}].nodes[${index}]`),
    );
    const edges = array(path.edges, `prerequisites.paths[${pathIndex}].edges`).map(
      (edge, index) => parseEdge(edge, `prerequisites.paths[${pathIndex}].edges[${index}]`),
    );
    if (nodes.length < 2 || edges.length !== nodes.length - 1) {
      fail(`prerequisites.paths[${pathIndex}]`, "an n-node, n-1-edge path");
    }
    edges.forEach((edge, index) => {
      if (
        edge.relationship_type !== "PREREQUISITE_OF" ||
        edge.source_id !== nodes[index]?.id ||
        edge.target_id !== nodes[index + 1]?.id
      ) {
        fail(
          `prerequisites.paths[${pathIndex}].edges[${index}]`,
          "an ordered PREREQUISITE_OF edge",
        );
      }
    });
    return { nodes, edges };
  });
  return {
    ...scoped,
    target_candidate_id: uuid(
      input.target_candidate_id,
      "prerequisites.target_candidate_id",
    ),
    paths,
  };
}

function parseReviewQueueItem(value: unknown, path: string): ReviewQueueItem {
  const input = record(value, path);
  const updatedAt = string(input.updated_at, `${path}.updated_at`);
  if (Number.isNaN(Date.parse(updatedAt))) fail(`${path}.updated_at`, "an ISO date-time");
  const confidence = finiteNumber(input.confidence, `${path}.confidence`);
  if (confidence < 0 || confidence > 1) fail(`${path}.confidence`, "between 0 and 1");
  return {
    candidate_id: uuid(input.candidate_id, `${path}.candidate_id`),
    kind: enumValue(input.kind, ["node", "relation"] as const, `${path}.kind`),
    status: enumValue(
      input.status,
      ["review_required", "in_review", "approved", "rejected", "superseded"] as const,
      `${path}.status`,
    ),
    type_name: string(input.type_name, `${path}.type_name`),
    label: string(input.label, `${path}.label`),
    confidence,
    revision_number: positiveInteger(input.revision_number, `${path}.revision_number`),
    evidence_count: nonNegativeInteger(input.evidence_count, `${path}.evidence_count`),
    updated_at: updatedAt,
  };
}

export function parseReviewQueueResponse(value: unknown): readonly ReviewQueueItem[] {
  return array(value, "reviewQueue").map((item, index) =>
    parseReviewQueueItem(item, `reviewQueue[${index}]`),
  );
}

function parseReviewEvidence(value: unknown, path: string): ReviewEvidence {
  const input = record(value, path);
  const sourceChunk = string(input.source_chunk, `${path}.source_chunk`);
  const evidenceSnippet = string(input.evidence_snippet, `${path}.evidence_snippet`);
  const start = nonNegativeInteger(input.char_start, `${path}.char_start`);
  const end = positiveInteger(input.char_end, `${path}.char_end`);
  if (end > sourceChunk.length || sourceChunk.slice(start, end) !== evidenceSnippet) {
    fail(path, "an exact evidence span within source_chunk");
  }
  const confidence = finiteNumber(input.confidence, `${path}.confidence`);
  if (confidence < 0 || confidence > 1) fail(`${path}.confidence`, "between 0 and 1");
  return {
    evidence_id: uuid(input.evidence_id, `${path}.evidence_id`),
    source_document_id: uuid(input.source_document_id, `${path}.source_document_id`),
    source_document_title: string(input.source_document_title, `${path}.source_document_title`),
    source_file_name: string(input.source_file_name, `${path}.source_file_name`),
    document_version_id: uuid(input.document_version_id, `${path}.document_version_id`),
    source_file_sha256: sha256(input.source_file_sha256, `${path}.source_file_sha256`),
    source_chunk_id: uuid(input.source_chunk_id, `${path}.source_chunk_id`),
    source_chunk: sourceChunk,
    evidence_snippet: evidenceSnippet,
    char_start: start,
    char_end: end,
    locator: record(input.locator, `${path}.locator`),
    support_role: enumValue(
      input.support_role,
      ["primary", "corroborating", "qualifying", "contradicting"] as const,
      `${path}.support_role`,
    ),
    confidence,
  };
}

export function parseReviewCandidateDetail(value: unknown): ReviewCandidateDetail {
  const input = record(value, "reviewDetail");
  return {
    item: parseReviewQueueItem(input.item, "reviewDetail.item"),
    canonical_key: string(input.canonical_key, "reviewDetail.canonical_key"),
    description: nullableString(input.description, "reviewDetail.description"),
    properties: record(input.properties, "reviewDetail.properties"),
    formula_latex: nullableString(input.formula_latex, "reviewDetail.formula_latex"),
    source_candidate_id:
      input.source_candidate_id === null
        ? null
        : uuid(input.source_candidate_id, "reviewDetail.source_candidate_id"),
    target_candidate_id:
      input.target_candidate_id === null
        ? null
        : uuid(input.target_candidate_id, "reviewDetail.target_candidate_id"),
    evidence: array(input.evidence, "reviewDetail.evidence").map((item, index) =>
      parseReviewEvidence(item, `reviewDetail.evidence[${index}]`),
    ),
  };
}

export function parseCandidateActionResponse(value: unknown): CandidateActionResponse {
  const input = record(value, "candidateAction");
  return {
    candidate_id: uuid(input.candidate_id, "candidateAction.candidate_id"),
    kind: enumValue(input.kind, ["node", "relation"] as const, "candidateAction.kind"),
    action: enumValue(
      input.action,
      ["approve", "reject", "edit", "merge"] as const,
      "candidateAction.action",
    ),
    decision_id: uuid(input.decision_id, "candidateAction.decision_id"),
    projection_state: enumValue(
      input.projection_state,
      ["pending_upsert", "pending_delete", "not_published"] as const,
      "candidateAction.projection_state",
    ),
  };
}

export function assertResponseScope(
  value: { course_id: string; curriculum_edition_id: string },
  scope: PhaseOneScope,
): void {
  if (
    value.course_id !== scope.courseId ||
    value.curriculum_edition_id !== scope.curriculumEditionId
  ) {
    throw new ContractError("response scope does not match the requested course edition");
  }
}

export function isValidScope(scope: PhaseOneScope): boolean {
  return UUID_PATTERN.test(scope.courseId) && UUID_PATTERN.test(scope.curriculumEditionId);
}

export function parseApiError(value: unknown): PhaseOneApiError | null {
  try {
    const envelope = record(value, "apiError");
    const error = record(envelope.error, "apiError.error");
    const traceId = error.trace_id;
    return {
      error: {
        code: string(error.code, "apiError.error.code"),
        message: string(error.message, "apiError.error.message"),
        ...(typeof traceId === "string" && traceId.length > 0 ? { trace_id: traceId } : {}),
      },
    };
  } catch {
    return null;
  }
}

export function locatorLabel(locator: EvidenceLocator | Readonly<Record<string, unknown>>): string {
  const type = locator.locator_type;
  if (type === "pdf_page" && typeof locator.physical_page === "number") {
    const printed =
      typeof locator.printed_page_label === "string" && locator.printed_page_label.length > 0
        ? `（印刷页 ${locator.printed_page_label}）`
        : "";
    return `PDF 物理页 ${locator.physical_page}${printed}`;
  }
  if (type === "slide" && typeof locator.slide_number === "number") {
    return `幻灯片 ${locator.slide_number}`;
  }
  if (type === "docx_paragraph" && typeof locator.paragraph_start === "number") {
    const end = typeof locator.paragraph_end === "number" ? locator.paragraph_end : locator.paragraph_start;
    return end === locator.paragraph_start
      ? `段落 ${locator.paragraph_start}`
      : `段落 ${locator.paragraph_start}–${end}`;
  }
  if (
    type === "xlsx_row" &&
    typeof locator.sheet_name === "string" &&
    typeof locator.row_start === "number"
  ) {
    const end = typeof locator.row_end === "number" ? locator.row_end : locator.row_start;
    return `${locator.sheet_name} · 行 ${locator.row_start}${end === locator.row_start ? "" : `–${end}`}`;
  }
  if (type === "text_lines" && typeof locator.line_start === "number") {
    const end = typeof locator.line_end === "number" ? locator.line_end : locator.line_start;
    return `文本行 ${locator.line_start}${end === locator.line_start ? "" : `–${end}`}`;
  }
  return "来源位置未标注（需复核）";
}
