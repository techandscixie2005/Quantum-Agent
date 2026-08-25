"""Authenticated student EvidencePacket retrieval API."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import authenticate_course_actor, bearer_credential
from quantum_agent.database import session_dependency
from quantum_agent.knowledge.evidence_packets import EvidencePacket
from quantum_agent.knowledge.retrieval import HybridEvidenceRetriever, RetrievalScope

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}",
    tags=["course-evidence"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


class EvidenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)


def retriever_dependency(request: Request) -> HybridEvidenceRetriever:
    retriever: Any = getattr(request.app.state, "hybrid_retriever", None)
    if not isinstance(retriever, HybridEvidenceRetriever):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Course retrieval is not configured",
        )
    return retriever


@router.post("/evidence-packets", response_model=EvidencePacket)
async def retrieve_evidence_packet(
    request: Request,
    course_id: UUID,
    curriculum_edition_id: UUID,
    body: EvidenceQuery,
    session: DatabaseSession,
    retriever: Annotated[HybridEvidenceRetriever, Depends(retriever_dependency)],
) -> EvidencePacket:
    await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
    )
    return await retriever.retrieve(
        RetrievalScope(
            course_id=course_id,
            curriculum_edition_id=curriculum_edition_id,
        ),
        body.query,
    )


__all__ = ["retriever_dependency", "router"]
