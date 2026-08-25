import assert from "node:assert/strict";
import test from "node:test";

import {
  ContractError,
  assertResponseScope,
  parseConceptSearchResponse,
  parsePrerequisitePathsResponse,
  parseReviewCandidateDetail,
  parseStudentSubgraphResponse,
} from "./contracts";

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const NODE_ID = "33333333-3333-4333-8333-333333333333";
const OTHER_NODE_ID = "44444444-4444-4444-8444-444444444444";
const EDGE_ID = "55555555-5555-4555-8555-555555555555";
const EVIDENCE_ID = "66666666-6666-4666-8666-666666666666";
const CHUNK_ID = "77777777-7777-4777-8777-777777777777";
const DOCUMENT_ID = "88888888-8888-4888-8888-888888888888";
const VERSION_ID = "99999999-9999-4999-8999-999999999999";

function citation() {
  const sourceChunk = "量子力学用波函数描述微观粒子的状态。";
  const evidenceSnippet = "波函数描述微观粒子的状态";
  const start = sourceChunk.indexOf(evidenceSnippet);
  return {
    evidence_id: EVIDENCE_ID,
    source_chunk_id: CHUNK_ID,
    source_document_id: DOCUMENT_ID,
    document_version_id: VERSION_ID,
    document_title: "量子力学讲义",
    document_version: 1,
    source_file_name: "量子力学讲义.pdf",
    source_file_sha256: "a".repeat(64),
    source_chunk_sha256: "b".repeat(64),
    evidence_sha256: "c".repeat(64),
    chapter: "第二章 量子力学基础",
    section_path: ["波函数"],
    locator: {
      locator_type: "pdf_page",
      physical_page: 13,
      printed_page_label: "1",
      slide_number: null,
      paragraph_start: null,
      paragraph_end: null,
      sheet_name: null,
      row_start: null,
      row_end: null,
      line_start: null,
      line_end: null,
    },
    source_chunk: sourceChunk,
    evidence_snippet: evidenceSnippet,
    evidence_char_start: start,
    evidence_char_end: start + evidenceSnippet.length,
    kind: "course_material",
  };
}

function node(id = NODE_ID, label = "波函数") {
  return {
    id,
    node_type: "Concept",
    canonical_key: `concept:${label}`,
    label,
    description: "课程中的概念说明",
    aliases: [],
    formula_latex: null,
    citations: [citation()],
  };
}

test("student concept response accepts scoped, exact course evidence", () => {
  const result = parseConceptSearchResponse({
    course_id: COURSE_ID,
    curriculum_edition_id: EDITION_ID,
    query: "波函数",
    results: [{ node: node(), score: 0.92 }],
    degraded: false,
    warnings: [],
  });
  assert.equal(result.results[0]?.node.citations[0]?.locator.physical_page, 13);
  assert.doesNotThrow(() =>
    assertResponseScope(result, { courseId: COURSE_ID, curriculumEditionId: EDITION_ID }),
  );
});

test("browser contract rejects a citation snippet outside its source chunk", () => {
  const badCitation = { ...citation(), evidence_snippet: "系统补写的句子" };
  assert.throws(
    () =>
      parseConceptSearchResponse({
        course_id: COURSE_ID,
        curriculum_edition_id: EDITION_ID,
        query: "波函数",
        results: [{ node: { ...node(), citations: [badCitation] }, score: 1 }],
        degraded: false,
        warnings: [],
      }),
    ContractError,
  );
});

test("browser contract rejects a subgraph edge with a hidden endpoint", () => {
  assert.throws(
    () =>
      parseStudentSubgraphResponse({
        course_id: COURSE_ID,
        curriculum_edition_id: EDITION_ID,
        root_candidate_id: NODE_ID,
        root_visible: true,
        nodes: [node()],
        edges: [
          {
            id: EDGE_ID,
            source_id: NODE_ID,
            target_id: OTHER_NODE_ID,
            relationship_type: "RELATED_TO",
            citations: [citation()],
          },
        ],
        degraded: false,
        warnings: [],
      }),
    ContractError,
  );
});

test("prerequisite paths must preserve ordered PREREQUISITE_OF edges", () => {
  const parsed = parsePrerequisitePathsResponse({
    course_id: COURSE_ID,
    curriculum_edition_id: EDITION_ID,
    target_candidate_id: OTHER_NODE_ID,
    paths: [
      {
        nodes: [node(), node(OTHER_NODE_ID, "统计解释")],
        edges: [
          {
            id: EDGE_ID,
            source_id: NODE_ID,
            target_id: OTHER_NODE_ID,
            relationship_type: "PREREQUISITE_OF",
            citations: [citation()],
          },
        ],
      },
    ],
    degraded: false,
    warnings: [],
  });
  assert.equal(parsed.paths[0]?.nodes[1]?.label, "统计解释");

  assert.throws(
    () =>
      parsePrerequisitePathsResponse({
        course_id: COURSE_ID,
        curriculum_edition_id: EDITION_ID,
        target_candidate_id: OTHER_NODE_ID,
        paths: [
          {
            nodes: [node(), node(OTHER_NODE_ID, "统计解释")],
            edges: [
              {
                id: EDGE_ID,
                source_id: NODE_ID,
                target_id: OTHER_NODE_ID,
                relationship_type: "RELATED_TO",
                citations: [citation()],
              },
            ],
          },
        ],
        degraded: false,
        warnings: [],
      }),
    ContractError,
  );
});

test("teacher detail accepts review evidence only when the source span is exact", () => {
  const sourceChunk = "工作表行：波函数的统计解释";
  const snippet = "波函数的统计解释";
  const detail = parseReviewCandidateDetail({
    item: {
      candidate_id: NODE_ID,
      kind: "node",
      status: "review_required",
      type_name: "concept",
      label: snippet,
      confidence: 1,
      revision_number: 1,
      evidence_count: 1,
      updated_at: "2026-08-22T01:00:00Z",
    },
    canonical_key: "taxonomy:wavefunction-statistical-interpretation",
    description: null,
    properties: {},
    formula_latex: null,
    source_candidate_id: null,
    target_candidate_id: null,
    evidence: [
      {
        evidence_id: EVIDENCE_ID,
        source_document_id: DOCUMENT_ID,
        source_document_title: "知识点分类",
        source_file_name: "知识点分类.xlsx",
        document_version_id: VERSION_ID,
        source_file_sha256: "d".repeat(64),
        source_chunk_id: CHUNK_ID,
        source_chunk: sourceChunk,
        evidence_snippet: snippet,
        char_start: sourceChunk.indexOf(snippet),
        char_end: sourceChunk.indexOf(snippet) + snippet.length,
        locator: { locator_type: "xlsx_row", sheet_name: "Sheet3", row_start: 41 },
        support_role: "primary",
        confidence: 1,
      },
    ],
  });
  assert.equal(detail.evidence[0]?.locator.row_start, 41);
});
