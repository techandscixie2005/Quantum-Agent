"""Approved-only Neo4j projection and deterministic in-memory test store.

PostgreSQL is the authority for candidate state, evidence support, revisions,
teacher decisions, and merge lineage.  Neo4j is a rebuildable read projection;
it has no approval API.  Consequently every sync input below requires a
PostgreSQL review decision id/revision and has the literal status ``approved``.

All dynamic Cypher labels and relationship types are selected from the enums in
``ontology.py``.  User/model strings are always query parameters and can never
be interpolated into Cypher identifiers.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantum_agent.knowledge.ontology import (
    NODE_LABEL_WHITELIST,
    RELATIONSHIP_TYPE_WHITELIST,
    NodeType,
    RelationshipType,
    is_allowed_triple,
)

AUTHORITATIVE_REVIEW_STORE: Final[str] = "postgresql"
MAX_GRAPH_DEPTH: Final[int] = 5
MAX_QUERY_LIMIT: Final[int] = 200


class GraphStoreError(RuntimeError):
    """Base error for graph projection failures."""


class GraphInvariantError(GraphStoreError):
    """The requested projection would violate an ontology/review invariant."""


class GraphNotFoundError(GraphStoreError):
    """A scoped approved graph entity required by an operation does not exist."""


class UnsafeGraphIdentifierError(GraphStoreError):
    """A dynamic Cypher identifier was not present in the ontology whitelist."""


def _strip_required(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("value must not be blank")
    return stripped


def _validate_json_object(value: dict[str, Any]) -> dict[str, Any]:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("properties must contain finite JSON values") from exc
    return value


class GraphScope(BaseModel):
    """Mandatory tenant and curriculum-version boundary for every operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: str = Field(min_length=1)
    curriculum_edition_id: str = Field(min_length=1)

    @field_validator("course_id", "curriculum_edition_id")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        return _strip_required(value)


class GraphEvidence(BaseModel):
    """Verified evidence pointer copied from an approved PostgreSQL revision.

    Full authoritative source-chunk text stays in PostgreSQL/object storage.
    Neo4j stores the exact quote plus immutable source/version/checksum pointers.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document_id: str = Field(min_length=1)
    source_chunk_id: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    document_version_id: str | None = None
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    chunk_checksum: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    chapter: str | None = None
    section_path: tuple[str, ...] = ()
    page_number: int | None = Field(default=None, ge=1)
    page_label: str | None = None
    slide_number: int | None = Field(default=None, ge=1)
    locator_type: Literal["page", "slide", "paragraph", "sheet_row", "line"] | None = None
    locator_start: str | int | None = None
    locator_end: str | int | None = None
    quote: str = Field(min_length=1)
    quote_start: int | None = Field(default=None, ge=0)
    quote_end: int | None = Field(default=None, ge=0)
    verified_at_review: Literal[True] = True

    @field_validator("source_document_id", "source_chunk_id", "source_file", "quote")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        return _strip_required(value)


class ApprovedGraphNode(BaseModel):
    """A teacher-approved node revision eligible for Neo4j projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    scope: GraphScope
    node_type: NodeType
    canonical_key: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=512)
    description: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[GraphEvidence, ...] = ()
    status: Literal["approved"] = "approved"
    review_decision_id: str = Field(min_length=1)
    review_revision: int = Field(ge=1)

    @field_validator("candidate_id", "canonical_key", "label", "review_decision_id")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_object(value)


class ApprovedGraphRelationship(BaseModel):
    """A teacher-approved, ontology-valid relationship revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    scope: GraphScope
    relationship_type: RelationshipType
    source_candidate_id: str = Field(min_length=1)
    target_candidate_id: str = Field(min_length=1)
    source_node_type: NodeType
    target_node_type: NodeType
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[GraphEvidence, ...] = ()
    status: Literal["approved"] = "approved"
    review_decision_id: str = Field(min_length=1)
    review_revision: int = Field(ge=1)

    @field_validator(
        "candidate_id", "source_candidate_id", "target_candidate_id", "review_decision_id"
    )
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_object(value)

    @model_validator(mode="after")
    def validate_ontology_pattern(self) -> ApprovedGraphRelationship:
        if not is_allowed_triple(
            self.source_node_type,
            self.relationship_type,
            self.target_node_type,
        ):
            raise ValueError("approved relationship does not match an allowed ontology pattern")
        return self


class GraphSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node: ApprovedGraphNode
    score: float = Field(ge=0)


class GraphSubgraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: GraphScope
    root_candidate_id: str
    nodes: tuple[ApprovedGraphNode, ...] = ()
    relationships: tuple[ApprovedGraphRelationship, ...] = ()


class PrerequisitePath(BaseModel):
    """One ordered path from a prerequisite to the requested target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[ApprovedGraphNode, ...]
    relationships: tuple[ApprovedGraphRelationship, ...]

    @model_validator(mode="after")
    def validate_path_shape(self) -> PrerequisitePath:
        if len(self.nodes) < 2 or len(self.relationships) != len(self.nodes) - 1:
            raise ValueError("a prerequisite path must contain n nodes and n-1 relationships")
        if any(
            relation.relationship_type is not RelationshipType.PREREQUISITE_OF
            for relation in self.relationships
        ):
            raise ValueError("prerequisite paths may only contain PREREQUISITE_OF")
        return self


@runtime_checkable
class GraphStore(Protocol):
    """Interface shared by Neo4j and the deterministic unit-test store."""

    async def ensure_schema(self) -> None: ...

    async def sync_node(self, node: ApprovedGraphNode) -> None: ...

    async def sync_relationship(self, relationship: ApprovedGraphRelationship) -> None: ...

    async def delete_node(self, scope: GraphScope, candidate_id: str) -> bool: ...

    async def delete_relationship(self, scope: GraphScope, candidate_id: str) -> bool: ...

    async def merge_nodes(
        self,
        scope: GraphScope,
        survivor_candidate_id: str,
        duplicate_candidate_ids: Sequence[str],
    ) -> None: ...

    async def search_nodes(
        self,
        scope: GraphScope,
        query: str,
        *,
        node_types: Sequence[NodeType] | None = None,
        limit: int = 20,
    ) -> list[GraphSearchHit]: ...

    async def get_subgraph(
        self,
        scope: GraphScope,
        root_candidate_id: str,
        *,
        max_depth: int = 2,
        limit: int = 100,
    ) -> GraphSubgraph: ...

    async def get_prerequisite_paths(
        self,
        scope: GraphScope,
        target_candidate_id: str,
        *,
        max_depth: int = 4,
        limit: int = 20,
    ) -> list[PrerequisitePath]: ...

    async def close(self) -> None: ...


def _validate_depth(max_depth: int) -> int:
    if not 1 <= max_depth <= MAX_GRAPH_DEPTH:
        raise ValueError(f"max_depth must be between 1 and {MAX_GRAPH_DEPTH}")
    return max_depth


def _validate_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_QUERY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_LIMIT}")
    return limit


def _stable_graph_key(scope: GraphScope, kind: str, candidate_id: str) -> str:
    payload = json.dumps(
        [scope.course_id, scope.curriculum_edition_id, kind, _strip_required(candidate_id)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evidence_graph_key(
    scope: GraphScope,
    *,
    claim_kind: Literal["node", "relationship"],
    claim_candidate_id: str,
    evidence: GraphEvidence,
) -> str:
    evidence_identity = _canonical_json(
        [
            claim_kind,
            claim_candidate_id,
            evidence.source_chunk_id,
            evidence.quote_start,
            evidence.quote_end,
            evidence.quote,
        ]
    )
    return _stable_graph_key(scope, "evidence", evidence_identity)


def _safe_node_label(node_type: NodeType | str) -> str:
    try:
        label = NodeType(node_type).value
    except ValueError as exc:
        raise UnsafeGraphIdentifierError("unknown graph node label") from exc
    if label not in NODE_LABEL_WHITELIST:
        raise UnsafeGraphIdentifierError("node label is not ontology-whitelisted")
    return label


def _safe_relationship_type(relationship_type: RelationshipType | str) -> str:
    try:
        rel_type = RelationshipType(relationship_type).value
    except ValueError as exc:
        raise UnsafeGraphIdentifierError("unknown graph relationship type") from exc
    if rel_type not in RELATIONSHIP_TYPE_WHITELIST:
        raise UnsafeGraphIdentifierError("relationship type is not ontology-whitelisted")
    return rel_type


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _node_parameters(node: ApprovedGraphNode) -> dict[str, Any]:
    return {
        "graph_key": _stable_graph_key(node.scope, "node", node.candidate_id),
        "candidate_id": node.candidate_id,
        "course_id": node.scope.course_id,
        "curriculum_edition_id": node.scope.curriculum_edition_id,
        "node_type": node.node_type.value,
        "canonical_key": node.canonical_key,
        "label": node.label,
        "description": node.description,
        "properties_json": _canonical_json(node.properties),
        "evidence_json": _canonical_json([item.model_dump(mode="json") for item in node.evidence]),
        "status": node.status,
        "review_decision_id": node.review_decision_id,
        "review_revision": node.review_revision,
    }


def _relationship_parameters(
    relationship: ApprovedGraphRelationship,
) -> dict[str, Any]:
    return {
        "graph_key": _stable_graph_key(
            relationship.scope, "relationship", relationship.candidate_id
        ),
        "source_graph_key": _stable_graph_key(
            relationship.scope, "node", relationship.source_candidate_id
        ),
        "target_graph_key": _stable_graph_key(
            relationship.scope, "node", relationship.target_candidate_id
        ),
        "candidate_id": relationship.candidate_id,
        "course_id": relationship.scope.course_id,
        "curriculum_edition_id": relationship.scope.curriculum_edition_id,
        "relationship_type": relationship.relationship_type.value,
        "source_candidate_id": relationship.source_candidate_id,
        "target_candidate_id": relationship.target_candidate_id,
        "source_node_type": relationship.source_node_type.value,
        "target_node_type": relationship.target_node_type.value,
        "properties_json": _canonical_json(relationship.properties),
        "evidence_json": _canonical_json(
            [item.model_dump(mode="json") for item in relationship.evidence]
        ),
        "status": relationship.status,
        "review_decision_id": relationship.review_decision_id,
        "review_revision": relationship.review_revision,
    }


def _decode_json(raw: Any, expected: type[list[Any]] | type[dict[str, Any]]) -> Any:
    if raw in (None, ""):
        return expected()
    if not isinstance(raw, str):
        raise GraphInvariantError("Neo4j JSON projection property is not a string")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GraphInvariantError("Neo4j JSON projection property is invalid") from exc
    if not isinstance(decoded, expected):
        raise GraphInvariantError("Neo4j JSON projection property has the wrong shape")
    return decoded


def _node_from_properties(properties: Mapping[str, Any]) -> ApprovedGraphNode:
    try:
        return ApprovedGraphNode(
            candidate_id=properties["candidate_id"],
            scope=GraphScope(
                course_id=properties["course_id"],
                curriculum_edition_id=properties["curriculum_edition_id"],
            ),
            node_type=properties["node_type"],
            canonical_key=properties["canonical_key"],
            label=properties["label"],
            description=properties.get("description"),
            properties=_decode_json(properties.get("properties_json"), dict),
            evidence=_decode_json(properties.get("evidence_json"), list),
            status=properties["status"],
            review_decision_id=properties["review_decision_id"],
            review_revision=properties["review_revision"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphInvariantError("Neo4j node projection is incomplete or invalid") from exc


def _relationship_from_properties(
    properties: Mapping[str, Any], relationship_type: str | None = None
) -> ApprovedGraphRelationship:
    try:
        resolved_relationship_type = RelationshipType(
            relationship_type or properties["relationship_type"]
        )
        return ApprovedGraphRelationship(
            candidate_id=properties["candidate_id"],
            scope=GraphScope(
                course_id=properties["course_id"],
                curriculum_edition_id=properties["curriculum_edition_id"],
            ),
            relationship_type=resolved_relationship_type,
            source_candidate_id=properties["source_candidate_id"],
            target_candidate_id=properties["target_candidate_id"],
            source_node_type=properties["source_node_type"],
            target_node_type=properties["target_node_type"],
            properties=_decode_json(properties.get("properties_json"), dict),
            evidence=_decode_json(properties.get("evidence_json"), list),
            status=properties["status"],
            review_decision_id=properties["review_decision_id"],
            review_revision=properties["review_revision"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphInvariantError("Neo4j relationship projection is incomplete or invalid") from exc


class Neo4jGraphStore:
    """Official async Neo4j-driver implementation of the approved projection."""

    def __init__(
        self,
        *,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        driver: Any | None = None,
    ) -> None:
        if driver is None:
            if not uri or not username or password is None:
                raise ValueError("uri, username and password are required without a driver")
            try:
                from neo4j import AsyncGraphDatabase
            except ImportError as exc:  # pragma: no cover - environment guard
                raise GraphStoreError("the official neo4j driver is not installed") from exc
            driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
            self._owns_driver = True
        else:
            self._owns_driver = False
        self._driver = driver
        self._database = database

    def _session(self) -> Any:
        if self._database:
            return self._driver.session(database=self._database)
        return self._driver.session()

    async def _sync_evidence_chain_tx(
        self,
        tx: Any,
        *,
        scope: GraphScope,
        claim_graph_key: str,
        claim_kind: Literal["node", "relationship"],
        claim_candidate_id: str,
        evidence: GraphEvidence,
    ) -> str:
        """Project one approved evidence pointer without copying source text."""

        document_label = _safe_node_label(NodeType.SOURCE_DOCUMENT)
        chunk_label = _safe_node_label(NodeType.SOURCE_CHUNK)
        evidence_label = _safe_node_label(NodeType.EVIDENCE)
        supported_by = _safe_relationship_type(RelationshipType.SUPPORTED_BY)
        part_of = _safe_relationship_type(RelationshipType.PART_OF)

        document_identity = evidence.document_version_id or evidence.source_document_id
        document_graph_key = _stable_graph_key(scope, "source_document", document_identity)
        chunk_graph_key = _stable_graph_key(scope, "source_chunk", evidence.source_chunk_id)
        evidence_graph_key = _evidence_graph_key(
            scope,
            claim_kind=claim_kind,
            claim_candidate_id=claim_candidate_id,
            evidence=evidence,
        )
        parameters = {
            "course_id": scope.course_id,
            "curriculum_edition_id": scope.curriculum_edition_id,
            "claim_graph_key": claim_graph_key,
            "claim_kind": claim_kind,
            "claim_candidate_id": claim_candidate_id,
            "document_graph_key": document_graph_key,
            "source_document_id": evidence.source_document_id,
            "document_version_id": evidence.document_version_id,
            "source_file": evidence.source_file,
            "document_sha256": evidence.document_sha256,
            "chunk_graph_key": chunk_graph_key,
            "source_chunk_id": evidence.source_chunk_id,
            "chunk_checksum": evidence.chunk_checksum,
            "chapter": evidence.chapter,
            "section_path_json": _canonical_json(list(evidence.section_path)),
            "page_number": evidence.page_number,
            "page_label": evidence.page_label,
            "slide_number": evidence.slide_number,
            "locator_type": evidence.locator_type,
            "locator_start": evidence.locator_start,
            "locator_end": evidence.locator_end,
            "evidence_graph_key": evidence_graph_key,
            "quote": evidence.quote,
            "quote_start": evidence.quote_start,
            "quote_end": evidence.quote_end,
            "claim_support_graph_key": _stable_graph_key(
                scope,
                "claim_support",
                f"{claim_kind}:{claim_candidate_id}:{evidence_graph_key}",
            ),
            "evidence_support_graph_key": _stable_graph_key(
                scope, "evidence_support", evidence_graph_key
            ),
            "chunk_document_graph_key": _stable_graph_key(
                scope,
                "chunk_document",
                f"{evidence.source_chunk_id}:{document_identity}",
            ),
        }
        # SourceDocument/SourceChunk are immutable published pointers. Evidence
        # is claim-specific and approved by the same PostgreSQL review decision
        # that authorized the claim projection.
        query = f"""
            MATCH (claim:GraphEntity {{graph_key: $claim_graph_key}})
            WHERE claim.course_id = $course_id
              AND claim.curriculum_edition_id = $curriculum_edition_id
              AND claim.status = 'approved'
            MERGE (document:ProvenanceEntity:{document_label}
                   {{graph_key: $document_graph_key}})
            SET document.course_id = $course_id,
                document.curriculum_edition_id = $curriculum_edition_id,
                document.node_type = '{document_label}',
                document.source_document_id = $source_document_id,
                document.document_version_id = $document_version_id,
                document.source_file = $source_file,
                document.document_sha256 = $document_sha256,
                document.status = 'published'
            MERGE (chunk:ProvenanceEntity:{chunk_label}
                   {{graph_key: $chunk_graph_key}})
            SET chunk.course_id = $course_id,
                chunk.curriculum_edition_id = $curriculum_edition_id,
                chunk.node_type = '{chunk_label}',
                chunk.source_chunk_id = $source_chunk_id,
                chunk.chunk_checksum = $chunk_checksum,
                chunk.chapter = $chapter,
                chunk.section_path_json = $section_path_json,
                chunk.page_number = $page_number,
                chunk.page_label = $page_label,
                chunk.slide_number = $slide_number,
                chunk.locator_type = $locator_type,
                chunk.locator_start = $locator_start,
                chunk.locator_end = $locator_end,
                chunk.status = 'published'
            MERGE (evidence:ProvenanceEntity:{evidence_label}
                   {{graph_key: $evidence_graph_key}})
            SET evidence.course_id = $course_id,
                evidence.curriculum_edition_id = $curriculum_edition_id,
                evidence.node_type = '{evidence_label}',
                evidence.claim_kind = $claim_kind,
                evidence.claim_candidate_id = $claim_candidate_id,
                evidence.source_document_id = $source_document_id,
                evidence.source_chunk_id = $source_chunk_id,
                evidence.quote = $quote,
                evidence.quote_start = $quote_start,
                evidence.quote_end = $quote_end,
                evidence.verified_at_review = true,
                evidence.status = 'approved'
            MERGE (claim)-[claim_support:{supported_by}
                   {{graph_key: $claim_support_graph_key}}]->(evidence)
            SET claim_support.course_id = $course_id,
                claim_support.curriculum_edition_id = $curriculum_edition_id,
                claim_support.claim_kind = $claim_kind,
                claim_support.claim_candidate_id = $claim_candidate_id,
                claim_support.status = 'approved'
            MERGE (evidence)-[evidence_support:{supported_by}
                   {{graph_key: $evidence_support_graph_key}}]->(chunk)
            SET evidence_support.course_id = $course_id,
                evidence_support.curriculum_edition_id = $curriculum_edition_id,
                evidence_support.status = 'approved'
            MERGE (chunk)-[chunk_document:{part_of}
                   {{graph_key: $chunk_document_graph_key}}]->(document)
            SET chunk_document.course_id = $course_id,
                chunk_document.curriculum_edition_id = $curriculum_edition_id,
                chunk_document.status = 'published'
        """
        result = await tx.run(query, **parameters)
        await result.consume()
        return evidence_graph_key

    async def _remove_stale_claim_evidence_tx(
        self,
        tx: Any,
        *,
        scope: GraphScope,
        claim_graph_key: str,
        claim_kind: Literal["node", "relationship"],
        claim_candidate_id: str,
        retained_evidence_keys: Sequence[str],
    ) -> None:
        supported_by = _safe_relationship_type(RelationshipType.SUPPORTED_BY)
        evidence_label = _safe_node_label(NodeType.EVIDENCE)
        result = await tx.run(
            f"""
            MATCH (claim:GraphEntity)-[support:{supported_by}]->
                  (evidence:ProvenanceEntity:{evidence_label})
            WHERE support.claim_kind = $claim_kind
              AND support.claim_candidate_id = $claim_candidate_id
              AND claim.course_id = $course_id
              AND claim.curriculum_edition_id = $curriculum_edition_id
              AND (claim.graph_key <> $claim_graph_key
                   OR NOT (evidence.graph_key IN $retained_evidence_keys))
            DETACH DELETE evidence
            """,
            claim_graph_key=claim_graph_key,
            claim_kind=claim_kind,
            claim_candidate_id=claim_candidate_id,
            retained_evidence_keys=list(retained_evidence_keys),
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
        )
        await result.consume()

    async def ensure_schema(self) -> None:
        queries = [
            (
                "CREATE CONSTRAINT quantum_graph_entity_key IF NOT EXISTS "
                "FOR (n:GraphEntity) REQUIRE n.graph_key IS UNIQUE"
            ),
            (
                "CREATE INDEX quantum_graph_scope IF NOT EXISTS "
                "FOR (n:GraphEntity) ON "
                "(n.course_id, n.curriculum_edition_id, n.status)"
            ),
            (
                "CREATE CONSTRAINT quantum_provenance_entity_key IF NOT EXISTS "
                "FOR (n:ProvenanceEntity) REQUIRE n.graph_key IS UNIQUE"
            ),
            (
                "CREATE INDEX quantum_provenance_scope IF NOT EXISTS "
                "FOR (n:ProvenanceEntity) ON "
                "(n.course_id, n.curriculum_edition_id, n.status)"
            ),
        ]
        for relationship_type in RelationshipType:
            safe_type = _safe_relationship_type(relationship_type)
            queries.append(
                f"CREATE CONSTRAINT quantum_graph_rel_{safe_type.lower()}_key "
                f"IF NOT EXISTS FOR ()-[r:{safe_type}]-() "
                "REQUIRE r.graph_key IS UNIQUE"
            )

        async with self._session() as session:
            for query in queries:
                result = await session.run(query)
                await result.consume()

    async def sync_node(self, node: ApprovedGraphNode) -> None:
        if node.status != "approved":  # defense even against model_construct()
            raise GraphInvariantError("only PostgreSQL-approved nodes may be synced")
        label = _safe_node_label(node.node_type)
        removable_labels = ":".join(sorted(NODE_LABEL_WHITELIST))
        params = _node_parameters(node)

        async def work(tx: Any) -> None:
            existing_result = await tx.run(
                "MATCH (n:GraphEntity {graph_key: $graph_key}) RETURN n.node_type AS node_type",
                graph_key=params["graph_key"],
            )
            existing = await existing_result.single()
            if existing is not None and existing["node_type"] != node.node_type.value:
                raise GraphInvariantError(
                    "a projected candidate id cannot change ontology node type"
                )

            query = f"""
                MERGE (n:GraphEntity {{graph_key: $graph_key}})
                REMOVE n:{removable_labels}
                SET n:{label}
                SET n.candidate_id = $candidate_id,
                    n.course_id = $course_id,
                    n.curriculum_edition_id = $curriculum_edition_id,
                    n.node_type = $node_type,
                    n.canonical_key = $canonical_key,
                    n.label = $label,
                    n.description = $description,
                    n.properties_json = $properties_json,
                    n.evidence_json = $evidence_json,
                    n.status = $status,
                    n.review_decision_id = $review_decision_id,
                    n.review_revision = $review_revision,
                    n.created_at = coalesce(n.created_at, datetime()),
                    n.updated_at = datetime()
                RETURN n.candidate_id AS candidate_id
            """
            result = await tx.run(query, **params)
            if await result.single() is None:
                raise GraphStoreError("Neo4j did not return the synced node")
            retained_evidence_keys = [
                await self._sync_evidence_chain_tx(
                    tx,
                    scope=node.scope,
                    claim_graph_key=params["graph_key"],
                    claim_kind="node",
                    claim_candidate_id=node.candidate_id,
                    evidence=evidence,
                )
                for evidence in node.evidence
            ]
            await self._remove_stale_claim_evidence_tx(
                tx,
                scope=node.scope,
                claim_graph_key=params["graph_key"],
                claim_kind="node",
                claim_candidate_id=node.candidate_id,
                retained_evidence_keys=retained_evidence_keys,
            )

        async with self._session() as session:
            await session.execute_write(work)

    async def sync_relationship(self, relationship: ApprovedGraphRelationship) -> None:
        if relationship.status != "approved":
            raise GraphInvariantError("only PostgreSQL-approved relationships may be synced")
        rel_type = _safe_relationship_type(relationship.relationship_type)
        params = _relationship_parameters(relationship)

        async def work(tx: Any) -> None:
            # A teacher edit may change endpoints or even relation type while
            # preserving candidate lineage. Remove only a conflicting old
            # projection with the same scoped graph key, then MERGE the final
            # state. Managed transaction retries remain idempotent.
            cleanup_result = await tx.run(
                """
                MATCH (old_source:GraphEntity)-[old]->(old_target:GraphEntity)
                WHERE old.graph_key = $graph_key
                  AND (
                    type(old) <> $relationship_type
                    OR old_source.graph_key <> $source_graph_key
                    OR old_target.graph_key <> $target_graph_key
                  )
                DELETE old
                """,
                **params,
            )
            await cleanup_result.consume()

            query = f"""
                MATCH (source:GraphEntity {{graph_key: $source_graph_key}})
                MATCH (target:GraphEntity {{graph_key: $target_graph_key}})
                WHERE source.course_id = $course_id
                  AND source.curriculum_edition_id = $curriculum_edition_id
                  AND source.status = 'approved'
                  AND source.node_type = $source_node_type
                  AND target.course_id = $course_id
                  AND target.curriculum_edition_id = $curriculum_edition_id
                  AND target.status = 'approved'
                  AND target.node_type = $target_node_type
                MERGE (source)-[r:{rel_type} {{graph_key: $graph_key}}]->(target)
                SET r.candidate_id = $candidate_id,
                    r.course_id = $course_id,
                    r.curriculum_edition_id = $curriculum_edition_id,
                    r.relationship_type = $relationship_type,
                    r.source_candidate_id = $source_candidate_id,
                    r.target_candidate_id = $target_candidate_id,
                    r.source_node_type = $source_node_type,
                    r.target_node_type = $target_node_type,
                    r.properties_json = $properties_json,
                    r.evidence_json = $evidence_json,
                    r.status = $status,
                    r.review_decision_id = $review_decision_id,
                    r.review_revision = $review_revision,
                    r.created_at = coalesce(r.created_at, datetime()),
                    r.updated_at = datetime()
                RETURN r.candidate_id AS candidate_id
            """
            result = await tx.run(query, **params)
            if await result.single() is None:
                raise GraphNotFoundError(
                    "approved relationship endpoints are missing, unapproved, or mistyped"
                )
            retained_evidence_keys = [
                await self._sync_evidence_chain_tx(
                    tx,
                    scope=relationship.scope,
                    claim_graph_key=params["source_graph_key"],
                    claim_kind="relationship",
                    claim_candidate_id=relationship.candidate_id,
                    evidence=evidence,
                )
                for evidence in relationship.evidence
            ]
            await self._remove_stale_claim_evidence_tx(
                tx,
                scope=relationship.scope,
                claim_graph_key=params["source_graph_key"],
                claim_kind="relationship",
                claim_candidate_id=relationship.candidate_id,
                retained_evidence_keys=retained_evidence_keys,
            )

        async with self._session() as session:
            await session.execute_write(work)

    async def delete_node(self, scope: GraphScope, candidate_id: str) -> bool:
        graph_key = _stable_graph_key(scope, "node", candidate_id)
        candidate_id = _strip_required(candidate_id)

        async def work(tx: Any) -> bool:
            evidence_result = await tx.run(
                """
                MATCH (n:GraphEntity {graph_key: $graph_key})
                      -[support:SUPPORTED_BY]->
                      (evidence:ProvenanceEntity:Evidence)
                WHERE n.course_id = $course_id
                  AND n.curriculum_edition_id = $curriculum_edition_id
                  AND support.claim_kind = 'node'
                  AND support.claim_candidate_id = $candidate_id
                RETURN evidence.graph_key AS evidence_graph_key
                """,
                graph_key=graph_key,
                candidate_id=candidate_id,
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
            )
            evidence_rows = await evidence_result.data()
            delete_result = await tx.run(
                """
                MATCH (n:GraphEntity {graph_key: $graph_key})
                WHERE n.course_id = $course_id
                  AND n.curriculum_edition_id = $curriculum_edition_id
                WITH n, n.candidate_id AS candidate_id
                DETACH DELETE n
                RETURN candidate_id
                """,
                graph_key=graph_key,
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
            )
            deleted = await delete_result.single() is not None
            if deleted and evidence_rows:
                cleanup_result = await tx.run(
                    """
                    MATCH (evidence:ProvenanceEntity:Evidence)
                    WHERE evidence.graph_key IN $evidence_graph_keys
                    DETACH DELETE evidence
                    """,
                    evidence_graph_keys=[row["evidence_graph_key"] for row in evidence_rows],
                )
                await cleanup_result.consume()
            return deleted

        async with self._session() as session:
            return bool(await session.execute_write(work))

    async def delete_relationship(self, scope: GraphScope, candidate_id: str) -> bool:
        graph_key = _stable_graph_key(scope, "relationship", candidate_id)
        candidate_id = _strip_required(candidate_id)

        async def work(tx: Any) -> bool:
            result = await tx.run(
                """
                MATCH (source:GraphEntity)-[r]->()
                WHERE r.graph_key = $graph_key
                  AND r.course_id = $course_id
                  AND r.curriculum_edition_id = $curriculum_edition_id
                WITH source, r, r.candidate_id AS deleted_candidate_id
                DELETE r
                RETURN source.graph_key AS source_graph_key, deleted_candidate_id
                """,
                graph_key=graph_key,
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
            )
            record = await result.single()
            if record is None:
                return False
            evidence_result = await tx.run(
                """
                MATCH (source:GraphEntity {graph_key: $source_graph_key})
                      -[support:SUPPORTED_BY]->
                      (evidence:ProvenanceEntity:Evidence)
                WHERE support.claim_kind = 'relationship'
                  AND support.claim_candidate_id = $candidate_id
                DETACH DELETE evidence
                """,
                source_graph_key=record["source_graph_key"],
                candidate_id=candidate_id,
            )
            await evidence_result.consume()
            return True

        async with self._session() as session:
            return bool(await session.execute_write(work))

    async def merge_nodes(
        self,
        scope: GraphScope,
        survivor_candidate_id: str,
        duplicate_candidate_ids: Sequence[str],
    ) -> None:
        survivor_candidate_id = _strip_required(survivor_candidate_id)
        duplicate_ids = sorted(
            {
                _strip_required(candidate_id)
                for candidate_id in duplicate_candidate_ids
                if candidate_id.strip() != survivor_candidate_id
            }
        )
        if not duplicate_ids:
            return
        survivor_key = _stable_graph_key(scope, "node", survivor_candidate_id)
        duplicate_keys = [
            _stable_graph_key(scope, "node", candidate_id) for candidate_id in duplicate_ids
        ]

        async def work(tx: Any) -> None:
            node_result = await tx.run(
                """
                MATCH (n:GraphEntity)
                WHERE n.graph_key IN $graph_keys
                  AND n.course_id = $course_id
                  AND n.curriculum_edition_id = $curriculum_edition_id
                  AND n.status = 'approved'
                RETURN properties(n) AS node
                """,
                graph_keys=[survivor_key, *duplicate_keys],
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
            )
            rows = await node_result.data()
            node_properties = [row["node"] for row in rows]
            survivor = next(
                (
                    item
                    for item in node_properties
                    if item.get("candidate_id") == survivor_candidate_id
                ),
                None,
            )
            if survivor is None:
                raise GraphNotFoundError("approved survivor node does not exist in scope")
            present_duplicate_keys = {
                item["graph_key"]
                for item in node_properties
                if item.get("candidate_id") in duplicate_ids
            }
            if not present_duplicate_keys:
                return  # idempotent replay after a successful merge
            if any(
                item.get("node_type") != survivor.get("node_type")
                for item in node_properties
                if item.get("graph_key") in present_duplicate_keys
            ):
                raise GraphInvariantError("only nodes of the same ontology type may merge")

            relation_result = await tx.run(
                """
                MATCH (source:GraphEntity)-[r]->(target:GraphEntity)
                WHERE (source.graph_key IN $duplicate_keys
                       OR target.graph_key IN $duplicate_keys)
                  AND source.course_id = $course_id
                  AND source.curriculum_edition_id = $curriculum_edition_id
                  AND source.status = 'approved'
                  AND target.course_id = $course_id
                  AND target.curriculum_edition_id = $curriculum_edition_id
                  AND target.status = 'approved'
                  AND r.course_id = $course_id
                  AND r.curriculum_edition_id = $curriculum_edition_id
                  AND r.status = 'approved'
                RETURN source.graph_key AS source_graph_key,
                       target.graph_key AS target_graph_key,
                       source.node_type AS source_node_type,
                       target.node_type AS target_node_type,
                       type(r) AS relationship_type,
                       properties(r) AS relationship
                """,
                duplicate_keys=list(present_duplicate_keys),
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
            )
            relation_rows = await relation_result.data()

            delete_relations_result = await tx.run(
                """
                MATCH (duplicate:GraphEntity)-[r]-()
                WHERE duplicate.graph_key IN $duplicate_keys
                DELETE r
                """,
                duplicate_keys=list(present_duplicate_keys),
            )
            await delete_relations_result.consume()

            for row in relation_rows:
                rel_type = _safe_relationship_type(row["relationship_type"])
                source_key = (
                    survivor_key
                    if row["source_graph_key"] in present_duplicate_keys
                    else row["source_graph_key"]
                )
                target_key = (
                    survivor_key
                    if row["target_graph_key"] in present_duplicate_keys
                    else row["target_graph_key"]
                )
                source_type = (
                    survivor["node_type"] if source_key == survivor_key else row["source_node_type"]
                )
                target_type = (
                    survivor["node_type"] if target_key == survivor_key else row["target_node_type"]
                )
                if not is_allowed_triple(source_type, rel_type, target_type):
                    raise GraphInvariantError(
                        "node merge would create an ontology-invalid relationship"
                    )
                relationship_properties = dict(row["relationship"])
                if source_key == survivor_key:
                    relationship_properties["source_candidate_id"] = survivor_candidate_id
                    relationship_properties["source_node_type"] = survivor["node_type"]
                if target_key == survivor_key:
                    relationship_properties["target_candidate_id"] = survivor_candidate_id
                    relationship_properties["target_node_type"] = survivor["node_type"]
                recreate_result = await tx.run(
                    f"""
                    MATCH (source:GraphEntity {{graph_key: $source_graph_key}})
                    MATCH (target:GraphEntity {{graph_key: $target_graph_key}})
                    MERGE (source)-[r:{rel_type} {{graph_key: $relationship_graph_key}}]->(target)
                    SET r = $relationship_properties
                    """,
                    source_graph_key=source_key,
                    target_graph_key=target_key,
                    relationship_graph_key=relationship_properties["graph_key"],
                    relationship_properties=relationship_properties,
                )
                await recreate_result.consume()
                projected_relationship = _relationship_from_properties(
                    relationship_properties, rel_type
                )
                retained_evidence_keys = [
                    await self._sync_evidence_chain_tx(
                        tx,
                        scope=scope,
                        claim_graph_key=source_key,
                        claim_kind="relationship",
                        claim_candidate_id=projected_relationship.candidate_id,
                        evidence=evidence,
                    )
                    for evidence in projected_relationship.evidence
                ]
                await self._remove_stale_claim_evidence_tx(
                    tx,
                    scope=scope,
                    claim_graph_key=source_key,
                    claim_kind="relationship",
                    claim_candidate_id=projected_relationship.candidate_id,
                    retained_evidence_keys=retained_evidence_keys,
                )

            delete_nodes_result = await tx.run(
                """
                MATCH (duplicate:GraphEntity)
                WHERE duplicate.graph_key IN $duplicate_keys
                DETACH DELETE duplicate
                """,
                duplicate_keys=list(present_duplicate_keys),
            )
            await delete_nodes_result.consume()
            update_result = await tx.run(
                """
                MATCH (survivor:GraphEntity {graph_key: $survivor_key})
                SET survivor.merged_candidate_ids_json = $merged_ids_json,
                    survivor.updated_at = datetime()
                """,
                survivor_key=survivor_key,
                merged_ids_json=_canonical_json(duplicate_ids),
            )
            await update_result.consume()

        async with self._session() as session:
            await session.execute_write(work)

    async def search_nodes(
        self,
        scope: GraphScope,
        query: str,
        *,
        node_types: Sequence[NodeType] | None = None,
        limit: int = 20,
    ) -> list[GraphSearchHit]:
        query = _strip_required(query)
        limit = _validate_limit(limit)
        safe_types = (
            [_safe_node_label(node_type) for node_type in node_types]
            if node_types is not None
            else None
        )
        cypher = """
            MATCH (n:GraphEntity)
            WHERE n.course_id = $course_id
              AND n.curriculum_edition_id = $curriculum_edition_id
              AND n.status = 'approved'
              AND ($node_types IS NULL OR n.node_type IN $node_types)
              AND (
                toLower(n.label) CONTAINS toLower($search_text)
                OR toLower(n.canonical_key) CONTAINS toLower($search_text)
                OR toLower(coalesce(n.description, '')) CONTAINS toLower($search_text)
              )
            WITH n,
                 CASE
                   WHEN toLower(n.label) = toLower($search_text) THEN 10.0
                   WHEN toLower(n.label) STARTS WITH toLower($search_text) THEN 5.0
                   WHEN toLower(n.canonical_key) = toLower($search_text) THEN 4.0
                   ELSE 1.0
                 END AS score
            RETURN properties(n) AS node, score
            ORDER BY score DESC, n.label ASC
            LIMIT $limit
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
                search_text=query,
                node_types=safe_types,
                limit=limit,
            )
            rows = await result.data()
        return [
            GraphSearchHit(node=_node_from_properties(row["node"]), score=row["score"])
            for row in rows
        ]

    async def get_subgraph(
        self,
        scope: GraphScope,
        root_candidate_id: str,
        *,
        max_depth: int = 2,
        limit: int = 100,
    ) -> GraphSubgraph:
        max_depth = _validate_depth(max_depth)
        limit = _validate_limit(limit)
        root_candidate_id = _strip_required(root_candidate_id)
        root_key = _stable_graph_key(scope, "node", root_candidate_id)
        cypher = f"""
            MATCH p=(root:GraphEntity {{graph_key: $root_key}})
                    -[*0..{max_depth}]-(neighbor:GraphEntity)
            WHERE root.course_id = $course_id
              AND root.curriculum_edition_id = $curriculum_edition_id
              AND root.status = 'approved'
              AND all(node IN nodes(p) WHERE
                    node:GraphEntity
                    AND node.course_id = $course_id
                    AND node.curriculum_edition_id = $curriculum_edition_id
                    AND node.status = 'approved')
              AND all(rel IN relationships(p) WHERE
                    rel.course_id = $course_id
                    AND rel.curriculum_edition_id = $curriculum_edition_id
                    AND rel.status = 'approved')
            RETURN [node IN nodes(p) | properties(node)] AS nodes,
                   [rel IN relationships(p) |
                    properties(rel) + {{relationship_type: type(rel)}}] AS relationships
            LIMIT $path_limit
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                root_key=root_key,
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
                path_limit=min(limit * 5, 1000),
            )
            rows = await result.data()
        if not rows:
            raise GraphNotFoundError("approved root node does not exist in scope")

        nodes_by_id: dict[str, ApprovedGraphNode] = {}
        relationships_by_id: dict[str, ApprovedGraphRelationship] = {}
        for row in rows:
            for raw_node in row["nodes"]:
                node = _node_from_properties(raw_node)
                nodes_by_id.setdefault(node.candidate_id, node)
            for raw_relationship in row["relationships"]:
                relationship = _relationship_from_properties(
                    raw_relationship, raw_relationship["relationship_type"]
                )
                relationships_by_id.setdefault(relationship.candidate_id, relationship)

        ordered_nodes = list(nodes_by_id.values())[:limit]
        included_ids = {node.candidate_id for node in ordered_nodes}
        ordered_relationships = [
            relationship
            for relationship in relationships_by_id.values()
            if relationship.source_candidate_id in included_ids
            and relationship.target_candidate_id in included_ids
        ]
        return GraphSubgraph(
            scope=scope,
            root_candidate_id=root_candidate_id,
            nodes=tuple(ordered_nodes),
            relationships=tuple(ordered_relationships),
        )

    async def get_prerequisite_paths(
        self,
        scope: GraphScope,
        target_candidate_id: str,
        *,
        max_depth: int = 4,
        limit: int = 20,
    ) -> list[PrerequisitePath]:
        max_depth = _validate_depth(max_depth)
        limit = _validate_limit(limit)
        target_key = _stable_graph_key(scope, "node", target_candidate_id)
        cypher = f"""
            MATCH p=(prerequisite:GraphEntity)-[:PREREQUISITE_OF*1..{max_depth}]->
                    (target:GraphEntity {{graph_key: $target_key}})
            WHERE target.course_id = $course_id
              AND target.curriculum_edition_id = $curriculum_edition_id
              AND target.status = 'approved'
              AND all(node IN nodes(p) WHERE
                    node.course_id = $course_id
                    AND node.curriculum_edition_id = $curriculum_edition_id
                    AND node.status = 'approved')
              AND all(rel IN relationships(p) WHERE
                    rel.course_id = $course_id
                    AND rel.curriculum_edition_id = $curriculum_edition_id
                    AND rel.status = 'approved')
            RETURN [node IN nodes(p) | properties(node)] AS nodes,
                   [rel IN relationships(p) |
                    properties(rel) + {{relationship_type: type(rel)}}] AS relationships
            ORDER BY size(relationships(p)) ASC
            LIMIT $limit
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                target_key=target_key,
                course_id=scope.course_id,
                curriculum_edition_id=scope.curriculum_edition_id,
                limit=limit,
            )
            rows = await result.data()
        return [
            PrerequisitePath(
                nodes=tuple(_node_from_properties(node) for node in row["nodes"]),
                relationships=tuple(
                    _relationship_from_properties(rel, rel["relationship_type"])
                    for rel in row["relationships"]
                ),
            )
            for row in rows
        ]

    async def close(self) -> None:
        if self._owns_driver:
            await self._driver.close()


class InMemoryGraphStore:
    """Behavioral test double with the same review/scope/ontology invariants."""

    def __init__(self) -> None:
        self._nodes: dict[str, ApprovedGraphNode] = {}
        self._relationships: dict[str, ApprovedGraphRelationship] = {}

    async def ensure_schema(self) -> None:
        return None

    async def sync_node(self, node: ApprovedGraphNode) -> None:
        if node.status != "approved":
            raise GraphInvariantError("only PostgreSQL-approved nodes may be synced")
        _safe_node_label(node.node_type)
        key = _stable_graph_key(node.scope, "node", node.candidate_id)
        existing = self._nodes.get(key)
        if existing is not None and existing.node_type is not node.node_type:
            raise GraphInvariantError("a projected candidate id cannot change ontology node type")
        self._nodes[key] = node.model_copy(deep=True)

    async def sync_relationship(self, relationship: ApprovedGraphRelationship) -> None:
        if relationship.status != "approved":
            raise GraphInvariantError("only PostgreSQL-approved relationships may be synced")
        _safe_relationship_type(relationship.relationship_type)
        source = self._nodes.get(
            _stable_graph_key(relationship.scope, "node", relationship.source_candidate_id)
        )
        target = self._nodes.get(
            _stable_graph_key(relationship.scope, "node", relationship.target_candidate_id)
        )
        if source is None or target is None:
            raise GraphNotFoundError("approved relationship endpoints are missing")
        if (
            source.scope != relationship.scope
            or target.scope != relationship.scope
            or source.node_type is not relationship.source_node_type
            or target.node_type is not relationship.target_node_type
        ):
            raise GraphInvariantError("relationship endpoints do not match approved nodes")
        key = _stable_graph_key(relationship.scope, "relationship", relationship.candidate_id)
        self._relationships[key] = relationship.model_copy(deep=True)

    async def delete_node(self, scope: GraphScope, candidate_id: str) -> bool:
        key = _stable_graph_key(scope, "node", candidate_id)
        removed = self._nodes.pop(key, None)
        if removed is None:
            return False
        incident_keys = [
            rel_key
            for rel_key, relation in self._relationships.items()
            if relation.scope == scope
            and candidate_id in (relation.source_candidate_id, relation.target_candidate_id)
        ]
        for rel_key in incident_keys:
            del self._relationships[rel_key]
        return True

    async def delete_relationship(self, scope: GraphScope, candidate_id: str) -> bool:
        key = _stable_graph_key(scope, "relationship", candidate_id)
        return self._relationships.pop(key, None) is not None

    async def merge_nodes(
        self,
        scope: GraphScope,
        survivor_candidate_id: str,
        duplicate_candidate_ids: Sequence[str],
    ) -> None:
        survivor_key = _stable_graph_key(scope, "node", survivor_candidate_id)
        survivor = self._nodes.get(survivor_key)
        if survivor is None:
            raise GraphNotFoundError("approved survivor node does not exist in scope")
        duplicate_ids = {
            _strip_required(candidate_id)
            for candidate_id in duplicate_candidate_ids
            if candidate_id.strip() != survivor_candidate_id
        }
        present_duplicates = {
            candidate_id: self._nodes[_stable_graph_key(scope, "node", candidate_id)]
            for candidate_id in duplicate_ids
            if _stable_graph_key(scope, "node", candidate_id) in self._nodes
        }
        if any(node.node_type is not survivor.node_type for node in present_duplicates.values()):
            raise GraphInvariantError("only nodes of the same ontology type may merge")
        if not present_duplicates:
            return

        for key, relation in list(self._relationships.items()):
            if relation.scope != scope:
                continue
            source_id = (
                survivor_candidate_id
                if relation.source_candidate_id in present_duplicates
                else relation.source_candidate_id
            )
            target_id = (
                survivor_candidate_id
                if relation.target_candidate_id in present_duplicates
                else relation.target_candidate_id
            )
            if (source_id, target_id) == (
                relation.source_candidate_id,
                relation.target_candidate_id,
            ):
                continue
            updated = relation.model_copy(
                update={
                    "source_candidate_id": source_id,
                    "target_candidate_id": target_id,
                    "source_node_type": (
                        survivor.node_type
                        if source_id == survivor_candidate_id
                        else relation.source_node_type
                    ),
                    "target_node_type": (
                        survivor.node_type
                        if target_id == survivor_candidate_id
                        else relation.target_node_type
                    ),
                },
                deep=True,
            )
            if not is_allowed_triple(
                updated.source_node_type,
                updated.relationship_type,
                updated.target_node_type,
            ):
                raise GraphInvariantError(
                    "node merge would create an ontology-invalid relationship"
                )
            self._relationships[key] = updated

        for candidate_id in present_duplicates:
            del self._nodes[_stable_graph_key(scope, "node", candidate_id)]

    async def search_nodes(
        self,
        scope: GraphScope,
        query: str,
        *,
        node_types: Sequence[NodeType] | None = None,
        limit: int = 20,
    ) -> list[GraphSearchHit]:
        normalized_query = _strip_required(query).casefold()
        limit = _validate_limit(limit)
        allowed_types = set(node_types) if node_types is not None else None
        hits: list[GraphSearchHit] = []
        for node in self._nodes.values():
            if node.scope != scope or node.status != "approved":
                continue
            if allowed_types is not None and node.node_type not in allowed_types:
                continue
            label = node.label.casefold()
            canonical_key = node.canonical_key.casefold()
            description = (node.description or "").casefold()
            if not any(normalized_query in field for field in (label, canonical_key, description)):
                continue
            if label == normalized_query:
                score = 10.0
            elif label.startswith(normalized_query):
                score = 5.0
            elif canonical_key == normalized_query:
                score = 4.0
            else:
                score = 1.0
            hits.append(GraphSearchHit(node=node.model_copy(deep=True), score=score))
        hits.sort(key=lambda item: (-item.score, item.node.label))
        return hits[:limit]

    async def get_subgraph(
        self,
        scope: GraphScope,
        root_candidate_id: str,
        *,
        max_depth: int = 2,
        limit: int = 100,
    ) -> GraphSubgraph:
        max_depth = _validate_depth(max_depth)
        limit = _validate_limit(limit)
        root_key = _stable_graph_key(scope, "node", root_candidate_id)
        root = self._nodes.get(root_key)
        if root is None or root.status != "approved":
            raise GraphNotFoundError("approved root node does not exist in scope")

        nodes_by_id: dict[str, ApprovedGraphNode] = {root.candidate_id: root}
        relationships_by_id: dict[str, ApprovedGraphRelationship] = {}
        queue: deque[tuple[str, int]] = deque([(root.candidate_id, 0)])
        while queue and len(nodes_by_id) < limit:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for relation in self._relationships.values():
                if relation.scope != scope or relation.status != "approved":
                    continue
                if relation.source_candidate_id == current_id:
                    other_id = relation.target_candidate_id
                elif relation.target_candidate_id == current_id:
                    other_id = relation.source_candidate_id
                else:
                    continue
                other = self._nodes.get(_stable_graph_key(scope, "node", other_id))
                if other is None or other.status != "approved":
                    continue
                if other_id not in nodes_by_id:
                    if len(nodes_by_id) >= limit:
                        break
                    nodes_by_id[other_id] = other
                    queue.append((other_id, depth + 1))
                relationships_by_id[relation.candidate_id] = relation

        included_ids = set(nodes_by_id)
        relationships = tuple(
            relation.model_copy(deep=True)
            for relation in relationships_by_id.values()
            if relation.source_candidate_id in included_ids
            and relation.target_candidate_id in included_ids
        )
        return GraphSubgraph(
            scope=scope,
            root_candidate_id=root_candidate_id,
            nodes=tuple(node.model_copy(deep=True) for node in nodes_by_id.values()),
            relationships=relationships,
        )

    async def get_prerequisite_paths(
        self,
        scope: GraphScope,
        target_candidate_id: str,
        *,
        max_depth: int = 4,
        limit: int = 20,
    ) -> list[PrerequisitePath]:
        max_depth = _validate_depth(max_depth)
        limit = _validate_limit(limit)
        target = self._nodes.get(_stable_graph_key(scope, "node", target_candidate_id))
        if target is None or target.status != "approved":
            raise GraphNotFoundError("approved target node does not exist in scope")

        paths: list[PrerequisitePath] = []
        queue: deque[tuple[list[ApprovedGraphNode], list[ApprovedGraphRelationship]]] = deque(
            [([target], [])]
        )
        while queue and len(paths) < limit:
            node_path, relation_path = queue.popleft()
            current = node_path[0]
            if len(relation_path) >= max_depth:
                continue
            for relation in self._relationships.values():
                if (
                    relation.scope != scope
                    or relation.status != "approved"
                    or relation.relationship_type is not RelationshipType.PREREQUISITE_OF
                    or relation.target_candidate_id != current.candidate_id
                ):
                    continue
                prerequisite = self._nodes.get(
                    _stable_graph_key(scope, "node", relation.source_candidate_id)
                )
                if prerequisite is None or prerequisite.status != "approved":
                    continue
                if any(node.candidate_id == prerequisite.candidate_id for node in node_path):
                    continue
                next_nodes = [prerequisite, *node_path]
                next_relationships = [relation, *relation_path]
                paths.append(
                    PrerequisitePath(
                        nodes=tuple(node.model_copy(deep=True) for node in next_nodes),
                        relationships=tuple(
                            item.model_copy(deep=True) for item in next_relationships
                        ),
                    )
                )
                if len(paths) >= limit:
                    break
                queue.append((next_nodes, next_relationships))
        return paths

    async def close(self) -> None:
        return None
