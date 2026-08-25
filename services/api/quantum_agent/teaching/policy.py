"""Teacher-configured, deterministic answer-release decisions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.db_models import (
    AnswerPolicy,
    AnswerReleaseLevel,
    TeachingAction,
    TeachingConversation,
    TeachingMode,
    TeachingTaskKind,
    TeachingTurn,
)
from quantum_agent.knowledge.evidence_packets import RetrievalCoverage
from quantum_agent.teaching.models import PolicySnapshot, ReleaseDecision


def safe_default_policy(mode: TeachingMode) -> PolicySnapshot:
    """Fail-conservative defaults used until a teacher publishes a policy."""

    return PolicySnapshot(
        source="safe_default",
        mode=mode,
        allow_full_solution=False,
        minimum_attempts_for_scaffold=1,
        minimum_attempts_for_full_solution=2,
        max_hint_level=3,
    )


class AnswerPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        mode: TeachingMode,
    ) -> PolicySnapshot:
        policy = await self._session.scalar(
            select(AnswerPolicy).where(
                AnswerPolicy.course_id == course_id,
                AnswerPolicy.curriculum_edition_id == curriculum_edition_id,
                AnswerPolicy.mode == mode,
                AnswerPolicy.active.is_(True),
            )
        )
        if policy is None:
            return safe_default_policy(mode)
        return PolicySnapshot(
            policy_id=policy.id,
            source="teacher_configured",
            mode=policy.mode,
            allow_full_solution=policy.allow_full_solution,
            minimum_attempts_for_scaffold=policy.minimum_attempts_for_scaffold,
            minimum_attempts_for_full_solution=policy.minimum_attempts_for_full_solution,
            max_hint_level=policy.max_hint_level,
        )

    async def count_prior_attempts(self, conversation_id: UUID) -> int:
        count = await self._session.scalar(
            select(func.count(TeachingTurn.id))
            .join(
                TeachingConversation,
                TeachingConversation.id == TeachingTurn.conversation_id,
            )
            .where(
                TeachingTurn.conversation_id == conversation_id,
                TeachingTurn.student_attempt.is_not(None),
                func.length(func.trim(TeachingTurn.student_attempt)) > 0,
            )
        )
        return int(count or 0)


class AnswerReleaseEngine:
    """Pure policy engine. Models cannot override these decisions."""

    @staticmethod
    def decide(
        *,
        mode: TeachingMode,
        task_kind: TeachingTaskKind,
        policy: PolicySnapshot,
        prior_attempts: int,
        has_current_attempt: bool,
        coverage: RetrievalCoverage,
    ) -> ReleaseDecision:
        attempts = prior_attempts + int(has_current_attempt)
        if coverage is RetrievalCoverage.NOT_FOUND:
            return ReleaseDecision(
                action=TeachingAction.ASK_DIAGNOSTIC_QUESTION,
                release_level=AnswerReleaseLevel.QUESTION_ONLY,
                attempts_observed=attempts,
                reason_code="course_evidence_not_found",
            )

        if mode is TeachingMode.LEARN_CONCEPTS and task_kind is TeachingTaskKind.CONCEPT_QUESTION:
            return ReleaseDecision(
                action=TeachingAction.EXPLAIN_THEN_CHECK,
                release_level=AnswerReleaseLevel.FULL_EXPLANATION,
                attempts_observed=attempts,
                reason_code="concept_explanation_allowed",
            )

        if mode is TeachingMode.RUN_EXPERIMENTS:
            return ReleaseDecision(
                action=TeachingAction.PREDICT_THEN_SIMULATE,
                release_level=(
                    AnswerReleaseLevel.SCAFFOLD
                    if has_current_attempt
                    else AnswerReleaseLevel.QUESTION_ONLY
                ),
                attempts_observed=attempts,
                reason_code=(
                    "prediction_submitted" if has_current_attempt else "prediction_required"
                ),
            )

        if mode is TeachingMode.WORK_ON_PROJECTS:
            return ReleaseDecision(
                action=TeachingAction.COACH_PROJECT_MILESTONE,
                release_level=(
                    AnswerReleaseLevel.SCAFFOLD
                    if has_current_attempt
                    else AnswerReleaseLevel.HINT
                ),
                attempts_observed=attempts,
                reason_code="project_milestone_coaching",
            )

        action = (
            TeachingAction.CHECK_DERIVATION_STEP
            if task_kind is TeachingTaskKind.DERIVATION_CHECK
            else TeachingAction.GIVE_PROGRESSIVE_HINT
        )
        if (
            policy.allow_full_solution
            and attempts >= policy.minimum_attempts_for_full_solution
        ):
            return ReleaseDecision(
                action=action,
                release_level=AnswerReleaseLevel.FULL_SOLUTION,
                attempts_observed=attempts,
                reason_code="teacher_policy_full_solution_threshold_met",
            )
        if attempts >= policy.minimum_attempts_for_scaffold:
            return ReleaseDecision(
                action=action,
                release_level=AnswerReleaseLevel.SCAFFOLD,
                attempts_observed=attempts,
                reason_code="attempt_threshold_for_scaffold_met",
            )
        return ReleaseDecision(
            action=TeachingAction.GIVE_PROGRESSIVE_HINT,
            release_level=AnswerReleaseLevel.HINT,
            attempts_observed=attempts,
            reason_code="progressive_hint_before_solution",
        )


__all__ = ["AnswerPolicyRepository", "AnswerReleaseEngine", "safe_default_policy"]
