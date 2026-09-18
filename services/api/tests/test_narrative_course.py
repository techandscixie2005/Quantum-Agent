"""Narrative-only ingestion has no synthetic graph or automatic publication."""

from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.knowledge.ingestion import IngestionConfig
from quantum_agent.knowledge.structural_import import import_authored_structures


async def test_narrative_course_has_no_invented_structure() -> None:
    report = await import_authored_structures(
        cast(AsyncSession, None),
        course_id=uuid4(),
        editions={"demo-v1": uuid4()},
        contexts={},
        ingestion_config=IngestionConfig(),
        ontology_version="1.0.0",
    )
    assert report.curriculum_units == 0
    assert report.syllabus_node_candidates == report.taxonomy_node_candidates == 0
    assert report.syllabus_relation_candidates == report.taxonomy_relation_candidates == 0
    assert report.diagnostics == ("no_authored_structure_supplied",)
