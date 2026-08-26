import assert from "node:assert/strict";
import test from "node:test";

import {
  WORKFLOW_ORDER,
  assertHitlScope,
  assertTeachingScope,
  parseHitlInterruptResponse,
  parseStudentHitlResumeRequest,
  parseTeachingTurnRequest,
  parseTeachingTurnResult,
  parseTeachingWorkflowOutcome,
  redactHitlProposedResponse,
} from "./contracts";

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const EDITION_ID = "22222222-2222-4222-8222-222222222222";
const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";
const TURN_ID = "44444444-4444-4444-8444-444444444444";
const EVIDENCE_ID = "55555555-5555-4555-8555-555555555555";
const CHUNK_ID = "66666666-6666-4666-8666-666666666666";
const DOCUMENT_ID = "77777777-7777-4777-8777-777777777777";
const VERSION_ID = "88888888-8888-4888-8888-888888888888";
const PACKET_ID = "99999999-9999-4999-8999-999999999999";
const INTERRUPT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const ATTACHMENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const EXTRACTION_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const SOURCE = "波函数的模方给出粒子在位置附近被发现的概率密度。";
const SHA = "a".repeat(64);

function validResult(): Record<string, unknown> {
  return {
    conversation_id: CONVERSATION_ID,
    turn_id: TURN_ID,
    workflow_version: "teaching-state-machine/1.0.0",
    interpretation: {
      task_kind: "concept_question",
      relevant_concepts: ["波函数"],
      needs_scientific_verification: false,
      confidence: 0.9,
    },
    diagnosis: {
      status: "insufficient_evidence",
      summary: "仅观察到一条问题，暂不推断掌握度。",
      likely_misconception: null,
      observation_basis: ["student_message"],
      target_concepts: ["波函数"],
      first_error: null,
      misconception_candidates: [],
      missing_prerequisites: [],
      progress_state: "no_attempt",
      confidence: 0,
      verification_needed: false,
      reason: "No student attempt was supplied.",
    },
    policy: {
      policy_id: null,
      source: "safe_default",
      mode: "learn_concepts",
      allow_full_solution: false,
      minimum_attempts_for_scaffold: 1,
      minimum_attempts_for_full_solution: 2,
      max_hint_level: 3,
    },
    release: {
      action: "explain_then_check",
      release_level: "full_explanation",
      attempts_observed: 0,
      reason_code: "conceptual_explanation_allowed",
    },
    evidence_packet: {
      id: PACKET_ID,
      course_id: COURSE_ID,
      curriculum_edition_id: EDITION_ID,
      query: "波函数",
      created_at: "2026-08-23T00:00:00Z",
      coverage: "sufficient",
      evidence: [
        {
          evidence_id: EVIDENCE_ID,
          chunk_id: CHUNK_ID,
          document_id: DOCUMENT_ID,
          document_version_id: VERSION_ID,
          document_title: "量子力学基础",
          document_version: 1,
          source_file_name: "2-量子力学基础.pdf",
          source_file_sha256: SHA,
          source_chunk_sha256: SHA,
          evidence_sha256: SHA,
          curriculum_edition_id: EDITION_ID,
          chapter: "第二章 量子力学基础",
          section_path: ["波函数的统计解释"],
          locator: {
            locator_type: "pdf_page",
            physical_page: 12,
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
          source_chunk: SOURCE,
          evidence_snippet: SOURCE,
          kind: "course_material",
          authority_priority: 100,
          contributions: [
            {
              channel: "postgres_full_text",
              rank: 1,
              raw_score: 1,
              fused_score: 1,
            },
          ],
        },
      ],
      graph_nodes: [],
      graph_edges: [],
      degraded_channels: ["pgvector_semantic"],
      warnings: ["semantic channel unavailable"],
    },
    response: {
      orientation: "先从课程原文中的统计解释开始。",
      claims: [
        {
          text: SOURCE,
          support_basis: "course_material",
          evidence_ids: [EVIDENCE_ID],
          scientific_result_ids: [],
        },
      ],
      next_question: "模方与概率本身有什么区别？",
      status: "grounded",
      limitations: [],
    },
    validation: {
      passed: true,
      citation_ids_valid: true,
      literal_course_claims_valid: true,
      scientific_references_valid: true,
      warnings: [],
    },
    scientific_results: [],
    trace: WORKFLOW_ORDER.map((name) => ({
      name,
      status: name === "run_scientific_tools" ? "skipped" : "completed",
      detail: `${name} completed deterministically`,
    })),
  };
}

function validInterrupt(): Record<string, unknown> {
  const result = validResult();
  return {
    status: "interrupted",
    conversation_id: CONVERSATION_ID,
    turn_id: TURN_ID,
    interrupt: {
      schema_version: "quantum-agent-hitl/1.0.0",
      interrupt_id: INTERRUPT_ID,
      thread_id: CONVERSATION_ID,
      conversation_id: CONVERSATION_ID,
      turn_id: TURN_ID,
      stage: "pre_release_review",
      reasons: ["ambiguous_transcription"],
      prompt: "请确认低置信度的手写符号。",
      student_allowed_actions: ["confirm_transcription"],
      staff_allowed_actions: ["approve", "reject", "edit", "take_over"],
    },
    artifacts: {
      interpretation: result.interpretation,
      evidence_packet: result.evidence_packet,
      evidence_bundle: null,
      diagnosis: result.diagnosis,
      policy: result.policy,
      release: result.release,
      scientific_results: result.scientific_results,
      proposed_response: result.response,
      validation: result.validation,
      trace: result.trace,
      multimodal_evidence: [
        {
          detected_text: "ψ = a|0⟩ + b|1⟩",
          equations: [],
          derivation_steps: [],
          diagram_interpretation: null,
          plot_axes: [],
          plot_interpretation: null,
          figure_description: null,
          confidence: 0.62,
          bounding_boxes: [],
          ambiguities: [],
          evidence_type: "visual",
          attachment_id: ATTACHMENT_ID,
          original_file_reference: `attachment:${ATTACHMENT_ID}`,
          extraction_method: "qwen_vision",
          confirmation_state: "required",
          requires_confirmation: true,
        },
      ],
      perception_trace: [
        {
          attachment_id: ATTACHMENT_ID,
          extraction_id: EXTRACTION_ID,
          evidence_type: "visual",
          extraction_status: "needs_confirmation",
          confidence: 0.62,
          confirmation_state: "required",
          admitted_to_diagnosis: false,
          exact_context_characters: 0,
          context_truncated: false,
          scientific_request_derived: false,
          scientific_derivation_ordinals: null,
          confirmed_ambiguity_resolutions: {},
          confirmation_source: "pending",
        },
      ],
    },
  };
}

test("accepts a complete, scoped, fixed-order teaching record", () => {
  const result = parseTeachingTurnResult(validResult());
  assert.equal(result.response.claims[0]?.evidence_ids[0], EVIDENCE_ID);
  assert.equal(result.trace.length, 10);
  assert.doesNotThrow(() =>
    assertTeachingScope(
      result,
      { courseId: COURSE_ID, curriculumEditionId: EDITION_ID },
      "learn_concepts",
    ),
  );
});

test("request boundary accepts only bounded, typed scientific input", () => {
  const request = parseTeachingTurnRequest({
    conversation_id: null,
    mode: "run_experiments",
    message: "检查双能级演化。",
    student_attempt: "我预测布居会周期振荡。",
    scientific_request: {
      kind: "two_level_simulation",
      initial_state: [{ real: 1, imag: 0 }, { real: 0, imag: 0 }],
      rabi_frequency: 1,
      detuning: 0,
      duration: Math.PI,
      steps: 101,
      absolute_tolerance: 1e-8,
    },
  });
  assert.equal(request.scientific_request?.kind, "two_level_simulation");
  assert.deepEqual(request.attachment_ids, []);

  assert.throws(() =>
    parseTeachingTurnRequest({
      conversation_id: null,
      mode: "run_experiments",
      message: "运行这个。",
      student_attempt: null,
      scientific_request: { kind: "code_test", code: "import os", tests: ["pass"] },
    }),
  );
});

test("request boundary preserves at most eight unique attachment ids", () => {
  const request = parseTeachingTurnRequest({
    conversation_id: null,
    mode: "review_derivations",
    message: "检查上传的推导。",
    student_attempt: null,
    attachment_ids: [ATTACHMENT_ID],
    scientific_request: null,
  });
  assert.deepEqual(request.attachment_ids, [ATTACHMENT_ID]);

  assert.throws(
    () =>
      parseTeachingTurnRequest({
        conversation_id: null,
        mode: "review_derivations",
        message: "检查上传的推导。",
        student_attempt: null,
        attachment_ids: [ATTACHMENT_ID, ATTACHMENT_ID],
        scientific_request: null,
      }),
    /unique attachment UUIDs/,
  );
  assert.throws(
    () =>
      parseTeachingTurnRequest({
        conversation_id: null,
        mode: "review_derivations",
        message: "检查上传的推导。",
        student_attempt: null,
        attachment_ids: Array.from(
          { length: 9 },
          (_, index) => `dddddddd-dddd-4ddd-8ddd-${String(index).padStart(12, "0")}`,
        ),
        scientific_request: null,
      }),
    /at most eight unique attachment UUIDs/,
  );
});

test("accepts an auditable same-thread transcription interrupt", () => {
  const pause = parseHitlInterruptResponse(validInterrupt());
  assert.equal(pause.interrupt.student_allowed_actions[0], "confirm_transcription");
  assert.equal(pause.artifacts.multimodal_evidence[0]?.attachment_id, ATTACHMENT_ID);
  assert.equal(parseTeachingWorkflowOutcome(validInterrupt()).conversation_id, CONVERSATION_ID);
  assert.doesNotThrow(() =>
    assertHitlScope(
      pause,
      { courseId: COURSE_ID, curriculumEditionId: EDITION_ID },
      "learn_concepts",
    ),
  );
});

test("student HITL serialization withholds the proposed tutor response", () => {
  const pause = parseHitlInterruptResponse(validInterrupt());
  const redacted = redactHitlProposedResponse(pause);
  assert.equal(redacted.artifacts.proposed_response.claims.length, 0);
  assert.doesNotMatch(JSON.stringify(redacted), /先从课程原文中的统计解释开始/);
  assert.doesNotThrow(() => parseHitlInterruptResponse(redacted));
});

test("rejects broadened student HITL actions and cross-thread identifiers", () => {
  const broadened = validInterrupt();
  const interrupt = broadened.interrupt as {
    student_allowed_actions: string[];
    thread_id: string;
  };
  interrupt.student_allowed_actions = ["approve"];
  assert.throws(() => parseHitlInterruptResponse(broadened), /student_allowed_actions/);

  const crossed = validInterrupt();
  (crossed.interrupt as { thread_id: string }).thread_id = INTERRUPT_ID;
  assert.throws(() => parseHitlInterruptResponse(crossed), /identifiers matching/);
});

test("student resume contract permits only a confirmed transcription", () => {
  const parsed = parseStudentHitlResumeRequest({
    interrupt_id: INTERRUPT_ID,
    mode: "review_derivations",
    action: "confirm_transcription",
    confirmed_student_attempt: "  ψ = a|0⟩ + b|1⟩  ",
  });
  assert.equal(parsed.confirmed_student_attempt, "ψ = a|0⟩ + b|1⟩");

  assert.throws(() =>
    parseStudentHitlResumeRequest({
      interrupt_id: INTERRUPT_ID,
      mode: "review_derivations",
      action: "approve",
      confirmed_student_attempt: "ψ",
    }),
  );
  assert.throws(() =>
    parseStudentHitlResumeRequest({
      interrupt_id: INTERRUPT_ID,
      mode: "review_derivations",
      action: "confirm_transcription",
      confirmed_student_attempt: " ",
      note: "unexpected field",
    }),
  );
});

test("accepts the backend scientific result identity and audited result", () => {
  const raw = validResult();
  const inputHash = "b".repeat(64);
  raw.scientific_results = [
    {
      kind: "numerical_normalization",
      method: "numerical",
      status: "pass",
      tool: { name: "NumPy", version: "2.0" },
      inputs_sha256: inputHash,
      observations: ["范数平方为 1。"],
      limitations: ["只验证提供的离散态矢。"],
      metrics: { norm_squared: 1 },
      visualization: null,
      error_code: null,
    },
  ];
  const response = raw.response as {
    claims: Array<{
      text: string;
      support_basis: string;
      evidence_ids: string[];
      scientific_result_ids: string[];
    }>;
  };
  response.claims.push({
    text: "范数平方为 1。",
    support_basis: "numerical_verification",
    evidence_ids: [],
    scientific_result_ids: [`numerical_normalization:${inputHash}`],
  });
  const parsed = parseTeachingTurnResult(raw);
  assert.equal(parsed.scientific_results[0]?.status, "pass");
  assert.equal(parsed.response.claims[1]?.scientific_result_ids[0]?.length, 88);
});

test("rejects reordered traces and citations outside the packet", () => {
  const reordered = validResult();
  const reorderedTrace = [...(reordered.trace as unknown[])];
  [reorderedTrace[0], reorderedTrace[1]] = [reorderedTrace[1], reorderedTrace[0]];
  reordered.trace = reorderedTrace;
  assert.throws(() => parseTeachingTurnResult(reordered), /turnResult\.trace\[0\]\.name/);

  const uncited = validResult();
  const response = uncited.response as { claims: Array<{ evidence_ids: string[] }> };
  response.claims[0]!.evidence_ids = ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"];
  assert.throws(() => parseTeachingTurnResult(uncited), /IDs from the evidence packet/);

  const paraphrased = validResult();
  const paraphrasedResponse = paraphrased.response as { claims: Array<{ text: string }> };
  paraphrasedResponse.claims[0]!.text = "这是没有逐字出现在课程证据中的改写。";
  assert.throws(
    () => parseTeachingTurnResult(paraphrased),
    /literal span from one cited evidence snippet/,
  );
});

test("rejects cross-edition evidence even when the outer packet is scoped", () => {
  const raw = validResult();
  const packet = raw.evidence_packet as {
    evidence: Array<{ curriculum_edition_id: string }>;
  };
  packet.evidence[0]!.curriculum_edition_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const parsed = parseTeachingTurnResult(raw);
  assert.throws(
    () =>
      assertTeachingScope(
        parsed,
        { courseId: COURSE_ID, curriculumEditionId: EDITION_ID },
        "learn_concepts",
      ),
    /crossed the requested curriculum edition/,
  );
});

test("parses a Learning-Native commitment gate in a turn result", () => {
  const raw = validResult();
  raw.learning_native = {
    commitment: {
      gate_decision: "attempt_required",
      attempt_required: true,
      attempt_type: "prediction",
      candidate_prompt: "你的预测是什么？",
      reason_summary: "先预测再解释。",
      accepted: false,
      confidence: null,
    },
    learning_action: "ask_commitment",
    teach_back: null,
    transfer: null,
    solo: null,
    cognitive_mirror: null,
    evidence_persisted: ["commitment"],
  };
  const parsed = parseTeachingTurnResult(raw);
  assert.equal(parsed.learning_native?.commitment?.gate_decision, "attempt_required");
  assert.equal(parsed.learning_native?.learning_action, "ask_commitment");
  assert.deepEqual(parsed.learning_native?.evidence_persisted, ["commitment"]);
});

test("parses a Learning-Native solo-mode transfer task", () => {
  const raw = validResult();
  raw.learning_native = {
    commitment: null,
    learning_action: "enter_solo",
    teach_back: null,
    transfer: {
      transfer_type: "representation",
      prompt: "画出不同势垒宽度下的透射率曲线。",
      source_concept_ids: [],
      key_parameters: ["barrier_width"],
      expected_observable: "",
      verifiable: false,
    },
    solo: {
      status: "active",
      active_transfer: {
        transfer_type: "representation",
        prompt: "画出不同势垒宽度下的透射率曲线。",
        source_concept_ids: [],
        key_parameters: ["barrier_width"],
        expected_observable: "",
        verifiable: false,
      },
      started_at: "2026-08-26T00:00:00Z",
      assistance_locked: true,
      unlock_reason: "",
    },
    cognitive_mirror: null,
    evidence_persisted: ["transfer"],
  };
  const parsed = parseTeachingTurnResult(raw);
  assert.equal(parsed.learning_native?.solo?.status, "active");
  assert.equal(parsed.learning_native?.solo?.assistance_locked, true);
  assert.equal(parsed.learning_native?.transfer?.transfer_type, "representation");
});

test("parses a Cognitive Mirror without personality profile", () => {
  const raw = validResult();
  raw.learning_native = {
    commitment: null,
    learning_action: null,
    teach_back: null,
    transfer: null,
    solo: null,
    cognitive_mirror: {
      current_concept_id: null,
      concept_states: [
        {
          concept_candidate_id: EVIDENCE_ID,
          label: "developing",
          evidence_summary: ["学生提交了预测。"],
          confidence_history: [[0.8, true]],
          calibration_gap: null,
          unaided_retrieval: null,
          transfer_evidence: [],
          hint_dependency: [],
          misconception_candidates: [],
          last_demonstrated_at: null,
        },
      ],
      summary: "本轮诊断状态：observed。镜像是观察记录，不是掌握度分数。",
      no_personality_profile: true,
    },
    evidence_persisted: [],
  };
  const parsed = parseTeachingTurnResult(raw);
  assert.equal(parsed.learning_native?.cognitive_mirror?.no_personality_profile, true);
  assert.equal(parsed.learning_native?.cognitive_mirror?.concept_states[0]?.label, "developing");
});

test("rejects a Learning-Native submission with an invalid commitment kind", () => {
  assert.throws(() =>
    parseTeachingTurnRequest({
      conversation_id: null,
      mode: "learn_concepts",
      message: "学习隧穿。",
      student_attempt: null,
      attachment_ids: [],
      scientific_request: null,
      learning_native: {
        commitment: {
          gate_decision: "attempt_required",
          attempt_required: true,
          attempt_type: "not_a_real_kind",
          candidate_prompt: "预测。",
          reason_summary: "",
          accepted: false,
          confidence: null,
        },
        confidence: null,
        teach_back: null,
        transfer_attempt: null,
        solo_attempt: null,
        request_transfer: false,
        request_solo_exit: false,
        request_teach_back: false,
        request_transfer_task: false,
      },
    }),
  );
});

