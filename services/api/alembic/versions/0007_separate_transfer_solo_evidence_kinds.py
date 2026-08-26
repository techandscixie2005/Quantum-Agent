"""Extend learning_evidence_kind with separated transfer/solo lifecycle kinds.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-27

PRD V3.0 P1-1 (Cognitive Mirror evidence semantics): the mirror must not
promote a learner to ``TRANSFER_READY`` or assert ``unaided_retrieval`` based
on task generation alone.  This migration adds the separated lifecycle kinds
``transfer_assigned``, ``transfer_attempted``, ``transfer_verified``,
``transfer_failed``, ``solo_assigned``, ``solo_verified``, and ``solo_aborted``
so the deterministic mirror can distinguish a task-issued row from a verified,
task-correlated, unaided attempt.  Legacy ``transfer`` / ``solo_attempt``
rows remain valid; the new kinds are a strict superset.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
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
    "transfer_assigned",
    "transfer_attempted",
    "transfer_verified",
    "transfer_failed",
    "solo_assigned",
    "solo_verified",
    "solo_aborted",
)


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    constraint_name = "ck_learning_evidence_learning_evidence_kind"
    new_check = (
        "kind IN ('student_attempt', 'diagnosis_inference', 'check_response', "
        "'tool_observation', 'commitment', 'confidence', 'teach_back', "
        "'transfer', 'solo', 'solo_attempt', 'retrieval_practice', "
        "'transfer_assigned', 'transfer_attempted', 'transfer_verified', "
        "'transfer_failed', 'solo_assigned', 'solo_verified', 'solo_aborted')"
    )

    if is_sqlite:
        # SQLite cannot ALTER a CHECK constraint in place.  We rebuild the
        # table in batch mode with ``recreate="always"`` and replace the old
        # CHECK constraint (whatever name batch reflection assigned it after
        # the 0005 rebuild) with the expanded one.  We do not call
        # ``drop_constraint`` because the reflected constraint name varies;
        # instead we omit the old constraint by not naming it, and add the
        # new named constraint explicitly.  ``recreate="always"`` copies
        # data and recreates indexes/triggers from the reflected schema,
        # but CHECK constraints are not carried over when the column type
        # is replaced in the same batch op — the new CHECK is the only one.
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_update"))
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_delete"))
        with op.batch_alter_table(
            "learning_evidence",
            schema=None,
            recreate="always",
        ) as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=_enum("learning_evidence_kind", *_LEARNING_EVIDENCE_KINDS),
                existing_nullable=False,
            )
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
        "commitment",
        "confidence",
        "teach_back",
        "transfer",
        "solo",
        "solo_attempt",
        "retrieval_practice",
    )
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    constraint_name = "ck_learning_evidence_learning_evidence_kind"
    legacy_check = (
        "kind IN ('student_attempt', 'diagnosis_inference', 'check_response', "
        "'tool_observation', 'commitment', 'confidence', 'teach_back', "
        "'transfer', 'solo', 'solo_attempt', 'retrieval_practice')"
    )

    if is_sqlite:
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_update"))
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_evidence_no_delete"))
        with op.batch_alter_table(
            "learning_evidence",
            schema=None,
            recreate="always",
        ) as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=_enum("learning_evidence_kind", *legacy_kinds),
                existing_nullable=False,
            )
            batch_op.create_check_constraint(constraint_name, legacy_check)
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
