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

# Deterministic markers that distinguish a factual / definition lookup from a
# reasoning / exercise / prediction task.  A factual lookup may legitimately
# bypass the commitment gate; a reasoning task must not.
_FACTUAL_LOOKUP_MARKERS: tuple[str, ...] = (
    "什么是", "是什么", "定义", "是指", "意思是", "请给出定义",
    "what is", "definition of", "define ",
)


def commitment_eligibility(
    *,
    mode: TeachingMode,
    task_kind: TeachingTaskKind,
    message: str,
    has_current_attempt: bool,
) -> bool:
    """Deterministic decision: does this turn require a cognitive commitment?

    The LLM never decides this.  Eligibility is a pure function of the
    teaching mode, the deterministic task kind, and the student's message
    text.  A factual/definition lookup (e.g. "什么是厄米算符?") bypasses the
    gate; reasoning, exercise, derivation, prediction, and experiment tasks
    require a commitment before the answer is released.

    A student who has already submitted an attempt this turn is treated as
    having satisfied the gate (the attempt itself is the commitment).
    """

    # A student who already submitted an attempt has, by definition, committed
    # a prediction / first step / reasoning step.  The gate does not ask twice.
    if has_current_attempt:
        return False

    # Experiment and project modes always require a prediction before the
    # simulation / milestone coaching is released.
    if mode in {TeachingMode.RUN_EXPERIMENTS, TeachingMode.WORK_ON_PROJECTS}:
        return True

    # Derivation review always requires the student's derivation first.
    if mode is TeachingMode.REVIEW_DERIVATIONS:
        return True

    # In LEARN_CONCEPTS mode, distinguish factual lookups from reasoning tasks.
    # PRD V3.0 Axiom 1 (fail-closed): the DEFAULT for a concept question is to
    # require a commitment, because a generic concept request such as
    # "解释波函数" or "讲一下隧穿" is a reasoning/explanation task, not a
    # definition lookup.  Only an explicit factual/definition lookup bypasses
    # the gate.  This inverts the previous default-bypass behaviour that let a
    # student phrase any concept query to avoid the commitment gate.
    if mode is TeachingMode.LEARN_CONCEPTS:
        if task_kind is TeachingTaskKind.EXERCISE_HELP:
            return True
        if task_kind is TeachingTaskKind.DERIVATION_CHECK:
            return True
        # CONCEPT_QUESTION: a bare factual/definition lookup bypasses; every
        # other concept request (including unmarked "解释X" / "讲一下X") is
        # treated as a reasoning task that requires a commitment.
        lowered = message.lower().strip()
        has_factual_marker = any(marker in lowered for marker in _FACTUAL_LOOKUP_MARKERS)
        if has_factual_marker:
            return False
        return True

    return False


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
        message: str | None = None,
    ) -> ReleaseDecision:
        attempts = prior_attempts + int(has_current_attempt)
        if coverage is RetrievalCoverage.NOT_FOUND:
            return ReleaseDecision(
                action=TeachingAction.ASK_DIAGNOSTIC_QUESTION,
                release_level=AnswerReleaseLevel.QUESTION_ONLY,
                attempts_observed=attempts,
                reason_code="course_evidence_not_found",
            )

        # PRD V3.0 Axiom 1: if the deterministic commitment policy requires a
        # commitment and the student has not submitted one yet, the release
        # level must be QUESTION_ONLY regardless of the underlying task kind.
        # This ensures the learning_native_pre node's commitment gate fires
        # for reasoning / exercise / prediction tasks, not just RUN_EXPERIMENTS.
        if message is not None and commitment_eligibility(
            mode=mode,
            task_kind=task_kind,
            message=message,
            has_current_attempt=has_current_attempt,
        ):
            return ReleaseDecision(
                action=TeachingAction.ASK_DIAGNOSTIC_QUESTION,
                release_level=AnswerReleaseLevel.QUESTION_ONLY,
                attempts_observed=attempts,
                reason_code="commitment_required_before_explanation",
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
