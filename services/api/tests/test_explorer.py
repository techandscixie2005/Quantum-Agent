from __future__ import annotations

import hashlib
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from quantum_agent.knowledge.evidence_packets import (
    EvidenceKind,
    EvidenceLocator,
    LocatorType,
)
from quantum_agent.knowledge.explorer import (
    ExplorerWarningCode,
    GraphExplorerService,
)
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    ApprovedGraphRelationship,
    GraphEvidence,
    GraphScope,
    GraphSearchHit,
    InMemoryGraphStore,
)
from quantum_agent.knowledge.ontology import NodeType, RelationshipType
from quantum_agent.knowledge.retrieval import AuthoritativeEvidenceRecord, RetrievalScope

COURSE = UUID("10000000-0000-0000-0000-000000000001")
EDITION = UUID("20000000-0000-0000-0000-000000000001")
OTHER_COURSE = UUID("10000000-0000-0000-0000-000000000002")
DOCUMENT = UUID("30000000-0000-0000-0000-000000000001")
VERSION = UUID("40000000-0000-0000-0000-000000000001")
SCOPE = RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION)


def authoritative_record(
    text: str,
    snippet: str,
    *,
    locator: EvidenceLocator,
) -> AuthoritativeEvidenceRecord:
    start = text.index(snippet)
    return AuthoritativeEvidenceRecord(
        course_id=COURSE,
        curriculum_edition_id=EDITION,
        evidence_id=uuid4(),
        chunk_id=uuid4(),
        document_id=DOCUMENT,
        document_version_id=VERSION,
        document_title="量子力学课程材料",
        document_version=1,
        source_file_name="量子力学讲义.pdf",
        source_file_sha256="a" * 64,
        source_chunk_sha256=hashlib.sha256(text.encode()).hexdigest(),
        evidence_sha256=hashlib.sha256(snippet.encode()).hexdigest(),
        chapter="第二章",
        section_path=("第二章", "波函数"),
        locator=locator,
        source_chunk=text,
        evidence_snippet=snippet,
        evidence_char_start=start,
        evidence_char_end=start + len(snippet),
        kind=EvidenceKind.COURSE_MATERIAL,
        authority_priority=90,
        publication_priority=95,
    )


NODE_RECORD = authoritative_record(
    "波函数具有统计解释。",
    "波函数具有统计解释",
    locator=EvidenceLocator(
        locator_type=LocatorType.PDF_PAGE,
        physical_page=12,
        printed_page_label="第二章-4",
    ),
)
TARGET_RECORD = authoritative_record(
    "概率密度等于波函数模方。",
    "概率密度等于波函数模方",
    locator=EvidenceLocator(
        locator_type=LocatorType.SLIDE,
        slide_number=17,
        physical_page=18,
    ),
)
EDGE_RECORD = authoritative_record(
    "波函数是理解概率密度的先修概念。",
    "波函数是理解概率密度的先修概念",
    locator=EvidenceLocator(
        locator_type=LocatorType.XLSX_ROW,
        sheet_name="先修关系",
        row_start=23,
        row_end=23,
    ),
)


def graph_evidence(record: AuthoritativeEvidenceRecord) -> GraphEvidence:
    return GraphEvidence(
        source_document_id=str(record.document_id),
        source_chunk_id=str(record.chunk_id),
        source_file=record.source_file_name,
        document_version_id=str(record.document_version_id),
        document_sha256=record.source_file_sha256,
        chunk_checksum=record.source_chunk_sha256,
        chapter=record.chapter,
        section_path=record.section_path,
        quote=record.evidence_snippet,
        quote_start=record.evidence_char_start,
        quote_end=record.evidence_char_end,
    )


def graph_node(
    label: str,
    record: AuthoritativeEvidenceRecord,
    *,
    candidate_id: UUID | None = None,
    scope: GraphScope | None = None,
) -> ApprovedGraphNode:
    resolved_id = candidate_id or uuid4()
    return ApprovedGraphNode(
        candidate_id=str(resolved_id),
        scope=scope or SCOPE.graph_scope(),
        node_type=NodeType.CONCEPT,
        canonical_key=f"concept:{resolved_id}",
        label=label,
        description=f"课程中的{label}",
        properties={"aliases": [f"{label}别名"], "formula_latex": r"|\psi|^2"},
        evidence=(graph_evidence(record),),
        review_decision_id=str(uuid4()),
        review_revision=1,
    )


def graph_relationship(
    source: ApprovedGraphNode,
    target: ApprovedGraphNode,
    record: AuthoritativeEvidenceRecord,
) -> ApprovedGraphRelationship:
    return ApprovedGraphRelationship(
        candidate_id=str(uuid4()),
        scope=SCOPE.graph_scope(),
        relationship_type=RelationshipType.PREREQUISITE_OF,
        source_candidate_id=source.candidate_id,
        target_candidate_id=target.candidate_id,
        source_node_type=NodeType.CONCEPT,
        target_node_type=NodeType.CONCEPT,
        evidence=(graph_evidence(record),),
        review_decision_id=str(uuid4()),
        review_revision=1,
    )


class StaticEvidenceRepository:
    def __init__(self, records: Sequence[AuthoritativeEvidenceRecord]) -> None:
        self.records = {record.chunk_id: (record,) for record in records}

    async def hydrate(
        self,
        _scope: RetrievalScope,
        chunk_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]]:
        return {
            chunk_id: self.records[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in self.records
        }


@pytest.mark.asyncio
async def test_search_omits_unpublished_graph_entity_and_returns_original_locator() -> None:
    store = InMemoryGraphStore()
    published = graph_node("波函数", NODE_RECORD)
    unpublished_record = authoritative_record(
        "未发布的波函数说明。",
        "未发布的波函数说明",
        locator=EvidenceLocator(locator_type=LocatorType.PDF_PAGE, physical_page=99),
    )
    unpublished = graph_node("波函数的未发布说明", unpublished_record)
    await store.sync_node(published)
    await store.sync_node(unpublished)
    service = GraphExplorerService(
        graph_store=store,
        evidence_repository=StaticEvidenceRepository([NODE_RECORD]),
    )

    response = await service.search_concepts(SCOPE, "波函数")

    assert [hit.node.id for hit in response.results] == [UUID(published.candidate_id)]
    citation = response.results[0].node.citations[0]
    assert citation.source_chunk == NODE_RECORD.source_chunk
    assert citation.evidence_snippet == NODE_RECORD.evidence_snippet
    assert citation.source_chunk_sha256 == NODE_RECORD.source_chunk_sha256
    assert citation.evidence_sha256 == NODE_RECORD.evidence_sha256
    assert citation.locator.physical_page == 12
    assert citation.locator.printed_page_label == "第二章-4"
    assert response.results[0].node.formula_latex == r"|\psi|^2"
    assert response.degraded is True
    assert ExplorerWarningCode.UNPUBLISHED_EVIDENCE in response.warnings
    assert ExplorerWarningCode.NO_VISIBLE_EVIDENCE in response.warnings


@pytest.mark.asyncio
async def test_search_rejects_graph_quote_with_nonmatching_chunk_hash() -> None:
    store = InMemoryGraphStore()
    stale = graph_node("波函数", NODE_RECORD).model_copy(
        update={
            "evidence": (
                graph_evidence(NODE_RECORD).model_copy(update={"chunk_checksum": "0" * 64}),
            )
        }
    )
    await store.sync_node(stale)
    service = GraphExplorerService(
        graph_store=store,
        evidence_repository=StaticEvidenceRepository([NODE_RECORD]),
    )

    response = await service.search_concepts(SCOPE, "波函数")

    assert response.results == ()
    assert ExplorerWarningCode.EVIDENCE_INTEGRITY_MISMATCH in response.warnings
    assert ExplorerWarningCode.NO_VISIBLE_EVIDENCE in response.warnings


class LeakySearchGraphStore(InMemoryGraphStore):
    def __init__(self, leaked_node: ApprovedGraphNode) -> None:
        super().__init__()
        self.leaked_node = leaked_node

    async def search_nodes(
        self,
        _scope: GraphScope,
        _query: str,
        *,
        node_types: Sequence[NodeType] | None = None,
        limit: int = 20,
    ) -> list[GraphSearchHit]:
        del node_types, limit
        return [GraphSearchHit(node=self.leaked_node, score=10)]


@pytest.mark.asyncio
async def test_malicious_cross_scope_graph_result_cannot_leak() -> None:
    leaked_node = graph_node(
        "另一个课程的秘密概念",
        NODE_RECORD,
        scope=GraphScope(
            course_id=str(OTHER_COURSE),
            curriculum_edition_id=str(EDITION),
        ),
    )
    service = GraphExplorerService(
        graph_store=LeakySearchGraphStore(leaked_node),
        evidence_repository=StaticEvidenceRepository([NODE_RECORD]),
    )

    response = await service.search_concepts(SCOPE, "秘密概念")

    assert response.results == ()
    assert response.warnings == (ExplorerWarningCode.SCOPE_MISMATCH,)
    assert "另一个课程" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_subgraph_requires_edge_own_published_evidence() -> None:
    store = InMemoryGraphStore()
    source = graph_node("波函数", NODE_RECORD)
    target = graph_node("概率密度", TARGET_RECORD)
    visible_edge = graph_relationship(source, target, EDGE_RECORD)
    unpublished_edge_record = authoritative_record(
        "另一条未发布先修关系。",
        "另一条未发布先修关系",
        locator=EvidenceLocator(locator_type=LocatorType.PDF_PAGE, physical_page=100),
    )
    hidden_edge = graph_relationship(source, target, unpublished_edge_record)
    await store.sync_node(source)
    await store.sync_node(target)
    await store.sync_relationship(visible_edge)
    await store.sync_relationship(hidden_edge)
    service = GraphExplorerService(
        graph_store=store,
        evidence_repository=StaticEvidenceRepository(
            [NODE_RECORD, TARGET_RECORD, EDGE_RECORD]
        ),
    )

    response = await service.subgraph(SCOPE, UUID(source.candidate_id))

    assert {node.id for node in response.nodes} == {
        UUID(source.candidate_id),
        UUID(target.candidate_id),
    }
    assert [edge.id for edge in response.edges] == [UUID(visible_edge.candidate_id)]
    edge_citation = response.edges[0].citations[0]
    assert edge_citation.locator.sheet_name == "先修关系"
    assert edge_citation.locator.row_start == 23
    assert ExplorerWarningCode.UNPUBLISHED_EVIDENCE in response.warnings


@pytest.mark.asyncio
async def test_prerequisite_paths_are_returned_only_when_whole_path_is_visible() -> None:
    store = InMemoryGraphStore()
    source = graph_node("波函数", NODE_RECORD)
    target = graph_node("概率密度", TARGET_RECORD)
    visible_edge = graph_relationship(source, target, EDGE_RECORD)
    hidden_source_record = authoritative_record(
        "未发布的先修概念。",
        "未发布的先修概念",
        locator=EvidenceLocator(locator_type=LocatorType.PDF_PAGE, physical_page=77),
    )
    hidden_source = graph_node("未发布先修概念", hidden_source_record)
    hidden_edge = graph_relationship(hidden_source, target, EDGE_RECORD)
    for node in (source, target, hidden_source):
        await store.sync_node(node)
    await store.sync_relationship(visible_edge)
    await store.sync_relationship(hidden_edge)
    service = GraphExplorerService(
        graph_store=store,
        evidence_repository=StaticEvidenceRepository(
            [NODE_RECORD, TARGET_RECORD, EDGE_RECORD]
        ),
    )

    response = await service.prerequisite_paths(SCOPE, UUID(target.candidate_id))

    assert len(response.paths) == 1
    assert [node.id for node in response.paths[0].nodes] == [
        UUID(source.candidate_id),
        UUID(target.candidate_id),
    ]
    assert response.paths[0].nodes[1].citations[0].locator.slide_number == 17
    assert response.paths[0].edges[0].id == UUID(visible_edge.candidate_id)
    assert ExplorerWarningCode.INCOMPLETE_PREREQUISITE_PATH in response.warnings


@pytest.mark.asyncio
async def test_cross_scope_relational_record_is_also_omitted() -> None:
    store = InMemoryGraphStore()
    node = graph_node("波函数", NODE_RECORD)
    await store.sync_node(node)
    wrong_scope_record = NODE_RECORD.model_copy(update={"course_id": OTHER_COURSE})
    service = GraphExplorerService(
        graph_store=store,
        evidence_repository=StaticEvidenceRepository([wrong_scope_record]),
    )

    response = await service.search_concepts(SCOPE, "波函数")

    assert response.results == ()
    assert ExplorerWarningCode.SCOPE_MISMATCH in response.warnings
    assert NODE_RECORD.evidence_snippet not in response.model_dump_json()
