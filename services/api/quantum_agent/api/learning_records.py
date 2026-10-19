"""Bounded, traceable exports of a single authorized classroom episode.

Exports are observations and explicitly attributed judgments. They are not
classroom outcome claims. Missing historic provenance remains unknown.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import authenticate_course_actor, bearer_credential
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    AgentTrace,
    CourseRole,
    LearningEvidence,
    TeachingConversation,
    TeachingReview,
    TeachingTurn,
)
from quantum_agent.teaching.access import require_evidence_access
from quantum_agent.teaching.execution_budget import budget_status_json

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/learning-records",
    tags=["learning-records"],
)
DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]
MAX_EXPORT_TURNS = 500
MAX_EXPORT_EVENTS = 5000
MAX_EXPORT_BYTES = 8_000_000


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


async def _serialize_export(
    metadata: dict[str, Any],
    sections: dict[str, tuple[AsyncGenerator[dict[str, Any], None], int]],
) -> bytes:
    """Build a complete canonical document within the byte/row budgets.

    Nothing is sent until validation succeeds. Only the bounded output buffer
    and the current database row are retained, instead of every result snapshot.
    """

    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = bytearray()
    digest = hashlib.sha256()

    def append(fragment: str, *, record: bool = True) -> None:
        # UTF-8 is at least one byte per character. Reject oversized fragments
        # before allocating an additional encoded copy of a large database field.
        if len(fragment) > MAX_EXPORT_BYTES - len(payload):
            raise HTTPException(status_code=413, detail="Episode exceeds export byte budget")
        encoded = fragment.encode("utf-8")
        if len(payload) + len(encoded) > MAX_EXPORT_BYTES:
            raise HTTPException(status_code=413, detail="Episode exceeds export byte budget")
        payload.extend(encoded)
        if record:
            digest.update(encoded)

    def item(value: Any) -> None:
        for fragment in encoder.iterencode(value):
            append(fragment)

    append('{"record":', record=False)
    append("{")
    for index, key in enumerate(sorted(metadata.keys() | sections.keys())):
        if index:
            append(",")
        item(key)
        append(":")
        if key not in sections:
            item(metadata[key])
            continue
        records, limit = sections[key]
        append("[")
        count = 0
        try:
            async for record_value in records:
                if count >= limit:
                    raise HTTPException(status_code=413, detail="Episode exceeds export row budget")
                if count:
                    append(",")
                item(record_value)
                count += 1
        finally:
            # Close the active database cursor immediately on any budget error.
            await records.aclose()
        append("]")
    append("}")
    append(',"record_sha256":' + encoder.encode(digest.hexdigest()) + "}", record=False)
    return bytes(payload)


@router.get("/{conversation_id}/export", response_model=None)
async def export_learning_record(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    conversation_id: UUID,
    session: DatabaseSession,
) -> Response:
    actor = await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
    )
    conversation = await session.scalar(
        select(TeachingConversation).where(
            TeachingConversation.id == conversation_id,
            TeachingConversation.course_id == course_id,
            TeachingConversation.curriculum_edition_id == curriculum_edition_id,
            *(
                [TeachingConversation.student_user_id == actor.user_id]
                if actor.course_role is CourseRole.STUDENT
                else []
            ),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Learning record not found")
    # A student cannot open another episode's previous assistance while Solo is
    # active. Teachers retain oversight, but students never receive the oracle.
    await require_evidence_access(session, actor)
    # Project only exported fields: the stored full result snapshot duplicates
    # response/evidence and can be large. Stream one row at a time and serialize
    # incrementally; a rejected export never loads the remaining episode.
    turn_statement = (
        select(
            TeachingTurn.id.label("turn_id"), TeachingTurn.sequence_number.label("sequence"),
            TeachingTurn.created_at, TeachingTurn.completed_at, TeachingTurn.status,
            TeachingTurn.user_message.label("initial_message"),
            TeachingTurn.student_attempt.label("student_answer"),
            TeachingTurn.scientific_results_json["__initial_request"].label("submitted_request"),
            TeachingTurn.execution_budget_json.label("execution_budget"),
            TeachingTurn.response_json.label("intervention"),
            TeachingTurn.evidence_packet_json.label("source_evidence"),
            TeachingTurn.teaching_action, TeachingTurn.release_level,
            TeachingTurn.scientific_results_json["results"].label("scientific_results"),
            TeachingTurn.validation_json.label("validation"), TeachingTurn.failure_code,
            TeachingTurn.scientific_results_json["__provenance"].label("provenance"),
            TeachingTurn.scientific_results_json["__result_snapshot"]["learning_native"]
            .label("learning_state"),
            TeachingTurn.scientific_results_json["__hitl_decisions"].label("durable_hitl_decisions"),
            AgentTrace.id.label("trace_id"),
            AgentTrace.steps_json["diagnosis"].label("diagnosis"),
            AgentTrace.policy_snapshot_json.label("policy"),
            AgentTrace.steps_json["hitl_events"].label("hitl_decisions"),
        )
        .outerjoin(AgentTrace, (AgentTrace.teaching_turn_id == TeachingTurn.id)
                   & (AgentTrace.course_id == course_id)
                   & (AgentTrace.curriculum_edition_id == curriculum_edition_id)
                   & (AgentTrace.student_user_id == conversation.student_user_id))
        .where(TeachingTurn.conversation_id == conversation_id)
        .order_by(TeachingTurn.sequence_number)
        .limit(MAX_EXPORT_TURNS + 1)
    )
    event_statement = (
        select(LearningEvidence)
        .join(TeachingTurn, TeachingTurn.id == LearningEvidence.teaching_turn_id)
        .where(
            TeachingTurn.conversation_id == conversation_id,
            LearningEvidence.course_id == course_id,
            LearningEvidence.curriculum_edition_id == curriculum_edition_id,
            LearningEvidence.student_user_id == conversation.student_user_id,
        )
        .order_by(LearningEvidence.created_at, LearningEvidence.id)
        .limit(MAX_EXPORT_EVENTS + 1)
    )
    review_statement = (
        select(TeachingReview)
        .where(
            TeachingReview.conversation_id == conversation_id,
            TeachingReview.course_id == course_id,
            TeachingReview.curriculum_edition_id == curriculum_edition_id,
            TeachingReview.student_user_id == conversation.student_user_id,
        )
        .order_by(TeachingReview.created_at, TeachingReview.id)
        .limit(MAX_EXPORT_TURNS + 1)
    )

    async def turn_records() -> AsyncGenerator[dict[str, Any], None]:
        result = await session.stream(turn_statement.execution_options(yield_per=1))
        try:
            async for row in result.mappings():
                record = dict(row)
                record["execution_budget"] = budget_status_json(
                    record["execution_budget"], record["turn_id"],
                )
                record["turn_id"] = str(record["turn_id"])
                record["trace_id"] = str(record["trace_id"]) if record["trace_id"] else None
                record["created_at"] = _iso(record["created_at"])
                record["completed_at"] = _iso(record["completed_at"])
                for key in ("status", "teaching_action", "release_level"):
                    record[key] = record[key].value if record[key] is not None else None
                record["scientific_results"] = record["scientific_results"] or []
                record["provenance"] = record["provenance"] or {
                    "code_revision": "unknown", "model_calls": [],
                    "historic_provenance": "unrecorded",
                }
                durable = record.pop("durable_hitl_decisions") or {}
                legacy = record["validation"].get("hitl")
                record["hitl_decisions"] = (
                    record["hitl_decisions"] or list(durable.values())
                    or ([{"interrupt": legacy["interrupt"], "resolution": legacy.get("resolution")}]
                        if isinstance(legacy, dict) and "interrupt" in legacy else [])
                )
                yield record
        finally:
            await result.close()

    async def event_records() -> AsyncGenerator[dict[str, Any], None]:
        result = await session.stream_scalars(event_statement.execution_options(yield_per=1))
        try:
            async for event in result:
                yield {
                    "event_id": str(event.id), "turn_id": str(event.teaching_turn_id),
                    "kind": event.kind.value, "observation": event.observation,
                    "payload": event.evidence_json, "created_at": _iso(event.created_at),
                }
        finally:
            await result.close()

    async def review_records() -> AsyncGenerator[dict[str, Any], None]:
        result = await session.stream_scalars(review_statement.execution_options(yield_per=1))
        try:
            async for review in result:
                yield {
                    "review_id": str(review.id), "source_turn_id": str(review.source_turn_id),
                    "reviewer_user_id": str(review.reviewer_user_id), "decision": review.decision,
                    "reason": review.reason, "follow_up": review.follow_up, "probe": review.probe,
                    "rubric": review.rubric_json, "created_at": _iso(review.created_at),
                }
        finally:
            await result.close()

    packet: dict[str, Any] = {
        "schema_version": "classroom-evidence/1.0.0",
        "exported_at": datetime.now(UTC).isoformat(),
        "course_id": str(course_id),
        "curriculum_edition_id": str(curriculum_edition_id),
        "conversation_id": str(conversation_id),
        "student_user_id": str(conversation.student_user_id),
        "semantics": {
            "source": "persisted_learning_records",
            "delivery": "persisted workflow outputs; client receipt is not proven",
            "classroom_outcomes": "not_established_by_this_export",
            "unaided": "in_app_assistance_lock_only; external assistance is unobservable",
            "diagnoses": "model_inferences; not observed prerequisite deficits",
            "teacher_approval": "only explicit attributed review decisions",
            "integrity": "SHA-256 detects file changes; it is not a signature",
        },
    }
    sections = {
        "turns": (turn_records(), MAX_EXPORT_TURNS),
        "events": (event_records(), MAX_EXPORT_EVENTS),
        "teacher_decisions": (review_records(), MAX_EXPORT_TURNS),
    }
    payload = await _serialize_export(packet, sections)
    return Response(
        payload,
        media_type="application/json",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="learning-{conversation_id}.json"',
        },
    )
