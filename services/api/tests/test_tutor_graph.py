"""B1 LangGraph migration tests: graph output must match state-machine output for
identical inputs. The fixture setup mirrors ``test_teaching_state_machine`` so the
assertions prove behavior preservation.
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command
from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    AgentTrace,
    AnswerReleaseLevel,
    AttachmentKind,
    AttachmentStatus,
    Course,
    CourseMembership,
    CourseRole,
    CurriculumEdition,
    MembershipStatus,
    MultimodalExtraction,
    MultimodalExtractionKind,
    MultimodalExtractionStatus,
    SystemRole,
    TeachingMode,
    TeachingTurn,
    TeachingTurnStatus,
    User,
    UserAttachment,
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
from quantum_agent.multimodal.contracts import (
    Ambiguity,
    AmbiguityCandidate,
    ConfirmationState,
    DerivationStep,
    ExtractionMethod,
    VisualEvidence,
)
from quantum_agent.multimodal.teaching import (
    TeachingAttachmentNotFoundError,
    resolve_teaching_attachments,
)
from quantum_agent.science import ComplexValue, NumericalNormalizationRequest
from quantum_agent.teaching.hitl import (
    HitlAction,
    HitlAuthorizationError,
    HitlInterruptResponse,
    HitlRejectedResponse,
    HitlResolutionValidationError,
    HitlResumeRequest,
)
from quantum_agent.teaching.models import (
    ResponseStatus,
    SupportBasis,
    TeachingTurnInput,
    TeachingTurnResult,
    WorkflowStepName,
    WorkflowStepStatus,
)
from quantum_agent.tutor.graph import TutorGraph

API_ROOT = Path(__file__).resolve().parents[1]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
async def teaching_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "teaching.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, config, "head")
    engine: AsyncEngine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class TeachingSeed:
    def __init__(self, actor: CourseActor, edition_id: UUID) -> None:
        self.actor = actor
        self.edition_id = edition_id


async def _seed(session: AsyncSession) -> TeachingSeed:
    course = Course(code=f"QP-{uuid4()}", title="Quantum Physics")
    student = User(
        email=f"student-{uuid4()}@example.edu",
        display_name="Student",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add_all([course, student])
    await session.flush()
    edition = CurriculumEdition(
        course_id=course.id,
        edition_key="2026",
        title="2026 Quantum Physics",
    )
    session.add(edition)
    await session.flush()
    return TeachingSeed(
        actor=CourseActor(
            user_id=student.id,
            session_id=uuid4(),
            course_id=course.id,
            email=student.email,
            display_name=student.display_name,
            system_role=student.system_role,
            course_role=CourseRole.STUDENT,
        ),
        edition_id=edition.id,
    )


def _packet(course_id: UUID, edition_id: UUID, *, found: bool = True) -> EvidencePacket:
    if not found:
        return EvidencePacket(
            course_id=course_id,
            curriculum_edition_id=edition_id,
            query="波函数",
            coverage=RetrievalCoverage.NOT_FOUND,
        )
    source = "波函数的模方给出粒子在位置附近被发现的概率密度。"
    evidence_id = uuid4()
    chunk_id = uuid4()
    return EvidencePacket(
        course_id=course_id,
        curriculum_edition_id=edition_id,
        query="波函数",
        coverage=RetrievalCoverage.SUFFICIENT,
        evidence=[
            EvidenceItem(
                evidence_id=evidence_id,
                chunk_id=chunk_id,
                document_id=uuid4(),
                document_version_id=uuid4(),
                document_title="量子力学基础",
                document_version=1,
                source_file_name="2-量子力学基础.pdf",
                source_file_sha256="a" * 64,
                source_chunk_sha256=_sha(source),
                evidence_sha256=_sha(source),
                curriculum_edition_id=edition_id,
                chapter="第二章 量子力学基础",
                section_path=["波函数的统计解释"],
                locator=EvidenceLocator(
                    locator_type=LocatorType.PDF_PAGE,
                    physical_page=12,
                ),
                source_chunk=source,
                evidence_snippet=source,
                kind=EvidenceKind.COURSE_MATERIAL,
                authority_priority=100,
                contributions=[
                    RetrievalContribution(
                        channel=RetrievalChannel.FULL_TEXT,
                        rank=1,
                        raw_score=1.0,
                        fused_score=1.0,
                    )
                ],
            )
        ],
    )


class StaticRetriever:
    def __init__(self, packet: EvidencePacket) -> None:
        self.packet = packet
        self.scopes: list[RetrievalScope] = []

    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        self.scopes.append(scope)
        return self.packet.model_copy(update={"query": query})


async def _seed_visual_attachment(
    session: AsyncSession,
    seeded: TeachingSeed,
    *,
    status: MultimodalExtractionStatus,
    steps: tuple[str, ...],
    ambiguities: tuple[Ambiguity, ...] = (),
    confirmation_json: dict[str, object] | None = None,
    owner_user_id: UUID | None = None,
) -> tuple[UserAttachment, MultimodalExtraction]:
    owner_id = owner_user_id or seeded.actor.user_id
    content_hash = _sha(str(uuid4()))
    attachment = UserAttachment(
        course_id=seeded.actor.course_id,
        curriculum_edition_id=seeded.edition_id,
        owner_user_id=owner_id,
        kind=AttachmentKind.IMAGE,
        original_filename="derivation.png",
        detected_media_type="image/png",
        byte_size=128,
        content_sha256=content_hash,
        storage_key=f"sha256/{content_hash}",
        status=AttachmentStatus.READY,
        validation_json={},
    )
    session.add(attachment)
    await session.flush()
    needs_confirmation = status is MultimodalExtractionStatus.NEEDS_CONFIRMATION
    confirmation_state = (
        ConfirmationState.REQUIRED
        if needs_confirmation
        else (
            ConfirmationState.CONFIRMED
            if status is MultimodalExtractionStatus.CONFIRMED
            else ConfirmationState.NOT_REQUIRED
        )
    )
    evidence = VisualEvidence(
        attachment_id=attachment.id,
        original_file_reference=f"attachment:{attachment.id}",
        extraction_method=ExtractionMethod.QWEN_VISION,
        detected_text="\n".join(steps),
        derivation_steps=tuple(
            DerivationStep(
                ordinal=index,
                source_text=step,
                latex=step,
                confidence=0.6 if needs_confirmation else 0.99,
                ambiguity_ids=(ambiguities[0].ambiguity_id,) if ambiguities else (),
            )
            for index, step in enumerate(steps, start=1)
        ),
        confidence=0.6 if needs_confirmation else 0.99,
        ambiguities=ambiguities,
        confirmation_state=(
            ConfirmationState.REQUIRED
            if status
            in {
                MultimodalExtractionStatus.NEEDS_CONFIRMATION,
                MultimodalExtractionStatus.CONFIRMED,
            }
            else ConfirmationState.NOT_REQUIRED
        ),
        requires_confirmation=(
            status
            in {
                MultimodalExtractionStatus.NEEDS_CONFIRMATION,
                MultimodalExtractionStatus.CONFIRMED,
            }
        ),
    )
    extraction = MultimodalExtraction(
        attachment_id=attachment.id,
        course_id=seeded.actor.course_id,
        curriculum_edition_id=seeded.edition_id,
        owner_user_id=owner_id,
        kind=MultimodalExtractionKind.VISION,
        pipeline_name="student-visual-perception",
        pipeline_version="1.0.0",
        extraction_method=ExtractionMethod.QWEN_VISION.value,
        model_name="qwen3.8-chat",
        status=status,
        confidence=evidence.confidence,
        raw_output_json={},
        evidence_json=evidence.model_dump(mode="json"),
        ambiguities_json=[item.model_dump(mode="json") for item in ambiguities],
        requires_confirmation=needs_confirmation,
        confirmed_by_user_id=(
            owner_id if status is MultimodalExtractionStatus.CONFIRMED else None
        ),
        confirmed_at=(
            datetime.now(UTC)
            if status is MultimodalExtractionStatus.CONFIRMED
            else None
        ),
        confirmation_json=confirmation_json or {},
    )
    session.add(extraction)
    await session.flush()
    assert confirmation_state in {
        ConfirmationState.REQUIRED,
        ConfirmationState.CONFIRMED,
        ConfirmationState.NOT_REQUIRED,
    }
    return attachment, extraction


async def test_tutor_graph_matches_state_machine_fixed_workflow(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=None,
        )
        result = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="波函数的统计解释是什么？",
            ),
        )
        await session.commit()

    assert isinstance(result, TeachingTurnResult)
    assert result.release.release_level is AnswerReleaseLevel.FULL_EXPLANATION
    assert result.response.status is ResponseStatus.MODEL_DEGRADED
    assert result.response.claims[0].text == packet.evidence[0].evidence_snippet
    assert result.response.claims[0].support_basis is SupportBasis.COURSE_MATERIAL
    assert result.validation.passed
    assert [step.name for step in result.trace] == list(WorkflowStepName)


async def test_tutor_graph_matches_state_machine_tool_and_release(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=None,
        )
        science_request = NumericalNormalizationRequest(
            state=[ComplexValue(real=1.0), ComplexValue(real=0.0)]
        )
        first = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="这道习题的答案怎么做？",
                scientific_request=science_request,
            ),
        )
        assert isinstance(first, TeachingTurnResult)
        second = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                conversation_id=first.conversation_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                message="请检查我的习题归一化步骤。",
                student_attempt="我计算得到 |1|^2 + |0|^2 = 1。",
                scientific_request=science_request,
            ),
        )
        await session.commit()

    assert isinstance(second, TeachingTurnResult)
    assert first.release.release_level is AnswerReleaseLevel.HINT
    assert first.scientific_results == []
    assert first.trace[6].status is WorkflowStepStatus.SKIPPED
    assert second.release.release_level is AnswerReleaseLevel.SCAFFOLD
    assert second.scientific_results[0].passed is True
    assert second.trace[6].status is WorkflowStepStatus.COMPLETED


async def test_tutor_graph_fails_closed_on_missing_evidence(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id, found=False)
            ),
            model_gateway=None,
        )
        result = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="课程没有覆盖的任意新理论是什么？",
            ),
        )
        await session.commit()

    assert isinstance(result, TeachingTurnResult)
    assert result.release.release_level is AnswerReleaseLevel.QUESTION_ONLY
    assert result.response.status is ResponseStatus.INSUFFICIENT_COURSE_EVIDENCE
    assert result.response.claims == []
    assert result.response.limitations


async def _seed_staff(
    session: AsyncSession,
    seeded: TeachingSeed,
) -> CourseActor:
    student_membership = CourseMembership(
        course_id=seeded.actor.course_id,
        user_id=seeded.actor.user_id,
        role=CourseRole.STUDENT,
        status=MembershipStatus.ACTIVE,
        joined_at=datetime.now(UTC),
    )
    ta = User(
        email=f"ta-{uuid4()}@example.edu",
        display_name="Course TA",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add_all([student_membership, ta])
    await session.flush()
    session.add(
        CourseMembership(
            course_id=seeded.actor.course_id,
            user_id=ta.id,
            role=CourseRole.TA,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return CourseActor(
        user_id=ta.id,
        session_id=uuid4(),
        course_id=seeded.actor.course_id,
        email=ta.email,
        display_name=ta.display_name,
        system_role=ta.system_role,
        course_role=CourseRole.TA,
    )


async def test_hitl_interrupt_is_committed_idempotent_and_resumes_same_thread(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        ta_actor = await _seed_staff(session, seeded)
        await session.commit()
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id, found=False)
            ),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            enable_hitl=True,
        )
        interrupted = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="课程没有覆盖的任意新理论是什么？",
            ),
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        assert interrupted.interrupt.reasons == ("insufficient_coverage",)
        assert interrupted.artifacts.diagnosis is not None
        assert interrupted.artifacts.policy.mode is TeachingMode.LEARN_CONCEPTS
        assert interrupted.artifacts.proposed_response.claims == []

        turn = await session.get(TeachingTurn, interrupted.turn_id)
        assert turn is not None
        assert turn.status is TeachingTurnStatus.RUNNING
        assert turn.validation_json["hitl"]["interrupt_id"] == str(
            interrupted.interrupt.interrupt_id
        )

        replay = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                conversation_id=interrupted.conversation_id,
                mode=TeachingMode.LEARN_CONCEPTS,
                message="课程没有覆盖的任意新理论是什么？",
            ),
        )
        assert isinstance(replay, HitlInterruptResponse)
        assert replay.interrupt.interrupt_id == interrupted.interrupt.interrupt_id
        turn_count = await session.scalar(select(func.count(TeachingTurn.id)))
        assert turn_count == 1

        with pytest.raises(HitlAuthorizationError):
            await graph.resume(
                session=session,
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                conversation_id=interrupted.conversation_id,
                request=HitlResumeRequest(action=HitlAction.APPROVE),
            )

        completed = await graph.resume(
            session=session,
            actor=ta_actor,
            curriculum_edition_id=seeded.edition_id,
            conversation_id=interrupted.conversation_id,
            request=HitlResumeRequest(action=HitlAction.APPROVE),
        )
        assert isinstance(completed, TeachingTurnResult)
        assert completed.conversation_id == interrupted.conversation_id
        assert completed.turn_id == interrupted.turn_id
        assert completed.response.status is ResponseStatus.INSUFFICIENT_COURSE_EVIDENCE

        completed_turn = await session.get(TeachingTurn, interrupted.turn_id)
        assert completed_turn is not None
        assert completed_turn.status is TeachingTurnStatus.COMPLETED
        trace = await session.scalar(
            select(AgentTrace).where(AgentTrace.teaching_turn_id == turn.id)
        )
        assert trace is not None
        events = trace.steps_json["hitl_events"]
        assert len(events) == 1
        assert events[0]["resolution"]["actor_user_id"] == str(ta_actor.user_id)


async def test_hitl_rejects_reviewer_response_outside_release_envelope(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        ta_actor = await _seed_staff(session, seeded)
        await session.commit()
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            enable_hitl=True,
        )
        interrupted = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="@TA 请检查这次解释。",
            ),
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        invalid_response = interrupted.artifacts.proposed_response.model_copy(
            update={
                "claims": [
                    interrupted.artifacts.proposed_response.claims[0].model_copy(
                        update={"text": "This text is not a literal source span."}
                    )
                ]
            }
        )
        with pytest.raises(HitlResolutionValidationError):
            await graph.resume(
                session=session,
                actor=ta_actor,
                curriculum_edition_id=seeded.edition_id,
                conversation_id=interrupted.conversation_id,
                request=HitlResumeRequest(
                    action=HitlAction.EDIT,
                    edited_response=invalid_response,
                ),
            )
        inspected = await graph.inspect_interrupt(
            session=session,
            actor=ta_actor,
            curriculum_edition_id=seeded.edition_id,
            conversation_id=interrupted.conversation_id,
        )
        assert inspected.interrupt.interrupt_id == interrupted.interrupt.interrupt_id
        rejected = await graph.resume(
            session=session,
            actor=ta_actor,
            curriculum_edition_id=seeded.edition_id,
            conversation_id=interrupted.conversation_id,
            request=HitlResumeRequest(
                action=HitlAction.REJECT,
                note="The course team must add authoritative evidence before release.",
            ),
        )
        assert isinstance(rejected, HitlRejectedResponse)
        turn = await session.get(TeachingTurn, interrupted.turn_id)
        assert turn is not None
        await session.refresh(turn)
        assert turn.status is TeachingTurnStatus.FAILED
        assert turn.failure_code == "HITL_REJECTED"


async def test_tutor_graph_admits_scoped_visual_derivation_and_runs_safe_verifier(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        attachment, extraction = await _seed_visual_attachment(
            session,
            seeded,
            status=MultimodalExtractionStatus.SUCCEEDED,
            steps=("f = (x + 1)^2", "f = x^2 + 2*x + 1"),
        )
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id)
            ),
            model_gateway=None,
        )
        result = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.REVIEW_DERIVATIONS,
                message="请检查我上传的推导。",
                attachment_ids=[attachment.id],
            ),
        )
        assert isinstance(result, TeachingTurnResult)
        await session.commit()

        trace = await session.scalar(
            select(AgentTrace).where(AgentTrace.teaching_turn_id == result.turn_id)
        )

    assert len(result.scientific_results) == 1
    assert result.scientific_results[0].passed is True
    assert result.trace[6].status is WorkflowStepStatus.COMPLETED
    assert trace is not None
    perception = trace.steps_json["perception_trace"]
    assert perception[0]["attachment_id"] == str(attachment.id)
    assert perception[0]["extraction_id"] == str(extraction.id)
    assert perception[0]["scientific_derivation_ordinals"] == [1, 2]
    assert trace.steps_json["multimodal_evidence"][0]["evidence_type"] == "visual"


async def test_tutor_graph_does_not_claim_verifier_for_unparseable_visual_derivation(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        attachment, _ = await _seed_visual_attachment(
            session,
            seeded,
            status=MultimodalExtractionStatus.SUCCEEDED,
            steps=(r"\psi = \alpha|0\rangle", r"\psi = \beta|1\rangle"),
        )
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id)
            ),
            model_gateway=None,
        )
        result = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.REVIEW_DERIVATIONS,
                message="请检查这个态矢推导。",
                attachment_ids=[attachment.id],
            ),
        )

    assert isinstance(result, TeachingTurnResult)
    assert result.scientific_results == []
    assert result.trace[6].status is WorkflowStepStatus.SKIPPED
    assert "no deterministic verifier was run" in result.trace[6].detail


async def test_confirmed_attachment_resolutions_are_verbatim_and_not_silently_applied(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        ambiguity = Ambiguity(
            ambiguity_id="symbol-1",
            field_path="derivation_steps.0.source_text",
            reason="The handwritten symbol is ambiguous.",
            candidates=(
                AmbiguityCandidate(value="alpha", confidence=0.55),
                AmbiguityCandidate(value="a", confidence=0.45),
            ),
        )
        resolution = "  student selected alpha exactly  "
        attachment, extraction = await _seed_visual_attachment(
            session,
            seeded,
            status=MultimodalExtractionStatus.CONFIRMED,
            steps=("f = a + 1", "f = a + 2"),
            ambiguities=(ambiguity,),
            confirmation_json={
                "decision": "accept",
                "ambiguity_resolutions": {"symbol-1": resolution},
                "corrected_evidence": None,
                "original_evidence_preserved": True,
            },
        )
        resolved = await resolve_teaching_attachments(
            session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.REVIEW_DERIVATIONS,
                message="请检查确认后的转录。",
                attachment_ids=[attachment.id],
            ),
        )

    assert resolved.request.student_attempt is not None
    assert "f = a + 1" in resolved.request.student_attempt
    assert f"symbol-1: {resolution}" in resolved.request.student_attempt
    assert resolved.perception_trace[0].confirmed_ambiguity_resolutions == {
        "symbol-1": resolution
    }
    assert resolved.perception_trace[0].extraction_id == extraction.id
    assert resolved.request.scientific_request is None
    assert resolved.multimodal_evidence[0].ambiguities == (ambiguity,)


async def test_tutor_graph_interrupts_unconfirmed_ocr_then_resumes_same_thread(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        await _seed_staff(session, seeded)
        ambiguity = Ambiguity(
            ambiguity_id="symbol-1",
            field_path="derivation_steps.0.source_text",
            reason="The exponent is unclear.",
            candidates=(
                AmbiguityCandidate(value="2", confidence=0.6),
                AmbiguityCandidate(value="3", confidence=0.4),
            ),
        )
        attachment, extraction = await _seed_visual_attachment(
            session,
            seeded,
            status=MultimodalExtractionStatus.NEEDS_CONFIRMATION,
            steps=("f = (x + 1)^?", "f = x^2 + 2*x + 1"),
            ambiguities=(ambiguity,),
        )
        await session.commit()
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id)
            ),
            model_gateway=None,
            checkpointer=InMemorySaver(),
            enable_hitl=True,
        )
        request = TeachingTurnInput(
            mode=TeachingMode.REVIEW_DERIVATIONS,
            message="请检查这个手写推导。",
            attachment_ids=[attachment.id],
        )
        interrupted = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=request,
        )
        assert isinstance(interrupted, HitlInterruptResponse)
        assert interrupted.interrupt.reasons == ("ambiguous_transcription",)
        assert interrupted.artifacts.perception_trace[0].admitted_to_diagnosis is False
        assert interrupted.artifacts.perception_trace[0].extraction_id == extraction.id
        assert interrupted.artifacts.multimodal_evidence[0].requires_confirmation is True

        replay = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=request.model_copy(update={"conversation_id": interrupted.conversation_id}),
        )
        assert isinstance(replay, HitlInterruptResponse)
        assert replay.turn_id == interrupted.turn_id

        completed = await graph.resume(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            conversation_id=interrupted.conversation_id,
            request=HitlResumeRequest(
                action=HitlAction.CONFIRM_TRANSCRIPTION,
                confirmed_student_attempt=(
                    "f = (x + 1)^2\n"
                    "f = x^2 + 2*x + 1"
                ),
            ),
        )
        assert isinstance(completed, TeachingTurnResult)
        trace = await session.scalar(
            select(AgentTrace).where(AgentTrace.teaching_turn_id == completed.turn_id)
        )

    assert completed.conversation_id == interrupted.conversation_id
    assert completed.turn_id == interrupted.turn_id
    assert len(completed.scientific_results) == 1
    assert completed.scientific_results[0].passed is True
    assert trace is not None
    assert trace.steps_json["perception_trace"][0]["confirmation_source"] == "teaching_hitl"
    assert trace.steps_json["perception_trace"][0]["extraction_id"] == str(extraction.id)


async def test_tutor_attachment_resolution_hides_cross_user_ids(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        other = User(
            email=f"other-{uuid4()}@example.edu",
            display_name="Other Student",
            system_role=SystemRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(other)
        await session.flush()
        attachment, _ = await _seed_visual_attachment(
            session,
            seeded,
            status=MultimodalExtractionStatus.SUCCEEDED,
            steps=("f = x", "f = x + 1"),
            owner_user_id=other.id,
        )
        with pytest.raises(TeachingAttachmentNotFoundError):
            await resolve_teaching_attachments(
                session,
                actor=seeded.actor,
                curriculum_edition_id=seeded.edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.REVIEW_DERIVATIONS,
                    message="尝试读取另一个学生的附件。",
                    attachment_ids=[attachment.id],
                ),
            )
