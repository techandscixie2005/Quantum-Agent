"""Validated contracts for the deterministic teaching workflow."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantum_agent.db_models import (
    AnswerReleaseLevel,
    TeachingAction,
    TeachingMode,
    TeachingTaskKind,
)
from quantum_agent.knowledge.evidence_packets import EvidencePacket
from quantum_agent.science import ScientificVerificationRequest, ScientificVerificationResult


class WorkflowStepName(StrEnum):
    CLASSIFY_TASK = "classify_task"
    IDENTIFY_CONCEPTS = "identify_concepts"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    DIAGNOSE_PROGRESS = "diagnose_progress"
    CHOOSE_TEACHING_ACTION = "choose_teaching_action"
    APPLY_ANSWER_POLICY = "apply_answer_policy"
    RUN_SCIENTIFIC_TOOLS = "run_scientific_tools"
    GENERATE_RESPONSE = "generate_response"
    VALIDATE_RESPONSE = "validate_response"
    RECORD_LEARNING_EVIDENCE = "record_learning_evidence"


WORKFLOW_ORDER: tuple[WorkflowStepName, ...] = tuple(WorkflowStepName)


class WorkflowStepStatus(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    FAILED = "failed"


class SupportBasis(StrEnum):
    COURSE_MATERIAL = "course_material"
    SYMBOLIC_VERIFICATION = "symbolic_verification"
    NUMERICAL_VERIFICATION = "numerical_verification"
    SIMULATION = "simulation"
    CODE_TEST = "code_test"
    PEDAGOGICAL_PROMPT = "pedagogical_prompt"
    UNVERIFIED_MODEL_INFERENCE = "unverified_model_inference"


class DiagnosisStatus(StrEnum):
    OBSERVED = "observed"
    MODEL_INFERENCE = "model_inference"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ResponseStatus(StrEnum):
    GROUNDED = "grounded"
    MIXED = "mixed"
    MODEL_DEGRADED = "model_degraded"
    INSUFFICIENT_COURSE_EVIDENCE = "insufficient_course_evidence"


class InterpretationOutput(BaseModel):
    """LLM-assisted interpretation; downstream policy constrains its effect."""

    model_config = ConfigDict(extra="forbid")

    task_kind: TeachingTaskKind
    relevant_concepts: list[str] = Field(default_factory=list, max_length=5)
    needs_scientific_verification: bool = False
    confidence: float = Field(ge=0, le=1)

    @field_validator("relevant_concepts")
    @classmethod
    def normalize_concepts(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            clean = " ".join(item.strip().split())
            if clean and clean not in normalized:
                normalized.append(clean[:160])
        return normalized


class DiagnosisProgressState(StrEnum):
    """Progress is a coarse, low-inference label, not a mastery verdict."""

    NO_ATTEMPT = "no_attempt"
    STARTED = "started"
    STRUGGLING = "struggling"
    PROGRESSING = "progressing"
    CONFIDENT = "confident"


class DiagnosisErrorKind(StrEnum):
    ALGEBRA_ERROR = "algebra_error"
    ASSUMPTION_ERROR = "assumption_error"
    BOUNDARY_CONDITION_ERROR = "boundary_condition_error"
    NORMALIZATION_ERROR = "normalization_error"
    BASIS_CONFUSION = "basis_confusion"
    OPERATOR_ERROR = "operator_error"
    DEGENERACY_ERROR = "degeneracy_error"
    DIMENSION_ERROR = "dimension_error"
    NUMERICAL_ERROR = "numerical_error"
    PHYSICAL_INTERPRETATION_ERROR = "physical_interpretation_error"
    NO_CLEAR_ERROR = "no_clear_error"
    INCONCLUSIVE = "inconclusive"


class StudentSnapshot(BaseModel):
    """Minimal, observation-only context supplied to the Diagnosis Agent.

    The snapshot deliberately excludes mastery scores, free-text memory, and
    personality-style inferences.  It carries only bounded counts that the
    deterministic application can derive from persisted teaching turns.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prior_attempt_count: int = Field(default=0, ge=0, le=1000)
    recent_no_progress_count: int = Field(default=0, ge=0, le=20)


class MisconceptionCandidate(BaseModel):
    """A named candidate misconception plus the evidence that suggests it."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0, le=1)


class FirstErrorLocalization(BaseModel):
    """A candidate first consequential error, never asserted without basis."""

    model_config = ConfigDict(extra="forbid")

    inferred: bool = True
    step_index: int | None = None
    kind: DiagnosisErrorKind = DiagnosisErrorKind.NO_CLEAR_ERROR
    description: str = Field(default="", max_length=400)


class DiagnosisOutput(BaseModel):
    """A light-weight diagnosis, explicitly not a scientific or mastery fact."""

    model_config = ConfigDict(extra="forbid")

    status: DiagnosisStatus
    summary: str = Field(min_length=1, max_length=800)
    likely_misconception: str | None = Field(default=None, max_length=500)
    observation_basis: list[Literal["student_message", "student_attempt", "course_evidence"]] = (
        Field(default_factory=list, max_length=3)
    )
    # Structured V2.1 fields (PRD §9.2). All optional-with-defaults so the B0/B1
    # baseline and older call sites continue to construct a minimal diagnosis.
    target_concepts: list[str] = Field(default_factory=list, max_length=6)
    first_error: FirstErrorLocalization | None = None
    misconception_candidates: list[MisconceptionCandidate] = Field(
        default_factory=list, max_length=4
    )
    missing_prerequisites: list[str] = Field(default_factory=list, max_length=6)
    progress_state: DiagnosisProgressState = DiagnosisProgressState.NO_ATTEMPT
    confidence: float = Field(default=0.0, ge=0, le=1)
    verification_needed: bool = False
    reason: str = Field(
        default="Baseline diagnosis without specialist-agent enrichment.",
        min_length=1,
        max_length=800,
    )

    @field_validator("reason")
    @classmethod
    def reason_is_auditable_summary(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("diagnosis reason must not be blank")
        return normalized

    @model_validator(mode="after")
    def inference_is_labeled(self) -> DiagnosisOutput:
        if self.likely_misconception and self.status is not DiagnosisStatus.MODEL_INFERENCE:
            raise ValueError("a likely misconception must be labeled model_inference")
        return self

    @model_validator(mode="after")
    def misconception_candidates_are_labeled(self) -> DiagnosisOutput:
        if self.misconception_candidates and self.status is not DiagnosisStatus.MODEL_INFERENCE:
            raise ValueError("misconception candidates must be labeled model_inference")
        return self

    @model_validator(mode="after")
    def first_error_requires_attempt(self) -> DiagnosisOutput:
        if self.first_error is not None and "student_attempt" not in self.observation_basis:
            raise ValueError("a first-error localization requires a student attempt")
        return self


class TeachingClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    support_basis: SupportBasis
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=6)
    scientific_result_ids: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def references_match_basis(self) -> TeachingClaim:
        if self.support_basis is SupportBasis.COURSE_MATERIAL and not self.evidence_ids:
            raise ValueError("course-material claims require evidence ids")
        scientific = {
            SupportBasis.SYMBOLIC_VERIFICATION,
            SupportBasis.NUMERICAL_VERIFICATION,
            SupportBasis.SIMULATION,
            SupportBasis.CODE_TEST,
        }
        if self.support_basis in scientific and not self.scientific_result_ids:
            raise ValueError("scientific claims require tool-result ids")
        if self.support_basis is SupportBasis.PEDAGOGICAL_PROMPT and (
            self.evidence_ids or self.scientific_result_ids
        ):
            raise ValueError("pedagogical prompts do not carry scientific citations")
        return self


class DraftTeachingResponse(BaseModel):
    """Model-facing response schema; it is revalidated against authority."""

    model_config = ConfigDict(extra="forbid")

    orientation: str = Field(min_length=1, max_length=1200)
    claims: list[TeachingClaim] = Field(default_factory=list, max_length=8)
    next_question: str = Field(min_length=1, max_length=1000)


class TeachingResponse(DraftTeachingResponse):
    status: ResponseStatus
    limitations: list[str] = Field(default_factory=list, max_length=8)


class PolicySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: UUID | None = None
    source: Literal["teacher_configured", "safe_default"]
    mode: TeachingMode
    allow_full_solution: bool
    minimum_attempts_for_scaffold: int = Field(ge=0)
    minimum_attempts_for_full_solution: int = Field(ge=0)
    max_hint_level: int = Field(ge=0, le=10)


class ReleaseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: TeachingAction
    release_level: AnswerReleaseLevel
    attempts_observed: int = Field(ge=0)
    reason_code: str = Field(min_length=1, max_length=120)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    citation_ids_valid: bool
    literal_course_claims_valid: bool
    scientific_references_valid: bool
    warnings: list[str] = Field(default_factory=list, max_length=12)


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: WorkflowStepName
    status: WorkflowStepStatus
    detail: str = Field(min_length=1, max_length=500)


class TeachingTurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID | None = None
    mode: TeachingMode
    message: str = Field(min_length=1, max_length=4000)
    student_attempt: str | None = Field(default=None, max_length=12000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=8)
    scientific_request: ScientificVerificationRequest | None = None
    learning_native: LearningNativeSubmission | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized

    @field_validator("student_attempt")
    @classmethod
    def normalize_attempt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("attachment_ids")
    @classmethod
    def attachment_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("attachment ids must be unique")
        return value


class LearningNativeSubmission(BaseModel):
    """Student-submitted Learning-Native artefacts for one turn.

    The student never selects a model or a policy action.  They submit a
    commitment, a teach-back reconstruction, or a transfer/solo attempt; the
    deterministic policy decides whether the submission is accepted and what
    is persisted as learning evidence.
    """

    model_config = ConfigDict(extra="forbid")

    commitment: CognitiveCommitment | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    teach_back: TeachBackSubmission | None = None
    transfer_attempt: TransferAttemptSubmission | None = None
    solo_attempt: SoloAttemptSubmission | None = None
    request_transfer: bool = False
    request_solo_exit: bool = False


class TeachBackSubmission(BaseModel):
    """A student reconstruction; the policy validates it before scoring."""

    model_config = ConfigDict(extra="forbid")

    reconstruction: str = Field(min_length=1, max_length=12000)
    target_concept_ids: list[UUID] = Field(default_factory=list, max_length=6)


class TransferAttemptSubmission(BaseModel):
    """A student attempt at a transfer task, submitted inside Solo Mode."""

    model_config = ConfigDict(extra="forbid")

    transfer_task_id: UUID
    response: str = Field(min_length=1, max_length=12000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SoloAttemptSubmission(BaseModel):
    """A student's unaided attempt for the current transfer task."""

    model_config = ConfigDict(extra="forbid")

    response: str = Field(min_length=1, max_length=12000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TeachingTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    turn_id: UUID
    workflow_version: str
    interpretation: InterpretationOutput
    diagnosis: DiagnosisOutput
    policy: PolicySnapshot
    release: ReleaseDecision
    evidence_packet: EvidencePacket
    response: TeachingResponse
    validation: ValidationReport
    scientific_results: list[ScientificVerificationResult] = Field(default_factory=list)
    trace: list[WorkflowStep]
    learning_native: LearningNativeTurnState | None = None

    @model_validator(mode="after")
    def trace_has_fixed_order(self) -> TeachingTurnResult:
        if tuple(step.name for step in self.trace) != WORKFLOW_ORDER:
            raise ValueError("teaching trace does not follow the fixed workflow")
        return self


class LearningNativeTurnState(BaseModel):
    """Per-turn Learning-Native artefacts produced by the deterministic policy.

    Every field here is observation or elicitation, never a mastery verdict or
    a psychological inference.  The LLM only proposes content (a commitment
    prompt, teach-back relations, a transfer task); code decides whether a
    gate is enforced, whether a submission satisfies it, whether Solo Mode is
    armed, and what is persisted as learning evidence.
    """

    model_config = ConfigDict(extra="forbid")

    commitment: CognitiveCommitment | None = None
    learning_action: LearningPolicyAction | None = None
    teach_back: TeachBackAnalysis | None = None
    transfer: TransferTask | None = None
    solo: SoloMode | None = None
    cognitive_mirror: CognitiveMirror | None = None
    evidence_persisted: list[str] = Field(default_factory=list, max_length=24)


# ---------------------------------------------------------------------------
# Learning-Native (PRD V3.0) contracts.  These are observation + elicitation
# contracts, explicitly not mastery verdicts, psychological inferences, or
# free-floating summaries.
# ---------------------------------------------------------------------------

class CommitmentKind(StrEnum):
    PREDICTION = "prediction"
    FIRST_STEP = "first_step"
    PHYSICAL_REASON = "physical_reason"
    DIAGRAM = "diagram"
    OPTION_WITH_CONFIDENCE = "option_with_confidence"
    SELF_EXPLANATION = "self_explanation"


class CommitmentGateDecision(StrEnum):
    ATTEMPT_REQUIRED = "attempt_required"
    PROCEED = "proceed"


class ConfidenceScale(StrEnum):
    PERCENT = "percent"  # 0-100; normalized to 0..1


class CognitiveCommitment(BaseModel):
    """A minimal cognitive commitment a student must submit before explanation.

    The LLM only proposes ``attempt_type`` and ``candidate_prompt``.  Whether a
    commitment is ``required`` and whether an actual submission satisfies it is
    decided by deterministic code.
    """

    model_config = ConfigDict(extra="forbid")

    gate_decision: CommitmentGateDecision
    attempt_required: bool
    attempt_type: CommitmentKind | None = None
    candidate_prompt: str = Field(default="", max_length=1200)
    reason_summary: str = Field(default="", max_length=600)
    accepted: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)


class TeachBackRelation(StrEnum):
    COVERED = "covered"
    MISSING = "missing"
    CONTRADICTORY = "contradictory"
    UNSUPPORTED = "unsupported"


class TeachBackFinding(BaseModel):
    """One relation-level finding against a student reconstruction."""

    model_config = ConfigDict(extra="forbid")

    relation: TeachBackRelation
    description: str = Field(min_length=1, max_length=500)
    target_concept_id: UUID | None = None


class TeachBackAnalysis(BaseModel):
    """Coverage review of a student reconstruction; no numeric score."""

    model_config = ConfigDict(extra="forbid")

    covered_relations: list[TeachBackFinding] = Field(default_factory=list, max_length=12)
    missing_relations: list[TeachBackFinding] = Field(default_factory=list, max_length=12)
    contradictions: list[TeachBackFinding] = Field(default_factory=list, max_length=6)
    unsupported_claims: list[TeachBackFinding] = Field(default_factory=list, max_length=6)
    recommended_probe: str = Field(default="", max_length=800)
    verified: bool = False
    is_model_inference: bool = True


class TransferType(StrEnum):
    NEAR = "near"
    PARAMETER = "parameter"
    REPRESENTATION = "representation"
    CONCEPTUAL = "conceptual"
    FAR = "far"
    DELAYED_RETRIEVAL = "delayed_retrieval"


class TransferTask(BaseModel):
    """An unaided transfer task, presented inside Solo Mode."""

    model_config = ConfigDict(extra="forbid")

    transfer_type: TransferType
    prompt: str = Field(min_length=1, max_length=2000)
    source_concept_ids: list[UUID] = Field(default_factory=list, max_length=6)
    key_parameters: list[str] = Field(default_factory=list, max_length=8)
    expected_observable: str = Field(default="", max_length=400)
    verifiable: bool = False


class SoloModeStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    EXITED = "exited"


class SoloMode(BaseModel):
    """Solo Mode is a backend-enforced assistance lock, not a UI badge."""

    model_config = ConfigDict(extra="forbid")

    status: SoloModeStatus = SoloModeStatus.INACTIVE
    active_transfer: TransferTask | None = None
    started_at: str | None = None
    assistance_locked: bool = True
    unlock_reason: str = Field(default="", max_length=400)


class ConceptStateLabel(StrEnum):
    UNKNOWN = "unknown"
    EXPOSED = "exposed"
    DEVELOPING = "developing"
    DEMONSTRATED = "demonstrated"
    TRANSFER_READY = "transfer_ready"
    FRAGILE = "fragile"
    NEEDS_REVIEW = "needs_review"


class ConceptMirrorState(BaseModel):
    """Evidence-based concept state; no fabricated percentage mastery."""

    model_config = ConfigDict(extra="forbid")

    concept_candidate_id: UUID
    label: ConceptStateLabel = ConceptStateLabel.UNKNOWN
    evidence_summary: list[str] = Field(default_factory=list, max_length=10)
    confidence_history: list[tuple[float, bool]] = Field(
        default_factory=list, max_length=24
    )
    calibration_gap: float | None = Field(default=None, ge=-1, le=1)
    unaided_retrieval: bool | None = None
    transfer_evidence: list[str] = Field(default_factory=list, max_length=6)
    hint_dependency: list[str] = Field(default_factory=list, max_length=6)
    misconception_candidates: list[str] = Field(default_factory=list, max_length=6)
    last_demonstrated_at: str | None = None


class CognitiveMirror(BaseModel):
    """The right-panel mirror: current concept + evidence, natural language."""

    model_config = ConfigDict(extra="forbid")

    current_concept_id: UUID | None = None
    concept_states: list[ConceptMirrorState] = Field(default_factory=list, max_length=40)
    summary: str = Field(default="", max_length=1200)
    no_personality_profile: bool = True


class LearningPolicyAction(StrEnum):
    ASK_COMMITMENT = "ask_commitment"
    ASK_PREDICTION = "ask_prediction"
    ASK_SELF_EXPLANATION = "ask_self_explanation"
    GIVE_CUE = "give_cue"
    GIVE_HINT = "give_hint"
    SHOW_COUNTEREXAMPLE = "show_counterexample"
    START_SIMULATION = "start_simulation"
    START_TEACH_BACK = "start_teach_back"
    START_TRANSFER = "start_transfer"
    ENTER_SOLO = "enter_solo"
    SHOW_WORKED_EXAMPLE = "show_worked_example"


__all__ = [
    "WORKFLOW_ORDER",
    "CognitiveCommitment",
    "CognitiveMirror",
    "CommitmentGateDecision",
    "CommitmentKind",
    "ConceptMirrorState",
    "ConceptStateLabel",
    "ConfidenceScale",
    "DiagnosisErrorKind",
    "DiagnosisOutput",
    "DiagnosisProgressState",
    "DiagnosisStatus",
    "DraftTeachingResponse",
    "FirstErrorLocalization",
    "InterpretationOutput",
    "LearningNativeSubmission",
    "LearningNativeTurnState",
    "LearningPolicyAction",
    "MisconceptionCandidate",
    "PolicySnapshot",
    "ReleaseDecision",
    "ResponseStatus",
    "SoloAttemptSubmission",
    "SoloMode",
    "SoloModeStatus",
    "StudentSnapshot",
    "SupportBasis",
    "TeachBackAnalysis",
    "TeachBackFinding",
    "TeachBackRelation",
    "TeachBackSubmission",
    "TeachingClaim",
    "TeachingResponse",
    "TeachingTurnInput",
    "TeachingTurnResult",
    "TransferAttemptSubmission",
    "TransferTask",
    "TransferType",
    "ValidationReport",
    "WorkflowStep",
    "WorkflowStepName",
    "WorkflowStepStatus",
]


# Resolve forward references for models that reference Learning-Native types
# defined later in this module.
TeachingTurnInput.model_rebuild()
LearningNativeSubmission.model_rebuild()
TeachingTurnResult.model_rebuild()
LearningNativeTurnState.model_rebuild()
TeachBackSubmission.model_rebuild()
TransferAttemptSubmission.model_rebuild()
SoloAttemptSubmission.model_rebuild()
