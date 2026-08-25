"""Extend learning_evidence_kind with Learning-Native observation kinds.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-26

PRD V3.0 introduces the Learning-Native cognitive runtime.  The
``learning_evidence`` table already existed with a small set of observation
kinds (student_attempt, diagnosis_inference, check_response, tool_observation).
This migration extends the enum so the deterministic Learning-Native policy
can persist commitment, confidence, teach_back, transfer, solo, solo_attempt,
and retrieval_practice observations.  No data is rewritten; existing rows
remain valid because their kinds are a subset of the new enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


_LEARNING_EVIDENCE_KINDS = (
    "student_attempt",
    "diagnosis_inference",
    "check_response",
    "tool_observation",
    "commitment",
    "confidence",
    "teach_back",
    "transfer",
    "solo",
    "solo_attempt",
    "retrieval_practice",
)


def upgrade() -> None:
    # The ``learning_evidence`` table is append-only (BEFORE DELETE / UPDATE
    # triggers block mutations).  Batch-mode table rebuilds therefore need
    # the triggers dropped first and recreated after the column type changes.
    # On PostgreSQL the direct ``alter_column`` works without touching the
    # triggers, so we branch on the dialect.
    #
    # The original CHECK constraint (from migration 0002) only allowed four
    # kinds.  We replace it with one that admits every Learning-Native kind.
    # On SQLite this requires a batch-mode table rebuild (SQLite cannot
    # ALTER a CHECK constraint in place); on PostgreSQL a direct
    # drop/create_constraint suffices.
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    constraint_name = "ck_learning_evidence_learning_evidence_kind"
    new_check = (
        "kind IN ('student_attempt', 'diagnosis_inference', 'check_response', "
        "'tool_observation', 'commitment', 'confidence', 'teach_back', "
        "'transfer', 'solo', 'solo_attempt', 'retrieval_practice')"
    )

    if is_sqlite:
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_update"))
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_delete"))
        with op.batch_alter_table("learning_evidence", schema=None) as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=_enum("learning_evidence_kind", *_LEARNING_EVIDENCE_KINDS),
                existing_nullable=False,
            )
            batch_op.drop_constraint("learning_evidence_kind", type_="check")
            batch_op.create_check_constraint(constraint_name, new_check)
        bind.execute(
            sa.text(
                """
                CREATE TRIGGER trg_learning_evidence_no_update
                    BEFORE UPDATE ON learning_evidence
                    BEGIN
                      SELECT RAISE(ABORT, 'teaching traces and learning evidence are append-only');
                    END
                """
            )
        )
        bind.execute(
            sa.text(
                """
                CREATE TRIGGER trg_learning_evidence_no_delete
                    BEFORE DELETE ON learning_evidence
                    BEGIN
                      SELECT RAISE(ABORT, 'teaching traces and learning evidence are append-only');
                    END
                """
            )
        )
    else:
        # PostgreSQL: replace the CHECK constraint in place.  We use raw SQL
        # because the Alembic ``op.drop_constraint``/``create_check_constraint``
        # wrappers add quoting that differs from the original 0002 constraint
        # definition; raw SQL keeps the constraint body identical to what
        # migration 0002 would have produced for the expanded kind set.
        op.execute(f"ALTER TABLE learning_evidence DROP CONSTRAINT {constraint_name}")
        op.execute(
            f"ALTER TABLE learning_evidence ADD CONSTRAINT {constraint_name} "
            f"CHECK ({new_check})"
        )


def downgrade() -> None:
    legacy_kinds = (
        "student_attempt",
        "diagnosis_inference",
        "check_response",
        "tool_observation",
    )
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    constraint_name = "ck_learning_evidence_learning_evidence_kind"
    legacy_check = (
        "kind IN ('student_attempt', 'diagnosis_inference', 'check_response', 'tool_observation')"
    )

    if is_sqlite:
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_update"))
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_delete"))
        with op.batch_alter_table("learning_evidence", schema=None) as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=_enum("learning_evidence_kind", *legacy_kinds),
                existing_nullable=False,
            )
        bind.execute(
            sa.text(
                """
                CREATE TRIGGER trg_learning_evidence_no_update
                    BEFORE UPDATE ON learning_evidence
                    BEGIN
                      SELECT RAISE(ABORT, 'teaching traces and learning evidence are append-only');
                    END
                """
            )
        )
        bind.execute(
            sa.text(
                """
                CREATE TRIGGER trg_learning_evidence_no_delete
                    BEFORE DELETE ON learning_evidence
                    BEGIN
                      SELECT RAISE(ABORT, 'teaching traces and learning evidence are append-only');
                    END
                """
            )
        )
    else:
        op.execute(f"ALTER TABLE learning_evidence DROP CONSTRAINT {constraint_name}")
        op.execute(
            f"ALTER TABLE learning_evidence ADD CONSTRAINT {constraint_name} "
            f"CHECK ({legacy_check})"
        )
