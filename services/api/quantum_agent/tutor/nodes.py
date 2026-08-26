"""LangGraph node implementations for the teaching workflow.

Each node reads from and writes to ``TutorState``. Nodes are thin, deterministic
wrappers around the shared module-level functions in ``state_machine`` so the
state machine (B0) and the graph (B1) exercise identical logic.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import TypeAdapter

from quantum_agent.db_models import AnswerReleaseLevel, LearningEvidenceKind
from quantum_agent.knowledge.retrieval import RetrievalScope
from quantum_agent.multimodal.contracts import ConfirmedEvidence
from quantum_agent.multimodal.teaching import (
    PerceptionTraceEntry,
    confirm_checkpoint_perception,
    derive_scientific_request,
)
from quantum_agent.science import ScientificVerificationStatus
from quantum_agent.teaching.agents import DiagnosisAgent, DiagnosisInput, EvidenceAgent
from quantum_agent.teaching.hitl import (
    HitlAction,
    HitlEvent,
    HitlRejectedResponse,
    HitlResolution,
    HitlResolutionValidationError,
    artifacts_from_state,
    build_interrupt_payload,
    determine_hitl_reasons,
    validate_human_response,
)
from quantum_agent.teaching.learning_native import (
    LearningNativeEvidence,
    LearningNativePolicy,
    propose_commitment,
    propose_teach_back_analysis,
    propose_transfer_task,
)
from quantum_agent.teaching.models import (
    CognitiveCommitment,
    CommitmentGateDecision,
    DurableLearningPhase,
    LearningPhase,
    LearningPolicyAction,
    SoloMode,
    SoloModeStatus,
    StudentSnapshot,
    TeachBackAnalysis,
    TransferTask,
    TransferType,
    ValidationReport,
    WorkflowStep,
    WorkflowStepName,
    WorkflowStepStatus,
)
from quantum_agent.teaching.policy import AnswerPolicyRepository, AnswerReleaseEngine
from quantum_agent.teaching.repository import (
    LearningEvidenceRecord,
    TeachingRepository,
)
from quantum_agent.teaching.state_machine import (
    WORKFLOW_VERSION,
    diagnose_turn,
    draft_response,
    interpret_turn,
)

if TYPE_CHECKING:
    from quantum_agent.tutor.state import TutorContext, TutorState


_MULTIMODAL_EVIDENCE_ADAPTER: TypeAdapter[ConfirmedEvidence] = TypeAdapter(
    ConfirmedEvidence
)


async def interpret_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    request = state["request"]
    model_gateway = runtime.context.model_gateway
    interpretation, degraded = await interpret_turn(
        request=request,
        model_gateway=model_gateway,
    )
    trace = list(state.get("trace", []))
    perception_trace = [
        PerceptionTraceEntry.model_validate(item)
        for item in state.get("perception_trace", [])
    ]
    refs = ",".join(
        f"{item.attachment_id}/{item.extraction_id}" for item in perception_trace
    )
    perception_detail = ""
    if perception_trace:
        admitted = sum(item.admitted_to_diagnosis for item in perception_trace)
        perception_detail = (
            f" Perception admitted {admitted}/{len(perception_trace)} scoped extraction(s); "
            f"refs={refs}."
        )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.CLASSIFY_TASK,
            status=(WorkflowStepStatus.DEGRADED if degraded else WorkflowStepStatus.COMPLETED),
            detail=(
                "Task class constrained by the selected product mode."
                + perception_detail
            )[:500],
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.IDENTIFY_CONCEPTS,
            status=WorkflowStepStatus.COMPLETED,
            detail=(
                f"Identified {len(interpretation.relevant_concepts)} query concepts; "
                "they are retrieval hints, not approved knowledge."
            ),
        )
    )
    return {
        "interpretation": interpretation,
        "interpretation_degraded": degraded,
        "trace": trace,
    }


async def retrieve_evidence_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    request = state["request"]
    interpretation = state["interpretation"]
    retriever = runtime.context.retriever
    actor = runtime.context.actor
    curriculum_edition_id = runtime.context.curriculum_edition_id

    retrieval_query = " ".join([request.message, *interpretation.relevant_concepts])[:5000]
    scope = RetrievalScope(
        course_id=actor.course_id,
        curriculum_edition_id=curriculum_edition_id,
    )
    if runtime.context.use_specialist_agents:
        bundle = await EvidenceAgent(retriever).gather(
            scope=scope,
            query=request.message,
            concept_hints=interpretation.relevant_concepts,
        )
        packet = bundle.to_evidence_packet()
    else:
        packet = await retriever.retrieve(scope, retrieval_query)
        bundle = None
    trace = list(state.get("trace", []))
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.RETRIEVE_EVIDENCE,
            status=(
                WorkflowStepStatus.DEGRADED
                if (packet.degraded_channels or packet.warnings)
                else WorkflowStepStatus.COMPLETED
            ),
            detail=(
                f"Retrieved {len(packet.evidence)} authoritative evidence items; "
                f"coverage={packet.coverage.value}."
            ),
        )
    )
    update: dict[str, Any] = {"evidence_packet": packet, "trace": trace}
    if bundle is not None:
        update["evidence_bundle"] = bundle
    return update


async def diagnose_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    request = state["request"]
    model_gateway = runtime.context.model_gateway
    if runtime.context.use_specialist_agents:
        diagnosis, degraded = await DiagnosisAgent(model_gateway).diagnose(
            diagnosis_input=DiagnosisInput(
                request=request,
                evidence_bundle=state["evidence_bundle"],
                student_snapshot=StudentSnapshot(
                    prior_attempt_count=runtime.context.started_turn.prior_attempts,
                    recent_no_progress_count=(
                        runtime.context.started_turn.recent_no_progress_count
                    ),
                ),
            )
        )
    else:
        diagnosis, degraded = await diagnose_turn(
            request=request,
            packet=state["evidence_packet"],
            model_gateway=model_gateway,
        )
    trace = list(state.get("trace", []))
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.DIAGNOSE_PROGRESS,
            status=(WorkflowStepStatus.DEGRADED if degraded else WorkflowStepStatus.COMPLETED),
            detail=f"Diagnosis is explicitly labeled {diagnosis.status.value}.",
        )
    )
    return {"diagnosis": diagnosis, "diagnosis_degraded": degraded, "trace": trace}


async def apply_policy_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    session = runtime.context.session
    actor = runtime.context.actor
    curriculum_edition_id = runtime.context.curriculum_edition_id
    request = state["request"]
    interpretation = state["interpretation"]
    packet = state["evidence_packet"]
    started = runtime.context.started_turn

    policy = await AnswerPolicyRepository(session).get_active(
        course_id=actor.course_id,
        curriculum_edition_id=curriculum_edition_id,
        mode=request.mode,
    )
    release = AnswerReleaseEngine.decide(
        mode=request.mode,
        task_kind=interpretation.task_kind,
        policy=policy,
        prior_attempts=started.prior_attempts,
        has_current_attempt=request.student_attempt is not None,
        coverage=packet.coverage,
        message=request.message,
    )
    trace = list(state.get("trace", []))
    trace.extend(
        [
            WorkflowStep(
                name=WorkflowStepName.CHOOSE_TEACHING_ACTION,
                status=WorkflowStepStatus.COMPLETED,
                detail=f"Backend selected action {release.action.value}.",
            ),
            WorkflowStep(
                name=WorkflowStepName.APPLY_ANSWER_POLICY,
                status=WorkflowStepStatus.COMPLETED,
                detail=(
                    f"Backend policy released {release.release_level.value}; "
                    f"reason={release.reason_code}."
                ),
            ),
        ]
    )
    return {"policy": policy, "release": release, "trace": trace}


async def scientific_tools_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    request = state["request"]
    release = state["release"]
    toolbox = runtime.context.scientific_toolbox
    scientific_results = list(state.get("scientific_results", []))

    tool_allowed = release.release_level in {
        AnswerReleaseLevel.SCAFFOLD,
        AnswerReleaseLevel.FULL_EXPLANATION,
        AnswerReleaseLevel.FULL_SOLUTION,
    }
    if request.scientific_request is None:
        has_visual_derivation = any(
            item.evidence_type == "visual" and item.admitted_to_diagnosis
            for item in state.get("perception_trace", [])
        )
        tool_step = WorkflowStep(
            name=WorkflowStepName.RUN_SCIENTIFIC_TOOLS,
            status=WorkflowStepStatus.SKIPPED,
            detail=(
                "No safely normalized adjacent equality was available; no deterministic "
                "verifier was run."
                if has_visual_derivation
                else "No validated scientific-tool request was supplied; no deterministic "
                "verifier was run."
            ),
        )
    elif not tool_allowed:
        tool_step = WorkflowStep(
            name=WorkflowStepName.RUN_SCIENTIFIC_TOOLS,
            status=WorkflowStepStatus.SKIPPED,
            detail="Backend answer policy withheld the requested tool result.",
        )
    else:
        tool_result = await asyncio.to_thread(
            toolbox.verify,
            request.scientific_request,
        )
        scientific_results.append(tool_result)
        tool_step = WorkflowStep(
            name=WorkflowStepName.RUN_SCIENTIFIC_TOOLS,
            status=(
                WorkflowStepStatus.DEGRADED
                if tool_result.status is ScientificVerificationStatus.INCONCLUSIVE
                else WorkflowStepStatus.COMPLETED
            ),
            detail=(
                f"{tool_result.method.value} verification completed with "
                f"status={tool_result.status.value}."
            ),
        )
    trace = list(state.get("trace", []))
    trace.append(tool_step)
    return {"scientific_results": scientific_results, "trace": trace}


async def learning_native_pre_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    """Run the Learning-Native commitment gate BEFORE answer generation.

    This is the PRD V3.0 Axiom 1 enforcement point.  When the gate is
    enforced (``ATTEMPT_REQUIRED``) and the student has not submitted an
    accepted commitment, we set ``answer_withheld_by_gate=True`` so the
    downstream ``generate_response_node`` skips the LLM call entirely and
    produces a deterministic "elicit a commitment first" response.  The
    LLM only proposes the commitment prompt; code decides whether to
    withhold the answer.

    PRD V3.0 P0-2: this node also enforces the durable Learning Phase.  When
    the conversation is in ``SOLO_ACTIVE``, normal Ask AI requests are
    blocked BEFORE the LLM is called — the student must submit a solo
    attempt or explicitly exit Solo.  Refresh / new tab / retry cannot
    escape the lock because the phase is persisted on the conversation.
    """

    request = state["request"]
    release = state["release"]
    model_gateway = runtime.context.model_gateway
    submission = request.learning_native
    release_is_question_only = release.release_level is AnswerReleaseLevel.QUESTION_ONLY
    # When the course evidence is not found, the commitment gate does not
    # fire: there is nothing to commit to.  The tutor will surface the
    # insufficient-evidence response instead.
    evidence_not_found = release.reason_code == "course_evidence_not_found"

    # PRD V3.0 P0-2: load the durable Learning Phase.  Solo Mode is
    # server-authoritative and restored BEFORE generation, so a normal Ask
    # AI request during Solo is blocked here rather than after the LLM
    # has already written an answer.
    durable_phase = runtime.context.started_turn.durable_phase
    solo_active = durable_phase.phase is LearningPhase.SOLO_ACTIVE
    solo_submission = (
        submission is not None
        and (submission.solo_attempt is not None or submission.transfer_attempt is not None)
    )
    solo_exit_requested = submission is not None and submission.request_solo_exit

    if solo_active and not solo_submission and not solo_exit_requested:
        # The student is in Solo Mode but is asking for AI help (not
        # submitting a solo attempt or exiting Solo).  Block the LLM call
        # and return a deterministic "Solo Mode active" response.
        solo_commitment = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.PROCEED,
            attempt_required=False,
            candidate_prompt="",
            reason_summary=(
                "Solo Mode 激活中：AI 辅助暂时不可用。请独立完成迁移任务，"
                "或点击“退出 Solo”按钮（将记录为 SOLO_ABORTED）。"
            ),
            accepted=True,
        )
        solo_pre_decision: dict[str, Any] = {
            "commitment": solo_commitment.model_dump(mode="json"),
            "learning_action": LearningPolicyAction.ENTER_SOLO.value,
            "withhold_answer": True,
            "commitment_evidence": [],
            "solo_blocked": True,
        }
        return {
            "learning_native_pre_decision": solo_pre_decision,
            "answer_withheld_by_gate": True,
            "learning_native_evidence": [],
            "solo_assistance_locked": True,
        }

    commitment_proposal = await propose_commitment(
        message=request.message,
        release_is_question_only=release_is_question_only and not evidence_not_found,
        model_gateway=model_gateway,
    )
    policy = LearningNativePolicy()
    # PRD V3.0 Axiom 1: a trivially short attempt (e.g. "a") does NOT satisfy
    # the commitment gate.  Use the deterministic meaningfulness check so the
    # gate cannot be bypassed by a one-character student_attempt.
    request_has_attempt = LearningNativePolicy.attempt_is_meaningful(request.student_attempt)
    # When evidence is not found, bypass the gate so the tutor can surface the
    # insufficient-evidence response.  The gate is only meaningful when there
    # is course evidence to withhold.
    if evidence_not_found:
        commitment, learning_action, withhold, commitment_evidence = (
            CognitiveCommitment(
                gate_decision=CommitmentGateDecision.PROCEED,
                attempt_required=False,
                candidate_prompt="",
                reason_summary="课程证据不足，承诺门未激活。",
                accepted=True,
            ),
            LearningPolicyAction.GIVE_CUE,
            False,
            list[LearningNativeEvidence](),
        )
    else:
        commitment, learning_action, withhold, commitment_evidence = policy.decide_pre_generation(
            request_has_attempt=request_has_attempt,
            release_is_question_only=release_is_question_only,
            proposal=commitment_proposal,
            submission=submission.commitment if submission is not None else None,
            submission_confidence=submission.confidence if submission is not None else None,
        )

    # Stash the pre-decision so the post node can assemble the final state
    # without re-running the commitment logic.
    pre_decision: dict[str, Any] = {
        "commitment": commitment.model_dump(mode="json"),
        "learning_action": (
            learning_action.value if learning_action is not None else None
        ),
        "withhold_answer": withhold,
        "commitment_evidence": [
            {
                "kind": item.kind.value,
                "observation": item.observation,
                "evidence_json": item.evidence_json,
            }
            for item in commitment_evidence
        ],
    }
    return {
        "learning_native_pre_decision": pre_decision,
        "answer_withheld_by_gate": withhold,
        "learning_native_evidence": pre_decision["commitment_evidence"],
    }


async def generate_response_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    """Generate the tutor response, or withhold it when the commitment gate fires.

    When ``answer_withheld_by_gate`` is True (the Learning-Native pre-node
    enforced the commitment gate), we skip the LLM call and produce a
    deterministic elicitation response.  This is the PRD V3.0 Axiom 1
    guarantee: the LLM never writes an explanation while the commitment
    gate is still open.
    """

    trace = list(state.get("trace", []))

    if state.get("answer_withheld_by_gate"):
        # The commitment gate withheld the answer.  Produce a deterministic
        # elicitation response with zero claims; the frontend renders the
        # CommitmentCard from ``learning_native.commitment``.
        from quantum_agent.db_models import AnswerReleaseLevel
        from quantum_agent.teaching.models import ResponseStatus, TeachingResponse
        from quantum_agent.teaching.state_machine import _next_question, _orientation

        request = state["request"]
        pre_decision_raw = state.get("learning_native_pre_decision") or {}
        pre_decision: dict[str, Any] = (
            pre_decision_raw if isinstance(pre_decision_raw, dict) else {}
        )
        commitment_data_raw = pre_decision.get("commitment") or {}
        commitment_data: dict[str, Any] = (
            commitment_data_raw if isinstance(commitment_data_raw, dict) else {}
        )
        candidate_prompt = str(commitment_data.get("candidate_prompt") or "")
        reason_summary = str(commitment_data.get("reason_summary") or "")
        solo_blocked = bool(pre_decision.get("solo_blocked"))
        question_level = AnswerReleaseLevel.QUESTION_ONLY
        if solo_blocked:
            orientation_text = reason_summary or candidate_prompt or _orientation(question_level)
            next_question_text = "请独立完成当前的迁移任务；提交后系统会确定性验证你的答案。"
            limitation_text = (
                "Solo Mode active: AI assistance is blocked until the student "
                "submits an independent transfer attempt or explicitly exits Solo."
            )
            generate_detail = (
                "Solo Mode blocked the LLM answer; the student must submit an "
                "independent transfer attempt before AI assistance resumes."
            )
            warning_code = "answer_blocked_by_solo_mode"
        else:
            orientation_text = (
                candidate_prompt or reason_summary or _orientation(question_level)
            )
            next_question_text = (
                candidate_prompt or _next_question(request.mode, question_level)
            )
            limitation_text = (
                "Commitment gate active: the AI explanation is withheld until "
                "the student submits a cognitive commitment."
            )
            generate_detail = (
                "Commitment gate withheld the LLM answer; the AI elicits a "
                "prediction / first step / physical reason before any "
                "explanation is released."
            )
            warning_code = "answer_withheld_by_commitment_gate"
        withheld_response = TeachingResponse(
            status=ResponseStatus.GROUNDED,
            orientation=orientation_text[:1200],
            claims=[],
            next_question=next_question_text[:1000],
            limitations=[limitation_text],
        )
        withheld_validation = ValidationReport(
            passed=True,
            citation_ids_valid=True,
            literal_course_claims_valid=True,
            scientific_references_valid=True,
            warnings=[warning_code],
        )
        trace.append(
            WorkflowStep(
                name=WorkflowStepName.GENERATE_RESPONSE,
                status=WorkflowStepStatus.SKIPPED,
                detail=generate_detail,
            )
        )
        trace.append(
            WorkflowStep(
                name=WorkflowStepName.VALIDATE_RESPONSE,
                status=WorkflowStepStatus.COMPLETED,
                detail="No claims emitted; validation is trivially satisfied.",
            )
        )
        trace.append(
            WorkflowStep(
                name=WorkflowStepName.RECORD_LEARNING_EVIDENCE,
                status=WorkflowStepStatus.COMPLETED,
                detail="Commitment-gate evidence persisted; zero unverified mastery adjustment.",
            )
        )
        return {
            "response": withheld_response,
            "validation": withheld_validation,
            "generation_degraded": False,
            "trace": trace,
        }

    request = state["request"]
    packet = state["evidence_packet"]
    diagnosis = state["diagnosis"]
    release_level = state["release"].release_level
    scientific_results = state["scientific_results"]
    model_gateway = runtime.context.model_gateway
    response, validation, degraded = await draft_response(
        request=request,
        packet=packet,
        diagnosis=diagnosis,
        release_level=release_level,
        scientific_results=scientific_results,
        model_gateway=model_gateway,
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.GENERATE_RESPONSE,
            status=(WorkflowStepStatus.DEGRADED if degraded else WorkflowStepStatus.COMPLETED),
            detail=(
                "Generated within the release envelope."
                if not degraded
                else "Used the exact-evidence fallback."
            ),
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.VALIDATE_RESPONSE,
            status=(
                WorkflowStepStatus.COMPLETED if validation.passed else WorkflowStepStatus.FAILED
            ),
            detail="Citation ids, literal spans, and tool references were checked.",
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.RECORD_LEARNING_EVIDENCE,
            status=WorkflowStepStatus.COMPLETED,
            detail="Persisted observations with zero unverified mastery adjustment.",
        )
    )
    return {
        "response": response,
        "validation": validation,
        "generation_degraded": degraded,
        "trace": trace,
    }


async def hitl_gate_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    """Persist and pause a fully inspectable turn when deterministic rules fire."""

    if not runtime.context.enable_hitl:
        return {"restart_after_confirmation": False}

    reasons = determine_hitl_reasons(
        request=state["request"],
        packet=state["evidence_packet"],
        bundle=state.get("evidence_bundle"),
        diagnosis=state["diagnosis"],
        scientific_results=list(state.get("scientific_results", [])),
        recent_no_progress_count=(runtime.context.started_turn.recent_no_progress_count),
        state=dict(state),
    )
    resolved_reasons = {
        reason
        for event in state.get("hitl_events", [])
        if event.resolution is not None
        for reason in event.interrupt.reasons
    }
    reasons = tuple(reason for reason in reasons if reason not in resolved_reasons)
    if not reasons:
        return {"restart_after_confirmation": False}

    started = runtime.context.started_turn
    payload = build_interrupt_payload(
        conversation_id=started.conversation.id,
        turn_id=started.turn.id,
        reasons=reasons,
    )
    artifacts = artifacts_from_state(dict(state))
    repository = TeachingRepository(runtime.context.session)
    await repository.record_interrupt(
        started=started,
        payload=payload,
        artifacts=artifacts,
    )
    # The durable SQL marker is committed before control is yielded. This call
    # is deliberately idempotent because LangGraph re-enters this node on resume.
    await runtime.context.session.commit()

    raw_resolution = interrupt(payload.model_dump(mode="json"))
    resolution = HitlResolution.model_validate(raw_resolution)
    if resolution.interrupt_id != payload.interrupt_id:
        raise HitlResolutionValidationError("resume command does not match the current interrupt")
    event = HitlEvent(interrupt=payload, resolution=resolution)
    await repository.record_resolution(started=started, event=event)
    await runtime.context.session.commit()

    update: dict[str, Any] = {
        "hitl_events": [*state.get("hitl_events", []), event],
        "restart_after_confirmation": False,
    }
    if resolution.action in {HitlAction.EDIT, HitlAction.TAKE_OVER}:
        assert resolution.edited_response is not None  # validated by HitlResolution
        validation = validate_human_response(
            response=resolution.edited_response,
            packet=state["evidence_packet"],
            scientific_results=list(state.get("scientific_results", [])),
            release=state["release"],
        )
        if not validation.passed:
            raise HitlResolutionValidationError(
                "reviewer-authored response violates the policy or evidence envelope: "
                + ", ".join(validation.warnings)
            )
        trace = list(state["trace"])
        for index, step in enumerate(trace):
            if step.name is WorkflowStepName.GENERATE_RESPONSE:
                trace[index] = step.model_copy(
                    update={
                        "detail": ("Teaching staff supplied a policy-bounded response during HITL.")
                    }
                )
            elif step.name is WorkflowStepName.VALIDATE_RESPONSE:
                trace[index] = step.model_copy(
                    update={
                        "status": WorkflowStepStatus.COMPLETED,
                        "detail": (
                            "Reviewer edits passed citation, literal-span, tool-reference, "
                            "and answer-release validation."
                        ),
                    }
                )
        update.update(
            {
                "response": resolution.edited_response,
                "validation": validation,
                "generation_degraded": False,
                "trace": trace,
            }
        )
    elif resolution.action is HitlAction.CONFIRM_TRANSCRIPTION:
        assert resolution.confirmed_student_attempt is not None
        evidence = [
            _MULTIMODAL_EVIDENCE_ADAPTER.validate_python(item)
            for item in state.get("multimodal_evidence", [])
        ]
        perception_trace = [
            PerceptionTraceEntry.model_validate(item)
            for item in state.get("perception_trace", [])
        ]
        confirmed_evidence, confirmed_trace = confirm_checkpoint_perception(
            evidence,
            perception_trace,
            resolution.confirmed_student_attempt,
        )
        current_request = state["request"]
        scientific_request = current_request.scientific_request
        if scientific_request is None:
            derived, derived_attachment_id, ordinals = derive_scientific_request(
                tuple(confirmed_evidence)
            )
            scientific_request = derived
            if derived_attachment_id is not None and ordinals is not None:
                confirmed_trace = [
                    item.model_copy(
                        update={
                            "scientific_request_derived": item.attachment_id
                            == derived_attachment_id,
                            "scientific_derivation_ordinals": (
                                ordinals
                                if item.attachment_id == derived_attachment_id
                                else None
                            ),
                        }
                    )
                    for item in confirmed_trace
                ]
        confirmed_request = type(current_request).model_validate(
            {
                **current_request.model_dump(mode="python"),
                "student_attempt": resolution.confirmed_student_attempt,
                "scientific_request": scientific_request,
            }
        )
        update.update(
            {
                "request": confirmed_request,
                "multimodal_evidence": confirmed_evidence,
                "perception_trace": confirmed_trace,
                # Re-run the bounded workflow from interpretation so no diagnosis
                # made from uncertain OCR survives confirmation.
                "trace": [],
                "scientific_results": [],
                "restart_after_confirmation": True,
            }
        )
    return update


async def reject_turn_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    event = state["hitl_events"][-1]
    if event.resolution is None or event.resolution.action is not HitlAction.REJECT:
        raise HitlResolutionValidationError("reject route requires a reject resolution")
    started = runtime.context.started_turn
    await TeachingRepository(runtime.context.session).fail_turn(
        started,
        failure_code="HITL_REJECTED",
    )
    await runtime.context.session.commit()
    return {
        "hitl_rejection": HitlRejectedResponse(
            conversation_id=started.conversation.id,
            turn_id=started.turn.id,
            interrupt_id=event.interrupt.interrupt_id,
        )
    }


async def assemble_result_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    from quantum_agent.teaching.models import TeachingTurnResult

    session = runtime.context.session
    actor = runtime.context.actor
    curriculum_edition_id = runtime.context.curriculum_edition_id
    started = runtime.context.started_turn

    # PRD V3.0 Axiom 1: when the commitment gate withheld the answer, redact
    # answer-bearing evidence snippets from the student-facing result.  The
    # frontend still sees that evidence exists (provenance preserved) but
    # cannot read the exact answer text until the gate is satisfied.
    evidence_packet = state["evidence_packet"]
    if state.get("answer_withheld_by_gate"):
        evidence_packet = evidence_packet.redacted_for_gate()

    result = TeachingTurnResult(
        conversation_id=started.conversation.id,
        turn_id=started.turn.id,
        workflow_version=WORKFLOW_VERSION,
        interpretation=state["interpretation"],
        diagnosis=state["diagnosis"],
        policy=state["policy"],
        release=state["release"],
        evidence_packet=evidence_packet,
        response=state["response"],
        validation=state["validation"],
        scientific_results=state["scientific_results"],
        trace=state["trace"],
        learning_native=state.get("learning_native"),
    )
    learning_native_records = _learning_native_records(state)
    await TeachingRepository(session).complete_turn(
        actor=actor,
        curriculum_edition_id=curriculum_edition_id,
        started=started,
        result=result,
        evidence_bundle=state.get("evidence_bundle"),
        hitl_events=list(state.get("hitl_events", [])),
        multimodal_evidence=list(state.get("multimodal_evidence", [])),
        perception_trace=list(state.get("perception_trace", [])),
        learning_native_evidence=learning_native_records,
    )
    # Commit before LangGraph checkpoints the successful node. If checkpointing
    # fails after this point, ``complete_turn`` is safe to execute again.
    await session.commit()
    return {"result": result}


def _learning_native_records(state: TutorState) -> list[LearningEvidenceRecord]:
    """Extract durable learning-evidence records from the Learning-Native state."""

    records: list[LearningEvidenceRecord] = []
    native = state.get("learning_native")
    if native is None:
        return records
    evidence_packet = state.get("evidence_packet")
    concept_id = (
        evidence_packet.graph_nodes[0].id
        if evidence_packet and evidence_packet.graph_nodes
        else None
    )
    seen: set[tuple[str, str]] = set()
    for evidence in _iter_native_evidence(state):
        key = (evidence.kind.value, evidence.observation)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            LearningEvidenceRecord(
                kind=evidence.kind,
                observation=evidence.observation[:1000],
                concept_candidate_id=concept_id,
                mastery_delta=0.0,
                evidence_json=evidence.evidence_json,
            )
        )
    return records


def _iter_native_evidence(state: TutorState) -> list[LearningNativeEvidence]:
    """Pull the evidence observations stashed on the state by the Learning-Native node."""

    raw = state.get("learning_native_evidence")
    if not raw:
        return []
    evidence: list[LearningNativeEvidence] = []
    for item in raw:
        kind_value = item.get("kind")
        if isinstance(kind_value, str):
            kind = LearningEvidenceKind(kind_value)
        elif isinstance(kind_value, LearningEvidenceKind):
            kind = kind_value
        else:
            continue
        observation_value = item.get("observation")
        if not isinstance(observation_value, str):
            continue
        evidence_json_value = item.get("evidence_json", {})
        if not isinstance(evidence_json_value, dict):
            evidence_json_value = {}
        evidence.append(
            LearningNativeEvidence(
                kind=kind,
                observation=observation_value,
                evidence_json=evidence_json_value,
            )
        )
    return evidence


async def learning_native_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    """Run the post-generation Learning-Native policy: teach-back, transfer/Solo, mirror.

    The commitment gate already ran in ``learning_native_pre_node`` BEFORE
    answer generation.  This node handles teach-back analysis, transfer /
    Solo Mode arming, solo-attempt recording, and the Cognitive Mirror.
    It assembles the final ``LearningNativeTurnState`` from the pre-decision
    (commitment) plus the post-decision (teach-back / transfer / solo / mirror).
    """

    request = state["request"]
    diagnosis = state["diagnosis"]
    evidence_packet = state["evidence_packet"]
    actor = runtime.context.actor
    curriculum_edition_id = runtime.context.curriculum_edition_id
    session = runtime.context.session
    model_gateway = runtime.context.model_gateway

    policy = LearningNativePolicy()
    submission = request.learning_native

    # PRD V3.0 P0-2: the durable Learning Phase is the single source of truth
    # for Solo Mode, transfer-task identity, and phase transitions.  It was
    # loaded from the conversation row in ``start_turn`` and is available on
    # the started turn.  We mutate a local copy and persist it at the end.
    durable_phase = runtime.context.started_turn.durable_phase
    conversation = runtime.context.started_turn.conversation
    repository = TeachingRepository(session)

    # Recover the pre-decision (commitment + evidence already persisted there).
    pre_decision_raw = state.get("learning_native_pre_decision") or {}
    pre_decision: dict[str, Any] = (
        pre_decision_raw if isinstance(pre_decision_raw, dict) else {}
    )
    commitment_data = pre_decision.get("commitment")
    commitment: Any = (
        CognitiveCommitment.model_validate(commitment_data)
        if isinstance(commitment_data, dict)
        else None
    )
    learning_action_value = pre_decision.get("learning_action")
    learning_action: Any = (
        LearningPolicyAction(learning_action_value)
        if isinstance(learning_action_value, str)
        else None
    )
    pre_evidence_raw = pre_decision.get("commitment_evidence") or []
    pre_evidence_list: list[Any] = (
        pre_evidence_raw if isinstance(pre_evidence_raw, list) else []
    )
    commitment_evidence: list[LearningNativeEvidence] = [
        LearningNativeEvidence(
            kind=LearningEvidenceKind(item["kind"]),
            observation=item["observation"],
            evidence_json=item.get("evidence_json", {}),
        )
        for item in pre_evidence_list
        if isinstance(item, dict) and "kind" in item and "observation" in item
    ]

    # Teach-back analysis (only when the student submitted a reconstruction).
    teach_back: Any = None
    teach_back_evidence: list[LearningNativeEvidence] = []
    if submission is not None and submission.teach_back is not None:
        target_names = [
            node.name
            for node in evidence_packet.graph_nodes
            if node.node_type in {"Concept", "Topic", "Formula"}
        ][:6]
        proposal = await propose_teach_back_analysis(
            reconstruction=submission.teach_back.reconstruction,
            target_concept_names=target_names,
            model_gateway=model_gateway,
        )
        teach_back, teach_back_evidence = policy.analyze_teach_back(
            submission_text=submission.teach_back.reconstruction,
            proposal=proposal,
        )
        # PRD V3.0 P0-2: after a teach-back reconstruction is submitted,
        # advance the durable phase to TRANSFER_REQUIRED so the next turn
        # can issue a transfer task.
        if durable_phase.phase is LearningPhase.RECONSTRUCTION_REQUIRED:
            durable_phase = durable_phase.model_copy(
                update={"phase": LearningPhase.TRANSFER_REQUIRED}
            )
    elif submission is not None and submission.request_teach_back:
        # PRD V3.0 P0-2: the UI requests a Teach-Back transition.  Set the
        # durable phase so the next turn requires a reconstruction.  The
        # frontend renders the TeachBackCard from the learning_native state.
        if durable_phase.phase in {
            LearningPhase.OPEN,
            LearningPhase.ATTEMPT_RECEIVED,
            LearningPhase.INTERVENTION,
        }:
            durable_phase = durable_phase.model_copy(
                update={"phase": LearningPhase.RECONSTRUCTION_REQUIRED}
            )
        # Surface a teach-back prompt even without a model proposal so the
        # frontend can render the card.
        teach_back = TeachBackAnalysis(
            covered_relations=[],
            missing_relations=[],
            contradictions=[],
            unsupported_claims=[],
            recommended_probe=(
                "不看上面的解释，现在用自己的话向一个第一次学这个概念的同学"
                "重新解释这个结论。"
            ),
            verified=False,
            is_model_inference=False,
        )

    # PRD V3.0 P0-2: Transfer / Solo Mode is driven by the durable phase, not
    # by ad-hoc submission flags.  The durable phase is the single source of
    # truth for whether Solo is active and which transfer task is in flight.
    active_solo: SoloMode | None = None
    if durable_phase.phase is LearningPhase.SOLO_ACTIVE:
        active_solo = SoloMode(
            status=SoloModeStatus.ACTIVE,
            active_transfer=TransferTask(
                transfer_type=TransferType.NEAR,
                prompt=durable_phase.active_transfer_task_prompt,
                source_concept_ids=[],
                key_parameters=[],
                expected_observable="",
                verifiable=False,
            )
            if durable_phase.active_transfer_task_prompt
            else None,
            started_at=durable_phase.solo_started_at,
            assistance_locked=durable_phase.solo_assistance_locked,
            unlock_reason="",
        )

    transfer: Any = None
    solo: SoloMode = active_solo or SoloMode(
        status=SoloModeStatus.INACTIVE,
        active_transfer=None,
        assistance_locked=True,
        unlock_reason="",
    )
    transfer_evidence: list[LearningNativeEvidence] = []

    # Handle explicit Solo exit (marks ABORTED, not SUCCESS).
    if (
        submission is not None
        and submission.request_solo_exit
        and durable_phase.phase is LearningPhase.SOLO_ACTIVE
    ):
        solo = SoloMode(
            status=SoloModeStatus.ABORTED,
            active_transfer=None,
            assistance_locked=False,
            unlock_reason="学生主动退出 Solo Mode（记录为 SOLO_ABORTED）。",
        )
        durable_phase = durable_phase.model_copy(
            update={
                "phase": LearningPhase.ABORTED,
                "solo_assistance_locked": False,
            }
        )
        transfer_evidence = [
            LearningNativeEvidence(
                kind=LearningEvidenceKind.SOLO_ABORTED,
                observation="学生主动退出 Solo Mode；记录为 SOLO_ABORTED，不计为已验证的独立迁移。",
                evidence_json={
                    "outcome": "SOLO_ABORTED",
                    "verified": False,
                    "active_transfer_task_id": (
                        str(durable_phase.active_transfer_task_id)
                        if durable_phase.active_transfer_task_id
                        else None
                    ),
                },
            )
        ]

    # Handle a solo / transfer attempt.  PRD V3.0 P0-2: the attempt must be
    # task-correlated (the durable phase must be SOLO_ACTIVE) and verified
    # before Solo unlocks.  An incorrect attempt does NOT exit Solo.
    elif (
        submission is not None
        and durable_phase.phase is LearningPhase.SOLO_ACTIVE
        and (submission.solo_attempt is not None or submission.transfer_attempt is not None)
    ):
        solo_attempt = submission.solo_attempt
        transfer_attempt = submission.transfer_attempt
        if solo_attempt is not None:
            attempt_text = solo_attempt.response
            attempt_confidence = solo_attempt.confidence
        else:
            assert transfer_attempt is not None
            attempt_text = transfer_attempt.response
            attempt_confidence = transfer_attempt.confidence
        verified = _attempt_verified(state, attempt_text)
        task_id = (
            str(durable_phase.active_transfer_task_id)
            if durable_phase.active_transfer_task_id
            else None
        )
        if verified:
            solo = SoloMode(
                status=SoloModeStatus.EXITED,
                active_transfer=None,
                assistance_locked=False,
                unlock_reason="学生提交了通过确定性验证的迁移尝试，Solo Mode 解除。",
            )
            durable_phase = durable_phase.model_copy(
                update={
                    "phase": LearningPhase.COMPLETE,
                    "solo_assistance_locked": False,
                }
            )
            transfer_evidence = [
                LearningNativeEvidence(
                    kind=LearningEvidenceKind.TRANSFER_VERIFIED,
                    observation=(
                        "学生在 Solo Mode 下提交迁移尝试并通过确定性验证；"
                        "Solo Mode 解除，迁移任务完成。"
                    ),
                    evidence_json={
                        "response_length": len(attempt_text),
                        "verified": True,
                        "confidence": attempt_confidence,
                        "outcome": "TRANSFER_VERIFIED",
                        "active_transfer_task_id": task_id,
                        "unaided": True,
                    },
                ),
                LearningNativeEvidence(
                    kind=LearningEvidenceKind.SOLO_VERIFIED,
                    observation="Solo Mode 以已验证的独立迁移结束。",
                    evidence_json={
                        "outcome": "SOLO_VERIFIED",
                        "verified": True,
                        "active_transfer_task_id": task_id,
                    },
                ),
            ]
        else:
            # Incorrect attempt: Solo stays active.  Persist the evidence but
            # do NOT unlock.  This is TRANSFER_ATTEMPTED (not verified), which
            # must NOT contribute to TRANSFER_READY / unaided_retrieval.
            transfer_evidence = [
                LearningNativeEvidence(
                    kind=LearningEvidenceKind.TRANSFER_ATTEMPTED,
                    observation=(
                        "学生在 Solo Mode 下提交迁移尝试，但未通过确定性验证；"
                        "Solo Mode 保持激活。"
                    ),
                    evidence_json={
                        "response_length": len(attempt_text),
                        "verified": False,
                        "confidence": attempt_confidence,
                        "outcome": "TRANSFER_ATTEMPTED_NOT_VERIFIED",
                        "active_transfer_task_id": task_id,
                        "unaided": True,
                    },
                ),
                LearningNativeEvidence(
                    kind=LearningEvidenceKind.TRANSFER_FAILED,
                    observation="迁移尝试未通过确定性验证。",
                    evidence_json={
                        "verified": False,
                        "outcome": "TRANSFER_FAILED",
                        "active_transfer_task_id": task_id,
                    },
                ),
            ]

    # PRD V3.0 P0-2: the UI can request a Teach-Back or Transfer transition.
    # The policy honours the request only when the durable phase allows it.
    elif submission is not None and submission.request_transfer_task:
        source_concept_ids = [
            node.id for node in evidence_packet.graph_nodes[:6]
        ]
        source_names = [
            node.name for node in evidence_packet.graph_nodes[:6]
        ]
        transfer_proposal = await propose_transfer_task(
            source_concept_names=source_names,
            transfer_type=None,
            model_gateway=model_gateway,
        )
        transfer, solo, transfer_evidence = policy.prepare_transfer(
            proposal=transfer_proposal,
            source_concept_ids=source_concept_ids,
            active_solo=active_solo,
        )
        if solo.status is SoloModeStatus.ACTIVE and transfer is not None:
            durable_phase = DurableLearningPhase(
                phase=LearningPhase.SOLO_ACTIVE,
                active_transfer_task_id=transfer.source_concept_ids[0]
                if transfer.source_concept_ids
                else None,
                active_transfer_task_prompt=transfer.prompt,
                solo_started_at=solo.started_at,
                solo_assistance_locked=True,
                expected_attempt_kind="transfer",
            )

    # Persist the durable phase so the next turn in this conversation
    # restores Solo / transfer state BEFORE generation.
    await repository.save_durable_learning_phase(
        conversation=conversation,
        phase=durable_phase,
    )

    # Cognitive mirror — aggregate persisted evidence for the focus concept.
    target_concept_id = (
        evidence_packet.graph_nodes[0].id if evidence_packet.graph_nodes else None
    )
    all_evidence = [*commitment_evidence, *teach_back_evidence, *transfer_evidence]
    cognitive_mirror = await policy.build_cognitive_mirror(
        course_id=actor.course_id,
        curriculum_edition_id=curriculum_edition_id,
        student_user_id=actor.user_id,
        session=session,
        target_concept_id=target_concept_id,
        diagnosis=diagnosis,
        evidence_packet=evidence_packet,
        current_turn_evidence=all_evidence,
    )

    evidence_kinds = [item.kind.value for item in all_evidence]
    native_state = policy.assemble_turn_state(
        commitment=commitment,
        learning_action=learning_action,
        teach_back=teach_back,
        transfer=transfer,
        solo=solo,
        cognitive_mirror=cognitive_mirror,
        evidence_kinds=evidence_kinds,
    )

    native_evidence_payload = [
        {
            "kind": item.kind.value,
            "observation": item.observation,
            "evidence_json": item.evidence_json,
        }
        for item in all_evidence
    ]

    return {
        "learning_native": native_state,
        "learning_native_evidence": native_evidence_payload,
        "solo_assistance_locked": solo.assistance_locked,
    }


def _state_solo(state: TutorState) -> SoloMode | None:
    """Read a Solo Mode snapshot from the durable state, if any."""

    native = state.get("learning_native")
    if native is None or native.solo is None:
        return None
    if native.solo.status is SoloModeStatus.ACTIVE:
        return native.solo
    return None


def _attempt_verified(state: TutorState, response: str) -> bool:
    """Best-effort deterministic verification of a transfer response.

    We only mark a transfer attempt as verified when a scientific tool result
    for this turn passed and the response references its observable.  The LLM
    is never allowed to assert verification on its own.
    """

    response_lower = response.lower()
    scientific_results = state.get("scientific_results") or []
    for result in scientific_results:
        if result.status is not ScientificVerificationStatus.PASS:
            continue
        for observation in result.observations:
            if observation.lower() in response_lower:
                return True
    return False
