"""deterministic teaching policy and learning evidence

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "answer_policies",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column(
            "mode",
            _enum(
                "teaching_mode",
                "learn_concepts",
                "review_derivations",
                "run_experiments",
                "work_on_projects",
            ),
            nullable=False,
        ),
        sa.Column("allow_full_solution", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "minimum_attempts_for_scaffold", sa.Integer(), server_default="1", nullable=False
        ),
        sa.Column(
            "minimum_attempts_for_full_solution",
            sa.Integer(),
            server_default="2",
            nullable=False,
        ),
        sa.Column("max_hint_level", sa.Integer(), server_default="3", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("policy_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "minimum_attempts_for_scaffold >= 0",
            name=op.f("ck_answer_policies_minimum_attempts_for_scaffold_nonnegative"),
        ),
        sa.CheckConstraint(
            "minimum_attempts_for_full_solution >= minimum_attempts_for_scaffold",
            name=op.f("ck_answer_policies_full_solution_after_scaffold"),
        ),
        sa.CheckConstraint(
            "max_hint_level >= 0 AND max_hint_level <= 10",
            name=op.f("ck_answer_policies_max_hint_level_range"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_answer_policies_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_answer_policies_edition_course",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_answer_policies_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_policies")),
        sa.UniqueConstraint(
            "curriculum_edition_id", "mode", name="uq_answer_policies_edition_mode"
        ),
    )
    op.create_index(
        "ix_answer_policies_scope_active",
        "answer_policies",
        ["course_id", "curriculum_edition_id", "active"],
    )

    op.create_table(
        "teaching_conversations",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("student_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "mode",
            _enum(
                "teaching_conversation_mode",
                "learn_concepts",
                "review_derivations",
                "run_experiments",
                "work_on_projects",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("teaching_conversation_status", "active", "completed", "archived"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "title IS NULL OR length(trim(title)) > 0",
            name=op.f("ck_teaching_conversations_title_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_teaching_conversations_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_teaching_conversations_edition_course",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"],
            ["users.id"],
            name=op.f("fk_teaching_conversations_student_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teaching_conversations")),
    )
    op.create_index(
        "ix_teaching_conversations_student_activity",
        "teaching_conversations",
        ["student_user_id", "course_id", "last_activity_at"],
    )

    op.create_table(
        "teaching_turns",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("student_attempt", sa.Text(), nullable=True),
        sa.Column(
            "task_kind",
            _enum(
                "teaching_task_kind",
                "concept_question",
                "derivation_check",
                "exercise_help",
                "experiment_help",
                "project_help",
            ),
            nullable=True,
        ),
        sa.Column(
            "teaching_action",
            _enum(
                "teaching_action",
                "explain_then_check",
                "ask_diagnostic_question",
                "give_progressive_hint",
                "check_derivation_step",
                "predict_then_simulate",
                "coach_project_milestone",
            ),
            nullable=True,
        ),
        sa.Column(
            "release_level",
            _enum(
                "answer_release_level",
                "question_only",
                "hint",
                "scaffold",
                "full_explanation",
                "full_solution",
            ),
            nullable=True,
        ),
        sa.Column(
            "status",
            _enum("teaching_turn_status", "running", "completed", "failed"),
            server_default="running",
            nullable=False,
        ),
        sa.Column("evidence_packet_json", JSON_TYPE, nullable=True),
        sa.Column("response_json", JSON_TYPE, nullable=True),
        sa.Column(
            "scientific_results_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("validation_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=160), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number > 0", name=op.f("ck_teaching_turns_sequence_number_positive")
        ),
        sa.CheckConstraint(
            "length(trim(user_message)) > 0",
            name=op.f("ck_teaching_turns_user_message_not_blank"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND response_json IS NOT NULL)",
            name=op.f("ck_teaching_turns_completed_has_response"),
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR (completed_at IS NOT NULL AND failure_code IS NOT NULL)",
            name=op.f("ck_teaching_turns_failed_has_code"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["teaching_conversations.id"],
            name=op.f("fk_teaching_turns_conversation_id_teaching_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teaching_turns")),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_teaching_turns_conversation_sequence",
        ),
    )
    op.create_index(
        "ix_teaching_turns_conversation_created",
        "teaching_turns",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "agent_traces",
        sa.Column("teaching_turn_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("student_user_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_version", sa.String(length=80), nullable=False),
        sa.Column("steps_json", JSON_TYPE, nullable=False),
        sa.Column("policy_snapshot_json", JSON_TYPE, nullable=False),
        sa.Column("model_gateway_status", sa.String(length=80), nullable=False),
        sa.Column("citation_validation_status", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(workflow_version)) > 0",
            name=op.f("ck_agent_traces_workflow_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_agent_traces_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_agent_traces_edition_course",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"],
            ["users.id"],
            name=op.f("fk_agent_traces_student_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teaching_turn_id"],
            ["teaching_turns.id"],
            name=op.f("fk_agent_traces_teaching_turn_id_teaching_turns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_traces")),
        sa.UniqueConstraint("teaching_turn_id", name=op.f("uq_agent_traces_teaching_turn_id")),
    )
    op.create_index(
        "ix_agent_traces_course_created", "agent_traces", ["course_id", "created_at"]
    )
    op.create_index(
        "ix_agent_traces_student_created", "agent_traces", ["student_user_id", "created_at"]
    )

    op.create_table(
        "learning_evidence",
        sa.Column("teaching_turn_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("student_user_id", sa.Uuid(), nullable=False),
        sa.Column("concept_candidate_id", sa.Uuid(), nullable=True),
        sa.Column(
            "kind",
            _enum(
                "learning_evidence_kind",
                "student_attempt",
                "diagnosis_inference",
                "check_response",
                "tool_observation",
            ),
            nullable=False,
        ),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("mastery_delta", sa.Float(), nullable=False),
        sa.Column("evidence_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(observation)) > 0",
            name=op.f("ck_learning_evidence_observation_not_blank"),
        ),
        sa.CheckConstraint(
            "mastery_delta >= -1.0 AND mastery_delta <= 1.0",
            name=op.f("ck_learning_evidence_mastery_delta_unit_interval"),
        ),
        sa.ForeignKeyConstraint(
            ["concept_candidate_id"],
            ["graph_node_candidates.id"],
            name=op.f("fk_learning_evidence_concept_candidate_id_graph_node_candidates"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_learning_evidence_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_learning_evidence_edition_course",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"],
            ["users.id"],
            name=op.f("fk_learning_evidence_student_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teaching_turn_id"],
            ["teaching_turns.id"],
            name=op.f("fk_learning_evidence_teaching_turn_id_teaching_turns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_evidence")),
    )
    op.create_index(
        "ix_learning_evidence_student_concept",
        "learning_evidence",
        ["student_user_id", "concept_candidate_id", "created_at"],
    )
    op.create_index(
        "ix_learning_evidence_course_kind",
        "learning_evidence",
        ["course_id", "kind", "created_at"],
    )
    _install_append_only_guards(op.get_bind().dialect.name)


def downgrade() -> None:
    _remove_append_only_guards(op.get_bind().dialect.name)
    op.drop_index("ix_learning_evidence_course_kind", table_name="learning_evidence")
    op.drop_index("ix_learning_evidence_student_concept", table_name="learning_evidence")
    op.drop_table("learning_evidence")
    op.drop_index("ix_agent_traces_student_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_course_created", table_name="agent_traces")
    op.drop_table("agent_traces")
    op.drop_index("ix_teaching_turns_conversation_created", table_name="teaching_turns")
    op.drop_table("teaching_turns")
    op.drop_index(
        "ix_teaching_conversations_student_activity", table_name="teaching_conversations"
    )
    op.drop_table("teaching_conversations")
    op.drop_index("ix_answer_policies_scope_active", table_name="answer_policies")
    op.drop_table("answer_policies")


def _install_append_only_guards(dialect: str) -> None:
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION qa_reject_teaching_evidence_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'teaching traces and learning evidence are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table_name in ("agent_traces", "learning_evidence"):
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION qa_reject_teaching_evidence_mutation()
                """
            )
    elif dialect == "sqlite":
        for table_name in ("agent_traces", "learning_evidence"):
            for operation in ("UPDATE", "DELETE"):
                op.execute(
                    f"""
                    CREATE TRIGGER trg_{table_name}_no_{operation.casefold()}
                    BEFORE {operation} ON {table_name}
                    BEGIN
                      SELECT RAISE(ABORT, 'teaching traces and learning evidence are append-only');
                    END
                    """
                )


def _remove_append_only_guards(dialect: str) -> None:
    if dialect == "postgresql":
        for table_name in ("agent_traces", "learning_evidence"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute("DROP FUNCTION IF EXISTS qa_reject_teaching_evidence_mutation()")
    elif dialect == "sqlite":
        for table_name in ("agent_traces", "learning_evidence"):
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_{operation}")
