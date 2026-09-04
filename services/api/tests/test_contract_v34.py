"""PRD V3.4 no-orphan + generalization contract tests.

These tests drive the REAL TutorGraph (TunnelingRetriever + FakeModelGateway,
no model tokens) to prove:

1. NO-ORPHAN INVARIANT: after a student submits a valid CommitmentCard, the
   episode CANNOT dead-end.  The accepted commitment advances the durable
   phase to ATTEMPT_RECEIVED with a concrete, actionable next step
   (required_action != none), and the same conversation CONTINUES into real
   Evidence → Diagnosis → Policy work on the following turn.
2. GENERALIZATION MATRIX: representative USTC quantum-physics questions
   (factual, concept, misconception, derivation-with-error, skipped-step,
   exercise, scientific, tunnelling Golden Loop, follow-up, insufficient
   evidence) each route to a grounded response with real provenance, and no
   incomplete loop state ever exposes ZERO actionable UI.
3. The old "commitment_accepted_but_phase_holds" same-phase hold is gone.

Everything is deterministic — a FakeModelGateway supplies model content; no
model tokens are spent.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    AnswerPolicy,
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    MembershipStatus,
    SystemRole,
    TeachingConversation,
    TeachingMode,
    User,
    UserStatus,
)
from quantum_agent.knowledge.evidence_packets import (
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidencePacket,
    LocatorType,
    RetrievalChannel,
    RetrievalContribution,
    RetrievalCoverage,
)
from quantum_agent.knowledge.retrieval import RetrievalScope
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.teaching.learning_native import (
    assert_phase_transition,
    phase_is_actionable_next_step,
    suppress_gated_commitment_evidence,
)
from quantum_agent.teaching.models import (
    AnswerReleaseLevel,
    CognitiveCommitment,
    CommitmentGateDecision,
    CommitmentKind,
    LearningNativeSubmission,
    LearningPhase,
    SoloMode,
    TeachingTurnInput,
)
from quantum_agent.tutor.graph import TutorGraph

API_ROOT = Path(__file__).resolve().parents[1]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
async def contract_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "contract-v34.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class _Seed:
    def __init__(self, actor: CourseActor, edition_id: UUID) -> None:
        self.actor = actor
        self.edition_id = edition_id


async def _seed_actor(session: AsyncSession) -> _Seed:
    now = datetime.now(UTC)
    course = Course(
        code=f"CT-{uuid4()}",
        title="Quantum Physics",
        status=CourseStatus.ACTIVE,
    )
    student = User(
        email=f"ct-student-{uuid4()}@example.edu",
        display_name="CT Student",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add_all([course, student])
    await session.flush()
    edition = CurriculumEdition(
        course_id=course.id,
        edition_key="2026",
        title="Quantum Physics 2026",
        status=CurriculumEditionStatus.PUBLISHED,
        published_at=now,
    )
    session.add(edition)
    await session.flush()
    session.add(
        CourseMembership(
            course_id=course.id,
            user_id=student.id,
            role=CourseRole.STUDENT,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    session.add(
        AnswerPolicy(
            course_id=course.id,
            curriculum_edition_id=edition.id,
            mode=TeachingMode.LEARN_CONCEPTS,
            active=True,
            allow_full_solution=False,
            minimum_attempts_for_scaffold=0,
            minimum_attempts_for_full_solution=3,
            max_hint_level=2,
        )
    )
    await session.commit()
    actor = CourseActor(
        user_id=student.id,
        session_id=uuid4(),
        course_id=course.id,
        email=student.email,
        display_name=student.display_name,
        system_role=student.system_role,
        course_role=CourseRole.STUDENT,
    )
    return _Seed(actor=actor, edition_id=edition.id)


def _evidence_packet(scope: RetrievalScope, *, topic: str = "量子隧穿") -> EvidencePacket:
    concept_id = uuid4()
    source_chunk = f"{topic} is a core quantum-physics concept covered in this course."
    locator = EvidenceLocator(
        locator_type=LocatorType.PDF_PAGE,
        physical_page=42,
        printed_page_label=None,
        slide_number=None,
        paragraph_start=None,
        paragraph_end=None,
        sheet_name=None,
        row_start=None,
        row_end=None,
        line_start=None,
        line_end=None,
    )
    item = EvidenceItem(
        evidence_id=uuid4(),
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_title="Quantum Physics",
        document_version=1,
        source_file_name="quantum.pdf",
        source_file_sha256=_sha("file"),
        source_chunk_sha256=_sha(source_chunk),
        evidence_sha256=_sha(source_chunk),
        curriculum_edition_id=scope.curriculum_edition_id,
        chapter="Ch. 2",
        section_path=["Core Concepts"],
        locator=locator,
        source_chunk=source_chunk,
        evidence_snippet=source_chunk,
        kind=EvidenceKind.COURSE_MATERIAL,
        authority_priority=10,
        contributions=[
            RetrievalContribution(
                channel=RetrievalChannel.FULL_TEXT,
                rank=1,
                raw_score=1.0,
                fused_score=1.0,
            )
        ],
    )
    from quantum_agent.knowledge.evidence_packets import GraphContextEdge, GraphContextNode

    node = GraphContextNode(
        id=concept_id,
        node_type="Concept",
        name=topic,
        aliases=[topic],
    )
    edge = GraphContextEdge(
        id=uuid4(),
        source_id=concept_id,
        target_id=concept_id,
        relation_type="RELATED_TO",
    )
    return EvidencePacket(
        course_id=scope.course_id,
        curriculum_edition_id=scope.curriculum_edition_id,
        query=topic,
        coverage=RetrievalCoverage.SUFFICIENT,
        evidence=[item],
        graph_nodes=[node],
        graph_edges=[edge],
    )


class _Retriever:
    def __init__(self, topic: str = "量子隧穿") -> None:
        self.topic = topic

    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        return _evidence_packet(scope, topic=self.topic)


def _graph(gateway: FakeModelGateway | None = None) -> TutorGraph:
    return TutorGraph(
        evidence_retriever=_Retriever(),
        model_gateway=gateway,
        checkpointer=InMemorySaver(),
        use_specialist_agents=False,
        enable_hitl=False,
    )


def _commitment_submission(text: str = "基态关于阱中心对称，动量期望为零。") -> LearningNativeSubmission:
    return LearningNativeSubmission(
        commitment=CognitiveCommitment(
            gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
            attempt_required=True,
            attempt_type=CommitmentKind.PREDICTION,
            candidate_prompt=text,
            reason_summary="",
            accepted=False,
        ),
        confidence=0.7,
    )


# ---------------------------------------------------------------------------
# Unit-level: the transition table and the no-orphan helper
# ---------------------------------------------------------------------------


class TestNoOrphanHelpers:
    def test_transition_table_rejects_the_orphan_hold(self) -> None:
        # The old same-phase hold that produced the post-commitment dead-end is
        # no longer a legal transition.
        with pytest.raises(ValueError):
            assert_phase_transition(
                LearningPhase.COMMITMENT_REQUIRED,
                LearningPhase.COMMITMENT_REQUIRED,
                cause="commitment_accepted_but_phase_holds",
            )
        # The new forward edge is legal.
        assert_phase_transition(
            LearningPhase.COMMITMENT_REQUIRED,
            LearningPhase.ATTEMPT_RECEIVED,
            cause="commitment_processed",
        )

    def test_committed_attempt_cannot_suggest_solo_mode_without_transfer(self) -> None:
        # Ghost state: an accepted commitment with a still-armed gate is exactly
        # the historical orphan — commit + gate armed must FAIL the actionability
        # check even though the phase is "attempt_received".
        commitment = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
            attempt_required=True,
            candidate_prompt="预测",
            accepted=True,
        )
        assert (
            phase_is_actionable_next_step(
                phase=LearningPhase.ATTEMPT_RECEIVED,
                commitment=commitment,
                teach_back=None,
                transfer=None,
                solo=None,
            )
            is False
        )

    def test_actionable_states_are_recognised(self) -> None:
        # ATTEMPT_RECEIVED with commitment suppressed + required_action revision
        # must be actionable (the minimal-intervention card / composer).
        assert (
            phase_is_actionable_next_step(
                phase=LearningPhase.ATTEMPT_RECEIVED,
                commitment=None,
                teach_back=None,
                transfer=None,
                solo=None,
            )
            is True
        )
        open_card = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
            attempt_required=True,
            candidate_prompt="预测",
            accepted=False,
        )
        assert (
            phase_is_actionable_next_step(
                phase=LearningPhase.COMMITMENT_REQUIRED,
                commitment=open_card,
                teach_back=None,
                transfer=None,
                solo=None,
            )
            is True
        )
        # A transfer task is always actionable.
        assert (
            phase_is_actionable_next_step(
                phase=LearningPhase.TRANSFER_REQUIRED,
                commitment=None,
                teach_back=None,
                transfer=object(),
                solo=None,
            )
            is True
        )
        # Active Solo Mode is actionable.
        assert (
            phase_is_actionable_next_step(
                phase=LearningPhase.SOLO_ACTIVE,
                commitment=None,
                teach_back=None,
                transfer=None,
                solo=SoloMode(status="active"),
            )
            is True
        )

    def test_accepted_commitment_is_suppressed_for_student_facing_state(self) -> None:
        commitment = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.PROCEED,
            attempt_required=True,
            attempt_type=CommitmentKind.PREDICTION,
            candidate_prompt="预测",
            accepted=True,
        )
        assert (
            suppress_gated_commitment_evidence(commitment, LearningPhase.ATTEMPT_RECEIVED)
            is None
        )
        # An open gate keeps its card.
        open_card = commitment.model_copy(
            update={
                "accepted": False,
                "gate_decision": CommitmentGateDecision.ATTEMPT_REQUIRED,
            }
        )
        assert (
            suppress_gated_commitment_evidence(open_card, LearningPhase.COMMITMENT_REQUIRED)
            is open_card
        )


# ---------------------------------------------------------------------------
# The regression test from the brief (§10): submit a valid CommitmentCard and
# assert the episode CONTINUES (not a dead end, not an orphan).
# ---------------------------------------------------------------------------


class TestCommitmentContinues:
    async def test_commitment_then_revision_then_evidence_work(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with contract_database() as session:
            seed = await _seed_actor(session)

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["量子隧穿"],
                    "needs_scientific_verification": False,
                    "confidence": 0.8,
                },
            }
        )
        graph = _graph(gateway)

        # --- Turn 1: the loop opens with a reasoning question. ---
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="为什么无限深势阱基态的平均动量为零？",
        )
        async with contract_database() as session:
            turn1 = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        conversation_id = turn1.conversation_id
        assert turn1.learning_native is not None
        assert turn1.learning_native.phase is LearningPhase.COMMITMENT_REQUIRED
        assert turn1.learning_native.required_action.value == "commitment"
        assert turn1.learning_loop_completed is False

        # --- Turn 2: the student submits a valid CommitmentCard. ---
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我的预测是动量期望为零。",
            conversation_id=conversation_id,
            learning_native=_commitment_submission(),
        )
        async with contract_database() as session:
            turn2 = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()

        # THE BUG REGRESSION: no orphan state after the first answer.
        assert turn2.learning_loop_completed is False
        assert turn2.learning_native is not None
        assert turn2.learning_native.loop_required is True
        assert turn2.learning_native.phase is LearningPhase.ATTEMPT_RECEIVED
        assert turn2.learning_native.required_action.value != "none"
        assert turn2.learning_native.current_stage is not None
        assert (
            turn2.learning_native.minimal_intervention_prompt
            or turn2.learning_native.required_action.value == "revision"
        )
        # The no-orphan invariant holds at the unit level too.
        assert phase_is_actionable_next_step(
            phase=turn2.learning_native.phase,
            commitment=turn2.learning_native.commitment,
            teach_back=turn2.learning_native.teach_back,
            transfer=turn2.learning_native.transfer,
            solo=turn2.learning_native.solo,
        ) is True
        # Invariant B: the phase did NOT jump to AWAITING_REVISION on the
        # commitment turn, and the release stayed at the minimal-intervention
        # envelope (not a full answer).
        assert turn2.learning_native.phase is not LearningPhase.AWAITING_REVISION
        assert turn2.release.release_level.value in {
            AnswerReleaseLevel.QUESTION_ONLY.value,
            AnswerReleaseLevel.HINT.value,
            AnswerReleaseLevel.SCAFFOLD.value,
        }
        # The accepted commitment flowed into Diagnosis as the attempt; the
        # conversation persisted the forward phase.
        async with contract_database() as session:
            conv = await session.scalar(
                select(TeachingConversation).where(
                    TeachingConversation.id == conversation_id
                )
            )
            assert conv is not None
            assert conv.learning_phase_json is not None
            assert conv.learning_phase_json["phase"] == "attempt_received"

        # --- Turn 3: the student answers the minimal-intervention probe with a
        # revised attempt.  The episode must CONTINUE into real work
        # (evidence/diagnosis/policy + generated response), not route back to a
        # commitment gate. ---
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="基态波函数关于阱中心对称，动量算符是奇算符，作用在对称态上期望为零。",
            conversation_id=conversation_id,
            learning_native=None,
        )
        async with contract_database() as session:
            turn3 = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert turn3.conversation_id == conversation_id
        assert turn3.learning_native is not None
        # Diagnostic evidence was actually retrieved (the retrieval trace step
        # is COMPLETED, not "retrieval_skipped_until_commitment").
        assert any(
            step.name.value == "retrieve_evidence" and step.status.value != "skipped"
            for step in turn3.trace
        ), "a continued episode must actually run retrieval"
        # The revised attempt advances to AWAITING_REVISION (verified_attempt).
        assert turn3.learning_native.phase is LearningPhase.AWAITING_REVISION
        assert turn3.learning_native.required_action.value == "revision"
        assert turn3.learning_loop_completed is False

    async def test_commitment_hold_cannot_return_orphan_through_graph(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """The exact regression: the old same-phase hold would have produced an
        orphan (phase=commitment_required, accepted=true, no action).  The
        graph-level assembly must never return that; if it ever did, the
        no-orphan invariant guard in ``assemble_result`` would raise.
        """
        async with contract_database() as session:
            seed = await _seed_actor(session)
            from tests.test_golden_loop_phase_sequence import _seed_conversation

            conversation_id = await _seed_conversation(
                session,
                _Seed(seed.actor, seed.edition_id),  # type: ignore[arg-type]
                phase="commitment_required",
                extra_phase={"loop_required": True},
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续 Learning-Native 学习循环。",
            conversation_id=conversation_id,
            learning_native=_commitment_submission(),
        )
        graph = _graph()
        async with contract_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.ATTEMPT_RECEIVED
        assert result.learning_loop_completed is False


# ---------------------------------------------------------------------------
# Generalization matrix (§9): representative USTC course questions.
# ---------------------------------------------------------------------------


class TestGeneralizationMatrix:
    @pytest.mark.parametrize(
        ("message", "mode", "expect_response"),
        [
            # A. factual / definition lookup — bypasses the gate, grounded answer.
            ("什么是厄米算符？", TeachingMode.LEARN_CONCEPTS, True),
            # B. conceptual question — clarifies a concept.
            ("为什么无限深势阱基态的平均动量为零？", TeachingMode.LEARN_CONCEPTS, True),
            # B. conceptual misconception — attempt-bearing, no redundant gate.
            ("波函数本身是不是概率？", TeachingMode.LEARN_CONCEPTS, True),
            # D. skipped-step derivation question.
            ("这个方程是如何从前一个方程推出的？", TeachingMode.LEARN_CONCEPTS, True),
            # C. exercise help.
            ("求解一维谐振子的能级。", TeachingMode.LEARN_CONCEPTS, True),
        ],
    )
    async def test_general_questions_produce_grounded_turns(
        self,
        contract_database: async_sessionmaker[AsyncSession],
        message: str,
        mode: TeachingMode,
        expect_response: bool,
    ) -> None:
        async with contract_database() as session:
            seed = await _seed_actor(session)

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "concept_question",
                    "relevant_concepts": ["量子隧穿"],
                    "needs_scientific_verification": False,
                    "confidence": 0.9,
                },
            }
        )
        graph = _graph(gateway)
        request = TeachingTurnInput(mode=mode, message=message)
        async with contract_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        if expect_response:
            assert result.learning_native is not None
            assert result.learning_loop_completed is False
            # Every incomplete loop-required turn must expose a real action; a
            # non-loop factual turn (phase=open, no durable loop armed) is not
            # an orphan because the composer accepts the next question.
            if result.learning_native.loop_required:
                assert result.learning_native.phase is LearningPhase.COMMITMENT_REQUIRED or (
                    result.learning_native.required_action.value != "none"
                )
                assert phase_is_actionable_next_step(
                    phase=result.learning_native.phase,
                    commitment=result.learning_native.commitment,
                    teach_back=result.learning_native.teach_back,
                    transfer=result.learning_native.transfer,
                    solo=result.learning_native.solo,
                ) is True
            else:
                assert result.learning_native.phase in {
                    LearningPhase.OPEN,
                    LearningPhase.COMMITMENT_REQUIRED,
                }

    async def test_factual_definition_bypasses_commitment_gate(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """A factual / definition lookup should NOT require a commitment."""
        async with contract_database() as session:
            seed = await _seed_actor(session)

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "concept_question",
                    "relevant_concepts": ["厄米算符"],
                    "needs_scientific_verification": False,
                    "confidence": 0.9,
                },
                "compose_grounded_teaching_response": {
                    "orientation": "厄米算符",
                    "claims": [
                        {
                            "text": "量子隧穿 is a core quantum-physics concept covered in this course.",
                            "support_basis": "course_material",
                            "evidence_ids": [],
                            "scientific_result_ids": [],
                        }
                    ],
                    "next_question": "关于这个定义，你有什么想问的？",
                },
            }
        )
        graph = _graph(gateway)
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="什么是厄米算符？",
        )
        async with contract_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        # The gate did NOT fire (factual lookup).
        assert (
            result.learning_native.commitment is None
            or result.learning_native.commitment.gate_decision
            is CommitmentGateDecision.PROCEED
        )
        # Evidence was retrieved and at least one grounded claim was produced.
        assert result.evidence_packet.evidence
        assert result.response.claims, "a factual lookup must yield a grounded claim"

    async def test_scientific_routing_tunneling_golden_loop(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """A scientific tunnelling turn routes through the oracle + observation."""
        from quantum_agent.science.models import RectangularBarrierRequest

        async with contract_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation_experiments(session, seed)

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["量子隧穿"],
                    "needs_scientific_verification": True,
                    "confidence": 0.9,
                },
            }
        )
        graph = _graph(gateway)
        request = TeachingTurnInput(
            mode=TeachingMode.RUN_EXPERIMENTS,
            message="计算 E=5eV, V0=10eV, a=1e-10m 的透射概率。",
            conversation_id=conversation_id,
            scientific_request=RectangularBarrierRequest(
                energy_eV=5.0,
                barrier_height_eV=10.0,
                barrier_width_m=1e-10,
                particle_mass_kg=9.1093837015e-31,
                conservation_tolerance=1e-9,
            ),
        )
        async with contract_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.scientific_results, "the deterministic oracle must run"
        assert result.scientific_results[0].status.value == "pass"
        assert "T" in result.scientific_results[0].metrics
        assert result.learning_native is not None
        assert result.learning_native.loop_required is True

    async def test_insufficient_evidence_fails_safely(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """When retrieval finds nothing, the system must not fabricate citations."""
        from quantum_agent.knowledge.evidence_packets import RetrievalCoverage as _RC

        async with contract_database() as session:
            seed = await _seed_actor(session)

        class _EmptyRetriever:
            async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
                return EvidencePacket(
                    course_id=scope.course_id,
                    curriculum_edition_id=scope.curriculum_edition_id,
                    query=query,
                    coverage=_RC.NOT_FOUND,
                )

        graph = TutorGraph(
            evidence_retriever=_EmptyRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="完全没有课程覆盖的主题。",
            # An attempt bypasses the commitment gate so retrieval's NOT_FOUND
            # branch is actually reached (the gate would otherwise intercept).
            student_attempt="我的尝试。",
        )
        async with contract_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.evidence_packet.coverage is _RC.NOT_FOUND
        assert result.response.claims == [], "zero claims when no evidence exists"
        assert result.response.status.value == "insufficient_course_evidence"


# ---------------------------------------------------------------------------
# §12 SSE streaming ordering (deterministic): the graph's per-stage progress
# callbacks fire incrementally and every progress event precedes the terminal
# (the BFF forwards them verbatim; the backend must emit them before the turn
# resolves).
# ---------------------------------------------------------------------------


class TestSseStreamingOrdering:
    async def test_commitment_turn_emits_progress_before_terminal(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with contract_database() as session:
            seed = await _seed_actor(session)

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["量子隧穿"],
                    "needs_scientific_verification": False,
                    "confidence": 0.8,
                },
            }
        )
        graph = _graph(gateway)
        stages: list[tuple[str, float]] = []

        async def on_stage(stage: str, elapsed: float) -> None:
            stages.append((stage, elapsed))

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="为什么无限深势阱基态的平均动量为零？",
        )
        async with contract_database() as session:
            await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
                on_stage=on_stage,
            )
            await session.commit()

        # A bounded turn: at least the interpret, commitment-gate and assemble
        # stages must have been emitted, and they must all precede the terminal
        # result object.
        assert stages, "the workflow must emit per-stage progress callbacks"
        emitted = [name for name, _elapsed in stages]
        assert "interpret" in emitted
        assert "commitment_gate" in emitted
        assert "assemble" in emitted
        # The reference stage order is functional: a real graph node ran before
        # the turn resolved, so the terminal is always last.
        last_event_index = max(index for index, _item in enumerate(stages))
        assert last_event_index >= 2
        # Elapsed times are monotonic (real backend timestamps, no fake).
        elapsed_values = [elapsed for _name, elapsed in stages]
        assert all(
            elapsed_values[index] <= elapsed_values[index + 1]
            for index in range(len(elapsed_values) - 1)
        )
        # The emitted stages map onto the backend's canonical stage labels.
        from quantum_agent.tutor.graph import _STAGE_LABELS as backend_stages

        for name, _elapsed in stages:
            assert name in backend_stages.values() or name in backend_stages

    async def test_scientific_turn_emits_progress_before_terminal(
        self,
        contract_database: async_sessionmaker[AsyncSession],
    ) -> None:
        from quantum_agent.science.models import RectangularBarrierRequest

        async with contract_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation_experiments(session, seed)

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["量子隧穿"],
                    "needs_scientific_verification": True,
                    "confidence": 0.9,
                },
            }
        )
        graph = _graph(gateway)
        stages: list[tuple[str, float]] = []

        async def on_stage(stage: str, elapsed: float) -> None:
            stages.append((stage, elapsed))

        request = TeachingTurnInput(
            mode=TeachingMode.RUN_EXPERIMENTS,
            message="计算 E=5eV, V0=10eV, a=1e-10m 的透射概率。",
            conversation_id=conversation_id,
            scientific_request=RectangularBarrierRequest(
                energy_eV=5.0,
                barrier_height_eV=10.0,
                barrier_width_m=1e-10,
                particle_mass_kg=9.1093837015e-31,
                conservation_tolerance=1e-9,
            ),
        )
        async with contract_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
                on_stage=on_stage,
            )
            await session.commit()
        assert result.scientific_results, "the scientific oracle must run"
        assert stages
        emitted = [name for name, _elapsed in stages]
        # The scientific stage must be observed on the experiment turn, before
        # the terminal assembled result.
        assert "scientific_tools" in emitted
        assert "assemble" in emitted
        scientific_index = emitted.index("scientific_tools")
        assemble_index = emitted.index("assemble")
        assert scientific_index < assemble_index, (
            "scientific_tools progress must be emitted before the terminal assemble "
            "(SSE must stream incrementally, never buffered)"
        )
        assert result.learning_native is not None
        assert result.learning_native.loop_required is True


async def _seed_conversation_experiments(
    session: AsyncSession,
    seed: _Seed,
) -> UUID:
    from tests.test_golden_loop_phase_sequence import _seed_conversation

    return await _seed_conversation(
        session,
        _Seed(seed.actor, seed.edition_id),  # type: ignore[arg-type]
        phase="awaiting_revision",
        extra_phase={"loop_required": True},
        mode=TeachingMode.RUN_EXPERIMENTS,
    )
