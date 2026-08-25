"""Student-safe knowledge-graph explorer.

Neo4j is only an approved read projection.  It is never sufficient authority
for a student response: every returned node and relationship is independently
re-grounded through PostgreSQL's ``student_visible_chunks`` view and an exact,
grounded relational ``Evidence`` row.  A projected entity with stale, missing,
cross-scope, or hash-mismatched provenance is omitted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantum_agent.knowledge.evidence_packets import EvidenceKind, EvidenceLocator
from quantum_agent.knowledge.graph_store import (
    ApprovedGraphNode,
    ApprovedGraphRelationship,
    GraphEvidence,
    GraphNotFoundError,
    GraphStore,
)
from quantum_agent.knowledge.ontology import NodeType, RelationshipType
from quantum_agent.knowledge.retrieval import AuthoritativeEvidenceRecord, RetrievalScope

EXPLORER_SEARCH_NODE_TYPES: tuple[NodeType, ...] = (
    NodeType.CHAPTER,
    NodeType.SECTION,
    NodeType.CONCEPT,
    NodeType.PRINCIPLE,
    NodeType.PHYSICAL_SYSTEM,
    NodeType.MATHEMATICAL_OBJECT,
    NodeType.OPERATOR,
    NodeType.QUANTUM_STATE,
    NodeType.APPROXIMATION,
    NodeType.FORMULA,
    NodeType.SYMBOL,
    NodeType.DERIVATION,
    NodeType.EXAMPLE,
    NodeType.EXERCISE,
    NodeType.MISCONCEPTION,
    NodeType.HINT,
    NodeType.EXPERIMENT,
    NodeType.VISUALIZATION,
    NodeType.PROJECT,
)


class GraphExplorerError(RuntimeError):
    """Base error at the student graph-explorer boundary."""


class GraphExplorerUnavailableError(GraphExplorerError):
    """Neo4j or the authoritative relational evidence gate is unavailable."""


class GraphExplorerNotFoundError(GraphExplorerError):
    """The requested approved graph root does not exist in the requested scope."""


class ExplorerWarningCode(StrEnum):
    """Non-sensitive aggregate reasons for omitting graph projection data."""

    SCOPE_MISMATCH = "graph_entity_omitted:scope_mismatch"
    INVALID_ENTITY_ID = "graph_entity_omitted:invalid_identifier"
    INVALID_EVIDENCE_POINTER = "graph_entity_omitted:invalid_evidence_pointer"
    UNPUBLISHED_EVIDENCE = "graph_entity_omitted:unpublished_evidence"
    EVIDENCE_INTEGRITY_MISMATCH = "graph_entity_omitted:evidence_integrity_mismatch"
    NO_VISIBLE_EVIDENCE = "graph_entity_omitted:no_visible_evidence"
    EDGE_ENDPOINT_HIDDEN = "graph_edge_omitted:hidden_endpoint"
    INCOMPLETE_PREREQUISITE_PATH = "prerequisite_path_omitted:incomplete"


class StudentCitationPreview(BaseModel):
    """Original course evidence and immutable provenance exposed to students."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    source_chunk_id: UUID
    source_document_id: UUID
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
    kind: EvidenceKind

    @model_validator(mode="after")
    def validate_exact_authoritative_span(self) -> StudentCitationPreview:
        if self.evidence_char_end > len(self.source_chunk):
            raise ValueError("citation evidence range exceeds source chunk")
        if (
            self.source_chunk[self.evidence_char_start : self.evidence_char_end]
            != self.evidence_snippet
        ):
            raise ValueError("citation snippet is not the exact authoritative span")
        if hashlib.sha256(self.source_chunk.encode("utf-8")).hexdigest() != (
            self.source_chunk_sha256
        ):
            raise ValueError("citation source-chunk hash does not match")
        if hashlib.sha256(self.evidence_snippet.encode("utf-8")).hexdigest() != (
            self.evidence_sha256
        ):
            raise ValueError("citation evidence hash does not match")
        return self

    @classmethod
    def from_record(cls, record: AuthoritativeEvidenceRecord) -> StudentCitationPreview:
        return cls(
            evidence_id=record.evidence_id,
            source_chunk_id=record.chunk_id,
            source_document_id=record.document_id,
            document_version_id=record.document_version_id,
            document_title=record.document_title,
            document_version=record.document_version,
            source_file_name=record.source_file_name,
            source_file_sha256=record.source_file_sha256,
            source_chunk_sha256=record.source_chunk_sha256,
            evidence_sha256=record.evidence_sha256,
            chapter=record.chapter,
            section_path=record.section_path,
            locator=record.locator.model_copy(deep=True),
            source_chunk=record.source_chunk,
            evidence_snippet=record.evidence_snippet,
            evidence_char_start=record.evidence_char_start,
            evidence_char_end=record.evidence_char_end,
            kind=record.kind,
        )


class StudentGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    node_type: NodeType
    canonical_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str | None = None
    aliases: tuple[str, ...] = ()
    formula_latex: str | None = None
    citations: tuple[StudentCitationPreview, ...] = Field(min_length=1)


class StudentGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    source_id: UUID
    target_id: UUID
    relationship_type: RelationshipType
    citations: tuple[StudentCitationPreview, ...] = Field(min_length=1)


class StudentGraphSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node: StudentGraphNode
    score: float = Field(ge=0)


class ConceptSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    query: str = Field(min_length=1)
    results: tuple[StudentGraphSearchHit, ...] = ()
    degraded: bool = False
    warnings: tuple[ExplorerWarningCode, ...] = ()


class StudentSubgraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    root_candidate_id: UUID
    root_visible: bool
    nodes: tuple[StudentGraphNode, ...] = ()
    edges: tuple[StudentGraphEdge, ...] = ()
    degraded: bool = False
    warnings: tuple[ExplorerWarningCode, ...] = ()


class StudentPrerequisitePath(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[StudentGraphNode, ...] = Field(min_length=2)
    edges: tuple[StudentGraphEdge, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ordered_path(self) -> StudentPrerequisitePath:
        if len(self.edges) != len(self.nodes) - 1:
            raise ValueError("a prerequisite path must contain n nodes and n-1 edges")
        for index, edge in enumerate(self.edges):
            if edge.relationship_type is not RelationshipType.PREREQUISITE_OF:
                raise ValueError("a prerequisite path may contain only PREREQUISITE_OF")
            if edge.source_id != self.nodes[index].id or edge.target_id != self.nodes[index + 1].id:
                raise ValueError("prerequisite path edge order does not match its nodes")
        return self


class PrerequisitePathsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    target_candidate_id: UUID
    paths: tuple[StudentPrerequisitePath, ...] = ()
    degraded: bool = False
    warnings: tuple[ExplorerWarningCode, ...] = ()


class StudentEvidenceHydrator(Protocol):
    """Narrow portion of StudentVisibleEvidenceRepository used by this service."""

    async def hydrate(
        self,
        scope: RetrievalScope,
        chunk_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]]: ...


def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


def _sorted_warnings(
    warnings: set[ExplorerWarningCode],
) -> tuple[ExplorerWarningCode, ...]:
    return tuple(sorted(warnings, key=lambda item: item.value))


def _graph_evidence_matches_record(
    evidence: GraphEvidence,
    record: AuthoritativeEvidenceRecord,
    scope: RetrievalScope,
) -> bool:
    document_id = _as_uuid(evidence.source_document_id)
    version_id = (
        _as_uuid(evidence.document_version_id)
        if evidence.document_version_id is not None
        else None
    )
    if document_id is None or version_id is None:
        return False
    if evidence.document_sha256 is None or evidence.chunk_checksum is None:
        return False
    if record.course_id != scope.course_id or record.curriculum_edition_id != (
        scope.curriculum_edition_id
    ):
        return False
    if document_id != record.document_id or version_id != record.document_version_id:
        return False
    if evidence.source_file != record.source_file_name:
        return False
    if evidence.document_sha256.casefold() != record.source_file_sha256:
        return False
    if evidence.chunk_checksum.casefold() != record.source_chunk_sha256:
        return False
    if evidence.quote != record.evidence_snippet:
        return False
    if hashlib.sha256(evidence.quote.encode("utf-8")).hexdigest() != record.evidence_sha256:
        return False
    offsets_present = evidence.quote_start is not None or evidence.quote_end is not None
    if offsets_present and (
        evidence.quote_start != record.evidence_char_start
        or evidence.quote_end != record.evidence_char_end
    ):
        return False
    return True


class GraphExplorerService:
    """Expose a student view only after relational publication re-validation."""

    def __init__(
        self,
        *,
        graph_store: GraphStore | None,
        evidence_repository: StudentEvidenceHydrator,
    ) -> None:
        self._graph_store = graph_store
        self._evidence_repository = evidence_repository

    def _store(self) -> GraphStore:
        if self._graph_store is None:
            raise GraphExplorerUnavailableError("graph projection is unavailable")
        return self._graph_store

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        return limit

    @staticmethod
    def _validate_depth(max_depth: int) -> int:
        if not 1 <= max_depth <= 5:
            raise ValueError("max_depth must be between 1 and 5")
        return max_depth

    @staticmethod
    def _entity_scope_is_valid(
        entity: ApprovedGraphNode | ApprovedGraphRelationship,
        scope: RetrievalScope,
    ) -> bool:
        return entity.status == "approved" and entity.scope == scope.graph_scope()

    async def _hydrate_entities(
        self,
        scope: RetrievalScope,
        entities: Sequence[ApprovedGraphNode | ApprovedGraphRelationship],
        warnings: set[ExplorerWarningCode],
    ) -> dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]]:
        chunk_ids: list[UUID] = []
        for entity in entities:
            if not self._entity_scope_is_valid(entity, scope):
                warnings.add(ExplorerWarningCode.SCOPE_MISMATCH)
                continue
            for evidence in entity.evidence:
                chunk_id = _as_uuid(evidence.source_chunk_id)
                if chunk_id is None:
                    warnings.add(ExplorerWarningCode.INVALID_EVIDENCE_POINTER)
                elif chunk_id not in chunk_ids:
                    chunk_ids.append(chunk_id)
        if not chunk_ids:
            return {}
        try:
            hydrated = await self._evidence_repository.hydrate(scope, chunk_ids)
        except Exception as exc:
            raise GraphExplorerUnavailableError(
                "authoritative graph evidence is unavailable"
            ) from exc

        safe_records: dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]] = {}
        requested = set(chunk_ids)
        for chunk_id, records in hydrated.items():
            if chunk_id not in requested:
                warnings.add(ExplorerWarningCode.SCOPE_MISMATCH)
                continue
            scoped = tuple(
                record
                for record in records
                if record.chunk_id == chunk_id
                and record.course_id == scope.course_id
                and record.curriculum_edition_id == scope.curriculum_edition_id
            )
            if len(scoped) != len(records):
                warnings.add(ExplorerWarningCode.SCOPE_MISMATCH)
            if scoped:
                safe_records[chunk_id] = scoped
        return safe_records

    @staticmethod
    def _resolve_citations(
        entity: ApprovedGraphNode | ApprovedGraphRelationship,
        scope: RetrievalScope,
        hydrated: dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]],
        warnings: set[ExplorerWarningCode],
    ) -> tuple[StudentCitationPreview, ...]:
        citations: dict[UUID, StudentCitationPreview] = {}
        for evidence in entity.evidence:
            chunk_id = _as_uuid(evidence.source_chunk_id)
            if chunk_id is None:
                warnings.add(ExplorerWarningCode.INVALID_EVIDENCE_POINTER)
                continue
            records = hydrated.get(chunk_id, ())
            if not records:
                warnings.add(ExplorerWarningCode.UNPUBLISHED_EVIDENCE)
                continue
            matched = False
            for record in records:
                if _graph_evidence_matches_record(evidence, record, scope):
                    matched = True
                    citations.setdefault(
                        record.evidence_id,
                        StudentCitationPreview.from_record(record),
                    )
            if not matched:
                warnings.add(ExplorerWarningCode.EVIDENCE_INTEGRITY_MISMATCH)
        return tuple(citations[key] for key in sorted(citations, key=str))

    @staticmethod
    def _project_node(
        node: ApprovedGraphNode,
        scope: RetrievalScope,
        hydrated: dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]],
        warnings: set[ExplorerWarningCode],
    ) -> StudentGraphNode | None:
        if not GraphExplorerService._entity_scope_is_valid(node, scope):
            warnings.add(ExplorerWarningCode.SCOPE_MISMATCH)
            return None
        node_id = _as_uuid(node.candidate_id)
        if node_id is None:
            warnings.add(ExplorerWarningCode.INVALID_ENTITY_ID)
            return None
        citations = GraphExplorerService._resolve_citations(node, scope, hydrated, warnings)
        if not citations:
            warnings.add(ExplorerWarningCode.NO_VISIBLE_EVIDENCE)
            return None
        raw_aliases = node.properties.get("aliases")
        aliases = (
            tuple(
                dict.fromkeys(
                    alias.strip()
                    for alias in raw_aliases
                    if isinstance(alias, str) and alias.strip()
                )
            )
            if isinstance(raw_aliases, (list, tuple))
            else ()
        )
        raw_formula = node.properties.get("formula_latex")
        formula_latex = (
            raw_formula.strip()
            if isinstance(raw_formula, str) and raw_formula.strip()
            else None
        )
        return StudentGraphNode(
            id=node_id,
            node_type=node.node_type,
            canonical_key=node.canonical_key,
            label=node.label,
            description=node.description,
            aliases=aliases,
            formula_latex=formula_latex,
            citations=citations,
        )

    @staticmethod
    def _project_edge(
        relationship: ApprovedGraphRelationship,
        scope: RetrievalScope,
        hydrated: dict[UUID, tuple[AuthoritativeEvidenceRecord, ...]],
        visible_node_ids: set[UUID],
        warnings: set[ExplorerWarningCode],
    ) -> StudentGraphEdge | None:
        if not GraphExplorerService._entity_scope_is_valid(relationship, scope):
            warnings.add(ExplorerWarningCode.SCOPE_MISMATCH)
            return None
        relationship_id = _as_uuid(relationship.candidate_id)
        source_id = _as_uuid(relationship.source_candidate_id)
        target_id = _as_uuid(relationship.target_candidate_id)
        if relationship_id is None or source_id is None or target_id is None:
            warnings.add(ExplorerWarningCode.INVALID_ENTITY_ID)
            return None
        if source_id not in visible_node_ids or target_id not in visible_node_ids:
            warnings.add(ExplorerWarningCode.EDGE_ENDPOINT_HIDDEN)
            return None
        citations = GraphExplorerService._resolve_citations(
            relationship, scope, hydrated, warnings
        )
        if not citations:
            warnings.add(ExplorerWarningCode.NO_VISIBLE_EVIDENCE)
            return None
        return StudentGraphEdge(
            id=relationship_id,
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship.relationship_type,
            citations=citations,
        )

    async def search_concepts(
        self,
        scope: RetrievalScope,
        query: str,
        *,
        limit: int = 20,
    ) -> ConceptSearchResponse:
        normalized_query = " ".join(query.strip().split())
        if not normalized_query:
            raise ValueError("query must not be blank")
        limit = self._validate_limit(limit)
        try:
            graph_hits = await self._store().search_nodes(
                scope.graph_scope(),
                normalized_query,
                node_types=EXPLORER_SEARCH_NODE_TYPES,
                limit=limit,
            )
        except GraphExplorerUnavailableError:
            raise
        except Exception as exc:
            raise GraphExplorerUnavailableError("graph search is unavailable") from exc

        warnings: set[ExplorerWarningCode] = set()
        entities = [hit.node for hit in graph_hits]
        hydrated = await self._hydrate_entities(scope, entities, warnings)
        visible_hits: list[StudentGraphSearchHit] = []
        seen_ids: set[UUID] = set()
        for hit in graph_hits:
            node = self._project_node(hit.node, scope, hydrated, warnings)
            if node is None or node.id in seen_ids:
                continue
            seen_ids.add(node.id)
            visible_hits.append(StudentGraphSearchHit(node=node, score=hit.score))
        warning_tuple = _sorted_warnings(warnings)
        return ConceptSearchResponse(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            query=normalized_query,
            results=tuple(visible_hits),
            degraded=bool(warning_tuple),
            warnings=warning_tuple,
        )

    async def subgraph(
        self,
        scope: RetrievalScope,
        root_candidate_id: UUID,
        *,
        max_depth: int = 2,
        limit: int = 100,
    ) -> StudentSubgraphResponse:
        max_depth = self._validate_depth(max_depth)
        limit = self._validate_limit(limit)
        try:
            graph = await self._store().get_subgraph(
                scope.graph_scope(),
                str(root_candidate_id),
                max_depth=max_depth,
                limit=limit,
            )
        except GraphNotFoundError as exc:
            raise GraphExplorerNotFoundError("graph root was not found") from exc
        except GraphExplorerUnavailableError:
            raise
        except Exception as exc:
            raise GraphExplorerUnavailableError("graph subgraph is unavailable") from exc

        warnings: set[ExplorerWarningCode] = set()
        entities: list[ApprovedGraphNode | ApprovedGraphRelationship] = [
            *graph.nodes,
            *graph.relationships,
        ]
        hydrated = await self._hydrate_entities(scope, entities, warnings)
        visible_nodes: dict[UUID, StudentGraphNode] = {}
        for raw_node in graph.nodes:
            node = self._project_node(raw_node, scope, hydrated, warnings)
            if node is not None:
                visible_nodes.setdefault(node.id, node)
        visible_edges: dict[UUID, StudentGraphEdge] = {}
        for raw_edge in graph.relationships:
            edge = self._project_edge(
                raw_edge,
                scope,
                hydrated,
                set(visible_nodes),
                warnings,
            )
            if edge is not None:
                visible_edges.setdefault(edge.id, edge)
        warning_tuple = _sorted_warnings(warnings)
        return StudentSubgraphResponse(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            root_candidate_id=root_candidate_id,
            root_visible=root_candidate_id in visible_nodes,
            nodes=tuple(
                sorted(visible_nodes.values(), key=lambda item: (item.label, str(item.id)))
            ),
            edges=tuple(sorted(visible_edges.values(), key=lambda item: str(item.id))),
            degraded=bool(warning_tuple),
            warnings=warning_tuple,
        )

    async def prerequisite_paths(
        self,
        scope: RetrievalScope,
        target_candidate_id: UUID,
        *,
        max_depth: int = 4,
        limit: int = 20,
    ) -> PrerequisitePathsResponse:
        max_depth = self._validate_depth(max_depth)
        limit = self._validate_limit(limit)
        try:
            graph_paths = await self._store().get_prerequisite_paths(
                scope.graph_scope(),
                str(target_candidate_id),
                max_depth=max_depth,
                limit=limit,
            )
        except GraphNotFoundError as exc:
            raise GraphExplorerNotFoundError("graph target was not found") from exc
        except GraphExplorerUnavailableError:
            raise
        except Exception as exc:
            raise GraphExplorerUnavailableError("prerequisite graph is unavailable") from exc

        warnings: set[ExplorerWarningCode] = set()
        entities: list[ApprovedGraphNode | ApprovedGraphRelationship] = []
        for path in graph_paths:
            entities.extend(path.nodes)
            entities.extend(path.relationships)
        hydrated = await self._hydrate_entities(scope, entities, warnings)

        visible_nodes: dict[UUID, StudentGraphNode] = {}
        visible_edges: dict[UUID, StudentGraphEdge] = {}
        for path in graph_paths:
            for raw_node in path.nodes:
                node = self._project_node(raw_node, scope, hydrated, warnings)
                if node is not None:
                    visible_nodes.setdefault(node.id, node)
        for path in graph_paths:
            for raw_edge in path.relationships:
                edge = self._project_edge(
                    raw_edge,
                    scope,
                    hydrated,
                    set(visible_nodes),
                    warnings,
                )
                if edge is not None:
                    visible_edges.setdefault(edge.id, edge)

        visible_paths: list[StudentPrerequisitePath] = []
        for raw_path in graph_paths:
            node_ids = [_as_uuid(node.candidate_id) for node in raw_path.nodes]
            edge_ids = [_as_uuid(edge.candidate_id) for edge in raw_path.relationships]
            if (
                any(item is None or item not in visible_nodes for item in node_ids)
                or any(item is None or item not in visible_edges for item in edge_ids)
            ):
                warnings.add(ExplorerWarningCode.INCOMPLETE_PREREQUISITE_PATH)
                continue
            # The guards above prove these optionals are present in the maps.
            concrete_node_ids = [item for item in node_ids if item is not None]
            concrete_edge_ids = [item for item in edge_ids if item is not None]
            try:
                visible_paths.append(
                    StudentPrerequisitePath(
                        nodes=tuple(visible_nodes[item] for item in concrete_node_ids),
                        edges=tuple(visible_edges[item] for item in concrete_edge_ids),
                    )
                )
            except ValueError:
                warnings.add(ExplorerWarningCode.INCOMPLETE_PREREQUISITE_PATH)
        warning_tuple = _sorted_warnings(warnings)
        return PrerequisitePathsResponse(
            course_id=scope.course_id,
            curriculum_edition_id=scope.curriculum_edition_id,
            target_candidate_id=target_candidate_id,
            paths=tuple(visible_paths),
            degraded=bool(warning_tuple),
            warnings=warning_tuple,
        )


__all__ = [
    "EXPLORER_SEARCH_NODE_TYPES",
    "ConceptSearchResponse",
    "ExplorerWarningCode",
    "GraphExplorerError",
    "GraphExplorerNotFoundError",
    "GraphExplorerService",
    "GraphExplorerUnavailableError",
    "PrerequisitePathsResponse",
    "StudentCitationPreview",
    "StudentGraphEdge",
    "StudentGraphNode",
    "StudentGraphSearchHit",
    "StudentPrerequisitePath",
    "StudentSubgraphResponse",
]
