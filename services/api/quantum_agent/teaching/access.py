"""Persisted Solo restrictions shared by student evidence entry points."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.db_models import CourseRole, TeachingConversation, TeachingConversationStatus


async def require_evidence_access(session: AsyncSession, actor: CourseActor) -> None:
    """Do not let another tab omit the episode id to obtain active assistance.

    The lock is scoped to this student and course, independent of browser state.
    Existing course files cannot be revoked from a student's external downloads.
    """
    if actor.course_role is not CourseRole.STUDENT:
        return
    phases = await session.scalars(
        select(TeachingConversation.learning_phase_json).where(
            TeachingConversation.course_id == actor.course_id,
            TeachingConversation.student_user_id == actor.user_id,
            TeachingConversation.status == TeachingConversationStatus.ACTIVE,
        ).with_for_update()
    )
    if any(
        phase.get("phase") == "solo_active" or phase.get("solo_assistance_locked") is True
        for phase in phases if phase is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="Solo 正在进行: 课程依据与提示暂不可用。请提交独立作答或明确退出 Solo。",
        )
