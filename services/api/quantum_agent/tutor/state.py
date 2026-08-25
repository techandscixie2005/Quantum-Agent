"""Serializable LangGraph state and non-persistent runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.knowledge.evidence_packets import EvidencePacket
from quantum_agent.llm.gateway import ModelGateway
from quantum_agent.multimodal.contracts import ConfirmedEvidence
from quantum_agent.multimodal.teaching import PerceptionTraceEntry
from quantum_agent.science import ScientificToolbox, ScientificVerificationResult
from quantum_agent.teaching.agents import EvidenceBundle
from quantum_agent.teaching.hitl import HitlEvent, HitlRejectedResponse
from quantum_agent.teaching.models import (
    DiagnosisOutput,
    InterpretationOutput,
    LearningNativeTurnState,
    PolicySnapshot,
    ReleaseDecision,
    TeachingResponse,
    TeachingTurnInput,
    TeachingTurnResult,
    ValidationReport,
    WorkflowStep,
)
from quantum_agent.teaching.repository import StartedTeachingTurn, StartedTeachingTurnRef
from quantum_agent.teaching.state_machine import EvidenceRetriever


@dataclass(frozen=True, slots=True)
class TutorContext:
    """Request-scoped dependencies that must never enter a checkpoint.

    LangGraph's ``context_schema`` passes this object directly to nodes while
    serializing only :class:`TutorState`.  A fresh context can therefore be
    supplied when a process resumes a durable thread.
    """

    session: AsyncSession
    actor: CourseActor
    curriculum_edition_id: UUID
    retriever: EvidenceRetriever
    model_gateway: ModelGateway | None
    scientific_toolbox: ScientificToolbox
    started_turn: StartedTeachingTurn
    use_specialist_agents: bool = False
    enable_hitl: bool = False


class TutorState(TypedDict, total=False):
    """Complete teaching graph state."""

    # Durable inputs and intermediates.  Every value here is JSON/Pydantic
    # serializable and safe for PostgreSQL-backed checkpointing.
    request: TeachingTurnInput
    interpretation: InterpretationOutput
    interpretation_degraded: bool
    evidence_packet: EvidencePacket
    evidence_bundle: EvidenceBundle
    diagnosis: DiagnosisOutput
    diagnosis_degraded: bool
    policy: PolicySnapshot
    release: ReleaseDecision
    scientific_results: list[ScientificVerificationResult]
    response: TeachingResponse
    validation: ValidationReport
    generation_degraded: bool
    trace: list[WorkflowStep]
    multimodal_evidence: list[ConfirmedEvidence]
    perception_trace: list[PerceptionTraceEntry]
    started_turn_ref: StartedTeachingTurnRef
    hitl_events: list[HitlEvent]
    restart_after_confirmation: bool
    hitl_rejection: HitlRejectedResponse | None

    # Learning-Native runtime state (PRD V3.0).  Carried through the same
    # checkpoint so a resumed turn keeps its commitment gate, Solo Mode, and
    # cognitive mirror.  The pre-generation decision is computed before
    # ``generate_response`` so the commitment gate can withhold the answer
    # rather than retroactively gating an already-generated explanation.
    learning_native: LearningNativeTurnState
    learning_native_evidence: list[dict[str, object]]
    solo_assistance_locked: bool
    learning_native_pre_decision: dict[str, object] | None
    answer_withheld_by_gate: bool

    # durable result
    result: TeachingTurnResult | None


__all__ = ["TutorContext", "TutorState"]
