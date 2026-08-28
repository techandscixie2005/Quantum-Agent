"""Authenticated deterministic teaching workflow and teacher policy API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, NoReturn, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import (
    TEACHER_ROLES,
    TEACHING_STAFF_ROLES,
    CourseActor,
    authenticate_course_actor,
    bearer_credential,
)
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AnswerPolicy,
    AuditEventType,
    AuditLog,
    AuditResourceType,
    CourseRole,
    TeachingMode,
)
from quantum_agent.knowledge.retrieval import RetrievalError
from quantum_agent.llm.gateway import ModelGateway
from quantum_agent.multimodal.teaching import (
    TeachingAttachmentConflictError,
    TeachingAttachmentNotFoundError,
)
from quantum_agent.teaching.hitl import (
    HitlAuthorizationError,
    HitlConflictError,
    HitlInterruptResponse,
    HitlNotFoundError,
    HitlRejectedResponse,
    HitlResolutionValidationError,
    HitlResumeRequest,
)
from quantum_agent.teaching.models import (
    PolicySnapshot,
    TeachingTurnInput,
    TeachingTurnResult,
)
from quantum_agent.teaching.policy import AnswerPolicyRepository
from quantum_agent.teaching.repository import TeachingConversationConflictError

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/teaching",
    tags=["deterministic-teaching"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


class TeachingWorkflow(Protocol):
    async def run(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        request: TeachingTurnInput,
        model_gateway_override: ModelGateway | None = None,
    ) -> TeachingTurnResult | HitlInterruptResponse: ...

    async def inspect_interrupt(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        conversation_id: UUID,
    ) -> HitlInterruptResponse: ...

    async def resume(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        conversation_id: UUID,
        request: HitlResumeRequest,
        model_gateway_override: ModelGateway | None = None,
    ) -> TeachingTurnResult | HitlInterruptResponse | HitlRejectedResponse: ...


def teaching_workflow_dependency(request: Request) -> TeachingWorkflow:
    # The legacy attribute remains a test-only compatibility seam while the
    # production application exposes only the checkpointed LangGraph workflow.
    workflow: Any = getattr(request.app.state, "teaching_state_machine", None)
    if workflow is None:
        workflow = getattr(request.app.state, "teaching_workflow", None)
    if workflow is None or not callable(getattr(workflow, "run", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Teaching workflow is unavailable",
        )
    return cast(TeachingWorkflow, workflow)


TeachingMachine = Annotated[TeachingWorkflow, Depends(teaching_workflow_dependency)]


async def _actor(
    request: Request,
    session: AsyncSession,
    course_id: UUID,
    *,
    allowed_roles: frozenset[CourseRole] | None = None,
) -> CourseActor:
    return await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
        allowed_roles=allowed_roles,
    )


async def _resolve_model_gateway_override(
    request: Request,
    actor: CourseActor,
) -> ModelGateway | None:
    """Resolve the per-session ModelGateway from the credential vault.

    PRD V3.1 §3.2: every agent call uses the session's API key through the
    central ModelGateway.  When the vault has a key for this session, we
    return a cached per-credential ``ModelRouter``; otherwise we return None
    so the graph falls back to the startup ``USTC_API`` env gateway.
    """

    factory = getattr(request.app.state, "credential_router_factory", None)
    if factory is None:
        return None
    try:
        router: ModelGateway | None = await factory.router_for_session(actor.session_id)
        return router
    except Exception as exc:
        # An authenticated request must fail closed; never route it through
        # the deployment credential after a vault/Redis failure.
        raise HTTPException(status_code=503, detail="session credential unavailable") from exc


TeachingApiOutcome = TeachingTurnResult | HitlInterruptResponse | HitlRejectedResponse


def _raise_hitl_http(error: Exception) -> NoReturn:
    if isinstance(error, HitlAuthorizationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    if isinstance(error, HitlNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, (HitlConflictError, TeachingConversationConflictError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if isinstance(error, HitlResolutionValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    raise error


@router.post("/turns", response_model=TeachingApiOutcome)
async def run_teaching_turn(
    request: Request,
    response: Response,
    course_id: UUID,
    curriculum_edition_id: UUID,
    body: TeachingTurnInput,
    session: DatabaseSession,
    machine: TeachingMachine,
) -> TeachingTurnResult | HitlInterruptResponse:
    actor = await _actor(request, session, course_id)
    gateway_override = await _resolve_model_gateway_override(request, actor)
    try:
        result = await machine.run(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            request=body,
            model_gateway_override=gateway_override,
        )
        await session.commit()
        if isinstance(result, HitlInterruptResponse):
            response.status_code = status.HTTP_202_ACCEPTED
        return result
    except (TeachingConversationConflictError, HitlConflictError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TeachingAttachmentNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TeachingAttachmentConflictError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RetrievalError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Course evidence retrieval is unavailable",
        ) from exc


def _sse(event: str, payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/turns/stream")
async def stream_teaching_turn(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    body: TeachingTurnInput,
    session: DatabaseSession,
    machine: TeachingMachine,
) -> StreamingResponse:
    actor = await _actor(request, session, course_id)
    gateway_override = await _resolve_model_gateway_override(request, actor)

    async def events() -> AsyncIterator[str]:
        yield _sse(
            "workflow.started",
            {"workflow_version": "teaching-state-machine/1.0.0"},
        )
        try:
            result = await machine.run(
                session=session,
                actor=actor,
                curriculum_edition_id=curriculum_edition_id,
                request=body,
                model_gateway_override=gateway_override,
            )
            await session.commit()
            if isinstance(result, HitlInterruptResponse):
                yield _sse("workflow.interrupted", result.model_dump(mode="json"))
            else:
                yield _sse("workflow.completed", result.model_dump(mode="json"))
        except (TeachingConversationConflictError, HitlConflictError):
            await session.rollback()
            yield _sse("workflow.failed", {"code": "CONVERSATION_CONFLICT"})
        except TeachingAttachmentNotFoundError:
            await session.rollback()
            yield _sse("workflow.failed", {"code": "ATTACHMENT_NOT_FOUND"})
        except TeachingAttachmentConflictError:
            await session.rollback()
            yield _sse("workflow.failed", {"code": "ATTACHMENT_NOT_READY"})
        except RetrievalError:
            await session.rollback()
            yield _sse("workflow.failed", {"code": "RETRIEVAL_UNAVAILABLE"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/threads/{conversation_id}/interrupt",
    response_model=HitlInterruptResponse,
)
async def inspect_teaching_interrupt(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    conversation_id: UUID,
    session: DatabaseSession,
    machine: TeachingMachine,
) -> HitlInterruptResponse:
    actor = await _actor(request, session, course_id)
    inspect = getattr(machine, "inspect_interrupt", None)
    if not callable(inspect):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Teaching HITL is unavailable",
        )
    try:
        return cast(
            HitlInterruptResponse,
            await inspect(
                session=session,
                actor=actor,
                curriculum_edition_id=curriculum_edition_id,
                conversation_id=conversation_id,
            ),
        )
    except (
        HitlAuthorizationError,
        HitlNotFoundError,
        HitlConflictError,
        TeachingConversationConflictError,
    ) as error:
        await session.rollback()
        _raise_hitl_http(error)


@router.post(
    "/threads/{conversation_id}/resume",
    response_model=TeachingApiOutcome,
)
async def resume_teaching_interrupt(
    request: Request,
    response: Response,
    course_id: UUID,
    curriculum_edition_id: UUID,
    conversation_id: UUID,
    body: HitlResumeRequest,
    session: DatabaseSession,
    machine: TeachingMachine,
) -> TeachingApiOutcome:
    actor = await _actor(request, session, course_id)
    gateway_override = await _resolve_model_gateway_override(request, actor)
    resume = getattr(machine, "resume", None)
    if not callable(resume):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Teaching HITL is unavailable",
        )
    try:
        outcome = cast(
            TeachingApiOutcome,
            await resume(
                session=session,
                actor=actor,
                curriculum_edition_id=curriculum_edition_id,
                conversation_id=conversation_id,
                request=body,
                model_gateway_override=gateway_override,
            ),
        )
        await session.commit()
        if isinstance(outcome, HitlInterruptResponse):
            response.status_code = status.HTTP_202_ACCEPTED
        return outcome
    except (
        HitlAuthorizationError,
        HitlNotFoundError,
        HitlConflictError,
        HitlResolutionValidationError,
        TeachingConversationConflictError,
    ) as error:
        await session.rollback()
        _raise_hitl_http(error)


class AnswerPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_full_solution: bool = False
    minimum_attempts_for_scaffold: int = Field(default=1, ge=0, le=20)
    minimum_attempts_for_full_solution: int = Field(default=2, ge=0, le=20)
    max_hint_level: int = Field(default=3, ge=0, le=10)
    rationale: str = Field(min_length=1, max_length=4000)


@router.get("/answer-policies/{mode}", response_model=PolicySnapshot)
async def get_answer_policy(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    mode: TeachingMode,
    session: DatabaseSession,
) -> PolicySnapshot:
    await _actor(
        request,
        session,
        course_id,
        allowed_roles=TEACHING_STAFF_ROLES,
    )
    return await AnswerPolicyRepository(session).get_active(
        course_id=course_id,
        curriculum_edition_id=curriculum_edition_id,
        mode=mode,
    )


@router.put("/answer-policies/{mode}", response_model=PolicySnapshot)
async def update_answer_policy(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    mode: TeachingMode,
    body: AnswerPolicyUpdate,
    session: DatabaseSession,
) -> PolicySnapshot:
    if body.minimum_attempts_for_full_solution < body.minimum_attempts_for_scaffold:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Full-solution threshold must not precede scaffold threshold",
        )
    actor = await _actor(
        request,
        session,
        course_id,
        allowed_roles=TEACHER_ROLES,
    )
    policy = await session.scalar(
        select(AnswerPolicy)
        .where(
            AnswerPolicy.course_id == course_id,
            AnswerPolicy.curriculum_edition_id == curriculum_edition_id,
            AnswerPolicy.mode == mode,
        )
        .with_for_update()
    )
    before = policy and {
        "allow_full_solution": policy.allow_full_solution,
        "minimum_attempts_for_scaffold": policy.minimum_attempts_for_scaffold,
        "minimum_attempts_for_full_solution": policy.minimum_attempts_for_full_solution,
        "max_hint_level": policy.max_hint_level,
    }
    if policy is None:
        policy = AnswerPolicy(
            course_id=course_id,
            curriculum_edition_id=curriculum_edition_id,
            mode=mode,
        )
        session.add(policy)
    policy.allow_full_solution = body.allow_full_solution
    policy.minimum_attempts_for_scaffold = body.minimum_attempts_for_scaffold
    policy.minimum_attempts_for_full_solution = body.minimum_attempts_for_full_solution
    policy.max_hint_level = body.max_hint_level
    policy.active = True
    policy.policy_json = {"rationale": body.rationale}
    policy.updated_by_user_id = actor.user_id
    await session.flush()
    after = {
        "allow_full_solution": policy.allow_full_solution,
        "minimum_attempts_for_scaffold": policy.minimum_attempts_for_scaffold,
        "minimum_attempts_for_full_solution": policy.minimum_attempts_for_full_solution,
        "max_hint_level": policy.max_hint_level,
    }
    session.add(
        AuditLog(
            event_type=AuditEventType.SETTINGS_CHANGED,
            resource_type=AuditResourceType.CURRICULUM_EDITION,
            resource_id=curriculum_edition_id,
            actor_user_id=actor.user_id,
            actor_session_id=actor.session_id,
            course_id=course_id,
            summary=f"Updated answer policy for {mode.value}.",
            before_json=before,
            after_json=after,
            context_json={"rationale": body.rationale},
        )
    )
    await session.commit()
    return PolicySnapshot(
        policy_id=policy.id,
        source="teacher_configured",
        mode=mode,
        allow_full_solution=policy.allow_full_solution,
        minimum_attempts_for_scaffold=policy.minimum_attempts_for_scaffold,
        minimum_attempts_for_full_solution=policy.minimum_attempts_for_full_solution,
        max_hint_level=policy.max_hint_level,
    )


__all__ = [
    "TeachingApiOutcome",
    "TeachingWorkflow",
    "router",
    "teaching_workflow_dependency",
]
