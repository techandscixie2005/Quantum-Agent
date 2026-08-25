"""Backend-enforced authentication and course authorization.

The API accepts opaque bearer sessions issued by an upstream identity/login
flow.  Only a SHA-256 digest is stored.  Prompts and model output never take
part in authorization decisions.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.db_models import (
    CourseMembership,
    CourseRole,
    MembershipStatus,
    SessionStatus,
    SystemRole,
    User,
    UserSession,
    UserStatus,
)


class CredentialTransport(StrEnum):
    BEARER = "bearer"


class SessionCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str
    transport: CredentialTransport = CredentialTransport.BEARER


class CourseActor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    session_id: UUID
    course_id: UUID
    email: str
    display_name: str
    system_role: SystemRole
    course_role: CourseRole


def issue_opaque_session_token() -> str:
    """Create a high-entropy token suitable for a separate login/SSO flow."""

    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_credential(request: Request) -> SessionCredential:
    """Extract an opaque bearer token without supporting insecure fallbacks."""

    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = token.strip()
    if not 32 <= len(token) <= 512:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return SessionCredential(token=token)


def _active_actor_query(
    *,
    token_sha256: str,
    course_id: UUID,
    now: datetime,
) -> Select[tuple[UserSession, User, CourseMembership]]:
    return (
        select(UserSession, User, CourseMembership)
        .join(User, User.id == UserSession.user_id)
        .join(
            CourseMembership,
            (CourseMembership.user_id == User.id)
            & (CourseMembership.course_id == course_id),
        )
        .where(
            UserSession.session_token_sha256 == token_sha256,
            UserSession.status == SessionStatus.ACTIVE,
            UserSession.expires_at > now,
            User.status == UserStatus.ACTIVE,
            CourseMembership.status == MembershipStatus.ACTIVE,
        )
    )


async def authenticate_course_actor(
    session: AsyncSession,
    *,
    credential: SessionCredential,
    course_id: UUID,
    allowed_roles: frozenset[CourseRole] | None = None,
) -> CourseActor:
    """Authenticate and authorize an actor against durable backend state."""

    digest = hash_session_token(credential.token)
    result = await session.execute(
        _active_actor_query(token_sha256=digest, course_id=course_id, now=datetime.now(UTC))
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_session, user, membership = row
    if allowed_roles is not None and membership.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient course permissions",
        )
    return CourseActor(
        user_id=user.id,
        session_id=user_session.id,
        course_id=course_id,
        email=user.email,
        display_name=user.display_name,
        system_role=user.system_role,
        course_role=membership.role,
    )


TEACHING_STAFF_ROLES = frozenset({CourseRole.TA, CourseRole.TEACHER, CourseRole.ADMIN})
TEACHER_ROLES = frozenset({CourseRole.TEACHER, CourseRole.ADMIN})


__all__ = [
    "TEACHER_ROLES",
    "TEACHING_STAFF_ROLES",
    "CourseActor",
    "CredentialTransport",
    "SessionCredential",
    "authenticate_course_actor",
    "bearer_credential",
    "hash_session_token",
    "issue_opaque_session_token",
]
