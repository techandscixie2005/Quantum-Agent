"""student attachments and multimodal extraction provenance

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-24

Student uploads are deliberately isolated from ``source_documents`` and
``extraction_runs``.  Only the latter participate in teacher-reviewed course
publication.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "user_attachments",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            _enum("attachment_kind", "image", "document", "text"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("detected_media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("attachment_status", "quarantined", "ready", "rejected", "deleted"),
            server_default="quarantined",
            nullable=False,
        ),
        sa.Column("validation_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("rejection_code", sa.String(length=160), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(original_filename)) > 0",
            name=op.f("ck_user_attachments_filename_not_blank"),
        ),
        sa.CheckConstraint("byte_size > 0", name=op.f("ck_user_attachments_byte_size_positive")),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name=op.f("ck_user_attachments_content_hash_sha256_length"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('ready', 'quarantined') OR storage_key IS NOT NULL",
            name=op.f("ck_user_attachments_stored_status_has_key"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR rejection_code IS NOT NULL",
            name=op.f("ck_user_attachments_rejected_has_code"),
        ),
        sa.CheckConstraint(
            "status <> 'deleted' OR deleted_at IS NOT NULL",
            name=op.f("ck_user_attachments_deleted_has_timestamp"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_user_attachments_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_user_attachments_edition_course",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_user_attachments_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_attachments")),
        sa.UniqueConstraint(
            "course_id",
            "curriculum_edition_id",
            "owner_user_id",
            "content_sha256",
            name="uq_user_attachments_owner_scope_hash",
        ),
        sa.UniqueConstraint(
            "id",
            "course_id",
            "curriculum_edition_id",
            "owner_user_id",
            name="uq_user_attachments_id_scope_owner",
        ),
    )
    op.create_index(
        "ix_user_attachments_owner_scope_created",
        "user_attachments",
        ["owner_user_id", "course_id", "curriculum_edition_id", "created_at"],
    )
    op.create_index(
        "ix_user_attachments_scope_status",
        "user_attachments",
        ["course_id", "curriculum_edition_id", "status"],
    )

    op.create_table(
        "multimodal_extractions",
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            _enum("multimodal_extraction_kind", "vision", "document"),
            nullable=False,
        ),
        sa.Column("pipeline_name", sa.String(length=200), nullable=False),
        sa.Column("pipeline_version", sa.String(length=100), nullable=False),
        sa.Column("extraction_method", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            _enum(
                "multimodal_extraction_status",
                "pending",
                "running",
                "needs_confirmation",
                "succeeded",
                "confirmed",
                "rejected",
                "failed",
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("raw_output_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("evidence_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("ambiguities_json", JSON_TYPE, server_default=sa.text("'[]'"), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("failure_code", sa.String(length=160), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(pipeline_name)) > 0",
            name=op.f("ck_multimodal_extractions_pipeline_name_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(pipeline_version)) > 0",
            name=op.f("ck_multimodal_extractions_pipeline_version_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(extraction_method)) > 0",
            name=op.f("ck_multimodal_extractions_method_not_blank"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name=op.f("ck_multimodal_extractions_confidence_unit_interval"),
        ),
        sa.CheckConstraint(
            "status <> 'needs_confirmation' OR requires_confirmation",
            name=op.f("ck_multimodal_extractions_confirmation_status_requires_confirmation"),
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR "
            "(confirmed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name=op.f("ck_multimodal_extractions_confirmed_has_actor_and_timestamp"),
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR failure_code IS NOT NULL",
            name=op.f("ck_multimodal_extractions_failed_has_code"),
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id", "course_id", "curriculum_edition_id", "owner_user_id"],
            [
                "user_attachments.id",
                "user_attachments.course_id",
                "user_attachments.curriculum_edition_id",
                "user_attachments.owner_user_id",
            ],
            name="fk_multimodal_extractions_attachment_scope_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name=op.f("fk_multimodal_extractions_confirmed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_multimodal_extractions")),
        sa.UniqueConstraint(
            "attachment_id",
            "pipeline_name",
            "pipeline_version",
            name="uq_multimodal_extractions_attachment_pipeline",
        ),
        sa.UniqueConstraint("id", "attachment_id", name="uq_multimodal_extractions_id_attachment"),
    )
    op.create_index(
        "ix_multimodal_extractions_attachment_status",
        "multimodal_extractions",
        ["attachment_id", "status"],
    )
    op.create_index(
        "ix_multimodal_extractions_owner_created",
        "multimodal_extractions",
        ["owner_user_id", "course_id", "created_at"],
    )

    op.create_table(
        "document_parse_runs",
        sa.Column("attachment_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_edition_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_name", sa.String(length=200), nullable=False),
        sa.Column("pipeline_version", sa.String(length=100), nullable=False),
        sa.Column("selected_method", sa.String(length=100), nullable=False),
        sa.Column("parser_name", sa.String(length=200), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            _enum(
                "document_parse_run_status",
                "pending",
                "running",
                "succeeded",
                "partial",
                "failed",
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("slide_count", sa.Integer(), nullable=True),
        sa.Column("fallback_chain_json", JSON_TYPE, server_default=sa.text("'[]'"), nullable=False),
        sa.Column("provenance_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("output_json", JSON_TYPE, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(pipeline_name)) > 0",
            name=op.f("ck_document_parse_runs_pipeline_name_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(pipeline_version)) > 0",
            name=op.f("ck_document_parse_runs_pipeline_version_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(selected_method)) > 0",
            name=op.f("ck_document_parse_runs_method_not_blank"),
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name=op.f("ck_document_parse_runs_page_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "slide_count IS NULL OR slide_count >= 0",
            name=op.f("ck_document_parse_runs_slide_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR slide_count IS NULL",
            name=op.f("ck_document_parse_runs_page_or_slide_count_not_both"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('succeeded', 'partial', 'failed') OR completed_at IS NOT NULL",
            name=op.f("ck_document_parse_runs_terminal_has_completed_at"),
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR error_code IS NOT NULL",
            name=op.f("ck_document_parse_runs_failed_has_code"),
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id", "course_id", "curriculum_edition_id", "owner_user_id"],
            [
                "user_attachments.id",
                "user_attachments.course_id",
                "user_attachments.curriculum_edition_id",
                "user_attachments.owner_user_id",
            ],
            name="fk_document_parse_runs_attachment_scope_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id", "attachment_id"],
            ["multimodal_extractions.id", "multimodal_extractions.attachment_id"],
            name="fk_document_parse_runs_extraction_attachment",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_parse_runs")),
        sa.UniqueConstraint(
            "attachment_id",
            "pipeline_name",
            "pipeline_version",
            name="uq_document_parse_runs_attachment_pipeline",
        ),
    )
    op.create_index(
        "ix_document_parse_runs_attachment_created",
        "document_parse_runs",
        ["attachment_id", "created_at"],
    )
    op.create_index(
        "ix_document_parse_runs_scope_status",
        "document_parse_runs",
        ["course_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_parse_runs_scope_status", table_name="document_parse_runs")
    op.drop_index("ix_document_parse_runs_attachment_created", table_name="document_parse_runs")
    op.drop_table("document_parse_runs")
    op.drop_index("ix_multimodal_extractions_owner_created", table_name="multimodal_extractions")
    op.drop_index(
        "ix_multimodal_extractions_attachment_status", table_name="multimodal_extractions"
    )
    op.drop_table("multimodal_extractions")
    op.drop_index("ix_user_attachments_scope_status", table_name="user_attachments")
    op.drop_index("ix_user_attachments_owner_scope_created", table_name="user_attachments")
    op.drop_table("user_attachments")
