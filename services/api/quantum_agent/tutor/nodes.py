"""LangGraph node implementations for the teaching workflow.

Each node reads from and writes to ``TutorState``. Nodes are thin, deterministic
wrappers around the shared module-level functions in ``state_machine`` so the
state machine (B0) and the graph (B1) exercise identical logic.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import TypeAdapter

from quantum_agent.coding import CodeArtifactRun, CodeGenerationTask
from quantum_agent.db_models import (
    AnswerReleaseLevel,
    LearningEvidenceKind,
    TeachingAction,
)
from quantum_agent.knowledge.evidence_packets import EvidencePacket, RetrievalCoverage
from quantum_agent.knowledge.retrieval import RetrievalScope
from quantum_agent.multimodal.contracts import ConfirmedEvidence
from quantum_agent.multimodal.teaching import (
    PerceptionTraceEntry,
    confirm_checkpoint_perception,
    derive_scientific_request,
)
from quantum_agent.science import (
    ScientificVerificationStatus,
)
from quantum_agent.science.models import (
    CodeTestRequest,
    RectangularBarrierRequest,
)
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
    TransferProposal,
    _required_action_for_phase,
    assert_phase_transition,
    phase_is_actionable_next_step,
    propose_commitment,
    propose_teach_back_analysis,
    propose_transfer_task,
    suppress_gated_commitment_evidence,
)
from quantum_agent.teaching.models import (
    CognitiveCommitment,
    CommitmentGateDecision,
    DiagnosisOutput,
    DiagnosisStatus,
    DurableLearningPhase,
    LearningPhase,
    LearningPolicyAction,
    LearningStage,
    ReleaseDecision,
    ResponseStatus,
    SoloMode,
    SoloModeStatus,
    StudentSnapshot,
    TeachBackAnalysis,
    TeachingResponse,
    TeachingTurnInput,
    TransferTask,
    TransferType,
    TransferVerificationSpec,
    ValidationReport,
    WorkflowStep,
    WorkflowStepName,
    WorkflowStepStatus,
)
from quantum_agent.teaching.policy import (
    AnswerPolicyRepository,
    AnswerReleaseEngine,
    commitment_eligibility,
    safe_default_policy,
)
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

# Durable phases at which the commitment gate has already been satisfied earlier
# in the episode.  While the conversation sits in any of these phases, neither
# the commitment gate (learning_native_pre) nor the answer-release engine may
# re-arm on a later turn — the student has produced a verified learning signal;
# re-arming would block the experiment (Coding Agent) stage or re-request a
# prediction mid-loop.
_COMMITMENT_SATISFIED_PHASES = frozenset(
    {
        # PRD V3.4: an accepted commitment (or a typed attempt) satisfies the
        # gate for the REST of the episode.  ATTEMPT_RECEIVED and INTERVENTION
        # must be in this set too, otherwise the very next revision turn would
        # re-arm the gate (the same class of regression the experiment-turn
        # test guards).
        LearningPhase.ATTEMPT_RECEIVED,
        LearningPhase.INTERVENTION,
        LearningPhase.AWAITING_REVISION,
        LearningPhase.RECONSTRUCTION_REQUIRED,
        LearningPhase.TRANSFER_REQUIRED,
        LearningPhase.SOLO_ACTIVE,
        LearningPhase.COMPLETE,
    }
)


def _perception_confirmation_source(item: object) -> str | None:
    """Read ``confirmation_source`` from a perception-trace entry that may be a
    ``PerceptionTraceEntry`` instance or a deserialized dict (after LangGraph
    checkpoint round-trip)."""

    if isinstance(item, PerceptionTraceEntry):
        return item.confirmation_source
    if isinstance(item, dict):
        value = item.get("confirmation_source")
        return value if isinstance(value, str) else None
    return None


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
        commitment_already_satisfied=started.durable_phase.phase
        in _COMMITMENT_SATISFIED_PHASES,
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


def _coding_task_from_request(
    request: TeachingTurnInput,
    scientific_request: object,
) -> CodeGenerationTask | None:
    """Build a Coding Agent brief from the scientific request, when supported.

    The Coding Agent writes fresh Python for the Golden Loop tunnelling
    computation (PRD §6, §9): ``rectangular_barrier_tunnelling``.  Other
    scientific requests (e.g. ``two_level_simulation`` in ``run_experiments``
    mode) are student-requested simulations whose deterministic tool is the
    authoritative result; the Coding Agent does not run for them, so the
    deterministic oracle remains the sole result and the student gets the
    simulation they requested even when the model-backed Coding Agent is
    unavailable.
    """

    student_question = request.message
    if isinstance(scientific_request, RectangularBarrierRequest):
        return CodeGenerationTask(
            student_question=student_question,
            learning_goal=(
                "Compute the rectangular-barrier transmission T and reflection R "
                "and compare to the student's prediction."
            ),
            known_variables={
                "energy_eV": str(scientific_request.energy_eV),
                "barrier_height_eV": str(scientific_request.barrier_height_eV),
                "barrier_width_m": str(scientific_request.barrier_width_m),
                "particle_mass_kg": str(scientific_request.particle_mass_kg),
                "conservation_tolerance": str(scientific_request.conservation_tolerance),
            },
            required_outputs=["T", "R", "conservation_error"],
            allowed_libraries=("numpy", "math", "cmath"),
            oracle_kind="rectangular_barrier_tunnelling",
        )
    return None


async def scientific_tools_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    request = state["request"]
    release = state["release"]
    toolbox = runtime.context.scientific_toolbox
    scientific_results = list(state.get("scientific_results", []))

    # Release-review P0 companion fix: Solo verification must not depend on
    # retrieval coverage.  When the durable phase is SOLO_ACTIVE and the
    # pre-node restored the persisted transfer oracle, the deterministic
    # verifier runs regardless of the release level — it checks the
    # student's independent answer rather than releasing any course answer
    # (generation still honours the release level).
    durable_phase = runtime.context.started_turn.durable_phase
    solo_verification_due = (
        durable_phase.phase is LearningPhase.SOLO_ACTIVE
        and durable_phase.transfer_verification is not None
        and bool(durable_phase.transfer_verification.scientific_request)
        and request.scientific_request is not None
    )
    tool_allowed = release.release_level in {
        AnswerReleaseLevel.SCAFFOLD,
        AnswerReleaseLevel.FULL_EXPLANATION,
        AnswerReleaseLevel.FULL_SOLUTION,
    } or solo_verification_due
    code_artifact: dict[str, Any] | None = None
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
        # PRD V3.1 P1-2: run the deterministic oracle and the Coding Agent
        # concurrently.  They are independent: the oracle verifies the
        # request deterministically (thread-pool), and the Coding Agent
        # writes and executes a fresh program (async coroutine).  Neither
        # result feeds the other; the oracle remains the cross-check, and
        # the Coding Agent's generated metrics are authoritative on PASS.
        # This cuts the node's wall-clock latency from ``oracle + coding``
        # to ``max(oracle, coding)`` for computation-bearing turns.
        coding_agent = runtime.context.coding_agent
        gateway = runtime.context.model_gateway
        coding_task = _coding_task_from_request(request, request.scientific_request)
        oracle_coro = asyncio.to_thread(toolbox.verify, request.scientific_request)
        # PRD V3.3 Solo shield: during Solo verification only the deterministic
        # oracle may run.  Its PASS status is the secondary signal for
        # ``_attempt_verified``; its numeric outcome is redacted below.  The
        # Coding Agent must NOT run here even though the restored transfer
        # request is a RectangularBarrierRequest — its ``code_artifact`` would
        # carry ``oracle_metrics`` with the correct T, leaking the answer to
        # the browser through the CodingArtifactPanel before the independent
        # attempt passes.
        coding_disabled_for_solo = solo_verification_due
        if (
            coding_agent is not None
            and gateway is not None
            and coding_task is not None
            and not isinstance(request.scientific_request, CodeTestRequest)
            and not coding_disabled_for_solo
        ):
            oracle_outcome, coding_outcome = await asyncio.gather(
                oracle_coro,
                coding_agent.solve(coding_task, gateway=gateway),
                return_exceptions=True,
            )
        else:
            oracle_outcome = await oracle_coro
            coding_outcome = None
        if isinstance(oracle_outcome, BaseException):
            # The deterministic oracle failed unexpectedly.  Re-raise so
            # the workflow surfaces the failure rather than silently
            # dropping the verification result.
            raise oracle_outcome
        tool_result = oracle_outcome
        scientific_results.append(tool_result)
        coding_detail = ""
        if isinstance(coding_outcome, CodeArtifactRun):
            run = coding_outcome
            code_artifact = run.model_dump(mode="json")
            if run.verification.status.value != "pass":
                # The Coding Agent cross-check did not pass.  Pop the oracle
                # so no PASS result is surfaced as a successful computation
                # (fail-closed: never fabricate the agent's success).  The
                # ``code_artifact`` carries the honest INCONCLUSIVE failure.
                scientific_results.pop()
            else:
                # PRD V3.1 §6: the Coding Agent's generated program passed the
                # deterministic oracle within tolerance.  The oracle result
                # already in ``scientific_results`` is the authoritative
                # displayed computation (its metrics equal the agent's
                # verified metrics within 1e-6); the agent's fresh program
                # and verification verdict are surfaced in ``code_artifact``.
                # We do NOT append a second scientific_results entry: the
                # BFF contract and the tunnelling-metrics panel render from
                # the single authoritative tool result.
                pass
            coding_detail = (
                f"Coding Agent wrote {len(run.artifact.code)} chars of Python; "
                f"verifier status={run.verification.status.value}; "
                f"repairs={len(run.repairs)}."
            )
        elif isinstance(coding_outcome, Exception):
            # Never let the Coding Agent crash the turn.  Pop the oracle so
            # no PASS result is surfaced when the agent computation failed;
            # the step is marked DEGRADED so the trace is honest.
            scientific_results.pop()
            coding_detail = (
                f"Coding Agent failed: {type(coding_outcome).__name__}; "
                "computation is inconclusive."
            )
        detail = (
            f"{tool_result.method.value} verification completed with "
            f"status={tool_result.status.value}."
        )
        if coding_detail:
            detail = f"{detail} {coding_detail}"
        tool_step = WorkflowStep(
            name=WorkflowStepName.RUN_SCIENTIFIC_TOOLS,
            status=(
                WorkflowStepStatus.DEGRADED
                if (
                    tool_result.status is ScientificVerificationStatus.INCONCLUSIVE
                    or (
                        coding_task is not None
                        and not scientific_results
                    )
                )
                else WorkflowStepStatus.COMPLETED
            ),
            detail=detail,
        )
    trace = list(state.get("trace", []))
    trace.append(tool_step)
    if solo_verification_due and scientific_results:
        # Solo Mode answer shield: the oracle ran so deterministic verification
        # is possible, but its numeric outcome must not leak into the response
        # (panels or the generation context) before the student's own attempt
        # passes.  The PASS status survives as _attempt_verified's secondary
        # signal; values, observations, and visualizations are withheld.
        scientific_results = [
            result.model_copy(
                update={
                    "observations": [
                        "Solo 验证已执行；在独立验证通过前，数值结果不予显示。"
                    ],
                    "metrics": {},
                    "visualization": None,
                }
            )
            for result in scientific_results
        ]
    update: dict[str, Any] = {"scientific_results": scientific_results, "trace": trace}
    if code_artifact is not None:
        update["code_artifact"] = code_artifact
    return update


async def learning_native_pre_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    """Run the Learning-Native commitment gate BEFORE retrieval and answer
    generation.

    This is the PRD V3.0 Axiom 1 enforcement point ("Learner generates before
    AI completes").  The gate decision is a pure function of the teaching mode,
    the deterministic task kind, the student's message, and whether the
    student already submitted a meaningful attempt this turn — it does NOT
    depend on the retrieved evidence.  When the gate fires, the graph skips
    retrieval/diagnosis/scientific-tools/generation entirely (see
    ``prepare_commitment_gate_node``) and produces a deterministic elicitation
    response with zero claims.  The LLM only proposes the commitment prompt;
    code decides whether to withhold the answer.

    PRD V3.0 P0-2: this node also enforces the durable Learning Phase.  When
    the conversation is in ``SOLO_ACTIVE``, normal Ask AI requests are
    blocked BEFORE the LLM is called — the student must submit a solo
    attempt or explicitly exit Solo.  Refresh / new tab / retry cannot
    escape the lock because the phase is persisted on the conversation.
    """

    if state.get("learning_native_pre_decision") is not None:
        return {}
    request = state["request"]
    interpretation = state["interpretation"]
    model_gateway = runtime.context.model_gateway
    submission = request.learning_native

    durable_phase = runtime.context.started_turn.durable_phase

    # Only an actual cognitive artefact can satisfy the commitment gate.  A
    # boolean UI transition request is never an attempt and therefore cannot
    # be used to jump directly to Teach-Back or Transfer.
    submitted_commitment = submission.commitment if submission is not None else None

    # Revision is a typed cross-turn obligation.  While the episode is in a
    # revision-bearing phase (ATTEMPT_RECEIVED / INTERVENTION /
    # AWAITING_REVISION), the student's message itself is the revised
    # explanation and must enter the Diagnosis Agent as ``student_attempt``.
    # PRD V3.4: after an accepted commitment the episode holds at
    # ATTEMPT_RECEIVED and the minimal-intervention probe is answered as free
    # text — so the same promotion applies there.
    phase_at_start = durable_phase.phase
    if (
        phase_at_start
        in {
            LearningPhase.ATTEMPT_RECEIVED,
            LearningPhase.INTERVENTION,
            LearningPhase.AWAITING_REVISION,
        }
        and not request.student_attempt
        and LearningNativePolicy.attempt_is_meaningful(request.message)
    ):
        request = request.model_copy(update={"student_attempt": request.message})

    # A Solo attempt is verified against the exact persisted transfer oracle,
    # never against an unrelated client-selected tool request.
    if (
        durable_phase.phase is LearningPhase.SOLO_ACTIVE
        and submission is not None
        and (submission.solo_attempt is not None or submission.transfer_attempt is not None)
        and durable_phase.transfer_verification is not None
        and durable_phase.transfer_verification.scientific_request
    ):
        scientific_request = runtime.context.scientific_toolbox.validate_request(
            durable_phase.transfer_verification.scientific_request
        )
        request = request.model_copy(update={"scientific_request": scientific_request})

    # PRD V3.0 P0-2: load the durable Learning Phase.  Solo Mode is
    # server-authoritative and restored BEFORE generation, so a normal Ask
    # AI request during Solo is blocked here rather than after the LLM
    # has already written an answer.
    solo_active = durable_phase.phase is LearningPhase.SOLO_ACTIVE
    solo_submission = (
        submission is not None
        and (submission.solo_attempt is not None or submission.transfer_attempt is not None)
    )
    solo_exit_requested = submission is not None and submission.request_solo_exit

    # Release-review P0 fix: a submitted Solo/Transfer attempt IS the
    # cognitive artefact for this turn.  Promote it to ``student_attempt``
    # so BOTH the commitment gate below and ``AnswerReleaseEngine.decide``
    # treat the turn as attempt-bearing.  Without this, the gate re-arms on
    # top of the solo submission (release stays QUESTION_ONLY), the
    # deterministic oracle is skipped in ``scientific_tools_node``, and a
    # numerically correct solo answer can never satisfy ``_attempt_verified``
    # — the Golden Loop could not close.  The promotion also replaces any
    # client-supplied ``student_attempt``, so an unrelated typed attempt
    # cannot ride along inside a Solo turn.
    if solo_active and solo_submission:
        assert submission is not None
        solo_artefact = submission.solo_attempt or submission.transfer_attempt
        assert solo_artefact is not None
        request = request.model_copy(update={"student_attempt": solo_artefact.response})

    # PRD V3.0 Axiom 1: the gate decision is deterministic and pre-retrieval.
    # ``commitment_eligibility`` returns True when the task kind requires a
    # cognitive commitment (reasoning / exercise / prediction / experiment)
    # and the student has not yet submitted one.  This is the same function
    # ``AnswerReleaseEngine.decide`` uses to set ``release_level =
    # QUESTION_ONLY`` with ``reason_code = commitment_required_before_explanation``,
    # so the gate decision is consistent with the release decision that
    # ``apply_policy`` would have made post-retrieval.
    request_has_attempt = LearningNativePolicy.attempt_is_meaningful(request.student_attempt)
    # PRD V3.3 root-cause #4 fix: a submitted Commitment Card is a PREDICTION,
    # not an attempt that satisfies the commitment gate.  The gate must stay
    # armed (release = question_only) after the student commits a prediction,
    # so the explanation is NOT released on the same turn.  Only a *revised*
    # student_attempt (a follow-up turn with a typed attempt and no commitment
    # card) satisfies the gate.  Including ``submitted_commitment is not None``
    # here previously disarmed the gate on the commitment turn, which released
    # the full explanation immediately — the "jump to the last step" symptom.
    #
    # PRD V3.3 Golden Loop closure: once the durable phase has advanced past
    # the commitment stages, the student has ALREADY satisfied the commitment
    # gate earlier in this episode (invariant C advanced the phase on a verified
    # learning signal).  The gate must NOT re-arm on a later turn — e.g. the
    # experiment turn that runs the Coding Agent after ``AWAITING_REVISION``
    # would otherwise re-request a prediction and skip the scientific tools
    # entirely.  Re-arming the gate after commitment is a regression that
    # blocks the Coding Agent stage of the loop.
    commitment_satisfied_in_episode = durable_phase.phase in _COMMITMENT_SATISFIED_PHASES
    gate_eligible = (
        not commitment_satisfied_in_episode
        and commitment_eligibility(
            mode=request.mode,
            task_kind=interpretation.task_kind,
            message=request.message,
            has_current_attempt=request_has_attempt,
        )
    )
    # The release is QUESTION_ONLY (from the gate's perspective) when the
    # gate is eligible.  This mirrors ``AnswerReleaseEngine.decide`` without
    # needing the retrieved coverage.
    release_is_question_only = gate_eligible

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
            "request": request,
            "learning_native_pre_decision": solo_pre_decision,
            "answer_withheld_by_gate": True,
            "learning_native_evidence": [],
            "solo_assistance_locked": True,
        }

    if (
        durable_phase.phase is LearningPhase.RECONSTRUCTION_REQUIRED
        and not (submission is not None and submission.teach_back is not None)
    ):
        reconstruction_commitment = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.PROCEED,
            attempt_required=False,
            candidate_prompt=(
                "请先完成当前 Teach-Back：不看上面的解释，用自己的话重构核心机制。"
            ),
            reason_summary="学习阶段要求先完成 Teach-Back，不能跳到迁移或新答案。",
            accepted=True,
        )
        phase_pre_decision: dict[str, Any] = {
            "commitment": reconstruction_commitment.model_dump(mode="json"),
            "learning_action": LearningPolicyAction.START_TEACH_BACK.value,
            "withhold_answer": True,
            "commitment_evidence": [],
            "phase_blocked": True,
        }
        return {
            "request": request,
            "learning_native_pre_decision": phase_pre_decision,
            "answer_withheld_by_gate": True,
            "learning_native_evidence": [],
        }

    # PRD V3.0 P0-1: when the turn carries an unconfirmed perception (e.g. an
    # ambiguous OCR extraction awaiting HITL confirmation), the commitment
    # gate must NOT fire yet.  The graph proceeds to retrieval and the HITL
    # gate so the student / teacher can confirm the transcription first.
    # After confirmation the graph restarts from ``interpret`` and the
    # commitment gate runs again with a confirmed perception.  This ordering
    # prevents the gate from withholding an answer before the student has
    # even confirmed what they wrote.
    perception_pending = any(
        _perception_confirmation_source(item) == "pending"
        for item in state.get("perception_trace", [])
    )
    if perception_pending:
        gate_eligible = False
        release_is_question_only = False

    commitment_proposal = await propose_commitment(
        message=request.message,
        release_is_question_only=release_is_question_only,
        model_gateway=model_gateway,
    )
    policy = LearningNativePolicy()
    commitment, learning_action, withhold, commitment_evidence = policy.decide_pre_generation(
        request_has_attempt=request_has_attempt,
        release_is_question_only=release_is_question_only,
        proposal=commitment_proposal,
        submission=submission.commitment if submission is not None else None,
        submission_confidence=submission.confidence if submission is not None else None,
    )

    # The formal Commitment Card is the student's first attempt.  Feed it to
    # retrieval/diagnosis and restore the scientific task that was captured
    # when the initial question opened the commitment gate.
    if commitment.accepted and submitted_commitment is not None:
        restored_scientific_request = request.scientific_request
        if durable_phase.pending_scientific_request:
            restored_scientific_request = runtime.context.scientific_toolbox.validate_request(
                durable_phase.pending_scientific_request
            )
        request = request.model_copy(
            update={
                "student_attempt": submitted_commitment.candidate_prompt,
                "scientific_request": restored_scientific_request,
            }
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
        "request": request,
        "learning_native_pre_decision": pre_decision,
        "answer_withheld_by_gate": withhold,
        "learning_native_evidence": pre_decision["commitment_evidence"],
    }


async def prepare_commitment_gate_node(
    state: TutorState,
    runtime: Runtime[TutorContext],
) -> dict[str, Any]:
    """Produce the deterministic commitment-gate response when the gate fires.

    PRD V3.0 Axiom 1 ("Learner generates before AI completes"): when the
    commitment gate fires, the graph skips retrieval / diagnosis /
    scientific-tools / generation entirely.  This node emits:

    * An empty ``EvidencePacket`` with ``coverage=NOT_FOUND`` and a
      ``retrieval_skipped_until_commitment`` warning so the student-facing
      result carries no answer-bearing evidence while the gate is open.
    * A ``DiagnosisOutput`` with ``status=INSUFFICIENT_EVIDENCE`` (there is
      no evidence to diagnose against).
    * A safe-default ``PolicySnapshot`` and a ``ReleaseDecision`` at
      ``QUESTION_ONLY`` with ``commitment_required_before_explanation``.
    * A deterministic elicitation ``TeachingResponse`` with zero claims.
    * SKIPPED trace steps for RETRIEVE_EVIDENCE, DIAGNOSE_PROGRESS,
      RUN_SCIENTIFIC_TOOLS, and GENERATE_RESPONSE; COMPLETED steps for
      CHOOSE_TEACHING_ACTION, APPLY_ANSWER_POLICY, VALIDATE_RESPONSE, and
      RECORD_LEARNING_EVIDENCE so the 10-step ``WORKFLOW_ORDER`` invariant
      is preserved.
    """

    from quantum_agent.teaching.state_machine import _next_question, _orientation

    request = state["request"]
    actor = runtime.context.actor
    started = runtime.context.started_turn
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

    # PRD V3.4: an accepted Commitment Card routed through this gate node only
    # when the durable phase was already advanced past COMMITMENT_REQUIRED (a
    # stale pre-decision after an HITL restart / confirmation).  Acknowledge
    # it positively instead of re-asking for an invisible second commitment.
    accepted_gate_commitment = (
        not solo_blocked
        and bool(commitment_data.get("accepted"))
        and commitment_data.get("attempt_required") is True
        and started.durable_phase.phase
        in {
            LearningPhase.ATTEMPT_RECEIVED,
            LearningPhase.INTERVENTION,
            LearningPhase.AWAITING_REVISION,
        }
    )
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
        reason_code = "solo_mode_assistance_locked"
    elif accepted_gate_commitment:
        # PRD V3.4 positive acknowledgement: this gated turn ACCEPTED the
        # student's commitment (prediction / first step / physical reason).
        # Acknowledge it deterministically and hand the student the minimal
        # intervention that follows from it — the tutorial step is at most the
        # hint probe, never a full answer.  Invariant B holds: the accepted
        # commitment is NOT the explanation, and it does NOT jump the phase
        # forward by itself; Evidence → Diagnosis → Policy have run this turn
        # and the student must revise/explain next.
        orientation_text = (
            "已收到你的承诺（预测 / 第一步 / 物理理由）。"
            + (candidate_prompt or "接下来基于它给出最小干预提示。")
        )
        next_action = _required_action_for_phase(started.durable_phase.phase)
        if next_action == "commitment":
            next_question_text = (
                candidate_prompt
                or "现在请基于你的承诺，完成下一步：写出的你的判断/推导/理由。"
            )
        elif next_action == "revision":
            next_question_text = (
                candidate_prompt
                or "现在请根据提示修正或解释你刚才的尝试（这是下一步）。"
            )
        else:
            next_question_text = candidate_prompt or "请看上面的提示继续。"
        limitation_text = (
            "Commitment accepted: a minimal intervention follows; the full "
            "course answer is released only as the backend policy allows."
        )
        generate_detail = (
            "Commitment accepted; the gate produced a minimal-intervention "
            "acknowledgement instead of the full answer."
        )
        warning_code = "answer_withheld_by_commitment_gate"
        reason_code = "commitment_accepted_minimal_intervention"
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
        reason_code = "commitment_required_before_explanation"

    empty_packet = EvidencePacket(
        course_id=actor.course_id,
        curriculum_edition_id=runtime.context.curriculum_edition_id,
        query=request.message[:5000],
        coverage=RetrievalCoverage.NOT_FOUND,
        warnings=["retrieval_skipped_until_commitment"],
    )
    gate_diagnosis = DiagnosisOutput(
        status=DiagnosisStatus.INSUFFICIENT_EVIDENCE,
        summary="Commitment gate is open; retrieval and diagnosis are skipped.",
        observation_basis=[],
        reason="The commitment gate withheld retrieval until the student commits.",
    )
    gate_policy = safe_default_policy(request.mode)
    gate_release = ReleaseDecision(
        action=TeachingAction.ASK_DIAGNOSTIC_QUESTION,
        release_level=AnswerReleaseLevel.QUESTION_ONLY,
        attempts_observed=started.prior_attempts,
        reason_code=reason_code,
    )
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

    trace = list(state.get("trace", []))
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.RETRIEVE_EVIDENCE,
            status=WorkflowStepStatus.SKIPPED,
            detail="Retrieval skipped until the student submits a cognitive commitment.",
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.DIAGNOSE_PROGRESS,
            status=WorkflowStepStatus.SKIPPED,
            detail="Diagnosis skipped until the student submits a cognitive commitment.",
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.CHOOSE_TEACHING_ACTION,
            status=WorkflowStepStatus.COMPLETED,
            detail=f"Backend selected action {gate_release.action.value}.",
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.APPLY_ANSWER_POLICY,
            status=WorkflowStepStatus.COMPLETED,
            detail=(
                f"Backend policy released {gate_release.release_level.value}; "
                f"reason={gate_release.reason_code}."
            ),
        )
    )
    trace.append(
        WorkflowStep(
            name=WorkflowStepName.RUN_SCIENTIFIC_TOOLS,
            status=WorkflowStepStatus.SKIPPED,
            detail="Scientific tools skipped until the student submits a cognitive commitment.",
        )
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
        "evidence_packet": empty_packet,
        "evidence_bundle": None,
        "diagnosis": gate_diagnosis,
        "policy": gate_policy,
        "release": gate_release,
        "scientific_results": [],
        "response": withheld_response,
        "validation": withheld_validation,
        "generation_degraded": False,
        "trace": trace,
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
        accepted_gate_commitment = (
            not solo_blocked
            and bool(commitment_data.get("accepted"))
            and runtime.context.started_turn.durable_phase.phase
            in {
                LearningPhase.ATTEMPT_RECEIVED,
                LearningPhase.INTERVENTION,
                LearningPhase.AWAITING_REVISION,
            }
        )
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
        elif accepted_gate_commitment:
            orientation_text = (
                "已收到你的承诺（预测 / 第一步 / 物理理由）。"
                + (candidate_prompt or "接下来基于它给出最小干预提示。")
            )
            next_action = _required_action_for_phase(
                runtime.context.started_turn.durable_phase.phase
            )
            if next_action == "revision":
                next_question_text = (
                    candidate_prompt
                    or "现在请根据提示修正或解释你刚才的尝试（这是下一步）。"
                )
            else:
                next_question_text = candidate_prompt or "请看上面的提示继续。"
            limitation_text = (
                "Commitment accepted: a minimal intervention follows; the full "
                "course answer is released only as the backend policy allows."
            )
            generate_detail = (
                "Commitment accepted; the gate produced a minimal-intervention "
                "acknowledgement instead of the full answer."
            )
            warning_code = "answer_withheld_by_commitment_gate"
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
        code_artifact=state.get("code_artifact"),
        trace=state["trace"],
        learning_native=state.get("learning_native"),
    )
    # PRD V3.3 root-cause #8 fix: ``learning_loop_completed`` is a computed
    # function of the authoritative durable phase, not a hardcoded False.  A
    # bounded graph turn reaching ``assemble_result`` is ``turn_completed``;
    # the *Learning-Native loop* is complete only when the durable phase is
    # ``COMPLETE``.  The browser reads this flag to render a distinct terminal
    # state and must NOT infer completion from the SSE ``workflow.completed``
    # lifecycle event, which fires for every bounded turn.
    native_state = state.get("learning_native")
    loop_complete = (
        native_state is not None
        and native_state.phase is LearningPhase.COMPLETE
    )
    result = result.model_copy(
        update={"learning_loop_completed": loop_complete}
    )
    # PRD V3.4 no-orphan invariant: it must NEVER be possible to end a turn in
    # a loop-required, incomplete LearningPhase with ZERO actionable next
    # steps.  The historical commit turn (phase=commitment_required,
    # commitment.accepted=true, gate_decision=attempt_required) is exactly the
    # forbidden machine state the UI cannot advance.  Fail CLOSED by raising
    # instead of returning an orphan result.
    if (
        loop_complete is False
        and native_state is not None
        and native_state.loop_required
        and native_state.phase is not LearningPhase.ABORTED
    ):
        actionable = phase_is_actionable_next_step(
            phase=native_state.phase,
            commitment=native_state.commitment,
            teach_back=native_state.teach_back,
            transfer=native_state.transfer,
            solo=native_state.solo,
        )
        if not actionable:

            raw = result.model_dump(mode="json")
            del raw["trace"]
            raise RuntimeError(
                "no-orphan invariant violated: loop-required learning phase "
                f"{native_state.phase.value} exposes no actionable next step. "
                f"result skeleton={str(raw)[:800]}"
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


def _append_learning_stages(
    existing: list[LearningStage],
    *stages: LearningStage,
) -> list[LearningStage]:
    ordered = list(existing)
    for stage in stages:
        if stage not in ordered:
            ordered.append(stage)
    return ordered


def _tunnelling_transfer_contract(
    payload: dict[str, object],
    runtime: Runtime[TutorContext],
) -> tuple[TransferProposal, TransferVerificationSpec] | None:
    """Create a changed-parameter, deterministically verifiable near transfer."""

    try:
        original = runtime.context.scientific_toolbox.validate_request(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(original, RectangularBarrierRequest):
        return None
    changed_width = min(original.barrier_width_m * 1.5, 1e-3)
    changed = original.model_copy(update={"barrier_width_m": changed_width})
    oracle = runtime.context.scientific_toolbox.verify(changed)
    expected = oracle.metrics.get("T")
    if oracle.status is not ScientificVerificationStatus.PASS or not isinstance(
        expected, (float, int)
    ):
        return None
    prompt = (
        "近迁移（独立完成）：保持粒子能量 "
        f"E={changed.energy_eV:g} eV 与势垒高度 V₀={changed.barrier_height_eV:g} eV，"
        f"把势垒宽度改为 a={changed.barrier_width_m * 1e9:.4g} nm。"
        "先判断透射率相对原情形如何变化，再计算透射系数 T；给出数值和物理理由。"
    )
    return (
        TransferProposal(
            transfer_type=TransferType.PARAMETER,
            prompt=prompt,
            key_parameters=[
                f"E={changed.energy_eV:g} eV",
                f"V0={changed.barrier_height_eV:g} eV",
                f"a={changed.barrier_width_m * 1e9:.4g} nm",
            ],
            expected_observable="transmission coefficient T",
        ),
        TransferVerificationSpec(
            scientific_request=changed.model_dump(mode="json"),
            metric_name="T",
            expected_value=float(expected),
            absolute_tolerance=5e-3,
        ),
    )


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
    phase_at_start = durable_phase.phase
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

    loop_needed = durable_phase.loop_required or commitment_eligibility(
        mode=request.mode,
        task_kind=state["interpretation"].task_kind,
        message=request.message,
        has_current_attempt=False,
    )

    # The first gated turn must persist what the student actually sees.  It is
    # never OPEN while the UI is asking for a commitment.  This only applies
    # when the durable phase is one of the pre-explanation phases; once the
    # student has advanced to AWAITING_REVISION / RECONSTRUCTION_REQUIRED /
    # TRANSFER_REQUIRED / SOLO_ACTIVE the commitment gate must not regress the
    # durable phase to COMMITMENT_REQUIRED.
    if (
        loop_needed
        and commitment is not None
        and commitment.gate_decision is CommitmentGateDecision.ATTEMPT_REQUIRED
        and not commitment.accepted
        and phase_at_start
        in {
            LearningPhase.OPEN,
            LearningPhase.ATTEMPT_RECEIVED,
            LearningPhase.INTERVENTION,
        }
    ):
        assert_phase_transition(
            phase_at_start,
            LearningPhase.COMMITMENT_REQUIRED,
            cause="gate_fired",
        )
        pending_request = (
            request.scientific_request.model_dump(mode="json")
            if request.scientific_request is not None
            else durable_phase.pending_scientific_request
        )
        durable_phase = durable_phase.model_copy(
            update={
                "phase": LearningPhase.COMMITMENT_REQUIRED,
                "loop_required": True,
                "pending_scientific_request": pending_request,
            }
        )

    # The barrier experiment frequently runs AFTER the phase has advanced to
    # AWAITING_REVISION (commitment holds, then the revised attempt is
    # verified, then the student runs the experiment).  Refresh the persisted
    # scientific request whenever a validated one arrives in a post-commitment
    # phase so the transfer oracle contract can be reconstructed
    # deterministically when Solo Mode is armed.  SOLO_ACTIVE is excluded:
    # solo turns resubmit the oracle request itself and must not overwrite it.
    if (
        request.scientific_request is not None
        and phase_at_start
        in {
            LearningPhase.ATTEMPT_RECEIVED,
            LearningPhase.INTERVENTION,
            LearningPhase.AWAITING_REVISION,
            LearningPhase.RECONSTRUCTION_REQUIRED,
            LearningPhase.TRANSFER_REQUIRED,
        }
    ):
        durable_phase = durable_phase.model_copy(
            update={
                "pending_scientific_request": request.scientific_request.model_dump(
                    mode="json"
                )
            }
        )

    # Teach-Back is required only after a diagnosed revision.  Invalid or
    # premature submissions fail closed and never advance the durable phase.
    teach_back: Any = None
    teach_back_evidence: list[LearningNativeEvidence] = []
    teach_back_satisfied = False
    if (
        submission is not None
        and submission.teach_back is not None
        and phase_at_start is LearningPhase.RECONSTRUCTION_REQUIRED
    ):
        reconstruction = submission.teach_back.reconstruction.strip()
        if len(reconstruction) < 24:
            teach_back = TeachBackAnalysis(
                covered_relations=[],
                missing_relations=[],
                contradictions=[],
                unsupported_claims=[],
                recommended_probe="请至少用两三句话重构机制，并说明关键因果关系。",
                verified=False,
                is_model_inference=False,
            )
        else:
            target_names = [
                node.name
                for node in evidence_packet.graph_nodes
                if node.node_type in {"Concept", "Topic", "Formula"}
            ][:6]
            proposal = await propose_teach_back_analysis(
                reconstruction=reconstruction,
                target_concept_names=target_names,
                model_gateway=model_gateway,
            )
            teach_back, teach_back_evidence = policy.analyze_teach_back(
                submission_text=reconstruction,
                proposal=proposal,
            )
            # Length alone never advances the loop.  The reconstruction passes
            # only when the analysis covers at least one relation and reports
            # no contradictions.  When the model is unavailable (proposal is
            # None) OR the model degenerated to an entirely empty analysis on
            # a substantial reconstruction (a live USTC round-trip observed
            # exactly this: covered=0/missing=0/contradictions=0 on a 50-char
            # reconstruction, which would otherwise deadlock the loop at
            # reconstruction_required), the reconstruction advances
            # deterministically so a model outage cannot deadlock the Golden
            # Loop — the same guarantee force-armed transfers provide.  The
            # substantial-text bar matches the analysis-entry bar (24 chars):
            # a reconstruction that reaches the model can fall back when the
            # model produces nothing; a trivial one still cannot pass.
            reconstruction_acceptable = bool(
                teach_back.covered_relations
            ) and not teach_back.contradictions
            model_degenerate_analysis = (
                proposal is not None
                and not teach_back.covered_relations
                and not teach_back.missing_relations
                and not teach_back.contradictions
                and not teach_back.unsupported_claims
            )
            model_unavailable_fallback = (
                proposal is None or model_degenerate_analysis
            ) and len(reconstruction) >= 24
            if reconstruction_acceptable or model_unavailable_fallback:
                teach_back_satisfied = True
                assert_phase_transition(
                    phase_at_start,
                    LearningPhase.TRANSFER_REQUIRED,
                    cause="teach_back_verified",
                )
                durable_phase = durable_phase.model_copy(
                    update={
                        "phase": LearningPhase.TRANSFER_REQUIRED,
                        "completed_stages": _append_learning_stages(
                            durable_phase.completed_stages,
                            LearningStage.TEACH_BACK,
                        ),
                    }
                )
            else:
                # Fail closed: the reconstruction covered no relations or
                # contains contradictions.  The phase holds and the card asks
                # for another attempt (legal same-phase hold).
                assert_phase_transition(
                    phase_at_start,
                    LearningPhase.RECONSTRUCTION_REQUIRED,
                    cause="teach_back_rejected",
                )
                if not teach_back.recommended_probe:
                    teach_back = teach_back.model_copy(
                        update={
                            "recommended_probe": (
                                "重构中还没有看到覆盖的关键关系；请用自己的话"
                                "说明核心机制和因果链，再提交一次。"
                            )
                        }
                    )
    elif phase_at_start is LearningPhase.RECONSTRUCTION_REQUIRED:
        # The required card is reconstructed from durable backend phase on
        # every turn; it does not depend on an LLM phrase or optional button.
        teach_back = TeachBackAnalysis(
            covered_relations=[],
            missing_relations=[],
            contradictions=[],
            unsupported_claims=[],
            recommended_probe=(
                "不看上面的解释，现在用自己的话向第一次学习这个概念的同学"
                "重构核心机制。"
            ),
            verified=False,
            is_model_inference=False,
        )

    passed_verification = any(
        result.status is ScientificVerificationStatus.PASS
        for result in state.get("scientific_results", [])
    )
    # PRD V3.3 root-cause #3 fix: a bare non-empty student_attempt must NOT
    # advance the phase to AWAITING_REVISION.  Invariant C requires a positive
    # learning signal: a scientific PASS correlated with the persisted
    # pending_scientific_request, OR an explicit student phase-advance request,
    # OR a *revised* student_attempt (not the commitment prediction itself).
    commitment_submitted_this_turn = (
        submission is not None and submission.commitment is not None
    )
    revised_attempt_this_turn = (
        LearningNativePolicy.attempt_is_meaningful(request.student_attempt)
        and not commitment_submitted_this_turn
    )
    # An explicit phase-advance flag is only a valid learning signal when the
    # requested transition is pedagogically legal from the current phase:
    # request_teach_back advances only from AWAITING_REVISION (D), and
    # request_transfer_task only from TRANSFER_REQUIRED (F).  Anything else is
    # ignored (fail closed) so flags cannot skip teach-back or transfer.
    explicit_advance = (
        submission is not None
        and (
            (
                submission.request_teach_back
                and phase_at_start is LearningPhase.AWAITING_REVISION
            )
            or (
                submission.request_transfer_task
                and phase_at_start is LearningPhase.TRANSFER_REQUIRED
            )
        )
    )
    # The verified_attempt advance to AWAITING_REVISION requires a REVISED,
    # non-commitment attempt.  A bare scientific PASS on the commitment turn
    # must NOT trigger it (the release generated this turn is at most the
    # minimal-intervention probe, and the student must revise/explain next).
    # Excluding the commitment turn here is invariant B: commitment accepted ≠
    # episode auto-advances / full answer released on the same turn.
    positive_learning_signal = (
        revised_attempt_this_turn
        or (passed_verification and not commitment_submitted_this_turn)
        or explicit_advance
    )

    # PRD V3.4 root-cause fix (accepted commitment = the initial attempt):
    # when this turn accepted a formal Commitment Card, the phase advances
    # COMMITMENT_REQUIRED -> ATTEMPT_RECEIVED (cause "commitment_processed")
    # so the episode CONTINUES into Evidence / Diagnosis / Minimal
    # Intervention instead of holding at COMMITMENT_REQUIRED with an accepted
    # commitment the UI cannot act on.  Invariant B still holds: the full
    # explanation is NOT auto-released by this advance and the phase does NOT
    # jump to AWAITING_REVISION on the commitment turn — the release engine
    # sees ``request.student_attempt`` set from the commitment candidate so
    # the response is at most the minimal-intervention probe, and the student
    # must revise/explain next (required_action == revision).
    if (
        loop_needed
        and not state.get("answer_withheld_by_gate")
        and commitment_submitted_this_turn
        and phase_at_start is LearningPhase.COMMITMENT_REQUIRED
        and commitment is not None
        and commitment.accepted
    ):
        assert_phase_transition(
            phase_at_start,
            LearningPhase.ATTEMPT_RECEIVED,
            cause="commitment_processed",
        )
        durable_phase = durable_phase.model_copy(
            update={
                "phase": LearningPhase.ATTEMPT_RECEIVED,
                "loop_required": True,
                "completed_stages": _append_learning_stages(
                    durable_phase.completed_stages,
                    LearningStage.PREDICT,
                    LearningStage.DIAGNOSE,
                    LearningStage.EXPLORE,
                    *((LearningStage.VERIFY,) if passed_verification else ()),
                ),
                "pending_scientific_request": (
                    request.scientific_request.model_dump(mode="json")
                    if request.scientific_request is not None
                    else durable_phase.pending_scientific_request
                ),
            }
        )

    if (
        loop_needed
        and not state.get("answer_withheld_by_gate")
        and not teach_back_satisfied
        and positive_learning_signal
    ):
        if phase_at_start in {
            LearningPhase.OPEN,
            LearningPhase.COMMITMENT_REQUIRED,
            LearningPhase.ATTEMPT_RECEIVED,
            LearningPhase.INTERVENTION,
        } and LearningNativePolicy.attempt_is_meaningful(request.student_attempt):
            completed = _append_learning_stages(
                durable_phase.completed_stages,
                LearningStage.PREDICT,
                LearningStage.DIAGNOSE,
                LearningStage.EXPLORE,
            )
            if passed_verification:
                completed = _append_learning_stages(completed, LearningStage.VERIFY)
            assert_phase_transition(
                phase_at_start,
                LearningPhase.AWAITING_REVISION,
                cause="verified_attempt",
            )
            durable_phase = durable_phase.model_copy(
                update={
                    "phase": LearningPhase.AWAITING_REVISION,
                    "loop_required": True,
                    "completed_stages": completed,
                    "pending_scientific_request": (
                        request.scientific_request.model_dump(mode="json")
                        if request.scientific_request is not None
                        else durable_phase.pending_scientific_request
                    ),
                }
            )
        elif (
            phase_at_start is LearningPhase.AWAITING_REVISION
            and submission is not None
            and submission.teach_back is not None
            and len(submission.teach_back.reconstruction.strip()) >= 24
        ):
            assert_phase_transition(
                phase_at_start,
                LearningPhase.RECONSTRUCTION_REQUIRED,
                cause="teach_back_requested",
            )
            durable_phase = durable_phase.model_copy(
                update={
                    "phase": LearningPhase.RECONSTRUCTION_REQUIRED,
                    "completed_stages": _append_learning_stages(
                        durable_phase.completed_stages,
                        LearningStage.DIAGNOSE,
                        LearningStage.EXPLORE,
                        *(
                            (LearningStage.VERIFY,)
                            if passed_verification
                            else ()
                        ),
                        LearningStage.EXPLAIN,
                    ),
                }
            )
            teach_back = TeachBackAnalysis(
                covered_relations=[],
                missing_relations=[],
                contradictions=[],
                unsupported_claims=[],
                recommended_probe=(
                    "不看上面的解释，现在用自己的话向第一次学习这个概念的同学"
                    "重构核心机制。"
                ),
                verified=False,
                is_model_inference=False,
            )
        elif (
            phase_at_start is LearningPhase.AWAITING_REVISION
            and submission is not None
            and submission.request_teach_back
        ):
            # PRD V3.3: the student clicked "进入 Teach-Back" from
            # AWAITING_REVISION.  The typed reconstruction has not arrived yet,
            # so the durable phase HOLDS at AWAITING_REVISION while we surface
            # a TeachBackCard (placeholder analysis + deterministic probe) to
            # type into.  The legal teach_back_requested transition fires on
            # the NEXT turn, when the actual reconstruction is submitted (see
            # the branch above).  Advancing on the bare click would consume
            # the transition before the student has produced any artefact.
            teach_back = TeachBackAnalysis(
                covered_relations=[],
                missing_relations=[],
                contradictions=[],
                unsupported_claims=[],
                recommended_probe=(
                    "不看上面的解释，现在用自己的话向第一次学习这个概念的同学"
                    "重构核心机制。"
                ),
                verified=False,
                is_model_inference=False,
            )

    # PRD V3.0 P0-2: Transfer / Solo Mode is driven by the durable phase, not
    # by ad-hoc submission flags.  The durable phase is the single source of
    # truth for whether Solo is active and which transfer task is in flight.
    active_solo: SoloMode | None = None
    if durable_phase.phase is LearningPhase.SOLO_ACTIVE:
        # PRD V3.0 Golden Loop closure: always surface a non-null transfer task
        # when Solo is active so the frontend TransferCard renders.  If the
        # persisted prompt is empty (e.g. corrupted phase JSON), fall back to
        # the deterministic near-transfer prompt.
        solo_prompt = durable_phase.active_transfer_task_prompt or (
            LearningNativePolicy.FALLBACK_TRANSFER_PROMPT
        )
        active_solo = SoloMode(
            status=SoloModeStatus.ACTIVE,
            active_transfer=TransferTask(
                task_id=(
                    durable_phase.active_transfer_task_id
                    if durable_phase.active_transfer_task_id is not None
                    else TransferTask(
                        transfer_type=TransferType.NEAR,
                        prompt=solo_prompt,
                    ).task_id
                ),
                transfer_type=TransferType.NEAR,
                prompt=solo_prompt,
                source_concept_ids=[],
                key_parameters=[],
                expected_observable="",
                verifiable=False,
            ),
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
    # PRD V3.0 Golden Loop closure: when the durable phase is SOLO_ACTIVE,
    # surface the active transfer task on both ``transfer`` and ``solo`` so the
    # frontend can render the TransferCard from either field.  This keeps the
    # ``LearningNativeTurnState`` self-consistent regardless of which field the
    # UI reads.
    if active_solo is not None and active_solo.active_transfer is not None:
        transfer = active_solo.active_transfer
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
        assert_phase_transition(
            durable_phase.phase,
            LearningPhase.ABORTED,
            cause="student_exit",
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
        verified = _attempt_verified(
            state,
            attempt_text,
            durable_phase.transfer_verification,
        )
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
            assert_phase_transition(
                durable_phase.phase,
                LearningPhase.COMPLETE,
                cause="solo_verified",
            )
            durable_phase = durable_phase.model_copy(
                update={
                    "phase": LearningPhase.COMPLETE,
                    "solo_assistance_locked": False,
                    "completed_stages": _append_learning_stages(
                        durable_phase.completed_stages,
                        LearningStage.SOLO,
                    ),
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
    elif teach_back_satisfied:
        # The Teach-Back turn previews the upcoming transfer task but does
        # NOT arm Solo Mode: arming is the student's next explicit action
        # from TRANSFER_REQUIRED (transition F, cause "transfer_armed").
        # Arming in this same turn would assert the illegal
        # RECONSTRUCTION_REQUIRED -> SOLO_ACTIVE transition and kill the
        # stream mid-turn.
        source_concept_ids = [
            node.id for node in evidence_packet.graph_nodes[:6]
        ]
        source_names = [
            node.name for node in evidence_packet.graph_nodes[:6]
        ]
        deterministic_contract = _tunnelling_transfer_contract(
            durable_phase.pending_scientific_request,
            runtime,
        )
        transfer_proposal: TransferProposal | None
        if deterministic_contract is not None:
            # The verification oracle is recomputed deterministically at
            # Solo-arming time; only the task preview is needed here.
            transfer_proposal, _ = deterministic_contract
        else:
            transfer_proposal = await propose_transfer_task(
                source_concept_names=source_names,
                transfer_type=None,
                model_gateway=model_gateway,
            )
        transfer = policy.build_transfer_task(transfer_proposal, source_concept_ids)

    elif (
        submission is not None
        and submission.request_transfer_task
        and phase_at_start is LearningPhase.TRANSFER_REQUIRED
    ):
        source_concept_ids = [
            node.id for node in evidence_packet.graph_nodes[:6]
        ]
        source_names = [
            node.name for node in evidence_packet.graph_nodes[:6]
        ]
        deterministic_contract = _tunnelling_transfer_contract(
            durable_phase.pending_scientific_request,
            runtime,
        )
        transfer_verification: TransferVerificationSpec | None = None
        if deterministic_contract is not None:
            transfer_proposal, transfer_verification = deterministic_contract
        else:
            transfer_proposal = await propose_transfer_task(
                source_concept_names=source_names,
                transfer_type=None,
                model_gateway=model_gateway,
            )
        # PRD V3.0 Golden Loop closure: when the student explicitly requests a
        # transfer task, force-arm Solo Mode even if the model fails to propose
        # a task.  A deterministic near-transfer fallback is used so the Golden
        # Loop can always progress to Solo Mode regardless of model availability.
        transfer, solo, transfer_evidence = policy.prepare_transfer(
            proposal=transfer_proposal,
            source_concept_ids=source_concept_ids,
            active_solo=active_solo,
            force_arm=True,
        )
        if solo.status is SoloModeStatus.ACTIVE and transfer is not None:
            assert_phase_transition(
                phase_at_start,
                LearningPhase.SOLO_ACTIVE,
                cause="transfer_armed",
            )
            durable_phase = DurableLearningPhase(
                phase=LearningPhase.SOLO_ACTIVE,
                active_transfer_task_id=transfer.task_id,
                active_transfer_task_prompt=transfer.prompt,
                solo_started_at=solo.started_at,
                solo_assistance_locked=True,
                expected_attempt_kind="transfer",
                loop_required=True,
                completed_stages=_append_learning_stages(
                    durable_phase.completed_stages,
                    LearningStage.TEACH_BACK,
                    LearningStage.TRANSFER,
                ),
                pending_scientific_request=durable_phase.pending_scientific_request,
                transfer_verification=transfer_verification,
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
    # PRD V3.4: once the accepted commitment has advanced the durable phase to
    # ATTEMPT_RECEIVED, the student-facing state must NOT carry an accepted
    # CommitmentCard (the UI would hide it — the historical orphan).  The
    # card is replaced by the minimal-intervention probe below.
    effective_commitment = suppress_gated_commitment_evidence(commitment, durable_phase.phase)
    native_state = policy.assemble_turn_state(
        commitment=effective_commitment,
        learning_action=learning_action,
        teach_back=teach_back,
        transfer=transfer,
        solo=solo,
        cognitive_mirror=cognitive_mirror,
        evidence_kinds=evidence_kinds,
        durable_phase=durable_phase,
    )
    if native_state is not None and (
        native_state.phase
        in {LearningPhase.ATTEMPT_RECEIVED, LearningPhase.INTERVENTION}
    ):
        # PRD V3.4: after an accepted commitment the episode holds at
        # ATTEMPT_RECEIVED with a MINIMAL-INTERVENTION probe.  Include the
        # interpret probe (the current response's next_question) as the
        # concrete next-step content the student must act on; the backend
        # state remains authoritative, the probe is only the visible question.
        raw_response = state.get("response")
        if raw_response is None:
            probe = ""
        elif isinstance(raw_response, dict):
            probe = str(raw_response.get("next_question") or "")
        else:
            probe = str(getattr(raw_response, "next_question", "") or "")
        native_state = native_state.model_copy(
            update={
                "learning_action": (
                    native_state.learning_action
                    or LearningPolicyAction.GIVE_HINT
                ),
                "minimal_intervention_prompt": (
                    probe or "请先针对当前提示给出你的判断，再继续。"
                ),
            }
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


_NUMERIC_PATTERN = re.compile(
    r"[-+]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][-+]?\d+)?"
)


def _attempt_verified(
    state: TutorState,
    response: str,
    verification: TransferVerificationSpec | None,
) -> bool:
    """Deterministic verification of a Solo transfer attempt.

    PRD V3.3 root-cause #5 fix: this is NO LONGER a substring match against
    passing scientific observations (an accidental phrase could close the
    loop).  The decisive check is a *numeric* match against the persisted
    ``transfer_verification`` oracle: we extract every number from the
    student's free-text response and require at least one to equal
    ``expected_value`` within ``absolute_tolerance``.  A correlated scientific
    PASS for this turn is still required as a secondary signal so a bare
    number without a supporting computation cannot pass.  The LLM never
    asserts verification on its own.

    When ``verification`` is None (legacy conversation with no persisted
    oracle) we fail closed: the loop cannot close without a deterministic
    contract to verify against.
    """

    if verification is None or verification.expected_value is None:
        return False

    # Secondary signal: a scientific tool result for this turn must have PASSed.
    scientific_results = state.get("scientific_results") or []
    has_pass = any(
        result.status is ScientificVerificationStatus.PASS
        for result in scientific_results
    )
    if not has_pass:
        return False

    expected = float(verification.expected_value)
    tolerance = float(verification.absolute_tolerance)
    for match in _NUMERIC_PATTERN.finditer(response):
        try:
            value = float(match.group())
        except ValueError:
            continue
        if abs(value - expected) <= tolerance:
            return True
    return False
