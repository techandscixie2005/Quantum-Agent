"""Add learning_phase_json to teaching_conversations for durable Learning-Native state.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-26

PRD V3.0 P0-2: the Learning-Native journey (commitment → attempt → intervention
→ reconstruction → transfer → solo → complete) must be a durable state machine
persisted server-side, not a set of optional UI submissions.  This migration
adds a ``learning_phase_json`` column to ``teaching_conversations`` so the
tutor graph can load the current phase BEFORE answer generation and route
deterministically (e.g. block Ask AI while Solo is active, require a
teach-back reconstruction before advancing).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teaching_conversations",
        sa.Column("learning_phase_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("teaching_conversations", "learning_phase_json")
