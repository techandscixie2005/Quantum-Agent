from __future__ import annotations

# Exact course labels intentionally preserve the source worksheet's Chinese text.
import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from quantum_agent.auth import (
    CourseActor,
    SessionCredential,
    authenticate_course_actor,
    hash_session_token,
    issue_opaque_session_token,
)
from quantum_agent.database import create_session_factory
from quantum_agent.db_models import (
    AgentTrace,
    AnswerReleaseLevel,
    CandidateStatus,
    ChunkExtractionStatus,
    CourseMembership,
    CourseRole,
    DocumentChunk,
    DocumentPublication,
    DocumentVersionStatus,
    Evidence,
    EvidenceStatus,
    GraphNodeCandidate,
    LearningEvidence,
    LearningEvidenceKind,
    MembershipStatus,
    PublicationStatus,
    SourceDocument,
    SourceDocumentVersion,
    SystemRole,
    TeachingMode,
    TeachingTaskKind,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.knowledge.evidence_packets import (
    EvidenceItem,
    EvidencePacket,
    LocatorType,
    RetrievalChannel,
)
from quantum_agent.knowledge.graph_store import InMemoryGraphStore
from quantum_agent.knowledge.graph_sync import GraphOutboxWorker
from quantum_agent.knowledge.pipeline import ingest_course_manifest
from quantum_agent.knowledge.retrieval import (
    HybridEvidenceRetriever,
    StudentVisibleEvidenceRepository,
)
from quantum_agent.knowledge.review import ReviewService
from quantum_agent.llm.embeddings import HashingEmbeddingGateway
from quantum_agent.science import (
    ComplexValue,
    NumericalNormalizationRequest,
    ScientificVerificationKind,
    ScientificVerificationMethod,
    ScientificVerificationStatus,
)
from quantum_agent.teaching.models import (
    ResponseStatus,
    SupportBasis,
    TeachingTurnInput,
    WorkflowStepName,
    WorkflowStepStatus,
)
from quantum_agent.teaching.state_machine import TeachingStateMachine

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "content" / "quantum_course" / "manifest.toml"
TAXONOMY_FILENAME = "量子物理-知识图谱(1).xlsx"
CONCEPT_LABEL = "波函数的统计解释"


def _require_real_materials() -> None:
    if not (REPOSITORY_ROOT / "knowledge").is_dir():
        pytest.skip("private course materials are not mounted")


async def _authenticated_actor(
    session: AsyncSession,
    *,
    course_id: UUID,
    role: CourseRole,
    email: str,
) -> CourseActor:
    user = User(
        email=email,
        display_name=f"Phase 2 real {role.value}",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    raw_token = issue_opaque_session_token()
    session.add(
        UserSession(
            user_id=user.id,
            session_token_sha256=hash_session_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    session.add(
        CourseMembership(
            course_id=course_id,
            user_id=user.id,
            role=role,
            status=MembershipStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return await authenticate_course_actor(
        session,
        credential=SessionCredential(token=raw_token),
        course_id=course_id,
        allowed_roles=frozenset({role}),
    )


def _taxonomy_citation(packet: EvidencePacket) -> EvidenceItem:
    citation = next(
        item
        for item in packet.evidence
        if item.source_file_name == TAXONOMY_FILENAME
        and item.locator.locator_type is LocatorType.XLSX_ROW
        and item.locator.sheet_name == "Sheet3"
        and item.locator.row_start == 41
    )
    assert CONCEPT_LABEL in citation.evidence_snippet
    assert citation.evidence_snippet in citation.source_chunk
    assert citation.source_chunk_sha256 == hashlib.sha256(
        citation.source_chunk.encode("utf-8")
    ).hexdigest()
    assert citation.evidence_sha256 == hashlib.sha256(
        citation.evidence_snippet.encode("utf-8")
    ).hexdigest()
    taxonomy_path = REPOSITORY_ROOT / "knowledge" / TAXONOMY_FILENAME
    assert citation.source_file_sha256 == hashlib.sha256(taxonomy_path.read_bytes()).hexdigest()
    return citation


async def test_real_course_evidence_drives_attempt_gated_teaching_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase-2 smoke: real approved evidence -> policy/tool workflow -> durable traces."""

    _require_real_materials()
    database_path = tmp_path / "phase2-real.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    alembic_config = Config(str(API_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(API_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    engine = create_async_engine(database_url)
    session_factory = create_session_factory(engine)
    embedding = HashingEmbeddingGateway()
    try:
        async with session_factory() as session:
            report = await ingest_course_manifest(
                session,
                manifest_path=MANIFEST_PATH,
                repository_root=REPOSITORY_ROOT,
                embedding_gateway=embedding,
            )
            await session.commit()

        taxonomy_edition_id = report.curriculum_edition_ids["lecture-decks-2022"]
        async with session_factory() as session:
            teacher = await _authenticated_actor(
                session,
                course_id=report.course_id,
                role=CourseRole.TEACHER,
                email="phase2-real-teacher@example.edu",
            )
            student = await _authenticated_actor(
                session,
                course_id=report.course_id,
                role=CourseRole.STUDENT,
                email="phase2-real-student@example.edu",
            )
            taxonomy_document = await session.scalar(
                select(SourceDocument).where(
                    SourceDocument.course_id == report.course_id,
                    SourceDocument.source_filename == TAXONOMY_FILENAME,
                )
            )
            assert taxonomy_document is not None
            taxonomy_version = await session.scalar(
                select(SourceDocumentVersion).where(
                    SourceDocumentVersion.document_id == taxonomy_document.id
                )
            )
            candidate = await session.scalar(
                select(GraphNodeCandidate).where(
                    GraphNodeCandidate.course_id == report.course_id,
                    GraphNodeCandidate.curriculum_edition_id == taxonomy_edition_id,
                    GraphNodeCandidate.label == CONCEPT_LABEL,
                )
            )
            assert taxonomy_version is not None and candidate is not None

            review = ReviewService(session)
            await review.approve_document_version(
                actor=teacher,
                curriculum_edition_id=taxonomy_edition_id,
                document_version_id=taxonomy_version.id,
                rationale="Verified the teacher-authored taxonomy and exact worksheet locators.",
            )
            await review.publish_document_version(
                actor=teacher,
                curriculum_edition_id=taxonomy_edition_id,
                document_version_id=taxonomy_version.id,
                rationale="Publish the reviewed taxonomy as student-visible course evidence.",
                priority=100,
            )
            await review.approve_node(
                actor=teacher,
                curriculum_edition_id=taxonomy_edition_id,
                candidate_id=candidate.id,
                rationale="The concept label is an exact claim on Sheet3 row 41.",
            )
            await session.commit()
            candidate_id = candidate.id
            taxonomy_document_id = taxonomy_document.id
            taxonomy_version_id = taxonomy_version.id
            student_actor = student

        graph = InMemoryGraphStore()
        worker = GraphOutboxWorker(
            session_factory=session_factory,
            graph_store=graph,
            worker_id="phase2-real-smoke",
        )
        assert await worker.run_batch(limit=10) == 1
        retriever = HybridEvidenceRetriever(
            repository=StudentVisibleEvidenceRepository(session_factory),
            embedding_gateway=embedding,
            graph_store=graph,
        )
        machine = TeachingStateMachine(
            evidence_retriever=retriever,
            model_gateway=None,
        )

        async with session_factory() as session:
            concept_turn = await machine.run(
                session=session,
                actor=student_actor,
                curriculum_edition_id=taxonomy_edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.LEARN_CONCEPTS,
                    message=CONCEPT_LABEL,
                    # PRD V3.0 P0-1: a concept question with no factual-lookup
                    # marker requires a commitment.  Submit a student attempt
                    # so the gate is satisfied and the concept-explanation
                    # path (FULL_EXPLANATION with the taxonomy citation) is
                    # exercised, matching the test's intent.
                    student_attempt="我预测波函数的统计解释与概率密度有关。",
                ),
            )
            exercise_turn = await machine.run(
                session=session,
                actor=student_actor,
                curriculum_edition_id=taxonomy_edition_id,
                request=TeachingTurnInput(
                    mode=TeachingMode.REVIEW_DERIVATIONS,
                    message=CONCEPT_LABEL,
                    student_attempt="我取态矢量 (1, 0), 计算 |1|^2 + |0|^2 = 1。",
                    scientific_request=NumericalNormalizationRequest(
                        state=[ComplexValue(real=1.0), ComplexValue(real=0.0)]
                    ),
                ),
            )
            await session.commit()

            traces = list(
                (
                    await session.scalars(
                        select(AgentTrace).where(
                            AgentTrace.teaching_turn_id.in_(
                                (concept_turn.turn_id, exercise_turn.turn_id)
                            )
                        )
                    )
                ).all()
            )
            learning = list(
                (
                    await session.scalars(
                        select(LearningEvidence).where(
                            LearningEvidence.teaching_turn_id == exercise_turn.turn_id
                        )
                    )
                ).all()
            )

            publication = await session.scalar(
                select(DocumentPublication).where(
                    DocumentPublication.document_version_id == taxonomy_version_id,
                    DocumentPublication.curriculum_edition_id == taxonomy_edition_id,
                )
            )
            version = await session.get(SourceDocumentVersion, taxonomy_version_id)
            approved_candidate = await session.get(GraphNodeCandidate, candidate_id)
            cited_chunk_ids = {
                item.chunk_id
                for result in (concept_turn, exercise_turn)
                for item in result.evidence_packet.evidence
            }
            cited_chunks = list(
                (
                    await session.scalars(
                        select(DocumentChunk).where(DocumentChunk.id.in_(cited_chunk_ids))
                    )
                ).all()
            )
            cited_evidence = list(
                (
                    await session.scalars(
                        select(Evidence).where(Evidence.source_chunk_id.in_(cited_chunk_ids))
                    )
                ).all()
            )

        concept_citation = _taxonomy_citation(concept_turn.evidence_packet)
        exercise_citation = _taxonomy_citation(exercise_turn.evidence_packet)
        assert concept_citation.document_id == taxonomy_document_id
        assert exercise_citation.document_id == taxonomy_document_id
        assert concept_citation.curriculum_edition_id == taxonomy_edition_id
        assert exercise_citation.curriculum_edition_id == taxonomy_edition_id
        assert RetrievalChannel.SEMANTIC in concept_turn.evidence_packet.degraded_channels
        assert any(node.id == candidate_id for node in concept_turn.evidence_packet.graph_nodes)

        assert concept_turn.policy.source == "safe_default"
        assert concept_turn.interpretation.task_kind is TeachingTaskKind.CONCEPT_QUESTION
        assert concept_turn.release.release_level is AnswerReleaseLevel.FULL_EXPLANATION
        assert concept_turn.response.status is ResponseStatus.MODEL_DEGRADED
        assert concept_turn.response.claims[0].text == concept_citation.evidence_snippet
        assert concept_turn.response.claims[0].support_basis is SupportBasis.COURSE_MATERIAL

        assert exercise_turn.policy.source == "safe_default"
        assert exercise_turn.policy.allow_full_solution is False
        assert exercise_turn.interpretation.task_kind is TeachingTaskKind.DERIVATION_CHECK
        assert exercise_turn.release.release_level is AnswerReleaseLevel.SCAFFOLD
        assert exercise_turn.release.reason_code == "attempt_threshold_for_scaffold_met"
        assert exercise_turn.release.attempts_observed == 1
        assert len(exercise_turn.scientific_results) == 1
        scientific = exercise_turn.scientific_results[0]
        assert scientific.kind is ScientificVerificationKind.NUMERICAL_NORMALIZATION
        assert scientific.method is ScientificVerificationMethod.NUMERICAL
        assert scientific.status is ScientificVerificationStatus.PASS
        assert scientific.tool.name == "numpy"
        assert scientific.metrics["norm_squared"] == 1.0
        assert scientific.limitations == ["Finite-precision complex128 arithmetic was used."]
        assert exercise_turn.trace[6].status is WorkflowStepStatus.COMPLETED
        assert any(
            claim.support_basis is SupportBasis.NUMERICAL_VERIFICATION
            for claim in exercise_turn.response.claims
        )

        expected_workflow = list(WorkflowStepName)
        assert len(expected_workflow) == 10
        for result in (concept_turn, exercise_turn):
            assert [step.name for step in result.trace] == expected_workflow
            assert result.validation.passed
        assert len(traces) == 2
        traces_by_turn = {trace.teaching_turn_id: trace for trace in traces}
        for result in (concept_turn, exercise_turn):
            assert traces_by_turn[result.turn_id].steps_json["steps"] == [
                step.model_dump(mode="json") for step in result.trace
            ]
        assert all(trace.citation_validation_status == "passed" for trace in traces)
        assert len(learning) == 1
        assert learning[0].kind is LearningEvidenceKind.STUDENT_ATTEMPT
        assert learning[0].mastery_delta == 0.0
        assert learning[0].concept_candidate_id == candidate_id

        assert publication is not None and publication.status is PublicationStatus.PUBLISHED
        assert version is not None and version.status is DocumentVersionStatus.PUBLISHED
        assert approved_candidate is not None
        assert approved_candidate.status is CandidateStatus.APPROVED
        assert cited_chunks and len(cited_chunks) == len(cited_chunk_ids)
        assert all(
            chunk.document_version_id == taxonomy_version_id
            and chunk.extraction_status is ChunkExtractionStatus.APPROVED
            for chunk in cited_chunks
        )
        assert cited_evidence
        assert all(item.status is EvidenceStatus.GROUNDED for item in cited_evidence)
    finally:
        await engine.dispose()
