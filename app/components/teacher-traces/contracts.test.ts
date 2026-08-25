import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { WORKFLOW_ORDER } from "../teaching/contracts";
import {
  assertEditedResponseAuthority,
  parseAgentTraceDetail,
  parseAgentTracePage,
  parseHitlRejectedResponse,
  parseReviewDecision,
} from "./contracts";

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const TRACE_ID = "33333333-3333-4333-8333-333333333333";
const TURN_ID = "44444444-4444-4444-8444-444444444444";
const CONVERSATION_ID = "55555555-5555-4555-8555-555555555555";
const STUDENT_ID = "66666666-6666-4666-8666-666666666666";
const EVIDENCE_ID = "77777777-7777-4777-8777-777777777777";
const CHUNK_ID = "88888888-8888-4888-8888-888888888888";
const DOCUMENT_ID = "99999999-9999-4999-8999-999999999999";
const VERSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const PACKET_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const INTERRUPT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const CONCEPT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const PREREQUISITE_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const RELATION_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const SHA = "a".repeat(64);

const scope = { courseId: COURSE_ID, curriculumEditionId: EDITION_ID } as const;

function evidence() {
  return {
    evidence_id: EVIDENCE_ID,
    chunk_id: CHUNK_ID,
    document_id: DOCUMENT_ID,
    document_version_id: VERSION_ID,
    document_title: "Griffiths 量子力学概论",
    document_version: 3,
    source_file_name: "griffiths.pdf",
    source_file_sha256: SHA,
    source_chunk_sha256: SHA,
    evidence_sha256: SHA,
    curriculum_edition_id: EDITION_ID,
    chapter: "第二章",
    section_path: ["定态薛定谔方程"],
    locator: {
      locator_type: "pdf_page",
      physical_page: 47,
      printed_page_label: "31",
      slide_number: null,
      paragraph_start: null,
      paragraph_end: null,
      sheet_name: null,
      row_start: null,
      row_end: null,
      line_start: null,
      line_end: null,
    },
    source_chunk: "边界条件要求波函数及其一阶导数满足相应的连续性。",
    evidence_snippet: "边界条件要求波函数及其一阶导数满足相应的连续性。",
    kind: "course_material",
    authority_priority: 100,
    contributions: [
      { channel: "postgres_full_text", rank: 1, raw_score: 0.9, fused_score: 0.7 },
    ],
  };
}

function citation() {
  const value: Record<string, unknown> = { ...evidence() };
  delete value.curriculum_edition_id;
  delete value.source_chunk;
  delete value.contributions;
  return value;
}

function traceSummary() {
  return {
    id: TRACE_ID,
    teaching_turn_id: TURN_ID,
    conversation_id: CONVERSATION_ID,
    student_user_id: STUDENT_ID,
    mode: "review_derivations",
    sequence_number: 2,
    task_kind: "derivation_check",
    teaching_action: "check_derivation_step",
    release_level: "hint",
    turn_status: "running",
    workflow_version: "teaching-state-machine/2.1.0",
    model_gateway_status: "validated",
    citation_validation_status: "passed",
    created_at: "2026-08-24T08:15:00Z",
    completed_at: null,
  };
}

function validDetail(): Record<string, unknown> {
  const prerequisite = {
    id: PREREQUISITE_ID,
    node_type: "Concept",
    name: "边界条件",
    aliases: [],
  };
  const target = {
    id: CONCEPT_ID,
    node_type: "Concept",
    name: "有限深方势阱",
    aliases: [],
  };
  const packet = {
    id: PACKET_ID,
    course_id: COURSE_ID,
    curriculum_edition_id: EDITION_ID,
    query: "检查有限深方势阱边界匹配",
    created_at: "2026-08-24T08:15:01Z",
    coverage: "sufficient",
    evidence: [evidence()],
    graph_nodes: [prerequisite, target],
    graph_edges: [
      { id: RELATION_ID, source_id: PREREQUISITE_ID, target_id: CONCEPT_ID, relation_type: "PREREQUISITE_OF" },
    ],
    degraded_channels: [],
    warnings: ["reranker unavailable; deterministic fused rank retained"],
  };
  const diagnosis = {
    status: "model_inference",
    summary: "学生在第二步错误地交换了导数连续条件的左右两侧。",
    likely_misconception: "认为有限势垒允许波函数导数跳变",
    observation_basis: ["student_attempt", "course_evidence"],
    target_concepts: ["有限深方势阱"],
    first_error: {
      inferred: true,
      step_index: 1,
      kind: "boundary_condition_error",
      description: "导数匹配条件符号错误",
    },
    misconception_candidates: [
      { statement: "有限势垒处导数可以不连续", confidence: 0.82 },
    ],
    missing_prerequisites: ["边界条件"],
    progress_state: "struggling",
    confidence: 0.84,
    verification_needed: true,
    reason: "学生尝试的第二步与引用课程材料中的连续条件不一致。",
  };
  const policy = {
    policy_id: null,
    source: "safe_default",
    mode: "review_derivations",
    allow_full_solution: false,
    minimum_attempts_for_scaffold: 1,
    minimum_attempts_for_full_solution: 2,
    max_hint_level: 3,
  };
  const release = {
    action: "check_derivation_step",
    release_level: "hint",
    attempts_observed: 1,
    reason_code: "FIRST_ERROR_MINIMAL_HINT",
  };
  const response = {
    orientation: "先重新检查势垒两侧的一阶导数匹配。",
    claims: [],
    next_question: "把 x=0 两侧的一阶导数分别写出后，它们应满足什么关系？",
    status: "grounded",
    limitations: [],
  };
  const validation = {
    passed: true,
    citation_ids_valid: true,
    literal_course_claims_valid: true,
    scientific_references_valid: true,
    warnings: [],
  };
  return {
    ...traceSummary(),
    user_message: "请检查我的有限深方势阱推导。",
    student_attempt: "第一步正确。第二步令 ψ'(0-) = -ψ'(0+)。",
    workflow_steps: WORKFLOW_ORDER.map((name) => ({
      name,
      status: name === "record_learning_evidence" ? "skipped" : "completed",
      detail: `${name} recorded`,
    })),
    policy_snapshot: policy,
    evidence_packet: packet,
    evidence_bundle: {
      course_id: COURSE_ID,
      curriculum_edition_id: EDITION_ID,
      query: "检查有限深方势阱边界匹配",
      retrieval_query: "有限深方势阱 导数 连续 边界条件",
      coverage: "sufficient",
      coverage_rationale: "课程材料直接覆盖导数连续条件。",
      source_chunks: [evidence()],
      citations: [citation()],
      relevant_concepts: [target],
      graph_nodes: [prerequisite, target],
      graph_edges: packet.graph_edges,
      prerequisite_paths: [
        { relation_id: RELATION_ID, prerequisite, target },
      ],
      misconception_links: [],
      formulas: [],
      degraded_channels: [],
      warnings: ["reranker unavailable; deterministic fused rank retained"],
      conflicts: [],
    },
    diagnosis,
    release_decision: release,
    response,
    scientific_results: [],
    validation,
    hitl_events: [
      {
        interrupt: {
          schema_version: "quantum-agent-hitl/1.0.0",
          interrupt_id: INTERRUPT_ID,
          thread_id: CONVERSATION_ID,
          conversation_id: CONVERSATION_ID,
          turn_id: TURN_ID,
          stage: "pre_release_review",
          reasons: ["verifier_model_disagreement"],
          prompt: "验证器与诊断结果需要教学团队检查。",
          student_allowed_actions: [],
          staff_allowed_actions: ["approve", "reject", "edit", "take_over"],
        },
        resolution: null,
      },
    ],
    failure_code: null,
  };
}

test("trace contracts preserve full citation locators and directed prerequisites", () => {
  const parsed = parseAgentTraceDetail(validDetail(), scope, TRACE_ID);
  assert.equal(parsed.evidence_bundle?.citations[0]?.locator.physical_page, 47);
  assert.equal(parsed.evidence_bundle?.citations[0]?.locator.printed_page_label, "31");
  assert.equal(parsed.evidence_bundle?.prerequisite_paths[0]?.prerequisite.name, "边界条件");
  assert.equal(parsed.evidence_bundle?.prerequisite_paths[0]?.target.name, "有限深方势阱");
  assert.equal(parsed.diagnosis?.confidence, 0.84);
  assert.match(parsed.diagnosis?.reason ?? "", /课程材料/);
});

test("trace page rejects cross-course payloads and unknown model fields", () => {
  assert.throws(() =>
    parseAgentTracePage(
      {
        course_id: "01234567-89ab-4cde-8fab-0123456789ab",
        curriculum_edition_id: EDITION_ID,
        items: [],
        total: 0,
        limit: 25,
        offset: 0,
        has_more: false,
      },
      scope,
    ),
  );
  assert.throws(() =>
    parseAgentTracePage(
      {
        course_id: COURSE_ID,
        curriculum_edition_id: EDITION_ID,
        items: [{ ...traceSummary(), concrete_model_name: "forbidden" }],
        total: 1,
        limit: 25,
        offset: 0,
        has_more: false,
      },
      scope,
    ),
  );
});

test("trace detail rejects malformed locators and HITL ownership mismatches", () => {
  const badLocator = structuredClone(validDetail());
  const bundle = badLocator.evidence_bundle as Record<string, unknown>;
  const citations = bundle.citations as Array<Record<string, unknown>>;
  citations[0] = {
    ...citations[0],
    locator: {
      locator_type: "pdf_page",
      physical_page: null,
      printed_page_label: null,
      slide_number: null,
      paragraph_start: null,
      paragraph_end: null,
      sheet_name: null,
      row_start: null,
      row_end: null,
      line_start: null,
      line_end: null,
    },
  };
  assert.throws(() => parseAgentTraceDetail(badLocator, scope, TRACE_ID));

  const wrongThread = structuredClone(validDetail());
  const hitlEvents = wrongThread.hitl_events as Array<Record<string, unknown>>;
  const interrupt = hitlEvents[0]?.interrupt as Record<string, unknown>;
  interrupt.conversation_id = "01234567-89ab-4cde-8fab-0123456789ab";
  interrupt.thread_id = interrupt.conversation_id;
  assert.throws(() => parseAgentTraceDetail(wrongThread, scope, TRACE_ID));
});

test("review decisions require bounded edits and auditable reject/take-over notes", () => {
  assert.deepEqual(
    parseReviewDecision({ interrupt_id: INTERRUPT_ID, action: "approve", note: null }),
    { interrupt_id: INTERRUPT_ID, action: "approve", note: null },
  );
  assert.throws(() =>
    parseReviewDecision({ interrupt_id: INTERRUPT_ID, action: "reject", note: "   " }),
  );
  assert.throws(() =>
    parseReviewDecision({ interrupt_id: INTERRUPT_ID, action: "take_over", note: "接管" }),
  );
  assert.throws(() =>
    parseReviewDecision({ interrupt_id: INTERRUPT_ID, action: "approve", note: null, model: "x" }),
  );

  const proposed = validDetail().response;
  const edited = parseReviewDecision({
    interrupt_id: INTERRUPT_ID,
    action: "edit",
    note: "缩短提示措辞",
    edited_response: proposed,
  });
  assert.equal(edited.action, "edit");
  assert.throws(() =>
    parseReviewDecision({
      interrupt_id: INTERRUPT_ID,
      action: "take_over",
      note: "   ",
      edited_response: proposed,
    }),
  );
});

test("staff edits cannot manufacture citation or tool authority", () => {
  const inspected = {
    orientation: "先检查边界。",
    claims: [
      {
        text: "原声明",
        support_basis: "course_material" as const,
        evidence_ids: [EVIDENCE_ID],
        scientific_result_ids: [],
      },
    ],
    next_question: "条件是什么？",
    status: "grounded" as const,
    limitations: [],
  };
  assert.doesNotThrow(() =>
    assertEditedResponseAuthority(
      {
        ...inspected,
        orientation: "请只检查边界条件。",
        claims: [{ ...inspected.claims[0]!, text: "修改后的受支持声明" }],
      },
      inspected,
    ),
  );
  assert.throws(() =>
    assertEditedResponseAuthority(
      {
        ...inspected,
        claims: [
          {
            ...inspected.claims[0]!,
            evidence_ids: ["01234567-89ab-4cde-8fab-0123456789ab"],
          },
        ],
      },
      inspected,
    ),
  );
  assert.throws(() =>
    assertEditedResponseAuthority(
      { ...inspected, claims: [], status: "mixed" },
      inspected,
    ),
  );
});

test("rejected HITL outcomes remain strict and turn-scoped", () => {
  const rejected = parseHitlRejectedResponse({
    status: "rejected",
    conversation_id: CONVERSATION_ID,
    turn_id: TURN_ID,
    interrupt_id: INTERRUPT_ID,
    reason_code: "HITL_REJECTED",
  });
  assert.equal(rejected.interrupt_id, INTERRUPT_ID);
  assert.throws(() => parseHitlRejectedResponse({ ...rejected, reason_code: "MODEL_REJECTED" }));
});

test("staff BFF uses qa_session and never legacy teacher credentials", async () => {
  const shared = await readFile(
    new URL("../../api/teacher/traces/_shared.ts", import.meta.url),
    "utf8",
  );
  const review = await readFile(
    new URL("../../api/teacher/traces/[traceId]/review/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(shared, /get\("qa_session"\)/);
  assert.doesNotMatch(shared, /TEACHER_PASSWORD|qa_teacher/);
  assert.match(review, /requireSameOrigin\(request\)/);
  assert.match(review, /loadCurrentReview/);
  assert.match(review, /assertEditedResponseAuthority/);
  assert.match(review, /edited_response/);
});
