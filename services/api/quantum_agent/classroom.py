"""Operator-only roster provisioning; never invoked by a public endpoint."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import hash_session_token, issue_opaque_session_token
from quantum_agent.db_models import (
    Course,
    CourseMembership,
    CourseRole,
    CourseStatus,
    MembershipStatus,
    SystemRole,
    User,
    UserSession,
    UserStatus,
)


async def provision_classroom_access(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    course_id: UUID,
    role: CourseRole,
    expires_hours: int = 24,
) -> dict[str, str]:
    """Create one named identity and short-lived exchange token for a roster member.

    Existing roles are never silently changed. Institution operators must make
    role changes through their roster/identity administration process.
    """
    if role not in {CourseRole.STUDENT, CourseRole.TA, CourseRole.TEACHER}:
        raise ValueError("classroom provisioning supports student, TA or teacher")
    if not 1 <= expires_hours <= 168:
        raise ValueError("access expiry must be between 1 and 168 hours")
    if not email.strip() or "@" not in email or not display_name.strip():
        raise ValueError("a named roster identity is required")
    course = await session.get(Course, course_id)
    if course is None or course.status is not CourseStatus.ACTIVE:
        raise ValueError("an active course is required")
    user = await session.scalar(select(User).where(User.email == email.strip()))
    if user is None:
        user = User(
            email=email.strip(),
            display_name=display_name.strip(),
            system_role=SystemRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()
    if user.status is not UserStatus.ACTIVE:
        raise ValueError("inactive roster members cannot receive access")
    membership = await session.scalar(
        select(CourseMembership).where(
            CourseMembership.course_id == course_id,
            CourseMembership.user_id == user.id,
        )
    )
    if membership is None:
        session.add(
            CourseMembership(
                course_id=course_id,
                user_id=user.id,
                role=role,
                status=MembershipStatus.ACTIVE,
                joined_at=datetime.now(UTC),
            )
        )
    elif membership.status is not MembershipStatus.ACTIVE or membership.role is not role:
        raise ValueError("existing membership differs; an operator must review the roster")
    token = issue_opaque_session_token()
    expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)
    session.add(
        UserSession(
            user_id=user.id,
            session_token_sha256=hash_session_token(token),
            expires_at=expires_at,
            user_agent="classroom-access",
        )
    )
    await session.flush()
    return {
        "classroom_access_token": token,
        "user_id": str(user.id),
        "course_id": str(course_id),
        "role": role.value,
        "expires_at": expires_at.isoformat(),
    }
