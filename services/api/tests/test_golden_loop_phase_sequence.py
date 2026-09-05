"""Phase 6 anti-skip integration tests for the V3.3 Golden Loop sprint.

These tests assert the brief's non-skipping invariants A-I against the REAL
TutorGraph (TunnelingRetriever + FakeModelGateway, no model tokens).  They
drive a single conversation through the durable LearningPhase sequence and
read ``conv.learning_phase_json["phase"]`` after each turn.  Every durable
phase mutation passes through ``assert_phase_transition``; these tests prove
that forbidden transitions are rejected and required student actions cannot
be bypassed.
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
from quantum_agent.coding import CodingAgent, SubprocessSandbox
from quantum_agent.db_models import (
    AnswerPolicy,
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    LearningEvidence,
    LearningEvidenceKind,
    MembershipStatus,
    SystemRole,
    TeachingConversation,
    TeachingConversationStatus,
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
from quantum_agent.science.models import (
    ScientificVerificationKind,
    ScientificVerificationMethod,
    ScientificVerificationResult,
    ScientificVerificationStatus,
    ToolIdentity,
)
from quantum_agent.teaching.learning_native import (
    assert_phase_transition,
)
from quantum_agent.teaching.models import (
    AnswerReleaseLevel,
    CognitiveCommitment,
    CommitmentGateDecision,
    CommitmentKind,
    ConceptStateLabel,
    LearningNativeSubmission,
    LearningPhase,
    SoloAttemptSubmission,
    SoloModeStatus,
    TeachBackSubmission,
    TeachingTurnInput,
    TransferVerificationSpec,
)
from quantum_agent.tutor.graph import TutorGraph

API_ROOT = Path(__file__).resolve().parents[1]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
async def golden_loop_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "golden-loop.sqlite3"
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
        code=f"GL-{uuid4()}",
        title="Quantum Physics",
        status=CourseStatus.ACTIVE,
    )
    student = User(
        email=f"gl-student-{uuid4()}@example.edu",
        display_name="GL Student",
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


async def _seed_conversation(
    session: AsyncSession,
    seed: _Seed,
    *,
    phase: str,
    extra_phase: dict[str, object] | None = None,
    mode: TeachingMode = TeachingMode.LEARN_CONCEPTS,
) -> UUID:
    learning_phase_json: dict[str, object] = {"phase": phase}
    if extra_phase is not None:
        learning_phase_json.update(extra_phase)
    conversation = TeachingConversation(
        course_id=seed.actor.course_id,
        curriculum_edition_id=seed.edition_id,
        student_user_id=seed.actor.user_id,
        mode=mode,
        status=TeachingConversationStatus.ACTIVE,
        last_activity_at=datetime.now(UTC),
        learning_phase_json=learning_phase_json,
    )
    session.add(conversation)
    await session.flush()
    conversation_id = conversation.id
    await session.commit()
    return conversation_id


def _evidence_packet(scope: RetrievalScope) -> EvidencePacket:
    concept_id = uuid4()
    source_chunk = "Tunneling through a rectangular barrier."
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
        section_path=["Tunneling"],
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
        name="量子隧穿",
        aliases=["tunneling"],
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
        query="tunneling",
        coverage=RetrievalCoverage.SUFFICIENT,
        evidence=[item],
        graph_nodes=[node],
        graph_edges=[edge],
    )


class _TunnelingRetriever:
    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        return _evidence_packet(scope)


async def _read_phase(
    database: async_sessionmaker[AsyncSession],
    conversation_id: UUID,
) -> str:
    async with database() as session:
        conv = await session.scalar(
            select(TeachingConversation).where(
                TeachingConversation.id == conversation_id
            )
        )
        assert conv is not None
        assert conv.learning_phase_json is not None
        return conv.learning_phase_json["phase"]


class _NotFoundRetriever:
    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        return EvidencePacket(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            query=query,
            coverage=RetrievalCoverage.NOT_FOUND,
        )


def _graph(
    gateway: FakeModelGateway | None = None,
    retriever: _TunnelingRetriever | _NotFoundRetriever | None = None,
    coding_agent: CodingAgent | None = None,
) -> TutorGraph:
    return TutorGraph(
        evidence_retriever=retriever if retriever is not None else _TunnelingRetriever(),
        model_gateway=gateway,
        coding_agent=coding_agent,
        checkpointer=InMemorySaver(),
        use_specialist_agents=False,
        enable_hitl=False,
    )


class TestGoldenLoopAntiSkip:
    """The brief's 10 anti-skip invariants + 2 negative skip tests."""

    async def test_concept_question_cannot_complete_without_commitment(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)

        result = await _graph().run_turn_via_fixture(
            session_factory=golden_loop_database,
            seed=seed,
            message="为什么无限深势阱基态的平均动量为零？",
        )
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.COMMITMENT_REQUIRED
        assert result.learning_native.required_action.value == "commitment"
        assert result.response.claims == []
        assert result.learning_loop_completed is False

    async def test_commitment_advances_and_episode_continues(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """PRD V3.4 regression: an accepted commitment is the student's initial
        attempt, NOT the end of the episode.  It must advance the durable phase
        COMMITMENT_REQUIRED -> ATTEMPT_RECEIVED (cause ``commitment_processed``)
        so the episode CONTINUES into Evidence / Diagnosis / Minimal
        Intervention — the UI must never be left with zero actionable steps
        (the reported "frontend ends after I answer the first question" bug).
        Invariant B still holds: the phase does NOT jump to AWAITING_REVISION
        and the full explanation is NOT auto-released by the commitment alone.
        """
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="commitment_required",
                extra_phase={
                    "loop_required": True,
                    "pending_scientific_request": {},
                },
            )

        class _ProbeGateway(FakeModelGateway):
            """Counts whether the full-explain compose was called on the
            commitment turn; over an interpretation fallback it reports the
            exercise classification so the release engine caps at SCAFFOLD."""

            def __init__(self) -> None:
                super().__init__(
                    {
                        "interpret_teaching_turn": {
                            "task_kind": "exercise_help",
                            "relevant_concepts": ["tunnelling"],
                            "needs_scientific_verification": False,
                            "confidence": 0.8,
                        }
                    }
                )
                self.compose_calls = 0

            async def structured_generate(self, *args: object, **kwargs: object) -> object:
                task = kwargs.get("task") or (args[0] if args else "")
                if task == "compose_grounded_teaching_response":
                    self.compose_calls += 1
                return await super().structured_generate(*args, **kwargs)

        gateway = _ProbeGateway()
        submission = LearningNativeSubmission(
            commitment=CognitiveCommitment(
                gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
                attempt_required=True,
                attempt_type=CommitmentKind.PREDICTION,
                candidate_prompt="基态对称，动量期望为零。",
                reason_summary="",
                accepted=False,
            ),
            confidence=0.7,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我的预测是动量期望为零。",
            conversation_id=conversation_id,
            learning_native=submission,
        )
        async with golden_loop_database() as session:
            result = await _graph(gateway=gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # The episode is NOT complete; but it is NOT an orphan either.
        assert result.learning_loop_completed is False
        assert result.learning_native is not None
        assert result.learning_native.loop_required is True
        # The accepted commitment advances the durable phase forward.
        assert result.learning_native.phase is LearningPhase.ATTEMPT_RECEIVED
        assert (
            await _read_phase(golden_loop_database, conversation_id)
            == "attempt_received"
        )
        # At least one concrete next step MUST be visible/actionable
        # (no-orphan invariant).
        assert result.learning_native.required_action.value != "none"
        assert result.learning_native.current_stage is not None
        # Invariant B: the phase does NOT jump to AWAITING_REVISION and the
        # full explanation is NOT auto-released on the commitment turn.  The
        # release stays at the minimal-intervention envelope (SCAFFOLD max).
        assert result.learning_native.phase is not LearningPhase.AWAITING_REVISION
        assert result.release.release_level.value in {
            AnswerReleaseLevel.QUESTION_ONLY.value,
            AnswerReleaseLevel.HINT.value,
            AnswerReleaseLevel.SCAFFOLD.value,
        }
        # The commitment was accepted and flows into diagnosis as the attempt,
        # but the UI must not re-render an invisible accepted card.
        if result.learning_native.commitment is not None:
            assert result.learning_native.commitment.accepted is True
        # The episode CAN continue: the next turn with a revised attempt must
        # run the real evidence/diagnosis/policy work (retrieve trace step is
        # no longer SKIPPED as "retrieval_skipped_until_commitment").
        assert not any(
            "retrieval_skipped_until_commitment" in step.detail
            for step in result.trace
        ), "a continued episode must actually run retrieval"

    async def test_commitment_hold_is_rejected_by_transition_table(
        self,
    ) -> None:
        # PRD V3.4: the old "commitment_accepted_but_phase_holds" same-phase
        # hold is REMOVED from the legal transition table — it was the machine
        # state that produced the post-commitment orphan.  Assert it is no
        # longer a legal transition.
        import pytest as _pytest

        with _pytest.raises(ValueError):
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

    async def test_explanation_does_not_imply_mastery(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="awaiting_revision",
                extra_phase={"loop_required": True},
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我用自己的话解释：基态关于势阱中心对称，动量算符是奇算符，期望为零。",
            conversation_id=conversation_id,
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        mirror = result.learning_native.cognitive_mirror
        if mirror is not None:
            for state in mirror.concept_states:
                assert state.label is not ConceptStateLabel.DEMONSTRATED
                assert state.label is not ConceptStateLabel.TRANSFER_READY

    async def test_experiment_turn_after_commitment_runs_scientific_tools(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # PRD V3.3 Golden Loop closure: once the durable phase has advanced to
        # AWAITING_REVISION the commitment gate must NOT re-arm on a later
        # turn.  An experiment turn (run_experiments + rectangular barrier)
        # must run the deterministic scientific toolbox even without a new
        # student attempt; re-arming the gate would withhold the release and
        # skip the scientific tools, blocking the Coding Agent stage.
        from quantum_agent.llm.gateway import FakeModelGateway
        from quantum_agent.science.models import RectangularBarrierRequest

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["tunnelling"],
                    "needs_scientific_verification": True,
                    "confidence": 0.8,
                },
            }
        )
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="awaiting_revision",
                extra_phase={"loop_required": True},
                mode=TeachingMode.RUN_EXPERIMENTS,
            )
            session.add(
                AnswerPolicy(
                    course_id=seed.actor.course_id,
                    curriculum_edition_id=seed.edition_id,
                    mode=TeachingMode.RUN_EXPERIMENTS,
                    active=True,
                    allow_full_solution=False,
                    minimum_attempts_for_scaffold=0,
                    minimum_attempts_for_full_solution=3,
                    max_hint_level=2,
                )
            )
            await session.commit()

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
        async with golden_loop_database() as session:
            result = await _graph(gateway=gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # The release must NOT be commitment-gated question_only, and the
        # scientific toolbox must have run (SCAFFOLD or higher releases the
        # experiment; the oracle PASSes with real T metrics).
        assert result.release.release_level.value in {
            AnswerReleaseLevel.SCAFFOLD.value,
            AnswerReleaseLevel.FULL_EXPLANATION.value,
            AnswerReleaseLevel.FULL_SOLUTION.value,
        }
        assert result.scientific_results, "the deterministic oracle must run"
        assert result.scientific_results[-1].status is ScientificVerificationStatus.PASS
        assert "T" in result.scientific_results[-1].metrics

    async def test_teach_back_required_for_configured_concept(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="awaiting_revision",
                extra_phase={"loop_required": True},
            )

        # A plain message WITHOUT a typed teach_back submission must NOT
        # advance the phase to reconstruction_required.
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续讲。",
            conversation_id=conversation_id,
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase == "awaiting_revision"
        assert result.learning_native is not None
        assert result.learning_native.phase is not LearningPhase.RECONSTRUCTION_REQUIRED

    async def test_transfer_assigned_is_not_transfer_verified(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="transfer_required",
                extra_phase={"loop_required": True},
            )

        # Drive a real turn with a plain message and NO solo_attempt submission.
        # The backend must keep the phase at transfer_required and must NOT
        # write TRANSFER_VERIFIED evidence, because verification requires a
        # numeric submission matching the oracle plus a correlated scientific
        # PASS (invariant F: TRANSFER_ASSIGNED != TRANSFER_VERIFIED).  A plain
        # dialogue message must not be misread as a transfer attempt.
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我打算先回顾一下势垒宽度的内容。",
            conversation_id=conversation_id,
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase == "transfer_required"
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.TRANSFER_REQUIRED
        assert result.learning_loop_completed is False
        # A turn ran; nevertheless no TRANSFER_VERIFIED evidence may exist.
        async with golden_loop_database() as session:
            from quantum_agent.db_models import TeachingTurn

            rows = (
                await session.execute(
                    select(LearningEvidence)
                    .join(TeachingTurn, TeachingTurn.id == LearningEvidence.teaching_turn_id)
                    .where(
                        TeachingTurn.conversation_id == conversation_id,
                        LearningEvidence.kind == LearningEvidenceKind.TRANSFER_VERIFIED,
                    )
                )
            ).scalars().all()
        assert rows == []

    async def test_solo_lock_blocks_normal_answer_generation(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "解释不同势垒宽度下透射率的变化趋势。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )

        class _CallTrackingGateway(FakeModelGateway):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)
                self.compose_calls = 0

            async def structured_generate(self, *args: object, **kwargs: object) -> object:
                task = kwargs.get("task") or (args[0] if args else "")
                if task == "compose_grounded_teaching_response":
                    self.compose_calls += 1
                return await super().structured_generate(*args, **kwargs)

        gateway = _CallTrackingGateway()
        graph = _graph(gateway)
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="请直接告诉我答案。",
            conversation_id=conversation_id,
        )
        async with golden_loop_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert gateway.compose_calls == 0
        assert result.response.claims == []

    async def test_cognitive_mirror_requires_verified_evidence(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Build a mirror after only an unverified transfer attempt.  The mirror
        # must not mark unaided_retrieval True or label the concept
        # transfer_ready, because the attempt was TRANSFER_ATTEMPTED not
        # TRANSFER_VERIFIED.
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "迁移任务。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的尝试。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="透射率随势垒宽度增加而指数下降。",
                    confidence=0.3,
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status.value == "active"
        mirror = result.learning_native.cognitive_mirror
        if mirror is not None:
            for state in mirror.concept_states:
                assert state.unaided_retrieval is not True
                assert state.label is not ConceptStateLabel.TRANSFER_READY

    async def test_complete_unreachable_with_pending_required_action(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Solo active WITHOUT a persisted transfer_verification oracle: the
        # numeric verifier fails closed, so the phase cannot reach complete
        # even if the student's response contains a number.
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "迁移任务。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我的答案是 0.001。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="透射率 T ≈ 0.001。",
                    confidence=0.5,
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase == "solo_active"
        assert result.learning_loop_completed is False

    async def test_real_transfer_submission_writes_TRANSFER_VERIFIED(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # The decisive numeric verifier + transition guard, exercised directly.
        # The graph-level integration of a PASS scientific result requires a
        # valid scientific_request + oracle; here we prove the verifier and
        # guard accept a correct numeric submission against a persisted oracle,
        # and reject a wrong one.
        verification = TransferVerificationSpec(
            scientific_request={},
            metric_name="transmission_coefficient",
            expected_value=0.001,
            absolute_tolerance=1e-4,
        )
        # A passing scientific result for this turn (correlated PASS signal).
        passing_result = ScientificVerificationResult(
            kind=ScientificVerificationKind.RECTANGULAR_BARRIER_TUNNELLING,
            method=ScientificVerificationMethod.NUMERICAL,
            status=ScientificVerificationStatus.PASS,
            tool=ToolIdentity(name="barrier-oracle", version="1.0.0"),
            inputs_sha256="a" * 64,
            observations=["T within tolerance of oracle."],
            limitations=["deterministic oracle"],
        )
        from quantum_agent.tutor.nodes import _attempt_verified

        state_with_pass = {"scientific_results": [passing_result]}
        assert _attempt_verified(state_with_pass, "T ≈ 0.001", verification) is True
        assert _attempt_verified(state_with_pass, "随便写的答案", verification) is False
        # Without the oracle, fail closed.
        assert _attempt_verified(state_with_pass, "T ≈ 0.001", None) is False
        # Without a PASS scientific result, fail closed.
        assert _attempt_verified({}, "T ≈ 0.001", verification) is False
        # The transition guard accepts the legal solo_verified transition.
        assert_phase_transition(
            LearningPhase.SOLO_ACTIVE,
            LearningPhase.COMPLETE,
            cause="solo_verified",
        )
        # And rejects an illegal cause.
        with pytest.raises(ValueError):
            assert_phase_transition(
                LearningPhase.SOLO_ACTIVE,
                LearningPhase.COMPLETE,
                cause="gate_fired",
            )

    async def test_correct_solo_attempt_closes_loop_through_graph(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Release-review P0 regression: a correct Solo/Transfer submission
        # must close the loop END-TO-END through the graph.  Previously the
        # commitment gate re-armed on top of the solo submission (no
        # ``student_attempt``), the deterministic oracle was skipped in
        # ``scientific_tools_node``, and ``_attempt_verified`` could never
        # see a PASS signal — a numerically correct solo answer was judged
        # unverified and the Golden Loop could not close.
        from quantum_agent.science.models import RectangularBarrierRequest
        from quantum_agent.science.toolbox import ScientificToolbox

        barrier_request = RectangularBarrierRequest(
            energy_eV=2.0,
            barrier_height_eV=5.0,
            barrier_width_m=1e-9,
            particle_mass_kg=9.1093837015e-31,
        )
        oracle = ScientificToolbox().verify(barrier_request)
        assert oracle.status is ScientificVerificationStatus.PASS
        expected_t = float(oracle.metrics["T"])
        assert 0.0 < expected_t < 1.0

        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "迁移任务：计算同一势垒的透射率。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                    "transfer_verification": {
                        "scientific_request": barrier_request.model_dump(mode="json"),
                        "metric_name": "T",
                        "expected_value": expected_t,
                        "absolute_tolerance": 1e-9,
                    },
                },
            )

        # A WRONG numeric answer must not close the loop.
        wrong = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我独立完成的迁移任务。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="透射率 T = 0.9",
                    confidence=0.5,
                )
            ),
        )
        async with golden_loop_database() as session:
            wrong_result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=wrong,
            )
            await session.commit()
        assert await _read_phase(golden_loop_database, conversation_id) == "solo_active"
        assert wrong_result.learning_loop_completed is False

        # The CORRECT numeric answer closes the loop: SOLO_ACTIVE -> COMPLETE.
        correct = wrong.model_copy(
            update={
                "learning_native": LearningNativeSubmission(
                    solo_attempt=SoloAttemptSubmission(
                        response=f"透射率 T = {expected_t!r}",
                        confidence=0.8,
                    )
                )
            }
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=correct,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.COMPLETE
        assert result.learning_loop_completed is True
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status.value == "exited"
        assert await _read_phase(golden_loop_database, conversation_id) == "complete"

    async def test_solo_verification_does_not_depend_on_retrieval_coverage(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Release-review P0 companion fix: the solo submission message can be
        # a generic continuation ("继续 Learning-Native 学习循环。"), for which
        # retrieval returns NOT_FOUND.  The deterministic oracle must still
        # run so a correct independent answer can close the loop.
        from quantum_agent.science.models import RectangularBarrierRequest
        from quantum_agent.science.toolbox import ScientificToolbox

        barrier_request = RectangularBarrierRequest(
            energy_eV=2.0,
            barrier_height_eV=5.0,
            barrier_width_m=1e-9,
            particle_mass_kg=9.1093837015e-31,
        )
        oracle = ScientificToolbox().verify(barrier_request)
        assert oracle.status is ScientificVerificationStatus.PASS
        expected_t = float(oracle.metrics["T"])

        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "迁移任务：计算同一势垒的透射率。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                    "transfer_verification": {
                        "scientific_request": barrier_request.model_dump(mode="json"),
                        "metric_name": "T",
                        "expected_value": expected_t,
                        "absolute_tolerance": 1e-9,
                    },
                },
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续 Learning-Native 学习循环。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response=f"透射率 T = {expected_t!r}",
                    confidence=0.8,
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(retriever=_NotFoundRetriever()).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.COMPLETE
        assert result.learning_loop_completed is True
        assert await _read_phase(golden_loop_database, conversation_id) == "complete"

    async def test_teach_back_previews_transfer_without_arming_solo(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Release-review P0 fix: the teach-back turn transitions
        # RECONSTRUCTION_REQUIRED -> TRANSFER_REQUIRED and previews the
        # transfer task, but must NOT arm Solo in the same turn (that would
        # assert the illegal RECONSTRUCTION_REQUIRED -> SOLO_ACTIVE edge and
        # kill the stream).  Solo arming is the next explicit action.
        from quantum_agent.science.models import RectangularBarrierRequest

        barrier_request = RectangularBarrierRequest(
            energy_eV=5.0,
            barrier_height_eV=10.0,
            barrier_width_m=1e-10,
            particle_mass_kg=9.1093837015e-31,
        )
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="reconstruction_required",
                extra_phase={
                    "loop_required": True,
                    "pending_scientific_request": barrier_request.model_dump(
                        mode="json"
                    ),
                },
            )

        gateway = FakeModelGateway(
            responses={
                "analyze_teach_back_reconstruction": {
                    "covered_relations": [
                        {
                            "relation": "covered",
                            "description": "势垒内波函数指数衰减与右侧非零振幅。",
                        }
                    ],
                    "missing_relations": [],
                    "contradictions": [],
                    "unsupported_claims": [],
                    "recommended_probe": "",
                }
            }
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的重构。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                teach_back=TeachBackSubmission(
                    reconstruction=(
                        "E<V0 时波函数在势垒内指数衰减但不为零，因此右侧仍有"
                        "小振幅，透射概率是一个小正数。"
                    )
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.TRANSFER_REQUIRED
        assert result.learning_native.transfer is not None
        assert (
            result.learning_native.solo is None
            or result.learning_native.solo.status is not SoloModeStatus.ACTIVE
        )
        assert (
            await _read_phase(golden_loop_database, conversation_id)
            == "transfer_required"
        )

    async def test_contradictory_teach_back_is_rejected_and_phase_holds(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Release-review P1 fix: length alone never advances the loop.  A
        # reconstruction the analysis flags as contradictory must keep the
        # phase at RECONSTRUCTION_REQUIRED (legal same-phase hold).
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="reconstruction_required",
                extra_phase={"loop_required": True},
            )

        gateway = FakeModelGateway(
            responses={
                "analyze_teach_back_reconstruction": {
                    "covered_relations": [],
                    "missing_relations": [],
                    "contradictions": [
                        {
                            "relation": "contradictory",
                            "description": "声称 E<V0 时透射概率恒为零。",
                        }
                    ],
                    "unsupported_claims": [],
                    "recommended_probe": "请重新考虑势垒内的波函数行为。",
                }
            }
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的重构。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                teach_back=TeachBackSubmission(
                    reconstruction=(
                        "因为能量小于势垒高度，粒子完全不可能出现在右侧，"
                        "透射概率恒为零。"
                    )
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert (
            result.learning_native.phase is LearningPhase.RECONSTRUCTION_REQUIRED
        )
        assert result.learning_native.teach_back is not None
        assert result.learning_native.teach_back.recommended_probe
        assert (
            await _read_phase(golden_loop_database, conversation_id)
            == "reconstruction_required"
        )

    async def test_degenerate_empty_analysis_does_not_deadlock_the_loop(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Live E2E observation (2026-09-05): the real USTC model returned an
        # ENTIRELY empty analysis (covered=0, missing=0, contradictions=0,
        # unsupported=0) on a substantial reconstruction.  With the old
        # fallback (only proposal is None) the loop deadlocked at
        # reconstruction_required: the gate failed closed, no contradictions
        # were reported, and the student had no way forward.  A substantial
        # reconstruction plus a degenerate empty analysis must advance
        # deterministically (same guarantee as the model-unavailable fallback),
        # while a SHORT reconstruction still holds (length alone never passes).
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="reconstruction_required",
                extra_phase={"loop_required": True},
            )

        gateway = FakeModelGateway(
            responses={
                "analyze_teach_back_reconstruction": {
                    "covered_relations": [],
                    "missing_relations": [],
                    "contradictions": [],
                    "unsupported_claims": [],
                    "recommended_probe": "",
                }
            }
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的重构。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                teach_back=TeachBackSubmission(
                    reconstruction=(
                        "E<V0 时波函数在势垒内不是突变为零，而是指数衰减；衰减后的"
                        "振幅在势垒右侧仍然非零，因此透射概率是一个很小的正数，"
                        "而不是零。这就是量子隧穿的波动图像。"
                    )
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.TRANSFER_REQUIRED
        assert (
            await _read_phase(golden_loop_database, conversation_id)
            == "transfer_required"
        )

    async def test_degenerate_empty_analysis_short_reconstruction_still_holds(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # The degenerate-analysis fallback requires a substantial
        # reconstruction (>= 24 chars, the analysis-entry bar).  A trivial one
        # with an empty analysis must still hold at RECONSTRUCTION_REQUIRED —
        # length alone never advances the loop.
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="reconstruction_required",
                extra_phase={"loop_required": True},
            )

        gateway = FakeModelGateway(
            responses={
                "analyze_teach_back_reconstruction": {
                    "covered_relations": [],
                    "missing_relations": [],
                    "contradictions": [],
                    "unsupported_claims": [],
                    "recommended_probe": "",
                }
            }
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的重构。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                teach_back=TeachBackSubmission(reconstruction="波函数指数衰减。")
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.RECONSTRUCTION_REQUIRED
        assert (
            await _read_phase(golden_loop_database, conversation_id)
            == "reconstruction_required"
        )

    async def test_solo_oracle_results_are_redacted_in_the_response(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # Release-review P1 fix: the solo oracle runs so deterministic
        # verification is possible, but the exact oracle value must not leak
        # into the turn response before the student's attempt passes.  A wrong
        # attempt must yield a PASS-status scientific result with NO metrics.
        from quantum_agent.science.models import RectangularBarrierRequest
        from quantum_agent.science.toolbox import ScientificToolbox

        barrier_request = RectangularBarrierRequest(
            energy_eV=2.0,
            barrier_height_eV=5.0,
            barrier_width_m=1e-9,
            particle_mass_kg=9.1093837015e-31,
        )
        oracle = ScientificToolbox().verify(barrier_request)
        expected_t = float(oracle.metrics["T"])

        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "迁移任务：计算同一势垒的透射率。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                    "transfer_verification": {
                        "scientific_request": barrier_request.model_dump(mode="json"),
                        "metric_name": "T",
                        "expected_value": expected_t,
                        "absolute_tolerance": 1e-9,
                    },
                },
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续 Learning-Native 学习循环。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="透射率 T = 0.9",
                    confidence=0.6,
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(retriever=_NotFoundRetriever()).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.SOLO_ACTIVE
        assert result.scientific_results, "the solo oracle must still run"
        for item in result.scientific_results:
            assert item.status is ScientificVerificationStatus.PASS
            assert item.metrics == {}, "oracle metrics must be redacted pre-verification"
            assert item.visualization is None

    async def test_solo_turn_never_leaks_coding_agent_oracle_metrics(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # PRD V3.3 Solo shield: the Coding Agent must NOT run during Solo
        # verification even though the restored transfer request is a
        # RectangularBarrierRequest.  Its code_artifact would carry the
        # correct oracle T and reach the browser before the independent
        # attempt passes (a real answer leak the scientific_results redaction
        # alone cannot contain).
        from quantum_agent.coding.models import CodeArtifact, CodeLanguage
        from quantum_agent.science.models import RectangularBarrierRequest
        from quantum_agent.science.toolbox import ScientificToolbox

        barrier_request = RectangularBarrierRequest(
            energy_eV=2.0,
            barrier_height_eV=5.0,
            barrier_width_m=1e-9,
            particle_mass_kg=9.1093837015e-31,
        )
        oracle = ScientificToolbox().verify(barrier_request)
        expected_t = float(oracle.metrics["T"])

        artifact = CodeArtifact(
            language=CodeLanguage.PYTHON,
            purpose="rectangular barrier tunnelling T/R",
            code="import math\nprint('### METRICS_JSON: {\"T\": 0.123}')\n",
            expected_outputs=["T", "R"],
            verification_plan="match oracle within 1e-6",
        )
        gateway = FakeModelGateway(
            {
                "generate_coding_artifact": artifact.model_dump(mode="json"),
            }
        )
        coding_agent = CodingAgent(sandbox=SubprocessSandbox())

        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "迁移任务：计算同一势垒的透射率。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                    "transfer_verification": {
                        "scientific_request": barrier_request.model_dump(mode="json"),
                        "metric_name": "T",
                        "expected_value": expected_t,
                        "absolute_tolerance": 1e-9,
                    },
                },
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续 Learning-Native 学习循环。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="透射率 T = 0.9",
                    confidence=0.6,
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph(
                gateway=gateway,
                retriever=_NotFoundRetriever(),
                coding_agent=coding_agent,
            ).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.phase is LearningPhase.SOLO_ACTIVE
        # Deterministic oracle ran; a (failing) coding artifact must NOT exist.
        assert result.scientific_results, "the solo oracle must still run"
        assert result.code_artifact is None, (
            "the Coding Agent must not run during Solo verification: its "
            "oracle_metrics would leak the correct answer before the student "
            "attempt passes"
        )

    async def test_learning_phase_survives_refresh_and_new_request(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="awaiting_revision",
                extra_phase={"loop_required": True},
            )

        # A turn that does NOT advance (plain message, no teach_back).
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续。",
            conversation_id=conversation_id,
        )
        async with golden_loop_database() as session:
            await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # Open a NEW session (simulating refresh) and read the durable phase.
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase == "awaiting_revision"

    async def test_cannot_skip_commitment_to_transfer(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="commitment_required",
                extra_phase={"loop_required": True},
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="给我一个迁移任务。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(request_transfer_task=True),
        )
        # The transfer_armed branch is gated on phase_at_start being
        # TRANSFER_REQUIRED, so from commitment_required the request is
        # ignored (fail-closed) and the phase does NOT advance.  The turn
        # completes normally; the invariant is that the durable phase is
        # unchanged.
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase == "commitment_required"
        assert result.learning_native is not None
        assert result.learning_native.phase is not LearningPhase.SOLO_ACTIVE
        assert result.learning_native.phase is not LearningPhase.TRANSFER_REQUIRED
        assert result.learning_loop_completed is False

    async def test_cannot_skip_commitment_to_complete(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="commitment_required",
                extra_phase={"loop_required": True},
            )

        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="T ≈ 0.001",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="T ≈ 0.001",
                    confidence=0.9,
                )
            ),
        )
        async with golden_loop_database() as session:
            result = await _graph().run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase == "commitment_required"
        assert result.learning_loop_completed is False
        async with golden_loop_database() as session:
            from quantum_agent.db_models import TeachingTurn

            verified = (
                await session.execute(
                    select(LearningEvidence)
                    .join(TeachingTurn, TeachingTurn.id == LearningEvidence.teaching_turn_id)
                    .where(
                        TeachingTurn.conversation_id == conversation_id,
                        LearningEvidence.kind == LearningEvidenceKind.TRANSFER_VERIFIED,
                    )
                )
            ).scalars().all()
        assert verified == []

    async def test_open_to_complete_is_rejected_at_guard(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        # The spec's negative skip test: a backend that tries to jump directly
        # from OPEN to COMPLETE must be rejected by the transition guard.  This
        # is the guard-level assertion that the allowed-set has no
        # (OPEN, COMPLETE, *) edge for any cause.
        for cause in (
            "gate_fired",
            "verified_attempt",
            "teach_back_requested",
            "teach_back_verified",
            "transfer_armed",
            "solo_verified",
            "student_exit",
            "commitment_accepted_but_phase_holds",
            "teach_back_rejected",
            "transfer_rearmed",
        ):
            with pytest.raises(ValueError):
                assert_phase_transition(
                    LearningPhase.OPEN,
                    LearningPhase.COMPLETE,
                    cause=cause,
                )
        # Sanity: the only legal edge out of OPEN is to COMMITMENT_REQUIRED
        # (gate_fired) or AWAITING_REVISION (verified_attempt).  Both must be
        # accepted; everything else to COMPLETE must be rejected.
        assert_phase_transition(
            LearningPhase.OPEN,
            LearningPhase.COMMITMENT_REQUIRED,
            cause="gate_fired",
        )
        assert_phase_transition(
            LearningPhase.OPEN,
            LearningPhase.AWAITING_REVISION,
            cause="verified_attempt",
        )

    async def test_mode_switch_continues_same_conversation(
        self,
        golden_loop_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """Golden Loop §6: the durable phase sequence runs on ONE
        conversation_id.  Switching the UI mode mid-loop (learn_concepts →
        run_experiments, e.g. for a Coding turn) must CONTINUE the same ACTIVE
        conversation — not raise a conflict and not re-fire the commitment
        gate.  The durable phase carries over and the persisted
        conversation.mode follows the latest turn's request.mode.
        """
        from quantum_agent.llm.gateway import FakeModelGateway

        async with golden_loop_database() as session:
            seed = await _seed_actor(session)
            conversation_id = await _seed_conversation(
                session,
                seed,
                phase="awaiting_revision",
                extra_phase={"loop_required": True},
                mode=TeachingMode.LEARN_CONCEPTS,
            )

        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["tunnelling"],
                    "needs_scientific_verification": False,
                    "confidence": 0.8,
                },
            }
        )
        request = TeachingTurnInput(
            mode=TeachingMode.RUN_EXPERIMENTS,
            message="现在换到实验模式继续这个会话。",
            conversation_id=conversation_id,
        )
        async with golden_loop_database() as session:
            result = await _graph(gateway=gateway).run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # The conversation continued (no TeachingConversationConflictError);
        # the commitment gate did NOT re-arm — the phase stayed inside the
        # commitment-satisfied region instead of jumping back to
        # commitment_required.
        assert result.learning_native is not None
        assert result.learning_native.phase is not LearningPhase.COMMITMENT_REQUIRED
        assert result.learning_native.required_action.value != "none"
        phase = await _read_phase(golden_loop_database, conversation_id)
        assert phase != "commitment_required"
        assert phase != "open"
        # The persisted conversation.mode follows the latest turn's request
        # (teacher trace summaries read conversation.mode).
        async with golden_loop_database() as session:
            conv = await session.scalar(
                select(TeachingConversation).where(
                    TeachingConversation.id == conversation_id
                )
            )
            assert conv is not None
            assert conv.mode is TeachingMode.RUN_EXPERIMENTS
# TutorGraph.run signature requires a session; this helper opens one.
async def _run_turn(
    graph: TutorGraph,
    database: async_sessionmaker[AsyncSession],
    seed: _Seed,
    *,
    message: str,
    conversation_id: UUID | None = None,
    learning_native: LearningNativeSubmission | None = None,
):
    request = TeachingTurnInput(
        mode=TeachingMode.LEARN_CONCEPTS,
        message=message,
        conversation_id=conversation_id,
        learning_native=learning_native,
    )
    async with database() as session:
        result = await graph.run(
            session=session,
            actor=seed.actor,
            curriculum_edition_id=seed.edition_id,
            request=request,
        )
        await session.commit()
    return result


# Patch TutorGraph with a fixture-friendly entry point for the first test.
def _install_run_turn_via_fixture() -> None:
    async def run_turn_via_fixture(
        self: TutorGraph,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        seed: _Seed,
        message: str,
    ) -> object:
        return await _run_turn(
            self,
            session_factory,
            seed,
            message=message,
        )

    TutorGraph.run_turn_via_fixture = run_turn_via_fixture  # type: ignore[attr-defined]


_install_run_turn_via_fixture()
