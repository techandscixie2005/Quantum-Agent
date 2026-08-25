from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.db_models import GraphNodeType, GraphRelationType
from quantum_agent.knowledge.pipeline import (
    _acquire_course_import_lock,
    course_advisory_lock_key,
)
from quantum_agent.knowledge.structural_import import (
    StructuralImportError,
    _validate_structural_triple,
)


@dataclass
class _Dialect:
    name: str


@dataclass
class _Bind:
    dialect: _Dialect


@dataclass
class _RecordingSession:
    dialect_name: str
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def get_bind(self) -> _Bind:
        return _Bind(dialect=_Dialect(name=self.dialect_name))

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> None:
        self.calls.append((str(statement), parameters))


def test_course_advisory_lock_key_is_stable_signed_int64() -> None:
    first = course_advisory_lock_key("quantum-physics-2026-fall")
    assert first == course_advisory_lock_key("quantum-physics-2026-fall")
    assert first != course_advisory_lock_key("another-course")
    assert -(2**63) <= first < 2**63


@pytest.mark.asyncio
async def test_postgresql_import_uses_course_scoped_transaction_lock() -> None:
    recording = _RecordingSession(dialect_name="postgresql")
    await _acquire_course_import_lock(
        cast(AsyncSession, cast(Any, recording)),
        "quantum-physics-2026-fall",
    )
    assert recording.calls == [
        (
            "SELECT pg_advisory_xact_lock(CAST(:lock_key AS BIGINT))",
            {"lock_key": course_advisory_lock_key("quantum-physics-2026-fall")},
        )
    ]


@pytest.mark.asyncio
async def test_sqlite_import_does_not_issue_postgresql_lock_sql() -> None:
    recording = _RecordingSession(dialect_name="sqlite")
    await _acquire_course_import_lock(
        cast(AsyncSession, cast(Any, recording)),
        "quantum-physics-2026-fall",
    )
    assert recording.calls == []


def test_structural_relations_are_checked_against_closed_world_ontology() -> None:
    _validate_structural_triple(
        relation_id="valid-prerequisite",
        source_type=GraphNodeType.CONCEPT,
        relation_type=GraphRelationType.PREREQUISITE_OF,
        target_type=GraphNodeType.CONCEPT,
    )
    with pytest.raises(StructuralImportError, match="closed-world ontology rejected"):
        _validate_structural_triple(
            relation_id="invalid-concept-parent",
            source_type=GraphNodeType.CONCEPT,
            relation_type=GraphRelationType.PART_OF,
            target_type=GraphNodeType.CONCEPT,
        )
