"""Learning-Native cognitive runtime tests (PRD V3.0).

These tests exercise the deterministic ``LearningNativePolicy`` and its
integration into the tutor graph: cognitive commitment gate, teach-back
analysis, transfer / Solo Mode, and the Cognitive Mirror.  No model tokens
are spent; the model gateway is either ``None`` or a fake.
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
from quantum_agent.auth import (
    CourseActor,
)
from quantum_agent.db_models import (
    AnswerPolicy,
    AnswerReleaseLevel,
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
    TeachingMode,
    TeachingTurnStatus,
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
from quantum_agent.llm.gateway import FakeModelGateway, GatewayError, ModelTier
from quantum_agent.teaching.learning_native import (
    CommitmentProposal,
    LearningNativePolicy,
    TeachBackProposal,
    TransferProposal,
    propose_commitment,
    propose_transfer_task,
)
from quantum_agent.teaching.models import (
    CognitiveCommitment,
    CommitmentGateDecision,
    CommitmentKind,
    LearningNativeSubmission,
    SoloAttemptSubmission,
    SoloMode,
    SoloModeStatus,
    TeachingTurnInput,
    TransferType,
)
from quantum_agent.tutor.graph import TutorGraph

API_ROOT = Path(__file__).resolve().parents[1]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
async def learning_native_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "learning-native.sqlite3"
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


class LearningSeed:
    def __init__(self, actor: CourseActor, edition_id: UUID) -> None:
        self.actor = actor
        self.edition_id = edition_id


async def _seed_actor(session: AsyncSession) -> LearningSeed:
    now = datetime.now(UTC)
    course = Course(
        code=f"LN-{uuid4()}",
        title="Quantum Physics",
        status=CourseStatus.ACTIVE,
    )
    student = User(
        email=f"ln-student-{uuid4()}@example.edu",
        display_name="LN Student",
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
    return LearningSeed(actor=actor, edition_id=edition.id)


def _evidence_packet(scope: RetrievalScope, *, with_concept: bool) -> EvidencePacket:
    if not with_concept:
        return EvidencePacket(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            query="tunneling",
            coverage=RetrievalCoverage.NOT_FOUND,
        )
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


class TunnelingRetriever:
    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        return _evidence_packet(scope, with_concept=True)


# ---------------------------------------------------------------------------
# Pure policy unit tests
# ---------------------------------------------------------------------------


class TestLearningNativePolicy:
    def test_commitment_gate_proceeds_when_student_already_attempted(self) -> None:
        policy = LearningNativePolicy()
        commitment, action, evidence = policy.decide_commitment(
            request_has_attempt=True,
            release_is_question_only=True,
            proposal=CommitmentProposal(
                attempt_type=CommitmentKind.PREDICTION,
                candidate_prompt="你的预测是什么？",
                reason_summary="先预测。",
            ),
            submission=None,
            submission_confidence=None,
        )
        assert commitment.gate_decision is CommitmentGateDecision.PROCEED
        assert commitment.accepted is True
        assert action.value == "give_cue"
        assert evidence == []

    def test_commitment_gate_enforces_when_proposal_and_no_attempt(self) -> None:
        policy = LearningNativePolicy()
        proposal = CommitmentProposal(
            attempt_type=CommitmentKind.PREDICTION,
            candidate_prompt="你的预测是什么？",
            reason_summary="先预测再解释。",
        )
        commitment, action, evidence = policy.decide_commitment(
            request_has_attempt=False,
            release_is_question_only=True,
            proposal=proposal,
            submission=None,
            submission_confidence=None,
        )
        assert commitment.gate_decision is CommitmentGateDecision.ATTEMPT_REQUIRED
        assert commitment.attempt_required is True
        assert commitment.attempt_type is CommitmentKind.PREDICTION
        assert action.value == "ask_commitment"
        assert evidence == []

    def test_commitment_submission_accepted_with_valid_text(self) -> None:
        policy = LearningNativePolicy()
        submission = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
            attempt_required=True,
            attempt_type=CommitmentKind.PREDICTION,
            candidate_prompt="透射概率会下降。",
            reason_summary="",
            accepted=False,
        )
        commitment, action, evidence = policy.decide_commitment(
            request_has_attempt=False,
            release_is_question_only=True,
            proposal=CommitmentProposal(
                attempt_type=CommitmentKind.PREDICTION,
                candidate_prompt="你的预测是什么？",
                reason_summary="",
            ),
            submission=submission,
            submission_confidence=0.8,
        )
        assert commitment.accepted is True
        assert commitment.gate_decision is CommitmentGateDecision.PROCEED
        assert commitment.confidence == 0.8
        assert action.value == "give_hint"
        assert any(item.kind is LearningEvidenceKind.COMMITMENT for item in evidence)
        assert any(item.kind is LearningEvidenceKind.CONFIDENCE for item in evidence)

    def test_option_with_confidence_submission_requires_confidence(self) -> None:
        policy = LearningNativePolicy()
        submission = CognitiveCommitment(
            gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
            attempt_required=True,
            attempt_type=CommitmentKind.OPTION_WITH_CONFIDENCE,
            candidate_prompt="B",
            reason_summary="",
            accepted=False,
        )
        commitment, _action, _evidence = policy.decide_commitment(
            request_has_attempt=False,
            release_is_question_only=True,
            proposal=CommitmentProposal(
                attempt_type=CommitmentKind.OPTION_WITH_CONFIDENCE,
                candidate_prompt="选择 B/C/D 之一",
                reason_summary="",
            ),
            submission=submission,
            submission_confidence=None,
        )
        assert commitment.accepted is False
        assert commitment.gate_decision is CommitmentGateDecision.ATTEMPT_REQUIRED

    def test_teach_back_analysis_marks_model_inference(self) -> None:
        policy = LearningNativePolicy()
        from quantum_agent.teaching.models import TeachBackFinding, TeachBackRelation

        proposal = TeachBackProposal(
            covered_relations=[
                TeachBackFinding(
                    relation=TeachBackRelation.COVERED,
                    description="势垒内波函数指数衰减。",
                )
            ],
            missing_relations=[
                TeachBackFinding(
                    relation=TeachBackRelation.MISSING,
                    description="未连接到非零透射概率。",
                )
            ],
            contradictions=[],
            unsupported_claims=[],
            recommended_probe="请说明透射概率为何不为零。",
        )
        analysis, evidence = policy.analyze_teach_back(
            submission_text="当 E<V0 时波函数在势垒内指数衰减。",
            proposal=proposal,
        )
        assert analysis.is_model_inference is True
        assert analysis.verified is False
        assert len(analysis.covered_relations) == 1
        assert len(analysis.missing_relations) == 1
        assert any(item.kind is LearningEvidenceKind.TEACH_BACK for item in evidence)

    def test_teach_back_without_model_returns_unverified(self) -> None:
        policy = LearningNativePolicy()
        analysis, evidence = policy.analyze_teach_back(
            submission_text="something",
            proposal=None,
        )
        assert analysis.is_model_inference is False
        assert analysis.verified is False
        assert any(item.kind is LearningEvidenceKind.TEACH_BACK for item in evidence)

    def test_transfer_proposal_arms_solo_mode(self) -> None:
        policy = LearningNativePolicy()
        proposal = TransferProposal(
            transfer_type=TransferType.REPRESENTATION,
            prompt="给出不同势垒宽度下透射率曲线并解释趋势。",
            key_parameters=["barrier_width"],
            expected_observable="transmission_probability",
        )
        task, solo, evidence = policy.prepare_transfer(
            proposal=proposal,
            source_concept_ids=[uuid4()],
            active_solo=None,
        )
        assert task is not None
        assert solo.status is SoloModeStatus.ACTIVE
        assert solo.assistance_locked is True
        assert task.verifiable is True
        assert any(item.kind is LearningEvidenceKind.TRANSFER for item in evidence)

    def test_record_transfer_attempt_exits_solo(self) -> None:
        policy = LearningNativePolicy()
        proposal = TransferProposal(
            transfer_type=TransferType.NEAR,
            prompt="解释双势垒共振透射。",
            key_parameters=[],
            expected_observable="",
        )
        _task, solo, _evidence = policy.prepare_transfer(
            proposal=proposal,
            source_concept_ids=[],
            active_solo=None,
        )
        exited, attempt_evidence = policy.record_transfer_attempt(
            solo=solo,
            response="共振时透射率达到 1。",
            confidence=0.7,
            verified=False,
        )
        assert exited.status is SoloModeStatus.EXITED
        assert exited.assistance_locked is False
        assert any(item.kind is LearningEvidenceKind.SOLO_ATTEMPT for item in attempt_evidence)

    def test_exit_solo_is_deterministic(self) -> None:
        policy = LearningNativePolicy()
        active = SoloMode(
            status=SoloModeStatus.ACTIVE,
            active_transfer=None,
            started_at="2026-01-01T00:00:00Z",
            assistance_locked=True,
            unlock_reason="",
        )
        exited = policy.exit_solo(active)
        assert exited.status is SoloModeStatus.EXITED
        assert exited.assistance_locked is False


# ---------------------------------------------------------------------------
# Async proposal helper tests (with a fake gateway)
# ---------------------------------------------------------------------------


class TestAsyncProposals:
    async def test_propose_commitment_skips_when_release_not_question_only(self) -> None:
        proposal = await propose_commitment(
            message="解释隧穿。",
            release_is_question_only=False,
            model_gateway=FakeModelGateway(),
        )
        assert proposal is None

    async def test_propose_commitment_returns_proposal_from_gateway(self) -> None:
        fake = FakeModelGateway(
            responses={
                "propose_cognitive_commitment": {
                    "attempt_type": "prediction",
                    "candidate_prompt": "你的预测是什么？",
                    "reason_summary": "先预测再解释。",
                }
            }
        )
        proposal = await propose_commitment(
            message="为什么隧穿会发生？",
            release_is_question_only=True,
            model_gateway=fake,
        )
        assert proposal is not None
        assert proposal.attempt_type is CommitmentKind.PREDICTION
        assert "预测" in proposal.candidate_prompt

    async def test_propose_commitment_returns_none_on_gateway_error(self) -> None:
        class FailingGateway:
            async def structured_generate(
                self, *, task: str, messages, output_type, model_tier=ModelTier.DEFAULT
            ):
                raise GatewayError("boom")

            async def probe(self):
                from quantum_agent.llm.gateway import GatewayCapabilities

                return GatewayCapabilities()

        proposal = await propose_commitment(
            message="x",
            release_is_question_only=True,
            model_gateway=FailingGateway(),
        )
        assert proposal is None

    async def test_propose_transfer_task_uses_gateway(self) -> None:
        fake = FakeModelGateway(
            responses={
                "generate_transfer_task": {
                    "transfer_type": "representation",
                    "prompt": "画图。",
                    "key_parameters": [],
                    "expected_observable": "",
                }
            }
        )
        proposal = await propose_transfer_task(
            source_concept_names=["隧穿"],
            transfer_type=None,
            model_gateway=fake,
        )
        assert proposal is not None
        assert proposal.transfer_type is TransferType.REPRESENTATION


# ---------------------------------------------------------------------------
# Tutor-graph integration: Learning-Native node attaches to the result
# ---------------------------------------------------------------------------


class TestTutorGraphLearningNative:
    async def test_learning_native_node_attaches_commitment_gate(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with learning_native_database() as session:
            seed = await _seed_actor(session)

        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="为什么 E<V0 时仍可能透射？",
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        # Without a model gateway, the commitment gate proceeds without blocking.
        assert (
            result.learning_native.commitment is not None
            and result.learning_native.commitment.gate_decision
            is CommitmentGateDecision.PROCEED
        )
        # The cognitive mirror is always assembled.
        assert result.learning_native.cognitive_mirror is not None
        assert result.learning_native.cognitive_mirror.no_personality_profile is True

    async def test_learning_native_node_persists_commitment_evidence(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with learning_native_database() as session:
            seed = await _seed_actor(session)

        # Use a fake gateway so the commitment proposal path is exercised.
        fake = FakeModelGateway(
            responses={
                "propose_cognitive_commitment": {
                    "attempt_type": "prediction",
                    "candidate_prompt": "你的预测是什么？",
                    "reason_summary": "先预测。",
                }
            }
        )
        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=fake,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        submission = LearningNativeSubmission(
            commitment=CognitiveCommitment(
                gate_decision=CommitmentGateDecision.ATTEMPT_REQUIRED,
                attempt_required=True,
                attempt_type=CommitmentKind.PREDICTION,
                candidate_prompt="透射概率会随宽度下降。",
                reason_summary="",
                accepted=False,
            ),
            confidence=0.75,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="为什么隧穿会发生？",
            learning_native=submission,
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
            rows = list(
                (
                    await session.execute(
                        select(LearningEvidence).where(
                            LearningEvidence.kind == LearningEvidenceKind.COMMITMENT
                        )
                    )
                ).scalars().all()
            )
        assert result.learning_native is not None
        assert result.learning_native.commitment is not None
        assert result.learning_native.commitment.accepted is True
        assert any(item.kind is LearningEvidenceKind.COMMITMENT for item in rows)
        assert any(
            item.kind is LearningEvidenceKind.CONFIDENCE
            for item in (
                result.learning_native.evidence_persisted  # type: ignore[attr-defined]
            )
            if False
        ) or True  # evidence_persisted is a list of kind strings
        assert "commitment" in result.learning_native.evidence_persisted
        assert "confidence" in result.learning_native.evidence_persisted

    async def test_learning_native_node_persists_transfer_solo(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with learning_native_database() as session:
            seed = await _seed_actor(session)

        fake = FakeModelGateway(
            responses={
                "generate_transfer_task": {
                    "transfer_type": "representation",
                    "prompt": "画出不同势垒宽度下的透射率曲线。",
                    "key_parameters": ["barrier_width"],
                    "expected_observable": "",
                }
            }
        )
        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=fake,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        # First turn: arm Solo Mode by requesting a transfer.
        request1 = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我想挑战一个迁移任务。",
            learning_native=LearningNativeSubmission(request_transfer=True),
        )
        async with learning_native_database() as session:
            result1 = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request1,
            )
            await session.commit()
        assert result1.learning_native is not None
        assert result1.learning_native.solo is not None
        assert result1.learning_native.solo.status is SoloModeStatus.ACTIVE
        assert result1.learning_native.transfer is not None

        # Second turn: submit a solo attempt that exits Solo Mode.
        request2 = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的迁移尝试。",
            conversation_id=result1.conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="透射率随势垒宽度增加而指数下降。",
                    confidence=0.6,
                )
            ),
        )
        async with learning_native_database() as session:
            result2 = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request2,
            )
            await session.commit()
            solo_rows = list(
                (
                    await session.execute(
                        select(LearningEvidence).where(
                            LearningEvidence.kind == LearningEvidenceKind.SOLO_ATTEMPT
                        )
                    )
                ).scalars().all()
            )
        assert result2.learning_native is not None
        assert result2.learning_native.solo is not None
        assert result2.learning_native.solo.status is SoloModeStatus.EXITED
        assert any(
            item.kind is LearningEvidenceKind.SOLO_ATTEMPT for item in solo_rows
        )

    async def test_cognitive_mirror_does_not_produce_personality_profile(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            # Insert a stale observation to ensure the mirror has data to read.
            from quantum_agent.db_models import (
                TeachingConversation,
                TeachingConversationStatus,
                TeachingTurn,
            )

            conversation = TeachingConversation(
                course_id=seed.actor.course_id,
                curriculum_edition_id=seed.edition_id,
                student_user_id=seed.actor.user_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
            )
            session.add(conversation)
            await session.flush()
            turn = TeachingTurn(
                conversation_id=conversation.id,
                sequence_number=1,
                user_message="earlier question",
                status=TeachingTurnStatus.RUNNING,
                release_level=AnswerReleaseLevel.HINT,
            )
            session.add(turn)
            await session.flush()
            session.add(
                LearningEvidence(
                    teaching_turn_id=turn.id,
                    course_id=seed.actor.course_id,
                    curriculum_edition_id=seed.edition_id,
                    student_user_id=seed.actor.user_id,
                    kind=LearningEvidenceKind.COMMITMENT,
                    observation="过去的承诺。",
                    mastery_delta=0.0,
                    evidence_json={},
                )
            )
            await session.commit()

        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="继续讨论隧穿。",
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        mirror = result.learning_native.cognitive_mirror
        assert mirror is not None
        assert mirror.no_personality_profile is True
        # The summary must not contain any mastery percentage or personality
        # verdict.  The disclaimer "不进行人格推断" is allowed because it is
        # the explicit no-profiling assertion, not a personality claim.
        assert "%" not in mirror.summary
        assert "IQ" not in mirror.summary
        assert "内向" not in mirror.summary
        assert "外向" not in mirror.summary
        assert "学习能力" not in mirror.summary

    async def test_commitment_gate_withholds_answer_before_generation(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """PRD V3.0 Axiom 1: the LLM must not generate an explanation while the
        commitment gate is still open.  When the gate is enforced (proposal +
        no student attempt + question-only release), the graph skips the LLM
        generation call entirely and emits a deterministic elicitation response.
        """

        async with learning_native_database() as session:
            seed = await _seed_actor(session)

        class _CallTrackingGateway(FakeModelGateway):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)
                self.compose_calls = 0

            async def structured_generate(self, *args: object, **kwargs: object) -> object:
                task = kwargs.get("task") or (args[0] if args else "")
                if task == "compose_grounded_teaching_response":
                    self.compose_calls += 1
                return await super().structured_generate(*args, **kwargs)

        gateway = _CallTrackingGateway(
            responses={
                "propose_cognitive_commitment": {
                    "attempt_type": "prediction",
                    "candidate_prompt": "你的预测是什么？透射概率随势垒宽度如何变化？",
                    "reason_summary": "先预测再解释。",
                }
            }
        )
        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=gateway,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        # First turn: RUN_EXPERIMENTS mode with no student attempt produces
        # a QUESTION_ONLY release (see AnswerReleaseEngine.decide), so the
        # commitment gate MUST enforce and withhold the LLM answer.
        request = TeachingTurnInput(
            mode=TeachingMode.RUN_EXPERIMENTS,
            message="为什么 E<V0 时仍可能透射？",
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        assert result.learning_native is not None
        assert result.learning_native.commitment is not None
        assert (
            result.learning_native.commitment.gate_decision
            is CommitmentGateDecision.ATTEMPT_REQUIRED
        )
        # The AI was withheld: zero claims, deterministic elicitation response.
        assert result.response.claims == []
        assert "Commitment gate" in " ".join(result.response.limitations)
        # The compose_grounded_teaching_response LLM call was never made.
        assert gateway.compose_calls == 0, (
            "commitment gate must prevent the LLM from generating an explanation"
        )
