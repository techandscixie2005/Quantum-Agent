"""Authenticated deterministic teaching workflow and teacher policy API."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
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


# PRD V3.2 streaming: per-stage progress callback.  The streaming endpoint
# passes this into ``machine.run`` so the workflow can emit a ``progress`` SSE
# event as each stage (interpret, retrieve, diagnose, ...) begins.  The
# callback receives the stage name and elapsed seconds since the workflow
# started.  It is optional; when ``None`` the workflow runs without per-stage
# notifications (the heartbeat loop still emits keepalives).
StageProgressCallback = Callable[[str, float], Awaitable[None]]


class TeachingWorkflow(Protocol):
    async def run(
        self,
        *,
        session: AsyncSession,
        actor: CourseActor,
        curriculum_edition_id: UUID,
        request: TeachingTurnInput,
        model_gateway_override: ModelGateway | None = None,
        on_stage: StageProgressCallback | None = None,
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
    credentials_required = bool(
        getattr(request.app.state, "session_credentials_required", False)
    )
    if factory is None:
        if credentials_required:
            raise HTTPException(status_code=503, detail="session credential unavailable")
        return None
    try:
        router: ModelGateway | None = await factory.router_for_session(actor.session_id)
        if router is None and credentials_required:
            raise HTTPException(status_code=503, detail="session credential unavailable")
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


def _sse_heartbeat() -> str:
    """SSE comment line that keeps the connection alive without producing a
    client-visible event.  Browsers silently consume ``:`` comment lines per
    the SSE spec; they reset the idle timer and prevent proxies from closing
    the connection during long model calls.
    """

    return ": keepalive\n\n"


# Heartbeat cadence (seconds).  Emitted between ``workflow.started`` and the
# terminal event while ``machine.run`` is in flight.  PRD V3.2 streaming: 4s
# keeps the connection alive well below typical proxy idle timeouts (60s) and
# the 240s BFF deadline, and gives the browser visible progress activity
# during multi-step model calls without flooding the SSE channel.  The first
# progress event is emitted immediately after ``workflow.started`` (see
# ``events`` below) so the browser sees activity within ~1s; subsequent
# heartbeats fire on this cadence, and per-stage ``progress`` events fire as
# each graph node begins (see ``_run_with_heartbeats``).
_HEARTBEAT_INTERVAL_SECONDS = 4.0


async def _run_with_heartbeats(
    machine: TeachingWorkflow,
    *,
    session: DatabaseSession,
    actor: CourseActor,
    curriculum_edition_id: UUID,
    request: TeachingTurnInput,
    model_gateway_override: ModelGateway | None,
    started_at: float,
    emit: Any,
) -> TeachingApiOutcome | HitlInterruptResponse:
    """Run ``machine.run`` while periodically emitting heartbeat SSE lines.

    ``emit`` is an awaitable callable that writes a chunk to the
    ``StreamingResponse`` body.  We use ``asyncio.wait`` with FIRST_COMPLETED
    so the heartbeat task wakes up at the configured cadence and emits a
    comment line; the moment the workflow task finishes, we cancel the
    heartbeat and return the result.  This keeps the SSE connection alive
    and gives the browser visible activity during long model calls without
    buffering or weakening any teaching gate.

    PRD V3.2 streaming: we also pass an ``on_stage`` callback into
    ``machine.run`` so the workflow emits a typed ``progress`` event as each
    stage (interpret, retrieve, diagnose, ...) begins.  The per-stage events
    are informational and never weaken the terminal contract; they do not add
    a new ``WorkflowStepName`` (the 10-step ``WORKFLOW_ORDER`` trace is
    unchanged).
    """

    async def on_stage(stage: str, elapsed: float) -> None:
        await emit(
            _sse(
                "progress",
                {
                    "step": stage,
                    "status": "stage_started",
                    "detail": f"workflow stage '{stage}' started",
                    "elapsed_seconds": round(elapsed, 1),
                },
            )
        )

    workflow_task = asyncio.create_task(
        machine.run(
            session=session,
            actor=actor,
            curriculum_edition_id=curriculum_edition_id,
            request=request,
            model_gateway_override=model_gateway_override,
            on_stage=on_stage,
        )
    )
    heartbeat_task = asyncio.create_task(asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS))
    try:
        while True:
            done, _pending = await asyncio.wait(
                {workflow_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                elapsed = time.monotonic() - started_at
                # PRD V3.1 P1-2: emit a comment-only keepalive plus a typed
                # ``progress`` event so the BFF can forward both to the
                # browser without parsing them.  The progress payload is
                # informational and never weakens the terminal contract.
                await emit(_sse_heartbeat())
                await emit(
                    _sse(
                        "progress",
                        {
                            "step": "workflow_running",
                            "status": "in_flight",
                            "detail": f"teaching workflow running for {elapsed:.1f}s",
                            "elapsed_seconds": round(elapsed, 1),
                        },
                    )
                )
                heartbeat_task = asyncio.create_task(
                    asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
                )
            if workflow_task in done:
                return await workflow_task
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except (asyncio.CancelledError, BaseException):
            pass
        if not workflow_task.done():
            workflow_task.cancel()
            try:
                await workflow_task
            except (asyncio.CancelledError, BaseException):
                pass


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

    # Buffer of emitted SSE chunks.  The producer coroutine appends chunks
    # here; the consumer (the async generator returned to FastAPI) drains
    # them.  This decouples the heartbeat producer from the response body
    # reader so neither blocks the other.
    chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def emit(chunk: str) -> None:
        await chunk_queue.put(chunk)

    async def events() -> AsyncIterator[str]:
        # PRD V3.1 P1-2: emit ``workflow.started`` immediately so the BFF
        # and the browser see the fixed contract event before any long
        # model call runs.  Then emit a ``progress`` event announcing the
        # workflow is running, followed by periodic heartbeats while the
        # graph is in flight, and finally the terminal event.
        yield _sse(
            "workflow.started",
            {"workflow_version": "teaching-state-machine/1.0.0"},
        )
        yield _sse(
            "progress",
            {
                "step": "workflow_started",
                "status": "started",
                "detail": "teaching workflow started",
                "elapsed_seconds": 0.0,
            },
        )
        started_at = time.monotonic()

        async def producer() -> None:
            try:
                result = await _run_with_heartbeats(
                    machine,
                    session=session,
                    actor=actor,
                    curriculum_edition_id=curriculum_edition_id,
                    request=body,
                    model_gateway_override=gateway_override,
                    started_at=started_at,
                    emit=emit,
                )
                await session.commit()
                if isinstance(result, HitlInterruptResponse):
                    await emit(
                        _sse(
                            "progress",
                            {
                                "step": "workflow_paused",
                                "status": "paused",
                                "detail": "teaching workflow paused for human review",
                                "elapsed_seconds": round(
                                    time.monotonic() - started_at, 1
                                ),
                            },
                        )
                    )
                    await emit(
                        _sse("workflow.interrupted", result.model_dump(mode="json"))
                    )
                else:
                    await emit(
                        _sse(
                            "progress",
                            {
                                "step": "workflow_completed",
                                "status": "completed",
                                "detail": "teaching workflow completed",
                                "elapsed_seconds": round(
                                    time.monotonic() - started_at, 1
                                ),
                            },
                        )
                    )
                    await emit(
                        _sse("workflow.completed", result.model_dump(mode="json"))
                    )
            except (TeachingConversationConflictError, HitlConflictError):
                await session.rollback()
                await emit(_sse("workflow.failed", {"code": "CONVERSATION_CONFLICT"}))
            except TeachingAttachmentNotFoundError:
                await session.rollback()
                await emit(_sse("workflow.failed", {"code": "ATTACHMENT_NOT_FOUND"}))
            except TeachingAttachmentConflictError:
                await session.rollback()
                await emit(_sse("workflow.failed", {"code": "ATTACHMENT_NOT_READY"}))
            except RetrievalError:
                await session.rollback()
                await emit(_sse("workflow.failed", {"code": "RETRIEVAL_UNAVAILABLE"}))
            finally:
                await chunk_queue.put(None)

        producer_task = asyncio.create_task(producer())
        try:
            while True:
                chunk = await chunk_queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except (asyncio.CancelledError, BaseException):
                    pass
            # Drain any remaining chunks to avoid leaking the queue.
            while not chunk_queue.empty():
                try:
                    chunk_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

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
