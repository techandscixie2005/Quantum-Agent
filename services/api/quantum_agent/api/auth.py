"""Competition demo-account login (PRD V3.0 P1-4).

The production identity story is an upstream SSO/login service that issues
opaque session tokens.  For the competition demo, we provide a minimal,
explicitly-gated bootstrap: when ``DEMO_LOGIN_SECRET`` is configured, a judge
can POST the shared secret to ``/api/v1/auth/demo-login`` and receive a
short-lived student session token for the seeded demo account.  The route is
fail-closed when the secret is unset, and it never runs in production.

This is NOT a substitute for real SSO.  It exists so a judge can enter
``/agent`` without manually seeding a database row or injecting a cookie.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import (
    hash_session_token,
    issue_opaque_session_token,
)
from quantum_agent.config import Settings
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    Course,
    CourseMembership,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    MembershipStatus,
    SessionStatus,
    User,
    UserSession,
    UserStatus,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


class DemoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    secret: str = Field(min_length=8, max_length=256)
    course_id: str | None = Field(default=None, max_length=64)


class DemoLoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_token: str
    course_id: str
    curriculum_edition_id: str
    user_id: str
    display_name: str
    expires_at: str


def _settings(request: Request) -> Settings:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise HTTPException(status_code=500, detail="server settings unavailable")
    return settings


@router.post("/demo-login", response_model=DemoLoginResponse)
async def demo_login(
    request: Request,
    body: DemoLoginRequest,
    session: DatabaseSession,
) -> DemoLoginResponse:
    settings = _settings(request)
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="demo login is not available in production")
    expected = settings.demo_login_secret
    if expected is None:
        raise HTTPException(status_code=404, detail="demo login is not configured")
    if expected.get_secret_value() != body.secret:
        raise HTTPException(status_code=401, detail="invalid demo secret")

    now = datetime.now(UTC)
    email = settings.demo_login_course_email

    user = await session.scalar(select(User).where(User.email == email).limit(1))
    if user is None:
        raise HTTPException(
            status_code=409,
            detail="demo account not seeded; run `quantum-agent seed-demo-account` first",
        )
    if user.status is not UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="demo account is not active")

    # Resolve the demo course membership.  If the caller supplied a course
    # id, use it; otherwise pick the first active course the demo student is
    # a member of.
    membership: CourseMembership | None = None
    if body.course_id is not None:
        membership = await session.scalar(
            select(CourseMembership).where(
                CourseMembership.user_id == user.id,
                CourseMembership.course_id == body.course_id,
                CourseMembership.status == MembershipStatus.ACTIVE,
            )
        )
    else:
        membership = await session.scalar(
            select(CourseMembership)
            .where(
                CourseMembership.user_id == user.id,
                CourseMembership.status == MembershipStatus.ACTIVE,
            )
            .order_by(CourseMembership.joined_at.desc())
            .limit(1)
        )
    if membership is None:
        raise HTTPException(
            status_code=409,
            detail="demo account has no active course membership; run `make demo-bootstrap`",
        )

    course = await session.scalar(select(Course).where(Course.id == membership.course_id))
    if course is None or course.status is not CourseStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="demo course is not active")

    edition = await session.scalar(
        select(CurriculumEdition)
        .where(
            CurriculumEdition.course_id == course.id,
            CurriculumEdition.status == CurriculumEditionStatus.PUBLISHED,
        )
        .order_by(CurriculumEdition.published_at.desc())
        .limit(1)
    )
    if edition is None:
        raise HTTPException(
            status_code=409,
            detail="demo course has no published curriculum edition",
        )

    raw_token = issue_opaque_session_token()
    session.add(
        UserSession(
            user_id=user.id,
            session_token_sha256=hash_session_token(raw_token),
            status=SessionStatus.ACTIVE,
            expires_at=now + timedelta(hours=8),
            user_agent="quantum-agent-demo-login",
        )
    )
    await session.commit()

    return DemoLoginResponse(
        session_token=raw_token,
        course_id=str(course.id),
        curriculum_edition_id=str(edition.id),
        user_id=str(user.id),
        display_name=user.display_name,
        expires_at=(now + timedelta(hours=8)).isoformat(),
    )


__all__ = ["router"]
