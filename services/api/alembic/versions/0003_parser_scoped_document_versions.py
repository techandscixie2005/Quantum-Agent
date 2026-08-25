"""scope document-version uniqueness by parser

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-24

The original `uq_document_versions_file_hash` enforced one version per
source file hash, but a fully-scanned PDF legitimately yields two versions
of the same file: a `pymupdf` pass (no text layer, zero chunks) and a
`vision-ocr-v1` pass (rendered pages transcribed).  The parser name is part
of the deterministic version id, so uniqueness should key off the parser too.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STUDENT_VISIBLE_CHUNKS_VIEW = """
CREATE VIEW student_visible_chunks AS
SELECT
    chunk.*,
    document.course_id,
    publication.curriculum_edition_id AS publication_curriculum_edition_id,
    document.id AS source_document_id,
    document.title AS source_document_title,
    document.source_filename,
    document.authority,
    document.source_role,
    document.authority_priority,
    publication.priority AS publication_priority,
    publication.published_at
FROM document_chunks AS chunk
JOIN source_document_versions AS version
  ON version.id = chunk.document_version_id
 AND version.status = 'published'
JOIN source_documents AS document
  ON document.id = version.document_id
 AND document.status = 'published'
JOIN document_publications AS publication
  ON publication.document_version_id = version.id
 AND publication.course_id = document.course_id
 AND publication.status = 'published'
 AND (
      document.curriculum_edition_id IS NULL
      OR document.curriculum_edition_id = publication.curriculum_edition_id
 )
WHERE chunk.extraction_status = 'approved'
"""

_SQLITE_SOURCE_IDENTITY_TRIGGER = """
CREATE TRIGGER trg_source_version_identity_immutable
BEFORE UPDATE OF document_id, version_number, source_file_sha256,
  immutable_source_path ON source_document_versions
WHEN NEW.document_id <> OLD.document_id
  OR NEW.version_number <> OLD.version_number
  OR NEW.source_file_sha256 <> OLD.source_file_sha256
  OR NEW.immutable_source_path <> OLD.immutable_source_path
BEGIN
  SELECT RAISE(ABORT, 'source document version identity is immutable');
END
"""


def _drop_sqlite_dependent_view() -> bool:
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        # SQLite validates dependent views while Alembic's batch operation
        # swaps the rebuilt table.  Temporarily removing this deterministic
        # view avoids a false "missing table" failure during the rename.
        op.execute("DROP VIEW IF EXISTS student_visible_chunks")
    return sqlite


def _restore_sqlite_dependent_view(sqlite: bool) -> None:
    if sqlite:
        op.execute(_STUDENT_VISIBLE_CHUNKS_VIEW)
        # Batch table recreation also removes triggers attached to the old
        # table, so reinstall the immutable source-identity guard from 0001.
        op.execute("DROP TRIGGER IF EXISTS trg_source_version_identity_immutable")
        op.execute(_SQLITE_SOURCE_IDENTITY_TRIGGER)


def upgrade() -> None:
    # SQLite cannot ALTER constraints in place.  Alembic's batch operation
    # transparently rebuilds the table there while retaining normal ALTER
    # statements on PostgreSQL, so the same migration remains production-first
    # and testable on the repository's deterministic SQLite fixtures.
    sqlite = _drop_sqlite_dependent_view()
    try:
        with op.batch_alter_table("source_document_versions") as batch_op:
            batch_op.drop_constraint(
                "uq_document_versions_file_hash",
                type_="unique",
            )
            batch_op.create_unique_constraint(
                "uq_document_versions_parser_file_hash",
                ["document_id", "source_file_sha256", "parser_name"],
            )
    finally:
        _restore_sqlite_dependent_view(sqlite)


def downgrade() -> None:
    sqlite = _drop_sqlite_dependent_view()
    try:
        with op.batch_alter_table("source_document_versions") as batch_op:
            batch_op.drop_constraint(
                "uq_document_versions_parser_file_hash",
                type_="unique",
            )
            batch_op.create_unique_constraint(
                "uq_document_versions_file_hash",
                ["document_id", "source_file_sha256"],
            )
    finally:
        _restore_sqlite_dependent_view(sqlite)
