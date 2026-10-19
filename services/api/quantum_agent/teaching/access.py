"""Persisted Solo restrictions shared by student evidence entry points."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    CourseRole,
    TeachingConversation,
    TeachingConversationStatus,
    User,
)


class TeachingConversationConflictError(RuntimeError):
    """Conversation or assistance is unavailable in the student's current scope."""


async def require_conversation_assistance_access(
    session: AsyncSession, actor: CourseActor, conversation_id: UUID | None,
) -> None:
    """Allow only bounded participation in an active Solo episode in this course.

    This includes other editions and tabs. The student row lock serializes the
    check with turn starts/Solo arming across workers. Staff retain oversight.
    """

    if actor.course_role is not CourseRole.STUDENT:
        return
    await session.scalar(select(User.id).where(User.id == actor.user_id).with_for_update())
    active_solo = select(TeachingConversation.id).where(
        TeachingConversation.course_id == actor.course_id,
        TeachingConversation.student_user_id == actor.user_id,
        TeachingConversation.status == TeachingConversationStatus.ACTIVE,
        or_(
            TeachingConversation.learning_phase_json["phase"].as_string() == "solo_active",
            TeachingConversation.learning_phase_json["solo_assistance_locked"].as_boolean().is_(True),
        ),
    )
    first_solo = await session.scalar(active_solo.limit(1))
    if first_solo is None or first_solo == conversation_id:
        return
    if conversation_id is not None and await session.scalar(
        active_solo.where(TeachingConversation.id == conversation_id).limit(1)
    ) is not None:
        # Also permits explicit exits if old data contains multiple active Solo
        # episodes. Every such episode retains its own assistance projection.
        return
    raise TeachingConversationConflictError(
        "Solo is active in this course; submit or explicitly exit that episode "
        "before obtaining help"
    )


async def require_evidence_access(session: AsyncSession, actor: CourseActor) -> None:
    """Do not let another tab omit the episode id to obtain active assistance.

    The lock is scoped to this student and course, independent of browser state.
    Existing course files cannot be revoked from a student's external downloads.
    """
    try:
        await require_conversation_assistance_access(session, actor, None)
    except TeachingConversationConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Solo 正在进行: 课程依据与提示暂不可用。请提交独立作答或明确退出 Solo。",
        ) from exc
