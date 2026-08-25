"""Typed, deterministic human-in-the-loop contracts and decision rules.

The models in this module are checkpoint-safe.  They intentionally contain no
database sessions, ORM objects, callbacks, or model clients.  Human review can
approve a bounded result, reject the turn, or provide a replacement response,
but it cannot alter the deterministic policy decision or manufacture citation
and verifier references.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from quantum_agent.db_models import (
    AnswerReleaseLevel,
    CourseRole,
    TeachingMode,
)
from quantum_agent.knowledge.evidence_packets import EvidencePacket, RetrievalCoverage
from quantum_agent.multimodal.contracts import ConfirmedEvidence
from quantum_agent.multimodal.teaching import PerceptionTraceEntry
from quantum_agent.science import (
    ScientificVerificationResult,
    ScientificVerificationStatus,
)
from quantum_agent.teaching.agents import EvidenceBundle
from quantum_agent.teaching.models import (
    DiagnosisErrorKind,
    DiagnosisOutput,
    DiagnosisProgressState,
    InterpretationOutput,
    PolicySnapshot,
    ReleaseDecision,
    SupportBasis,
    TeachingResponse,
    TeachingTurnInput,
    ValidationReport,
    WorkflowStep,
)

HITL_SCHEMA_VERSION = "quantum-agent-hitl/1.0.0"
_MULTIMODAL_EVIDENCE_ADAPTER: TypeAdapter[ConfirmedEvidence] = TypeAdapter(
    ConfirmedEvidence
)


class HitlReason(StrEnum):
    TA_REQUESTED = "ta_requested"
    AMBIGUOUS_TRANSCRIPTION = "ambiguous_transcription"
    EVIDENCE_CONFLICT = "evidence_conflict"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    VERIFIER_MODEL_DISAGREEMENT = "verifier_model_disagreement"
    REPEATED_NO_PROGRESS = "repeated_no_progress"
    TEACHER_APPROVAL_REQUIRED = "teacher_approval_required"
    PROJECT_MILESTONE_REVIEW = "project_milestone_review"
    SAFETY_CONDITION = "safety_condition"


class HitlAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    TAKE_OVER = "take_over"
    CONFIRM_TRANSCRIPTION = "confirm_transcription"


STAFF_HITL_ACTIONS: tuple[HitlAction, ...] = (
    HitlAction.APPROVE,
    HitlAction.REJECT,
    HitlAction.EDIT,
    HitlAction.TAKE_OVER,
)


class HitlInterruptPayload(BaseModel):
    """Small value passed to LangGraph's ``interrupt`` primitive."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["quantum-agent-hitl/1.0.0"] = "quantum-agent-hitl/1.0.0"
    interrupt_id: UUID
    thread_id: UUID
    conversation_id: UUID
    turn_id: UUID
    stage: Literal["pre_release_review"] = "pre_release_review"
    reasons: tuple[HitlReason, ...] = Field(min_length=1, max_length=9)
    prompt: str = Field(min_length=1, max_length=1200)
    student_allowed_actions: tuple[HitlAction, ...] = ()
    staff_allowed_actions: tuple[HitlAction, ...] = STAFF_HITL_ACTIONS

    @model_validator(mode="after")
    def identifiers_and_actions_are_consistent(self) -> Self:
        if self.thread_id != self.conversation_id:
            raise ValueError("the LangGraph thread id must equal the conversation id")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("HITL reasons must be unique")
        can_confirm = self.reasons == (HitlReason.AMBIGUOUS_TRANSCRIPTION,)
        expected_student_actions = (HitlAction.CONFIRM_TRANSCRIPTION,) if can_confirm else ()
        if self.student_allowed_actions != expected_student_actions:
            raise ValueError("student actions do not match the interrupt reasons")
        if self.staff_allowed_actions != STAFF_HITL_ACTIONS:
            raise ValueError("staff actions must use the fixed review envelope")
        return self


class HitlResumeRequest(BaseModel):
    """Client-supplied review decision before actor identity is attached."""

    model_config = ConfigDict(extra="forbid")

    action: HitlAction
    note: str | None = Field(default=None, max_length=4000)
    edited_response: TeachingResponse | None = None
    confirmed_student_attempt: str | None = Field(default=None, max_length=12000)

    @model_validator(mode="after")
    def action_has_required_content(self) -> Self:
        if self.action in {HitlAction.EDIT, HitlAction.TAKE_OVER}:
            if self.edited_response is None:
                raise ValueError("edit and take-over actions require an edited response")
        elif self.edited_response is not None:
            raise ValueError("an edited response is allowed only for edit or take-over")
        if self.action is HitlAction.CONFIRM_TRANSCRIPTION:
            if not self.confirmed_student_attempt or not self.confirmed_student_attempt.strip():
                raise ValueError("transcription confirmation requires the confirmed attempt")
        elif self.confirmed_student_attempt is not None:
            raise ValueError("confirmed text is allowed only for transcription confirmation")
        if self.action in {HitlAction.REJECT, HitlAction.TAKE_OVER} and not (
            self.note and self.note.strip()
        ):
            raise ValueError("reject and take-over actions require an auditable note")
        return self


class HitlResolution(BaseModel):
    """Server-authenticated value supplied through ``Command(resume=...)``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interrupt_id: UUID
    action: HitlAction
    actor_user_id: UUID
    actor_role: CourseRole
    note: str | None = Field(default=None, max_length=4000)
    edited_response: TeachingResponse | None = None
    confirmed_student_attempt: str | None = Field(default=None, max_length=12000)

    @classmethod
    def authenticated(
        cls,
        *,
        payload: HitlInterruptPayload,
        request: HitlResumeRequest,
        actor_user_id: UUID,
        actor_role: CourseRole,
    ) -> HitlResolution:
        # Revalidate the client model here so construction never bypasses its
        # cross-field rules if an internal caller supplies a model copy.
        checked = HitlResumeRequest.model_validate(request.model_dump(mode="python"))
        return cls(
            interrupt_id=payload.interrupt_id,
            action=checked.action,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            note=checked.note.strip() if checked.note else None,
            edited_response=checked.edited_response,
            confirmed_student_attempt=(
                checked.confirmed_student_attempt.strip()
                if checked.confirmed_student_attempt
                else None
            ),
        )

    @model_validator(mode="after")
    def action_has_authenticated_authority(self) -> Self:
        if self.actor_role is CourseRole.STUDENT:
            if self.action is not HitlAction.CONFIRM_TRANSCRIPTION:
                raise ValueError("students may only confirm an ambiguous transcription")
        elif self.actor_role in {CourseRole.TA, CourseRole.TEACHER, CourseRole.ADMIN}:
            if self.action not in STAFF_HITL_ACTIONS:
                raise ValueError("teaching staff must use a staff review action")
        else:  # pragma: no cover - exhaustive protection for future enum members
            raise ValueError("actor role cannot resolve a HITL interrupt")
        if self.action in {HitlAction.EDIT, HitlAction.TAKE_OVER}:
            if self.edited_response is None:
                raise ValueError("edit and take-over actions require an edited response")
        elif self.edited_response is not None:
            raise ValueError("unexpected edited response")
        if self.action is HitlAction.CONFIRM_TRANSCRIPTION:
            if not self.confirmed_student_attempt:
                raise ValueError("confirmed transcription is missing")
        elif self.confirmed_student_attempt is not None:
            raise ValueError("unexpected transcription content")
        return self


class HitlEvent(BaseModel):
    """Checkpointed and eventually persisted audit record for one pause."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interrupt: HitlInterruptPayload
    resolution: HitlResolution | None = None

    @model_validator(mode="after")
    def resolution_matches_interrupt(self) -> Self:
        if self.resolution and self.resolution.interrupt_id != self.interrupt.interrupt_id:
            raise ValueError("resolution does not match the interrupt")
        return self


class HitlArtifacts(BaseModel):
    """Complete bounded state exposed to an authorized reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation: InterpretationOutput
    evidence_packet: EvidencePacket
    evidence_bundle: EvidenceBundle | None = None
    diagnosis: DiagnosisOutput
    policy: PolicySnapshot
    release: ReleaseDecision
    scientific_results: tuple[ScientificVerificationResult, ...] = ()
    proposed_response: TeachingResponse
    validation: ValidationReport
    trace: tuple[WorkflowStep, ...]
    multimodal_evidence: tuple[ConfirmedEvidence, ...] = ()
    perception_trace: tuple[PerceptionTraceEntry, ...] = ()


class HitlInterruptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["interrupted"] = "interrupted"
    conversation_id: UUID
    turn_id: UUID
    interrupt: HitlInterruptPayload
    artifacts: HitlArtifacts


class HitlRejectedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["rejected"] = "rejected"
    conversation_id: UUID
    turn_id: UUID
    interrupt_id: UUID
    reason_code: Literal["HITL_REJECTED"] = "HITL_REJECTED"


TeachingTurnOutcome = HitlInterruptResponse | HitlRejectedResponse


class HitlAuthorizationError(PermissionError):
    """Authenticated actor is not allowed to inspect or resolve the pause."""


class HitlNotFoundError(LookupError):
    """No current interrupt exists for the requested course thread."""


class HitlConflictError(RuntimeError):
    """The checkpoint or durable turn is no longer resumable."""


class HitlResolutionValidationError(ValueError):
    """A human-edited response violates policy or evidence constraints."""


_TA_REQUEST_RE = re.compile(
    r"(?:@ta\b|\brequest[ _-]?ta\b|\bask (?:a )?ta\b|请求助教|联系助教|请助教|人工协助)",
    flags=re.IGNORECASE,
)
_PROJECT_REVIEW_RE = re.compile(
    r"(?:\bmilestone\b|\bsubmit(?:ted|ting)?\b|\breview\b|里程碑|提交审阅|项目审阅)",
    flags=re.IGNORECASE,
)
_TEACHER_APPROVAL_RE = re.compile(
    r"(?:\bteacher approval\b|\binstructor approval\b|教师批准|老师审批|教师审批)",
    flags=re.IGNORECASE,
)


def _has_unconfirmed_perception(value: object) -> bool:
    """Recognize current/future typed multimodal evidence without trusting prose."""

    if isinstance(value, BaseModel):
        data: object = value.model_dump(mode="python")
    else:
        data = value
    if isinstance(data, dict):
        state = data.get("confirmation_state")
        required = data.get("requires_confirmation")
        if required is True and state in {None, "required"}:
            return True
        return any(
            _has_unconfirmed_perception(item)
            for key, item in data.items()
            if key in {"visual_evidence", "document_evidence", "multimodal_evidence"}
        )
    if isinstance(data, (list, tuple)):
        return any(_has_unconfirmed_perception(item) for item in data)
    return False


def _verifier_disagrees(
    diagnosis: DiagnosisOutput,
    results: list[ScientificVerificationResult],
) -> bool:
    if not diagnosis.verification_needed or not results:
        return False
    first_error = diagnosis.first_error
    model_reports_error = first_error is not None and first_error.kind not in {
        DiagnosisErrorKind.NO_CLEAR_ERROR,
        DiagnosisErrorKind.INCONCLUSIVE,
    }
    verifier_passes = any(result.status is ScientificVerificationStatus.PASS for result in results)
    verifier_fails = any(result.status is ScientificVerificationStatus.FAIL for result in results)
    return (model_reports_error and verifier_passes) or (not model_reports_error and verifier_fails)


def determine_hitl_reasons(
    *,
    request: TeachingTurnInput,
    packet: EvidencePacket,
    bundle: EvidenceBundle | None,
    diagnosis: DiagnosisOutput,
    scientific_results: list[ScientificVerificationResult],
    recent_no_progress_count: int,
    state: dict[str, Any],
) -> tuple[HitlReason, ...]:
    """Return deterministic, stable-order reasons for a pre-release pause."""

    reasons: list[HitlReason] = []
    if _TA_REQUEST_RE.search(request.message):
        reasons.append(HitlReason.TA_REQUESTED)
    if _has_unconfirmed_perception(state):
        reasons.append(HitlReason.AMBIGUOUS_TRANSCRIPTION)
    if bundle is not None and bundle.conflicts:
        reasons.append(HitlReason.EVIDENCE_CONFLICT)
    if packet.coverage is RetrievalCoverage.NOT_FOUND:
        reasons.append(HitlReason.INSUFFICIENT_COVERAGE)
    if _verifier_disagrees(diagnosis, scientific_results):
        reasons.append(HitlReason.VERIFIER_MODEL_DISAGREEMENT)
    if (
        recent_no_progress_count >= 2
        and diagnosis.progress_state is DiagnosisProgressState.STRUGGLING
    ):
        reasons.append(HitlReason.REPEATED_NO_PROGRESS)
    if _TEACHER_APPROVAL_RE.search(request.message):
        reasons.append(HitlReason.TEACHER_APPROVAL_REQUIRED)
    if request.mode is TeachingMode.WORK_ON_PROJECTS and _PROJECT_REVIEW_RE.search(request.message):
        reasons.append(HitlReason.PROJECT_MILESTONE_REVIEW)
    if state.get("safety_condition") is True:
        reasons.append(HitlReason.SAFETY_CONDITION)
    return tuple(reasons)


def build_interrupt_payload(
    *,
    conversation_id: UUID,
    turn_id: UUID,
    reasons: tuple[HitlReason, ...],
) -> HitlInterruptPayload:
    reason_key = ",".join(reason.value for reason in reasons)
    interrupt_id = uuid5(
        NAMESPACE_URL,
        f"{HITL_SCHEMA_VERSION}:{conversation_id}:{turn_id}:pre_release_review:{reason_key}",
    )
    prompt = "Human review is required before this bounded teaching response can be released: "
    prompt += ", ".join(reason.value for reason in reasons)
    student_actions = (
        (HitlAction.CONFIRM_TRANSCRIPTION,)
        if reasons == (HitlReason.AMBIGUOUS_TRANSCRIPTION,)
        else ()
    )
    return HitlInterruptPayload(
        interrupt_id=interrupt_id,
        thread_id=conversation_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        reasons=reasons,
        prompt=prompt,
        student_allowed_actions=student_actions,
    )


_CLAIM_LIMIT = {
    AnswerReleaseLevel.QUESTION_ONLY: 0,
    AnswerReleaseLevel.HINT: 1,
    AnswerReleaseLevel.SCAFFOLD: 3,
    AnswerReleaseLevel.FULL_EXPLANATION: 6,
    AnswerReleaseLevel.FULL_SOLUTION: 8,
}


def validate_human_response(
    *,
    response: TeachingResponse,
    packet: EvidencePacket,
    scientific_results: list[ScientificVerificationResult],
    release: ReleaseDecision,
) -> ValidationReport:
    """Apply the same citation/tool envelope to a reviewer-authored response."""

    evidence_by_id = {item.evidence_id: item for item in packet.evidence}
    scientific_ids = {
        f"{result.kind.value}:{result.inputs_sha256}" for result in scientific_results
    }
    citation_ids_valid = True
    literal_claims_valid = True
    scientific_references_valid = True
    warnings: list[str] = []
    for claim in response.claims:
        if any(identifier not in evidence_by_id for identifier in claim.evidence_ids):
            citation_ids_valid = False
        if claim.support_basis is SupportBasis.COURSE_MATERIAL:
            sources = [
                evidence_by_id[identifier]
                for identifier in claim.evidence_ids
                if identifier in evidence_by_id
            ]
            if not any(claim.text in item.evidence_snippet for item in sources):
                literal_claims_valid = False
        if any(identifier not in scientific_ids for identifier in claim.scientific_result_ids):
            scientific_references_valid = False
    if len(response.claims) > _CLAIM_LIMIT[release.release_level]:
        warnings.append("human_response_exceeds_release_claim_limit")
    if not citation_ids_valid:
        warnings.append("unknown_evidence_id")
    if not literal_claims_valid:
        warnings.append("course_claim_not_literal_source_span")
    if not scientific_references_valid:
        warnings.append("unknown_scientific_result_id")
    passed = not warnings
    return ValidationReport(
        passed=passed,
        citation_ids_valid=citation_ids_valid,
        literal_course_claims_valid=literal_claims_valid,
        scientific_references_valid=scientific_references_valid,
        warnings=warnings,
    )


def artifacts_from_state(state: dict[str, Any]) -> HitlArtifacts:
    return HitlArtifacts(
        interpretation=InterpretationOutput.model_validate(state["interpretation"]),
        evidence_packet=EvidencePacket.model_validate(state["evidence_packet"]),
        evidence_bundle=(
            EvidenceBundle.model_validate(state["evidence_bundle"])
            if state.get("evidence_bundle") is not None
            else None
        ),
        diagnosis=DiagnosisOutput.model_validate(state["diagnosis"]),
        policy=PolicySnapshot.model_validate(state["policy"]),
        release=ReleaseDecision.model_validate(state["release"]),
        scientific_results=tuple(
            ScientificVerificationResult.model_validate(item)
            for item in state.get("scientific_results", [])
        ),
        proposed_response=TeachingResponse.model_validate(state["response"]),
        validation=ValidationReport.model_validate(state["validation"]),
        trace=tuple(WorkflowStep.model_validate(item) for item in state.get("trace", [])),
        multimodal_evidence=tuple(
            _MULTIMODAL_EVIDENCE_ADAPTER.validate_python(item)
            for item in state.get("multimodal_evidence", [])
        ),
        perception_trace=tuple(
            PerceptionTraceEntry.model_validate(item)
            for item in state.get("perception_trace", [])
        ),
    )


__all__ = [
    "HITL_SCHEMA_VERSION",
    "STAFF_HITL_ACTIONS",
    "HitlAction",
    "HitlArtifacts",
    "HitlAuthorizationError",
    "HitlConflictError",
    "HitlEvent",
    "HitlInterruptPayload",
    "HitlInterruptResponse",
    "HitlNotFoundError",
    "HitlReason",
    "HitlRejectedResponse",
    "HitlResolution",
    "HitlResolutionValidationError",
    "HitlResumeRequest",
    "TeachingTurnOutcome",
    "artifacts_from_state",
    "build_interrupt_payload",
    "determine_hitl_reasons",
    "validate_human_response",
]
