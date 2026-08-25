from __future__ import annotations

import hashlib
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantum_agent.knowledge.evidence_packets import (
    EvidenceKind,
    EvidenceLocator,
    LocatorType,
    RetrievalChannel,
    RetrievalCoverage,
)
from quantum_agent.knowledge.fusion import RankedChunk
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    GraphEvidence,
    InMemoryGraphStore,
)
from quantum_agent.knowledge.ontology import NodeType
from quantum_agent.knowledge.retrieval import (
    AuthoritativeEvidenceRecord,
    HybridEvidenceRetriever,
    HybridRetrievalConfig,
    RetrievalScope,
    StudentVisibleEvidenceRepository,
    build_hydration_statement,
    build_postgres_full_text_statement,
    build_postgres_semantic_statement,
    lexical_query_terms,
)
from quantum_agent.llm.embeddings import EmbeddingProbe, HashingEmbeddingGateway

COURSE = UUID("00000000-0000-0000-0000-000000000010")
EDITION = UUID("00000000-0000-0000-0000-000000000020")
CHUNK_ONE = UUID("00000000-0000-0000-0000-000000000101")
CHUNK_TWO = UUID("00000000-0000-0000-0000-000000000102")
DOCUMENT = UUID("00000000-0000-0000-0000-000000000201")
VERSION = UUID("00000000-0000-0000-0000-000000000301")
EVIDENCE_ONE = UUID("00000000-0000-0000-0000-000000000401")
EVIDENCE_TWO = UUID("00000000-0000-0000-0000-000000000402")


def record(
    chunk_id: UUID,
    evidence_id: UUID,
    text: str,
    snippet: str,
) -> AuthoritativeEvidenceRecord:
    start = text.index(snippet)
    return AuthoritativeEvidenceRecord(
        course_id=COURSE,
        curriculum_edition_id=EDITION,
        evidence_id=evidence_id,
        chunk_id=chunk_id,
        document_id=DOCUMENT,
        document_version_id=VERSION,
        document_title="量子力学第二章",
        document_version=1,
        source_file_name="第1-2章.pdf",
        source_file_sha256="a" * 64,
        source_chunk_sha256=hashlib.sha256(text.encode()).hexdigest(),
        evidence_sha256=hashlib.sha256(snippet.encode()).hexdigest(),
        chapter="第二章",
        section_path=("第二章", "波函数"),
        locator=EvidenceLocator(locator_type=LocatorType.PDF_PAGE, physical_page=12),
        source_chunk=text,
        evidence_snippet=snippet,
        evidence_char_start=start,
        evidence_char_end=start + len(snippet),
        kind=EvidenceKind.COURSE_MATERIAL,
        authority_priority=90,
        publication_priority=95,
    )


RECORD_ONE = record(CHUNK_ONE, EVIDENCE_ONE, "波函数具有统计解释。", "波函数具有统计解释")
RECORD_TWO = record(CHUNK_TWO, EVIDENCE_TWO, "概率密度等于波函数模方。", "概率密度")


def _postgresql_dialect() -> Dialect:
    return postgresql.dialect()  # type: ignore[no-untyped-call]


def test_postgres_statements_compile_fts_vector_visibility_and_hash_guards() -> None:
    dialect = _postgresql_dialect()
    full_text = str(build_postgres_full_text_statement(3).compile(dialect=dialect))
    semantic = str(build_postgres_semantic_statement().compile(dialect=dialect))
    hydration = str(build_hydration_statement().compile(dialect=dialect))

    assert "student_visible_chunks" in full_text
    assert "@@ plainto_tsquery" in full_text
    assert "publication_curriculum_edition_id" in full_text
    assert "evidence.status" in full_text
    assert "evidence.chunk_content_sha256 = student_visible_chunks.content_sha256" in full_text
    assert "<=>" in semantic
    assert "embedding_dimension" in semantic
    assert "embedding_model" in semantic
    assert "source_document_versions.status" in hydration
    assert "evidence.evidence_sha256" in hydration
    assert "source_document_versions.source_file_sha256" in hydration


def test_jieba_query_terms_preserve_useful_cjk_concepts() -> None:
    terms = lexical_query_terms("什么是波函数的统计解释?")
    assert "波函数" in terms
    assert "统计" in terms
    assert "什么" not in terms


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self._rows)


class RecordingSession:
    def __init__(self, rows: list[dict[str, Any]], dialect_name: str = "postgresql") -> None:
        self.rows = rows
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))

    async def __aenter__(self) -> RecordingSession:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def get_bind(self) -> Any:
        return self._bind

    async def execute(self, statement: Any, parameters: dict[str, Any]) -> FakeResult:
        self.calls.append((statement, parameters))
        return FakeResult(self.rows)


@pytest.mark.asyncio
async def test_session_double_proves_query_text_and_scope_are_parameters() -> None:
    malicious_query = "波函数%' OR true --"
    session = RecordingSession([{"chunk_id": CHUNK_ONE, "raw_score": 0.8}])
    repository = StudentVisibleEvidenceRepository(lambda: session)
    scope = RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION)

    hits = await repository.full_text(scope, malicious_query, limit=5)

    assert hits == [RankedChunk(CHUNK_ONE, 0.8)]
    statement, parameters = session.calls[0]
    rendered = str(statement.compile(dialect=_postgresql_dialect()))
    assert malicious_query not in rendered
    assert parameters["course_id"] == COURSE
    assert parameters["curriculum_edition_id"] == EDITION
    assert parameters["approved_status"] == "approved"
    assert "true" in parameters["fts_query"]
    assert any("true" in str(value) for key, value in parameters.items() if key.startswith("term_"))


@pytest.mark.asyncio
async def test_sqlite_repository_returns_only_visible_grounded_exact_evidence() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_text = "波函数的统计解释给出概率密度。"
    snippet = "波函数的统计解释"
    chunk_sha = hashlib.sha256(source_text.encode()).hexdigest()
    evidence_sha = hashlib.sha256(snippet.encode()).hexdigest()
    review_chunk = uuid4()
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            """
            CREATE TABLE source_document_versions (
                id CHAR(32) PRIMARY KEY, version_number INTEGER NOT NULL,
                source_file_sha256 VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL
            )
            """
        )
        await connection.exec_driver_sql(
            """
            CREATE TABLE evidence (
                id CHAR(32) PRIMARY KEY, source_chunk_id CHAR(32) NOT NULL,
                evidence_snippet TEXT NOT NULL, char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL, evidence_sha256 VARCHAR(64) NOT NULL,
                chunk_content_sha256 VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
                locator_json JSON NOT NULL
            )
            """
        )
        await connection.exec_driver_sql(
            """
            CREATE TABLE projected_chunks (
                id CHAR(32), document_version_id CHAR(32), ordinal INTEGER,
                locator_type VARCHAR(32), locator_start VARCHAR(32), locator_end VARCHAR(32),
                physical_page INTEGER, printed_page_label VARCHAR(32), slide_number INTEGER,
                paragraph_start INTEGER, paragraph_end INTEGER, section_path JSON,
                content TEXT, evidence_snippet TEXT, content_sha256 VARCHAR(64),
                search_text TEXT, search_vector TEXT, embedding JSON,
                embedding_dimension INTEGER, embedding_model VARCHAR(100),
                extraction_status VARCHAR(32), course_id CHAR(32),
                publication_curriculum_edition_id CHAR(32),
                source_document_id CHAR(32), source_document_title VARCHAR(200),
                source_filename VARCHAR(200), source_role VARCHAR(50),
                authority_priority INTEGER, publication_priority INTEGER,
                published_at DATETIME
            )
            """
        )
        await connection.exec_driver_sql(
            "CREATE VIEW student_visible_chunks AS "
            "SELECT * FROM projected_chunks WHERE extraction_status = 'approved'"
        )
        await connection.exec_driver_sql(
            "INSERT INTO source_document_versions VALUES (?, 1, ?, 'published')",
            (VERSION.hex, "a" * 64),
        )
        insert_chunk = """
            INSERT INTO projected_chunks (
                id, document_version_id, ordinal, locator_type, locator_start, locator_end,
                physical_page, section_path, content, content_sha256, search_text,
                extraction_status, course_id, publication_curriculum_edition_id,
                source_document_id, source_document_title, source_filename, source_role,
                authority_priority, publication_priority, published_at
            ) VALUES (?, ?, 0, 'page', '12', '12', 12, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'lecture', 90, 95, '2026-08-22T12:00:00+00:00')
        """
        await connection.exec_driver_sql(
            insert_chunk,
            (
                CHUNK_ONE.hex,
                VERSION.hex,
                '["第二章", "波函数"]',
                source_text,
                chunk_sha,
                source_text,
                "approved",
                COURSE.hex,
                EDITION.hex,
                DOCUMENT.hex,
                "量子力学第二章",
                "第1-2章.pdf",
            ),
        )
        await connection.exec_driver_sql(
            insert_chunk,
            (
                review_chunk.hex,
                VERSION.hex,
                '["第二章"]',
                "仍待审核的波函数内容",
                hashlib.sha256("仍待审核的波函数内容".encode()).hexdigest(),
                "仍待审核的波函数内容",
                "review_required",
                COURSE.hex,
                EDITION.hex,
                DOCUMENT.hex,
                "待审核",
                "review.pdf",
            ),
        )
        await connection.exec_driver_sql(
            "INSERT INTO evidence VALUES (?, ?, ?, 0, ?, ?, ?, 'grounded', '{}')",
            (
                EVIDENCE_ONE.hex,
                CHUNK_ONE.hex,
                snippet,
                len(snippet),
                evidence_sha,
                chunk_sha,
            ),
        )

    repository = StudentVisibleEvidenceRepository(session_factory)
    scope = RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION)
    hits = await repository.full_text(scope, "波函数统计解释", limit=10)
    hydrated = await repository.hydrate(scope, [CHUNK_ONE, review_chunk])

    assert [hit.chunk_id for hit in hits] == [CHUNK_ONE]
    assert set(hydrated) == {CHUNK_ONE}
    assert hydrated[CHUNK_ONE][0].source_chunk == source_text
    assert hydrated[CHUNK_ONE][0].evidence_snippet == snippet
    assert hydrated[CHUNK_ONE][0].source_chunk_sha256 == chunk_sha
    assert hydrated[CHUNK_ONE][0].evidence_sha256 == evidence_sha
    await engine.dispose()


class StaticRepository:
    def __init__(self) -> None:
        self.records = {
            CHUNK_ONE: (RECORD_ONE,),
            CHUNK_TWO: (RECORD_TWO,),
        }
        self.fail_hydration = False

    async def full_text(
        self,
        _scope: RetrievalScope,
        _query: str,
        *,
        limit: int,
        max_terms: int = 8,
    ) -> list[RankedChunk]:
        del max_terms
        return [RankedChunk(CHUNK_ONE, 0.8)][:limit]

    async def semantic(
        self,
        _scope: RetrievalScope,
        _embedding: Sequence[float],
        *,
        embedding_model: str,
        limit: int,
    ) -> list[RankedChunk]:
        del embedding_model
        return [RankedChunk(CHUNK_TWO, 0.95)][:limit]

    async def hydrate(
        self, _scope: RetrievalScope, chunk_ids: Sequence[UUID]
    ) -> dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]]:
        if self.fail_hydration:
            raise RuntimeError("database unavailable")
        return {
            chunk_id: self.records[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in self.records
        }


class LearnedEmbeddingGateway:
    @property
    def dimensions(self) -> int:
        return 384

    async def probe(self) -> EmbeddingProbe:
        return EmbeddingProbe(available=True, dimensions=384, provider="test_semantic")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 383 for _text in texts]


@pytest.mark.asyncio
async def test_hybrid_fusion_uses_graph_only_after_relational_resolution() -> None:
    repository = StaticRepository()
    graph_store = InMemoryGraphStore()
    graph_node_id = uuid4()
    await graph_store.sync_node(
        ApprovedGraphNode(
            candidate_id=str(graph_node_id),
            scope=RetrievalScope(
                course_id=COURSE, curriculum_edition_id=EDITION
            ).graph_scope(),
            node_type=NodeType.CONCEPT,
            canonical_key="concept:wave-function",
            label="波函数",
            evidence=(
                GraphEvidence(
                    source_document_id=str(DOCUMENT),
                    source_chunk_id=str(CHUNK_TWO),
                    source_file="第1-2章.pdf",
                    page_number=12,
                    quote="概率密度",
                ),
            ),
            review_decision_id=str(uuid4()),
            review_revision=1,
        )
    )
    retriever = HybridEvidenceRetriever(
        repository=repository,
        embedding_gateway=LearnedEmbeddingGateway(),
        graph_store=graph_store,
        config=HybridRetrievalConfig(sufficient_evidence_count=2),
    )

    packet = await retriever.retrieve(
        RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION), "波函数"
    )

    assert packet.coverage is RetrievalCoverage.SUFFICIENT
    assert {item.chunk_id for item in packet.evidence} == {CHUNK_ONE, CHUNK_TWO}
    second = next(item for item in packet.evidence if item.chunk_id == CHUNK_TWO)
    assert {item.channel for item in second.contributions} == {
        RetrievalChannel.SEMANTIC,
        RetrievalChannel.GRAPH,
    }
    assert second.source_chunk == RECORD_TWO.source_chunk
    assert second.evidence_sha256 == RECORD_TWO.evidence_sha256
    assert [node.id for node in packet.graph_nodes] == [graph_node_id]
    assert packet.degraded_channels == []


@pytest.mark.asyncio
async def test_graph_text_without_matching_relational_evidence_is_not_a_channel_hit() -> None:
    graph_store = InMemoryGraphStore()
    graph_node_id = uuid4()
    await graph_store.sync_node(
        ApprovedGraphNode(
            candidate_id=str(graph_node_id),
            scope=RetrievalScope(
                course_id=COURSE, curriculum_edition_id=EDITION
            ).graph_scope(),
            node_type=NodeType.CONCEPT,
            canonical_key="concept:unresolved-claim",
            label="波函数",
            evidence=(
                GraphEvidence(
                    source_document_id=str(DOCUMENT),
                    source_chunk_id=str(CHUNK_TWO),
                    source_file="第1-2章.pdf",
                    page_number=12,
                    quote="关系库中不存在的证据",
                ),
            ),
            review_decision_id=str(uuid4()),
            review_revision=1,
        )
    )
    retriever = HybridEvidenceRetriever(
        repository=StaticRepository(),
        embedding_gateway=LearnedEmbeddingGateway(),
        graph_store=graph_store,
    )

    packet = await retriever.retrieve(
        RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION), "波函数"
    )

    chunk_two = next(item for item in packet.evidence if item.chunk_id == CHUNK_TWO)
    assert {item.channel for item in chunk_two.contributions} == {
        RetrievalChannel.SEMANTIC
    }
    assert packet.graph_nodes == []
    assert RetrievalChannel.GRAPH in packet.degraded_channels
    assert "neo4j_graph_omitted:exact_relational_evidence_not_found" in packet.warnings


@pytest.mark.asyncio
async def test_local_hashing_is_explicitly_lexical_degraded() -> None:
    retriever = HybridEvidenceRetriever(
        repository=StaticRepository(),
        embedding_gateway=HashingEmbeddingGateway(384),
        graph_store=None,
    )
    packet = await retriever.retrieve(
        RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION), "波函数"
    )
    assert packet.coverage is RetrievalCoverage.PARTIAL
    assert RetrievalChannel.SEMANTIC in packet.degraded_channels
    assert RetrievalChannel.GRAPH in packet.degraded_channels
    assert "pgvector_semantic_degraded:local_hashing_is_lexical" in packet.warnings


@pytest.mark.asyncio
async def test_authoritative_hydration_failure_fails_closed() -> None:
    repository = StaticRepository()
    repository.fail_hydration = True
    retriever = HybridEvidenceRetriever(
        repository=repository,
        embedding_gateway=LearnedEmbeddingGateway(),
        graph_store=None,
    )
    packet = await retriever.retrieve(
        RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION), "波函数"
    )
    assert packet.coverage is RetrievalCoverage.NOT_FOUND
    assert packet.evidence == []
    assert packet.graph_nodes == []
    assert set(packet.degraded_channels) == set(RetrievalChannel)
    assert any(
        warning.startswith("authoritative_evidence_unavailable")
        for warning in packet.warnings
    )


@pytest.mark.asyncio
async def test_hydrated_record_from_another_scope_is_never_returned() -> None:
    repository = StaticRepository()
    repository.records[CHUNK_ONE] = (
        RECORD_ONE.model_copy(update={"course_id": uuid4()}),
    )
    retriever = HybridEvidenceRetriever(
        repository=repository,
        embedding_gateway=None,
        graph_store=None,
    )

    packet = await retriever.retrieve(
        RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION), "波函数"
    )

    assert packet.coverage is RetrievalCoverage.NOT_FOUND
    assert packet.evidence == []
    assert "authoritative_evidence_omitted:scope_mismatch" in packet.warnings
