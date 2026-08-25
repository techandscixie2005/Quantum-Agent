from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from quantum_agent.knowledge.graph_store import (
    AUTHORITATIVE_REVIEW_STORE,
    ApprovedGraphNode,
    ApprovedGraphRelationship,
    GraphEvidence,
    GraphInvariantError,
    GraphNotFoundError,
    GraphScope,
    InMemoryGraphStore,
    Neo4jGraphStore,
    UnsafeGraphIdentifierError,
    _safe_node_label,
    _safe_relationship_type,
)
from quantum_agent.knowledge.ontology import NodeType, RelationshipType

SCOPE = GraphScope(course_id="quantum-physics", curriculum_edition_id="2026")
OTHER_EDITION = GraphScope(course_id="quantum-physics", curriculum_edition_id="2025")


def approved_evidence() -> GraphEvidence:
    return GraphEvidence(
        source_document_id="doc-v1",
        source_chunk_id="chunk-2",
        source_file="第1-2章.pdf",
        chapter="第二章",
        page_number=12,
        quote="厄米算符的本征值是实数。",
    )


def node(
    candidate_id: str,
    label: str,
    *,
    scope: GraphScope = SCOPE,
    node_type: NodeType = NodeType.CONCEPT,
) -> ApprovedGraphNode:
    return ApprovedGraphNode(
        candidate_id=candidate_id,
        scope=scope,
        node_type=node_type,
        canonical_key=f"concept:{candidate_id}",
        label=label,
        description=f"Course description of {label}",
        evidence=(approved_evidence(),),
        review_decision_id=f"decision-{candidate_id}",
        review_revision=1,
    )


def relationship(
    candidate_id: str,
    source_id: str,
    target_id: str,
    *,
    scope: GraphScope = SCOPE,
    relationship_type: RelationshipType = RelationshipType.PREREQUISITE_OF,
    source_type: NodeType = NodeType.CONCEPT,
    target_type: NodeType = NodeType.CONCEPT,
) -> ApprovedGraphRelationship:
    return ApprovedGraphRelationship(
        candidate_id=candidate_id,
        scope=scope,
        relationship_type=relationship_type,
        source_candidate_id=source_id,
        target_candidate_id=target_id,
        source_node_type=source_type,
        target_node_type=target_type,
        evidence=(approved_evidence(),),
        review_decision_id=f"decision-{candidate_id}",
        review_revision=1,
    )


def test_projection_models_require_postgresql_approval_and_valid_ontology() -> None:
    assert AUTHORITATIVE_REVIEW_STORE == "postgresql"
    with pytest.raises(ValidationError):
        ApprovedGraphNode(
            candidate_id="unreviewed",
            scope=SCOPE,
            node_type=NodeType.CONCEPT,
            canonical_key="concept:x",
            label="x",
            status="pending",
            review_decision_id="",
            review_revision=0,
        )
    with pytest.raises(ValidationError):
        relationship(
            "invalid-relation",
            "exercise",
            "course",
            relationship_type=RelationshipType.ACTS_ON,
            source_type=NodeType.EXERCISE,
            target_type=NodeType.COURSE,
        )


@pytest.mark.asyncio
async def test_in_memory_store_sync_is_idempotent_scoped_and_searches_approved() -> None:
    store = InMemoryGraphStore()
    current = node("hermitian", "厄米算符")
    old = node("hermitian", "旧版厄米算符", scope=OTHER_EDITION)
    await store.sync_node(current)
    await store.sync_node(current.model_copy(update={"description": "updated"}))
    await store.sync_node(old)

    current_hits = await store.search_nodes(SCOPE, "厄米")
    old_hits = await store.search_nodes(OTHER_EDITION, "厄米")
    assert [(hit.node.label, hit.node.description) for hit in current_hits] == [
        ("厄米算符", "updated")
    ]
    assert [hit.node.label for hit in old_hits] == ["旧版厄米算符"]


@pytest.mark.asyncio
async def test_relationship_requires_existing_approved_scoped_endpoints() -> None:
    store = InMemoryGraphStore()
    await store.sync_node(node("a", "A"))
    with pytest.raises(GraphNotFoundError):
        await store.sync_relationship(relationship("a-before-b", "a", "b"))
    await store.sync_node(node("b", "B", scope=OTHER_EDITION))
    with pytest.raises(GraphNotFoundError):
        await store.sync_relationship(relationship("cross-edition", "a", "b"))


@pytest.mark.asyncio
async def test_subgraph_and_prerequisite_paths_preserve_course_order() -> None:
    store = InMemoryGraphStore()
    for item in (
        node("linear-algebra", "线性代数"),
        node("state-space", "态空间"),
        node("measurement", "量子测量"),
    ):
        await store.sync_node(item)
    await store.sync_relationship(relationship("r1", "linear-algebra", "state-space"))
    await store.sync_relationship(relationship("r2", "state-space", "measurement"))

    graph = await store.get_subgraph(SCOPE, "measurement", max_depth=2)
    assert {item.candidate_id for item in graph.nodes} == {
        "linear-algebra",
        "state-space",
        "measurement",
    }
    assert {item.candidate_id for item in graph.relationships} == {"r1", "r2"}

    paths = await store.get_prerequisite_paths(SCOPE, "measurement", max_depth=3)
    assert [[item.candidate_id for item in path.nodes] for path in paths] == [
        ["state-space", "measurement"],
        ["linear-algebra", "state-space", "measurement"],
    ]


@pytest.mark.asyncio
async def test_merge_rewires_relationships_and_delete_operations_are_idempotent() -> None:
    store = InMemoryGraphStore()
    await store.sync_node(node("canonical", "波函数"))
    await store.sync_node(node("duplicate", "波函数(重复)"))
    await store.sync_node(node("measurement", "测量"))
    await store.sync_relationship(relationship("duplicate-prereq", "duplicate", "measurement"))

    await store.merge_nodes(SCOPE, "canonical", ["duplicate"])
    await store.merge_nodes(SCOPE, "canonical", ["duplicate"])
    graph = await store.get_subgraph(SCOPE, "canonical", max_depth=1)
    assert {item.candidate_id for item in graph.nodes} == {"canonical", "measurement"}
    assert graph.relationships[0].source_candidate_id == "canonical"
    assert not await store.delete_node(SCOPE, "duplicate")
    assert await store.delete_relationship(SCOPE, "duplicate-prereq")
    assert not await store.delete_relationship(SCOPE, "duplicate-prereq")
    assert await store.delete_node(SCOPE, "measurement")
    assert not await store.delete_node(SCOPE, "measurement")


@pytest.mark.asyncio
async def test_merge_rejects_different_ontology_types() -> None:
    store = InMemoryGraphStore()
    await store.sync_node(node("concept", "概念"))
    await store.sync_node(node("formula", "公式", node_type=NodeType.FORMULA))
    with pytest.raises(GraphInvariantError):
        await store.merge_nodes(SCOPE, "concept", ["formula"])


def test_dynamic_cypher_identifiers_are_closed_whitelists() -> None:
    assert _safe_node_label(NodeType.OPERATOR) == "Operator"
    assert _safe_relationship_type(RelationshipType.ACTS_ON) == "ACTS_ON"
    with pytest.raises(UnsafeGraphIdentifierError):
        _safe_node_label("Concept`) DETACH DELETE n //")
    with pytest.raises(UnsafeGraphIdentifierError):
        _safe_relationship_type("USES]->() DELETE r //")


class FakeResult:
    def __init__(
        self,
        *,
        single_record: Mapping[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.single_record = single_record
        self.rows = rows or []

    async def single(self) -> Mapping[str, Any] | None:
        return self.single_record

    async def data(self) -> list[dict[str, Any]]:
        return self.rows

    async def consume(self) -> None:
        return None


class FakeTransaction:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    async def run(self, query: str, **parameters: Any) -> FakeResult:
        self.calls.append((query, parameters))
        if "RETURN n.node_type AS node_type" in query:
            return FakeResult(single_record=None)
        if "RETURN n.candidate_id AS candidate_id" in query:
            return FakeResult(single_record={"candidate_id": parameters["candidate_id"]})
        if "RETURN r.candidate_id AS candidate_id" in query:
            return FakeResult(single_record={"candidate_id": parameters["candidate_id"]})
        return FakeResult()


class FakeSession:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def run(self, query: str, **parameters: Any) -> FakeResult:
        return await FakeTransaction(self.calls).run(query, **parameters)

    async def execute_write(self, work: Any) -> Any:
        return await work(FakeTransaction(self.calls))


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def session(self, **_kwargs: Any) -> FakeSession:
        return FakeSession(self.calls)


@pytest.mark.asyncio
async def test_neo4j_store_interpolates_only_whitelisted_label_not_user_text() -> None:
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)
    malicious_label = "x'}) MATCH (n) DETACH DELETE n //"
    approved = node("safe-id", malicious_label, node_type=NodeType.OPERATOR)
    await store.sync_node(approved)

    rendered_query, parameters = next(
        (query, params) for query, params in driver.calls if "MERGE (n:GraphEntity" in query
    )
    assert "SET n:Operator" in rendered_query
    assert malicious_label not in rendered_query
    assert parameters["label"] == malicious_label
    assert "review_decision_id" in parameters

    provenance_query, provenance_parameters = next(
        (query, params)
        for query, params in driver.calls
        if "MERGE (document:ProvenanceEntity:SourceDocument" in query
    )
    assert "MERGE (chunk:ProvenanceEntity:SourceChunk" in provenance_query
    assert "MERGE (evidence:ProvenanceEntity:Evidence" in provenance_query
    assert "claim_support:SUPPORTED_BY" in provenance_query
    assert "evidence_support:SUPPORTED_BY" in provenance_query
    assert "chunk_document:PART_OF" in provenance_query
    assert "status = 'published'" in provenance_query
    assert approved.evidence[0].quote not in provenance_query
    assert provenance_parameters["quote"] == approved.evidence[0].quote
    assert provenance_parameters["claim_kind"] == "node"


@pytest.mark.asyncio
async def test_relationship_sync_projects_its_approved_evidence_chain() -> None:
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)
    approved_relationship = relationship("rel-evidence", "source", "target")
    await store.sync_relationship(approved_relationship)

    provenance_parameters = next(
        params
        for query, params in driver.calls
        if "MERGE (document:ProvenanceEntity:SourceDocument" in query
    )
    assert provenance_parameters["claim_kind"] == "relationship"
    assert provenance_parameters["claim_candidate_id"] == "rel-evidence"
    assert provenance_parameters["source_chunk_id"] == "chunk-2"


@pytest.mark.asyncio
async def test_neo4j_schema_uses_whitelisted_constraints() -> None:
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)
    await store.ensure_schema()
    queries = [query for query, _parameters in driver.calls]
    assert any("quantum_graph_entity_key" in query for query in queries)
    assert any("quantum_provenance_entity_key" in query for query in queries)
    assert any("[r:PREREQUISITE_OF]" in query for query in queries)
    assert all("$" not in query for query in queries)  # DDL contains no user input
