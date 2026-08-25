"""Read-only, course-scoped teaching governance endpoints.

The endpoints in this module expose durable state-machine traces and modest
event counts to course teaching staff.  Learning-evidence statistics retain the
database distinction between observations and model-generated diagnostic
hypotheses.  They intentionally do not calculate or report student mastery.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import (
    TEACHING_STAFF_ROLES,
    authenticate_course_actor,
    bearer_credential,
)
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AgentTrace,
    AnswerReleaseLevel,
    CurriculumEdition,
    LearningEvidence,
    LearningEvidenceKind,
    TeachingAction,
    TeachingConversation,
    TeachingMode,
    TeachingTaskKind,
    TeachingTurn,
    TeachingTurnStatus,
)
from quantum_agent.knowledge.evidence_packets import EvidencePacket
from quantum_agent.science import ScientificVerificationResult
from quantum_agent.teaching.agents import EvidenceBundle
from quantum_agent.teaching.hitl import HitlEvent
from quantum_agent.teaching.models import (
    DiagnosisOutput,
    PolicySnapshot,
    ReleaseDecision,
    TeachingResponse,
    ValidationReport,
    WorkflowStep,
)

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/teacher",
    tags=["teacher-insights"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


class AgentTraceSummary(BaseModel):
    """Small trace representation suitable for a paginated queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    teaching_turn_id: UUID
    conversation_id: UUID
    student_user_id: UUID
    mode: TeachingMode
    sequence_number: int = Field(ge=1)
    task_kind: TeachingTaskKind | None
    teaching_action: TeachingAction | None
    release_level: AnswerReleaseLevel | None
    turn_status: TeachingTurnStatus
    workflow_version: str
    model_gateway_status: str
    citation_validation_status: str
    created_at: datetime
    completed_at: datetime | None


class AgentTracePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    items: list[AgentTraceSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    has_more: bool


class AgentTraceDetail(AgentTraceSummary):
    """Validated execution record for teacher inspection."""

    user_message: str
    student_attempt: str | None
    workflow_steps: list[WorkflowStep]
    policy_snapshot: PolicySnapshot
    evidence_packet: EvidencePacket | None
    evidence_bundle: EvidenceBundle | None
    diagnosis: DiagnosisOutput | None
    release_decision: ReleaseDecision | None
    response: TeachingResponse | None
    scientific_results: list[ScientificVerificationResult]
    validation: ValidationReport | None
    hitl_events: list[HitlEvent]
    failure_code: str | None


class EvidenceEventAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_count: int = Field(ge=0)
    distinct_students: int = Field(ge=0)


class InferredMisconceptionAggregate(BaseModel):
    """A model-generated hypothesis count, never an observed student fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inferred_label: str = Field(min_length=1, max_length=500)
    inference_event_count: int = Field(ge=1)
    distinct_students: int = Field(ge=1)
    evidence_class: Literal["diagnosis_inference"] = "diagnosis_inference"


class StatisticsSemantics(BaseModel):
    """Machine-readable guardrails for consumers of aggregate counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation_unit: Literal["recorded_learning_evidence_events"] = (
        "recorded_learning_evidence_events"
    )
    observed_attempts: Literal["Student submitted an attempt; correctness is not implied."] = (
        "Student submitted an attempt; correctness is not implied."
    )
    diagnosis_inferences: Literal["Model-generated diagnostic hypotheses; not observed facts."] = (
        "Model-generated diagnostic hypotheses; not observed facts."
    )
    mastery: Literal["No mastery estimate is produced by these statistics."] = (
        "No mastery estimate is produced by these statistics."
    )


class LearningEvidenceStatistics(BaseModel):
    """Course/edition event aggregates with explicit epistemic labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    total_recorded_events: int = Field(ge=0)
    observed_attempts: EvidenceEventAggregate
    observed_check_responses: EvidenceEventAggregate
    deterministic_tool_observations: EvidenceEventAggregate
    diagnosis_inferences: EvidenceEventAggregate
    inferred_misconceptions: list[InferredMisconceptionAggregate]
    inferred_misconception_label_count: int = Field(ge=0)
    inferred_misconceptions_truncated: bool
    semantics: StatisticsSemantics = Field(default_factory=StatisticsSemantics)


async def _authorize_and_require_edition(
    request: Request,
    session: AsyncSession,
    *,
    course_id: UUID,
    curriculum_edition_id: UUID,
) -> None:
    await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
        allowed_roles=TEACHING_STAFF_ROLES,
    )
    edition_exists = await session.scalar(
        select(CurriculumEdition.id).where(
            CurriculumEdition.id == curriculum_edition_id,
            CurriculumEdition.course_id == course_id,
        )
    )
    if edition_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course edition not found",
        )


def _trace_summary(
    trace: AgentTrace,
    turn: TeachingTurn,
    conversation: TeachingConversation,
) -> AgentTraceSummary:
    return AgentTraceSummary(
        id=trace.id,
        teaching_turn_id=trace.teaching_turn_id,
        conversation_id=turn.conversation_id,
        student_user_id=trace.student_user_id,
        mode=conversation.mode,
        sequence_number=turn.sequence_number,
        task_kind=turn.task_kind,
        teaching_action=turn.teaching_action,
        release_level=turn.release_level,
        turn_status=turn.status,
        workflow_version=trace.workflow_version,
        model_gateway_status=trace.model_gateway_status,
        citation_validation_status=trace.citation_validation_status,
        created_at=trace.created_at,
        completed_at=turn.completed_at,
    )


def _validated_trace_detail(
    trace: AgentTrace,
    turn: TeachingTurn,
    conversation: TeachingConversation,
) -> AgentTraceDetail:
    try:
        raw_steps = trace.steps_json.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("trace steps are malformed")
        workflow_steps = [WorkflowStep.model_validate(item) for item in raw_steps]
        policy = PolicySnapshot.model_validate(trace.policy_snapshot_json)
        packet = (
            EvidencePacket.model_validate(turn.evidence_packet_json)
            if turn.evidence_packet_json is not None
            else None
        )
        raw_bundle = trace.steps_json.get("evidence_bundle")
        evidence_bundle = (
            EvidenceBundle.model_validate(raw_bundle) if raw_bundle is not None else None
        )
        raw_diagnosis = trace.steps_json.get("diagnosis")
        diagnosis = (
            DiagnosisOutput.model_validate(raw_diagnosis) if raw_diagnosis is not None else None
        )
        raw_release = trace.steps_json.get("release")
        release_decision = (
            ReleaseDecision.model_validate(raw_release) if raw_release is not None else None
        )
        response = (
            TeachingResponse.model_validate(turn.response_json)
            if turn.response_json is not None
            else None
        )
        raw_results = turn.scientific_results_json.get("results", [])
        if not isinstance(raw_results, list):
            raise ValueError("scientific results are malformed")
        scientific_results = [
            ScientificVerificationResult.model_validate(item) for item in raw_results
        ]
        validation = (
            ValidationReport.model_validate(turn.validation_json) if turn.validation_json else None
        )
        raw_hitl_events = trace.steps_json.get("hitl_events", [])
        if not isinstance(raw_hitl_events, list):
            raise ValueError("trace HITL events are malformed")
        hitl_events = [HitlEvent.model_validate(item) for item in raw_hitl_events]
    except (TypeError, ValueError, ValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored agent trace failed validation",
        ) from error

    summary = _trace_summary(trace, turn, conversation)
    return AgentTraceDetail(
        **summary.model_dump(),
        user_message=turn.user_message,
        student_attempt=turn.student_attempt,
        workflow_steps=workflow_steps,
        policy_snapshot=policy,
        evidence_packet=packet,
        evidence_bundle=evidence_bundle,
        diagnosis=diagnosis,
        release_decision=release_decision,
        response=response,
        scientific_results=scientific_results,
        validation=validation,
        hitl_events=hitl_events,
        failure_code=turn.failure_code,
    )


@router.get("/agent-traces", response_model=AgentTracePage)
async def list_agent_traces(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> AgentTracePage:
    await _authorize_and_require_edition(
        request,
        session,
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
    )
    scope = (
        AgentTrace.course_id == course_id,
        AgentTrace.curriculum_edition_id == curriculum_edition_id,
    )
    total = int(await session.scalar(select(func.count(AgentTrace.id)).where(*scope)) or 0)
    rows = (
        await session.execute(
            select(AgentTrace, TeachingTurn, TeachingConversation)
            .join(TeachingTurn, TeachingTurn.id == AgentTrace.teaching_turn_id)
            .join(
                TeachingConversation,
                TeachingConversation.id == TeachingTurn.conversation_id,
            )
            .where(*scope)
            .order_by(AgentTrace.created_at.desc(), AgentTrace.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return AgentTracePage(
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
        items=[_trace_summary(trace, turn, conversation) for trace, turn, conversation in rows],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(rows) < total,
    )


@router.get("/agent-traces/{trace_id}", response_model=AgentTraceDetail)
async def get_agent_trace(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    trace_id: UUID,
    session: DatabaseSession,
) -> AgentTraceDetail:
    await _authorize_and_require_edition(
        request,
        session,
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
    )
    row = (
        await session.execute(
            select(AgentTrace, TeachingTurn, TeachingConversation)
            .join(TeachingTurn, TeachingTurn.id == AgentTrace.teaching_turn_id)
            .join(
                TeachingConversation,
                TeachingConversation.id == TeachingTurn.conversation_id,
            )
            .where(
                AgentTrace.id == trace_id,
                AgentTrace.course_id == course_id,
                AgentTrace.curriculum_edition_id == curriculum_edition_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent trace not found")
    return _validated_trace_detail(*row)


@router.get("/learning-statistics", response_model=LearningEvidenceStatistics)
async def learning_statistics(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    session: DatabaseSession,
    misconception_limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> LearningEvidenceStatistics:
    await _authorize_and_require_edition(
        request,
        session,
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
    )
    scope = (
        LearningEvidence.course_id == course_id,
        LearningEvidence.curriculum_edition_id == curriculum_edition_id,
    )
    kind_rows = (
        await session.execute(
            select(
                LearningEvidence.kind,
                func.count(LearningEvidence.id),
                func.count(distinct(LearningEvidence.student_user_id)),
            )
            .where(*scope)
            .group_by(LearningEvidence.kind)
        )
    ).all()
    counts = {
        kind: EvidenceEventAggregate(
            event_count=int(event_count),
            distinct_students=int(student_count),
        )
        for kind, event_count, student_count in kind_rows
    }

    misconception_label = LearningEvidence.evidence_json["likely_misconception"].as_string()
    misconception_scope = (
        *scope,
        LearningEvidence.kind == LearningEvidenceKind.DIAGNOSIS_INFERENCE,
        misconception_label.is_not(None),
        func.length(func.trim(misconception_label)) > 0,
    )
    inferred_label_count = int(
        await session.scalar(
            select(func.count(distinct(misconception_label))).where(*misconception_scope)
        )
        or 0
    )
    misconception_rows = (
        await session.execute(
            select(
                misconception_label,
                func.count(LearningEvidence.id).label("event_count"),
                func.count(distinct(LearningEvidence.student_user_id)).label("student_count"),
            )
            .where(*misconception_scope)
            .group_by(misconception_label)
            .order_by(
                func.count(LearningEvidence.id).desc(),
                misconception_label.asc(),
            )
            .limit(misconception_limit)
        )
    ).all()

    empty = EvidenceEventAggregate(event_count=0, distinct_students=0)
    return LearningEvidenceStatistics(
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
        total_recorded_events=sum(item.event_count for item in counts.values()),
        observed_attempts=counts.get(LearningEvidenceKind.STUDENT_ATTEMPT, empty),
        observed_check_responses=counts.get(LearningEvidenceKind.CHECK_RESPONSE, empty),
        deterministic_tool_observations=counts.get(
            LearningEvidenceKind.TOOL_OBSERVATION,
            empty,
        ),
        diagnosis_inferences=counts.get(LearningEvidenceKind.DIAGNOSIS_INFERENCE, empty),
        inferred_misconceptions=[
            InferredMisconceptionAggregate(
                inferred_label=str(label)[:500],
                inference_event_count=int(event_count),
                distinct_students=int(student_count),
            )
            for label, event_count, student_count in misconception_rows
        ],
        inferred_misconception_label_count=inferred_label_count,
        inferred_misconceptions_truncated=inferred_label_count > len(misconception_rows),
    )


__all__ = [
    "AgentTraceDetail",
    "AgentTracePage",
    "AgentTraceSummary",
    "EvidenceEventAggregate",
    "InferredMisconceptionAggregate",
    "LearningEvidenceStatistics",
    "StatisticsSemantics",
    "router",
]
