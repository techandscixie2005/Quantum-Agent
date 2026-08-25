"""Transactional, idempotent persistence for authoritative course materials.

The original files remain the source of truth.  This pipeline verifies the
manifest hashes before writing, persists immutable versions/chunks/evidence,
and delegates only authored DOCX/XLSX structure to the deterministic structural
importer.  It never publishes a document or approves graph knowledge.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.db_models import (
    EMBEDDING_DIMENSION,
    ChunkExtractionStatus,
    Course,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    DocumentChunk,
    DocumentPublication,
    DocumentStatus,
    DocumentType,
    DocumentVersionStatus,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    GraphNodeCandidate,
    GraphRelationCandidate,
    PublicationStatus,
    SourceDocument,
    SourceDocumentVersion,
    SourceRole,
)
from quantum_agent.db_models import (
    LocatorType as DatabaseLocatorType,
)
from quantum_agent.db_models import (
    SourceAuthority as DatabaseSourceAuthority,
)
from quantum_agent.knowledge.ingestion import (
    IngestedDocument,
    IngestionConfig,
    IngestionStatus,
    SourceChunk,
    SourceUnit,
    parse_document,
    parse_scanned_pdf_document,
    sha256_text,
)
from quantum_agent.knowledge.ingestion import (
    LocatorType as IngestionLocatorType,
)
from quantum_agent.knowledge.source_manifest import (
    CourseSourceManifest,
    ManifestSource,
    load_manifest,
    verify_sources,
)
from quantum_agent.knowledge.source_manifest import (
    SourceAuthority as ManifestAuthority,
)
from quantum_agent.knowledge.structural_import import (
    StructuralImportReport,
    StructuralSourceContext,
    import_authored_structures,
)
from quantum_agent.llm.embeddings import EmbeddingGateway

PIPELINE_VERSION = "1.0.0"
ONTOLOGY_VERSION = "1.0.0"
IDENTITY_NAMESPACE = "quantum-agent:identity:v1"
INGESTION_CONTRACT_VERSION = "1"
MANIFEST_SETTINGS_KEY = "source_manifest_governance"


class PipelineError(RuntimeError):
    """Base error for an ingestion transaction that must not be committed."""


class SourceIntegrityError(PipelineError):
    """Raised before persistence when a manifest source is missing or changed."""


class PersistenceInvariantError(PipelineError):
    """Raised when a stable persisted identity disagrees with source provenance."""


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    embedding_batch_size: int = Field(default=64, ge=1, le=512)
    pipeline_version: str = PIPELINE_VERSION
    ontology_version: str = ONTOLOGY_VERSION


class EmbeddingRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    provider: str
    persisted_model_label: str | None
    retrieval_mode: Literal["semantic", "lexical_degraded", "unavailable"]
    dimensions: int | None
    detail: str | None = None


class SourcePersistenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_path: str
    sha256: str
    document_id: UUID
    document_version_id: UUID
    parsed_units: int
    parsed_chunks: int
    persisted_chunks: int
    persisted_evidence: int
    omitted_empty_units: int
    statuses: dict[str, int]


class KnowledgePipelineReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_ids: dict[str, UUID]
    source_reports: tuple[SourcePersistenceReport, ...]
    embedding: EmbeddingRunReport
    structural: StructuralImportReport
    document_count: int
    version_count: int
    chunk_count: int
    evidence_count: int
    node_candidate_count: int
    relation_candidate_count: int
    student_visible_chunk_count: int


def deterministic_uuid(kind: str, *parts: object) -> UUID:
    """Generate stable database IDs without treating parser IDs as UUIDs."""

    payload = "|".join(str(part) for part in parts)
    return uuid5(NAMESPACE_URL, f"{IDENTITY_NAMESPACE}:{kind}:{payload}")


def course_advisory_lock_key(course_key: str) -> int:
    """Return the stable signed int64 used by PostgreSQL advisory locking."""

    digest = bytes.fromhex(sha256_text(f"{IDENTITY_NAMESPACE}:course-import:{course_key}"))
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _acquire_course_import_lock(session: AsyncSession, course_key: str) -> None:
    """Serialize writes for one course for the lifetime of the current transaction."""

    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(CAST(:lock_key AS BIGINT))"),
        {"lock_key": course_advisory_lock_key(course_key)},
    )


_DOCUMENT_TYPE_BY_KIND: dict[str, DocumentType] = {
    "syllabus": DocumentType.SYLLABUS,
    "teacher_curated_taxonomy": DocumentType.KNOWLEDGE_EXPORT,
    "lecture_deck": DocumentType.LECTURE_SLIDES,
    "supplemental_text": DocumentType.NOTES,
    "textbook": DocumentType.TEXTBOOK,
    "scanned_textbook": DocumentType.TEXTBOOK,
}

_SOURCE_ROLE_BY_KIND: dict[str, SourceRole] = {
    "syllabus": SourceRole.SYLLABUS,
    "teacher_curated_taxonomy": SourceRole.KNOWLEDGE_EXPORT,
    "lecture_deck": SourceRole.LECTURE,
    "supplemental_text": SourceRole.REFERENCE,
    "textbook": SourceRole.TEXTBOOK,
    "scanned_textbook": SourceRole.TEXTBOOK,
}

_AUTHORITY_MAP: dict[ManifestAuthority, DatabaseSourceAuthority] = {
    ManifestAuthority.COURSE_POLICY: DatabaseSourceAuthority.COURSE_PRIMARY,
    ManifestAuthority.COURSE_STRUCTURE: DatabaseSourceAuthority.COURSE_PRIMARY,
    ManifestAuthority.COURSE_MATERIAL: DatabaseSourceAuthority.COURSE_PRIMARY,
    ManifestAuthority.COURSE_REFERENCE: DatabaseSourceAuthority.COURSE_SUPPORTING,
    ManifestAuthority.REFERENCE: DatabaseSourceAuthority.REFERENCE,
}

_LOCATOR_MAP: dict[IngestionLocatorType, DatabaseLocatorType] = {
    IngestionLocatorType.PAGE: DatabaseLocatorType.PAGE,
    IngestionLocatorType.SLIDE: DatabaseLocatorType.SLIDE,
    IngestionLocatorType.PARAGRAPH: DatabaseLocatorType.PARAGRAPH,
    IngestionLocatorType.SHEET_ROW: DatabaseLocatorType.SHEET_ROW,
    IngestionLocatorType.LINE: DatabaseLocatorType.LINE,
}


def _document_type(source: ManifestSource) -> DocumentType:
    return _DOCUMENT_TYPE_BY_KIND.get(source.kind, DocumentType.OTHER)


def _source_role(source: ManifestSource) -> SourceRole:
    return _SOURCE_ROLE_BY_KIND.get(source.kind, SourceRole.OTHER)


def _jsonable_mapping(value: Mapping[str, object]) -> dict[str, object]:
    loaded = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return cast(dict[str, object], loaded)


def _manifest_governance_metadata(manifest: CourseSourceManifest) -> dict[str, object]:
    """Keep authored alignments auditable without materializing graph edges."""

    return {
        "manifest_schema_version": manifest.schema_version,
        "governance": manifest.governance.model_dump(mode="json"),
        "alignment_hints": [
            hint.model_dump(mode="json", by_alias=True) for hint in manifest.alignment_hints
        ],
        "alignment_hint_policy": {
            "status": "REVIEW_REQUIRED",
            "graph_effect": "NONE_UNTIL_EXPLICIT_TEACHER_APPROVAL",
            "scope": "CROSS_EDITION_GOVERNANCE_METADATA",
        },
    }


def _ingestion_contract(
    parsed: IngestedDocument,
    config: IngestionConfig,
) -> dict[str, object]:
    contract: dict[str, object] = {
        "contract_version": INGESTION_CONTRACT_VERSION,
        "parser_name": parsed.parser_name,
        "parser_version": parsed.parser_version,
        "chunking_configuration": config.model_dump(mode="json"),
    }
    encoded = json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {**contract, "sha256": sha256_text(encoded)}


def _chunk_status(status: IngestionStatus) -> ChunkExtractionStatus:
    return {
        IngestionStatus.READY: ChunkExtractionStatus.EXTRACTED,
        IngestionStatus.REVIEW_REQUIRED: ChunkExtractionStatus.REVIEW_REQUIRED,
        IngestionStatus.OCR_REQUIRED: ChunkExtractionStatus.OCR_REQUIRED,
    }[status]


def _chunk_quality(status: IngestionStatus) -> float:
    return {
        IngestionStatus.READY: 1.0,
        IngestionStatus.REVIEW_REQUIRED: 0.5,
        IngestionStatus.OCR_REQUIRED: 0.0,
    }[status]


def _locator_fields(chunk: SourceChunk) -> dict[str, object | None]:
    locator = chunk.locator
    return {
        "locator_type": _LOCATOR_MAP[locator.locator_type],
        "locator_start": str(locator.start),
        "locator_end": str(locator.end),
        "physical_page": locator.physical_page,
        "printed_page_label": locator.page_label,
        "slide_number": (
            int(locator.start) if locator.locator_type == IngestionLocatorType.SLIDE else None
        ),
        "paragraph_start": (
            int(locator.start) if locator.locator_type == IngestionLocatorType.PARAGRAPH else None
        ),
        "paragraph_end": (
            int(locator.end) if locator.locator_type == IngestionLocatorType.PARAGRAPH else None
        ),
    }


def _bounding_boxes(unit: SourceUnit) -> list[dict[str, object]]:
    return [
        {
            "block_ordinal": block.ordinal,
            "bbox": list(block.bbox),
            "kind": block.kind,
            "region": block.region,
            "removed_as_repeated_marginalia": block.removed_as_repeated_marginalia,
            "metadata": _jsonable_mapping(block.metadata),
        }
        for block in unit.blocks
        if block.bbox is not None
    ]


def _chunk_parser_metadata(chunk: SourceChunk, unit: SourceUnit) -> dict[str, object]:
    return {
        "ingestion_chunk_id": chunk.id,
        "ingestion_source_unit_id": unit.id,
        "content_char_start": chunk.content_char_start,
        "content_char_end": chunk.content_char_end,
        "evidence_char_start": chunk.evidence_char_start,
        "evidence_char_end": chunk.evidence_char_end,
        "evidence_snippet_basis": chunk.evidence_snippet_basis,
        "source_unit_raw_text": unit.raw_text,
        "source_unit_content_text": unit.content_text,
        "source_unit_raw_checksum": unit.raw_checksum,
        "removed_marginalia": list(unit.removed_marginalia),
        "ingestion_status": chunk.status.value,
        "flags": list(chunk.flags),
        "render_required": unit.render_required,
        "source_locator": chunk.locator.model_dump(mode="json"),
        "source_unit_metadata": _jsonable_mapping(unit.metadata),
    }


def _empty_unit_diagnostic(unit: SourceUnit) -> dict[str, object]:
    return {
        "source_unit_id": unit.id,
        "locator": unit.locator.model_dump(mode="json"),
        "section_path": list(unit.section_path),
        "raw_checksum": unit.raw_checksum,
        "status": unit.status.value,
        "flags": list(unit.flags),
        "render_required": unit.render_required,
        "bounding_boxes": _bounding_boxes(unit),
        "reason": "empty exact text cannot satisfy immutable DocumentChunk/Evidence constraints",
    }


def _validate_chunk_identity(existing: DocumentChunk, chunk: SourceChunk) -> None:
    expected_locator = _locator_fields(chunk)
    disagreements: list[str] = []
    if existing.content_sha256 != chunk.checksum or existing.content != chunk.exact_text:
        disagreements.append("content")
    for field_name in (
        "locator_type",
        "locator_start",
        "locator_end",
        "physical_page",
        "printed_page_label",
        "slide_number",
        "paragraph_start",
        "paragraph_end",
    ):
        if getattr(existing, field_name) != expected_locator[field_name]:
            disagreements.append(field_name)
    if disagreements:
        raise PersistenceInvariantError(
            f"stable chunk {existing.id} disagrees on {sorted(set(disagreements))}"
        )


def _validate_evidence_identity(existing: Evidence, chunk: SourceChunk) -> None:
    if (
        existing.evidence_snippet != chunk.evidence_snippet
        or existing.char_start != chunk.evidence_char_start
        or existing.char_end != chunk.evidence_char_end
        or existing.evidence_sha256 != sha256_text(chunk.evidence_snippet)
        or existing.chunk_content_sha256 != chunk.checksum
    ):
        raise PersistenceInvariantError(f"stable evidence {existing.id} changed provenance")


class CourseKnowledgePipeline:
    """Persist one verified source manifest into an injected async session."""

    def __init__(
        self,
        *,
        embedding_gateway: EmbeddingGateway,
        config: PipelineConfig | None = None,
    ) -> None:
        self._embedding_gateway = embedding_gateway
        self._config = config or PipelineConfig()

    async def _embedding_report(self) -> EmbeddingRunReport:
        try:
            probe = await self._embedding_gateway.probe()
        except Exception as error:  # the source pipeline remains usable without vectors
            return EmbeddingRunReport(
                available=False,
                provider=type(self._embedding_gateway).__name__,
                persisted_model_label=None,
                retrieval_mode="unavailable",
                dimensions=None,
                detail=type(error).__name__,
            )
        dimensions = probe.dimensions or self._embedding_gateway.dimensions
        if probe.available and dimensions != EMBEDDING_DIMENSION:
            raise PipelineError(
                f"embedding gateway dimension {dimensions} does not match schema "
                f"dimension {EMBEDDING_DIMENSION}"
            )
        if not probe.available:
            return EmbeddingRunReport(
                available=False,
                provider=probe.provider,
                persisted_model_label=None,
                retrieval_mode="unavailable",
                dimensions=probe.dimensions,
                detail=probe.detail,
            )
        is_hashing = probe.provider == "local_hashing"
        return EmbeddingRunReport(
            available=True,
            provider=probe.provider,
            persisted_model_label=(
                "local_hashing:lexical/degraded" if is_hashing else probe.provider
            ),
            retrieval_mode="lexical_degraded" if is_hashing else "semantic",
            dimensions=dimensions,
            detail=probe.detail,
        )

    async def _ensure_course(
        self,
        session: AsyncSession,
        manifest: CourseSourceManifest,
    ) -> Course:
        course_id = deterministic_uuid("course", manifest.course_key)
        course = await session.get(Course, course_id)
        manifest_metadata = _manifest_governance_metadata(manifest)
        if course is None:
            course = Course(
                id=course_id,
                code=manifest.course_key,
                title=manifest.course_title,
                institution="USTC",
                status=CourseStatus.DRAFT,
                settings_json={
                    "manifest_schema_version": manifest.schema_version,
                    "governance": manifest.governance.model_dump(mode="json"),
                    MANIFEST_SETTINGS_KEY: manifest_metadata,
                },
            )
            session.add(course)
        elif course.code != manifest.course_key:
            raise PersistenceInvariantError("deterministic course ID belongs to another course")
        else:
            settings = dict(course.settings_json)
            existing_metadata = settings.get(MANIFEST_SETTINGS_KEY)
            if existing_metadata is None:
                # Backfill only the importer-owned namespace.  Teacher-owned settings
                # and review/publication state are deliberately left untouched.
                course.settings_json = {
                    **settings,
                    MANIFEST_SETTINGS_KEY: manifest_metadata,
                }
            elif existing_metadata != manifest_metadata:
                raise PersistenceInvariantError(
                    "source-manifest governance metadata changed; explicit teacher review "
                    "is required before replacing alignment hints"
                )
        return course

    async def _ensure_editions(
        self,
        session: AsyncSession,
        *,
        course: Course,
        manifest: CourseSourceManifest,
    ) -> dict[str, CurriculumEdition]:
        editions: dict[str, CurriculumEdition] = {}
        for authored in manifest.curriculum_editions:
            edition_id = deterministic_uuid("curriculum-edition", course.id, authored.key)
            edition = await session.get(CurriculumEdition, edition_id)
            outline = {
                "manifest_chapter_count": authored.chapter_count,
                "canonical": authored.canonical,
                "manifest_key": authored.key,
                "status": "awaiting_structural_review",
            }
            if edition is None:
                edition = CurriculumEdition(
                    id=edition_id,
                    course_id=course.id,
                    edition_key=authored.key,
                    title=authored.title,
                    academic_year="2022" if authored.key == "lecture-decks-2022" else None,
                    ontology_version=self._config.ontology_version,
                    status=CurriculumEditionStatus.DRAFT,
                    outline_json=outline,
                )
                session.add(edition)
            elif edition.course_id != course.id or edition.edition_key != authored.key:
                raise PersistenceInvariantError(
                    f"deterministic curriculum ID collision for {authored.key!r}"
                )
            editions[authored.key] = edition
        await session.flush()
        return editions

    async def _ensure_document_and_version(
        self,
        session: AsyncSession,
        *,
        course: Course,
        edition: CurriculumEdition | None,
        source: ManifestSource,
        parsed: IngestedDocument,
        embedding: EmbeddingRunReport,
    ) -> tuple[SourceDocument, SourceDocumentVersion]:
        document_id = deterministic_uuid("source-document", course.id, source.path)
        document = await session.get(SourceDocument, document_id)
        relative_source_path = str(Path("knowledge") / source.path)
        if document is None:
            document = SourceDocument(
                id=document_id,
                course_id=course.id,
                curriculum_edition_id=edition.id if edition is not None else None,
                logical_key=source.path,
                title=Path(source.path).stem,
                source_filename=Path(source.path).name,
                source_path=relative_source_path,
                media_type=parsed.media_type,
                document_type=_document_type(source),
                authority=_AUTHORITY_MAP[source.authority],
                source_role=_source_role(source),
                authority_priority=source.priority,
                status=DocumentStatus.REVIEW_REQUIRED,
                bibliographic_json={
                    "manifest_kind": source.kind,
                    "manifest_locator": source.locator,
                    "claim_scope": source.claim_scope,
                    "requires_ocr": source.requires_ocr,
                },
            )
            session.add(document)
            await session.flush()
        elif (
            document.course_id != course.id
            or document.logical_key != source.path
            or document.curriculum_edition_id != (edition.id if edition is not None else None)
        ):
            raise PersistenceInvariantError(
                f"source document identity/scope changed for {source.path!r}"
            )

        version_id = deterministic_uuid(
            "source-document-version", document.id, parsed.sha256, parsed.parser_name
        )
        version = await session.get(SourceDocumentVersion, version_id)
        nonempty_unit_ids = {chunk.source_unit_id for chunk in parsed.chunks if chunk.exact_text}
        empty_units = [unit for unit in parsed.units if unit.id not in nonempty_unit_ids]
        diagnostics = {
            "ingestion_document_id": parsed.document_id,
            "ingestion_document_version_id": parsed.document_version_id,
            "unit_count": len(parsed.units),
            "chunk_count": len(parsed.chunks),
            "status_counts": dict(Counter(unit.status.value for unit in parsed.units)),
            "empty_source_units": [_empty_unit_diagnostic(unit) for unit in empty_units],
        }
        ingestion_contract = _ingestion_contract(parsed, self._config.ingestion)
        source_metadata = {
            "manifest": source.model_dump(mode="json"),
            "parser_metadata": _jsonable_mapping(parsed.metadata),
            "ingestion_contract": ingestion_contract,
            "embedding": embedding.model_dump(mode="json"),
        }
        if version is None:
            maximum_version = await session.scalar(
                select(func.max(SourceDocumentVersion.version_number)).where(
                    SourceDocumentVersion.document_id == document.id
                )
            )
            version = SourceDocumentVersion(
                id=version_id,
                document_id=document.id,
                version_number=int(maximum_version or 0) + 1,
                source_file_sha256=parsed.sha256,
                byte_size=parsed.byte_size,
                immutable_source_path=relative_source_path,
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
                status=DocumentVersionStatus.REVIEW_REQUIRED,
                parse_diagnostics_json=diagnostics,
                source_metadata_json=source_metadata,
            )
            session.add(version)
            await session.flush()
        elif (
            version.document_id != document.id
            or version.source_file_sha256 != parsed.sha256
            or version.byte_size != parsed.byte_size
            or version.immutable_source_path != relative_source_path
        ):
            raise PersistenceInvariantError(f"immutable source version changed for {source.path!r}")
        else:
            persisted_contract = version.source_metadata_json.get("ingestion_contract")
            if (
                version.parser_name != parsed.parser_name
                or version.parser_version != parsed.parser_version
                or persisted_contract != ingestion_contract
            ):
                raise PersistenceInvariantError(
                    f"immutable source version {version.id} was produced by a different "
                    "parser/chunk configuration; use an explicit versioned reprocessing "
                    "workflow instead of overwriting its chunks"
                )
        return document, version

    async def _embed(
        self,
        chunks: Sequence[SourceChunk],
        embedding: EmbeddingRunReport,
    ) -> dict[str, list[float]]:
        if not embedding.available:
            return {}
        vectors: dict[str, list[float]] = {}
        batch_size = self._config.embedding_batch_size
        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            returned = await self._embedding_gateway.embed([chunk.exact_text for chunk in batch])
            if len(returned) != len(batch):
                raise PipelineError("embedding gateway returned the wrong batch length")
            for chunk, vector in zip(batch, returned, strict=True):
                if len(vector) != EMBEDDING_DIMENSION:
                    raise PipelineError("embedding gateway returned an invalid vector dimension")
                vectors[chunk.id] = vector
        return vectors

    async def _persist_chunks_and_evidence(
        self,
        session: AsyncSession,
        *,
        source: ManifestSource,
        parsed: IngestedDocument,
        version: SourceDocumentVersion,
        embedding: EmbeddingRunReport,
    ) -> tuple[
        dict[str, UUID],
        dict[str, UUID],
        int,
        int,
        int,
    ]:
        units_by_id = {unit.id: unit for unit in parsed.units}
        nonempty_chunks = [chunk for chunk in parsed.chunks if chunk.exact_text]
        parsed_chunks_by_id = {chunk.id: chunk for chunk in nonempty_chunks}
        omitted_empty = len(parsed.chunks) - len(nonempty_chunks)
        chunk_ids = {
            chunk.id: deterministic_uuid("document-chunk", version.id, chunk.id)
            for chunk in nonempty_chunks
        }
        existing_chunks = {
            row.id: row
            for row in (
                await session.scalars(
                    select(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
                )
            ).all()
        }
        parsed_id_by_database_id = {
            database_id: parsed_id for parsed_id, database_id in chunk_ids.items()
        }
        for database_id, existing in existing_chunks.items():
            parsed_id = parsed_id_by_database_id.get(database_id)
            if parsed_id is None:
                raise PersistenceInvariantError(
                    f"document version {version.id} contains an unknown persisted chunk"
                )
            parsed_chunk = parsed_chunks_by_id[parsed_id]
            _validate_chunk_identity(existing, parsed_chunk)

        chunks_requiring_vectors = [
            chunk
            for chunk in nonempty_chunks
            if chunk_ids[chunk.id] not in existing_chunks
            or existing_chunks[chunk_ids[chunk.id]].embedding is None
        ]
        vectors = await self._embed(chunks_requiring_vectors, embedding)
        added_chunks = 0
        for chunk in nonempty_chunks:
            database_id = chunk_ids[chunk.id]
            existing_chunk = existing_chunks.get(database_id)
            vector = vectors.get(chunk.id)
            if existing_chunk is not None:
                if vector is not None and existing_chunk.embedding is None:
                    existing_chunk.embedding = vector
                    existing_chunk.embedding_dimension = EMBEDDING_DIMENSION
                    existing_chunk.embedding_model = embedding.persisted_model_label
                continue
            unit = units_by_id[chunk.source_unit_id]
            locator_fields = _locator_fields(chunk)
            session.add(
                DocumentChunk(
                    id=database_id,
                    document_version_id=version.id,
                    extraction_run_id=None,
                    ordinal=chunk.ordinal,
                    locator_type=locator_fields["locator_type"],
                    locator_start=locator_fields["locator_start"],
                    locator_end=locator_fields["locator_end"],
                    physical_page=locator_fields["physical_page"],
                    printed_page_label=locator_fields["printed_page_label"],
                    slide_number=locator_fields["slide_number"],
                    paragraph_start=locator_fields["paragraph_start"],
                    paragraph_end=locator_fields["paragraph_end"],
                    section_path=list(chunk.section_path),
                    bounding_boxes_json=_bounding_boxes(unit),
                    content=chunk.exact_text,
                    normalized_content=None,
                    evidence_snippet=chunk.evidence_snippet or None,
                    content_sha256=chunk.checksum,
                    search_text=chunk.exact_text,
                    embedding=vector,
                    embedding_dimension=EMBEDDING_DIMENSION if vector is not None else None,
                    embedding_model=(
                        embedding.persisted_model_label if vector is not None else None
                    ),
                    extraction_quality=_chunk_quality(chunk.status),
                    extraction_status=_chunk_status(chunk.status),
                    parser_metadata_json=_chunk_parser_metadata(chunk, unit),
                )
            )
            added_chunks += 1
        await session.flush()

        existing_evidence = {
            row.id: row
            for row in (
                await session.scalars(
                    select(Evidence)
                    .join(DocumentChunk, Evidence.source_chunk_id == DocumentChunk.id)
                    .where(DocumentChunk.document_version_id == version.id)
                )
            ).all()
        }
        evidence_ids: dict[str, UUID] = {}
        added_evidence = 0
        for chunk in nonempty_chunks:
            if not chunk.evidence_snippet:
                continue
            chunk_id = chunk_ids[chunk.id]
            evidence_id = deterministic_uuid(
                "evidence",
                chunk_id,
                chunk.evidence_char_start,
                chunk.evidence_char_end,
                sha256_text(chunk.evidence_snippet),
            )
            evidence_ids[chunk.id] = evidence_id
            existing_evidence_row = existing_evidence.get(evidence_id)
            if existing_evidence_row is not None:
                _validate_evidence_identity(existing_evidence_row, chunk)
                continue
            evidence_status = (
                EvidenceStatus.GROUNDED
                if chunk.status == IngestionStatus.READY
                else EvidenceStatus.REVIEW_REQUIRED
            )
            session.add(
                Evidence(
                    id=evidence_id,
                    source_chunk_id=chunk_id,
                    evidence_type=EvidenceType.TEXT,
                    evidence_snippet=chunk.evidence_snippet,
                    char_start=chunk.evidence_char_start,
                    char_end=chunk.evidence_char_end,
                    evidence_sha256=sha256_text(chunk.evidence_snippet),
                    chunk_content_sha256=chunk.checksum,
                    status=evidence_status,
                    locator_json={
                        "source_path": source.path,
                        "source_file_sha256": parsed.sha256,
                        "section_path": list(chunk.section_path),
                        "locator": chunk.locator.model_dump(mode="json"),
                        "content_char_start": chunk.content_char_start,
                        "content_char_end": chunk.content_char_end,
                        "evidence_char_start": chunk.evidence_char_start,
                        "evidence_char_end": chunk.evidence_char_end,
                        "evidence_snippet_basis": chunk.evidence_snippet_basis,
                    },
                )
            )
            added_evidence += 1
        await session.flush()
        return chunk_ids, evidence_ids, added_chunks, added_evidence, omitted_empty

    async def ingest_manifest(
        self,
        session: AsyncSession,
        *,
        manifest_path: Path,
        repository_root: Path,
    ) -> KnowledgePipelineReport:
        """Verify, parse, and persist all sources without committing the session."""

        manifest = load_manifest(manifest_path)
        verifications = verify_sources(manifest, repository_root=repository_root)
        failures = [
            verification
            for verification in verifications
            if not verification.exists or not verification.checksum_matches
        ]
        if failures:
            details = ", ".join(
                f"{item.source.path}:{'missing' if not item.exists else 'sha256_mismatch'}"
                for item in failures
            )
            raise SourceIntegrityError(
                f"manifest verification failed before persistence: {details}"
            )

        embedding = await self._embedding_report()
        await _acquire_course_import_lock(session, manifest.course_key)
        course = await self._ensure_course(session, manifest)
        await session.flush()
        editions = await self._ensure_editions(
            session,
            course=course,
            manifest=manifest,
        )

        contexts: dict[str, StructuralSourceContext] = {}
        source_reports: list[SourcePersistenceReport] = []
        for verification in verifications:
            source = verification.source
            parsed = parse_document(
                verification.resolved_path,
                config=self._config.ingestion,
                source_name=source.path,
            )
            if parsed.sha256 != source.sha256:
                raise SourceIntegrityError(
                    f"source changed between verification and parse: {source.path}"
                )
            edition = editions.get(source.curriculum_edition or "")
            document, version = await self._ensure_document_and_version(
                session,
                course=course,
                edition=edition,
                source=source,
                parsed=parsed,
                embedding=embedding,
            )
            (
                chunk_ids,
                evidence_ids,
                _added_chunks,
                _added_evidence,
                omitted_empty,
            ) = await self._persist_chunks_and_evidence(
                session,
                source=source,
                parsed=parsed,
                version=version,
                embedding=embedding,
            )
            contexts[source.path] = StructuralSourceContext(
                source=source,
                resolved_path=verification.resolved_path,
                document_id=document.id,
                document_version_id=version.id,
                parsed=parsed,
                chunk_ids_by_ingestion_id=chunk_ids,
                evidence_ids_by_ingestion_chunk_id=evidence_ids,
            )
            persisted_evidence = len(evidence_ids)
            source_reports.append(
                SourcePersistenceReport(
                    source_path=source.path,
                    sha256=parsed.sha256,
                    document_id=document.id,
                    document_version_id=version.id,
                    parsed_units=len(parsed.units),
                    parsed_chunks=len(parsed.chunks),
                    persisted_chunks=len(chunk_ids),
                    persisted_evidence=persisted_evidence,
                    omitted_empty_units=omitted_empty,
                    statuses=dict(Counter(unit.status.value for unit in parsed.units)),
                )
            )

        structural = await import_authored_structures(
            session,
            course_id=course.id,
            editions={key: edition.id for key, edition in editions.items()},
            contexts=contexts,
            ingestion_config=self._config.ingestion,
            ontology_version=self._config.ontology_version,
        )
        await session.flush()

        document_count = int(
            await session.scalar(
                select(func.count())
                .select_from(SourceDocument)
                .where(SourceDocument.course_id == course.id)
            )
            or 0
        )
        version_count = int(
            await session.scalar(
                select(func.count())
                .select_from(SourceDocumentVersion)
                .join(SourceDocument)
                .where(SourceDocument.course_id == course.id)
            )
            or 0
        )
        chunk_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .join(SourceDocumentVersion)
                .join(SourceDocument)
                .where(SourceDocument.course_id == course.id)
            )
            or 0
        )
        evidence_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Evidence)
                .join(DocumentChunk)
                .join(SourceDocumentVersion)
                .join(SourceDocument)
                .where(SourceDocument.course_id == course.id)
            )
            or 0
        )
        node_candidate_count = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphNodeCandidate)
                .where(GraphNodeCandidate.course_id == course.id)
            )
            or 0
        )
        relation_candidate_count = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphRelationCandidate)
                .where(GraphRelationCandidate.course_id == course.id)
            )
            or 0
        )
        student_visible_chunk_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .join(SourceDocumentVersion)
                .join(SourceDocument)
                .join(
                    DocumentPublication,
                    (DocumentPublication.document_version_id == SourceDocumentVersion.id)
                    & (DocumentPublication.course_id == SourceDocument.course_id)
                    & or_(
                        SourceDocument.curriculum_edition_id.is_(None),
                        SourceDocument.curriculum_edition_id
                        == DocumentPublication.curriculum_edition_id,
                    ),
                )
                .where(
                    SourceDocument.course_id == course.id,
                    SourceDocument.status == DocumentStatus.PUBLISHED,
                    SourceDocumentVersion.status == DocumentVersionStatus.PUBLISHED,
                    DocumentPublication.status == PublicationStatus.PUBLISHED,
                    DocumentChunk.extraction_status == ChunkExtractionStatus.APPROVED,
                )
            )
            or 0
        )
        return KnowledgePipelineReport(
            course_id=course.id,
            curriculum_edition_ids={key: edition.id for key, edition in editions.items()},
            source_reports=tuple(source_reports),
            embedding=embedding,
            structural=structural,
            document_count=document_count,
            version_count=version_count,
            chunk_count=chunk_count,
            evidence_count=evidence_count,
            node_candidate_count=node_candidate_count,
            relation_candidate_count=relation_candidate_count,
            student_visible_chunk_count=student_visible_chunk_count,
        )

    async def reprocess_scanned_source(
        self,
        session: AsyncSession,
        *,
        manifest_path: Path,
        repository_root: Path,
        source_path: str,
        transcribe: Any,
        render_dpi: int = 120,
    ) -> SourcePersistenceReport:
        """OCR one scanned source and persist chunks/evidence as a new version.

        ``transcribe`` is the async vision-callable.  This produces a distinct
        version (``parser_name=vision-ocr-v1``) rather than mutating the
        pymupdf version that holds zero extractable chunks for a scanned PDF.
        It never commits; the caller owns the transaction.
        """

        manifest = load_manifest(manifest_path)
        matching = [source for source in manifest.sources if source.path == source_path]
        if len(matching) != 1:
            raise SourceIntegrityError(
                f"manifest must contain exactly one source for {source_path!r}; "
                f"found {len(matching)}"
            )
        source = matching[0]
        verifications = verify_sources(manifest, repository_root=repository_root)
        verification = next(
            (item for item in verifications if item.source.path == source_path),
            None,
        )
        if verification is None:
            raise SourceIntegrityError(f"could not verify source {source_path!r}")
        if not verification.exists or not verification.checksum_matches:
            raise SourceIntegrityError(f"scanned source failed verification: {source_path!r}")

        embedding = await self._embedding_report()
        await _acquire_course_import_lock(session, manifest.course_key)
        course = await self._ensure_course(session, manifest)
        editions = await self._ensure_editions(session, course=course, manifest=manifest)
        edition = editions.get(source.curriculum_edition or "")

        parsed = await parse_scanned_pdf_document(
            verification.resolved_path,
            config=self._config.ingestion,
            source_name=source.path,
            transcribe=transcribe,
            render_dpi=render_dpi,
        )
        if parsed.sha256 != source.sha256:
            raise SourceIntegrityError("scanned source changed between verification and OCR")

        document, version = await self._ensure_document_and_version(
            session,
            course=course,
            edition=edition,
            source=source,
            parsed=parsed,
            embedding=embedding,
        )
        (
            chunk_ids,
            evidence_ids,
            _added_chunks,
            _added_evidence,
            omitted_empty,
        ) = await self._persist_chunks_and_evidence(
            session,
            source=source,
            parsed=parsed,
            version=version,
            embedding=embedding,
        )
        await session.flush()
        return SourcePersistenceReport(
            source_path=source.path,
            sha256=parsed.sha256,
            document_id=document.id,
            document_version_id=version.id,
            parsed_units=len(parsed.units),
            parsed_chunks=len(parsed.chunks),
            persisted_chunks=len(chunk_ids),
            persisted_evidence=len(evidence_ids),
            omitted_empty_units=omitted_empty,
            statuses=dict(Counter(unit.status.value for unit in parsed.units)),
        )


async def ingest_course_manifest(
    session: AsyncSession,
    *,
    manifest_path: Path,
    repository_root: Path,
    embedding_gateway: EmbeddingGateway,
    config: PipelineConfig | None = None,
) -> KnowledgePipelineReport:
    """Functional entry point for CLI jobs, tests, and FastAPI workers."""

    return await CourseKnowledgePipeline(
        embedding_gateway=embedding_gateway,
        config=config,
    ).ingest_manifest(
        session,
        manifest_path=manifest_path,
        repository_root=repository_root,
    )


__all__ = [
    "CourseKnowledgePipeline",
    "EmbeddingRunReport",
    "KnowledgePipelineReport",
    "PersistenceInvariantError",
    "PipelineConfig",
    "PipelineError",
    "SourceIntegrityError",
    "SourcePersistenceReport",
    "course_advisory_lock_key",
    "deterministic_uuid",
    "ingest_course_manifest",
]
