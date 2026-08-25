from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    AgentTrace,
    AnswerPolicy,
    AnswerReleaseLevel,
    Course,
    CourseRole,
    CurriculumEdition,
    LearningEvidence,
    SystemRole,
    TeachingMode,
    TeachingTurn,
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
from quantum_agent.science import ComplexValue, NumericalNormalizationRequest
from quantum_agent.teaching.models import (
    ResponseStatus,
    SupportBasis,
    TeachingTurnInput,
    WorkflowStepName,
    WorkflowStepStatus,
)
from quantum_agent.teaching.repository import TeachingConversationConflictError
from quantum_agent.teaching.state_machine import TeachingStateMachine

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
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class TeachingSeed:
    def __init__(self, actor: CourseActor, edition_id: UUID, other_actor: CourseActor) -> None:
        self.actor = actor
        self.edition_id = edition_id
        self.other_actor = other_actor


async def _seed(session: AsyncSession) -> TeachingSeed:
    course = Course(code=f"QP-{uuid4()}", title="Quantum Physics")
    student = User(
        email=f"student-{uuid4()}@example.edu",
        display_name="Student",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    other = User(
        email=f"other-{uuid4()}@example.edu",
        display_name="Other student",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add_all([course, student, other])
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
        other_actor=CourseActor(
            user_id=other.id,
            session_id=uuid4(),
            course_id=course.id,
            email=other.email,
            display_name=other.display_name,
            system_role=other.system_role,
            course_role=CourseRole.STUDENT,
        ),
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


async def test_fixed_workflow_persists_trace_and_literal_course_evidence(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        machine = TeachingStateMachine(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=None,
        )
        result = await machine.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="波函数的统计解释是什么？",
            ),
        )
        await session.commit()

        trace = await session.scalar(
            select(AgentTrace).where(AgentTrace.teaching_turn_id == result.turn_id)
        )
        turn = await session.get(TeachingTurn, result.turn_id)

    assert result.release.release_level is AnswerReleaseLevel.FULL_EXPLANATION
    assert result.response.status is ResponseStatus.MODEL_DEGRADED
    assert result.response.claims[0].text == packet.evidence[0].evidence_snippet
    assert result.response.claims[0].support_basis is SupportBasis.COURSE_MATERIAL
    assert result.validation.passed
    assert [step.name for step in result.trace] == list(WorkflowStepName)
    assert trace is not None and trace.citation_validation_status == "passed"
    assert turn is not None and turn.response_json is not None


async def test_policy_blocks_tool_before_attempt_then_runs_it_after_attempt(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        machine = TeachingStateMachine(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=None,
        )
        science_request = NumericalNormalizationRequest(
            state=[ComplexValue(real=1.0), ComplexValue(real=0.0)]
        )
        first = await machine.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="这道习题的答案怎么做？",
                scientific_request=science_request,
            ),
        )
        second = await machine.run(
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
        learning = list(
            (
                await session.scalars(
                    select(LearningEvidence).where(
                        LearningEvidence.teaching_turn_id == second.turn_id
                    )
                )
            ).all()
        )

    assert first.release.release_level is AnswerReleaseLevel.HINT
    assert first.scientific_results == []
    assert first.trace[6].status is WorkflowStepStatus.SKIPPED
    assert second.release.release_level is AnswerReleaseLevel.SCAFFOLD
    assert second.scientific_results[0].passed is True
    assert second.trace[6].status is WorkflowStepStatus.COMPLETED
    assert any(
        claim.support_basis is SupportBasis.NUMERICAL_VERIFICATION
        for claim in second.response.claims
    )
    assert len(learning) == 1 and learning[0].mastery_delta == 0.0


async def test_teacher_policy_is_the_only_path_to_full_solution(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        session.add(
            AnswerPolicy(
                course_id=seeded.actor.course_id,
                curriculum_edition_id=seeded.edition_id,
                mode=TeachingMode.REVIEW_DERIVATIONS,
                allow_full_solution=True,
                minimum_attempts_for_scaffold=1,
                minimum_attempts_for_full_solution=1,
                max_hint_level=3,
                updated_by_user_id=seeded.actor.user_id,
            )
        )
        await session.flush()
        machine = TeachingStateMachine(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id)
            ),
            model_gateway=None,
        )
        result = await machine.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.REVIEW_DERIVATIONS,
                message="检查这一步推导。",
                student_attempt="我先把哈密顿算符作用到试探波函数上。",
            ),
        )
        await session.commit()

    assert result.policy.source == "teacher_configured"
    assert result.release.release_level is AnswerReleaseLevel.FULL_SOLUTION
    assert result.release.reason_code == "teacher_policy_full_solution_threshold_met"


async def test_missing_course_evidence_fails_closed(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        machine = TeachingStateMachine(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id, found=False)
            ),
            model_gateway=None,
        )
        result = await machine.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="课程没有覆盖的任意新理论是什么？",
            ),
        )
        await session.commit()

    assert result.release.release_level is AnswerReleaseLevel.QUESTION_ONLY
    assert result.response.status is ResponseStatus.INSUFFICIENT_COURSE_EVIDENCE
    assert result.response.claims == []
    assert result.response.limitations


async def test_conversation_scope_is_bound_to_authenticated_student(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        machine = TeachingStateMachine(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id)
            ),
            model_gateway=None,
        )
        first = await machine.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="解释波函数。",
            ),
        )
        with pytest.raises(TeachingConversationConflictError):
            await machine.run(
                session=session,
                actor=seeded.other_actor,
                curriculum_edition_id=seeded.edition_id,
                request=TeachingTurnInput(
                    conversation_id=first.conversation_id,
                    mode=TeachingMode.LEARN_CONCEPTS,
                    message="读取另一位学生的会话。",
                ),
            )


async def test_agent_trace_is_append_only_after_migration(
    teaching_database: async_sessionmaker[AsyncSession],
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        machine = TeachingStateMachine(
            evidence_retriever=StaticRetriever(
                _packet(seeded.actor.course_id, seeded.edition_id)
            ),
            model_gateway=None,
        )
        result = await machine.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.LEARN_CONCEPTS,
                message="解释测量。",
            ),
        )
        await session.commit()
        trace_id = await session.scalar(
            select(AgentTrace.id).where(AgentTrace.teaching_turn_id == result.turn_id)
        )
        assert trace_id is not None
        with pytest.raises(IntegrityError):
            await session.execute(
                update(AgentTrace)
                .where(AgentTrace.id == trace_id)
                .values(model_gateway_status="tampered")
            )
            await session.commit()
        await session.rollback()
