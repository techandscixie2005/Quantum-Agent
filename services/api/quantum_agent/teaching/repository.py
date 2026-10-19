"""Persistence boundary for teaching turns, traces, and learning observations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    AgentTrace,
    CourseMembership,
    LearningEvidence,
    LearningEvidenceKind,
    MembershipStatus,
    TeachingConversation,
    TeachingConversationStatus,
    TeachingTurn,
    TeachingTurnStatus,
    User,
)
from quantum_agent.multimodal.contracts import ConfirmedEvidence
from quantum_agent.multimodal.teaching import PerceptionTraceEntry
from quantum_agent.teaching.access import (
    TeachingConversationConflictError,
    require_conversation_assistance_access,
)
from quantum_agent.teaching.agents import EvidenceBundle
from quantum_agent.teaching.hitl import HitlArtifacts, HitlEvent, HitlInterruptPayload
from quantum_agent.teaching.models import (
    DurableLearningPhase,
    TeachingTurnInput,
    TeachingTurnResult,
)


class LearningEvidenceRecord(BaseModel):
    """A learning-evidence row the deterministic Learning-Native policy asked to persist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: LearningEvidenceKind
    observation: str = Field(min_length=1, max_length=1000)
    concept_candidate_id: UUID | None = None
    mastery_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    evidence_json: dict[str, object] = Field(default_factory=dict)


class StartedTeachingTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    conversation: TeachingConversation
    turn: TeachingTurn
    prior_attempts: int = Field(ge=0)
    recent_no_progress_count: int = Field(default=0, ge=0, le=20)
    idempotent_replay: bool = False
    durable_phase: DurableLearningPhase = Field(default_factory=DurableLearningPhase)


class StartedTeachingTurnRef(BaseModel):
    """Serializable identity needed to reconstruct runtime context on resume."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    turn_id: UUID
    student_user_id: UUID
    prior_attempts: int = Field(ge=0)
    recent_no_progress_count: int = Field(default=0, ge=0, le=20)

    @classmethod
    def from_started(cls, started: StartedTeachingTurn) -> StartedTeachingTurnRef:
        return cls(
            conversation_id=started.conversation.id,
            turn_id=started.turn.id,
            student_user_id=started.conversation.student_user_id,
            prior_attempts=started.prior_attempts,
            recent_no_progress_count=started.recent_no_progress_count,
        )


class TeachingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start_turn(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        request: TeachingTurnInput,
    ) -> StartedTeachingTurn:
        # A database lock protects starts across workers, including requests
        # that have no conversation id yet. No process-local cache can do this.
        await self._session.scalar(
            select(User.id).where(User.id == actor.user_id).with_for_update()
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json", exclude={"conversation_id", "client_request_id"}),
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if request.client_request_id:
            replay = (
                await self._session.execute(
                    select(TeachingConversation, TeachingTurn)
                    .join(TeachingTurn, TeachingTurn.conversation_id == TeachingConversation.id)
                    .where(
                        TeachingConversation.course_id == actor.course_id,
                        TeachingConversation.curriculum_edition_id == curriculum_edition_id,
                        TeachingConversation.student_user_id == actor.user_id,
                        TeachingTurn.client_request_id == request.client_request_id,
                    )
                    .order_by(TeachingTurn.created_at.asc())
                    .limit(1)
                    .with_for_update().execution_options(populate_existing=True)
                )
            ).one_or_none()
            if replay is not None:
                conversation, replay_turn = replay
                if request.conversation_id not in {None, conversation.id}:
                    raise TeachingConversationConflictError("request key belongs to another thread")
                if replay_turn.request_fingerprint is not None:
                    same_input = replay_turn.request_fingerprint == fingerprint
                else:
                    # Legacy rows retain only part of the original request.
                    same_input = (
                        replay_turn.user_message == request.message
                        and replay_turn.student_attempt == request.student_attempt
                    )
                if not same_input:
                    raise TeachingConversationConflictError(
                        "request key was reused with changed input"
                    )
                await require_conversation_assistance_access(
                    self._session, actor, conversation.id,
                )
                return await self._replayed_turn(conversation, replay_turn)
        await require_conversation_assistance_access(
            self._session, actor, request.conversation_id,
        )
        if request.conversation_id is None:
            conversation = TeachingConversation(
                course_id=actor.course_id,
                curriculum_edition_id=curriculum_edition_id,
                student_user_id=actor.user_id,
                mode=request.mode,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
            )
            self._session.add(conversation)
            await self._session.flush()
            sequence_number = 1
            prior_attempts = 0
            recent_no_progress_count = 0
        else:
            existing_conversation = await self._session.scalar(
                select(TeachingConversation)
                .where(
                    TeachingConversation.id == request.conversation_id,
                    TeachingConversation.course_id == actor.course_id,
                    TeachingConversation.curriculum_edition_id == curriculum_edition_id,
                    TeachingConversation.student_user_id == actor.user_id,
                    TeachingConversation.status == TeachingConversationStatus.ACTIVE,
                )
                .with_for_update().execution_options(populate_existing=True)
            )
            if existing_conversation is None:
                raise TeachingConversationConflictError(
                    "conversation is unavailable in this course, edition, mode, or account"
                )
            conversation = existing_conversation
            phase = await self.load_durable_learning_phase(conversation=conversation)
            if (
                request.course_package is not None
                and phase.course_package is not None
                and (
                    request.course_package.package_id != phase.course_package.package_id
                    or request.course_package.version != phase.course_package.version
                )
            ):
                raise TeachingConversationConflictError("course package is pinned for this thread")
            # Golden Loop §6: the durable phase sequence must run on ONE
            # conversation_id.  A mode switch mid-loop (e.g. learn_concepts →
            # run_experiments for a coding turn) continues the same ACTIVE
            # conversation instead of forcing the student back through the
            # commitment gate; the durable phase carries over.  The mutation
            # happens only after the replay/running checks below.
            running_turn = await self._session.scalar(
                select(TeachingTurn)
                .where(
                    TeachingTurn.conversation_id == conversation.id,
                    TeachingTurn.status == TeachingTurnStatus.RUNNING,
                )
                .order_by(TeachingTurn.sequence_number.desc())
                .limit(1)
            )
            if running_turn is not None:
                stored_attachment_ids = running_turn.validation_json.get(
                    "input_attachment_ids", []
                )
                if (
                    not request.client_request_id
                    and running_turn.user_message == request.message
                    and running_turn.student_attempt == request.student_attempt
                    and stored_attachment_ids
                    == [str(attachment_id) for attachment_id in request.attachment_ids]
                ):
                    return await self._replayed_turn(conversation, running_turn)
                raise TeachingConversationConflictError(
                    "conversation has a teaching turn awaiting human review"
                )
            if conversation.mode is not request.mode:
                conversation.mode = request.mode
            last_sequence = await self._session.scalar(
                select(func.max(TeachingTurn.sequence_number)).where(
                    TeachingTurn.conversation_id == conversation.id
                )
            )
            sequence_number = int(last_sequence or 0) + 1
            prior_attempts = await self._attempt_count(conversation.id)
            recent_no_progress_count = await self._recent_no_progress_count(conversation.id)
            conversation.last_activity_at = datetime.now(UTC)

        turn = TeachingTurn(
            conversation_id=conversation.id,
            sequence_number=sequence_number,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
            user_message=request.message,
            student_attempt=request.student_attempt,
            status=TeachingTurnStatus.RUNNING,
            # Preserve the validated input before any provider/native work.
            # Raw submissions are audit evidence, never qualification as a
            # valid, independent, correct or mastered performance.
            scientific_results_json={"__initial_request": request.model_dump(mode="json")},
            validation_json={
                "input_attachment_ids": [
                    str(attachment_id) for attachment_id in request.attachment_ids
                ],
                "client_request_id": request.client_request_id or "",
            },
        )
        self._session.add(turn)
        await self._session.flush()
        return StartedTeachingTurn(
            conversation=conversation,
            turn=turn,
            prior_attempts=prior_attempts,
            recent_no_progress_count=recent_no_progress_count,
            durable_phase=await self.load_durable_learning_phase(
                conversation=conversation
            ),
        )

    async def _replayed_turn(
        self, conversation: TeachingConversation, turn: TeachingTurn,
    ) -> StartedTeachingTurn:
        from quantum_agent.teaching.execution_budget import raise_if_execution_exhausted

        raise_if_execution_exhausted(turn)
        return StartedTeachingTurn(
            conversation=conversation, turn=turn, idempotent_replay=True,
            prior_attempts=await self._attempt_count(conversation.id, excluding_turn_id=turn.id),
            recent_no_progress_count=await self._recent_no_progress_count(
                conversation.id, excluding_turn_id=turn.id,
            ),
            durable_phase=await self.load_durable_learning_phase(conversation=conversation),
        )

    async def _attempt_count(
        self,
        conversation_id: UUID,
        *,
        excluding_turn_id: UUID | None = None,
    ) -> int:
        statement = select(func.count(TeachingTurn.id)).where(
            TeachingTurn.conversation_id == conversation_id,
            TeachingTurn.student_attempt.is_not(None),
            func.length(func.trim(TeachingTurn.student_attempt)) > 0,
        )
        if excluding_turn_id is not None:
            statement = statement.where(TeachingTurn.id != excluding_turn_id)
        return int(await self._session.scalar(statement) or 0)

    async def _recent_no_progress_count(
        self,
        conversation_id: UUID,
        *,
        excluding_turn_id: UUID | None = None,
    ) -> int:
        statement = (
            select(TeachingTurn, AgentTrace)
            .outerjoin(AgentTrace, AgentTrace.teaching_turn_id == TeachingTurn.id)
            .where(TeachingTurn.conversation_id == conversation_id)
            .order_by(TeachingTurn.sequence_number.desc())
            .limit(5)
        )
        if excluding_turn_id is not None:
            statement = statement.where(TeachingTurn.id != excluding_turn_id)
        rows = (await self._session.execute(statement)).all()
        count = 0
        for turn, trace in rows:
            # Provider failures and teacher rejections do not diagnose a learner.
            no_progress = False
            if turn.status is TeachingTurnStatus.COMPLETED:
                raw_results = turn.scientific_results_json.get("results", [])
                assertion_kinds = {
                    "symbolic_equivalence", "symbolic_residual",
                    "numerical_normalization", "numerical_unitarity",
                }
                statuses = {
                    item.get("status")
                    for item in raw_results
                    if isinstance(item, dict) and item.get("kind") in assertion_kinds
                }
                if "pass" in statuses:
                    no_progress = False
                elif "fail" in statuses:
                    no_progress = True
                elif trace is not None:
                    diagnosis = trace.steps_json.get("diagnosis", {})
                    no_progress = (
                        isinstance(diagnosis, dict)
                        and diagnosis.get("progress_state") == "struggling"
                    )
            if not no_progress:
                break
            count += 1
        return count

    async def load_started_turn(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        reference: StartedTeachingTurnRef,
    ) -> StartedTeachingTurn:
        row = (
            await self._session.execute(
                select(TeachingConversation, TeachingTurn)
                .join(
                    TeachingTurn,
                    TeachingTurn.conversation_id == TeachingConversation.id,
                )
                .where(
                    TeachingConversation.id == reference.conversation_id,
                    TeachingConversation.course_id == course_id,
                    TeachingConversation.curriculum_edition_id == curriculum_edition_id,
                    TeachingConversation.student_user_id == reference.student_user_id,
                    TeachingTurn.id == reference.turn_id,
                )
                .with_for_update().execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise TeachingConversationConflictError(
                "checkpointed teaching turn is unavailable in this course scope"
            )
        conversation, turn = row
        if turn.status is not TeachingTurnStatus.RUNNING:
            raise TeachingConversationConflictError(
                "checkpointed teaching turn is no longer resumable"
            )
        return StartedTeachingTurn(
            conversation=conversation,
            turn=turn,
            prior_attempts=reference.prior_attempts,
            recent_no_progress_count=reference.recent_no_progress_count,
            idempotent_replay=True,
            durable_phase=await self.load_durable_learning_phase(
                conversation=conversation
            ),
        )

    async def resolved_interrupt(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        conversation_id: UUID,
        interrupt_id: UUID,
    ) -> tuple[StartedTeachingTurn, HitlEvent] | None:
        """Find an exact durable decision even after its checkpoint has advanced."""

        row = (
            await self._session.execute(
                select(TeachingConversation, TeachingTurn)
                .join(TeachingTurn, TeachingTurn.conversation_id == TeachingConversation.id)
                .where(
                    TeachingConversation.id == conversation_id,
                    TeachingConversation.course_id == actor.course_id,
                    TeachingConversation.curriculum_edition_id == curriculum_edition_id,
                    TeachingTurn.scientific_results_json["__hitl_decisions"][str(interrupt_id)]
                    .as_string().is_not(None),
                )
                .with_for_update().execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            return None
        conversation, turn = row
        decision = HitlEvent.model_validate(
            turn.scientific_results_json["__hitl_decisions"][str(interrupt_id)]
        )
        return await self._replayed_turn(conversation, turn), decision

    async def student_actor_for_resume(
        self,
        *,
        started: StartedTeachingTurn,
        acting_actor: CourseActor,
    ) -> CourseActor:
        row = (
            await self._session.execute(
                select(User, CourseMembership)
                .join(
                    CourseMembership,
                    (CourseMembership.user_id == User.id)
                    & (CourseMembership.course_id == started.conversation.course_id),
                )
                .where(
                    User.id == started.conversation.student_user_id,
                    CourseMembership.status == MembershipStatus.ACTIVE,
                )
            )
        ).one_or_none()
        if row is None:
            raise TeachingConversationConflictError(
                "student membership is no longer active for this teaching thread"
            )
        user, membership = row
        return CourseActor(
            user_id=user.id,
            # Only request attribution uses the acting session. Durable learning
            # evidence remains attributed to the original student user id.
            session_id=acting_actor.session_id,
            course_id=started.conversation.course_id,
            email=user.email,
            display_name=user.display_name,
            system_role=user.system_role,
            course_role=membership.role,
        )

    async def record_interrupt(
        self,
        *,
        started: StartedTeachingTurn,
        payload: HitlInterruptPayload,
        artifacts: HitlArtifacts,
    ) -> None:
        """Persist one pause marker idempotently before yielding control."""

        turn = started.turn
        if turn.status is not TeachingTurnStatus.RUNNING:
            raise TeachingConversationConflictError("turn is no longer interruptible")
        current = turn.validation_json.get("hitl")
        if isinstance(current, dict) and current.get("interrupt_id") == str(payload.interrupt_id):
            return
        turn.task_kind = artifacts.interpretation.task_kind
        turn.teaching_action = artifacts.release.action
        turn.release_level = artifacts.release.release_level
        turn.evidence_packet_json = artifacts.evidence_packet.model_dump(mode="json")
        turn.response_json = None
        from quantum_agent.teaching.state_machine import WORKFLOW_VERSION
        from quantum_agent.versioning import build_evidence_provenance, current_model_calls

        earlier_calls = turn.scientific_results_json.get("__model_calls_before_review", [])
        calls = [*earlier_calls, *current_model_calls()][:128]
        package = started.durable_phase.course_package
        provenance = build_evidence_provenance(
            packet=artifacts.evidence_packet, workflow_version=WORKFLOW_VERSION,
            course_package=package.model_dump(mode="json") if package is not None else None,
        )
        previous_provenance = turn.scientific_results_json.get("__provenance", {})
        segments = previous_provenance.get("execution_segments", [])
        # A deployment may change while a teacher reviews a pause. Retain the
        # code/content version of each execution, instead of relabeling earlier
        # model calls with the version that eventually completes the turn.
        provenance["execution_segments"] = [*segments, dict(provenance)][:16]
        provenance["model_calls"] = calls
        turn.scientific_results_json = {
            **turn.scientific_results_json,
            "results": [item.model_dump(mode="json") for item in artifacts.scientific_results],
            "__model_calls_before_review": calls,
            "__provenance": provenance,
        }
        turn.validation_json = {
            "input_attachment_ids": turn.validation_json.get("input_attachment_ids", []),
            "client_request_id": turn.client_request_id or "",
            "hitl": {
                "interrupt_id": str(payload.interrupt_id),
                "interrupt": payload.model_dump(mode="json"),
                "artifacts": artifacts.model_dump(mode="json"),
                "resolution": None,
            },
        }
        await self._session.flush()
        # Stop the active clock atomically with the durable pause marker.
        # Re-entering this node on resume returns above and cannot re-charge
        # human waiting or close the new execution segment prematurely.
        from quantum_agent.teaching.execution_budget import current_execution_budget

        budget = current_execution_budget()
        if budget is not None:
            await budget.finish("waiting")

    async def record_resolution(
        self,
        *,
        started: StartedTeachingTurn,
        event: HitlEvent,
    ) -> None:
        await self._session.refresh(started.turn, with_for_update=True)
        current = started.turn.validation_json.get("hitl")
        if not isinstance(current, dict) or current.get("interrupt_id") != str(
            event.interrupt.interrupt_id
        ):
            raise TeachingConversationConflictError(
                "durable interrupt marker does not match the resumed checkpoint"
            )
        serialized = (
            event.resolution.model_dump(mode="json") if event.resolution is not None else None
        )
        if current.get("resolution") == serialized:
            return
        if current.get("resolution") is not None:
            raise TeachingConversationConflictError("interrupt already has another decision")
        decisions = dict(started.turn.scientific_results_json.get("__hitl_decisions", {}))
        decisions[str(event.interrupt.interrupt_id)] = event.model_dump(mode="json")
        started.turn.scientific_results_json = {
            **started.turn.scientific_results_json, "__hitl_decisions": decisions,
        }
        started.turn.validation_json = {
            "input_attachment_ids": started.turn.validation_json.get(
                "input_attachment_ids", []
            ),
            "client_request_id": started.turn.client_request_id or "",
            "hitl": {
                **current,
                "resolution": serialized,
            },
        }
        await self._session.flush()

    async def complete_turn(
        self,
        *,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        started: StartedTeachingTurn,
        result: TeachingTurnResult,
        evidence_bundle: EvidenceBundle | None = None,
        hitl_events: list[HitlEvent] | None = None,
        multimodal_evidence: list[ConfirmedEvidence] | None = None,
        perception_trace: list[PerceptionTraceEntry] | None = None,
        learning_native_evidence: list[LearningEvidenceRecord] | None = None,
    ) -> None:
        turn = started.turn
        await self._session.refresh(turn, with_for_update=True)
        if turn.status is TeachingTurnStatus.COMPLETED:
            return
        if turn.status is TeachingTurnStatus.FAILED:
            raise TeachingConversationConflictError("a rejected turn cannot be completed")
        turn.task_kind = result.interpretation.task_kind
        turn.teaching_action = result.release.action
        turn.release_level = result.release.release_level
        turn.status = TeachingTurnStatus.COMPLETED
        turn.evidence_packet_json = result.evidence_packet.model_dump(mode="json")
        turn.response_json = result.response.model_dump(mode="json")
        # PRD V3.0 P1-2: store the full result snapshot and the idempotency
        # metadata in the scientific_results_json column (a flexible JSON
        # dict) so a client_request_id replay can return the stored result
        # without re-running the graph, and so the replay lookup can find
        # the key.  The validation_json column is kept as the clean
        # ValidationReport so the teacher-insights trace-detail endpoint
        # can still ValidationReport.model_validate it.
        from quantum_agent.versioning import build_turn_provenance

        provenance = build_turn_provenance(result)
        previous_provenance = turn.scientific_results_json.get("__provenance")
        if isinstance(previous_provenance, dict):
            segments = previous_provenance.get("execution_segments", [])
            provenance["execution_segments"] = [*segments, dict(provenance)][:16]
        provenance["model_calls"] = [
            *turn.scientific_results_json.get("__model_calls_before_review", []),
            *provenance["model_calls"],
        ][:128]
        turn.scientific_results_json = {
            **turn.scientific_results_json,
            "__provenance": provenance,
            "results": [item.model_dump(mode="json") for item in result.scientific_results],
            "__result_snapshot": result.model_dump(mode="json"),
            "__client_request_id": turn.client_request_id or "",
            "__input_attachment_ids": turn.validation_json.get("input_attachment_ids", []),
        }
        turn.validation_json = result.validation.model_dump(mode="json")
        turn.completed_at = datetime.now(UTC)

        existing_trace = await self._session.scalar(
            select(AgentTrace).where(AgentTrace.teaching_turn_id == turn.id)
        )
        if existing_trace is None:
            self._session.add(
                AgentTrace(
                    teaching_turn_id=turn.id,
                    course_id=actor.course_id,
                    curriculum_edition_id=curriculum_edition_id,
                    student_user_id=actor.user_id,
                    workflow_version=result.workflow_version,
                    steps_json={
                        "provenance": provenance,
                        "steps": [step.model_dump(mode="json") for step in result.trace],
                        **(
                            {"evidence_bundle": evidence_bundle.model_dump(mode="json")}
                            if evidence_bundle is not None
                            else {}
                        ),
                        "diagnosis": result.diagnosis.model_dump(mode="json"),
                        "release": result.release.model_dump(mode="json"),
                        "scientific_results": [
                            item.model_dump(mode="json") for item in result.scientific_results
                        ],
                        "hitl_events": [
                            event.model_dump(mode="json") for event in (hitl_events or [])
                        ],
                        "multimodal_evidence": [
                            item.model_dump(mode="json")
                            for item in (multimodal_evidence or [])
                        ],
                        "perception_trace": [
                            item.model_dump(mode="json") for item in (perception_trace or [])
                        ],
                        **(
                            {"learning_native": result.learning_native.model_dump(mode="json")}
                            if result.learning_native is not None
                            else {}
                        ),
                    },
                    policy_snapshot_json=result.policy.model_dump(mode="json"),
                    model_gateway_status=(
                        "degraded"
                        if result.response.status.value.endswith("degraded")
                        else "completed"
                    ),
                    citation_validation_status=("passed" if result.validation.passed else "failed"),
                )
            )

        concept_id = (
            result.evidence_packet.graph_nodes[0].id if result.evidence_packet.graph_nodes else None
        )
        existing_kinds = set(
            await self._session.scalars(
                select(LearningEvidence.kind).where(LearningEvidence.teaching_turn_id == turn.id)
            )
        )
        if (
            (
                started.turn.student_attempt
                or any(
                    item.admitted_to_diagnosis for item in (perception_trace or [])
                )
            )
            and LearningEvidenceKind.STUDENT_ATTEMPT not in existing_kinds
        ):
            self._session.add(
                LearningEvidence(
                    teaching_turn_id=turn.id,
                    course_id=actor.course_id,
                    curriculum_edition_id=curriculum_edition_id,
                    student_user_id=actor.user_id,
                    concept_candidate_id=concept_id,
                    kind=LearningEvidenceKind.STUDENT_ATTEMPT,
                    observation="Student submitted an attempt for this teaching turn.",
                    mastery_delta=0.0,
                    evidence_json={
                        "task_kind": result.interpretation.task_kind.value,
                        "attempt_present": True,
                        "attachment_ids": [
                            str(item.attachment_id)
                            for item in (perception_trace or [])
                            if item.admitted_to_diagnosis
                        ],
                    },
                )
            )
        if (
            result.diagnosis.status.value == "model_inference"
            and LearningEvidenceKind.DIAGNOSIS_INFERENCE not in existing_kinds
        ):
            self._session.add(
                LearningEvidence(
                    teaching_turn_id=turn.id,
                    course_id=actor.course_id,
                    curriculum_edition_id=curriculum_edition_id,
                    student_user_id=actor.user_id,
                    concept_candidate_id=concept_id,
                    kind=LearningEvidenceKind.DIAGNOSIS_INFERENCE,
                    observation=result.diagnosis.summary,
                    mastery_delta=0.0,
                    evidence_json={
                        "inference_only": True,
                        "likely_misconception": result.diagnosis.likely_misconception,
                        "observation_basis": result.diagnosis.observation_basis,
                    },
                )
            )
        if learning_native_evidence:
            existing_rows = await self._session.execute(
                select(LearningEvidence.kind, LearningEvidence.observation)
                .where(LearningEvidence.teaching_turn_id == turn.id)
                .where(
                    LearningEvidence.kind.in_(
                        [
                            LearningEvidenceKind.COMMITMENT,
                            LearningEvidenceKind.CONFIDENCE,
                            LearningEvidenceKind.TEACH_BACK,
                            LearningEvidenceKind.TRANSFER,
                            LearningEvidenceKind.SOLO,
                            LearningEvidenceKind.SOLO_ATTEMPT,
                            LearningEvidenceKind.RETRIEVAL_PRACTICE,
                        ]
                    )
                )
            )
            existing_native_keys: set[tuple[LearningEvidenceKind, str]] = {
                (kind, obs) for kind, obs in existing_rows.all()
            }
            for record in learning_native_evidence:
                # De-duplicate by (kind, observation) so a replayed turn does
                # not double-count a single commitment or teach-back.
                key: tuple[LearningEvidenceKind, str] = (record.kind, record.observation)
                if key in existing_native_keys:
                    continue
                existing_native_keys.add(key)
                self._session.add(
                    LearningEvidence(
                        teaching_turn_id=turn.id,
                        course_id=actor.course_id,
                        curriculum_edition_id=curriculum_edition_id,
                        student_user_id=actor.user_id,
                        concept_candidate_id=record.concept_candidate_id or concept_id,
                        kind=record.kind,
                        observation=record.observation,
                        mastery_delta=record.mastery_delta,
                        evidence_json=record.evidence_json,
                    )
                )
        await self._session.flush()

    async def load_latest_learning_native(
        self,
        *,
        conversation_id: UUID,
    ) -> dict[str, Any] | None:
        """Return the most recent ``learning_native`` payload for a conversation.

        Used by the tutor graph to restore Solo Mode and the cognitive mirror
        across turns in the same thread.  Returns ``None`` if no completed
        turn has persisted Learning-Native state yet.
        """

        from quantum_agent.db_models import AgentTrace as _AgentTrace

        row = await self._session.scalar(
            select(_AgentTrace)
            .join(TeachingTurn, _AgentTrace.teaching_turn_id == TeachingTurn.id)
            .where(TeachingTurn.conversation_id == conversation_id)
            .order_by(_AgentTrace.created_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        steps = row.steps_json or {}
        native = steps.get("learning_native")
        if not isinstance(native, dict):
            return None
        return native

    async def load_durable_learning_phase(
        self,
        *,
        conversation: TeachingConversation,
    ) -> DurableLearningPhase:
        """Load the durable Learning-Native phase from the conversation row.

        Returns a default ``OPEN`` phase if the conversation has no persisted
        phase yet (first turn in a new thread).
        """

        raw = conversation.learning_phase_json
        if raw is None:
            return DurableLearningPhase()
        if not isinstance(raw, dict):
            raise TeachingConversationConflictError("stored learning phase requires repair")
        try:
            return DurableLearningPhase.model_validate(raw)
        except ValidationError as exc:
            # Resetting malformed Solo state to OPEN would release its answer
            # lock and falsely credit an assisted retry as independent work.
            raise TeachingConversationConflictError(
                "stored learning phase requires repair"
            ) from exc

    async def save_durable_learning_phase(
        self,
        *,
        conversation: TeachingConversation,
        phase: DurableLearningPhase,
    ) -> None:
        """Persist the durable Learning-Native phase on the conversation row."""

        conversation.learning_phase_json = phase.model_dump(mode="json")
        await self._session.flush()

    async def fail_turn(self, started: StartedTeachingTurn, *, failure_code: str) -> None:
        if started.turn.status is TeachingTurnStatus.FAILED:
            if started.turn.failure_code == failure_code[:160]:
                return
            raise TeachingConversationConflictError("turn already failed with another code")
        if started.turn.status is TeachingTurnStatus.COMPLETED:
            raise TeachingConversationConflictError("completed turn cannot be failed")
        started.turn.status = TeachingTurnStatus.FAILED
        started.turn.failure_code = failure_code[:160]
        started.turn.completed_at = datetime.now(UTC)
        await self._session.flush()


__all__ = [
    "LearningEvidenceRecord",
    "StartedTeachingTurn",
    "StartedTeachingTurnRef",
    "TeachingConversationConflictError",
    "TeachingRepository",
]
