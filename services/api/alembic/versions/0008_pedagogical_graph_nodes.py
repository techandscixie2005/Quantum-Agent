"""Add derivation steps, assumptions and validity conditions to reviewed knowledge.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = (
    "course", "chapter", "section", "source_document", "source_chunk", "evidence",
    "concept", "principle", "physical_system", "mathematical_object", "operator",
    "quantum_state", "approximation", "formula", "symbol", "derivation", "example",
    "exercise", "misconception", "hint", "experiment", "visualization", "project",
)
_NEW = (*_OLD, "derivation_step", "assumption", "validity_condition")


def _replace(values: tuple[str, ...]) -> None:
    bind = op.get_bind()
    objects: list[tuple[str, str, str]] = []
    if bind.dialect.name == "sqlite":
        # SQLite validates dependent views when the batch table is renamed.
        # Recreate their exact definitions around the table rebuild.
        objects = list(bind.execute(sa.text(
            "SELECT type, name, sql FROM sqlite_master WHERE type IN ('view', 'trigger') "
            "ORDER BY type DESC, name"
        )).tuples())
        for kind, name, _ in objects:
            bind.execute(sa.text(f'DROP {kind.upper()} "{name}"'))
    name = op.f("ck_graph_node_candidates_graph_node_type")
    expression = "node_type IN (" + ", ".join(repr(v) for v in values) + ")"
    with op.batch_alter_table("graph_node_candidates") as batch:
        batch.drop_constraint(name, type_="check")
        batch.create_check_constraint(name, expression)
    for _, _, definition in objects:
        bind.execute(sa.text(definition))


def upgrade() -> None:
    _replace(_NEW)


def downgrade() -> None:
    # The old constraint rejects incompatible rows instead of deleting teacher work.
    _replace(_OLD)
