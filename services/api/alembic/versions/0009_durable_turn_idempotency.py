"""Index immutable turn request identities, including first-turn retries.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teaching_turns", sa.Column("client_request_id", sa.String(128), nullable=True))
    op.add_column("teaching_turns", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.create_index("ix_teaching_turns_client_request_id", "teaching_turns", ["client_request_id"])
    # Preserve legacy retries through interruptions as well as completion.
    turns = sa.table(
        "teaching_turns", sa.column("id", sa.Uuid()),
        sa.column("validation_json", sa.JSON()),
        sa.column("scientific_results_json", sa.JSON()),
        sa.column("client_request_id", sa.String(128)),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(turns)).mappings():
        key = (row["validation_json"] or {}).get("client_request_id") or (
            row["scientific_results_json"] or {}
        ).get("__client_request_id")
        if isinstance(key, str) and key.strip():
            connection.execute(
                turns.update().where(turns.c.id == row["id"]).values(client_request_id=key)
            )


def downgrade() -> None:
    op.drop_index("ix_teaching_turns_client_request_id", table_name="teaching_turns")
    op.drop_column("teaching_turns", "request_fingerprint")
    op.drop_column("teaching_turns", "client_request_id")
