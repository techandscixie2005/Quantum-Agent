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
    TeachingConversation,
    TeachingConversationStatus,
    TeachingMode,
    TeachingTaskKind,
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
    ConceptStateLabel,
    LearningNativeSubmission,
    LearningPhase,
    SoloAttemptSubmission,
    SoloMode,
    SoloModeStatus,
    TeachBackSubmission,
    TeachingTurnInput,
    TransferType,
    WorkflowStepName,
    WorkflowStepStatus,
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


async def _seed_conversation_with_phase(
    session: AsyncSession,
    seed: LearningSeed,
    *,
    phase: str,
    extra_phase: dict[str, object] | None = None,
    mode: TeachingMode = TeachingMode.LEARN_CONCEPTS,
) -> UUID:
    """Persist a conversation with a pre-seeded durable LearningPhase.

    The Phase 3 transition guards make every durable-phase mutation pass
    through ``assert_phase_transition``.  Tests that exercise a *later* phase
    (AWAITING_REVISION, RECONSTRUCTION_REQUIRED, TRANSFER_REQUIRED, SOLO_ACTIVE)
    must therefore seed the conversation into that phase rather than expecting
    a single fresh turn to skip there — skipping is exactly the behaviour the
    guards now forbid.
    """

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
        # PRD V3.3 root-cause #4: an accepted commitment is a PREDICTION, not a
        # verified learning signal.  The gate stays armed (ATTEMPT_REQUIRED) so
        # the explanation is NOT released on the same turn; the student must
        # submit a *revised* attempt.  Invariant B: commitment accepted ≠
        # explanation released.
        assert commitment.gate_decision is CommitmentGateDecision.ATTEMPT_REQUIRED
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
        # PRD V3.0 P1-1: a transfer task being ASSIGNED is recorded as
        # TRANSFER_ASSIGNED + SOLO_ASSIGNED, NOT as the legacy TRANSFER kind.
        # The mirror must not count task generation as transfer competence.
        kinds = {item.kind for item in evidence}
        assert LearningEvidenceKind.TRANSFER_ASSIGNED in kinds
        assert LearningEvidenceKind.SOLO_ASSIGNED in kinds
        assert LearningEvidenceKind.TRANSFER not in kinds
        # The assigned evidence must be marked unverified so the mirror
        # cannot promote on it.
        for item in evidence:
            assert item.evidence_json.get("verified") is False
            assert item.evidence_json.get("outcome") in {
                "TRANSFER_ASSIGNED",
                "SOLO_ASSIGNED",
            }

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
# P0-1 adversarial tests: deterministic eligibility + fail-closed + redaction
# ---------------------------------------------------------------------------


class TestCommitmentEligibility:
    """The LLM never decides whether the gate fires; eligibility is deterministic."""

    def test_factual_lookup_bypasses_gate(self) -> None:
        from quantum_agent.teaching.policy import commitment_eligibility

        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.CONCEPT_QUESTION,
                message="什么是厄米算符？",
                has_current_attempt=False,
            )
            is False
        )

    def test_reasoning_question_requires_commitment(self) -> None:
        from quantum_agent.teaching.policy import commitment_eligibility

        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.CONCEPT_QUESTION,
                message="为什么 E<V0 时仍可能透射？",
                has_current_attempt=False,
            )
            is True
        )

    def test_generic_concept_question_requires_commitment_fail_closed(self) -> None:
        # PRD V3.0 Axiom 1 (fail-closed): a generic concept question with NO
        # factual-lookup marker and NO exercise marker is still a
        # reasoning/explanation task, not a definition lookup.  The default
        # for CONCEPT_QUESTION must be to require a commitment so a student
        # cannot phrase "解释波函数" to bypass the gate.
        from quantum_agent.teaching.policy import commitment_eligibility

        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.CONCEPT_QUESTION,
                message="解释波函数的统计解释",
                has_current_attempt=False,
            )
            is True
        )
        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.CONCEPT_QUESTION,
                message="讲一下隧穿效应",
                has_current_attempt=False,
            )
            is True
        )
        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.CONCEPT_QUESTION,
                message="帮我理解角动量算符",
                has_current_attempt=False,
            )
            is True
        )

    def test_exercise_help_requires_commitment(self) -> None:
        from quantum_agent.teaching.policy import commitment_eligibility

        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.EXERCISE_HELP,
                message="求解一维势阱的能级。",
                has_current_attempt=False,
            )
            is True
        )

    def test_run_experiments_requires_commitment(self) -> None:
        from quantum_agent.teaching.policy import commitment_eligibility

        assert (
            commitment_eligibility(
                mode=TeachingMode.RUN_EXPERIMENTS,
                task_kind=TeachingTaskKind.EXPERIMENT_HELP,
                message="运行模拟",
                has_current_attempt=False,
            )
            is True
        )

    def test_existing_attempt_satisfies_gate(self) -> None:
        from quantum_agent.teaching.policy import commitment_eligibility

        assert (
            commitment_eligibility(
                mode=TeachingMode.LEARN_CONCEPTS,
                task_kind=TeachingTaskKind.EXERCISE_HELP,
                message="求解一维势阱的能级。",
                has_current_attempt=True,
            )
            is False
        )


class TestCommitmentGateFailClosed:
    """Model unavailability must never bypass the commitment gate."""

    def test_fail_closed_when_model_unavailable_and_release_is_question_only(self) -> None:
        policy = LearningNativePolicy()
        commitment, action, _evidence = policy.decide_commitment(
            request_has_attempt=False,
            release_is_question_only=True,
            proposal=None,
            submission=None,
            submission_confidence=None,
        )
        assert commitment.gate_decision is CommitmentGateDecision.ATTEMPT_REQUIRED
        assert commitment.attempt_required is True
        assert commitment.accepted is False
        assert commitment.candidate_prompt == policy.FALLBACK_COMMITMENT_PROMPT
        assert action.value == "ask_commitment"

    def test_fail_closed_when_gateway_error_returns_none(self) -> None:
        policy = LearningNativePolicy()
        # Simulate the gateway returning None (GatewayError caught in
        # propose_commitment).  The gate must still fire.
        commitment, _action, _evidence = policy.decide_commitment(
            request_has_attempt=False,
            release_is_question_only=True,
            proposal=None,
            submission=None,
            submission_confidence=None,
        )
        assert commitment.gate_decision is CommitmentGateDecision.ATTEMPT_REQUIRED

    def test_proceed_when_release_is_not_question_only_and_no_proposal(self) -> None:
        policy = LearningNativePolicy()
        commitment, _action, _evidence = policy.decide_commitment(
            request_has_attempt=False,
            release_is_question_only=False,
            proposal=None,
            submission=None,
            submission_confidence=None,
        )
        # A teacher-configured full-solution release, or a factual lookup that
        # bypassed the gate, proceeds without a commitment.
        assert commitment.gate_decision is CommitmentGateDecision.PROCEED
        assert commitment.accepted is True

    def test_trivial_attempt_does_not_satisfy_gate(self) -> None:
        assert LearningNativePolicy.attempt_is_meaningful("a") is False
        assert LearningNativePolicy.attempt_is_meaningful("。") is False
        assert LearningNativePolicy.attempt_is_meaningful("  ") is False
        assert LearningNativePolicy.attempt_is_meaningful(None) is False

    def test_meaningful_attempt_satisfies_gate(self) -> None:
        assert LearningNativePolicy.attempt_is_meaningful("透射概率随宽度指数下降。") is True
        assert LearningNativePolicy.attempt_is_meaningful("I predict T is small.") is True


class TestEvidenceRedactionWhileGated:
    """Answer-bearing evidence must not leak while the commitment gate is open."""

    def test_redacted_evidence_item_replaces_snippet_with_placeholder(self) -> None:

        item = _build_evidence_item(snippet="The exact answer is 42.")
        redacted = item.redacted_for_gate()
        assert "42" not in redacted.evidence_snippet
        assert "42" not in redacted.source_chunk
        assert redacted.document_title == item.document_title
        assert redacted.chapter == item.chapter
        assert redacted.evidence_id == item.evidence_id
        # The placeholder is its own grounded snippet (validator passes).
        assert redacted.evidence_snippet == redacted.source_chunk

    def test_redacted_packet_preserves_provenance_but_not_text(self) -> None:

        item = _build_evidence_item(snippet="Transmission T = 0.0821 for E<V0.")
        packet = _build_evidence_packet(items=[item])
        redacted = packet.redacted_for_gate()
        assert redacted.evidence
        for original, redacted_item in zip(packet.evidence, redacted.evidence, strict=True):
            assert "0.0821" not in redacted_item.evidence_snippet
            assert redacted_item.document_title == original.document_title


def _build_evidence_item(snippet: str) -> EvidenceItem:
    from quantum_agent.knowledge.evidence_packets import (
        EvidenceItem,
        EvidenceKind,
        EvidenceLocator,
        LocatorType,
        RetrievalChannel,
        RetrievalContribution,
    )

    source_chunk = (
        "Context: " + snippet + " This is the surrounding source text."
    )
    return EvidenceItem(
        evidence_id=uuid4(),
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_title="Quantum Mechanics Textbook",
        document_version=1,
        source_file_name="textbook.pdf",
        source_file_sha256=hashlib.sha256(b"file").hexdigest(),
        source_chunk_sha256=hashlib.sha256(source_chunk.encode("utf-8")).hexdigest(),
        evidence_sha256=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
        chapter="Chapter 3",
        section_path=["Chapter 3", "Section 2"],
        locator=EvidenceLocator(
            locator_type=LocatorType.PDF_PAGE,
            physical_page=42,
        ),
        source_chunk=source_chunk,
        evidence_snippet=snippet,
        kind=EvidenceKind.COURSE_MATERIAL,
        authority_priority=10,
        contributions=[
            RetrievalContribution(
                channel=RetrievalChannel.FULL_TEXT,
                rank=1,
                fused_score=1.0,
            )
        ],
    )


def _build_evidence_packet(items: list[EvidenceItem]) -> EvidencePacket:
    from quantum_agent.knowledge.evidence_packets import EvidencePacket, RetrievalCoverage

    return EvidencePacket(
        course_id=uuid4(),
        curriculum_edition_id=uuid4(),
        query="tunnelling",
        coverage=RetrievalCoverage.SUFFICIENT,
        evidence=items,
    )


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
        # PRD V3.0 Axiom 1 (fail-closed): with no model gateway, the
        # commitment gate must STILL fire for a reasoning question.  The
        # deterministic fallback prompt is used; the answer is withheld.
        assert (
            result.learning_native.commitment is not None
            and result.learning_native.commitment.gate_decision
            is CommitmentGateDecision.ATTEMPT_REQUIRED
        )
        assert result.learning_native.commitment.accepted is False
        assert result.learning_native.commitment.candidate_prompt
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
            # Phase 3 invariants: transfer-arming requires TRANSFER_REQUIRED
            # and Solo verification requires a persisted transfer oracle.
            # This test exercises an UNVERIFIED attempt, so we seed SOLO_ACTIVE
            # directly (no oracle) and confirm the attempt fails closed — Solo
            # stays active.  The previous single-turn jump from OPEN to Solo
            # is exactly what the Phase 3 guards now forbid.
            conversation_id = await _seed_conversation_with_phase(
                session,
                seed,
                phase="solo_active",
                extra_phase={
                    "active_transfer_task_prompt": "画出不同势垒宽度下的透射率曲线。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )

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
        # Submit a solo attempt.  PRD V3.0 P0-2 + Phase 3 root-cause #5: an
        # unverified attempt (no persisted oracle / no scientific PASS this
        # turn) does NOT exit Solo.  The attempt is recorded as evidence but
        # Solo stays active until a numerically-verified attempt is submitted.
        request2 = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的迁移尝试。",
            conversation_id=conversation_id,
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
            attempt_rows = list(
                (
                    await session.execute(
                        select(LearningEvidence).where(
                            LearningEvidence.kind.in_(
                                [
                                    LearningEvidenceKind.TRANSFER_ATTEMPTED,
                                    LearningEvidenceKind.TRANSFER_FAILED,
                                ]
                            )
                        )
                    )
                ).scalars().all()
            )
        assert result2.learning_native is not None
        # Solo stays ACTIVE because the attempt was not verified.
        assert result2.learning_native.solo is not None
        assert result2.learning_native.solo.status is SoloModeStatus.ACTIVE
        # PRD V3.0 P1-1: the unverified attempt is persisted as
        # TRANSFER_ATTEMPTED + TRANSFER_FAILED, NOT as a verified transfer.
        # The mirror must not count this toward TRANSFER_READY.
        assert len(attempt_rows) >= 2
        for row in attempt_rows:
            assert row.evidence_json.get("verified") is False

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


# ---------------------------------------------------------------------------
# P1-1 adversarial tests: Cognitive Mirror evidence semantics
# ---------------------------------------------------------------------------


class TestCognitiveMirrorEvidenceSemantics:
    """The mirror must not promote a learner on task generation alone.

    PRD V3.0 P1-1: only a verified, task-correlated, unaided transfer attempt
    contributes to TRANSFER_READY / unaided_retrieval.  A transfer task being
    ASSIGNED is not evidence of transfer competence.
    """

    @staticmethod
    def _make_evidence(
        kind: LearningEvidenceKind,
        *,
        verified: bool = False,
        concept_id: UUID | None = None,
        outcome: str = "",
    ) -> LearningEvidence:
        row = LearningEvidence(
            kind=kind,
            observation=f"observation for {kind.value}",
            evidence_json={"verified": verified, "outcome": outcome},
            concept_candidate_id=concept_id,
        )
        # ``created_at`` is set by the ORM mixin on flush; for unit tests that
        # never flush, set it manually so ``_concept_state`` can call
        # ``.isoformat()`` on it.
        row.created_at = datetime.now(UTC)
        return row

    def test_transfer_assigned_only_does_not_yield_transfer_ready(self) -> None:
        # A learner who merely had a transfer task generated (TRANSFER_ASSIGNED
        # + SOLO_ASSIGNED) and submitted a teach-back must NOT be promoted to
        # TRANSFER_READY, because no verified unaided attempt exists.
        concept_id = uuid4()
        observations = [
            self._make_evidence(
                LearningEvidenceKind.TRANSFER_ASSIGNED,
                concept_id=concept_id,
                outcome="TRANSFER_ASSIGNED",
            ),
            self._make_evidence(
                LearningEvidenceKind.SOLO_ASSIGNED,
                concept_id=concept_id,
                outcome="SOLO_ASSIGNED",
            ),
            self._make_evidence(
                LearningEvidenceKind.TEACH_BACK,
                concept_id=concept_id,
            ),
        ]
        state = LearningNativePolicy._concept_state(
            concept_id=concept_id,
            observations=observations,
            diagnosis=None,
        )
        assert state.label is not ConceptStateLabel.TRANSFER_READY
        assert state.unaided_retrieval is False

    def test_transfer_verified_plus_teach_back_yields_transfer_ready(self) -> None:
        # Only a VERIFIED transfer attempt + teach-back yields TRANSFER_READY.
        concept_id = uuid4()
        observations = [
            self._make_evidence(
                LearningEvidenceKind.TRANSFER_VERIFIED,
                verified=True,
                concept_id=concept_id,
                outcome="TRANSFER_VERIFIED",
            ),
            self._make_evidence(
                LearningEvidenceKind.TEACH_BACK,
                concept_id=concept_id,
            ),
        ]
        state = LearningNativePolicy._concept_state(
            concept_id=concept_id,
            observations=observations,
            diagnosis=None,
        )
        assert state.label is ConceptStateLabel.TRANSFER_READY
        assert state.unaided_retrieval is True
        # The transfer_evidence list must contain the verified observation.
        assert any(
            "TRANSFER_VERIFIED" in item or "observation" in item
            for item in state.transfer_evidence
        )

    def test_unverified_transfer_attempt_does_not_yield_unaided_retrieval(self) -> None:
        # An unverified transfer attempt (TRANSFER_ATTEMPTED / TRANSFER_FAILED)
        # must NOT set unaided_retrieval or yield TRANSFER_READY.
        concept_id = uuid4()
        observations = [
            self._make_evidence(
                LearningEvidenceKind.TRANSFER_ATTEMPTED,
                verified=False,
                concept_id=concept_id,
                outcome="TRANSFER_ATTEMPTED_NOT_VERIFIED",
            ),
            self._make_evidence(
                LearningEvidenceKind.TRANSFER_FAILED,
                verified=False,
                concept_id=concept_id,
                outcome="TRANSFER_FAILED",
            ),
            self._make_evidence(
                LearningEvidenceKind.TEACH_BACK,
                concept_id=concept_id,
            ),
        ]
        state = LearningNativePolicy._concept_state(
            concept_id=concept_id,
            observations=observations,
            diagnosis=None,
        )
        assert state.label is not ConceptStateLabel.TRANSFER_READY
        assert state.unaided_retrieval is False
        # A failed transfer marks the concept FRAGILE.
        assert state.label is ConceptStateLabel.FRAGILE

    def test_legacy_solo_attempt_only_counts_when_verified(self) -> None:
        # Legacy pre-remediation SOLO_ATTEMPT rows must only count toward
        # unaided_retrieval when their evidence_json marks verified=True.
        concept_id = uuid4()
        unverified_legacy = [
            self._make_evidence(
                LearningEvidenceKind.SOLO_ATTEMPT,
                verified=False,
                concept_id=concept_id,
                outcome="SOLO_ATTEMPTED_NOT_VERIFIED",
            ),
            self._make_evidence(
                LearningEvidenceKind.TEACH_BACK,
                concept_id=concept_id,
            ),
        ]
        state_unverified = LearningNativePolicy._concept_state(
            concept_id=concept_id,
            observations=unverified_legacy,
            diagnosis=None,
        )
        assert state_unverified.unaided_retrieval is False
        assert state_unverified.label is not ConceptStateLabel.TRANSFER_READY

        verified_legacy = [
            self._make_evidence(
                LearningEvidenceKind.SOLO_ATTEMPT,
                verified=True,
                concept_id=concept_id,
                outcome="SOLO_VERIFIED",
            ),
            self._make_evidence(
                LearningEvidenceKind.TEACH_BACK,
                concept_id=concept_id,
            ),
        ]
        state_verified = LearningNativePolicy._concept_state(
            concept_id=concept_id,
            observations=verified_legacy,
            diagnosis=None,
        )
        assert state_verified.unaided_retrieval is True
        assert state_verified.label is ConceptStateLabel.TRANSFER_READY

    def test_untagged_evidence_uses_stable_bucket_not_random_uuid(self) -> None:
        # PRD V3.0 P1-1: untagged evidence must group under a stable bucket
        # UUID, not a fresh uuid4() on every build.  Two calls with the same
        # untagged observations must produce the same concept_candidate_id.
        observations = [
            self._make_evidence(LearningEvidenceKind.COMMITMENT, concept_id=None),
        ]
        state_a = LearningNativePolicy._concept_state(
            concept_id=None,
            observations=observations,
            diagnosis=None,
        )
        state_b = LearningNativePolicy._concept_state(
            concept_id=None,
            observations=observations,
            diagnosis=None,
        )
        assert state_a.concept_candidate_id == state_b.concept_candidate_id

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
        # PRD V3.0 Axiom 1 (gate-before-retrieval): the commitment gate fires
        # BEFORE evidence retrieval, so the student-facing result carries NO
        # evidence while the gate is open — there is nothing to redact because
        # retrieval was skipped.  The packet warns that retrieval is deferred
        # until the student commits a prediction / first step.
        assert result.evidence_packet.evidence == [], (
            "the gate-fires branch must not surface any evidence; retrieval is "
            "skipped until the student submits a cognitive commitment"
        )
        assert "retrieval_skipped_until_commitment" in result.evidence_packet.warnings

    async def test_commitment_precedes_evidence_and_diagnosis(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """PRD V3.0 Axiom 1: the commitment gate fires BEFORE evidence
        retrieval and diagnosis.  When the gate is enforced (RUN_EXPERIMENTS +
        no student attempt), retrieval must not run, the RETRIEVE_EVIDENCE and
        DIAGNOSE_PROGRESS trace steps must be SKIPPED, and the commitment
        proposal LLM call must occur before any retrieval could have happened.
        """

        class _OrderRetriever(TunnelingRetriever):
            def __init__(self) -> None:
                self.retrieved = False

            async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
                self.retrieved = True
                return await super().retrieve(scope, query)

        class _OrderGateway(FakeModelGateway):
            def __init__(self, retriever: _OrderRetriever) -> None:
                super().__init__(
                    {
                        "propose_cognitive_commitment": {
                            "attempt_type": "prediction",
                            "candidate_prompt": "先预测透射率是否为零。",
                            "reason_summary": "先承诺，再检索证据。",
                        }
                    }
                )
                self.retriever = retriever

            async def structured_generate(self, *args: object, **kwargs: object) -> object:
                task = kwargs.get("task") or (args[0] if args else "")
                if task == "propose_cognitive_commitment":
                    assert not self.retriever.retrieved
                return await super().structured_generate(*args, **kwargs)

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
        retriever = _OrderRetriever()
        graph = TutorGraph(
            evidence_retriever=retriever,
            model_gateway=_OrderGateway(retriever),
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.RUN_EXPERIMENTS,
                    message="为什么 E<V0 时仍可能透射？",
                ),
            )
            await session.commit()
        # The gate fired, so retrieval was never called.
        assert retriever.retrieved is False, (
            "the commitment gate must fire BEFORE evidence retrieval; the "
            "retriever must not be called when the gate withholds the answer"
        )
        # The 10-step trace invariant is preserved; steps 3 (RETRIEVE_EVIDENCE)
        # and 4 (DIAGNOSE_PROGRESS) are SKIPPED because the gate skipped
        # retrieval and diagnosis.
        assert [step.name for step in result.trace] == list(WorkflowStepName)
        assert result.trace[2].name is WorkflowStepName.RETRIEVE_EVIDENCE
        assert result.trace[2].status is WorkflowStepStatus.SKIPPED
        assert result.trace[3].name is WorkflowStepName.DIAGNOSE_PROGRESS
        assert result.trace[3].status is WorkflowStepStatus.SKIPPED
        # The commitment gate is enforced and the answer is withheld.
        assert result.learning_native is not None
        assert result.learning_native.commitment is not None
        assert (
            result.learning_native.commitment.gate_decision
            is CommitmentGateDecision.ATTEMPT_REQUIRED
        )
        assert result.response.claims == []


# ---------------------------------------------------------------------------
# P0-2 adversarial tests: durable Learning Phase, Solo lock, UI transitions
# ---------------------------------------------------------------------------


class TestDurableLearningPhaseSoloLock:
    """Solo Mode is server-authoritative, restored BEFORE generation, and
    blocks Ask AI.  Refresh / retry / new tab cannot escape the lock.
    """

    async def test_solo_blocks_ask_ai_before_llm_generation(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """A normal Ask AI request during Solo Mode is blocked BEFORE the LLM
        is called.  The LLM compose call count must remain zero.
        """

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            # Pre-arm Solo Mode by persisting a durable phase on the conversation.
            conversation = TeachingConversation(
                course_id=seed.actor.course_id,
                curriculum_edition_id=seed.edition_id,
                student_user_id=seed.actor.user_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
                learning_phase_json={
                    "phase": "solo_active",
                    "active_transfer_task_prompt": "解释不同势垒宽度下透射率的变化趋势。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
            await session.commit()

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
        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=gateway,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        # The student asks for AI help (not a solo attempt) during Solo Mode.
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="请直接告诉我答案。",
            conversation_id=conversation_id,
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # The LLM was NOT called — Solo blocked it before generation.
        assert gateway.compose_calls == 0, (
            "Solo Mode must block the LLM compose call before generation"
        )
        # The response is a deterministic Solo-block message with zero claims.
        assert result.response.claims == []
        assert "Solo" in " ".join(result.response.limitations)

    async def test_solo_persists_across_refresh_and_new_turn(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """Refresh / new turn in the same conversation must restore Solo Mode."""

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            conversation = TeachingConversation(
                course_id=seed.actor.course_id,
                curriculum_edition_id=seed.edition_id,
                student_user_id=seed.actor.user_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
                learning_phase_json={
                    "phase": "solo_active",
                    "active_transfer_task_prompt": "迁移任务。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
            await session.commit()

        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        # A new turn in the same conversation: Solo must still be active.
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="帮我解释一下。",
            conversation_id=conversation_id,
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # Solo is still active — the durable phase was restored.
        assert result.learning_native is not None
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status is SoloModeStatus.ACTIVE

    async def test_unverified_solo_attempt_does_not_exit_solo(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """An incorrect / unverified attempt must NOT unlock Solo."""

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            conversation = TeachingConversation(
                course_id=seed.actor.course_id,
                curriculum_edition_id=seed.edition_id,
                student_user_id=seed.actor.user_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
                learning_phase_json={
                    "phase": "solo_active",
                    "active_transfer_task_prompt": "迁移任务。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
            await session.commit()

        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        # Submit an unverified solo attempt (no scientific tool result this turn).
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="这是我的尝试。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                solo_attempt=SoloAttemptSubmission(
                    response="随便写的答案。",
                    confidence=0.3,
                )
            ),
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # Solo stays ACTIVE because the attempt was not verified.
        assert result.learning_native is not None
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status is SoloModeStatus.ACTIVE

    async def test_empty_message_does_not_exit_solo(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """An empty / random unrelated message must not unlock Solo."""

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            conversation = TeachingConversation(
                course_id=seed.actor.course_id,
                curriculum_edition_id=seed.edition_id,
                student_user_id=seed.actor.user_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
                learning_phase_json={
                    "phase": "solo_active",
                    "active_transfer_task_prompt": "迁移任务。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
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
            message="继续",
            conversation_id=conversation_id,
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
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status is SoloModeStatus.ACTIVE

    async def test_explicit_solo_exit_marks_aborted_not_success(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """Explicit Solo exit records ABORTED, not SUCCESS."""

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            conversation = TeachingConversation(
                course_id=seed.actor.course_id,
                curriculum_edition_id=seed.edition_id,
                student_user_id=seed.actor.user_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                status=TeachingConversationStatus.ACTIVE,
                last_activity_at=datetime.now(UTC),
                learning_phase_json={
                    "phase": "solo_active",
                    "active_transfer_task_prompt": "迁移任务。",
                    "solo_started_at": datetime.now(UTC).isoformat(),
                    "solo_assistance_locked": True,
                    "expected_attempt_kind": "transfer",
                },
            )
            session.add(conversation)
            await session.flush()
            conversation_id = conversation.id
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
            message="我想退出 Solo。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(request_solo_exit=True),
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
        assert result.learning_native.solo is not None
        # ABORTED, not EXITED/SUCCESS.
        assert result.learning_native.solo.status is SoloModeStatus.ABORTED


class TestTeachBackAndTransferUIInitiation:
    """Teach-Back and Transfer must be reachable from the normal UI via
    ``request_teach_back`` and ``request_transfer_task`` submission flags.
    """

    async def test_request_teach_back_transitions_phase(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            # Phase 3 invariant D: Teach-Back is reachable only from
            # AWAITING_REVISION.  A fresh OPEN conversation can no longer jump
            # straight to Teach-Back — the student must commit, then explain,
            # first.  Seed the durable phase to AWAITING_REVISION.
            conversation_id = await _seed_conversation_with_phase(
                session,
                seed,
                phase="awaiting_revision",
            )

        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="我想用自己的话重新解释这个概念。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(
                request_teach_back=True,
                teach_back=TeachBackSubmission(
                    reconstruction=(
                        "基态波函数在势阱内关于中心对称，动量算符是奇算符，"
                        "所以动量期望值在对称态上为零。"
                    ),
                ),
            ),
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # The Teach-Back card is rendered (teach_back is non-null) and the
        # durable phase advanced from AWAITING_REVISION to
        # RECONSTRUCTION_REQUIRED (invariant D, cause teach_back_requested).
        assert result.learning_native is not None
        assert result.learning_native.teach_back is not None
        assert result.learning_native.teach_back.recommended_probe
        assert result.learning_native.phase is LearningPhase.RECONSTRUCTION_REQUIRED

    async def test_request_transfer_task_arms_solo(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            # Phase 3 invariant F: transfer-arming requires the durable phase
            # to already be TRANSFER_REQUIRED.  A fresh OPEN conversation can
            # no longer jump straight to Solo — the student must first commit,
            # explain, and complete Teach-Back.  Seed TRANSFER_REQUIRED.
            conversation_id = await _seed_conversation_with_phase(
                session,
                seed,
                phase="transfer_required",
            )

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
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="给我一个迁移任务。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(request_transfer_task=True),
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
        assert result.learning_native.transfer is not None
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status is SoloModeStatus.ACTIVE
        # The durable phase is persisted on the conversation.
        async with learning_native_database() as session:
            from sqlalchemy import select as _select

            conv = await session.scalar(
                _select(TeachingConversation).where(
                    TeachingConversation.id == result.conversation_id
                )
            )
            assert conv is not None
            phase = conv.learning_phase_json
            assert phase is not None
            assert phase["phase"] == "solo_active"

    async def test_request_transfer_task_arms_solo_with_model_unavailable(
        self,
        learning_native_database: async_sessionmaker[AsyncSession],
    ) -> None:
        """Golden Loop closure: when the student explicitly requests a transfer
        task (``request_transfer_task=True``) but the model gateway is
        unavailable (``None``), the policy must STILL arm Solo Mode using a
        deterministic near-transfer fallback.  Model failure must never block
        the Golden Loop from progressing to Solo Mode.
        """

        async with learning_native_database() as session:
            seed = await _seed_actor(session)
            # Phase 3 invariant F: seed TRANSFER_REQUIRED (see test above).
            conversation_id = await _seed_conversation_with_phase(
                session,
                seed,
                phase="transfer_required",
            )

        # model_gateway=None simulates model unavailability; the fallback path
        # must still arm Solo Mode.
        graph = TutorGraph(
            evidence_retriever=TunnelingRetriever(),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            use_specialist_agents=False,
            enable_hitl=False,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.LEARN_CONCEPTS,
            message="给我一个迁移任务。",
            conversation_id=conversation_id,
            learning_native=LearningNativeSubmission(request_transfer_task=True),
        )
        async with learning_native_database() as session:
            result = await graph.run(
                session=session,
                actor=seed.actor,
                curriculum_edition_id=seed.edition_id,
                request=request,
            )
            await session.commit()
        # Solo Mode is armed deterministically even without a model proposal.
        assert result.learning_native is not None
        assert result.learning_native.transfer is not None
        assert result.learning_native.solo is not None
        assert result.learning_native.solo.status is SoloModeStatus.ACTIVE
        assert result.learning_native.solo.active_transfer is not None
        # The fallback transfer task uses the deterministic near-transfer prompt.
        assert (
            result.learning_native.transfer.prompt
            == LearningNativePolicy.FALLBACK_TRANSFER_PROMPT
        )
        # The durable phase is persisted as SOLO_ACTIVE.
        async with learning_native_database() as session:
            from sqlalchemy import select as _select

            conv = await session.scalar(
                _select(TeachingConversation).where(
                    TeachingConversation.id == result.conversation_id
                )
            )
            assert conv is not None
            phase = conv.learning_phase_json
            assert phase is not None
            assert phase["phase"] == "solo_active"
            assert phase["active_transfer_task_prompt"] == (
                LearningNativePolicy.FALLBACK_TRANSFER_PROMPT
            )
