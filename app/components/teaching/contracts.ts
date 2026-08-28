/**
 * Runtime-checked browser contracts for the deterministic teaching workflow.
 *
 * The FastAPI service is an untrusted network boundary. These parsers are
 * intentionally dependency-free and reject cross-course results, malformed
 * provenance, reordered workflow steps, and scientific data that cannot be
 * rendered safely.
 */

import { UUID_PATTERN, type EvidenceLocator } from "../knowledge/contracts";

export const TEACHING_MODES = [
  "learn_concepts",
  "review_derivations",
  "run_experiments",
  "work_on_projects",
] as const;

export type TeachingMode = (typeof TEACHING_MODES)[number];

export type TeachingScope = Readonly<{
  courseId: string;
  curriculumEditionId: string;
}>;

export type ComplexValue = Readonly<{ real: number; imag: number }>;

export type SymbolicEquivalenceRequest = Readonly<{
  kind: "symbolic_equivalence";
  left: string;
  right: string;
  symbols: readonly string[];
  timeout_seconds: number;
}>;

export type NumericalNormalizationRequest = Readonly<{
  kind: "numerical_normalization";
  state: readonly ComplexValue[];
  target_norm_squared: number;
  absolute_tolerance: number;
}>;

export type TwoLevelSimulationRequest = Readonly<{
  kind: "two_level_simulation";
  initial_state: readonly [ComplexValue, ComplexValue];
  rabi_frequency: number;
  detuning: number;
  duration: number;
  steps: number;
  absolute_tolerance: number;
}>;

export type RectangularBarrierRequest = Readonly<{
  kind: "rectangular_barrier_tunnelling";
  energy_eV: number;
  barrier_height_eV: number;
  barrier_width_m: number;
  particle_mass_kg: number;
  conservation_tolerance: number;
}>;

export type SupportedScientificRequest =
  | SymbolicEquivalenceRequest
  | NumericalNormalizationRequest
  | TwoLevelSimulationRequest
  | RectangularBarrierRequest;

export type TeachingTurnRequest = Readonly<{
  conversation_id: string | null;
  mode: TeachingMode;
  message: string;
  student_attempt: string | null;
  attachment_ids: readonly string[];
  scientific_request: SupportedScientificRequest | null;
  learning_native: LearningNativeSubmission | null;
  // PRD V3.0 P1-2: client-generated idempotency key.  The browser sends the
  // same key on a retry so the backend can return the original completed
  // turn instead of creating a duplicate.
  client_request_id: string | null;
}>;

export const WORKFLOW_ORDER = [
  "classify_task",
  "identify_concepts",
  "retrieve_evidence",
  "diagnose_progress",
  "choose_teaching_action",
  "apply_answer_policy",
  "run_scientific_tools",
  "generate_response",
  "validate_response",
  "record_learning_evidence",
] as const;

export type WorkflowStepName = (typeof WORKFLOW_ORDER)[number];
export type WorkflowStepStatus = "completed" | "degraded" | "skipped" | "failed";

export type EvidenceContribution = Readonly<{
  channel: "postgres_full_text" | "pgvector_semantic" | "neo4j_graph";
  rank: number;
  raw_score: number | null;
  fused_score: number;
}>;

export type TeachingEvidence = Readonly<{
  evidence_id: string;
  chunk_id: string;
  document_id: string;
  document_version_id: string;
  document_title: string;
  document_version: number;
  source_file_name: string;
  source_file_sha256: string;
  source_chunk_sha256: string;
  evidence_sha256: string;
  curriculum_edition_id: string | null;
  chapter: string | null;
  section_path: readonly string[];
  locator: EvidenceLocator;
  source_chunk: string;
  evidence_snippet: string;
  kind:
    | "course_material"
    | "teacher_curated"
    | "symbolic_verification"
    | "numerical_verification"
    | "simulation"
    | "code_test"
    | "model_inference";
  authority_priority: number;
  contributions: readonly EvidenceContribution[];
}>;

export type EvidencePacket = Readonly<{
  id: string;
  course_id: string;
  curriculum_edition_id: string;
  query: string;
  created_at: string;
  coverage: "sufficient" | "partial" | "not_found";
  evidence: readonly TeachingEvidence[];
  graph_nodes: readonly Readonly<{
    id: string;
    node_type: string;
    name: string;
    aliases: readonly string[];
  }>[];
  graph_edges: readonly Readonly<{
    id: string;
    source_id: string;
    target_id: string;
    relation_type: string;
  }>[];
  degraded_channels: readonly EvidenceContribution["channel"][];
  warnings: readonly string[];
}>;

export type CourseCitation = Readonly<{
  evidence_id: string;
  chunk_id: string;
  document_id: string;
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
  evidence_snippet: string;
  kind: TeachingEvidence["kind"];
  authority_priority: number;
}>;

export type EvidenceBundle = Readonly<{
  course_id: string;
  curriculum_edition_id: string;
  query: string;
  retrieval_query: string;
  coverage: "sufficient" | "partial" | "insufficient";
  coverage_rationale: string;
  source_chunks: readonly TeachingEvidence[];
  citations: readonly CourseCitation[];
  relevant_concepts: EvidencePacket["graph_nodes"];
  graph_nodes: EvidencePacket["graph_nodes"];
  graph_edges: EvidencePacket["graph_edges"];
  prerequisite_paths: readonly Readonly<{
    relation_id: string;
    prerequisite: EvidencePacket["graph_nodes"][number];
    target: EvidencePacket["graph_nodes"][number];
  }>[];
  misconception_links: readonly Readonly<{
    relation_id: string;
    source: EvidencePacket["graph_nodes"][number];
    misconception: EvidencePacket["graph_nodes"][number];
  }>[];
  formulas: EvidencePacket["graph_nodes"];
  degraded_channels: EvidencePacket["degraded_channels"];
  warnings: readonly string[];
  conflicts: readonly Readonly<{
    evidence_ids: readonly string[];
    summary: string;
  }>[];
}>;

export type HitlMultimodalEvidence = Readonly<Record<string, unknown>> & Readonly<{
  evidence_type: "visual" | "document";
  attachment_id: string;
  original_file_reference: string;
  extraction_method: "native" | "qwen_vision" | "mineru" | "vision_ocr" | "unlimited_ocr";
  confirmation_state: "not_required" | "required" | "confirmed" | "rejected";
  requires_confirmation: boolean;
  confidence: number;
}>;

export type PerceptionTraceEntry = Readonly<{
  attachment_id: string;
  extraction_id: string;
  evidence_type: "visual" | "document";
  extraction_status:
    | "pending"
    | "running"
    | "needs_confirmation"
    | "succeeded"
    | "confirmed"
    | "rejected"
    | "failed";
  confidence: number;
  confirmation_state: "not_required" | "required" | "confirmed" | "rejected";
  admitted_to_diagnosis: boolean;
  exact_context_characters: number;
  context_truncated: boolean;
  scientific_request_derived: boolean;
  scientific_derivation_ordinals: readonly [number, number] | null;
  confirmed_ambiguity_resolutions: Readonly<Record<string, string>>;
  confirmation_source: "pending" | "not_required" | "attachment_api" | "teaching_hitl";
}>;

export type VisualizationSpec = Readonly<{
  renderer: Readonly<{ name: string; version: string }>;
  kind: "line";
  title: string;
  x_label: string;
  y_label: string;
  x: readonly number[];
  series: readonly Readonly<{ label: string; y: readonly number[] }>[];
  rendering_sha256: string;
}>;

export type ScientificResult = Readonly<{
  kind:
    | "symbolic_equivalence"
    | "symbolic_residual"
    | "numerical_normalization"
    | "numerical_unitarity"
    | "two_level_simulation"
    | "rectangular_barrier_tunnelling"
    | "line_visualization"
    | "code_test"
    | "unverified";
  method: "symbolic" | "numerical" | "simulation" | "code_test" | "unverified";
  status: "pass" | "fail" | "inconclusive";
  tool: Readonly<{ name: string; version: string }>;
  inputs_sha256: string;
  observations: readonly string[];
  limitations: readonly string[];
  metrics: Readonly<Record<string, string | number | boolean>>;
  visualization: VisualizationSpec | null;
  error_code: string | null;
}>;

// PRD V3.1 §6: Coding Agent artifact types.  The agent writes fresh Python,
// runs it in the sandbox, and cross-checks against the deterministic oracle.
// These mirror services/api/quantum_agent/coding/models.py.

export type CodeLanguage = "python";

export type CodeArtifact = Readonly<{
  language: CodeLanguage;
  purpose: string;
  code: string;
  expected_outputs: readonly string[];
  verification_plan: string;
}>;

export type CodeExecutionResult = Readonly<{
  completed: boolean;
  exit_code: number | null;
  timed_out: boolean;
  truncated: boolean;
  stdout_bounded: string;
  stderr_bounded: string;
  duration_seconds: number;
}>;

export type CodeVerificationStatus = "pass" | "fail" | "inconclusive" | "no_oracle";

export type CodeVerificationResult = Readonly<{
  status: CodeVerificationStatus;
  oracle_kind: string | null;
  agent_metrics: Readonly<Record<string, string | number | boolean>>;
  oracle_metrics: Readonly<Record<string, string | number | boolean>>;
  observations: readonly string[];
  tolerance: number;
}>;

export type CodeRepairAttempt = Readonly<{
  attempt_number: number;
  failure_summary: string;
  stderr_excerpt: string;
}>;

export type CodingProgress = "planning" | "writing" | "running" | "verifying" | "result";

export type CodeArtifactRun = Readonly<{
  artifact: CodeArtifact;
  execution: CodeExecutionResult;
  verification: CodeVerificationResult;
  repairs: readonly CodeRepairAttempt[];
  progress: CodingProgress;
  figure_png_base64: string | null;
}>;

export type SupportBasis =
  | "course_material"
  | "symbolic_verification"
  | "numerical_verification"
  | "simulation"
  | "code_test"
  | "pedagogical_prompt"
  | "unverified_model_inference";

export type CommitmentKind =
  | "prediction"
  | "first_step"
  | "physical_reason"
  | "diagram"
  | "option_with_confidence"
  | "self_explanation";

export type CommitmentGateDecision = "attempt_required" | "proceed";

export type CognitiveCommitment = Readonly<{
  gate_decision: CommitmentGateDecision;
  attempt_required: boolean;
  attempt_type: CommitmentKind | null;
  candidate_prompt: string;
  reason_summary: string;
  accepted: boolean;
  confidence: number | null;
}>;

export type TeachBackRelation = "covered" | "missing" | "contradictory" | "unsupported";

export type TeachBackFinding = Readonly<{
  relation: TeachBackRelation;
  description: string;
  target_concept_id: string | null;
}>;

export type TeachBackAnalysis = Readonly<{
  covered_relations: readonly TeachBackFinding[];
  missing_relations: readonly TeachBackFinding[];
  contradictions: readonly TeachBackFinding[];
  unsupported_claims: readonly TeachBackFinding[];
  recommended_probe: string;
  verified: boolean;
  is_model_inference: boolean;
}>;

export type TransferType =
  | "near"
  | "parameter"
  | "representation"
  | "conceptual"
  | "far"
  | "delayed_retrieval";

export type TransferTask = Readonly<{
  transfer_type: TransferType;
  prompt: string;
  source_concept_ids: readonly string[];
  key_parameters: readonly string[];
  expected_observable: string;
  verifiable: boolean;
}>;

export type SoloModeStatus = "inactive" | "active" | "exited";

export type SoloMode = Readonly<{
  status: SoloModeStatus;
  active_transfer: TransferTask | null;
  started_at: string | null;
  assistance_locked: boolean;
  unlock_reason: string;
}>;

export type ConceptStateLabel =
  | "unknown"
  | "exposed"
  | "developing"
  | "demonstrated"
  | "transfer_ready"
  | "fragile"
  | "needs_review";

export type ConceptMirrorState = Readonly<{
  concept_candidate_id: string;
  label: ConceptStateLabel;
  evidence_summary: readonly string[];
  confidence_history: readonly Readonly<readonly [number, boolean]>[];
  calibration_gap: number | null;
  unaided_retrieval: boolean | null;
  transfer_evidence: readonly string[];
  hint_dependency: readonly string[];
  misconception_candidates: readonly string[];
  last_demonstrated_at: string | null;
}>;

export type CognitiveMirror = Readonly<{
  current_concept_id: string | null;
  concept_states: readonly ConceptMirrorState[];
  summary: string;
  no_personality_profile: boolean;
}>;

export type LearningPolicyAction =
  | "ask_commitment"
  | "ask_prediction"
  | "ask_self_explanation"
  | "give_cue"
  | "give_hint"
  | "show_counterexample"
  | "start_simulation"
  | "start_teach_back"
  | "start_transfer"
  | "enter_solo"
  | "show_worked_example";

export type LearningNativeTurnState = Readonly<{
  commitment: CognitiveCommitment | null;
  learning_action: LearningPolicyAction | null;
  teach_back: TeachBackAnalysis | null;
  transfer: TransferTask | null;
  solo: SoloMode | null;
  cognitive_mirror: CognitiveMirror | null;
  evidence_persisted: readonly string[];
}>;

export type LearningNativeSubmission = Readonly<{
  commitment: CognitiveCommitment | null;
  confidence: number | null;
  teach_back: Readonly<{ reconstruction: string; target_concept_ids: readonly string[] }> | null;
  transfer_attempt: Readonly<{
    transfer_task_id: string;
    response: string;
    confidence: number | null;
  }> | null;
  solo_attempt: Readonly<{ response: string; confidence: number | null }> | null;
  request_transfer: boolean;
  request_solo_exit: boolean;
  request_teach_back: boolean;
  request_transfer_task: boolean;
}>;

export type TeachingTurnResult = Readonly<{
  conversation_id: string;
  turn_id: string;
  workflow_version: string;
  interpretation: Readonly<{
    task_kind:
      | "concept_question"
      | "derivation_check"
      | "exercise_help"
      | "experiment_help"
      | "project_help";
    relevant_concepts: readonly string[];
    needs_scientific_verification: boolean;
    confidence: number;
  }>;
  diagnosis: Readonly<{
    status: "observed" | "model_inference" | "insufficient_evidence";
    summary: string;
    likely_misconception: string | null;
    observation_basis: readonly ("student_message" | "student_attempt" | "course_evidence")[];
    target_concepts: readonly string[];
    first_error: Readonly<{
      inferred: boolean;
      step_index: number | null;
      kind:
        | "algebra_error"
        | "assumption_error"
        | "boundary_condition_error"
        | "normalization_error"
        | "basis_confusion"
        | "operator_error"
        | "degeneracy_error"
        | "dimension_error"
        | "numerical_error"
        | "physical_interpretation_error"
        | "no_clear_error"
        | "inconclusive";
      description: string;
    }> | null;
    misconception_candidates: readonly Readonly<{ statement: string; confidence: number }>[];
    missing_prerequisites: readonly string[];
    progress_state: "no_attempt" | "started" | "struggling" | "progressing" | "confident";
    confidence: number;
    verification_needed: boolean;
    reason: string;
  }>;
  policy: Readonly<{
    policy_id: string | null;
    source: "teacher_configured" | "safe_default";
    mode: TeachingMode;
    allow_full_solution: boolean;
    minimum_attempts_for_scaffold: number;
    minimum_attempts_for_full_solution: number;
    max_hint_level: number;
  }>;
  release: Readonly<{
    action:
      | "explain_then_check"
      | "ask_diagnostic_question"
      | "give_progressive_hint"
      | "check_derivation_step"
      | "predict_then_simulate"
      | "coach_project_milestone";
    release_level: "question_only" | "hint" | "scaffold" | "full_explanation" | "full_solution";
    attempts_observed: number;
    reason_code: string;
  }>;
  evidence_packet: EvidencePacket;
  response: Readonly<{
    orientation: string;
    claims: readonly Readonly<{
      text: string;
      support_basis: SupportBasis;
      evidence_ids: readonly string[];
      scientific_result_ids: readonly string[];
    }>[];
    next_question: string;
    status: "grounded" | "mixed" | "model_degraded" | "insufficient_course_evidence";
    limitations: readonly string[];
  }>;
  validation: Readonly<{
    passed: boolean;
    citation_ids_valid: boolean;
    literal_course_claims_valid: boolean;
    scientific_references_valid: boolean;
    warnings: readonly string[];
  }>;
  scientific_results: readonly ScientificResult[];
  code_artifact: CodeArtifactRun | null;
  trace: readonly Readonly<{
    name: WorkflowStepName;
    status: WorkflowStepStatus;
    detail: string;
  }>[];
  learning_native: LearningNativeTurnState | null;
}>;

export const HITL_REASONS = [
  "ta_requested",
  "ambiguous_transcription",
  "evidence_conflict",
  "insufficient_coverage",
  "verifier_model_disagreement",
  "repeated_no_progress",
  "teacher_approval_required",
  "project_milestone_review",
  "safety_condition",
] as const;

export type HitlReason = (typeof HITL_REASONS)[number];
export type StudentHitlAction = "confirm_transcription";
export type StaffHitlAction = "approve" | "reject" | "edit" | "take_over";

export type HitlInterruptResponse = Readonly<{
  status: "interrupted";
  conversation_id: string;
  turn_id: string;
  interrupt: Readonly<{
    schema_version: "quantum-agent-hitl/1.0.0";
    interrupt_id: string;
    thread_id: string;
    conversation_id: string;
    turn_id: string;
    stage: "pre_release_review";
    reasons: readonly HitlReason[];
    prompt: string;
    student_allowed_actions: readonly StudentHitlAction[];
    staff_allowed_actions: readonly StaffHitlAction[];
  }>;
  artifacts: Readonly<{
    interpretation: TeachingTurnResult["interpretation"];
    evidence_packet: EvidencePacket;
    evidence_bundle: EvidenceBundle | null;
    diagnosis: TeachingTurnResult["diagnosis"];
    policy: TeachingTurnResult["policy"];
    release: TeachingTurnResult["release"];
    scientific_results: TeachingTurnResult["scientific_results"];
    proposed_response: TeachingTurnResult["response"];
    validation: TeachingTurnResult["validation"];
    trace: TeachingTurnResult["trace"];
    multimodal_evidence: readonly HitlMultimodalEvidence[];
    perception_trace: readonly PerceptionTraceEntry[];
  }>;
}>;

export type TeachingWorkflowOutcome = TeachingTurnResult | HitlInterruptResponse;

export type StudentHitlResumeRequest = Readonly<{
  interrupt_id: string;
  mode: TeachingMode;
  action: StudentHitlAction;
  confirmed_student_attempt: string;
}>;

export type TeachingApiError = Readonly<{
  error: Readonly<{ code: string; message: string; trace_id?: string }>;
}>;

export class TeachingContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TeachingContractError";
  }
}

type UnknownRecord = Record<string, unknown>;

function fail(path: string, expected: string): never {
  throw new TeachingContractError(`${path} must be ${expected}`);
}

function record(value: unknown, path: string): UnknownRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return fail(path, "an object");
  }
  return value as UnknownRecord;
}

function exactKeys(value: UnknownRecord, allowed: readonly string[], path: string): void {
  const allowedSet = new Set(allowed);
  const unknown = Object.keys(value).find((key) => !allowedSet.has(key));
  if (unknown) fail(`${path}.${unknown}`, "absent (unknown field)");
}

function array(value: unknown, path: string): readonly unknown[] {
  if (!Array.isArray(value)) return fail(path, "an array");
  return value;
}

function text(value: unknown, path: string, max = 20_000): string {
  if (typeof value !== "string" || value.length < 1 || value.length > max) {
    return fail(path, `a string of 1–${max} characters`);
  }
  return value;
}

function nullableText(value: unknown, path: string, max = 20_000): string | null {
  return value === null ? null : text(value, path, max);
}

function boundedTextAllowEmpty(value: unknown, path: string, max: number): string {
  if (typeof value !== "string" || value.length > max) {
    return fail(path, `a string of 0–${max} characters`);
  }
  return value;
}

function bool(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "a boolean");
  return value;
}

function finite(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fail(path, "a finite number");
  return value;
}

function bounded(value: unknown, path: string, min: number, max: number): number {
  const parsed = finite(value, path);
  if (parsed < min || parsed > max) return fail(path, `between ${min} and ${max}`);
  return parsed;
}

function integer(value: unknown, path: string, min = 0, max = Number.MAX_SAFE_INTEGER): number {
  const parsed = bounded(value, path, min, max);
  if (!Number.isInteger(parsed)) return fail(path, "an integer");
  return parsed;
}

function uuid(value: unknown, path: string): string {
  const parsed = text(value, path, 64);
  if (!UUID_PATTERN.test(parsed)) return fail(path, "a UUID");
  return parsed;
}

function nullableUuid(value: unknown, path: string): string | null {
  return value === null ? null : uuid(value, path);
}

const SHA256_PATTERN = /^[a-f0-9]{64}$/;

function sha256(value: unknown, path: string): string {
  const parsed = text(value, path, 64);
  if (!SHA256_PATTERN.test(parsed)) return fail(path, "a lowercase SHA-256 digest");
  return parsed;
}

function oneOf<const T extends string>(value: unknown, values: readonly T[], path: string): T {
  const parsed = text(value, path, 120);
  if (!values.includes(parsed as T)) return fail(path, values.join(" | "));
  return parsed as T;
}

function strings(value: unknown, path: string, maxItems = 32, itemMax = 4_000): readonly string[] {
  const values = array(value, path);
  if (values.length > maxItems) fail(path, `an array of no more than ${maxItems} strings`);
  return values.map((item, index) => text(item, `${path}[${index}]`, itemMax));
}

function parseComplex(value: unknown, path: string): ComplexValue {
  const input = record(value, path);
  exactKeys(input, ["real", "imag"], path);
  const real = bounded(input.real, `${path}.real`, -1e100, 1e100);
  const imag = bounded(input.imag, `${path}.imag`, -1e100, 1e100);
  return { real, imag };
}

const SYMBOL_PATTERN = /^[A-Za-z][A-Za-z0-9_]{0,31}$/;

function parseScientificRequest(value: unknown, path: string): SupportedScientificRequest {
  const input = record(value, path);
  const kind = oneOf(
    input.kind,
    [
      "symbolic_equivalence",
      "numerical_normalization",
      "two_level_simulation",
      "rectangular_barrier_tunnelling",
    ] as const,
    `${path}.kind`,
  );
  if (kind === "symbolic_equivalence") {
    exactKeys(input, ["kind", "left", "right", "symbols", "timeout_seconds"], path);
    const symbols = strings(input.symbols, `${path}.symbols`, 16, 32);
    if (symbols.some((symbol) => !SYMBOL_PATTERN.test(symbol)) || new Set(symbols).size !== symbols.length) {
      fail(`${path}.symbols`, "unique safe identifiers");
    }
    return {
      kind,
      left: text(input.left, `${path}.left`, 1_024),
      right: text(input.right, `${path}.right`, 1_024),
      symbols,
      timeout_seconds: bounded(input.timeout_seconds, `${path}.timeout_seconds`, 0.1, 5),
    };
  }
  if (kind === "numerical_normalization") {
    exactKeys(input, ["kind", "state", "target_norm_squared", "absolute_tolerance"], path);
    const stateValues = array(input.state, `${path}.state`);
    if (stateValues.length < 1 || stateValues.length > 4_096) {
      fail(`${path}.state`, "an array with 1–4096 amplitudes");
    }
    return {
      kind,
      state: stateValues.map((item, index) => parseComplex(item, `${path}.state[${index}]`)),
      target_norm_squared: bounded(input.target_norm_squared, `${path}.target_norm_squared`, Number.MIN_VALUE, 1e12),
      absolute_tolerance: bounded(input.absolute_tolerance, `${path}.absolute_tolerance`, Number.MIN_VALUE, 1e-2),
    };
  }

  if (kind === "rectangular_barrier_tunnelling") {
    exactKeys(
      input,
      [
        "kind",
        "energy_eV",
        "barrier_height_eV",
        "barrier_width_m",
        "particle_mass_kg",
        "conservation_tolerance",
      ],
      path,
    );
    const energy = bounded(input.energy_eV, `${path}.energy_eV`, Number.MIN_VALUE, 1e6);
    const height = bounded(input.barrier_height_eV, `${path}.barrier_height_eV`, Number.MIN_VALUE, 1e6);
    const width = bounded(input.barrier_width_m, `${path}.barrier_width_m`, Number.MIN_VALUE, 1e-3);
    const mass = bounded(input.particle_mass_kg, `${path}.particle_mass_kg`, Number.MIN_VALUE, 1e-21);
    if (Math.abs(energy - height) <= 1e-9 * height) {
      fail(`${path}.energy_eV`, "not approximately equal to barrier_height_eV");
    }
    return {
      kind,
      energy_eV: energy,
      barrier_height_eV: height,
      barrier_width_m: width,
      particle_mass_kg: mass,
      conservation_tolerance: bounded(
        input.conservation_tolerance,
        `${path}.conservation_tolerance`,
        Number.MIN_VALUE,
        1e-2,
      ),
    };
  }

  exactKeys(
    input,
    [
      "kind",
      "initial_state",
      "rabi_frequency",
      "detuning",
      "duration",
      "steps",
      "absolute_tolerance",
    ],
    path,
  );
  const initial = array(input.initial_state, `${path}.initial_state`);
  if (initial.length !== 2) fail(`${path}.initial_state`, "exactly two amplitudes");
  const rabi = bounded(input.rabi_frequency, `${path}.rabi_frequency`, -1e6, 1e6);
  const detuning = bounded(input.detuning, `${path}.detuning`, -1e6, 1e6);
  const duration = bounded(input.duration, `${path}.duration`, Number.MIN_VALUE, 1e4);
  if (Math.max(Math.abs(rabi), Math.abs(detuning)) * duration > 1_000) {
    fail(path, "within the evolution-work guard");
  }
  return {
    kind,
    initial_state: [
      parseComplex(initial[0], `${path}.initial_state[0]`),
      parseComplex(initial[1], `${path}.initial_state[1]`),
    ],
    rabi_frequency: rabi,
    detuning,
    duration,
    steps: integer(input.steps, `${path}.steps`, 2, 2_001),
    absolute_tolerance: bounded(input.absolute_tolerance, `${path}.absolute_tolerance`, Number.MIN_VALUE, 1e-2),
  };
}

export function parseTeachingTurnRequest(value: unknown): TeachingTurnRequest {
  const input = record(value, "turnRequest");
  exactKeys(
    input,
    [
      "conversation_id",
      "mode",
      "message",
      "student_attempt",
      "attachment_ids",
      "scientific_request",
      "learning_native",
      "client_request_id",
    ],
    "turnRequest",
  );
  const mode = oneOf(input.mode, TEACHING_MODES, "turnRequest.mode");
  const message = text(input.message, "turnRequest.message", 4_000).trim();
  if (!message) fail("turnRequest.message", "non-blank");
  const attempt = input.student_attempt === null
    ? null
    : text(input.student_attempt, "turnRequest.student_attempt", 12_000).trim();
  const attachmentIds = (input.attachment_ids === undefined
    ? []
    : array(input.attachment_ids, "turnRequest.attachment_ids")
  ).map((item, index) => uuid(item, `turnRequest.attachment_ids[${index}]`));
  if (attachmentIds.length > 8 || new Set(attachmentIds).size !== attachmentIds.length) {
    fail("turnRequest.attachment_ids", "at most eight unique attachment UUIDs");
  }
  // PRD V3.0 P1-2: optional client-generated idempotency key.  When present
  // it must be a bounded ASCII string so the backend can index it.
  const clientRequestId =
    input.client_request_id === undefined || input.client_request_id === null
      ? null
      : text(input.client_request_id, "turnRequest.client_request_id", 128).trim();
  return {
    conversation_id: nullableUuid(input.conversation_id, "turnRequest.conversation_id"),
    mode,
    message,
    student_attempt: attempt || null,
    attachment_ids: attachmentIds,
    scientific_request:
      input.scientific_request === null
        ? null
        : parseScientificRequest(input.scientific_request, "turnRequest.scientific_request"),
    learning_native:
      input.learning_native === undefined || input.learning_native === null
        ? null
        : parseLearningNativeSubmission(input.learning_native, "turnRequest.learning_native"),
    client_request_id: clientRequestId || null,
  };
}

function parseLearningNativeSubmission(value: unknown, path: string): LearningNativeSubmission {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "commitment",
      "confidence",
      "teach_back",
      "transfer_attempt",
      "solo_attempt",
      "request_transfer",
      "request_solo_exit",
      "request_teach_back",
      "request_transfer_task",
    ],
    path,
  );
  return {
    commitment:
      input.commitment === undefined || input.commitment === null
        ? null
        : parseCognitiveCommitment(input.commitment, `${path}.commitment`),
    confidence:
      input.confidence === undefined || input.confidence === null
        ? null
        : bounded(input.confidence, `${path}.confidence`, 0, 1),
    teach_back:
      input.teach_back === undefined || input.teach_back === null
        ? null
        : parseTeachBackSubmission(input.teach_back, `${path}.teach_back`),
    transfer_attempt:
      input.transfer_attempt === undefined || input.transfer_attempt === null
        ? null
        : parseTransferAttemptSubmission(input.transfer_attempt, `${path}.transfer_attempt`),
    solo_attempt:
      input.solo_attempt === undefined || input.solo_attempt === null
        ? null
        : parseSoloAttemptSubmission(input.solo_attempt, `${path}.solo_attempt`),
    request_transfer:
      input.request_transfer === undefined ? false : bool(input.request_transfer, `${path}.request_transfer`),
    request_solo_exit:
      input.request_solo_exit === undefined
        ? false
        : bool(input.request_solo_exit, `${path}.request_solo_exit`),
    request_teach_back:
      input.request_teach_back === undefined
        ? false
        : bool(input.request_teach_back, `${path}.request_teach_back`),
    request_transfer_task:
      input.request_transfer_task === undefined
        ? false
        : bool(input.request_transfer_task, `${path}.request_transfer_task`),
  };
}

function parseCognitiveCommitment(value: unknown, path: string): CognitiveCommitment {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "gate_decision",
      "attempt_required",
      "attempt_type",
      "candidate_prompt",
      "reason_summary",
      "accepted",
      "confidence",
    ],
    path,
  );
  return {
    gate_decision: oneOf(
      input.gate_decision,
      ["attempt_required", "proceed"] as const,
      `${path}.gate_decision`,
    ),
    attempt_required: bool(input.attempt_required, `${path}.attempt_required`),
    attempt_type:
      input.attempt_type === undefined || input.attempt_type === null
        ? null
        : oneOf(
            input.attempt_type,
            [
              "prediction",
              "first_step",
              "physical_reason",
              "diagram",
              "option_with_confidence",
              "self_explanation",
            ] as const,
            `${path}.attempt_type`,
          ),
    candidate_prompt: boundedText(input.candidate_prompt, `${path}.candidate_prompt`, 1200),
    reason_summary: boundedText(input.reason_summary, `${path}.reason_summary`, 600),
    accepted: bool(input.accepted, `${path}.accepted`),
    confidence:
      input.confidence === undefined || input.confidence === null
        ? null
        : bounded(input.confidence, `${path}.confidence`, 0, 1),
  };
}

function parseTeachBackSubmission(
  value: unknown,
  path: string,
): LearningNativeSubmission["teach_back"] {
  const input = record(value, path);
  exactKeys(input, ["reconstruction", "target_concept_ids"], path);
  const targetIds = array(input.target_concept_ids, `${path}.target_concept_ids`).map((item, index) =>
    uuid(item, `${path}.target_concept_ids[${index}]`),
  );
  return {
    reconstruction: text(input.reconstruction, `${path}.reconstruction`, 12_000),
    target_concept_ids: targetIds,
  };
}

function parseTransferAttemptSubmission(
  value: unknown,
  path: string,
): LearningNativeSubmission["transfer_attempt"] {
  const input = record(value, path);
  exactKeys(input, ["transfer_task_id", "response", "confidence"], path);
  return {
    transfer_task_id: uuid(input.transfer_task_id, `${path}.transfer_task_id`),
    response: text(input.response, `${path}.response`, 12_000),
    confidence:
      input.confidence === undefined || input.confidence === null
        ? null
        : bounded(input.confidence, `${path}.confidence`, 0, 1),
  };
}

function parseSoloAttemptSubmission(
  value: unknown,
  path: string,
): LearningNativeSubmission["solo_attempt"] {
  const input = record(value, path);
  exactKeys(input, ["response", "confidence"], path);
  return {
    response: text(input.response, `${path}.response`, 12_000),
    confidence:
      input.confidence === undefined || input.confidence === null
        ? null
        : bounded(input.confidence, `${path}.confidence`, 0, 1),
  };
}

function parseLocator(value: unknown, path: string): EvidenceLocator {
  const input = record(value, path);
  const locatorType = oneOf(
    input.locator_type,
    ["pdf_page", "slide", "docx_paragraph", "xlsx_row", "text_lines"] as const,
    `${path}.locator_type`,
  );
  const optionalPositive = (key: string): number | null =>
    input[key] === null ? null : integer(input[key], `${path}.${key}`, 1);
  const optionalString = (key: string): string | null =>
    input[key] === null ? null : text(input[key], `${path}.${key}`, 500);
  const locator: EvidenceLocator = {
    locator_type: locatorType,
    physical_page: optionalPositive("physical_page"),
    printed_page_label: optionalString("printed_page_label"),
    slide_number: optionalPositive("slide_number"),
    paragraph_start: optionalPositive("paragraph_start"),
    paragraph_end: optionalPositive("paragraph_end"),
    sheet_name: optionalString("sheet_name"),
    row_start: optionalPositive("row_start"),
    row_end: optionalPositive("row_end"),
    line_start: optionalPositive("line_start"),
    line_end: optionalPositive("line_end"),
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

function parseContribution(value: unknown, path: string): EvidenceContribution {
  const input = record(value, path);
  return {
    channel: oneOf(
      input.channel,
      ["postgres_full_text", "pgvector_semantic", "neo4j_graph"] as const,
      `${path}.channel`,
    ),
    rank: integer(input.rank, `${path}.rank`, 1),
    raw_score: input.raw_score === null ? null : finite(input.raw_score, `${path}.raw_score`),
    fused_score: bounded(input.fused_score, `${path}.fused_score`, 0, Number.MAX_VALUE),
  };
}

function normalized(value: string): string {
  return value.toLocaleLowerCase().replace(/\s+/g, "");
}

function parseEvidence(value: unknown, path: string): TeachingEvidence {
  const input = record(value, path);
  const sourceChunk = text(input.source_chunk, `${path}.source_chunk`, 200_000);
  const evidenceSnippet = text(input.evidence_snippet, `${path}.evidence_snippet`, 200_000);
  if (!normalized(sourceChunk).includes(normalized(evidenceSnippet))) {
    fail(`${path}.evidence_snippet`, "literal content from source_chunk");
  }
  const contributions = array(input.contributions, `${path}.contributions`).map((item, index) =>
    parseContribution(item, `${path}.contributions[${index}]`),
  );
  if (contributions.length < 1) fail(`${path}.contributions`, "a non-empty array");
  return {
    evidence_id: uuid(input.evidence_id, `${path}.evidence_id`),
    chunk_id: uuid(input.chunk_id, `${path}.chunk_id`),
    document_id: uuid(input.document_id, `${path}.document_id`),
    document_version_id: uuid(input.document_version_id, `${path}.document_version_id`),
    document_title: text(input.document_title, `${path}.document_title`, 2_000),
    document_version: integer(input.document_version, `${path}.document_version`, 1),
    source_file_name: text(input.source_file_name, `${path}.source_file_name`, 2_000),
    source_file_sha256: sha256(input.source_file_sha256, `${path}.source_file_sha256`),
    source_chunk_sha256: sha256(input.source_chunk_sha256, `${path}.source_chunk_sha256`),
    evidence_sha256: sha256(input.evidence_sha256, `${path}.evidence_sha256`),
    curriculum_edition_id:
      input.curriculum_edition_id === null
        ? null
        : uuid(input.curriculum_edition_id, `${path}.curriculum_edition_id`),
    chapter: nullableText(input.chapter, `${path}.chapter`, 1_000),
    section_path: strings(input.section_path, `${path}.section_path`, 32, 1_000),
    locator: parseLocator(input.locator, `${path}.locator`),
    source_chunk: sourceChunk,
    evidence_snippet: evidenceSnippet,
    kind: oneOf(
      input.kind,
      [
        "course_material",
        "teacher_curated",
        "symbolic_verification",
        "numerical_verification",
        "simulation",
        "code_test",
        "model_inference",
      ] as const,
      `${path}.kind`,
    ),
    authority_priority: integer(input.authority_priority, `${path}.authority_priority`, 0, 100),
    contributions,
  };
}

function parseEvidencePacket(value: unknown, path: string): EvidencePacket {
  const input = record(value, path);
  const evidence = array(input.evidence, `${path}.evidence`).map((item, index) =>
    parseEvidence(item, `${path}.evidence[${index}]`),
  );
  const coverage = oneOf(input.coverage, ["sufficient", "partial", "not_found"] as const, `${path}.coverage`);
  if ((coverage === "not_found") !== (evidence.length === 0)) {
    fail(path, "coverage consistent with evidence presence");
  }
  const createdAt = text(input.created_at, `${path}.created_at`, 100);
  if (Number.isNaN(Date.parse(createdAt))) fail(`${path}.created_at`, "an ISO date-time");
  const graphNodes = array(input.graph_nodes, `${path}.graph_nodes`).map((item, index) => {
    const node = record(item, `${path}.graph_nodes[${index}]`);
    return {
      id: uuid(node.id, `${path}.graph_nodes[${index}].id`),
      node_type: text(node.node_type, `${path}.graph_nodes[${index}].node_type`, 160),
      name: text(node.name, `${path}.graph_nodes[${index}].name`, 1_000),
      aliases: strings(node.aliases, `${path}.graph_nodes[${index}].aliases`, 64, 1_000),
    };
  });
  const nodeIds = new Set(graphNodes.map((node) => node.id));
  const graphEdges = array(input.graph_edges, `${path}.graph_edges`).map((item, index) => {
    const edge = record(item, `${path}.graph_edges[${index}]`);
    const parsed = {
      id: uuid(edge.id, `${path}.graph_edges[${index}].id`),
      source_id: uuid(edge.source_id, `${path}.graph_edges[${index}].source_id`),
      target_id: uuid(edge.target_id, `${path}.graph_edges[${index}].target_id`),
      relation_type: text(edge.relation_type, `${path}.graph_edges[${index}].relation_type`, 160),
    };
    if (!nodeIds.has(parsed.source_id) || !nodeIds.has(parsed.target_id)) {
      fail(`${path}.graph_edges[${index}]`, "an edge between returned graph nodes");
    }
    return parsed;
  });
  return {
    id: uuid(input.id, `${path}.id`),
    course_id: uuid(input.course_id, `${path}.course_id`),
    curriculum_edition_id: uuid(input.curriculum_edition_id, `${path}.curriculum_edition_id`),
    query: text(input.query, `${path}.query`, 10_000),
    created_at: createdAt,
    coverage,
    evidence,
    graph_nodes: graphNodes,
    graph_edges: graphEdges,
    degraded_channels: array(input.degraded_channels, `${path}.degraded_channels`).map((item, index) =>
      oneOf(
        item,
        ["postgres_full_text", "pgvector_semantic", "neo4j_graph"] as const,
        `${path}.degraded_channels[${index}]`,
      ),
    ),
    warnings: strings(input.warnings, `${path}.warnings`, 64, 2_000),
  };
}

function parseBundleNode(
  value: unknown,
  path: string,
): EvidencePacket["graph_nodes"][number] {
  const input = record(value, path);
  exactKeys(input, ["id", "node_type", "name", "aliases"], path);
  return {
    id: uuid(input.id, `${path}.id`),
    node_type: text(input.node_type, `${path}.node_type`, 160),
    name: text(input.name, `${path}.name`, 1_000),
    aliases: strings(input.aliases, `${path}.aliases`, 64, 1_000),
  };
}

function parseCourseCitation(value: unknown, path: string): CourseCitation {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "evidence_id",
      "chunk_id",
      "document_id",
      "document_version_id",
      "document_title",
      "document_version",
      "source_file_name",
      "source_file_sha256",
      "source_chunk_sha256",
      "evidence_sha256",
      "chapter",
      "section_path",
      "locator",
      "evidence_snippet",
      "kind",
      "authority_priority",
    ],
    path,
  );
  return {
    evidence_id: uuid(input.evidence_id, `${path}.evidence_id`),
    chunk_id: uuid(input.chunk_id, `${path}.chunk_id`),
    document_id: uuid(input.document_id, `${path}.document_id`),
    document_version_id: uuid(input.document_version_id, `${path}.document_version_id`),
    document_title: text(input.document_title, `${path}.document_title`, 2_000),
    document_version: integer(input.document_version, `${path}.document_version`, 1),
    source_file_name: text(input.source_file_name, `${path}.source_file_name`, 2_000),
    source_file_sha256: sha256(input.source_file_sha256, `${path}.source_file_sha256`),
    source_chunk_sha256: sha256(input.source_chunk_sha256, `${path}.source_chunk_sha256`),
    evidence_sha256: sha256(input.evidence_sha256, `${path}.evidence_sha256`),
    chapter: nullableText(input.chapter, `${path}.chapter`, 1_000),
    section_path: strings(input.section_path, `${path}.section_path`, 32, 1_000),
    locator: parseLocator(input.locator, `${path}.locator`),
    evidence_snippet: text(input.evidence_snippet, `${path}.evidence_snippet`, 200_000),
    kind: oneOf(
      input.kind,
      [
        "course_material",
        "teacher_curated",
        "symbolic_verification",
        "numerical_verification",
        "simulation",
        "code_test",
        "model_inference",
      ] as const,
      `${path}.kind`,
    ),
    authority_priority: integer(input.authority_priority, `${path}.authority_priority`, 0, 100),
  };
}

function sameJson(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function parseEvidenceBundle(
  value: unknown,
  path: string,
  packet: EvidencePacket,
): EvidenceBundle {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "course_id",
      "curriculum_edition_id",
      "query",
      "retrieval_query",
      "coverage",
      "coverage_rationale",
      "source_chunks",
      "citations",
      "relevant_concepts",
      "graph_nodes",
      "graph_edges",
      "prerequisite_paths",
      "misconception_links",
      "formulas",
      "degraded_channels",
      "warnings",
      "conflicts",
    ],
    path,
  );
  const sourceChunks = array(input.source_chunks, `${path}.source_chunks`).map((item, index) =>
    parseEvidence(item, `${path}.source_chunks[${index}]`),
  );
  const citations = array(input.citations, `${path}.citations`).map((item, index) =>
    parseCourseCitation(item, `${path}.citations[${index}]`),
  );
  if (sourceChunks.length > 6 || citations.length !== sourceChunks.length) {
    fail(path, "at most six source chunks with one exact citation each");
  }
  for (const [index, source] of sourceChunks.entries()) {
    const citation = citations[index];
    if (
      !citation ||
      citation.evidence_id !== source.evidence_id ||
      citation.chunk_id !== source.chunk_id ||
      citation.document_id !== source.document_id ||
      citation.document_version_id !== source.document_version_id ||
      citation.source_file_sha256 !== source.source_file_sha256 ||
      citation.source_chunk_sha256 !== source.source_chunk_sha256 ||
      citation.evidence_sha256 !== source.evidence_sha256 ||
      citation.evidence_snippet !== source.evidence_snippet ||
      !sameJson(citation.locator, source.locator)
    ) {
      fail(`${path}.citations[${index}]`, "the exact provenance of its source chunk");
    }
  }
  if (!sameJson(sourceChunks, packet.evidence)) {
    fail(`${path}.source_chunks`, "the evidence in the release packet");
  }

  const graphNodes = array(input.graph_nodes, `${path}.graph_nodes`).map((item, index) =>
    parseBundleNode(item, `${path}.graph_nodes[${index}]`),
  );
  const nodeById = new Map(graphNodes.map((node) => [node.id, node] as const));
  const graphEdges = array(input.graph_edges, `${path}.graph_edges`).map((item, index) => {
    const edge = record(item, `${path}.graph_edges[${index}]`);
    exactKeys(edge, ["id", "source_id", "target_id", "relation_type"], `${path}.graph_edges[${index}]`);
    const parsed = {
      id: uuid(edge.id, `${path}.graph_edges[${index}].id`),
      source_id: uuid(edge.source_id, `${path}.graph_edges[${index}].source_id`),
      target_id: uuid(edge.target_id, `${path}.graph_edges[${index}].target_id`),
      relation_type: text(edge.relation_type, `${path}.graph_edges[${index}].relation_type`, 160),
    };
    if (!nodeById.has(parsed.source_id) || !nodeById.has(parsed.target_id)) {
      fail(`${path}.graph_edges[${index}]`, "an edge between bundled graph nodes");
    }
    return parsed;
  });
  if (!sameJson(graphNodes, packet.graph_nodes) || !sameJson(graphEdges, packet.graph_edges)) {
    fail(path, "graph context identical to the release packet");
  }
  const edgeById = new Map(graphEdges.map((edge) => [edge.id, edge] as const));
  const parseNodeSubset = (key: "relevant_concepts" | "formulas") =>
    array(input[key], `${path}.${key}`).map((item, index) => {
      const node = parseBundleNode(item, `${path}.${key}[${index}]`);
      if (!sameJson(nodeById.get(node.id), node)) {
        fail(`${path}.${key}[${index}]`, "a node from graph_nodes");
      }
      return node;
    });
  const relevantConcepts = parseNodeSubset("relevant_concepts");
  const formulas = parseNodeSubset("formulas");
  const prerequisitePaths = array(input.prerequisite_paths, `${path}.prerequisite_paths`).map(
    (item, index) => {
      const itemPath = `${path}.prerequisite_paths[${index}]`;
      const relation = record(item, itemPath);
      exactKeys(relation, ["relation_id", "prerequisite", "target"], itemPath);
      const relationId = uuid(relation.relation_id, `${itemPath}.relation_id`);
      const prerequisite = parseBundleNode(relation.prerequisite, `${itemPath}.prerequisite`);
      const target = parseBundleNode(relation.target, `${itemPath}.target`);
      const edge = edgeById.get(relationId);
      if (
        edge?.relation_type !== "PREREQUISITE_OF" ||
        edge.source_id !== prerequisite.id ||
        edge.target_id !== target.id
      ) {
        fail(itemPath, "a prerequisite edge from the bundled graph");
      }
      return { relation_id: relationId, prerequisite, target };
    },
  );
  const misconceptionLinks = array(input.misconception_links, `${path}.misconception_links`).map(
    (item, index) => {
      const itemPath = `${path}.misconception_links[${index}]`;
      const relation = record(item, itemPath);
      exactKeys(relation, ["relation_id", "source", "misconception"], itemPath);
      const relationId = uuid(relation.relation_id, `${itemPath}.relation_id`);
      const source = parseBundleNode(relation.source, `${itemPath}.source`);
      const misconception = parseBundleNode(relation.misconception, `${itemPath}.misconception`);
      const edge = edgeById.get(relationId);
      if (
        edge?.relation_type !== "HAS_MISCONCEPTION" ||
        edge.source_id !== source.id ||
        edge.target_id !== misconception.id ||
        misconception.node_type !== "Misconception"
      ) {
        fail(itemPath, "a misconception edge from the bundled graph");
      }
      return { relation_id: relationId, source, misconception };
    },
  );
  const evidenceIds = new Set(sourceChunks.map((item) => item.evidence_id));
  const conflicts = array(input.conflicts, `${path}.conflicts`).map((item, index) => {
    const itemPath = `${path}.conflicts[${index}]`;
    const conflict = record(item, itemPath);
    exactKeys(conflict, ["evidence_ids", "summary"], itemPath);
    const identifiers = strings(conflict.evidence_ids, `${itemPath}.evidence_ids`, 6, 64).map(
      (identifier, identifierIndex) => uuid(identifier, `${itemPath}.evidence_ids[${identifierIndex}]`),
    );
    if (
      identifiers.length < 2 ||
      new Set(identifiers).size !== identifiers.length ||
      identifiers.some((identifier) => !evidenceIds.has(identifier))
    ) {
      fail(`${itemPath}.evidence_ids`, "2–6 distinct bundled evidence IDs");
    }
    return { evidence_ids: identifiers, summary: text(conflict.summary, `${itemPath}.summary`, 500) };
  });
  if (conflicts.length > 6) fail(`${path}.conflicts`, "at most six conflicts");
  const coverage = oneOf(
    input.coverage,
    ["sufficient", "partial", "insufficient"] as const,
    `${path}.coverage`,
  );
  const expectedCoverage = packet.coverage === "not_found" ? "insufficient" : packet.coverage;
  if (coverage !== expectedCoverage) fail(`${path}.coverage`, "consistent with the release packet");
  const courseId = uuid(input.course_id, `${path}.course_id`);
  const editionId = uuid(input.curriculum_edition_id, `${path}.curriculum_edition_id`);
  if (courseId !== packet.course_id || editionId !== packet.curriculum_edition_id) {
    fail(path, "inside the release packet course scope");
  }
  return {
    course_id: courseId,
    curriculum_edition_id: editionId,
    query: text(input.query, `${path}.query`, 5_000),
    retrieval_query: text(input.retrieval_query, `${path}.retrieval_query`, 5_000),
    coverage,
    coverage_rationale: text(input.coverage_rationale, `${path}.coverage_rationale`, 500),
    source_chunks: sourceChunks,
    citations,
    relevant_concepts: relevantConcepts,
    graph_nodes: graphNodes,
    graph_edges: graphEdges,
    prerequisite_paths: prerequisitePaths,
    misconception_links: misconceptionLinks,
    formulas,
    degraded_channels: array(input.degraded_channels, `${path}.degraded_channels`).map((item, index) =>
      oneOf(
        item,
        ["postgres_full_text", "pgvector_semantic", "neo4j_graph"] as const,
        `${path}.degraded_channels[${index}]`,
      ),
    ),
    warnings: strings(input.warnings, `${path}.warnings`, 32, 2_000),
    conflicts,
  };
}

const EXTRACTION_METHODS = [
  "native",
  "qwen_vision",
  "mineru",
  "vision_ocr",
  "unlimited_ocr",
] as const;
const CONFIRMATION_STATES = ["not_required", "required", "confirmed", "rejected"] as const;

function boundedText(value: unknown, path: string, max: number): string {
  if (typeof value !== "string" || value.length > max) {
    return fail(path, `a string of 0–${max} characters`);
  }
  return value;
}

function nullableBoundedText(value: unknown, path: string, max: number): string | null {
  return value === null ? null : boundedText(value, path, max);
}

function boundedStrings(
  value: unknown,
  path: string,
  maxItems: number,
  itemMax: number,
): readonly string[] {
  const values = array(value, path);
  if (values.length > maxItems) fail(path, `an array of no more than ${maxItems} strings`);
  return values.map((item, index) => boundedText(item, `${path}[${index}]`, itemMax));
}

function nullableFinite(value: unknown, path: string): number | null {
  return value === null ? null : finite(value, path);
}

function nullableInteger(
  value: unknown,
  path: string,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
): number | null {
  return value === null ? null : integer(value, path, min, max);
}

function parseMultimodalBoundingBox(value: unknown, path: string): UnknownRecord {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "x_min",
      "y_min",
      "x_max",
      "y_max",
      "coordinate_system",
      "page_number",
      "slide_number",
      "region_id",
    ],
    path,
  );
  const xMin = bounded(input.x_min, `${path}.x_min`, 0, Number.MAX_VALUE);
  const yMin = bounded(input.y_min, `${path}.y_min`, 0, Number.MAX_VALUE);
  const xMax = bounded(input.x_max, `${path}.x_max`, Number.MIN_VALUE, Number.MAX_VALUE);
  const yMax = bounded(input.y_max, `${path}.y_max`, Number.MIN_VALUE, Number.MAX_VALUE);
  const coordinateSystem = oneOf(
    input.coordinate_system,
    ["pixels", "points", "normalized", "emu"] as const,
    `${path}.coordinate_system`,
  );
  const pageNumber = nullableInteger(input.page_number, `${path}.page_number`, 1);
  const slideNumber = nullableInteger(input.slide_number, `${path}.slide_number`, 1);
  if (
    xMax <= xMin ||
    yMax <= yMin ||
    (pageNumber !== null && slideNumber !== null) ||
    (coordinateSystem === "normalized" && (xMax > 1 || yMax > 1))
  ) {
    fail(path, "a valid, unambiguous source bounding box");
  }
  nullableText(input.region_id, `${path}.region_id`, 160);
  return input;
}

function parseMultimodalAmbiguity(value: unknown, path: string): UnknownRecord {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "ambiguity_id",
      "field_path",
      "reason",
      "candidates",
      "bounding_boxes",
      "requires_confirmation",
    ],
    path,
  );
  text(input.ambiguity_id, `${path}.ambiguity_id`, 160);
  text(input.field_path, `${path}.field_path`, 500);
  text(input.reason, `${path}.reason`, 2_000);
  const candidates = array(input.candidates, `${path}.candidates`);
  if (candidates.length > 12) fail(`${path}.candidates`, "at most 12 candidates");
  candidates.forEach((candidate, index) => {
    const candidatePath = `${path}.candidates[${index}]`;
    const parsed = record(candidate, candidatePath);
    exactKeys(parsed, ["value", "confidence"], candidatePath);
    text(parsed.value, `${candidatePath}.value`, 4_000);
    bounded(parsed.confidence, `${candidatePath}.confidence`, 0, 1);
  });
  const boxes = array(input.bounding_boxes, `${path}.bounding_boxes`);
  if (boxes.length > 20) fail(`${path}.bounding_boxes`, "at most 20 boxes");
  boxes.forEach((box, index) =>
    parseMultimodalBoundingBox(box, `${path}.bounding_boxes[${index}]`),
  );
  bool(input.requires_confirmation, `${path}.requires_confirmation`);
  return input;
}

function parseDetectedMath(
  value: unknown,
  path: string,
  withOrdinal: boolean,
): Readonly<{ ambiguityIds: readonly string[]; ordinal: number | null }> {
  const input = record(value, path);
  exactKeys(
    input,
    [
      ...(withOrdinal ? ["ordinal"] : []),
      "source_text",
      "latex",
      "confidence",
      "bounding_boxes",
      "ambiguity_ids",
    ],
    path,
  );
  text(input.source_text, `${path}.source_text`, withOrdinal ? 12_000 : 8_000);
  text(input.latex, `${path}.latex`, withOrdinal ? 12_000 : 8_000);
  bounded(input.confidence, `${path}.confidence`, 0, 1);
  const boxes = array(input.bounding_boxes, `${path}.bounding_boxes`);
  if (boxes.length > 20) fail(`${path}.bounding_boxes`, "at most 20 boxes");
  boxes.forEach((box, index) =>
    parseMultimodalBoundingBox(box, `${path}.bounding_boxes[${index}]`),
  );
  const ambiguityIds = strings(input.ambiguity_ids, `${path}.ambiguity_ids`, 20, 160);
  return {
    ambiguityIds,
    ordinal: withOrdinal ? integer(input.ordinal, `${path}.ordinal`, 1) : null,
  };
}

function parseVisualEvidence(input: UnknownRecord, path: string): HitlMultimodalEvidence {
  exactKeys(
    input,
    [
      "detected_text",
      "equations",
      "derivation_steps",
      "diagram_interpretation",
      "plot_axes",
      "plot_interpretation",
      "figure_description",
      "confidence",
      "bounding_boxes",
      "ambiguities",
      "evidence_type",
      "attachment_id",
      "original_file_reference",
      "extraction_method",
      "confirmation_state",
      "requires_confirmation",
    ],
    path,
  );
  boundedText(input.detected_text, `${path}.detected_text`, 100_000);
  const ambiguities = array(input.ambiguities, `${path}.ambiguities`);
  if (ambiguities.length > 100) fail(`${path}.ambiguities`, "at most 100 ambiguities");
  const ambiguityIds = new Set<string>();
  ambiguities.forEach((ambiguity, index) => {
    const ambiguityPath = `${path}.ambiguities[${index}]`;
    const parsed = parseMultimodalAmbiguity(ambiguity, ambiguityPath);
    const identifier = text(parsed.ambiguity_id, `${ambiguityPath}.ambiguity_id`, 160);
    if (ambiguityIds.has(identifier)) fail(`${ambiguityPath}.ambiguity_id`, "unique");
    ambiguityIds.add(identifier);
  });
  const referencedIds: string[] = [];
  const equations = array(input.equations, `${path}.equations`);
  if (equations.length > 200) fail(`${path}.equations`, "at most 200 equations");
  equations.forEach((equation, index) => {
    referencedIds.push(...parseDetectedMath(equation, `${path}.equations[${index}]`, false).ambiguityIds);
  });
  const steps = array(input.derivation_steps, `${path}.derivation_steps`);
  if (steps.length > 200) fail(`${path}.derivation_steps`, "at most 200 steps");
  steps.forEach((step, index) => {
    const parsed = parseDetectedMath(step, `${path}.derivation_steps[${index}]`, true);
    if (parsed.ordinal !== index + 1) fail(`${path}.derivation_steps`, "contiguous one-based ordinals");
    referencedIds.push(...parsed.ambiguityIds);
  });
  if (referencedIds.some((identifier) => !ambiguityIds.has(identifier))) {
    fail(path, "math items referencing only declared ambiguities");
  }
  nullableBoundedText(input.diagram_interpretation, `${path}.diagram_interpretation`, 20_000);
  nullableBoundedText(input.plot_interpretation, `${path}.plot_interpretation`, 20_000);
  nullableBoundedText(input.figure_description, `${path}.figure_description`, 20_000);
  const axes = array(input.plot_axes, `${path}.plot_axes`);
  if (axes.length > 8) fail(`${path}.plot_axes`, "at most eight plot axes");
  axes.forEach((axis, index) => {
    const axisPath = `${path}.plot_axes[${index}]`;
    const parsed = record(axis, axisPath);
    exactKeys(parsed, ["axis", "label", "unit", "minimum", "maximum", "confidence"], axisPath);
    oneOf(parsed.axis, ["x", "y", "z", "color"] as const, `${axisPath}.axis`);
    nullableBoundedText(parsed.label, `${axisPath}.label`, 500);
    nullableBoundedText(parsed.unit, `${axisPath}.unit`, 160);
    const minimum = nullableFinite(parsed.minimum, `${axisPath}.minimum`);
    const maximum = nullableFinite(parsed.maximum, `${axisPath}.maximum`);
    if (minimum !== null && maximum !== null && maximum < minimum) {
      fail(axisPath, "an ordered plot-axis range");
    }
    bounded(parsed.confidence, `${axisPath}.confidence`, 0, 1);
  });
  const boxes = array(input.bounding_boxes, `${path}.bounding_boxes`);
  if (boxes.length > 500) fail(`${path}.bounding_boxes`, "at most 500 boxes");
  boxes.forEach((box, index) =>
    parseMultimodalBoundingBox(box, `${path}.bounding_boxes[${index}]`),
  );
  return parseMultimodalEvidenceEnvelope(input, path, "visual");
}

function parseDocumentLocator(value: unknown, path: string): UnknownRecord {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "page_number",
      "page_label",
      "slide_number",
      "paragraph_start",
      "paragraph_end",
      "line_start",
      "line_end",
    ],
    path,
  );
  const page = nullableInteger(input.page_number, `${path}.page_number`, 1);
  const slide = nullableInteger(input.slide_number, `${path}.slide_number`, 1);
  const paragraphStart = nullableInteger(input.paragraph_start, `${path}.paragraph_start`, 0);
  const paragraphEnd = nullableInteger(input.paragraph_end, `${path}.paragraph_end`, 0);
  const lineStart = nullableInteger(input.line_start, `${path}.line_start`, 1);
  const lineEnd = nullableInteger(input.line_end, `${path}.line_end`, 1);
  nullableBoundedText(input.page_label, `${path}.page_label`, 160);
  if (
    (page === null && slide === null && paragraphStart === null && lineStart === null) ||
    (page !== null && slide !== null) ||
    (paragraphStart !== null && paragraphEnd !== null && paragraphEnd < paragraphStart) ||
    (lineStart !== null && lineEnd !== null && lineEnd < lineStart)
  ) {
    fail(path, "a valid page, slide, paragraph, or line locator");
  }
  return input;
}

function parseDocumentEvidence(input: UnknownRecord, path: string): HitlMultimodalEvidence {
  exactKeys(
    input,
    [
      "evidence_type",
      "attachment_id",
      "original_file_reference",
      "filename",
      "media_type",
      "extraction_method",
      "parser_name",
      "parser_version",
      "units",
      "page_count",
      "slide_count",
      "confidence",
      "ambiguities",
      "fallback_chain",
      "confirmation_state",
      "requires_confirmation",
    ],
    path,
  );
  text(input.filename, `${path}.filename`, 255);
  text(input.media_type, `${path}.media_type`, 255);
  text(input.parser_name, `${path}.parser_name`, 200);
  text(input.parser_version, `${path}.parser_version`, 100);
  const units = array(input.units, `${path}.units`);
  if (units.length > 2_000) fail(`${path}.units`, "at most 2,000 document units");
  units.forEach((unit, index) => {
    const unitPath = `${path}.units[${index}]`;
    const parsed = record(unit, unitPath);
    exactKeys(
      parsed,
      [
        "ordinal",
        "locator",
        "headings",
        "blocks",
        "exact_text",
        "formulas_latex",
        "tables",
        "figures",
        "captions",
      ],
      unitPath,
    );
    if (integer(parsed.ordinal, `${unitPath}.ordinal`, 0) !== index) {
      fail(`${path}.units`, "contiguous zero-based ordinals");
    }
    parseDocumentLocator(parsed.locator, `${unitPath}.locator`);
    boundedStrings(parsed.headings, `${unitPath}.headings`, 40, 20_000);
    boundedText(parsed.exact_text, `${unitPath}.exact_text`, 500_000);
    boundedStrings(parsed.formulas_latex, `${unitPath}.formulas_latex`, 500, 20_000);
    boundedStrings(parsed.tables, `${unitPath}.tables`, 200, 100_000);
    boundedStrings(parsed.figures, `${unitPath}.figures`, 200, 100_000);
    boundedStrings(parsed.captions, `${unitPath}.captions`, 200, 100_000);
    const blocks = array(parsed.blocks, `${unitPath}.blocks`);
    if (blocks.length > 2_000) fail(`${unitPath}.blocks`, "at most 2,000 blocks");
    blocks.forEach((block, blockIndex) => {
      const blockPath = `${unitPath}.blocks[${blockIndex}]`;
      const parsedBlock = record(block, blockPath);
      exactKeys(parsedBlock, ["reading_order", "kind", "exact_text", "latex", "bounding_box"], blockPath);
      integer(parsedBlock.reading_order, `${blockPath}.reading_order`, 0);
      oneOf(
        parsedBlock.kind,
        ["text", "formula", "table", "figure", "caption", "other"] as const,
        `${blockPath}.kind`,
      );
      boundedText(parsedBlock.exact_text, `${blockPath}.exact_text`, 100_000);
      nullableBoundedText(parsedBlock.latex, `${blockPath}.latex`, 20_000);
      if (parsedBlock.bounding_box !== null) {
        parseMultimodalBoundingBox(parsedBlock.bounding_box, `${blockPath}.bounding_box`);
      }
    });
  });
  const pageCount = nullableInteger(input.page_count, `${path}.page_count`, 0);
  const slideCount = nullableInteger(input.slide_count, `${path}.slide_count`, 0);
  if (pageCount !== null && slideCount !== null) {
    fail(path, "only a page count or slide count, not both");
  }
  const ambiguities = array(input.ambiguities, `${path}.ambiguities`);
  if (ambiguities.length > 100) fail(`${path}.ambiguities`, "at most 100 ambiguities");
  ambiguities.forEach((ambiguity, index) =>
    parseMultimodalAmbiguity(ambiguity, `${path}.ambiguities[${index}]`),
  );
  const fallbacks = array(input.fallback_chain, `${path}.fallback_chain`);
  if (fallbacks.length > 12) fail(`${path}.fallback_chain`, "at most 12 parse attempts");
  fallbacks.forEach((fallback, index) => {
    const fallbackPath = `${path}.fallback_chain[${index}]`;
    const parsed = record(fallback, fallbackPath);
    exactKeys(parsed, ["method", "status", "detail"], fallbackPath);
    oneOf(parsed.method, EXTRACTION_METHODS, `${fallbackPath}.method`);
    oneOf(
      parsed.status,
      ["succeeded", "partial", "failed", "unavailable", "not_needed"] as const,
      `${fallbackPath}.status`,
    );
    text(parsed.detail, `${fallbackPath}.detail`, 2_000);
  });
  return parseMultimodalEvidenceEnvelope(input, path, "document");
}

function parseMultimodalEvidenceEnvelope(
  input: UnknownRecord,
  path: string,
  evidenceType: "visual" | "document",
): HitlMultimodalEvidence {
  const confirmationState = oneOf(
    input.confirmation_state,
    CONFIRMATION_STATES,
    `${path}.confirmation_state`,
  );
  const requiresConfirmation = bool(input.requires_confirmation, `${path}.requires_confirmation`);
  if (requiresConfirmation !== (confirmationState === "required")) {
    fail(path, "a confirmation state consistent with its required flag");
  }
  return {
    ...input,
    evidence_type: oneOf(input.evidence_type, [evidenceType] as const, `${path}.evidence_type`),
    attachment_id: uuid(input.attachment_id, `${path}.attachment_id`),
    original_file_reference: text(
      input.original_file_reference,
      `${path}.original_file_reference`,
      500,
    ),
    extraction_method: oneOf(
      input.extraction_method,
      EXTRACTION_METHODS,
      `${path}.extraction_method`,
    ),
    confirmation_state: confirmationState,
    requires_confirmation: requiresConfirmation,
    confidence: bounded(input.confidence, `${path}.confidence`, 0, 1),
  };
}

function parseHitlMultimodalEvidence(value: unknown, path: string): HitlMultimodalEvidence {
  const input = record(value, path);
  const evidenceType = oneOf(input.evidence_type, ["visual", "document"] as const, `${path}.evidence_type`);
  return evidenceType === "visual"
    ? parseVisualEvidence(input, path)
    : parseDocumentEvidence(input, path);
}

function parsePerceptionTrace(value: unknown, path: string): PerceptionTraceEntry {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "attachment_id",
      "extraction_id",
      "evidence_type",
      "extraction_status",
      "confidence",
      "confirmation_state",
      "admitted_to_diagnosis",
      "exact_context_characters",
      "context_truncated",
      "scientific_request_derived",
      "scientific_derivation_ordinals",
      "confirmed_ambiguity_resolutions",
      "confirmation_source",
    ],
    path,
  );
  const derived = bool(input.scientific_request_derived, `${path}.scientific_request_derived`);
  let ordinals: readonly [number, number] | null = null;
  if (input.scientific_derivation_ordinals !== null) {
    const values = array(
      input.scientific_derivation_ordinals,
      `${path}.scientific_derivation_ordinals`,
    );
    if (values.length !== 2) {
      fail(`${path}.scientific_derivation_ordinals`, "exactly two ordinals");
    }
    ordinals = [
      integer(values[0], `${path}.scientific_derivation_ordinals[0]`, 1),
      integer(values[1], `${path}.scientific_derivation_ordinals[1]`, 1),
    ];
  }
  if (derived !== (ordinals !== null)) {
    fail(path, "scientific derivation ordinals consistent with the derived flag");
  }
  const resolutionsInput = record(
    input.confirmed_ambiguity_resolutions,
    `${path}.confirmed_ambiguity_resolutions`,
  );
  const resolutionEntries = Object.entries(resolutionsInput);
  if (resolutionEntries.length > 100) {
    fail(`${path}.confirmed_ambiguity_resolutions`, "at most 100 resolutions");
  }
  const resolutions: Record<string, string> = {};
  for (const [ambiguityId, resolution] of resolutionEntries) {
    if (!ambiguityId || ambiguityId.length > 160) {
      fail(`${path}.confirmed_ambiguity_resolutions`, "1–160 character ambiguity ids");
    }
    const parsedResolution = text(
      resolution,
      `${path}.confirmed_ambiguity_resolutions.${ambiguityId}`,
      4_000,
    );
    if (!parsedResolution.trim()) {
      fail(
        `${path}.confirmed_ambiguity_resolutions.${ambiguityId}`,
        "a nonblank resolution",
      );
    }
    resolutions[ambiguityId] = parsedResolution;
  }
  return {
    attachment_id: uuid(input.attachment_id, `${path}.attachment_id`),
    extraction_id: uuid(input.extraction_id, `${path}.extraction_id`),
    evidence_type: oneOf(
      input.evidence_type,
      ["visual", "document"] as const,
      `${path}.evidence_type`,
    ),
    extraction_status: oneOf(
      input.extraction_status,
      [
        "pending",
        "running",
        "needs_confirmation",
        "succeeded",
        "confirmed",
        "rejected",
        "failed",
      ] as const,
      `${path}.extraction_status`,
    ),
    confidence: bounded(input.confidence, `${path}.confidence`, 0, 1),
    confirmation_state: oneOf(
      input.confirmation_state,
      CONFIRMATION_STATES,
      `${path}.confirmation_state`,
    ),
    admitted_to_diagnosis: bool(input.admitted_to_diagnosis, `${path}.admitted_to_diagnosis`),
    exact_context_characters: integer(
      input.exact_context_characters,
      `${path}.exact_context_characters`,
      0,
      12_000,
    ),
    context_truncated: bool(input.context_truncated, `${path}.context_truncated`),
    scientific_request_derived: derived,
    scientific_derivation_ordinals: ordinals,
    confirmed_ambiguity_resolutions: resolutions,
    confirmation_source: oneOf(
      input.confirmation_source,
      ["pending", "not_required", "attachment_api", "teaching_hitl"] as const,
      `${path}.confirmation_source`,
    ),
  };
}

function parseTool(value: unknown, path: string): Readonly<{ name: string; version: string }> {
  const input = record(value, path);
  return { name: text(input.name, `${path}.name`, 80), version: text(input.version, `${path}.version`, 80) };
}

function parseVisualization(value: unknown, path: string): VisualizationSpec {
  const input = record(value, path);
  const x = array(input.x, `${path}.x`).map((item, index) => finite(item, `${path}.x[${index}]`));
  if (x.length < 2 || x.length > 5_000) fail(`${path}.x`, "2–5000 finite values");
  const series = array(input.series, `${path}.series`).map((item, index) => {
    const seriesInput = record(item, `${path}.series[${index}]`);
    const y = array(seriesInput.y, `${path}.series[${index}].y`).map((point, pointIndex) =>
      finite(point, `${path}.series[${index}].y[${pointIndex}]`),
    );
    if (y.length !== x.length) fail(`${path}.series[${index}].y`, "aligned with x");
    return { label: text(seriesInput.label, `${path}.series[${index}].label`, 80), y };
  });
  if (series.length < 1 || series.length > 8) fail(`${path}.series`, "1–8 series");
  return {
    renderer: parseTool(input.renderer, `${path}.renderer`),
    kind: oneOf(input.kind, ["line"] as const, `${path}.kind`),
    title: text(input.title, `${path}.title`, 160),
    x_label: text(input.x_label, `${path}.x_label`, 80),
    y_label: text(input.y_label, `${path}.y_label`, 80),
    x,
    series,
    rendering_sha256: sha256(input.rendering_sha256, `${path}.rendering_sha256`),
  };
}

function parseScientificResult(value: unknown, path: string): ScientificResult {
  const input = record(value, path);
  const metricsInput = record(input.metrics, `${path}.metrics`);
  const metrics: Record<string, string | number | boolean> = {};
  for (const [key, metric] of Object.entries(metricsInput)) {
    if (typeof metric === "string" || typeof metric === "boolean") metrics[key] = metric;
    else if (typeof metric === "number" && Number.isFinite(metric)) metrics[key] = metric;
    else fail(`${path}.metrics.${key}`, "a finite number, string, or boolean");
  }
  return {
    kind: oneOf(
      input.kind,
      [
        "symbolic_equivalence",
        "symbolic_residual",
        "numerical_normalization",
        "numerical_unitarity",
        "two_level_simulation",
        "rectangular_barrier_tunnelling",
        "line_visualization",
        "code_test",
        "unverified",
      ] as const,
      `${path}.kind`,
    ),
    method: oneOf(input.method, ["symbolic", "numerical", "simulation", "code_test", "unverified"] as const, `${path}.method`),
    status: oneOf(input.status, ["pass", "fail", "inconclusive"] as const, `${path}.status`),
    tool: parseTool(input.tool, `${path}.tool`),
    inputs_sha256: sha256(input.inputs_sha256, `${path}.inputs_sha256`),
    observations: strings(input.observations, `${path}.observations`, 16, 4_000),
    limitations: strings(input.limitations, `${path}.limitations`, 16, 4_000),
    metrics,
    visualization: input.visualization === null ? null : parseVisualization(input.visualization, `${path}.visualization`),
    error_code: input.error_code === null ? null : text(input.error_code, `${path}.error_code`, 64),
  };
}

export function parseTeachingTurnResult(value: unknown): TeachingTurnResult {
  const input = record(value, "turnResult");
  const interpretationInput = record(input.interpretation, "turnResult.interpretation");
  const diagnosisInput = record(input.diagnosis, "turnResult.diagnosis");
  const policyInput = record(input.policy, "turnResult.policy");
  const releaseInput = record(input.release, "turnResult.release");
  const responseInput = record(input.response, "turnResult.response");
  const validationInput = record(input.validation, "turnResult.validation");
  const diagnosisStatus = oneOf(
    diagnosisInput.status,
    ["observed", "model_inference", "insufficient_evidence"] as const,
    "turnResult.diagnosis.status",
  );
  const misconception = nullableText(
    diagnosisInput.likely_misconception,
    "turnResult.diagnosis.likely_misconception",
    500,
  );
  if (misconception && diagnosisStatus !== "model_inference") {
    fail("turnResult.diagnosis", "a labeled model inference when a misconception is proposed");
  }
  const firstErrorInput =
    diagnosisInput.first_error === null
      ? null
      : record(diagnosisInput.first_error, "turnResult.diagnosis.first_error");
  const firstError = firstErrorInput
    ? {
        inferred: bool(firstErrorInput.inferred, "turnResult.diagnosis.first_error.inferred"),
        step_index:
          firstErrorInput.step_index === null
            ? null
            : integer(firstErrorInput.step_index, "turnResult.diagnosis.first_error.step_index", 0, 10_000),
        kind: oneOf(
          firstErrorInput.kind,
          [
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
          ] as const,
          "turnResult.diagnosis.first_error.kind",
        ),
        description: text(
          firstErrorInput.description,
          "turnResult.diagnosis.first_error.description",
          400,
        ),
      }
    : null;
  const misconceptionCandidates = array(
    diagnosisInput.misconception_candidates,
    "turnResult.diagnosis.misconception_candidates",
  ).map((item, index) => {
    const candidate = record(item, `turnResult.diagnosis.misconception_candidates[${index}]`);
    return {
      statement: text(
        candidate.statement,
        `turnResult.diagnosis.misconception_candidates[${index}].statement`,
        400,
      ),
      confidence: bounded(
        candidate.confidence,
        `turnResult.diagnosis.misconception_candidates[${index}].confidence`,
        0,
        1,
      ),
    };
  });
  const evidencePacket = parseEvidencePacket(input.evidence_packet, "turnResult.evidence_packet");
  const evidenceIds = new Set(evidencePacket.evidence.map((item) => item.evidence_id));
  const scientificResults = array(input.scientific_results, "turnResult.scientific_results").map((item, index) =>
    parseScientificResult(item, `turnResult.scientific_results[${index}]`),
  );
  const scientificIds = new Set(
    scientificResults.map((item) => `${item.kind}:${item.inputs_sha256}`),
  );
  const scientificById = new Map<string, ScientificResult>(
    scientificResults.map((item) => [`${item.kind}:${item.inputs_sha256}`, item] as const),
  );
  const rawClaims = array(responseInput.claims, "turnResult.response.claims");
  if (rawClaims.length > 8) fail("turnResult.response.claims", "no more than 8 claims");
  const claims = rawClaims.map((item, index) => {
    const claim = record(item, `turnResult.response.claims[${index}]`);
    const supportBasis = oneOf(
      claim.support_basis,
      [
        "course_material",
        "symbolic_verification",
        "numerical_verification",
        "simulation",
        "code_test",
        "pedagogical_prompt",
        "unverified_model_inference",
      ] as const,
      `turnResult.response.claims[${index}].support_basis`,
    );
    const claimEvidenceIds = strings(claim.evidence_ids, `turnResult.response.claims[${index}].evidence_ids`, 6, 64).map((id, idIndex) =>
      uuid(id, `turnResult.response.claims[${index}].evidence_ids[${idIndex}]`),
    );
    if (claimEvidenceIds.some((id) => !evidenceIds.has(id))) {
      fail(`turnResult.response.claims[${index}].evidence_ids`, "IDs from the evidence packet");
    }
    const resultIds = strings(
      claim.scientific_result_ids,
      `turnResult.response.claims[${index}].scientific_result_ids`,
      4,
      128,
    );
    if (resultIds.some((id) => !scientificIds.has(id))) {
      fail(`turnResult.response.claims[${index}].scientific_result_ids`, "scientific input hashes from this turn");
    }
    const claimText = text(claim.text, `turnResult.response.claims[${index}].text`, 4_000);
    if (supportBasis === "course_material" && claimEvidenceIds.length === 0) {
      fail(`turnResult.response.claims[${index}]`, "course evidence for a course-material claim");
    }
    if (
      supportBasis === "course_material" &&
      !claimEvidenceIds.some((id) =>
        evidencePacket.evidence.some(
          (evidence) => evidence.evidence_id === id && evidence.evidence_snippet.includes(claimText),
        ),
      )
    ) {
      fail(
        `turnResult.response.claims[${index}].text`,
        "a literal span from one cited evidence snippet",
      );
    }
    const expectedMethod: Partial<Record<SupportBasis, ScientificResult["method"]>> = {
      symbolic_verification: "symbolic",
      numerical_verification: "numerical",
      simulation: "simulation",
      code_test: "code_test",
    };
    const method = expectedMethod[supportBasis];
    if (method && (resultIds.length === 0 || resultIds.some((id) => scientificById.get(id)?.method !== method))) {
      fail(
        `turnResult.response.claims[${index}].scientific_result_ids`,
        `results verified by the ${method} method`,
      );
    }
    if (
      supportBasis === "pedagogical_prompt" &&
      (claimEvidenceIds.length > 0 || resultIds.length > 0)
    ) {
      fail(`turnResult.response.claims[${index}]`, "a pedagogical prompt without authority references");
    }
    return {
      text: claimText,
      support_basis: supportBasis,
      evidence_ids: claimEvidenceIds,
      scientific_result_ids: resultIds,
    };
  });
  const trace = array(input.trace, "turnResult.trace").map((item, index) => {
    const step = record(item, `turnResult.trace[${index}]`);
    const name = oneOf(step.name, WORKFLOW_ORDER, `turnResult.trace[${index}].name`);
    if (name !== WORKFLOW_ORDER[index]) fail(`turnResult.trace[${index}].name`, WORKFLOW_ORDER[index] ?? "absent");
    return {
      name,
      status: oneOf(step.status, ["completed", "degraded", "skipped", "failed"] as const, `turnResult.trace[${index}].status`),
      detail: text(step.detail, `turnResult.trace[${index}].detail`, 500),
    };
  });
  if (trace.length !== WORKFLOW_ORDER.length) fail("turnResult.trace", "the fixed ten-step workflow");
  const validation = {
    passed: bool(validationInput.passed, "turnResult.validation.passed"),
    citation_ids_valid: bool(validationInput.citation_ids_valid, "turnResult.validation.citation_ids_valid"),
    literal_course_claims_valid: bool(validationInput.literal_course_claims_valid, "turnResult.validation.literal_course_claims_valid"),
    scientific_references_valid: bool(validationInput.scientific_references_valid, "turnResult.validation.scientific_references_valid"),
    warnings: strings(validationInput.warnings, "turnResult.validation.warnings", 12, 2_000),
  };
  if (
    !validation.passed ||
    !validation.citation_ids_valid ||
    !validation.literal_course_claims_valid ||
    !validation.scientific_references_valid
  ) {
    fail("turnResult.validation", "a passed citation and scientific validation report");
  }
  return {
    conversation_id: uuid(input.conversation_id, "turnResult.conversation_id"),
    turn_id: uuid(input.turn_id, "turnResult.turn_id"),
    workflow_version: text(input.workflow_version, "turnResult.workflow_version", 160),
    interpretation: {
      task_kind: oneOf(
        interpretationInput.task_kind,
        ["concept_question", "derivation_check", "exercise_help", "experiment_help", "project_help"] as const,
        "turnResult.interpretation.task_kind",
      ),
      relevant_concepts: strings(interpretationInput.relevant_concepts, "turnResult.interpretation.relevant_concepts", 5, 160),
      needs_scientific_verification: bool(interpretationInput.needs_scientific_verification, "turnResult.interpretation.needs_scientific_verification"),
      confidence: bounded(interpretationInput.confidence, "turnResult.interpretation.confidence", 0, 1),
    },
    diagnosis: {
      status: diagnosisStatus,
      summary: text(diagnosisInput.summary, "turnResult.diagnosis.summary", 800),
      likely_misconception: misconception,
      observation_basis: array(diagnosisInput.observation_basis, "turnResult.diagnosis.observation_basis").map((item, index) =>
        oneOf(item, ["student_message", "student_attempt", "course_evidence"] as const, `turnResult.diagnosis.observation_basis[${index}]`),
      ),
      target_concepts: strings(
        diagnosisInput.target_concepts,
        "turnResult.diagnosis.target_concepts",
        6,
        160,
      ),
      first_error: firstError,
      misconception_candidates: misconceptionCandidates,
      missing_prerequisites: strings(
        diagnosisInput.missing_prerequisites,
        "turnResult.diagnosis.missing_prerequisites",
        6,
        160,
      ),
      progress_state: oneOf(
        diagnosisInput.progress_state,
        ["no_attempt", "started", "struggling", "progressing", "confident"] as const,
        "turnResult.diagnosis.progress_state",
      ),
      confidence: bounded(
        diagnosisInput.confidence,
        "turnResult.diagnosis.confidence",
        0,
        1,
      ),
      verification_needed: bool(
        diagnosisInput.verification_needed,
        "turnResult.diagnosis.verification_needed",
      ),
      reason: text(diagnosisInput.reason, "turnResult.diagnosis.reason", 800),
    },
    policy: {
      policy_id: nullableUuid(policyInput.policy_id, "turnResult.policy.policy_id"),
      source: oneOf(policyInput.source, ["teacher_configured", "safe_default"] as const, "turnResult.policy.source"),
      mode: oneOf(policyInput.mode, TEACHING_MODES, "turnResult.policy.mode"),
      allow_full_solution: bool(policyInput.allow_full_solution, "turnResult.policy.allow_full_solution"),
      minimum_attempts_for_scaffold: integer(policyInput.minimum_attempts_for_scaffold, "turnResult.policy.minimum_attempts_for_scaffold"),
      minimum_attempts_for_full_solution: integer(policyInput.minimum_attempts_for_full_solution, "turnResult.policy.minimum_attempts_for_full_solution"),
      max_hint_level: integer(policyInput.max_hint_level, "turnResult.policy.max_hint_level", 0, 10),
    },
    release: {
      action: oneOf(
        releaseInput.action,
        ["explain_then_check", "ask_diagnostic_question", "give_progressive_hint", "check_derivation_step", "predict_then_simulate", "coach_project_milestone"] as const,
        "turnResult.release.action",
      ),
      release_level: oneOf(releaseInput.release_level, ["question_only", "hint", "scaffold", "full_explanation", "full_solution"] as const, "turnResult.release.release_level"),
      attempts_observed: integer(releaseInput.attempts_observed, "turnResult.release.attempts_observed"),
      reason_code: text(releaseInput.reason_code, "turnResult.release.reason_code", 120),
    },
    evidence_packet: evidencePacket,
    response: {
      orientation: text(responseInput.orientation, "turnResult.response.orientation", 1_200),
      claims,
      next_question: text(responseInput.next_question, "turnResult.response.next_question", 1_000),
      status: oneOf(responseInput.status, ["grounded", "mixed", "model_degraded", "insufficient_course_evidence"] as const, "turnResult.response.status"),
      limitations: strings(responseInput.limitations, "turnResult.response.limitations", 8, 4_000),
    },
    validation,
    scientific_results: scientificResults,
    code_artifact: parseCodeArtifactRun(input.code_artifact),
    trace,
    learning_native:
      input.learning_native === undefined || input.learning_native === null
        ? null
        : parseLearningNativeTurnState(input.learning_native, "turnResult.learning_native"),
  };
}

function parseCodeArtifactRun(value: unknown): CodeArtifactRun | null {
  if (value === undefined || value === null) return null;
  // Fail-closed: a malformed artifact is dropped rather than failing the
  // whole turn, so a Coding Agent hiccup can never break the Golden Loop.
  try {
    const input = record(value, "turnResult.code_artifact");
    const artifact = record(input.artifact, "turnResult.code_artifact.artifact");
    const execution = record(input.execution, "turnResult.code_artifact.execution");
    const verification = record(input.verification, "turnResult.code_artifact.verification");
    const repairs = Array.isArray(input.repairs) ? input.repairs : [];
    return {
      artifact: {
        language: oneOf(artifact.language, ["python"] as const, "turnResult.code_artifact.artifact.language"),
        purpose: text(artifact.purpose, "turnResult.code_artifact.artifact.purpose", 600),
        code: text(artifact.code, "turnResult.code_artifact.artifact.code", 20_000),
        expected_outputs: strings(artifact.expected_outputs, "turnResult.code_artifact.artifact.expected_outputs", 8, 200),
        verification_plan: text(artifact.verification_plan, "turnResult.code_artifact.artifact.verification_plan", 600),
      },
      execution: {
        completed: bool(execution.completed, "turnResult.code_artifact.execution.completed"),
        exit_code: execution.exit_code === null || execution.exit_code === undefined ? null : Number(execution.exit_code),
        timed_out: bool(execution.timed_out, "turnResult.code_artifact.execution.timed_out"),
        truncated: bool(execution.truncated, "turnResult.code_artifact.execution.truncated"),
        stdout_bounded: boundedTextAllowEmpty(execution.stdout_bounded, "turnResult.code_artifact.execution.stdout_bounded", 8_000),
        stderr_bounded: boundedTextAllowEmpty(execution.stderr_bounded, "turnResult.code_artifact.execution.stderr_bounded", 4_000),
        duration_seconds: bounded(Number(execution.duration_seconds ?? 0), "turnResult.code_artifact.execution.duration_seconds", 0, 600),
      },
      verification: {
        status: oneOf(verification.status, ["pass", "fail", "inconclusive", "no_oracle"] as const, "turnResult.code_artifact.verification.status"),
        oracle_kind: verification.oracle_kind === null || verification.oracle_kind === undefined ? null : text(verification.oracle_kind, "turnResult.code_artifact.verification.oracle_kind", 80),
        agent_metrics: recordMetrics(verification.agent_metrics, "turnResult.code_artifact.verification.agent_metrics"),
        oracle_metrics: recordMetrics(verification.oracle_metrics, "turnResult.code_artifact.verification.oracle_metrics"),
        observations: strings(verification.observations, "turnResult.code_artifact.verification.observations", 12, 1_000),
        tolerance: bounded(Number(verification.tolerance ?? 1e-6), "turnResult.code_artifact.verification.tolerance", 0, 1),
      },
      repairs: repairs.map((repair, index) => {
        const r = record(repair, `turnResult.code_artifact.repairs[${index}]`);
        return {
          attempt_number: integer(r.attempt_number, `turnResult.code_artifact.repairs[${index}].attempt_number`),
          failure_summary: text(r.failure_summary, `turnResult.code_artifact.repairs[${index}].failure_summary`, 1_000),
          stderr_excerpt: text(r.stderr_excerpt, `turnResult.code_artifact.repairs[${index}].stderr_excerpt`, 1_000),
        };
      }),
      progress: oneOf(input.progress, ["planning", "writing", "running", "verifying", "result"] as const, "turnResult.code_artifact.progress"),
      figure_png_base64:
        input.figure_png_base64 === null || input.figure_png_base64 === undefined
          ? null
          : text(input.figure_png_base64, "turnResult.code_artifact.figure_png_base64", 200_000),
    };
  } catch {
    return null;
  }
}

function recordMetrics(value: unknown, path: string): Readonly<Record<string, string | number | boolean>> {
  const input = record(value, path);
  const out: Record<string, string | number | boolean> = {};
  for (const [key, val] of Object.entries(input)) {
    if (typeof val === "string" || typeof val === "number" || typeof val === "boolean") {
      out[key] = val;
    }
  }
  return out;
}

function parseLearningNativeTurnState(value: unknown, path: string): LearningNativeTurnState {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "commitment",
      "learning_action",
      "teach_back",
      "transfer",
      "solo",
      "cognitive_mirror",
      "evidence_persisted",
    ],
    path,
  );
  return {
    commitment:
      input.commitment === undefined || input.commitment === null
        ? null
        : parseCognitiveCommitment(input.commitment, `${path}.commitment`),
    learning_action:
      input.learning_action === undefined || input.learning_action === null
        ? null
        : oneOf(
            input.learning_action,
            [
              "ask_commitment",
              "ask_prediction",
              "ask_self_explanation",
              "give_cue",
              "give_hint",
              "show_counterexample",
              "start_simulation",
              "start_teach_back",
              "start_transfer",
              "enter_solo",
              "show_worked_example",
            ] as const,
            `${path}.learning_action`,
          ),
    teach_back:
      input.teach_back === undefined || input.teach_back === null
        ? null
        : parseTeachBackAnalysis(input.teach_back, `${path}.teach_back`),
    transfer:
      input.transfer === undefined || input.transfer === null
        ? null
        : parseTransferTask(input.transfer, `${path}.transfer`),
    solo:
      input.solo === undefined || input.solo === null
        ? null
        : parseSoloMode(input.solo, `${path}.solo`),
    cognitive_mirror:
      input.cognitive_mirror === undefined || input.cognitive_mirror === null
        ? null
        : parseCognitiveMirror(input.cognitive_mirror, `${path}.cognitive_mirror`),
    evidence_persisted: strings(input.evidence_persisted, `${path}.evidence_persisted`, 24, 64),
  };
}

function parseTeachBackAnalysis(value: unknown, path: string): TeachBackAnalysis {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "covered_relations",
      "missing_relations",
      "contradictions",
      "unsupported_claims",
      "recommended_probe",
      "verified",
      "is_model_inference",
    ],
    path,
  );
  return {
    covered_relations: array(input.covered_relations, `${path}.covered_relations`).map((item, index) =>
      parseTeachBackFinding(item, `${path}.covered_relations[${index}]`),
    ),
    missing_relations: array(input.missing_relations, `${path}.missing_relations`).map((item, index) =>
      parseTeachBackFinding(item, `${path}.missing_relations[${index}]`),
    ),
    contradictions: array(input.contradictions, `${path}.contradictions`).map((item, index) =>
      parseTeachBackFinding(item, `${path}.contradictions[${index}]`),
    ),
    unsupported_claims: array(input.unsupported_claims, `${path}.unsupported_claims`).map((item, index) =>
      parseTeachBackFinding(item, `${path}.unsupported_claims[${index}]`),
    ),
    recommended_probe: boundedText(input.recommended_probe, `${path}.recommended_probe`, 800),
    verified: bool(input.verified, `${path}.verified`),
    is_model_inference: bool(input.is_model_inference, `${path}.is_model_inference`),
  };
}

function parseTeachBackFinding(value: unknown, path: string): TeachBackFinding {
  const input = record(value, path);
  exactKeys(input, ["relation", "description", "target_concept_id"], path);
  return {
    relation: oneOf(
      input.relation,
      ["covered", "missing", "contradictory", "unsupported"] as const,
      `${path}.relation`,
    ),
    description: text(input.description, `${path}.description`, 500),
    target_concept_id:
      input.target_concept_id === undefined || input.target_concept_id === null
        ? null
        : uuid(input.target_concept_id, `${path}.target_concept_id`),
  };
}

function parseTransferTask(value: unknown, path: string): TransferTask {
  const input = record(value, path);
  exactKeys(
    input,
    ["transfer_type", "prompt", "source_concept_ids", "key_parameters", "expected_observable", "verifiable"],
    path,
  );
  return {
    transfer_type: oneOf(
      input.transfer_type,
      ["near", "parameter", "representation", "conceptual", "far", "delayed_retrieval"] as const,
      `${path}.transfer_type`,
    ),
    prompt: text(input.prompt, `${path}.prompt`, 2000),
    source_concept_ids: array(input.source_concept_ids, `${path}.source_concept_ids`).map((item, index) =>
      uuid(item, `${path}.source_concept_ids[${index}]`),
    ),
    key_parameters: strings(input.key_parameters, `${path}.key_parameters`, 8, 200),
    expected_observable: boundedText(input.expected_observable, `${path}.expected_observable`, 400),
    verifiable: bool(input.verifiable, `${path}.verifiable`),
  };
}

function parseSoloMode(value: unknown, path: string): SoloMode {
  const input = record(value, path);
  exactKeys(
    input,
    ["status", "active_transfer", "started_at", "assistance_locked", "unlock_reason"],
    path,
  );
  return {
    status: oneOf(input.status, ["inactive", "active", "exited"] as const, `${path}.status`),
    active_transfer:
      input.active_transfer === undefined || input.active_transfer === null
        ? null
        : parseTransferTask(input.active_transfer, `${path}.active_transfer`),
    started_at:
      input.started_at === undefined || input.started_at === null
        ? null
        : boundedText(input.started_at, `${path}.started_at`, 100),
    assistance_locked: bool(input.assistance_locked, `${path}.assistance_locked`),
    unlock_reason: boundedText(input.unlock_reason, `${path}.unlock_reason`, 400),
  };
}

function parseCognitiveMirror(value: unknown, path: string): CognitiveMirror {
  const input = record(value, path);
  exactKeys(input, ["current_concept_id", "concept_states", "summary", "no_personality_profile"], path);
  return {
    current_concept_id:
      input.current_concept_id === undefined || input.current_concept_id === null
        ? null
        : uuid(input.current_concept_id, `${path}.current_concept_id`),
    concept_states: array(input.concept_states, `${path}.concept_states`).map((item, index) =>
      parseConceptMirrorState(item, `${path}.concept_states[${index}]`),
    ),
    summary: boundedText(input.summary, `${path}.summary`, 1200),
    no_personality_profile: bool(input.no_personality_profile, `${path}.no_personality_profile`),
  };
}

function parseConceptMirrorState(value: unknown, path: string): ConceptMirrorState {
  const input = record(value, path);
  exactKeys(
    input,
    [
      "concept_candidate_id",
      "label",
      "evidence_summary",
      "confidence_history",
      "calibration_gap",
      "unaided_retrieval",
      "transfer_evidence",
      "hint_dependency",
      "misconception_candidates",
      "last_demonstrated_at",
    ],
    path,
  );
  const confidenceHistory = array(input.confidence_history, `${path}.confidence_history`).map(
    (item, index) => {
      const pair = array(item, `${path}.confidence_history[${index}]`);
      if (pair.length !== 2) fail(`${path}.confidence_history[${index}]`, "a [number, boolean] pair");
      return [bounded(pair[0], `${path}.confidence_history[${index}][0]`, 0, 1), bool(pair[1], `${path}.confidence_history[${index}][1]`)] as const;
    },
  );
  return {
    concept_candidate_id: uuid(input.concept_candidate_id, `${path}.concept_candidate_id`),
    label: oneOf(
      input.label,
      [
        "unknown",
        "exposed",
        "developing",
        "demonstrated",
        "transfer_ready",
        "fragile",
        "needs_review",
      ] as const,
      `${path}.label`,
    ),
    evidence_summary: strings(input.evidence_summary, `${path}.evidence_summary`, 10, 400),
    confidence_history: confidenceHistory,
    calibration_gap:
      input.calibration_gap === undefined || input.calibration_gap === null
        ? null
        : bounded(input.calibration_gap, `${path}.calibration_gap`, -1, 1),
    unaided_retrieval:
      input.unaided_retrieval === undefined || input.unaided_retrieval === null
        ? null
        : bool(input.unaided_retrieval, `${path}.unaided_retrieval`),
    transfer_evidence: strings(input.transfer_evidence, `${path}.transfer_evidence`, 6, 400),
    hint_dependency: strings(input.hint_dependency, `${path}.hint_dependency`, 6, 400),
    misconception_candidates: strings(
      input.misconception_candidates,
      `${path}.misconception_candidates`,
      6,
      400,
    ),
    last_demonstrated_at:
      input.last_demonstrated_at === undefined || input.last_demonstrated_at === null
        ? null
        : boundedText(input.last_demonstrated_at, `${path}.last_demonstrated_at`, 100),
  };
}

const STAFF_HITL_ACTIONS = ["approve", "reject", "edit", "take_over"] as const;

export function parseHitlInterruptResponse(value: unknown): HitlInterruptResponse {
  const input = record(value, "hitlResponse");
  exactKeys(input, ["status", "conversation_id", "turn_id", "interrupt", "artifacts"], "hitlResponse");
  const conversationId = uuid(input.conversation_id, "hitlResponse.conversation_id");
  const turnId = uuid(input.turn_id, "hitlResponse.turn_id");
  const interruptInput = record(input.interrupt, "hitlResponse.interrupt");
  exactKeys(
    interruptInput,
    [
      "schema_version",
      "interrupt_id",
      "thread_id",
      "conversation_id",
      "turn_id",
      "stage",
      "reasons",
      "prompt",
      "student_allowed_actions",
      "staff_allowed_actions",
    ],
    "hitlResponse.interrupt",
  );
  const reasons = array(interruptInput.reasons, "hitlResponse.interrupt.reasons").map(
    (item, index) => oneOf(item, HITL_REASONS, `hitlResponse.interrupt.reasons[${index}]`),
  );
  if (reasons.length < 1 || reasons.length > HITL_REASONS.length || new Set(reasons).size !== reasons.length) {
    fail("hitlResponse.interrupt.reasons", "1–9 unique deterministic reasons");
  }
  const studentActions = array(
    interruptInput.student_allowed_actions,
    "hitlResponse.interrupt.student_allowed_actions",
  ).map((item, index) =>
    oneOf(
      item,
      ["confirm_transcription"] as const,
      `hitlResponse.interrupt.student_allowed_actions[${index}]`,
    ),
  );
  const shouldAllowConfirmation =
    reasons.length === 1 && reasons[0] === "ambiguous_transcription";
  if (
    (shouldAllowConfirmation && !sameJson(studentActions, ["confirm_transcription"])) ||
    (!shouldAllowConfirmation && studentActions.length !== 0)
  ) {
    fail(
      "hitlResponse.interrupt.student_allowed_actions",
      "confirmation only for a sole ambiguous-transcription reason",
    );
  }
  const staffActions = array(
    interruptInput.staff_allowed_actions,
    "hitlResponse.interrupt.staff_allowed_actions",
  ).map((item, index) =>
    oneOf(item, STAFF_HITL_ACTIONS, `hitlResponse.interrupt.staff_allowed_actions[${index}]`),
  );
  if (!sameJson(staffActions, STAFF_HITL_ACTIONS)) {
    fail("hitlResponse.interrupt.staff_allowed_actions", "the fixed staff action envelope");
  }
  const interrupt = {
    schema_version: oneOf(
      interruptInput.schema_version,
      ["quantum-agent-hitl/1.0.0"] as const,
      "hitlResponse.interrupt.schema_version",
    ),
    interrupt_id: uuid(interruptInput.interrupt_id, "hitlResponse.interrupt.interrupt_id"),
    thread_id: uuid(interruptInput.thread_id, "hitlResponse.interrupt.thread_id"),
    conversation_id: uuid(
      interruptInput.conversation_id,
      "hitlResponse.interrupt.conversation_id",
    ),
    turn_id: uuid(interruptInput.turn_id, "hitlResponse.interrupt.turn_id"),
    stage: oneOf(
      interruptInput.stage,
      ["pre_release_review"] as const,
      "hitlResponse.interrupt.stage",
    ),
    reasons,
    prompt: text(interruptInput.prompt, "hitlResponse.interrupt.prompt", 1_200),
    student_allowed_actions: studentActions,
    staff_allowed_actions: staffActions,
  };
  if (
    interrupt.thread_id !== conversationId ||
    interrupt.conversation_id !== conversationId ||
    interrupt.turn_id !== turnId
  ) {
    fail("hitlResponse.interrupt", "identifiers matching the paused turn and thread");
  }

  const artifactsInput = record(input.artifacts, "hitlResponse.artifacts");
  exactKeys(
    artifactsInput,
    [
      "interpretation",
      "evidence_packet",
      "evidence_bundle",
      "diagnosis",
      "policy",
      "release",
      "scientific_results",
      "proposed_response",
      "validation",
      "trace",
      "multimodal_evidence",
      "perception_trace",
    ],
    "hitlResponse.artifacts",
  );
  const validated = parseTeachingTurnResult({
    conversation_id: conversationId,
    turn_id: turnId,
    workflow_version: "hitl-proposed/1.0.0",
    interpretation: artifactsInput.interpretation,
    diagnosis: artifactsInput.diagnosis,
    policy: artifactsInput.policy,
    release: artifactsInput.release,
    evidence_packet: artifactsInput.evidence_packet,
    response: artifactsInput.proposed_response,
    validation: artifactsInput.validation,
    scientific_results: artifactsInput.scientific_results,
    trace: artifactsInput.trace,
  });
  const evidenceBundle =
    artifactsInput.evidence_bundle === null
      ? null
      : parseEvidenceBundle(
          artifactsInput.evidence_bundle,
          "hitlResponse.artifacts.evidence_bundle",
          validated.evidence_packet,
        );
  const multimodalEvidence = array(
    artifactsInput.multimodal_evidence,
    "hitlResponse.artifacts.multimodal_evidence",
  );
  if (multimodalEvidence.length > 8) {
    fail("hitlResponse.artifacts.multimodal_evidence", "at most eight attachment records");
  }
  const parsedMultimodalEvidence = multimodalEvidence.map((item, index) =>
    parseHitlMultimodalEvidence(
      item,
      `hitlResponse.artifacts.multimodal_evidence[${index}]`,
    ),
  );
  const perceptionTrace = array(
    artifactsInput.perception_trace,
    "hitlResponse.artifacts.perception_trace",
  );
  if (perceptionTrace.length > 8) {
    fail("hitlResponse.artifacts.perception_trace", "at most eight trace records");
  }
  const parsedPerceptionTrace = perceptionTrace.map((item, index) =>
    parsePerceptionTrace(item, `hitlResponse.artifacts.perception_trace[${index}]`),
  );
  const evidenceAttachmentIds = new Set(
    parsedMultimodalEvidence.map((item) => item.attachment_id),
  );
  if (
    parsedPerceptionTrace.some((item) => !evidenceAttachmentIds.has(item.attachment_id))
  ) {
    fail(
      "hitlResponse.artifacts.perception_trace",
      "entries backed by the preserved multimodal evidence",
    );
  }
  return {
    status: oneOf(input.status, ["interrupted"] as const, "hitlResponse.status"),
    conversation_id: conversationId,
    turn_id: turnId,
    interrupt,
    artifacts: {
      interpretation: validated.interpretation,
      evidence_packet: validated.evidence_packet,
      evidence_bundle: evidenceBundle,
      diagnosis: validated.diagnosis,
      policy: validated.policy,
      release: validated.release,
      scientific_results: validated.scientific_results,
      proposed_response: validated.response,
      validation: validated.validation,
      trace: validated.trace,
      multimodal_evidence: parsedMultimodalEvidence,
      perception_trace: parsedPerceptionTrace,
    },
  };
}

export function parseTeachingWorkflowOutcome(value: unknown): TeachingWorkflowOutcome {
  if (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>).status === "interrupted"
  ) {
    return parseHitlInterruptResponse(value);
  }
  return parseTeachingTurnResult(value);
}

export function redactHitlProposedResponse(
  response: HitlInterruptResponse,
): HitlInterruptResponse {
  return {
    ...response,
    artifacts: {
      ...response.artifacts,
      proposed_response: {
        orientation: "拟议回答已隐藏，等待当前人工复核完成。",
        claims: [],
        next_question: "请完成当前允许的确认操作，或等待助教与教师复核。",
        status:
          response.artifacts.evidence_packet.coverage === "not_found"
            ? "insufficient_course_evidence"
            : "mixed",
        limitations: ["学生端不会接收人工复核前的拟议回答。"],
      },
    },
  };
}

export function parseStudentHitlResumeRequest(value: unknown): StudentHitlResumeRequest {
  const input = record(value, "hitlResumeRequest");
  exactKeys(
    input,
    ["interrupt_id", "mode", "action", "confirmed_student_attempt"],
    "hitlResumeRequest",
  );
  const confirmedAttempt = text(
    input.confirmed_student_attempt,
    "hitlResumeRequest.confirmed_student_attempt",
    12_000,
  ).trim();
  if (!confirmedAttempt) {
    fail("hitlResumeRequest.confirmed_student_attempt", "non-blank confirmed text");
  }
  return {
    interrupt_id: uuid(input.interrupt_id, "hitlResumeRequest.interrupt_id"),
    mode: oneOf(input.mode, TEACHING_MODES, "hitlResumeRequest.mode"),
    action: oneOf(
      input.action,
      ["confirm_transcription"] as const,
      "hitlResumeRequest.action",
    ),
    confirmed_student_attempt: confirmedAttempt,
  };
}

export function assertTeachingScope(
  result: TeachingTurnResult,
  scope: TeachingScope,
  requestedMode: TeachingMode,
): void {
  if (
    result.evidence_packet.course_id !== scope.courseId ||
    result.evidence_packet.curriculum_edition_id !== scope.curriculumEditionId
  ) {
    throw new TeachingContractError("teaching result crossed the requested course boundary");
  }
  if (result.policy.mode !== requestedMode) {
    throw new TeachingContractError("teaching result mode does not match the request");
  }
  for (const [index, evidence] of result.evidence_packet.evidence.entries()) {
    if (
      evidence.curriculum_edition_id !== null &&
      evidence.curriculum_edition_id !== scope.curriculumEditionId
    ) {
      throw new TeachingContractError(`evidence[${index}] crossed the requested curriculum edition`);
    }
  }
}

export function assertHitlScope(
  response: HitlInterruptResponse,
  scope: TeachingScope,
  requestedMode: TeachingMode,
): void {
  if (
    response.artifacts.evidence_packet.course_id !== scope.courseId ||
    response.artifacts.evidence_packet.curriculum_edition_id !== scope.curriculumEditionId ||
    response.artifacts.policy.mode !== requestedMode
  ) {
    throw new TeachingContractError("HITL state crossed the requested course, edition, or mode");
  }
  if (
    response.artifacts.evidence_bundle &&
    (response.artifacts.evidence_bundle.course_id !== scope.courseId ||
      response.artifacts.evidence_bundle.curriculum_edition_id !== scope.curriculumEditionId)
  ) {
    throw new TeachingContractError("EvidenceBundle crossed the requested course boundary");
  }
  for (const [index, evidence] of response.artifacts.evidence_packet.evidence.entries()) {
    if (
      evidence.curriculum_edition_id !== null &&
      evidence.curriculum_edition_id !== scope.curriculumEditionId
    ) {
      throw new TeachingContractError(
        `HITL evidence[${index}] crossed the requested curriculum edition`,
      );
    }
  }
}

export function isTeachingMode(value: string): value is TeachingMode {
  return (TEACHING_MODES as readonly string[]).includes(value);
}

export function isValidTeachingScope(scope: TeachingScope): boolean {
  return UUID_PATTERN.test(scope.courseId) && UUID_PATTERN.test(scope.curriculumEditionId);
}

export function parseTeachingApiError(value: unknown): TeachingApiError | null {
  try {
    const envelope = record(value, "apiError");
    const error = record(envelope.error, "apiError.error");
    const traceId = error.trace_id;
    return {
      error: {
        code: text(error.code, "apiError.error.code", 160),
        message: text(error.message, "apiError.error.message", 1_000),
        ...(typeof traceId === "string" && traceId.length > 0 && traceId.length <= 128
          ? { trace_id: traceId }
          : {}),
      },
    };
  } catch {
    return null;
  }
}
