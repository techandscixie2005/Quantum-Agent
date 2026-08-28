"""LangGraph StateGraph implementation of the deterministic teaching workflow.

The graph is a behavior-preserving (B1) re-expression of
``TeachingStateMachine.run``: an ordered chain of nodes that read and write the
same ``TutorState`` fields and produce an identical ``TeachingTurnResult``.
Conditional routing, subgraphs, and the Policy Gate interrupt are introduced in
later milestones.
"""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import TEACHING_STAFF_ROLES, CourseActor
from quantum_agent.coding import CodingAgent, RemoteSandbox, SandboxDisabled, SubprocessSandbox
from quantum_agent.db_models import CourseRole, TeachingTurnStatus
from quantum_agent.llm.gateway import ModelGateway
from quantum_agent.multimodal.teaching import (
    UnconfirmedPerceptionError,
    resolve_teaching_attachments,
)
from quantum_agent.science import ScientificToolbox
from quantum_agent.teaching.hitl import (
    HitlAction,
    HitlAuthorizationError,
    HitlConflictError,
    HitlInterruptPayload,
    HitlInterruptResponse,
    HitlNotFoundError,
    HitlRejectedResponse,
    HitlResolution,
    HitlResolutionValidationError,
    HitlResumeRequest,
    TeachingTurnOutcome,
    artifacts_from_state,
    validate_human_response,
)
from quantum_agent.teaching.models import TeachingTurnInput, TeachingTurnResult
from quantum_agent.teaching.repository import (
    StartedTeachingTurn,
    StartedTeachingTurnRef,
    TeachingRepository,
)
from quantum_agent.teaching.state_machine import EvidenceRetriever
from quantum_agent.tutor.nodes import (
    apply_policy_node,
    assemble_result_node,
    diagnose_node,
    generate_response_node,
    hitl_gate_node,
    interpret_node,
    learning_native_node,
    learning_native_pre_node,
    prepare_commitment_gate_node,
    reject_turn_node,
    retrieve_evidence_node,
    scientific_tools_node,
)
from quantum_agent.tutor.state import TutorContext, TutorState

__all__ = ["TutorGraph"]


def _route_after_hitl(
    state: TutorState,
) -> Literal["assemble_result", "reject_turn", "restart"]:
    if state.get("restart_after_confirmation"):
        return "restart"
    events = state.get("hitl_events", [])
    if (
        events
        and events[-1].resolution is not None
        and events[-1].resolution.action is HitlAction.REJECT
    ):
        return "reject_turn"
    return "assemble_result"


def _route_after_learning_native_pre(
    state: TutorState,
) -> Literal["prepare_commitment_gate", "retrieve_evidence"]:
    """PRD V3.0 Axiom 1: when the commitment gate withholds the answer, skip
    retrieval/diagnosis/scientific-tools/generation and go straight to the
    deterministic gate response.  Otherwise run the full evidence-grounded
    workflow.
    """
    if state.get("answer_withheld_by_gate"):
        return "prepare_commitment_gate"
    return "retrieve_evidence"


def _route_after_learning_native(
    state: TutorState,
) -> Literal["assemble_result", "hitl_gate"]:
    """When the gate withheld the answer, skip HITL (there is no LLM output to
    review) and assemble the result directly.  Otherwise run the HITL gate.
    """
    if state.get("answer_withheld_by_gate"):
        return "assemble_result"
    return "hitl_gate"


class TutorGraph:
    """Compiled teaching graph with runtime dependency injection."""

    def __init__(
        self,
        *,
        evidence_retriever: EvidenceRetriever,
        model_gateway: ModelGateway | None,
        scientific_toolbox: ScientificToolbox | None = None,
        checkpointer: BaseCheckpointSaver[str] | None = None,
        use_specialist_agents: bool = False,
        enable_hitl: bool = False,
        coding_agent: CodingAgent | None = None,
        sandbox: SubprocessSandbox | RemoteSandbox | SandboxDisabled | None = None,
    ) -> None:
        if enable_hitl and checkpointer is None:
            raise ValueError("HITL requires a durable or in-memory LangGraph checkpointer")
        self._evidence_retriever = evidence_retriever
        self._model_gateway = model_gateway
        self._scientific_toolbox = scientific_toolbox or ScientificToolbox()
        self._use_specialist_agents = use_specialist_agents
        self._enable_hitl = enable_hitl
        self._has_checkpointer = checkpointer is not None
        self._coding_agent = coding_agent
        self._sandbox = sandbox

        builder = StateGraph(TutorState, context_schema=TutorContext)
        builder.add_node("interpret", interpret_node)
        # PRD V3.0 Axiom 1 ("Learner generates before AI completes"): the
        # commitment gate runs BEFORE retrieval so the student must commit a
        # prediction / first step before any evidence-grounded explanation is
        # produced.  ``learning_native_pre_node`` uses the deterministic
        # ``commitment_eligibility`` policy (mode + task kind + message +
        # has-attempt) to decide whether the gate fires; it does not need the
        # retrieved evidence.  When the gate fires, the graph skips
        # retrieval/diagnosis/scientific-tools/generation and goes straight to
        # ``prepare_commitment_gate`` which emits a deterministic elicitation
        # response with zero claims.  When the gate does not fire, the full
        # evidence-grounded workflow runs.
        builder.add_node("learning_native_pre", learning_native_pre_node)
        builder.add_node("prepare_commitment_gate", prepare_commitment_gate_node)
        builder.add_node("retrieve_evidence", retrieve_evidence_node)
        builder.add_node("diagnose", diagnose_node)
        builder.add_node("apply_policy", apply_policy_node)
        builder.add_node("scientific_tools", scientific_tools_node)
        builder.add_node("generate_response", generate_response_node)
        builder.add_node("learning_native", learning_native_node)
        builder.add_node("hitl_gate", hitl_gate_node)
        builder.add_node("reject_turn", reject_turn_node)
        builder.add_node("assemble_result", assemble_result_node)

        builder.add_edge(START, "interpret")
        builder.add_edge("interpret", "learning_native_pre")
        builder.add_conditional_edges(
            "learning_native_pre",
            _route_after_learning_native_pre,
            {
                "prepare_commitment_gate": "prepare_commitment_gate",
                "retrieve_evidence": "retrieve_evidence",
            },
        )
        # Gate-fires branch: skip retrieval/diagnosis/scientific-tools/generation;
        # the gate node emits the deterministic elicitation response and all
        # remaining trace steps, then the post-generation Learning-Native node
        # assembles the commitment + cognitive mirror before assembly.
        builder.add_edge("prepare_commitment_gate", "learning_native")
        # Non-gate branch: full evidence-grounded workflow.
        builder.add_edge("retrieve_evidence", "diagnose")
        builder.add_edge("diagnose", "apply_policy")
        builder.add_edge("apply_policy", "scientific_tools")
        builder.add_edge("scientific_tools", "generate_response")
        builder.add_edge("generate_response", "learning_native")
        builder.add_conditional_edges(
            "learning_native",
            _route_after_learning_native,
            {
                "assemble_result": "assemble_result",
                "hitl_gate": "hitl_gate",
            },
        )
        builder.add_conditional_edges(
            "hitl_gate",
            _route_after_hitl,
            {
                "assemble_result": "assemble_result",
                "reject_turn": "reject_turn",
                "restart": "interpret",
            },
        )
        builder.add_edge("reject_turn", END)
        builder.add_edge("assemble_result", END)

        self._graph = builder.compile(checkpointer=checkpointer)

    async def run(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        request: TeachingTurnInput,
        model_gateway_override: ModelGateway | None = None,
    ) -> TeachingTurnResult | HitlInterruptResponse:
        resolved = await resolve_teaching_attachments(
            session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            request=request,
        )
        if resolved.has_unconfirmed_evidence and not self._enable_hitl:
            raise UnconfirmedPerceptionError(
                "ambiguous attachment transcription requires explicit confirmation"
            )
        repository = TeachingRepository(session)
        started = await repository.start_turn(
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            request=request,
        )

        if started.idempotent_replay:
            # PRD V3.0 P1-2: a client_request_id replay may target either a
            # RUNNING turn (HITL interrupt in flight) or a COMPLETED turn
            # (the original response was persisted but the browser lost the
            # response and retried).  For a COMPLETED turn, return the
            # stored TeachingTurnResult so the retry cannot create a
            # duplicate AgentTrace or LearningEvidence rows.
            if started.turn.status is TeachingTurnStatus.COMPLETED:
                return await self._replay_completed_turn(
                    session=session,
                    actor=actor,
                    curriculum_edition_id=curriculum_edition_id,
                    started=started,
                )
            try:
                return await self._inspect_interrupt(
                    session=session,
                    actor=actor,
                    curriculum_edition_id=curriculum_edition_id,
                    conversation_id=started.conversation.id,
                )
            except HitlNotFoundError as error:
                raise HitlConflictError(
                    "a running SQL turn has no resumable LangGraph interrupt"
                ) from error

        initial_state: TutorState = {
            "request": resolved.request,
            "scientific_results": [],
            "trace": [],
            "multimodal_evidence": list(resolved.multimodal_evidence),
            "perception_trace": list(resolved.perception_trace),
            "started_turn_ref": StartedTeachingTurnRef.from_started(started),
            "hitl_events": [],
            "restart_after_confirmation": False,
            "hitl_rejection": None,
            "learning_native_evidence": [],
            "solo_assistance_locked": False,
            "learning_native_pre_decision": None,
            "answer_withheld_by_gate": False,
            "code_artifact": None,
            "result": None,
        }
        context = self._context(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            started=started,
            model_gateway_override=model_gateway_override,
        )
        config = self._config(started.conversation.id)

        # The graph returns the final state keyed by node; extract the result.
        outcome = await self._graph.ainvoke(
            initial_state,
            config,
            context=context,
            durability="sync" if self._has_checkpointer else None,
        )
        final_state = cast(TutorState, outcome)
        if final_state.get("result") is not None:
            return TeachingTurnResult.model_validate(final_state["result"])
        return await self._inspect_interrupt(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            conversation_id=started.conversation.id,
        )

    def _context(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        started: StartedTeachingTurn,
        model_gateway_override: ModelGateway | None = None,
    ) -> TutorContext:
        return TutorContext(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            retriever=self._evidence_retriever,
            model_gateway=model_gateway_override or self._model_gateway,
            scientific_toolbox=self._scientific_toolbox,
            started_turn=started,
            use_specialist_agents=self._use_specialist_agents,
            enable_hitl=self._enable_hitl,
            coding_agent=self._coding_agent,
            sandbox=self._sandbox,
        )

    @staticmethod
    def _config(conversation_id: UUID) -> RunnableConfig:
        return {"configurable": {"thread_id": str(conversation_id)}}

    async def _checkpoint_interrupt(
        self,
        conversation_id: UUID,
    ) -> tuple[HitlInterruptPayload, TutorState]:
        snapshot = await self._graph.aget_state(self._config(conversation_id))
        if not snapshot.interrupts:
            raise HitlNotFoundError("teaching thread has no current HITL interrupt")
        payload = HitlInterruptPayload.model_validate(snapshot.interrupts[-1].value)
        state = cast(TutorState, snapshot.values)
        if payload.conversation_id != conversation_id:
            raise HitlConflictError("checkpoint interrupt belongs to another thread")
        return payload, state

    @staticmethod
    def _reference(state: TutorState) -> StartedTeachingTurnRef:
        raw_reference = state.get("started_turn_ref")
        if raw_reference is None:
            raise HitlConflictError("checkpoint is missing the durable turn reference")
        return StartedTeachingTurnRef.model_validate(raw_reference)

    @staticmethod
    def _authorize_inspection(
        *,
        actor: CourseActor,
        reference: StartedTeachingTurnRef,
    ) -> None:
        if actor.course_role is CourseRole.STUDENT:
            if actor.user_id != reference.student_user_id:
                raise HitlAuthorizationError("student does not own this teaching thread")
            return
        if actor.course_role not in TEACHING_STAFF_ROLES:
            raise HitlAuthorizationError("actor cannot inspect HITL teaching state")

    @staticmethod
    def _authorize_resolution(
        *,
        actor: CourseActor,
        reference: StartedTeachingTurnRef,
        payload: HitlInterruptPayload,
        request: HitlResumeRequest,
    ) -> None:
        TutorGraph._authorize_inspection(actor=actor, reference=reference)
        if actor.course_role is CourseRole.STUDENT:
            if request.action is not HitlAction.CONFIRM_TRANSCRIPTION:
                raise HitlAuthorizationError(
                    "students may only confirm their own ambiguous transcription"
                )
            if request.action not in payload.student_allowed_actions:
                raise HitlAuthorizationError("this interrupt requires teaching-staff review")
            return
        if request.action not in payload.staff_allowed_actions:
            raise HitlAuthorizationError("action is not available to teaching staff")

    async def _replay_completed_turn(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        started: StartedTeachingTurn,
    ) -> TeachingTurnResult:
        """Return the stored TeachingTurnResult for a completed-turn replay.

        PRD V3.0 P1-2: when a browser retries a turn whose ``client_request_id``
        matches an already-completed turn, we return the persisted result
        snapshot instead of re-running the graph.  This guarantees a retry
        cannot create duplicate AgentTrace / LearningEvidence rows or
        duplicate phase transitions.
        """

        snapshot = started.turn.scientific_results_json.get("__result_snapshot")
        if not isinstance(snapshot, dict):
            raise HitlConflictError(
                "completed turn replay is missing its result snapshot; "
                "the turn predates the idempotency-key feature"
            )
        result = TeachingTurnResult.model_validate(snapshot)
        # Re-authorise the replay against the current actor.
        if (
            started.conversation.student_user_id != actor.user_id
            or started.conversation.course_id != actor.course_id
            or curriculum_edition_id != started.conversation.curriculum_edition_id
        ):
            raise HitlConflictError("replay actor does not own the completed turn")
        return result

    async def _inspect_interrupt(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        conversation_id: UUID,
    ) -> HitlInterruptResponse:
        payload, state = await self._checkpoint_interrupt(conversation_id)
        reference = self._reference(state)
        if reference.conversation_id != conversation_id:
            raise HitlConflictError("checkpoint turn reference belongs to another thread")
        self._authorize_inspection(actor=actor, reference=reference)
        await TeachingRepository(session).load_started_turn(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            reference=reference,
        )
        return HitlInterruptResponse(
            conversation_id=reference.conversation_id,
            turn_id=reference.turn_id,
            interrupt=payload,
            artifacts=artifacts_from_state(dict(state)),
        )

    async def inspect_interrupt(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        conversation_id: UUID,
    ) -> HitlInterruptResponse:
        if not self._enable_hitl:
            raise HitlNotFoundError("HITL is disabled for this workflow")
        return await self._inspect_interrupt(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            conversation_id=conversation_id,
        )

    async def resume(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        conversation_id: UUID,
        request: HitlResumeRequest,
        model_gateway_override: ModelGateway | None = None,
    ) -> TeachingTurnResult | TeachingTurnOutcome:
        if not self._enable_hitl:
            raise HitlNotFoundError("HITL is disabled for this workflow")
        payload, state = await self._checkpoint_interrupt(conversation_id)
        reference = self._reference(state)
        self._authorize_resolution(
            actor=actor,
            reference=reference,
            payload=payload,
            request=request,
        )
        if request.edited_response is not None:
            validation = validate_human_response(
                response=request.edited_response,
                packet=state["evidence_packet"],
                scientific_results=list(state.get("scientific_results", [])),
                release=state["release"],
            )
            if not validation.passed:
                raise HitlResolutionValidationError(
                    "reviewer-authored response violates the policy or evidence envelope: "
                    + ", ".join(validation.warnings)
                )

        repository = TeachingRepository(session)
        started = await repository.load_started_turn(
            course_id=actor.course_id,
            curriculum_edition_id=curriculum_edition_id,
            reference=reference,
        )
        student_actor = await repository.student_actor_for_resume(
            started=started,
            acting_actor=actor,
        )
        resolution = HitlResolution.authenticated(
            payload=payload,
            request=request,
            actor_user_id=actor.user_id,
            actor_role=actor.course_role,
        )
        context = self._context(
            session=session,
            actor=student_actor,
            curriculum_edition_id=curriculum_edition_id,
            started=started,
            model_gateway_override=model_gateway_override,
        )
        outcome = await self._graph.ainvoke(
            Command(resume=resolution.model_dump(mode="json")),
            self._config(conversation_id),
            context=context,
            durability="sync" if self._has_checkpointer else None,
        )
        final_state = cast(TutorState, outcome)
        if final_state.get("result") is not None:
            return TeachingTurnResult.model_validate(final_state["result"])
        if final_state.get("hitl_rejection") is not None:
            return HitlRejectedResponse.model_validate(final_state["hitl_rejection"])
        # Confirmation can expose another independently reviewable reason. Keep
        # the same thread and return the new typed pause rather than guessing.
        return await self._inspect_interrupt(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            conversation_id=conversation_id,
        )
