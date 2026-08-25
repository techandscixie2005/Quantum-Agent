"""Authenticated course and edition context for the standalone Agent UI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import bearer_credential, hash_session_token
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    CurriculumUnit,
    CurriculumUnitType,
    MembershipStatus,
    SessionStatus,
    User,
    UserSession,
    UserStatus,
)

router = APIRouter(prefix="/api/v1/me", tags=["student-context"])
DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


class ChapterContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    ordinal: int
    title: str
    canonical_path: str


class CourseEditionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    course_code: str
    course_title: str
    institution: str
    role: CourseRole
    curriculum_edition_id: UUID
    edition_title: str
    academic_year: str | None
    term: str | None
    chapters: list[ChapterContext]


class StudentCourseContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    display_name: str
    courses: list[CourseEditionContext]


@router.get("/course-context", response_model=StudentCourseContext)
async def course_context(
    request: Request,
    session: DatabaseSession,
) -> StudentCourseContext:
    """Resolve published course scopes server-side instead of trusting UI UUIDs."""

    credential = bearer_credential(request)
    now = datetime.now(UTC)
    identity = (
        await session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.session_token_sha256 == hash_session_token(credential.token),
                UserSession.status == SessionStatus.ACTIVE,
                UserSession.expires_at > now,
                User.status == UserStatus.ACTIVE,
            )
        )
    ).one_or_none()
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_session, user = identity
    rows = (
        await session.execute(
            select(CourseMembership, Course, CurriculumEdition)
            .join(Course, Course.id == CourseMembership.course_id)
            .join(CurriculumEdition, CurriculumEdition.course_id == Course.id)
            .where(
                CourseMembership.user_id == user.id,
                CourseMembership.status == MembershipStatus.ACTIVE,
                Course.status == CourseStatus.ACTIVE,
                CurriculumEdition.status == CurriculumEditionStatus.PUBLISHED,
            )
            .order_by(
                Course.code.asc(),
                CurriculumEdition.published_at.desc(),
                CurriculumEdition.id.asc(),
            )
        )
    ).all()
    edition_ids = [edition.id for _, _, edition in rows]
    chapter_rows = (
        (
            await session.execute(
                select(CurriculumUnit)
                .where(
                    CurriculumUnit.curriculum_edition_id.in_(edition_ids),
                    CurriculumUnit.unit_type == CurriculumUnitType.CHAPTER,
                )
                .order_by(
                    CurriculumUnit.curriculum_edition_id.asc(),
                    CurriculumUnit.ordinal.asc(),
                    CurriculumUnit.id.asc(),
                )
            )
        ).scalars().all()
        if edition_ids
        else []
    )
    chapters_by_edition: dict[UUID, list[ChapterContext]] = {}
    for chapter in chapter_rows:
        chapters_by_edition.setdefault(chapter.curriculum_edition_id, []).append(
            ChapterContext(
                id=chapter.id,
                ordinal=chapter.ordinal,
                title=chapter.title,
                canonical_path=chapter.canonical_path,
            )
        )
    user_session.last_seen_at = now
    await session.commit()
    return StudentCourseContext(
        user_id=user.id,
        display_name=user.display_name,
        courses=[
            CourseEditionContext(
                course_id=course.id,
                course_code=course.code,
                course_title=course.title,
                institution=course.institution,
                role=membership.role,
                curriculum_edition_id=edition.id,
                edition_title=edition.title,
                academic_year=edition.academic_year,
                term=edition.term,
                chapters=chapters_by_edition.get(edition.id, []),
            )
            for membership, course, edition in rows
        ],
    )


__all__ = ["ChapterContext", "CourseEditionContext", "StudentCourseContext", "router"]
