"""Deterministic import of teacher-authored DOCX/XLSX course structure.

Structural files are privileged authored inputs, but importing them is not a
teacher approval decision.  Every graph node and relationship created here is
therefore ``REVIEW_REQUIRED`` and linked to an exact first-class Evidence row.
The six-chapter 2026 syllabus and eight-root 2022 taxonomy are scoped to
different CurriculumEdition IDs and are never aligned by chapter number.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.db_models import (
    CandidateOrigin,
    CandidateStatus,
    CurriculumEdition,
    CurriculumOutlineSource,
    CurriculumUnit,
    CurriculumUnitType,
    EvidenceSupportRole,
    ExtractionRun,
    ExtractionRunStatus,
    GraphNodeCandidate,
    GraphNodeType,
    GraphRelationCandidate,
    GraphRelationType,
    NodeCandidateEvidenceSupport,
    RelationCandidateEvidenceSupport,
    utc_now,
)
from quantum_agent.knowledge.ingestion import (
    CourseOutlineEntry,
    HierarchySeedNode,
    IngestedDocument,
    IngestionConfig,
    OutlineEntryType,
    SeedNodeType,
    SeedRelationType,
    parse_docx_outline_seed,
    parse_xlsx_hierarchy_seed,
    sha256_text,
)
from quantum_agent.knowledge.ontology import (
    NodeType as OntologyNodeType,
)
from quantum_agent.knowledge.ontology import (
    RelationshipType as OntologyRelationshipType,
)
from quantum_agent.knowledge.ontology import is_allowed_triple
from quantum_agent.knowledge.source_manifest import ManifestSource

STRUCTURAL_IMPORT_VERSION = "1.1.0"
STRUCTURAL_IDENTITY_NAMESPACE = "quantum-agent:structural-identity:v1"


class StructuralImportError(RuntimeError):
    """Raised when authored structure cannot be grounded exactly."""


@dataclass(frozen=True, slots=True)
class StructuralSourceContext:
    source: ManifestSource
    resolved_path: Path
    document_id: UUID
    document_version_id: UUID
    parsed: IngestedDocument
    chunk_ids_by_ingestion_id: Mapping[str, UUID]
    evidence_ids_by_ingestion_chunk_id: Mapping[str, UUID]


class StructuralImportReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    syllabus_chapter_roots: int
    taxonomy_roots: int
    syllabus_node_candidates: int
    syllabus_relation_candidates: int
    taxonomy_node_candidates: int
    taxonomy_relation_candidates: int
    curriculum_units: int
    diagnostics: tuple[str, ...] = ()


def _stable_uuid(kind: str, *parts: object) -> UUID:
    payload = "|".join(str(part) for part in parts)
    return uuid5(
        NAMESPACE_URL,
        f"{STRUCTURAL_IDENTITY_NAMESPACE}:{kind}:{payload}",
    )


def _validate_structural_triple(
    *,
    relation_id: str,
    source_type: GraphNodeType,
    relation_type: GraphRelationType,
    target_type: GraphNodeType,
) -> None:
    """Fail closed when database enums drift outside the explicit ontology."""

    try:
        ontology_source = OntologyNodeType[source_type.name]
        ontology_relation = OntologyRelationshipType[relation_type.name]
        ontology_target = OntologyNodeType[target_type.name]
    except KeyError as error:
        raise StructuralImportError(
            f"structural relation {relation_id!r} uses an unmapped ontology enum: "
            f"{source_type.name} {relation_type.name} {target_type.name}"
        ) from error
    if not is_allowed_triple(ontology_source, ontology_relation, ontology_target):
        raise StructuralImportError(
            f"closed-world ontology rejected structural relation {relation_id!r}: "
            f"{ontology_source.value} {ontology_relation.value} {ontology_target.value}"
        )


def _configuration_sha256(
    kind: str,
    config: IngestionConfig,
    ontology_version: str,
) -> str:
    payload = json.dumps(
        {
            "kind": kind,
            "structural_import_version": STRUCTURAL_IMPORT_VERSION,
            "ontology_version": ontology_version,
            "ingestion": config.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(payload)


async def _ensure_extraction_run(
    session: AsyncSession,
    *,
    context: StructuralSourceContext,
    kind: str,
    config: IngestionConfig,
    ontology_version: str,
) -> ExtractionRun:
    run_id = _stable_uuid(
        "extraction-run",
        context.document_version_id,
        kind,
        STRUCTURAL_IMPORT_VERSION,
        _configuration_sha256(kind, config, ontology_version),
        ontology_version,
    )
    run = await session.get(ExtractionRun, run_id)
    if run is None:
        now = utc_now()
        run = ExtractionRun(
            id=run_id,
            document_version_id=context.document_version_id,
            pipeline_name=f"authored-{kind}-structural-import",
            pipeline_version=STRUCTURAL_IMPORT_VERSION,
            ontology_version=ontology_version,
            model_provider=None,
            model_name=None,
            configuration_sha256=_configuration_sha256(kind, config, ontology_version),
            status=ExtractionRunStatus.SUCCEEDED,
            started_at=now,
            completed_at=now,
            metrics_json={"mode": "deterministic_import", "teacher_review_required": True},
        )
        session.add(run)
        await session.flush()
    elif (
        run.document_version_id != context.document_version_id
        or run.pipeline_version != STRUCTURAL_IMPORT_VERSION
        or run.ontology_version != ontology_version
        or run.configuration_sha256 != _configuration_sha256(kind, config, ontology_version)
    ):
        raise StructuralImportError("stable extraction run identity/configuration changed")
    return run


async def _ensure_outline_source(
    session: AsyncSession,
    *,
    edition_id: UUID,
    context: StructuralSourceContext,
    extracted_outline: dict[str, object],
) -> None:
    record_id = _stable_uuid("outline-source", edition_id, context.document_version_id)
    record = await session.get(CurriculumOutlineSource, record_id)
    if record is None:
        session.add(
            CurriculumOutlineSource(
                id=record_id,
                curriculum_edition_id=edition_id,
                document_version_id=context.document_version_id,
                is_primary=True,
                extracted_outline_json=extracted_outline,
            )
        )
    elif (
        record.curriculum_edition_id != edition_id
        or record.document_version_id != context.document_version_id
    ):
        raise StructuralImportError("stable outline-source identity changed")


def _required_evidence(context: StructuralSourceContext, chunk_id: str) -> UUID:
    try:
        return context.evidence_ids_by_ingestion_chunk_id[chunk_id]
    except KeyError as error:
        raise StructuralImportError(
            f"structural source chunk {chunk_id!r} has no exact Evidence row"
        ) from error


async def _load_nodes(session: AsyncSession, ids: list[UUID]) -> dict[UUID, GraphNodeCandidate]:
    if not ids:
        return {}
    return {
        node.id: node
        for node in (
            await session.scalars(select(GraphNodeCandidate).where(GraphNodeCandidate.id.in_(ids)))
        ).all()
    }


async def _load_relations(
    session: AsyncSession, ids: list[UUID]
) -> dict[UUID, GraphRelationCandidate]:
    if not ids:
        return {}
    return {
        relation.id: relation
        for relation in (
            await session.scalars(
                select(GraphRelationCandidate).where(GraphRelationCandidate.id.in_(ids))
            )
        ).all()
    }


async def _add_node_supports(
    session: AsyncSession,
    supports: list[tuple[UUID, UUID, dict[str, object]]],
) -> None:
    if not supports:
        return
    candidate_ids = [candidate_id for candidate_id, _, _ in supports]
    existing = set(
        (
            await session.execute(
                select(
                    NodeCandidateEvidenceSupport.node_candidate_id,
                    NodeCandidateEvidenceSupport.evidence_id,
                ).where(NodeCandidateEvidenceSupport.node_candidate_id.in_(candidate_ids))
            )
        ).all()
    )
    for candidate_id, evidence_id, span in supports:
        if (candidate_id, evidence_id) in existing:
            continue
        session.add(
            NodeCandidateEvidenceSupport(
                node_candidate_id=candidate_id,
                evidence_id=evidence_id,
                support_role=EvidenceSupportRole.PRIMARY,
                confidence=1.0,
                extraction_span_json=span,
            )
        )


async def _add_relation_supports(
    session: AsyncSession,
    supports: list[tuple[UUID, UUID, dict[str, object]]],
) -> None:
    if not supports:
        return
    candidate_ids = [candidate_id for candidate_id, _, _ in supports]
    existing = set(
        (
            await session.execute(
                select(
                    RelationCandidateEvidenceSupport.relation_candidate_id,
                    RelationCandidateEvidenceSupport.evidence_id,
                ).where(RelationCandidateEvidenceSupport.relation_candidate_id.in_(candidate_ids))
            )
        ).all()
    )
    for candidate_id, evidence_id, span in supports:
        if (candidate_id, evidence_id) in existing:
            continue
        session.add(
            RelationCandidateEvidenceSupport(
                relation_candidate_id=candidate_id,
                evidence_id=evidence_id,
                support_role=EvidenceSupportRole.PRIMARY,
                confidence=1.0,
                extraction_span_json=span,
            )
        )


@dataclass(frozen=True, slots=True)
class _UnitSpec:
    source_id: str
    parent_source_id: str | None
    unit_type: CurriculumUnitType
    canonical_path: str
    source_label: str | None
    ordinal: int
    title: str
    description: str | None
    evidence_id: UUID


async def _ensure_curriculum_units(
    session: AsyncSession,
    *,
    edition_id: UUID,
    specs: list[_UnitSpec],
) -> int:
    ids_by_source = {
        spec.source_id: _stable_uuid("curriculum-unit", edition_id, spec.source_id)
        for spec in specs
    }
    existing = {
        unit.id: unit
        for unit in (
            await session.scalars(
                select(CurriculumUnit).where(CurriculumUnit.curriculum_edition_id == edition_id)
            )
        ).all()
    }
    for spec in specs:
        unit_id = ids_by_source[spec.source_id]
        parent_id = (
            ids_by_source.get(spec.parent_source_id) if spec.parent_source_id is not None else None
        )
        unit = existing.get(unit_id)
        if unit is None:
            session.add(
                CurriculumUnit(
                    id=unit_id,
                    curriculum_edition_id=edition_id,
                    parent_unit_id=parent_id,
                    unit_type=spec.unit_type,
                    canonical_path=spec.canonical_path,
                    source_label=spec.source_label,
                    ordinal=spec.ordinal,
                    title=spec.title,
                    description=spec.description,
                    source_evidence_id=spec.evidence_id,
                )
            )
        elif (
            unit.parent_unit_id != parent_id
            or unit.unit_type != spec.unit_type
            or unit.canonical_path != spec.canonical_path
            or unit.title != spec.title
            or unit.source_evidence_id != spec.evidence_id
        ):
            raise StructuralImportError(f"curriculum unit {unit_id} changed provenance")
    await session.flush()
    return len(specs)


def _outline_graph_type(entry: CourseOutlineEntry) -> GraphNodeType:
    return {
        OutlineEntryType.CHAPTER: GraphNodeType.CHAPTER,
        OutlineEntryType.SECTION: GraphNodeType.SECTION,
        OutlineEntryType.TOPIC: GraphNodeType.CONCEPT,
    }[entry.entry_type]


def _outline_unit_type(entry: CourseOutlineEntry) -> CurriculumUnitType:
    return {
        OutlineEntryType.CHAPTER: CurriculumUnitType.CHAPTER,
        OutlineEntryType.SECTION: CurriculumUnitType.SECTION,
        OutlineEntryType.TOPIC: CurriculumUnitType.TOPIC,
    }[entry.entry_type]


async def _import_syllabus(
    session: AsyncSession,
    *,
    course_id: UUID,
    edition_id: UUID,
    context: StructuralSourceContext,
    ingestion_config: IngestionConfig,
    ontology_version: str,
) -> tuple[int, int, int, tuple[str, ...]]:
    seed = parse_docx_outline_seed(
        context.resolved_path,
        config=ingestion_config,
        source_name=context.source.path,
    )
    if seed.document.sha256 != context.parsed.sha256:
        raise StructuralImportError("syllabus changed between source and structural parsing")
    structural_entries = [
        entry
        for entry in seed.entries
        if entry.entry_type
        in {OutlineEntryType.CHAPTER, OutlineEntryType.SECTION, OutlineEntryType.TOPIC}
    ]
    entries_by_id = {entry.id: entry for entry in structural_entries}
    relation_specs = [
        relation
        for relation in seed.relations
        if relation.child_id in entries_by_id and relation.parent_id in entries_by_id
    ]
    for relation in relation_specs:
        if relation.child_id == relation.parent_id:
            raise StructuralImportError(f"structural relation {relation.id!r} has a self endpoint")
        _validate_structural_triple(
            relation_id=relation.id,
            source_type=_outline_graph_type(entries_by_id[relation.child_id]),
            relation_type=GraphRelationType.PART_OF,
            target_type=_outline_graph_type(entries_by_id[relation.parent_id]),
        )
    diagnostics = list(seed.diagnostics)
    excluded_relation_count = len(seed.relations) - len(relation_specs)
    if excluded_relation_count:
        diagnostics.append(
            f"{excluded_relation_count} authored outline relation(s) excluded because one or "
            "both endpoints are outside the explicit Chapter/Section/Concept graph scope"
        )
    run = await _ensure_extraction_run(
        session,
        context=context,
        kind="docx-outline",
        config=ingestion_config,
        ontology_version=ontology_version,
    )
    candidate_ids = {
        entry.id: _stable_uuid("outline-node-candidate", edition_id, entry.id)
        for entry in structural_entries
    }
    existing_nodes = await _load_nodes(session, list(candidate_ids.values()))
    node_supports: list[tuple[UUID, UUID, dict[str, object]]] = []
    for entry in structural_entries:
        candidate_id = candidate_ids[entry.id]
        evidence_id = _required_evidence(context, entry.source_chunk_id)
        canonical_key = f"authored:docx-outline:{entry.id}"
        existing = existing_nodes.get(candidate_id)
        if existing is None:
            session.add(
                GraphNodeCandidate(
                    id=candidate_id,
                    course_id=course_id,
                    curriculum_edition_id=edition_id,
                    extraction_run_id=run.id,
                    node_type=_outline_graph_type(entry),
                    canonical_key=canonical_key,
                    label=entry.verbatim_label,
                    description=None,
                    properties_json={
                        "structural_source": "2026_docx_syllabus",
                        "verbatim_label": entry.verbatim_label,
                        "canonical_label": entry.canonical_label,
                        "outline_number": entry.outline_number,
                        "depth": entry.depth,
                        "hours": entry.hours,
                        "section_path": list(entry.section_path),
                        "source_locator": entry.source_locator.model_dump(mode="json"),
                        "review_flags": list(entry.review_flags),
                    },
                    origin=CandidateOrigin.IMPORTED,
                    confidence=1.0,
                    status=CandidateStatus.REVIEW_REQUIRED,
                    revision_number=1,
                )
            )
        elif (
            existing.course_id != course_id
            or existing.curriculum_edition_id != edition_id
            or existing.node_type != _outline_graph_type(entry)
            or existing.canonical_key != canonical_key
            or existing.label != entry.verbatim_label
        ):
            raise StructuralImportError(f"syllabus node candidate {candidate_id} changed")
        node_supports.append(
            (
                candidate_id,
                evidence_id,
                {
                    "source_chunk_id": entry.source_chunk_id,
                    "locator": entry.source_locator.model_dump(mode="json"),
                    "basis": "exact_authored_paragraph",
                },
            )
        )
    await session.flush()
    await _add_node_supports(session, node_supports)

    relation_ids = {
        relation.id: _stable_uuid("outline-relation-candidate", edition_id, relation.id)
        for relation in relation_specs
    }
    existing_relations = await _load_relations(session, list(relation_ids.values()))
    relation_supports: list[tuple[UUID, UUID, dict[str, object]]] = []
    for relation in relation_specs:
        relation_id = relation_ids[relation.id]
        source_id = candidate_ids[relation.child_id]
        target_id = candidate_ids[relation.parent_id]
        canonical_key = f"authored:docx-outline:{relation.id}"
        existing_relation = existing_relations.get(relation_id)
        if existing_relation is None:
            session.add(
                GraphRelationCandidate(
                    id=relation_id,
                    course_id=course_id,
                    curriculum_edition_id=edition_id,
                    extraction_run_id=run.id,
                    source_node_candidate_id=source_id,
                    target_node_candidate_id=target_id,
                    relation_type=GraphRelationType.PART_OF,
                    canonical_key=canonical_key,
                    properties_json={
                        "structural_source": "2026_docx_syllabus",
                        "child_verbatim_label": entries_by_id[relation.child_id].verbatim_label,
                        "parent_verbatim_label": entries_by_id[relation.parent_id].verbatim_label,
                    },
                    origin=CandidateOrigin.IMPORTED,
                    confidence=1.0,
                    status=CandidateStatus.REVIEW_REQUIRED,
                    revision_number=1,
                )
            )
        elif (
            existing_relation.source_node_candidate_id != source_id
            or existing_relation.target_node_candidate_id != target_id
            or existing_relation.relation_type != GraphRelationType.PART_OF
            or existing_relation.canonical_key != canonical_key
        ):
            raise StructuralImportError(f"syllabus relation candidate {relation_id} changed")
        evidence_id = _required_evidence(context, relation.source_chunk_id)
        relation_supports.append(
            (
                relation_id,
                evidence_id,
                {
                    "source_chunk_id": relation.source_chunk_id,
                    "basis": "exact_authored_hierarchy",
                },
            )
        )
    await session.flush()
    await _add_relation_supports(session, relation_supports)

    unit_specs = [
        _UnitSpec(
            source_id=entry.id,
            parent_source_id=(entry.parent_id if entry.parent_id in candidate_ids else None),
            unit_type=_outline_unit_type(entry),
            canonical_path=f"authored/docx/{entry.id}",
            source_label=entry.outline_number,
            ordinal=int(entry.source_locator.start),
            title=entry.verbatim_label,
            description=None,
            evidence_id=_required_evidence(context, entry.source_chunk_id),
        )
        for entry in structural_entries
    ]
    unit_count = await _ensure_curriculum_units(
        session,
        edition_id=edition_id,
        specs=unit_specs,
    )
    roots = sum(entry.entry_type == OutlineEntryType.CHAPTER for entry in structural_entries)
    await _ensure_outline_source(
        session,
        edition_id=edition_id,
        context=context,
        extracted_outline={
            "source_sha256": seed.document.sha256,
            "academic_year": seed.academic_year,
            "term": seed.term,
            "chapter_count": roots,
            "chapter_labels": [
                entry.verbatim_label
                for entry in structural_entries
                if entry.entry_type == OutlineEntryType.CHAPTER
            ],
            "diagnostics": diagnostics,
            "review_status": "REVIEW_REQUIRED",
        },
    )
    edition = await session.get(CurriculumEdition, edition_id)
    if edition is None:
        raise StructuralImportError("syllabus curriculum edition is missing")
    if seed.academic_year is not None:
        if edition.academic_year not in (None, str(seed.academic_year)):
            raise StructuralImportError("syllabus academic year conflicts with persisted edition")
        edition.academic_year = str(seed.academic_year)
    if seed.term is not None:
        if edition.term not in (None, seed.term):
            raise StructuralImportError("syllabus term conflicts with persisted edition")
        edition.term = seed.term
    edition.outline_json = {
        **edition.outline_json,
        "structural_source_sha256": seed.document.sha256,
        "structural_root_count": roots,
        "structural_review_status": "REVIEW_REQUIRED",
    }
    run.metrics_json = {
        **run.metrics_json,
        "node_candidates": len(structural_entries),
        "relation_candidates": len(relation_specs),
        "ontology_validated_relations": len(relation_specs),
        "curriculum_units": unit_count,
        "chapter_roots": roots,
    }
    return len(structural_entries), len(relation_specs), unit_count, tuple(diagnostics)


def _taxonomy_graph_type(node: HierarchySeedNode) -> GraphNodeType:
    if node.node_type == SeedNodeType.CONCEPT:
        return GraphNodeType.CONCEPT
    if node.parent_id is None:
        return GraphNodeType.CHAPTER
    return GraphNodeType.SECTION


def _taxonomy_unit_type(node: HierarchySeedNode) -> CurriculumUnitType:
    if node.node_type == SeedNodeType.CONCEPT:
        return CurriculumUnitType.TOPIC
    if node.parent_id is None:
        return CurriculumUnitType.CHAPTER
    return CurriculumUnitType.SECTION


_TAXONOMY_RELATION_MAP: dict[SeedRelationType, GraphRelationType] = {
    SeedRelationType.PART_OF: GraphRelationType.PART_OF,
    SeedRelationType.PREREQUISITE_OF: GraphRelationType.PREREQUISITE_OF,
    SeedRelationType.RELATED_TO: GraphRelationType.RELATED_TO,
}


async def _import_taxonomy(
    session: AsyncSession,
    *,
    course_id: UUID,
    edition_id: UUID,
    context: StructuralSourceContext,
    ingestion_config: IngestionConfig,
    ontology_version: str,
) -> tuple[int, int, int, tuple[str, ...]]:
    seed = parse_xlsx_hierarchy_seed(
        context.resolved_path,
        config=ingestion_config,
        source_name=context.source.path,
    )
    if seed.document.sha256 != context.parsed.sha256:
        raise StructuralImportError("taxonomy changed between source and structural parsing")
    nodes_by_id = {node.id: node for node in seed.nodes}
    for relation in seed.relations:
        if relation.source_node_id is None or relation.target_node_id is None:
            raise StructuralImportError(
                f"taxonomy relation {relation.id!r} has an unresolved endpoint; "
                "the authored row must be corrected before import"
            )
        if relation.source_node_id not in nodes_by_id or relation.target_node_id not in nodes_by_id:
            raise StructuralImportError(
                f"taxonomy relation {relation.id!r} references a node outside the "
                "authored hierarchy"
            )
        if relation.source_node_id == relation.target_node_id:
            raise StructuralImportError(f"taxonomy relation {relation.id!r} has a self endpoint")
        _validate_structural_triple(
            relation_id=relation.id,
            source_type=_taxonomy_graph_type(nodes_by_id[relation.source_node_id]),
            relation_type=_TAXONOMY_RELATION_MAP[relation.relation_type],
            target_type=_taxonomy_graph_type(nodes_by_id[relation.target_node_id]),
        )
    run = await _ensure_extraction_run(
        session,
        context=context,
        kind="xlsx-taxonomy",
        config=ingestion_config,
        ontology_version=ontology_version,
    )
    candidate_ids = {
        node.id: _stable_uuid("taxonomy-node-candidate", edition_id, node.id) for node in seed.nodes
    }
    existing_nodes = await _load_nodes(session, list(candidate_ids.values()))
    node_supports: list[tuple[UUID, UUID, dict[str, object]]] = []
    for node in seed.nodes:
        candidate_id = candidate_ids[node.id]
        evidence_id = _required_evidence(context, node.source_chunk_id)
        canonical_key = f"authored:xlsx-taxonomy:{node.id}"
        graph_type = _taxonomy_graph_type(node)
        existing = existing_nodes.get(candidate_id)
        if existing is None:
            session.add(
                GraphNodeCandidate(
                    id=candidate_id,
                    course_id=course_id,
                    curriculum_edition_id=edition_id,
                    extraction_run_id=run.id,
                    node_type=graph_type,
                    canonical_key=canonical_key,
                    label=node.verbatim_label,
                    description=node.description,
                    properties_json={
                        "structural_source": "2022_xlsx_taxonomy",
                        "verbatim_label": node.verbatim_label,
                        "canonical_label": node.canonical_label,
                        "aliases": list(node.aliases),
                        "hierarchy_path": list(node.hierarchy_path),
                        "tags": list(node.tags),
                        "knowledge_category": node.knowledge_category,
                        "source_locator": node.source_locator.model_dump(mode="json"),
                        "review_flags": list(node.review_flags),
                    },
                    origin=CandidateOrigin.IMPORTED,
                    confidence=1.0,
                    status=CandidateStatus.REVIEW_REQUIRED,
                    revision_number=1,
                )
            )
        elif (
            existing.course_id != course_id
            or existing.curriculum_edition_id != edition_id
            or existing.node_type != graph_type
            or existing.canonical_key != canonical_key
            or existing.label != node.verbatim_label
        ):
            raise StructuralImportError(f"taxonomy node candidate {candidate_id} changed")
        node_supports.append(
            (
                candidate_id,
                evidence_id,
                {
                    "source_chunk_id": node.source_chunk_id,
                    "locator": node.source_locator.model_dump(mode="json"),
                    "basis": "exact_authored_sheet_row",
                },
            )
        )
    await session.flush()
    await _add_node_supports(session, node_supports)

    diagnostics = list(seed.diagnostics)
    persisted_relations = list(seed.relations)
    relation_ids = {
        relation.id: _stable_uuid("taxonomy-relation-candidate", edition_id, relation.id)
        for relation in persisted_relations
    }
    existing_relations = await _load_relations(session, list(relation_ids.values()))
    relation_supports: list[tuple[UUID, UUID, dict[str, object]]] = []
    for relation in persisted_relations:
        if relation.source_node_id is None or relation.target_node_id is None:
            raise AssertionError("validated taxonomy relation has missing endpoints")
        candidate_id = relation_ids[relation.id]
        source_id = candidate_ids[relation.source_node_id]
        target_id = candidate_ids[relation.target_node_id]
        relation_type = _TAXONOMY_RELATION_MAP[relation.relation_type]
        canonical_key = f"authored:xlsx-taxonomy:{relation.id}"
        existing_relation = existing_relations.get(candidate_id)
        if existing_relation is None:
            session.add(
                GraphRelationCandidate(
                    id=candidate_id,
                    course_id=course_id,
                    curriculum_edition_id=edition_id,
                    extraction_run_id=run.id,
                    source_node_candidate_id=source_id,
                    target_node_candidate_id=target_id,
                    relation_type=relation_type,
                    canonical_key=canonical_key,
                    properties_json={
                        "structural_source": "2022_xlsx_taxonomy",
                        "verbatim_source_label": relation.verbatim_source_label,
                        "canonical_source_label": relation.canonical_source_label,
                        "verbatim_target_label": relation.verbatim_target_label,
                        "canonical_target_label": relation.canonical_target_label,
                        "declared_on_node_id": relation.declared_on_node_id,
                        "source_locator": relation.source_locator.model_dump(mode="json"),
                        "review_flags": list(relation.review_flags),
                    },
                    origin=CandidateOrigin.IMPORTED,
                    confidence=1.0,
                    status=CandidateStatus.REVIEW_REQUIRED,
                    revision_number=1,
                )
            )
        elif (
            existing_relation.source_node_candidate_id != source_id
            or existing_relation.target_node_candidate_id != target_id
            or existing_relation.relation_type != relation_type
            or existing_relation.canonical_key != canonical_key
        ):
            raise StructuralImportError(f"taxonomy relation candidate {candidate_id} changed")
        evidence_id = _required_evidence(context, relation.source_chunk_id)
        relation_supports.append(
            (
                candidate_id,
                evidence_id,
                {
                    "source_chunk_id": relation.source_chunk_id,
                    "locator": relation.source_locator.model_dump(mode="json"),
                    "basis": "exact_authored_relation_cell",
                },
            )
        )
    await session.flush()
    await _add_relation_supports(session, relation_supports)

    unit_specs = [
        _UnitSpec(
            source_id=node.id,
            parent_source_id=node.parent_id,
            unit_type=_taxonomy_unit_type(node),
            canonical_path=f"authored/xlsx/{node.id}",
            source_label=node.verbatim_label,
            ordinal=int(node.source_locator.start),
            title=node.verbatim_label,
            description=node.description,
            evidence_id=_required_evidence(context, node.source_chunk_id),
        )
        for node in seed.nodes
    ]
    unit_count = await _ensure_curriculum_units(
        session,
        edition_id=edition_id,
        specs=unit_specs,
    )
    roots = sum(node.parent_id is None for node in seed.nodes)
    await _ensure_outline_source(
        session,
        edition_id=edition_id,
        context=context,
        extracted_outline={
            "source_sha256": seed.document.sha256,
            "root_count": roots,
            "root_labels": [node.verbatim_label for node in seed.nodes if node.parent_id is None],
            "node_count": len(seed.nodes),
            "relation_count": len(persisted_relations),
            "diagnostics": diagnostics,
            "review_status": "REVIEW_REQUIRED",
        },
    )
    edition = await session.get(CurriculumEdition, edition_id)
    if edition is None:
        raise StructuralImportError("taxonomy curriculum edition is missing")
    edition.outline_json = {
        **edition.outline_json,
        "structural_source_sha256": seed.document.sha256,
        "structural_root_count": roots,
        "structural_review_status": "REVIEW_REQUIRED",
    }
    run.metrics_json = {
        **run.metrics_json,
        "node_candidates": len(seed.nodes),
        "relation_candidates": len(persisted_relations),
        "ontology_validated_relations": len(persisted_relations),
        "curriculum_units": unit_count,
        "chapter_roots": roots,
    }
    return len(seed.nodes), len(persisted_relations), unit_count, tuple(diagnostics)


async def import_authored_structures(
    session: AsyncSession,
    *,
    course_id: UUID,
    editions: Mapping[str, UUID],
    contexts: Mapping[str, StructuralSourceContext],
    ingestion_config: IngestionConfig,
    ontology_version: str,
) -> StructuralImportReport:
    """Import the two authored structures into isolated review queues."""

    syllabus_context = next(
        (context for context in contexts.values() if context.source.kind == "syllabus"),
        None,
    )
    taxonomy_context = next(
        (
            context
            for context in contexts.values()
            if context.source.kind == "teacher_curated_taxonomy"
        ),
        None,
    )
    if syllabus_context is None or taxonomy_context is None:
        raise StructuralImportError(
            "manifest must include authored DOCX syllabus and XLSX taxonomy"
        )
    try:
        syllabus_edition_id = editions["syllabus-2026-fall"]
        taxonomy_edition_id = editions["lecture-decks-2022"]
    except KeyError as error:
        raise StructuralImportError("required curriculum edition is absent") from error
    if syllabus_edition_id == taxonomy_edition_id:
        raise StructuralImportError("syllabus and taxonomy curriculum editions must be isolated")

    (
        syllabus_nodes,
        syllabus_relations,
        syllabus_units,
        syllabus_diagnostics,
    ) = await _import_syllabus(
        session,
        course_id=course_id,
        edition_id=syllabus_edition_id,
        context=syllabus_context,
        ingestion_config=ingestion_config,
        ontology_version=ontology_version,
    )
    (
        taxonomy_nodes,
        taxonomy_relations,
        taxonomy_units,
        taxonomy_diagnostics,
    ) = await _import_taxonomy(
        session,
        course_id=course_id,
        edition_id=taxonomy_edition_id,
        context=taxonomy_context,
        ingestion_config=ingestion_config,
        ontology_version=ontology_version,
    )
    await session.flush()
    syllabus_roots = int(
        sum(
            unit.parent_unit_id is None
            for unit in (
                await session.scalars(
                    select(CurriculumUnit).where(
                        CurriculumUnit.curriculum_edition_id == syllabus_edition_id
                    )
                )
            ).all()
        )
    )
    taxonomy_roots = int(
        sum(
            unit.parent_unit_id is None
            for unit in (
                await session.scalars(
                    select(CurriculumUnit).where(
                        CurriculumUnit.curriculum_edition_id == taxonomy_edition_id
                    )
                )
            ).all()
        )
    )
    return StructuralImportReport(
        syllabus_chapter_roots=syllabus_roots,
        taxonomy_roots=taxonomy_roots,
        syllabus_node_candidates=syllabus_nodes,
        syllabus_relation_candidates=syllabus_relations,
        taxonomy_node_candidates=taxonomy_nodes,
        taxonomy_relation_candidates=taxonomy_relations,
        curriculum_units=syllabus_units + taxonomy_units,
        diagnostics=tuple((*syllabus_diagnostics, *taxonomy_diagnostics)),
    )


__all__ = [
    "StructuralImportError",
    "StructuralImportReport",
    "StructuralSourceContext",
    "import_authored_structures",
]
