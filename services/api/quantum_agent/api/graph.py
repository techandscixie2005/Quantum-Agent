"""Authenticated student-safe graph explorer HTTP API."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import authenticate_course_actor, bearer_credential
from quantum_agent.database import session_dependency
from quantum_agent.knowledge.explorer import (
    ConceptSearchResponse,
    GraphExplorerNotFoundError,
    GraphExplorerService,
    GraphExplorerUnavailableError,
    PrerequisitePathsResponse,
    StudentSubgraphResponse,
)
from quantum_agent.knowledge.retrieval import RetrievalScope

router = APIRouter(
    prefix="/api/v1/courses/{course_id}/editions/{curriculum_edition_id}/graph",
    tags=["student-graph-explorer"],
)

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


async def authenticated_graph_explorer(
    request: Request,
    course_id: UUID,
    session: DatabaseSession,
) -> GraphExplorerService:
    """Authenticate any active course member before resolving the graph service."""

    await authenticate_course_actor(
        session,
        credential=bearer_credential(request),
        course_id=course_id,
        allowed_roles=None,
    )
    explorer = getattr(request.app.state, "graph_explorer", None)
    required_methods = ("search_concepts", "subgraph", "prerequisite_paths")
    if explorer is None or not all(
        callable(getattr(explorer, method, None)) for method in required_methods
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph explorer is unavailable",
        )
    # This dependency is intentionally overrideable for isolated API tests and
    # alternate application composition. Application startup owns wiring.
    return cast(GraphExplorerService, explorer)


GraphExplorerDependency = Annotated[
    GraphExplorerService,
    Depends(authenticated_graph_explorer),
]


def _translate_explorer_error(error: Exception) -> HTTPException:
    if isinstance(error, GraphExplorerNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Graph explorer is unavailable",
    )


@router.get("/concepts/search", response_model=ConceptSearchResponse)
async def concept_search(
    course_id: UUID,
    curriculum_edition_id: UUID,
    explorer: GraphExplorerDependency,
    q: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConceptSearchResponse:
    try:
        return await explorer.search_concepts(
            RetrievalScope(
                course_id=course_id,
                curriculum_edition_id=curriculum_edition_id,
            ),
            q,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Graph search query must not be blank",
        ) from error
    except GraphExplorerUnavailableError as error:
        raise _translate_explorer_error(error) from error


@router.get("/nodes/{candidate_id}/subgraph", response_model=StudentSubgraphResponse)
async def graph_subgraph(
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    explorer: GraphExplorerDependency,
    max_depth: Annotated[int, Query(ge=1, le=5)] = 2,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> StudentSubgraphResponse:
    try:
        return await explorer.subgraph(
            RetrievalScope(
                course_id=course_id,
                curriculum_edition_id=curriculum_edition_id,
            ),
            candidate_id,
            max_depth=max_depth,
            limit=limit,
        )
    except (GraphExplorerNotFoundError, GraphExplorerUnavailableError) as error:
        raise _translate_explorer_error(error) from error


@router.get(
    "/nodes/{candidate_id}/prerequisites",
    response_model=PrerequisitePathsResponse,
)
async def prerequisite_paths(
    course_id: UUID,
    curriculum_edition_id: UUID,
    candidate_id: UUID,
    explorer: GraphExplorerDependency,
    max_depth: Annotated[int, Query(ge=1, le=5)] = 4,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PrerequisitePathsResponse:
    try:
        return await explorer.prerequisite_paths(
            RetrievalScope(
                course_id=course_id,
                curriculum_edition_id=curriculum_edition_id,
            ),
            candidate_id,
            max_depth=max_depth,
            limit=limit,
        )
    except (GraphExplorerNotFoundError, GraphExplorerUnavailableError) as error:
        raise _translate_explorer_error(error) from error


__all__ = ["authenticated_graph_explorer", "router"]
