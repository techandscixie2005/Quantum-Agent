from __future__ import annotations

# Real fixture names intentionally preserve course-authored Chinese punctuation.
# ruff: noqa: RUF001
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from quantum_agent.database import create_session_factory
from quantum_agent.db_models import (
    Base,
    CandidateStatus,
    ChunkExtractionStatus,
    Course,
    CurriculumEdition,
    CurriculumOutlineSource,
    CurriculumUnit,
    DocumentChunk,
    DocumentPublication,
    DocumentStatus,
    DocumentVersionStatus,
    Evidence,
    ExtractionRun,
    GraphNodeCandidate,
    GraphNodeType,
    GraphRelationCandidate,
    GraphSyncOutbox,
    LocatorType,
    NodeCandidateEvidenceSupport,
    RelationCandidateEvidenceSupport,
    SourceAuthority,
    SourceDocument,
    SourceDocumentVersion,
    SourceRole,
)
from quantum_agent.knowledge.ingestion import IngestionConfig
from quantum_agent.knowledge.pipeline import (
    PersistenceInvariantError,
    PipelineConfig,
    SourceIntegrityError,
    ingest_course_manifest,
)
from quantum_agent.knowledge.source_manifest import load_manifest
from quantum_agent.llm.embeddings import HashingEmbeddingGateway

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "content" / "quantum_course" / "manifest.toml"


def _require_real_materials() -> None:
    knowledge = REPOSITORY_ROOT / "knowledge"
    if not knowledge.is_dir():
        pytest.skip("private course materials are not mounted")
    pytest.importorskip("pymupdf")
    pytest.importorskip("docx")
    pytest.importorskip("openpyxl")


async def _count(session: AsyncSession, model: Any) -> int:
    scalar = await session.scalar(select(func.count()).select_from(model))
    return int(scalar or 0)


async def _snapshot(session: AsyncSession) -> tuple[int, ...]:
    return tuple(
        [
            await _count(session, model)
            for model in (
                SourceDocument,
                SourceDocumentVersion,
                DocumentChunk,
                Evidence,
                CurriculumEdition,
                CurriculumOutlineSource,
                CurriculumUnit,
                ExtractionRun,
                GraphNodeCandidate,
                GraphRelationCandidate,
                NodeCandidateEvidenceSupport,
                RelationCandidateEvidenceSupport,
                DocumentPublication,
            )
        ]
    )


@pytest.mark.asyncio
async def test_real_manifest_pipeline_is_idempotent_scoped_and_fail_closed() -> None:
    _require_real_materials()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(
        database_connection: sqlite3.Connection,
        _connection_record: object,
    ) -> None:
        database_connection.execute("PRAGMA foreign_keys=ON")

    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    gateway = HashingEmbeddingGateway()
    async with session_factory() as session:
        first = await ingest_course_manifest(
            session,
            manifest_path=MANIFEST_PATH,
            repository_root=REPOSITORY_ROOT,
            embedding_gateway=gateway,
        )
        await session.commit()

    assert first.document_count == 12
    assert first.version_count == 12
    assert first.chunk_count == 2_204
    assert first.evidence_count == 2_204
    assert len(first.source_reports) == 12
    assert sum(report.parsed_units for report in first.source_reports) == 2_173
    assert (
        sum(
            report.parsed_units
            for report in first.source_reports
            if report.source_path.casefold().endswith(".pdf")
        )
        == 1_750
    )
    assert sum(report.parsed_chunks for report in first.source_reports) == 2_534
    assert sum(report.persisted_chunks for report in first.source_reports) == 2_204
    assert sum(report.persisted_evidence for report in first.source_reports) == 2_204
    assert sum(report.omitted_empty_units for report in first.source_reports) == 330
    assert first.embedding.retrieval_mode == "lexical_degraded"
    assert first.embedding.persisted_model_label == "local_hashing:lexical/degraded"
    assert first.structural.syllabus_chapter_roots == 6
    assert first.structural.taxonomy_roots == 8
    assert first.structural.syllabus_node_candidates == 63
    assert first.structural.syllabus_relation_candidates == 57
    assert first.structural.taxonomy_node_candidates == 335
    assert first.structural.taxonomy_relation_candidates == 419
    assert first.node_candidate_count == 398
    assert first.relation_candidate_count == 476
    assert first.student_visible_chunk_count == 0
    assert any("duplicate outline number '4.2.3'" in item for item in first.structural.diagnostics)

    manifest = load_manifest(MANIFEST_PATH)
    expected_hashes = {source.path: source.sha256 for source in manifest.sources}
    assert {report.source_path: report.sha256 for report in first.source_reports} == expected_hashes

    syllabus_id = first.curriculum_edition_ids["syllabus-2026-fall"]
    taxonomy_id = first.curriculum_edition_ids["lecture-decks-2022"]
    assert syllabus_id != taxonomy_id

    async with session_factory() as session:
        course = await session.get(Course, first.course_id)
        assert course is not None
        governance_metadata = course.settings_json["source_manifest_governance"]
        assert governance_metadata["alignment_hints"] == [
            hint.model_dump(mode="json", by_alias=True) for hint in manifest.alignment_hints
        ]
        assert all(
            hint["status"] == "REVIEW_REQUIRED" for hint in governance_metadata["alignment_hints"]
        )
        assert governance_metadata["alignment_hint_policy"] == {
            "status": "REVIEW_REQUIRED",
            "graph_effect": "NONE_UNTIL_EXPLICIT_TEACHER_APPROVAL",
            "scope": "CROSS_EDITION_GOVERNANCE_METADATA",
        }

        persisted_documents = (
            await session.scalars(select(SourceDocument).order_by(SourceDocument.logical_key))
        ).all()
        assert len(persisted_documents) == 12
        assert all(
            document.status == DocumentStatus.REVIEW_REQUIRED for document in persisted_documents
        )
        assert (
            sum(document.curriculum_edition_id == syllabus_id for document in persisted_documents)
            == 1
        )
        assert (
            sum(document.curriculum_edition_id == taxonomy_id for document in persisted_documents)
            == 8
        )
        assert sum(document.curriculum_edition_id is None for document in persisted_documents) == 3
        persisted_versions = (await session.scalars(select(SourceDocumentVersion))).all()
        assert all(
            version.status == DocumentVersionStatus.REVIEW_REQUIRED
            for version in persisted_versions
        )
        assert all(
            version.parser_version == "1.1.0"
            and version.source_metadata_json["ingestion_contract"]["parser_version"] == "1.1.0"
            and len(version.source_metadata_json["ingestion_contract"]["sha256"]) == 64
            for version in persisted_versions
        )
        assert {
            document.logical_key: document.authority_priority for document in persisted_documents
        } == {source.path: source.priority for source in manifest.sources}
        expected_authorities = {
            "course_policy": SourceAuthority.COURSE_PRIMARY,
            "course_structure": SourceAuthority.COURSE_PRIMARY,
            "course_material": SourceAuthority.COURSE_PRIMARY,
            "course_reference": SourceAuthority.COURSE_SUPPORTING,
            "reference": SourceAuthority.REFERENCE,
        }
        expected_roles = {
            "syllabus": SourceRole.SYLLABUS,
            "teacher_curated_taxonomy": SourceRole.KNOWLEDGE_EXPORT,
            "lecture_deck": SourceRole.LECTURE,
            "supplemental_text": SourceRole.REFERENCE,
            "textbook": SourceRole.TEXTBOOK,
            "scanned_textbook": SourceRole.TEXTBOOK,
        }
        documents_by_path = {document.logical_key: document for document in persisted_documents}
        assert all(
            documents_by_path[source.path].authority == expected_authorities[source.authority.value]
            and documents_by_path[source.path].source_role == expected_roles[source.kind]
            for source in manifest.sources
        )

        scanned_document = documents_by_path[
            "量子力学概论（翻译版） (格里菲斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
        ]
        scanned_version = await session.scalar(
            select(SourceDocumentVersion).where(
                SourceDocumentVersion.document_id == scanned_document.id
            )
        )
        assert scanned_version is not None
        empty_ocr_pages = scanned_version.parse_diagnostics_json["empty_source_units"]
        assert len(empty_ocr_pages) == 323
        assert all(page["status"] == "OCR_REQUIRED" for page in empty_ocr_pages)
        assert all(page["locator"]["physical_page"] is not None for page in empty_ocr_pages)

        taxonomy_document = documents_by_path["量子物理-知识图谱(1).xlsx"]
        taxonomy_chunk = await session.scalar(
            select(DocumentChunk)
            .join(SourceDocumentVersion)
            .where(SourceDocumentVersion.document_id == taxonomy_document.id)
            .order_by(DocumentChunk.ordinal)
            .limit(1)
        )
        assert taxonomy_chunk is not None
        assert taxonomy_chunk.locator_type == LocatorType.SHEET_ROW
        assert taxonomy_chunk.parser_metadata_json["source_locator"]["sheet_name"] == "Sheet3"

        lecture_document = documents_by_path["第1-2章.pdf"]
        lecture_chunks = (
            await session.scalars(
                select(DocumentChunk)
                .join(SourceDocumentVersion)
                .where(SourceDocumentVersion.document_id == lecture_document.id)
                .order_by(DocumentChunk.ordinal)
                .limit(20)
            )
        ).all()
        assert lecture_chunks
        assert all(chunk.locator_type == LocatorType.PAGE for chunk in lecture_chunks)
        assert all(chunk.physical_page is not None for chunk in lecture_chunks)
        assert any(chunk.bounding_boxes_json for chunk in lecture_chunks)

        syllabus_roots = (
            await session.scalars(
                select(CurriculumUnit).where(
                    CurriculumUnit.curriculum_edition_id == syllabus_id,
                    CurriculumUnit.parent_unit_id.is_(None),
                )
            )
        ).all()
        taxonomy_roots = (
            await session.scalars(
                select(CurriculumUnit).where(
                    CurriculumUnit.curriculum_edition_id == taxonomy_id,
                    CurriculumUnit.parent_unit_id.is_(None),
                )
            )
        ).all()
        assert len(syllabus_roots) == 6
        assert len(taxonomy_roots) == 8
        assert {root.title for root in syllabus_roots}.isdisjoint(
            {root.title for root in taxonomy_roots}
        )

        taxonomy_nodes = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphNodeCandidate)
                .where(GraphNodeCandidate.curriculum_edition_id == taxonomy_id)
            )
            or 0
        )
        taxonomy_relations = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphRelationCandidate)
                .where(GraphRelationCandidate.curriculum_edition_id == taxonomy_id)
            )
            or 0
        )
        taxonomy_chapters = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphNodeCandidate)
                .where(
                    GraphNodeCandidate.curriculum_edition_id == taxonomy_id,
                    GraphNodeCandidate.node_type == GraphNodeType.CHAPTER,
                )
            )
            or 0
        )
        assert (taxonomy_nodes, taxonomy_relations, taxonomy_chapters) == (335, 419, 8)
        extraction_runs = (await session.scalars(select(ExtractionRun))).all()
        validated_relation_counts = {
            run.pipeline_name: run.metrics_json["ontology_validated_relations"]
            for run in extraction_runs
        }
        assert validated_relation_counts == {
            "authored-docx-outline-structural-import": 57,
            "authored-xlsx-taxonomy-structural-import": 419,
        }

        assert await _count(session, DocumentPublication) == 0
        assert await _count(session, GraphSyncOutbox) == 0
        assert await _count(session, NodeCandidateEvidenceSupport) == 398
        assert await _count(session, RelationCandidateEvidenceSupport) == 476
        assert (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(DocumentChunk.extraction_status == ChunkExtractionStatus.APPROVED)
                )
                or 0
            )
            == 0
        )
        assert (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(GraphNodeCandidate)
                    .where(GraphNodeCandidate.status != CandidateStatus.REVIEW_REQUIRED)
                )
                or 0
            )
            == 0
        )
        assert (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(GraphRelationCandidate)
                    .where(GraphRelationCandidate.status != CandidateStatus.REVIEW_REQUIRED)
                )
                or 0
            )
            == 0
        )
        evidence_sample = (
            await session.scalars(select(Evidence).order_by(Evidence.created_at).limit(50))
        ).all()
        chunks_by_id = {
            chunk.id: chunk
            for chunk in (
                await session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.id.in_(
                            [evidence.source_chunk_id for evidence in evidence_sample]
                        )
                    )
                )
            ).all()
        }
        assert evidence_sample
        assert all(
            evidence.evidence_snippet
            == chunks_by_id[evidence.source_chunk_id].content[
                evidence.char_start : evidence.char_end
            ]
            for evidence in evidence_sample
        )
        preserved_document = persisted_documents[0]
        preserved_document.status = DocumentStatus.APPROVED
        preserved_chunk = chunks_by_id[evidence_sample[0].source_chunk_id]
        preserved_chunk.extraction_status = ChunkExtractionStatus.APPROVED
        preserved_node_candidate = await session.scalar(
            select(GraphNodeCandidate).order_by(GraphNodeCandidate.created_at).limit(1)
        )
        preserved_relation_candidate = await session.scalar(
            select(GraphRelationCandidate).order_by(GraphRelationCandidate.created_at).limit(1)
        )
        assert preserved_node_candidate is not None
        assert preserved_relation_candidate is not None
        preserved_node_candidate.status = CandidateStatus.IN_REVIEW
        preserved_relation_candidate.status = CandidateStatus.IN_REVIEW
        preserved_document_id = preserved_document.id
        preserved_chunk_id = preserved_chunk.id
        preserved_node_candidate_id = preserved_node_candidate.id
        preserved_relation_candidate_id = preserved_relation_candidate.id
        await session.commit()
        first_snapshot = await _snapshot(session)

    async with session_factory() as session:
        second = await ingest_course_manifest(
            session,
            manifest_path=MANIFEST_PATH,
            repository_root=REPOSITORY_ROOT,
            embedding_gateway=gateway,
        )
        await session.commit()
        second_snapshot = await _snapshot(session)
        loaded_document_after_reingest = await session.get(
            SourceDocument, preserved_document_id
        )
        loaded_chunk_after_reingest = await session.get(DocumentChunk, preserved_chunk_id)
        loaded_node_after_reingest = await session.get(
            GraphNodeCandidate, preserved_node_candidate_id
        )
        loaded_relation_after_reingest = await session.get(
            GraphRelationCandidate, preserved_relation_candidate_id
        )
        assert loaded_document_after_reingest is not None
        assert loaded_chunk_after_reingest is not None
        assert loaded_node_after_reingest is not None
        assert loaded_relation_after_reingest is not None
        assert loaded_document_after_reingest.status == DocumentStatus.APPROVED
        assert loaded_chunk_after_reingest.extraction_status == ChunkExtractionStatus.APPROVED
        assert loaded_node_after_reingest.status == CandidateStatus.IN_REVIEW
        assert loaded_relation_after_reingest.status == CandidateStatus.IN_REVIEW

    assert second_snapshot == first_snapshot
    assert second.document_count == 12
    assert second.version_count == 12
    assert second.structural.taxonomy_node_candidates == 335
    assert second.structural.taxonomy_relation_candidates == 419
    assert second.student_visible_chunk_count == 0

    async with session_factory() as session:
        snapshot_before_changed_config = await _snapshot(session)
        with pytest.raises(PersistenceInvariantError, match="parser/chunk configuration"):
            await ingest_course_manifest(
                session,
                manifest_path=MANIFEST_PATH,
                repository_root=REPOSITORY_ROOT,
                embedding_gateway=gateway,
                config=PipelineConfig(
                    ingestion=IngestionConfig(max_chunk_chars=1_700),
                ),
            )
        await session.rollback()
    async with session_factory() as session:
        assert await _snapshot(session) == snapshot_before_changed_config
        loaded_document_after_rollback = await session.get(
            SourceDocument, preserved_document_id
        )
        loaded_chunk_after_rollback = await session.get(DocumentChunk, preserved_chunk_id)
        loaded_node_after_rollback = await session.get(
            GraphNodeCandidate, preserved_node_candidate_id
        )
        loaded_relation_after_rollback = await session.get(
            GraphRelationCandidate, preserved_relation_candidate_id
        )
        assert loaded_document_after_rollback is not None
        assert loaded_chunk_after_rollback is not None
        assert loaded_node_after_rollback is not None
        assert loaded_relation_after_rollback is not None
        assert loaded_document_after_rollback.status == DocumentStatus.APPROVED
        assert loaded_chunk_after_rollback.extraction_status == ChunkExtractionStatus.APPROVED
        assert loaded_node_after_rollback.status == CandidateStatus.IN_REVIEW
        assert loaded_relation_after_rollback.status == CandidateStatus.IN_REVIEW
    await engine.dispose()


@pytest.mark.asyncio
async def test_manifest_hash_failure_writes_nothing(tmp_path: Path) -> None:
    _require_real_materials()
    tampered_manifest = tmp_path / "manifest.toml"
    original = MANIFEST_PATH.read_text(encoding="utf-8")
    tampered_manifest.write_text(
        original.replace(
            "b70af9b50c701779de8ab753eaacbd576451529a98f993a618f4a5c57baeb3dc",
            "070af9b50c701779de8ab753eaacbd576451529a98f993a618f4a5c57baeb3dc",
            1,
        ),
        encoding="utf-8",
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        with pytest.raises(SourceIntegrityError, match="sha256_mismatch"):
            await ingest_course_manifest(
                session,
                manifest_path=tampered_manifest,
                repository_root=REPOSITORY_ROOT,
                embedding_gateway=HashingEmbeddingGateway(),
            )
        assert await _count(session, SourceDocument) == 0
        await session.rollback()
    await engine.dispose()
