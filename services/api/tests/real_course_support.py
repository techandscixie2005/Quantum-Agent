"""Publish a real textbook inside isolated SQLite smoke-test databases only."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.db_models import SourceDocument, SourceDocumentVersion
from quantum_agent.knowledge.review import ReviewService

TEXTBOOK_FILENAME = "Yan_QPhys.pdf"


async def publish_test_textbook(
    session: AsyncSession, actor: CourseActor, edition_id: UUID,
) -> tuple[UUID, UUID]:
    assert session.get_bind().dialect.name == "sqlite"
    document, version = (await session.execute(
        select(SourceDocument, SourceDocumentVersion)
        .join(SourceDocumentVersion, SourceDocumentVersion.document_id == SourceDocument.id)
        .where(SourceDocument.course_id == actor.course_id,
               SourceDocument.source_filename == TEXTBOOK_FILENAME)
    )).one()
    review = ReviewService(session)
    await review.approve_document_version(
        actor=actor, curriculum_edition_id=edition_id, document_version_id=version.id,
        rationale="Isolated smoke fixture: exact native textbook page provenance.",
    )
    await review.publish_document_version(
        actor=actor, curriculum_edition_id=edition_id, document_version_id=version.id,
        rationale="Isolated smoke fixture: use textbook prose for teaching evidence.",
        priority=90,
    )
    return document.id, version.id
