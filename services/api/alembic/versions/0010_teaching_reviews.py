"""Append-only teacher learning reviews and follow-up decisions.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teaching_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(),
                  sa.ForeignKey("teaching_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_turn_id", sa.Uuid(),
                  sa.ForeignKey("teaching_turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("follow_up", sa.String(40), nullable=False),
        sa.Column("probe", sa.Text(), server_default="", nullable=False),
        sa.Column("rubric_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_teaching_reviews_edition_course", ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="reason_not_blank"),
        sa.CheckConstraint("decision IN ('confirmed', 'revise', 'needs_follow_up')",
                           name="decision_known"),
        sa.CheckConstraint(
            "follow_up IN ('continue', 'request_revision', 'revisit_prerequisite')",
            name="follow_up_known",
        ),
    )
    op.create_index("ix_teaching_reviews_conversation_created", "teaching_reviews",
                    ["conversation_id", "created_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE TRIGGER trg_teaching_reviews_append_only
            BEFORE UPDATE OR DELETE ON teaching_reviews
            FOR EACH ROW EXECUTE FUNCTION qa_reject_teaching_evidence_mutation()
        """)
    elif op.get_bind().dialect.name == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER trg_teaching_reviews_no_{operation.casefold()}
                BEFORE {operation} ON teaching_reviews
                BEGIN
                  SELECT RAISE(ABORT, 'teacher learning reviews are append-only');
                END
            """)


def downgrade() -> None:
    op.drop_table("teaching_reviews")
