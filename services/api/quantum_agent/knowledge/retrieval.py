"""Course-scoped, approval-gated hybrid retrieval for student evidence.

PostgreSQL's ``student_visible_chunks`` view is the mandatory visibility gate
for every channel.  Neo4j may propose approved concept/subgraph identifiers,
but graph text is never returned as evidence: every graph source-chunk pointer
must resolve through the view and a grounded relational ``Evidence`` row.

The three channels deliberately keep their provider scores incomparable and
are fused by deterministic reciprocal-rank fusion.  Channel failures degrade
explicitly; a failure to hydrate authoritative relational evidence fails
closed and returns no citations.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from uuid import UUID

import jieba  # type: ignore[import-untyped]
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Uuid,
    and_,
    bindparam,
    case,
    column,
    exists,
    func,
    literal,
    or_,
    select,
    table,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.sql import Select

from quantum_agent.db_models import (
    EMBEDDING_DIMENSION,
    DocumentVersionStatus,
    Evidence,
    EvidenceStatus,
    SourceDocumentVersion,
)
from quantum_agent.knowledge.evidence_packets import (
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidencePacket,
    GraphContextEdge,
    GraphContextNode,
    LocatorType,
    RetrievalChannel,
    RetrievalContribution,
    RetrievalCoverage,
)
from quantum_agent.knowledge.fusion import RankedChunk, reciprocal_rank_fusion
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    ApprovedGraphRelationship,
    GraphScope,
    GraphStore,
)
from quantum_agent.knowledge.ontology import NodeType
from quantum_agent.llm.embeddings import EmbeddingGateway

jieba.setLogLevel(logging.WARNING)

STUDENT_VISIBLE_CHUNKS: Final = table(
    "student_visible_chunks",
    column("id", Uuid(as_uuid=True)),
    column("document_version_id", Uuid(as_uuid=True)),
    column("ordinal", Integer()),
    column("locator_type", String()),
    column("locator_start", String()),
    column("locator_end", String()),
    column("physical_page", Integer()),
    column("printed_page_label", String()),
    column("slide_number", Integer()),
    column("paragraph_start", Integer()),
    column("paragraph_end", Integer()),
    column("section_path", JSON()),
    column("content", Text()),
    column("evidence_snippet", Text()),
    column("content_sha256", String(64)),
    column("search_text", Text()),
    column("search_vector", TSVECTOR()),
    column("embedding", Vector(EMBEDDING_DIMENSION)),
    column("embedding_dimension", Integer()),
    column("embedding_model", String()),
    column("extraction_status", String()),
    column("course_id", Uuid(as_uuid=True)),
    column("publication_curriculum_edition_id", Uuid(as_uuid=True)),
    column("source_document_id", Uuid(as_uuid=True)),
    column("source_document_title", String()),
    column("source_filename", String()),
    column("source_role", String()),
    column("authority_priority", Integer()),
    column("publication_priority", Integer()),
    column("published_at", DateTime(timezone=True)),
)

GRAPH_SEARCH_NODE_TYPES: Final[tuple[NodeType, ...]] = (
    NodeType.CONCEPT,
    NodeType.PRINCIPLE,
    NodeType.MATHEMATICAL_OBJECT,
    NodeType.OPERATOR,
    NodeType.QUANTUM_STATE,
    NodeType.APPROXIMATION,
    NodeType.FORMULA,
    NodeType.DERIVATION,
)
CHANNEL_ORDER: Final[tuple[RetrievalChannel, ...]] = (
    RetrievalChannel.FULL_TEXT,
    RetrievalChannel.SEMANTIC,
    RetrievalChannel.GRAPH,
)


class RetrievalError(RuntimeError):
    """Base error for the hybrid retrieval boundary."""


class RetrievalChannelUnavailable(RetrievalError):
    """A retrieval channel cannot run in the configured environment."""


class RetrievalIntegrityError(RetrievalError):
    """Authoritative relational provenance is inconsistent or malformed."""


class RetrievalScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID

    def graph_scope(self) -> GraphScope:
        return GraphScope(
            course_id=str(self.course_id),
            curriculum_edition_id=str(self.curriculum_edition_id),
        )


class HybridRetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel_limit: int = Field(default=20, ge=1, le=100)
    max_evidence: int = Field(default=6, ge=1, le=6)
    graph_root_limit: int = Field(default=3, ge=1, le=10)
    graph_depth: int = Field(default=1, ge=1, le=3)
    sufficient_evidence_count: int = Field(default=2, ge=1, le=6)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    max_lexical_terms: int = Field(default=8, ge=1, le=16)


class AuthoritativeEvidenceRecord(BaseModel):
    """One grounded Evidence row joined to one student-visible source chunk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    evidence_id: UUID
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_title: str = Field(min_length=1)
    document_version: int = Field(ge=1)
    source_file_name: str = Field(min_length=1)
    source_file_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_chunk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chapter: str | None = None
    section_path: tuple[str, ...] = ()
    locator: EvidenceLocator
    source_chunk: str = Field(min_length=1)
    evidence_snippet: str = Field(min_length=1)
    evidence_char_start: int = Field(ge=0)
    evidence_char_end: int = Field(gt=0)
    kind: EvidenceKind = EvidenceKind.COURSE_MATERIAL
    authority_priority: int = Field(ge=0, le=100)
    publication_priority: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def verify_authoritative_hashes_and_span(self) -> AuthoritativeEvidenceRecord:
        if self.evidence_char_end <= self.evidence_char_start:
            raise ValueError("evidence character range is empty")
        if self.evidence_char_end > len(self.source_chunk):
            raise ValueError("evidence character range exceeds source chunk")
        if (
            self.source_chunk[self.evidence_char_start : self.evidence_char_end]
            != self.evidence_snippet
        ):
            raise ValueError("evidence span is not an exact source-chunk slice")
        chunk_hash = hashlib.sha256(self.source_chunk.encode("utf-8")).hexdigest()
        evidence_hash = hashlib.sha256(self.evidence_snippet.encode("utf-8")).hexdigest()
        if chunk_hash != self.source_chunk_sha256:
            raise ValueError("source chunk hash does not match source text")
        if evidence_hash != self.evidence_sha256:
            raise ValueError("evidence hash does not match evidence snippet")
        return self

    def to_evidence_item(self, contributions: Sequence[RetrievalContribution]) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=self.evidence_id,
            chunk_id=self.chunk_id,
            document_id=self.document_id,
            document_version_id=self.document_version_id,
            document_title=self.document_title,
            document_version=self.document_version,
            source_file_name=self.source_file_name,
            source_file_sha256=self.source_file_sha256,
            source_chunk_sha256=self.source_chunk_sha256,
            evidence_sha256=self.evidence_sha256,
            curriculum_edition_id=self.curriculum_edition_id,
            chapter=self.chapter,
            section_path=list(self.section_path),
            locator=self.locator,
            source_chunk=self.source_chunk,
            evidence_snippet=self.evidence_snippet,
            kind=self.kind,
            authority_priority=self.authority_priority,
            contributions=list(contributions),
        )


def _grounded_evidence_exists() -> Any:
    evidence_table = Evidence.__table__
    return exists(
        select(literal(1))
        .where(
            evidence_table.c.source_chunk_id == STUDENT_VISIBLE_CHUNKS.c.id,
            evidence_table.c.status == EvidenceStatus.GROUNDED,
            evidence_table.c.chunk_content_sha256 == STUDENT_VISIBLE_CHUNKS.c.content_sha256,
        )
        .correlate(STUDENT_VISIBLE_CHUNKS)
    )


def _visibility_predicates() -> tuple[Any, ...]:
    return (
        STUDENT_VISIBLE_CHUNKS.c.course_id == bindparam("course_id", type_=Uuid()),
        STUDENT_VISIBLE_CHUNKS.c.publication_curriculum_edition_id
        == bindparam("curriculum_edition_id", type_=Uuid()),
        STUDENT_VISIBLE_CHUNKS.c.extraction_status == bindparam("approved_status", type_=String()),
        STUDENT_VISIBLE_CHUNKS.c.published_at.is_not(None),
        _grounded_evidence_exists(),
    )


def build_postgres_full_text_statement(term_count: int) -> Select[Any]:
    """Build parameterized PostgreSQL FTS plus CJK-safe ILIKE fallback."""

    if not 1 <= term_count <= 16:
        raise ValueError("term_count must be between 1 and 16")
    fts_query_param = bindparam("fts_query", type_=Text())
    ts_query = func.plainto_tsquery("simple", fts_query_param)
    vector_match = STUDENT_VISIBLE_CHUNKS.c.search_vector.op("@@")(ts_query)
    fallback_matches = [
        STUDENT_VISIBLE_CHUNKS.c.search_text.ilike(
            bindparam(f"term_{index}", type_=Text()), escape="!"
        )
        for index in range(term_count)
    ]
    fallback_match = or_(*fallback_matches)
    score = (
        func.coalesce(func.ts_rank_cd(STUDENT_VISIBLE_CHUNKS.c.search_vector, ts_query), 0.0)
        + case((fallback_match, 0.05), else_=0.0)
    ).label("raw_score")
    return (
        select(STUDENT_VISIBLE_CHUNKS.c.id.label("chunk_id"), score)
        .where(*_visibility_predicates(), or_(vector_match, fallback_match))
        .order_by(score.desc(), STUDENT_VISIBLE_CHUNKS.c.id.asc())
        .limit(bindparam("limit", type_=Integer()))
    )


def build_sqlite_lexical_statement(term_count: int) -> Select[Any]:
    """Portable lexical fallback used only in deterministic/local environments."""

    if not 1 <= term_count <= 16:
        raise ValueError("term_count must be between 1 and 16")
    matches = [
        func.lower(STUDENT_VISIBLE_CHUNKS.c.search_text).like(
            func.lower(bindparam(f"term_{index}", type_=Text())), escape="!"
        )
        for index in range(term_count)
    ]
    return (
        select(
            STUDENT_VISIBLE_CHUNKS.c.id.label("chunk_id"),
            literal(1.0, type_=Float()).label("raw_score"),
        )
        .where(*_visibility_predicates(), or_(*matches))
        .order_by(
            STUDENT_VISIBLE_CHUNKS.c.publication_priority.desc(),
            STUDENT_VISIBLE_CHUNKS.c.authority_priority.desc(),
            STUDENT_VISIBLE_CHUNKS.c.id.asc(),
        )
        .limit(bindparam("limit", type_=Integer()))
    )


def build_postgres_semantic_statement() -> Select[Any]:
    """Build a 384-dimensional pgvector cosine-distance query."""

    query_embedding = bindparam("query_embedding", type_=Vector(EMBEDDING_DIMENSION))
    distance = STUDENT_VISIBLE_CHUNKS.c.embedding.cosine_distance(query_embedding)
    similarity = (literal(1.0) - distance).label("raw_score")
    return (
        select(STUDENT_VISIBLE_CHUNKS.c.id.label("chunk_id"), similarity)
        .where(
            *_visibility_predicates(),
            STUDENT_VISIBLE_CHUNKS.c.embedding.is_not(None),
            STUDENT_VISIBLE_CHUNKS.c.embedding_dimension == EMBEDDING_DIMENSION,
            STUDENT_VISIBLE_CHUNKS.c.embedding_model
            == bindparam("embedding_model", type_=String()),
        )
        .order_by(distance.asc(), STUDENT_VISIBLE_CHUNKS.c.id.asc())
        .limit(bindparam("limit", type_=Integer()))
    )


def build_hydration_statement() -> Select[Any]:
    """Join visible chunks to immutable versions and grounded exact evidence."""

    version = SourceDocumentVersion.__table__
    evidence = Evidence.__table__
    source = STUDENT_VISIBLE_CHUNKS.join(
        version,
        and_(
            version.c.id == STUDENT_VISIBLE_CHUNKS.c.document_version_id,
            version.c.status == DocumentVersionStatus.PUBLISHED,
        ),
    ).join(
        evidence,
        and_(
            evidence.c.source_chunk_id == STUDENT_VISIBLE_CHUNKS.c.id,
            evidence.c.status == EvidenceStatus.GROUNDED,
            evidence.c.chunk_content_sha256 == STUDENT_VISIBLE_CHUNKS.c.content_sha256,
        ),
    )
    return (
        select(
            STUDENT_VISIBLE_CHUNKS.c.course_id,
            STUDENT_VISIBLE_CHUNKS.c.publication_curriculum_edition_id.label(
                "curriculum_edition_id"
            ),
            evidence.c.id.label("evidence_id"),
            STUDENT_VISIBLE_CHUNKS.c.id.label("chunk_id"),
            STUDENT_VISIBLE_CHUNKS.c.source_document_id.label("document_id"),
            STUDENT_VISIBLE_CHUNKS.c.document_version_id,
            STUDENT_VISIBLE_CHUNKS.c.source_document_title.label("document_title"),
            version.c.version_number.label("document_version"),
            STUDENT_VISIBLE_CHUNKS.c.source_filename.label("source_file_name"),
            version.c.source_file_sha256,
            STUDENT_VISIBLE_CHUNKS.c.content_sha256.label("source_chunk_sha256"),
            evidence.c.evidence_sha256,
            STUDENT_VISIBLE_CHUNKS.c.section_path,
            STUDENT_VISIBLE_CHUNKS.c.locator_type,
            STUDENT_VISIBLE_CHUNKS.c.locator_start,
            STUDENT_VISIBLE_CHUNKS.c.locator_end,
            STUDENT_VISIBLE_CHUNKS.c.physical_page,
            STUDENT_VISIBLE_CHUNKS.c.printed_page_label,
            STUDENT_VISIBLE_CHUNKS.c.slide_number,
            STUDENT_VISIBLE_CHUNKS.c.paragraph_start,
            STUDENT_VISIBLE_CHUNKS.c.paragraph_end,
            STUDENT_VISIBLE_CHUNKS.c.content.label("source_chunk"),
            evidence.c.evidence_snippet,
            evidence.c.char_start.label("evidence_char_start"),
            evidence.c.char_end.label("evidence_char_end"),
            evidence.c.locator_json,
            STUDENT_VISIBLE_CHUNKS.c.source_role,
            STUDENT_VISIBLE_CHUNKS.c.authority_priority,
            STUDENT_VISIBLE_CHUNKS.c.publication_priority,
        )
        .select_from(source)
        .where(
            *_visibility_predicates(),
            STUDENT_VISIBLE_CHUNKS.c.id.in_(bindparam("chunk_ids", expanding=True, type_=Uuid())),
        )
        .order_by(
            STUDENT_VISIBLE_CHUNKS.c.id.asc(),
            evidence.c.char_start.asc(),
            evidence.c.id.asc(),
        )
    )


_QUERY_PUNCTUATION = re.compile(r"^\W+$", re.UNICODE)
_QUERY_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {"什么", "为何", "为什么", "如何", "怎么", "是否", "一个", "这个", "那个", "请问", "的", "是"}
)


def lexical_query_terms(query: str, *, limit: int = 8) -> tuple[str, ...]:
    """Generate deterministic CJK/search terms without altering source text."""

    normalized = " ".join(query.strip().split())
    if not normalized:
        raise ValueError("query must not be blank")
    terms: list[str] = []
    for token in jieba.lcut_for_search(normalized, HMM=False):
        value = token.strip().casefold()
        if (
            not value
            or value in _QUERY_STOP_WORDS
            or _QUERY_PUNCTUATION.fullmatch(value)
            or (len(value) == 1 and not value.isascii())
        ):
            continue
        if value not in terms:
            terms.append(value)
    if not terms:
        terms.append(normalized.casefold())
    return tuple(terms[:limit])


def _escape_like(term: str) -> str:
    return "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _as_uuid(value: object, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise RetrievalIntegrityError(f"{field_name} is not a UUID") from exc


def _as_positive_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _locator_from_row(row: Mapping[str, Any]) -> EvidenceLocator:
    raw_locator = row.get("locator_json")
    locator_json = raw_locator if isinstance(raw_locator, Mapping) else {}
    nested_locator = locator_json.get("locator")
    locator = nested_locator if isinstance(nested_locator, Mapping) else locator_json
    locator_type = _enum_value(row.get("locator_type"))
    start = locator.get("start", row.get("locator_start"))
    end = locator.get("end", row.get("locator_end"))
    if locator_type == "page":
        physical_page = _as_positive_int(
            row.get("physical_page") or locator.get("physical_page")
        )
        if physical_page is None:
            raise RetrievalIntegrityError("published page evidence has no physical page")
        return EvidenceLocator(
            locator_type=LocatorType.PDF_PAGE,
            physical_page=physical_page,
            printed_page_label=row.get("printed_page_label") or locator.get("page_label"),
        )
    if locator_type == "slide":
        slide_number = _as_positive_int(row.get("slide_number") or start)
        if slide_number is None:
            raise RetrievalIntegrityError("published slide evidence has no slide number")
        return EvidenceLocator(
            locator_type=LocatorType.SLIDE,
            slide_number=slide_number,
            physical_page=_as_positive_int(row.get("physical_page")),
        )
    if locator_type == "paragraph":
        paragraph_start = _as_positive_int(row.get("paragraph_start") or start)
        if paragraph_start is None:
            raise RetrievalIntegrityError("published paragraph evidence has no ordinal")
        return EvidenceLocator(
            locator_type=LocatorType.DOCX_PARAGRAPH,
            paragraph_start=paragraph_start,
            paragraph_end=_as_positive_int(row.get("paragraph_end") or end),
        )
    if locator_type == "sheet_row":
        sheet_name = locator.get("sheet_name")
        row_start = _as_positive_int(start)
        if not isinstance(sheet_name, str) or not sheet_name or row_start is None:
            raise RetrievalIntegrityError("published worksheet evidence has no exact row locator")
        return EvidenceLocator(
            locator_type=LocatorType.XLSX_ROW,
            sheet_name=sheet_name,
            row_start=row_start,
            row_end=_as_positive_int(end),
        )
    if locator_type == "line":
        line_start = _as_positive_int(start)
        if line_start is None:
            raise RetrievalIntegrityError("published text evidence has no line locator")
        return EvidenceLocator(
            locator_type=LocatorType.TEXT_LINES,
            line_start=line_start,
            line_end=_as_positive_int(end),
        )
    raise RetrievalIntegrityError("published evidence has an unsupported locator type")


def _record_from_row(row: Mapping[str, Any]) -> AuthoritativeEvidenceRecord:
    raw_section_path = row.get("section_path")
    section_path = (
        tuple(str(item) for item in raw_section_path)
        if isinstance(raw_section_path, (list, tuple))
        else ()
    )
    source_role = _enum_value(row.get("source_role"))
    kind = (
        EvidenceKind.TEACHER_CURATED
        if source_role == "knowledge_export"
        else EvidenceKind.COURSE_MATERIAL
    )
    return AuthoritativeEvidenceRecord(
        course_id=_as_uuid(row["course_id"], "course_id"),
        curriculum_edition_id=_as_uuid(row["curriculum_edition_id"], "curriculum_edition_id"),
        evidence_id=_as_uuid(row["evidence_id"], "evidence_id"),
        chunk_id=_as_uuid(row["chunk_id"], "chunk_id"),
        document_id=_as_uuid(row["document_id"], "document_id"),
        document_version_id=_as_uuid(row["document_version_id"], "document_version_id"),
        document_title=str(row["document_title"]),
        document_version=int(row["document_version"]),
        source_file_name=str(row["source_file_name"]),
        source_file_sha256=str(row["source_file_sha256"]),
        source_chunk_sha256=str(row["source_chunk_sha256"]),
        evidence_sha256=str(row["evidence_sha256"]),
        chapter=section_path[0] if section_path else None,
        section_path=section_path,
        locator=_locator_from_row(row),
        source_chunk=str(row["source_chunk"]),
        evidence_snippet=str(row["evidence_snippet"]),
        evidence_char_start=int(row["evidence_char_start"]),
        evidence_char_end=int(row["evidence_char_end"]),
        kind=kind,
        authority_priority=int(row["authority_priority"]),
        publication_priority=int(row["publication_priority"]),
    )


class EvidenceRepository(Protocol):
    async def full_text(
        self,
        scope: RetrievalScope,
        query: str,
        *,
        limit: int,
        max_terms: int = 8,
    ) -> list[RankedChunk]: ...

    async def semantic(
        self,
        scope: RetrievalScope,
        embedding: Sequence[float],
        *,
        embedding_model: str,
        limit: int,
    ) -> list[RankedChunk]: ...

    async def hydrate(
        self,
        scope: RetrievalScope,
        chunk_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]]: ...


class StudentVisibleEvidenceRepository:
    """SQLAlchemy repository whose only chunk source is the gated view."""

    def __init__(self, session_factory: Any, *, dialect_name: str | None = None) -> None:
        self._session_factory = session_factory
        self._dialect_name_override = dialect_name

    def _dialect_name(self, session: Any) -> str:
        if self._dialect_name_override:
            return self._dialect_name_override
        return str(session.get_bind().dialect.name)

    @staticmethod
    def _scope_parameters(scope: RetrievalScope, limit: int) -> dict[str, Any]:
        return {
            "course_id": scope.course_id,
            "curriculum_edition_id": scope.curriculum_edition_id,
            "approved_status": "approved",
            "limit": limit,
        }

    @staticmethod
    def _ranked_rows(rows: Sequence[Mapping[str, Any]]) -> list[RankedChunk]:
        ranked: list[RankedChunk] = []
        seen: set[UUID] = set()
        for row in rows:
            chunk_id = _as_uuid(row["chunk_id"], "chunk_id")
            if chunk_id in seen:
                continue
            score = float(row["raw_score"]) if row.get("raw_score") is not None else None
            if score is not None and not math.isfinite(score):
                raise RetrievalIntegrityError("retrieval score is not finite")
            seen.add(chunk_id)
            ranked.append(RankedChunk(chunk_id=chunk_id, raw_score=score))
        return ranked

    async def full_text(
        self,
        scope: RetrievalScope,
        query: str,
        *,
        limit: int,
        max_terms: int = 8,
    ) -> list[RankedChunk]:
        terms = lexical_query_terms(query, limit=max_terms)
        params = self._scope_parameters(scope, limit)
        params.update(
            {
                "fts_query": " ".join(terms),
                **{f"term_{index}": _escape_like(term) for index, term in enumerate(terms)},
            }
        )
        async with self._session_factory() as session:
            dialect = self._dialect_name(session)
            if dialect == "postgresql":
                statement = build_postgres_full_text_statement(len(terms))
            elif dialect == "sqlite":
                statement = build_sqlite_lexical_statement(len(terms))
            else:
                raise RetrievalChannelUnavailable(
                    f"full-text retrieval does not support dialect {dialect!r}"
                )
            result = await session.execute(statement, params)
            rows = result.mappings().all()
        return self._ranked_rows(rows)

    async def semantic(
        self,
        scope: RetrievalScope,
        embedding: Sequence[float],
        *,
        embedding_model: str,
        limit: int,
    ) -> list[RankedChunk]:
        if len(embedding) != EMBEDDING_DIMENSION or any(
            not math.isfinite(value) for value in embedding
        ):
            raise RetrievalIntegrityError("query embedding is not a finite 384-vector")
        async with self._session_factory() as session:
            if self._dialect_name(session) != "postgresql":
                raise RetrievalChannelUnavailable("pgvector semantic retrieval requires PostgreSQL")
            params = self._scope_parameters(scope, limit)
            params.update(
                {
                    "query_embedding": list(embedding),
                    "embedding_model": embedding_model,
                }
            )
            result = await session.execute(build_postgres_semantic_statement(), params)
            rows = result.mappings().all()
        return self._ranked_rows(rows)

    async def hydrate(
        self,
        scope: RetrievalScope,
        chunk_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]]:
        unique_ids = list(dict.fromkeys(chunk_ids))
        if not unique_ids:
            return {}
        params = self._scope_parameters(scope, len(unique_ids))
        params["chunk_ids"] = unique_ids
        async with self._session_factory() as session:
            result = await session.execute(build_hydration_statement(), params)
            rows = result.mappings().all()
        grouped: dict[UUID, list[AuthoritativeEvidenceRecord]] = {}
        for row in rows:
            record = _record_from_row(row)
            if record.course_id != scope.course_id or (
                record.curriculum_edition_id != scope.curriculum_edition_id
            ):
                raise RetrievalIntegrityError("hydrated evidence escaped retrieval scope")
            grouped.setdefault(record.chunk_id, []).append(record)
        return {
            chunk_id: tuple(
                sorted(
                    records,
                    key=lambda item: (
                        item.evidence_char_start,
                        item.evidence_char_end,
                        str(item.evidence_id),
                    ),
                )
            )
            for chunk_id, records in grouped.items()
        }


@dataclass(slots=True)
class _ChannelRun:
    channel: RetrievalChannel
    rankings: list[RankedChunk] = field(default_factory=list)
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _GraphRun(_ChannelRun):
    nodes: dict[UUID, ApprovedGraphNode] = field(default_factory=dict)
    relationships: dict[UUID, ApprovedGraphRelationship] = field(default_factory=dict)
    node_chunks: dict[UUID, set[UUID]] = field(default_factory=dict)
    relationship_chunks: dict[UUID, set[UUID]] = field(default_factory=dict)
    chunk_quotes: dict[UUID, set[str]] = field(default_factory=dict)


class HybridEvidenceRetriever:
    """Run, fuse, hydrate, and validate the three Phase-1 retrieval channels."""

    def __init__(
        self,
        *,
        repository: EvidenceRepository,
        embedding_gateway: EmbeddingGateway | None,
        graph_store: GraphStore | None,
        config: HybridRetrievalConfig | None = None,
    ) -> None:
        self._repository = repository
        self._embedding_gateway = embedding_gateway
        self._graph_store = graph_store
        self._config = config or HybridRetrievalConfig()

    async def _run_full_text(self, scope: RetrievalScope, query: str) -> _ChannelRun:
        try:
            rankings = await self._repository.full_text(
                scope,
                query,
                limit=self._config.channel_limit,
                max_terms=self._config.max_lexical_terms,
            )
            return _ChannelRun(channel=RetrievalChannel.FULL_TEXT, rankings=rankings)
        except Exception as exc:
            return _ChannelRun(
                channel=RetrievalChannel.FULL_TEXT,
                degraded=True,
                warnings=[f"postgres_full_text_unavailable:{type(exc).__name__}"],
            )

    async def _run_semantic(self, scope: RetrievalScope, query: str) -> _ChannelRun:
        if self._embedding_gateway is None:
            return _ChannelRun(
                channel=RetrievalChannel.SEMANTIC,
                degraded=True,
                warnings=["pgvector_semantic_unavailable:no_embedding_gateway"],
            )
        local_hashing_warning: list[str] = []
        try:
            probe = await self._embedding_gateway.probe()
            if not probe.available:
                return _ChannelRun(
                    channel=RetrievalChannel.SEMANTIC,
                    degraded=True,
                    warnings=["pgvector_semantic_unavailable:probe_failed"],
                )
            dimensions = probe.dimensions or self._embedding_gateway.dimensions
            if dimensions != EMBEDDING_DIMENSION:
                return _ChannelRun(
                    channel=RetrievalChannel.SEMANTIC,
                    degraded=True,
                    warnings=["pgvector_semantic_unavailable:dimension_mismatch"],
                )
            vectors = await self._embedding_gateway.embed([query])
            if len(vectors) != 1 or len(vectors[0]) != EMBEDDING_DIMENSION:
                raise RetrievalIntegrityError("embedding gateway returned an invalid batch")
            is_local_hashing = probe.provider == "local_hashing"
            if is_local_hashing:
                local_hashing_warning.append("pgvector_semantic_degraded:local_hashing_is_lexical")
            model_label = "local_hashing:lexical/degraded" if is_local_hashing else probe.provider
            rankings = await self._repository.semantic(
                scope,
                vectors[0],
                embedding_model=model_label,
                limit=self._config.channel_limit,
            )
            return _ChannelRun(
                channel=RetrievalChannel.SEMANTIC,
                rankings=rankings,
                degraded=is_local_hashing,
                warnings=local_hashing_warning,
            )
        except Exception as exc:
            return _ChannelRun(
                channel=RetrievalChannel.SEMANTIC,
                degraded=True,
                warnings=[
                    *local_hashing_warning,
                    f"pgvector_semantic_unavailable:{type(exc).__name__}",
                ],
            )

    @staticmethod
    def _graph_evidence_chunk_ids(
        evidence_items: Sequence[Any],
    ) -> tuple[dict[UUID, set[str]], bool]:
        chunk_quotes: dict[UUID, set[str]] = {}
        invalid = False
        for evidence in evidence_items:
            try:
                chunk_id = UUID(str(evidence.source_chunk_id))
                quote = "".join(str(evidence.quote).casefold().split())
                if not quote:
                    raise ValueError("empty graph evidence quote")
                chunk_quotes.setdefault(chunk_id, set()).add(quote)
            except (TypeError, ValueError):
                invalid = True
        return chunk_quotes, invalid

    @staticmethod
    def _graph_uuid(value: str) -> UUID | None:
        try:
            return UUID(value)
        except ValueError:
            return None

    def _collect_graph_node(
        self,
        run: _GraphRun,
        node: ApprovedGraphNode,
        scope: RetrievalScope,
    ) -> list[UUID]:
        if node.scope != scope.graph_scope() or node.status != "approved":
            run.degraded = True
            run.warnings.append("neo4j_graph_omitted:scope_or_approval_mismatch")
            return []
        node_id = self._graph_uuid(node.candidate_id)
        if node_id is None:
            run.degraded = True
            run.warnings.append("neo4j_graph_omitted:non_uuid_node_id")
            return []
        chunk_quotes, invalid = self._graph_evidence_chunk_ids(node.evidence)
        if invalid:
            run.degraded = True
            run.warnings.append("neo4j_graph_omitted:invalid_source_chunk_pointer")
        run.nodes.setdefault(node_id, node)
        chunk_ids = set(chunk_quotes)
        run.node_chunks.setdefault(node_id, set()).update(chunk_ids)
        for chunk_id, quotes in chunk_quotes.items():
            run.chunk_quotes.setdefault(chunk_id, set()).update(quotes)
        return sorted(chunk_ids, key=str)

    def _collect_graph_relationship(
        self,
        run: _GraphRun,
        relationship: ApprovedGraphRelationship,
        scope: RetrievalScope,
    ) -> list[UUID]:
        if relationship.scope != scope.graph_scope() or relationship.status != "approved":
            run.degraded = True
            run.warnings.append("neo4j_graph_omitted:scope_or_approval_mismatch")
            return []
        relationship_id = self._graph_uuid(relationship.candidate_id)
        if relationship_id is None:
            run.degraded = True
            run.warnings.append("neo4j_graph_omitted:non_uuid_relationship_id")
            return []
        chunk_quotes, invalid = self._graph_evidence_chunk_ids(relationship.evidence)
        if invalid:
            run.degraded = True
            run.warnings.append("neo4j_graph_omitted:invalid_source_chunk_pointer")
        run.relationships.setdefault(relationship_id, relationship)
        chunk_ids = set(chunk_quotes)
        run.relationship_chunks.setdefault(relationship_id, set()).update(chunk_ids)
        for chunk_id, quotes in chunk_quotes.items():
            run.chunk_quotes.setdefault(chunk_id, set()).update(quotes)
        return sorted(chunk_ids, key=str)

    async def _run_graph(self, scope: RetrievalScope, query: str) -> _GraphRun:
        run = _GraphRun(channel=RetrievalChannel.GRAPH)
        if self._graph_store is None:
            run.degraded = True
            run.warnings.append("neo4j_graph_unavailable:no_graph_store")
            return run
        try:
            hits = await self._graph_store.search_nodes(
                scope.graph_scope(),
                query,
                node_types=GRAPH_SEARCH_NODE_TYPES,
                limit=self._config.channel_limit,
            )
            ordered_chunks: list[RankedChunk] = []
            seen_chunks: set[UUID] = set()
            for hit in hits[: self._config.graph_root_limit]:
                for chunk_id in self._collect_graph_node(run, hit.node, scope):
                    if chunk_id not in seen_chunks:
                        seen_chunks.add(chunk_id)
                        ordered_chunks.append(RankedChunk(chunk_id=chunk_id, raw_score=hit.score))
                try:
                    subgraph = await self._graph_store.get_subgraph(
                        scope.graph_scope(),
                        hit.node.candidate_id,
                        max_depth=self._config.graph_depth,
                        limit=self._config.channel_limit,
                    )
                except Exception as exc:
                    run.degraded = True
                    run.warnings.append(f"neo4j_subgraph_unavailable:{type(exc).__name__}")
                    continue
                for graph_node in subgraph.nodes:
                    for chunk_id in self._collect_graph_node(run, graph_node, scope):
                        if chunk_id not in seen_chunks:
                            seen_chunks.add(chunk_id)
                            ordered_chunks.append(
                                RankedChunk(chunk_id=chunk_id, raw_score=hit.score)
                            )
                for relationship in subgraph.relationships:
                    for chunk_id in self._collect_graph_relationship(run, relationship, scope):
                        if chunk_id not in seen_chunks:
                            seen_chunks.add(chunk_id)
                            ordered_chunks.append(
                                RankedChunk(chunk_id=chunk_id, raw_score=hit.score)
                            )
            run.rankings = ordered_chunks[: self._config.channel_limit]
            run.warnings = sorted(set(run.warnings))
            return run
        except Exception as exc:
            return _GraphRun(
                channel=RetrievalChannel.GRAPH,
                degraded=True,
                warnings=[f"neo4j_graph_unavailable:{type(exc).__name__}"],
            )

    @staticmethod
    def _graph_context(
        graph_run: _GraphRun,
        visible_chunk_ids: set[UUID],
    ) -> tuple[list[GraphContextNode], list[GraphContextEdge], bool]:
        visible_nodes: dict[UUID, GraphContextNode] = {}
        omitted = False
        for node_id, node in graph_run.nodes.items():
            if not graph_run.node_chunks.get(node_id, set()) & visible_chunk_ids:
                omitted = True
                continue
            raw_aliases = node.properties.get("aliases", [])
            aliases = (
                [str(alias) for alias in raw_aliases if isinstance(alias, str)]
                if isinstance(raw_aliases, list)
                else []
            )
            visible_nodes[node_id] = GraphContextNode(
                id=node_id,
                node_type=node.node_type.value,
                name=node.label,
                aliases=aliases,
            )
        edges: list[GraphContextEdge] = []
        for relationship_id, relationship in graph_run.relationships.items():
            source_id = HybridEvidenceRetriever._graph_uuid(relationship.source_candidate_id)
            target_id = HybridEvidenceRetriever._graph_uuid(relationship.target_candidate_id)
            if (
                source_id is None
                or target_id is None
                or source_id not in visible_nodes
                or target_id not in visible_nodes
                or not (
                    graph_run.relationship_chunks.get(relationship_id, set()) & visible_chunk_ids
                )
            ):
                omitted = True
                continue
            edges.append(
                GraphContextEdge(
                    id=relationship_id,
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relationship.relationship_type.value,
                )
            )
        return (
            sorted(visible_nodes.values(), key=lambda item: str(item.id)),
            sorted(edges, key=lambda item: str(item.id)),
            omitted,
        )

    async def retrieve(self, scope: RetrievalScope, query: str) -> EvidencePacket:
        query = " ".join(query.strip().split())
        if not query:
            raise ValueError("query must not be blank")

        full_text_run, semantic_run, graph_run = await asyncio.gather(
            self._run_full_text(scope, query),
            self._run_semantic(scope, query),
            self._run_graph(scope, query),
        )
        channel_runs: tuple[_ChannelRun, ...] = (
            full_text_run,
            semantic_run,
            graph_run,
        )
        degraded = {run.channel for run in channel_runs if run.degraded}
        warnings = [warning for run in channel_runs for warning in run.warnings]
        candidate_ids = list(
            dict.fromkeys(hit.chunk_id for run in channel_runs for hit in run.rankings)
        )
        try:
            hydrated = await self._repository.hydrate(scope, candidate_ids)
        except Exception as exc:
            return EvidencePacket(
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
                query=query,
                coverage=RetrievalCoverage.NOT_FOUND,
                degraded_channels=list(CHANNEL_ORDER),
                warnings=sorted(
                    set(
                        [
                            *warnings,
                            f"authoritative_evidence_unavailable:{type(exc).__name__}",
                        ]
                    )
                ),
            )

        requested_chunk_ids = set(candidate_ids)
        visible_chunk_ids = {
            chunk_id
            for chunk_id, records in hydrated.items()
            if chunk_id in requested_chunk_ids
            and records
            and all(
                record.chunk_id == chunk_id
                and record.course_id == scope.course_id
                and record.curriculum_edition_id == scope.curriculum_edition_id
                for record in records
            )
        }
        if len(visible_chunk_ids) != len(hydrated):
            warnings.append("authoritative_evidence_omitted:scope_mismatch")
        verified_graph_chunk_ids = {
            chunk_id
            for chunk_id, graph_quotes in graph_run.chunk_quotes.items()
            if chunk_id in visible_chunk_ids
            and graph_quotes
            & {"".join(record.evidence_snippet.casefold().split()) for record in hydrated[chunk_id]}
        }
        unresolved_graph_chunks = {
            hit.chunk_id for hit in graph_run.rankings
        } - verified_graph_chunk_ids
        if unresolved_graph_chunks:
            degraded.add(RetrievalChannel.GRAPH)
            warnings.append("neo4j_graph_omitted:exact_relational_evidence_not_found")
        rankings = {
            run.channel: [
                hit
                for hit in run.rankings
                if hit.chunk_id
                in (
                    verified_graph_chunk_ids
                    if run.channel is RetrievalChannel.GRAPH
                    else visible_chunk_ids
                )
            ]
            for run in channel_runs
        }
        authority_priorities = {
            chunk_id: max(
                max(record.authority_priority, record.publication_priority) for record in records
            )
            for chunk_id, records in hydrated.items()
            if chunk_id in visible_chunk_ids
        }
        fused = reciprocal_rank_fusion(
            rankings,
            authority_priorities=authority_priorities,
            rrf_k=self._config.rrf_k,
            limit=self._config.max_evidence,
        )

        evidence_items: list[EvidenceItem] = []
        for fused_chunk in fused:
            records = hydrated.get(fused_chunk.chunk_id, ())
            if not records:
                continue
            contributions = [
                RetrievalContribution(
                    channel=contribution.channel,
                    rank=contribution.rank,
                    raw_score=contribution.raw_score,
                    fused_score=contribution.weighted_rrf,
                )
                for contribution in fused_chunk.contributions
            ]
            evidence_items.append(records[0].to_evidence_item(contributions))

        graph_nodes, graph_edges, graph_omitted = self._graph_context(
            graph_run, verified_graph_chunk_ids
        )
        if graph_omitted:
            warnings.append("neo4j_graph_omitted:unresolved_relational_provenance")
            degraded.add(RetrievalChannel.GRAPH)
        degraded_channels = [channel for channel in CHANNEL_ORDER if channel in degraded]
        if not evidence_items:
            coverage = RetrievalCoverage.NOT_FOUND
            graph_nodes = []
            graph_edges = []
        elif (
            len(evidence_items) >= self._config.sufficient_evidence_count and not degraded_channels
        ):
            coverage = RetrievalCoverage.SUFFICIENT
        else:
            coverage = RetrievalCoverage.PARTIAL
        return EvidencePacket(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            query=query,
            coverage=coverage,
            evidence=evidence_items,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            degraded_channels=degraded_channels,
            warnings=sorted(set(warnings)),
        )
