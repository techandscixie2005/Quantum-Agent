import { z } from "zod";

import { WORKFLOW_ORDER } from "@/app/components/teaching/contracts";

const uuid = z.string().uuid();
const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
const timestamp = z.string().datetime({ offset: true });
const boundedText = (maximum: number) => z.string().min(1).max(maximum);

export const traceScopeSchema = z
  .object({
    courseId: uuid,
    curriculumEditionId: uuid,
  })
  .strict();

export type TraceScope = z.infer<typeof traceScopeSchema>;

const teachingModeSchema = z.enum([
  "learn_concepts",
  "review_derivations",
  "run_experiments",
  "work_on_projects",
]);
const taskKindSchema = z.enum([
  "concept_question",
  "derivation_check",
  "exercise_help",
  "experiment_help",
  "project_help",
]);
const teachingActionSchema = z.enum([
  "explain_then_check",
  "ask_diagnostic_question",
  "give_progressive_hint",
  "check_derivation_step",
  "predict_then_simulate",
  "coach_project_milestone",
]);
const releaseLevelSchema = z.enum([
  "question_only",
  "hint",
  "scaffold",
  "full_explanation",
  "full_solution",
]);

const locatorSchema = z
  .object({
    locator_type: z.enum(["pdf_page", "slide", "docx_paragraph", "xlsx_row", "text_lines"]),
    physical_page: z.number().int().positive().nullable(),
    printed_page_label: z.string().max(160).nullable(),
    slide_number: z.number().int().positive().nullable(),
    paragraph_start: z.number().int().positive().nullable(),
    paragraph_end: z.number().int().positive().nullable(),
    sheet_name: z.string().max(160).nullable(),
    row_start: z.number().int().positive().nullable(),
    row_end: z.number().int().positive().nullable(),
    line_start: z.number().int().positive().nullable(),
    line_end: z.number().int().positive().nullable(),
  })
  .strict()
  .superRefine((locator, context) => {
    const complete = {
      pdf_page: locator.physical_page !== null,
      slide: locator.slide_number !== null,
      docx_paragraph: locator.paragraph_start !== null,
      xlsx_row: locator.sheet_name !== null && locator.row_start !== null,
      text_lines: locator.line_start !== null,
    }[locator.locator_type];
    if (!complete) {
      context.addIssue({
        code: "custom",
        message: "locator fields do not match locator_type",
      });
    }
  });

const contributionSchema = z
  .object({
    channel: z.enum(["postgres_full_text", "pgvector_semantic", "neo4j_graph"]),
    rank: z.number().int().positive(),
    raw_score: z.number().finite().nullable(),
    fused_score: z.number().finite(),
  })
  .strict();

const evidenceKindSchema = z.enum([
  "course_material",
  "teacher_curated",
  "symbolic_verification",
  "numerical_verification",
  "simulation",
  "code_test",
  "model_inference",
]);

const evidenceSchema = z
  .object({
    evidence_id: uuid,
    chunk_id: uuid,
    document_id: uuid,
    document_version_id: uuid,
    document_title: boundedText(500),
    document_version: z.number().int().positive(),
    source_file_name: boundedText(500),
    source_file_sha256: sha256,
    source_chunk_sha256: sha256,
    evidence_sha256: sha256,
    curriculum_edition_id: uuid.nullable(),
    chapter: z.string().max(500).nullable(),
    section_path: z.array(boundedText(500)).max(20),
    locator: locatorSchema,
    source_chunk: boundedText(200_000),
    evidence_snippet: boundedText(50_000),
    kind: evidenceKindSchema,
    authority_priority: z.number().int().min(0).max(100),
    contributions: z.array(contributionSchema).min(1).max(12),
  })
  .strict();

const graphNodeSchema = z
  .object({
    id: uuid,
    node_type: boundedText(100),
    name: boundedText(500),
    aliases: z.array(boundedText(500)).max(40),
  })
  .strict();

const graphEdgeSchema = z
  .object({
    id: uuid,
    source_id: uuid,
    target_id: uuid,
    relation_type: boundedText(100),
  })
  .strict();

export const evidencePacketSchema = z
  .object({
    id: uuid,
    course_id: uuid,
    curriculum_edition_id: uuid,
    query: boundedText(5_000),
    created_at: timestamp,
    coverage: z.enum(["sufficient", "partial", "not_found"]),
    evidence: z.array(evidenceSchema).max(6),
    graph_nodes: z.array(graphNodeSchema).max(64),
    graph_edges: z.array(graphEdgeSchema).max(128),
    degraded_channels: z
      .array(z.enum(["postgres_full_text", "pgvector_semantic", "neo4j_graph"]))
      .max(8),
    warnings: z.array(z.string().max(1_000)).max(32),
  })
  .strict();

const courseCitationSchema = z
  .object({
    evidence_id: uuid,
    chunk_id: uuid,
    document_id: uuid,
    document_version_id: uuid,
    document_title: boundedText(500),
    document_version: z.number().int().positive(),
    source_file_name: boundedText(500),
    source_file_sha256: sha256,
    source_chunk_sha256: sha256,
    evidence_sha256: sha256,
    chapter: z.string().max(500).nullable(),
    section_path: z.array(boundedText(500)).max(20),
    locator: locatorSchema,
    evidence_snippet: boundedText(50_000),
    kind: evidenceKindSchema,
    authority_priority: z.number().int().min(0).max(100),
  })
  .strict();

const prerequisitePathSchema = z
  .object({
    relation_id: uuid,
    prerequisite: graphNodeSchema,
    target: graphNodeSchema,
  })
  .strict();

const misconceptionLinkSchema = z
  .object({
    relation_id: uuid,
    source: graphNodeSchema,
    misconception: graphNodeSchema,
  })
  .strict();

export const evidenceBundleSchema = z
  .object({
    course_id: uuid,
    curriculum_edition_id: uuid,
    query: boundedText(5_000),
    retrieval_query: boundedText(5_000),
    coverage: z.enum(["sufficient", "partial", "insufficient"]),
    coverage_rationale: boundedText(500),
    source_chunks: z.array(evidenceSchema).max(6),
    citations: z.array(courseCitationSchema).max(6),
    relevant_concepts: z.array(graphNodeSchema).max(32),
    graph_nodes: z.array(graphNodeSchema).max(64),
    graph_edges: z.array(graphEdgeSchema).max(128),
    prerequisite_paths: z.array(prerequisitePathSchema).max(32),
    misconception_links: z.array(misconceptionLinkSchema).max(32),
    formulas: z.array(graphNodeSchema).max(32),
    degraded_channels: z
      .array(z.enum(["postgres_full_text", "pgvector_semantic", "neo4j_graph"]))
      .max(8),
    warnings: z.array(z.string().max(1_000)).max(32),
    conflicts: z
      .array(
        z
          .object({
            evidence_ids: z.array(uuid).min(2).max(6),
            summary: boundedText(500),
          })
          .strict(),
      )
      .max(6),
  })
  .strict();

export const diagnosisSchema = z
  .object({
    status: z.enum(["observed", "model_inference", "insufficient_evidence"]),
    summary: boundedText(800),
    likely_misconception: z.string().max(500).nullable(),
    observation_basis: z
      .array(z.enum(["student_message", "student_attempt", "course_evidence"]))
      .max(3),
    target_concepts: z.array(boundedText(160)).max(6),
    first_error: z
      .object({
        inferred: z.boolean(),
        step_index: z.number().int().nonnegative().nullable(),
        kind: z.enum([
          "algebra_error",
          "assumption_error",
          "boundary_condition_error",
          "normalization_error",
          "basis_confusion",
          "operator_error",
          "degeneracy_error",
          "dimension_error",
          "numerical_error",
          "physical_interpretation_error",
          "no_clear_error",
          "inconclusive",
        ]),
        description: z.string().max(400),
      })
      .strict()
      .nullable(),
    misconception_candidates: z
      .array(
        z
          .object({
            statement: boundedText(400),
            confidence: z.number().min(0).max(1),
          })
          .strict(),
      )
      .max(4),
    missing_prerequisites: z.array(boundedText(160)).max(6),
    progress_state: z.enum(["no_attempt", "started", "struggling", "progressing", "confident"]),
    confidence: z.number().min(0).max(1),
    verification_needed: z.boolean(),
    reason: boundedText(800),
  })
  .strict();

export const policySchema = z
  .object({
    policy_id: uuid.nullable(),
    source: z.enum(["teacher_configured", "safe_default"]),
    mode: teachingModeSchema,
    allow_full_solution: z.boolean(),
    minimum_attempts_for_scaffold: z.number().int().nonnegative(),
    minimum_attempts_for_full_solution: z.number().int().nonnegative(),
    max_hint_level: z.number().int().min(0).max(10),
  })
  .strict();

export const releaseSchema = z
  .object({
    action: teachingActionSchema,
    release_level: releaseLevelSchema,
    attempts_observed: z.number().int().nonnegative(),
    reason_code: boundedText(120),
  })
  .strict();

const claimSchema = z
  .object({
    text: boundedText(4_000),
    support_basis: z.enum([
      "course_material",
      "symbolic_verification",
      "numerical_verification",
      "simulation",
      "code_test",
      "pedagogical_prompt",
      "unverified_model_inference",
    ]),
    evidence_ids: z.array(uuid).max(6),
    scientific_result_ids: z.array(z.string().min(1).max(200)).max(4),
  })
  .strict();

export const teachingResponseSchema = z
  .object({
    orientation: boundedText(1_200),
    claims: z.array(claimSchema).max(8),
    next_question: boundedText(1_000),
    status: z.enum(["grounded", "mixed", "model_degraded", "insufficient_course_evidence"]),
    limitations: z.array(z.string().max(4_000)).max(8),
  })
  .strict();

export const validationSchema = z
  .object({
    passed: z.boolean(),
    citation_ids_valid: z.boolean(),
    literal_course_claims_valid: z.boolean(),
    scientific_references_valid: z.boolean(),
    warnings: z.array(z.string().max(1_000)).max(12),
  })
  .strict();

const toolIdentitySchema = z
  .object({ name: boundedText(80), version: boundedText(80) })
  .strict();
const visualizationSchema = z
  .object({
    renderer: toolIdentitySchema,
    kind: z.literal("line"),
    title: boundedText(160),
    x_label: boundedText(80),
    y_label: boundedText(80),
    x: z.array(z.number().finite()).min(2).max(5_000),
    series: z
      .array(
        z.object({ label: boundedText(80), y: z.array(z.number().finite()).min(2).max(5_000) }).strict(),
      )
      .min(1)
      .max(8),
    rendering_sha256: sha256,
  })
  .strict();

export const scientificResultSchema = z
  .object({
    kind: z.enum([
      "symbolic_equivalence",
      "symbolic_residual",
      "numerical_normalization",
      "numerical_unitarity",
      "two_level_simulation",
      "line_visualization",
      "code_test",
      "unverified",
    ]),
    method: z.enum(["symbolic", "numerical", "simulation", "code_test", "unverified"]),
    status: z.enum(["pass", "fail", "inconclusive"]),
    tool: toolIdentitySchema,
    inputs_sha256: sha256,
    observations: z.array(boundedText(4_000)).min(1).max(16),
    limitations: z.array(boundedText(4_000)).min(1).max(16),
    metrics: z.record(z.string(), z.union([z.string(), z.number().finite(), z.boolean()])),
    visualization: visualizationSchema.nullable(),
    error_code: z.string().regex(/^[A-Z0-9_]{3,64}$/).nullable(),
  })
  .strict();

const workflowStepSchema = z
  .object({
    name: z.enum(WORKFLOW_ORDER),
    status: z.enum(["completed", "degraded", "skipped", "failed"]),
    detail: boundedText(500),
  })
  .strict();

const workflowSchema = z
  .array(workflowStepSchema)
  .length(WORKFLOW_ORDER.length)
  .refine(
    (steps) => steps.every((step, index) => step.name === WORKFLOW_ORDER[index]),
    "workflow steps must follow the fixed deterministic order",
  );

const staffActions = ["approve", "reject", "edit", "take_over"] as const;
const hitlReasonSchema = z.enum([
  "ta_requested",
  "ambiguous_transcription",
  "evidence_conflict",
  "insufficient_coverage",
  "verifier_model_disagreement",
  "repeated_no_progress",
  "teacher_approval_required",
  "project_milestone_review",
  "safety_condition",
]);

const interruptSchema = z
  .object({
    schema_version: z.literal("quantum-agent-hitl/1.0.0"),
    interrupt_id: uuid,
    thread_id: uuid,
    conversation_id: uuid,
    turn_id: uuid,
    stage: z.literal("pre_release_review"),
    reasons: z.array(hitlReasonSchema).min(1).max(9),
    prompt: boundedText(1_200),
    student_allowed_actions: z.array(z.literal("confirm_transcription")).max(1),
    staff_allowed_actions: z
      .array(z.enum(staffActions))
      .length(staffActions.length)
      .refine((actions) => actions.every((action, index) => action === staffActions[index])),
  })
  .strict()
  .refine((interrupt) => interrupt.thread_id === interrupt.conversation_id, {
    message: "thread and conversation identifiers must match",
  });

const resolutionSchema = z
  .object({
    interrupt_id: uuid,
    action: z.enum([...staffActions, "confirm_transcription"]),
    actor_user_id: uuid,
    actor_role: z.enum(["student", "ta", "teacher", "admin"]),
    note: z.string().max(4_000).nullable(),
    edited_response: teachingResponseSchema.nullable(),
    confirmed_student_attempt: z.string().max(12_000).nullable(),
  })
  .strict();

const hitlEventSchema = z
  .object({ interrupt: interruptSchema, resolution: resolutionSchema.nullable() })
  .strict()
  .refine(
    (event) => event.resolution === null || event.resolution.interrupt_id === event.interrupt.interrupt_id,
    "HITL resolution must match its interrupt",
  );

export const traceSummarySchema = z
  .object({
    id: uuid,
    teaching_turn_id: uuid,
    conversation_id: uuid,
    student_user_id: uuid,
    mode: teachingModeSchema,
    sequence_number: z.number().int().positive(),
    task_kind: taskKindSchema.nullable(),
    teaching_action: teachingActionSchema.nullable(),
    release_level: releaseLevelSchema.nullable(),
    turn_status: z.enum(["running", "completed", "failed"]),
    workflow_version: boundedText(160),
    model_gateway_status: boundedText(160),
    citation_validation_status: boundedText(160),
    created_at: timestamp,
    completed_at: timestamp.nullable(),
  })
  .strict();

export const agentTracePageSchema = z
  .object({
    course_id: uuid,
    curriculum_edition_id: uuid,
    items: z.array(traceSummarySchema).max(100),
    total: z.number().int().nonnegative(),
    limit: z.number().int().min(1).max(100),
    offset: z.number().int().min(0).max(100_000),
    has_more: z.boolean(),
  })
  .strict();

export const agentTraceDetailSchema = traceSummarySchema.extend({
  user_message: boundedText(4_000),
  student_attempt: z.string().max(12_000).nullable(),
  workflow_steps: workflowSchema,
  policy_snapshot: policySchema,
  evidence_packet: evidencePacketSchema.nullable(),
  evidence_bundle: evidenceBundleSchema.nullable(),
  diagnosis: diagnosisSchema.nullable(),
  release_decision: releaseSchema.nullable(),
  response: teachingResponseSchema.nullable(),
  scientific_results: z.array(scientificResultSchema).max(16),
  validation: validationSchema.nullable(),
  hitl_events: z.array(hitlEventSchema).max(32),
  failure_code: z.string().max(160).nullable(),
}).strict();

const reviewNoteSchema = z.string().trim().max(4_000).nullable();
const requiredReviewNoteSchema = z.string().trim().min(1).max(4_000);

export const reviewDecisionSchema = z.discriminatedUnion("action", [
  z
    .object({
      interrupt_id: uuid,
      action: z.literal("approve"),
      note: reviewNoteSchema,
    })
    .strict(),
  z
    .object({
      interrupt_id: uuid,
      action: z.literal("reject"),
      note: requiredReviewNoteSchema,
    })
    .strict(),
  z
    .object({
      interrupt_id: uuid,
      action: z.literal("edit"),
      note: reviewNoteSchema,
      edited_response: teachingResponseSchema,
    })
    .strict(),
  z
    .object({
      interrupt_id: uuid,
      action: z.literal("take_over"),
      note: requiredReviewNoteSchema,
      edited_response: teachingResponseSchema,
    })
    .strict(),
]);

export const reviewResolutionSchema = z
  .object({
    status: z.literal("resolved"),
    action: z.enum(staffActions),
    outcome: z.enum(["completed", "rejected", "interrupted"]),
    conversation_id: uuid,
    turn_id: uuid,
  })
  .strict();

export const hitlRejectedResponseSchema = z
  .object({
    status: z.literal("rejected"),
    conversation_id: uuid,
    turn_id: uuid,
    interrupt_id: uuid,
    reason_code: z.literal("HITL_REJECTED"),
  })
  .strict();

export type AgentTracePage = z.infer<typeof agentTracePageSchema>;
export type AgentTraceSummary = z.infer<typeof traceSummarySchema>;
export type AgentTraceDetail = z.infer<typeof agentTraceDetailSchema>;
export type EvidenceBundle = z.infer<typeof evidenceBundleSchema>;
export type TeachingResponse = z.infer<typeof teachingResponseSchema>;
export type ReviewDecision = z.infer<typeof reviewDecisionSchema>;
export type ReviewResolution = z.infer<typeof reviewResolutionSchema>;
export type HitlRejectedResponse = z.infer<typeof hitlRejectedResponseSchema>;

export function parseAgentTracePage(value: unknown, scope: TraceScope): AgentTracePage {
  const parsed = agentTracePageSchema.parse(value);
  if (
    parsed.course_id !== scope.courseId ||
    parsed.curriculum_edition_id !== scope.curriculumEditionId
  ) {
    throw new Error("trace page crossed the requested course boundary");
  }
  return parsed;
}

export function parseAgentTraceDetail(
  value: unknown,
  scope: TraceScope,
  traceId: string,
): AgentTraceDetail {
  const parsed = agentTraceDetailSchema.parse(value);
  if (parsed.id !== traceId) throw new Error("trace identifier changed upstream");
  for (const evidence of [parsed.evidence_packet, parsed.evidence_bundle]) {
    if (
      evidence !== null &&
      (evidence.course_id !== scope.courseId ||
        evidence.curriculum_edition_id !== scope.curriculumEditionId)
    ) {
      throw new Error("trace evidence crossed the requested course boundary");
    }
  }
  for (const event of parsed.hitl_events) {
    if (
      event.interrupt.conversation_id !== parsed.conversation_id ||
      event.interrupt.turn_id !== parsed.teaching_turn_id
    ) {
      throw new Error("trace HITL event does not belong to this turn");
    }
  }
  return parsed;
}

export function parseReviewDecision(value: unknown): ReviewDecision {
  return reviewDecisionSchema.parse(value);
}

export function assertEditedResponseAuthority(
  candidate: TeachingResponse,
  inspected: TeachingResponse,
): void {
  if (candidate.status !== inspected.status) {
    throw new Error("staff edits cannot change the validated response status");
  }
  if (candidate.claims.length !== inspected.claims.length) {
    throw new Error("staff edits cannot add or remove authority-bearing claims");
  }
  for (const [index, claim] of candidate.claims.entries()) {
    const original = inspected.claims[index];
    if (
      !original ||
      claim.support_basis !== original.support_basis ||
      JSON.stringify(claim.evidence_ids) !== JSON.stringify(original.evidence_ids) ||
      JSON.stringify(claim.scientific_result_ids) !==
        JSON.stringify(original.scientific_result_ids)
    ) {
      throw new Error(`staff edit changed the authority envelope for claim ${index}`);
    }
  }
}

export function parseReviewResolution(value: unknown): ReviewResolution {
  return reviewResolutionSchema.parse(value);
}

export function parseHitlRejectedResponse(value: unknown): HitlRejectedResponse {
  return hitlRejectedResponseSchema.parse(value);
}
