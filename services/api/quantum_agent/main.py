"""Quantum Agent FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from quantum_agent.api.attachments import router as attachments_router
from quantum_agent.api.auth import router as auth_router
from quantum_agent.api.course_context import router as course_context_router
from quantum_agent.api.graph import router as graph_router
from quantum_agent.api.retrieval import router as retrieval_router
from quantum_agent.api.review import router as review_router
from quantum_agent.api.source_files import SourceFileRepository
from quantum_agent.api.source_files import router as source_files_router
from quantum_agent.api.teacher_insights import router as teacher_insights_router
from quantum_agent.api.teaching import router as teaching_router
from quantum_agent.config import Settings, get_settings
from quantum_agent.database import (
    create_database_engine,
    create_session_factory,
    session_dependency,
)
from quantum_agent.gateways import (
    build_coding_agent,
    build_credential_router_factory,
    build_credential_vault,
    build_embedding_gateway,
    build_graph_store,
    build_model_capability_registry,
    build_model_gateway,
    build_sandbox,
    build_vision_gateway,
)
from quantum_agent.knowledge.explorer import GraphExplorerService
from quantum_agent.knowledge.retrieval import (
    HybridEvidenceRetriever,
    StudentVisibleEvidenceRepository,
)
from quantum_agent.llm.routing import ModelRouter
from quantum_agent.multimodal.runtime import build_attachment_runtime
from quantum_agent.tutor.graph import TutorGraph


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    components: dict[str, str]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = create_database_engine(resolved_settings)
    session_factory = create_session_factory(engine)
    graph_store = build_graph_store(resolved_settings)
    embedding_gateway = build_embedding_gateway(resolved_settings)
    model_gateway = build_model_gateway(resolved_settings)
    vision_gateway = build_vision_gateway(resolved_settings)
    attachment_runtime = build_attachment_runtime(
        resolved_settings,
        vision_gateway=vision_gateway,
    )
    evidence_repository = StudentVisibleEvidenceRepository(session_factory)
    hybrid_retriever = HybridEvidenceRetriever(
        repository=evidence_repository,
        embedding_gateway=embedding_gateway,
        graph_store=graph_store,
    )
    graph_explorer = GraphExplorerService(
        graph_store=graph_store,
        evidence_repository=evidence_repository,
    )
    # PRD V3.1 §3. encrypted session vault for user-supplied API keys, and the
    # per-credential ModelRouter cache that reads from it.  When the vault is
    # disabled (no SESSION_VAULT_KEY), the startup USTC_API gateway is used.
    credential_vault = build_credential_vault(resolved_settings)
    capability_registry = build_model_capability_registry(resolved_settings)
    credential_router_factory = build_credential_router_factory(
        resolved_settings,
        registry=capability_registry,
        fallback_router=model_gateway if isinstance(model_gateway, ModelRouter) else None,
        vault=credential_vault,
    )
    # PRD V3.1 §6: Coding Agent + subprocess sandbox.
    sandbox = build_sandbox(resolved_settings)
    scientific_toolbox_for_coding = None  # CodingAgent builds its own ScientificToolbox
    coding_agent = build_coding_agent(
        resolved_settings,
        sandbox=sandbox,
        toolbox=scientific_toolbox_for_coding,
    )

    async def app_session_dependency() -> AsyncIterator[Any]:
        async with session_factory() as session:
            yield session

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI) -> Any:
        try:
            if resolved_settings.is_sqlite:
                yield
            else:
                checkpoint_url = resolved_settings.database_url.replace(
                    "postgresql+asyncpg://", "postgresql://", 1
                )
                async with AsyncPostgresSaver.from_conn_string(checkpoint_url) as saver:
                    await saver.setup()
                    lifespan_app.state.teaching_workflow = TutorGraph(
                        evidence_retriever=hybrid_retriever,
                        model_gateway=model_gateway,
                        checkpointer=saver,
                        use_specialist_agents=True,
                        enable_hitl=True,
                        coding_agent=coding_agent,
                        sandbox=sandbox,
                    )
                    yield
        finally:
            if graph_store is not None:
                await graph_store.close()
            if credential_vault is not None:
                await credential_vault.close()
            await engine.dispose()

    production = resolved_settings.environment == "production"
    app = FastAPI(
        title="Quantum Agent API",
        version="0.1.0",
        docs_url=None if production else "/api/docs",
        redoc_url=None,
        openapi_url=None if production else "/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.graph_store = graph_store
    app.state.evidence_repository = evidence_repository
    app.state.hybrid_retriever = hybrid_retriever
    app.state.graph_explorer = graph_explorer
    app.state.model_gateway = model_gateway
    app.state.attachment_runtime = attachment_runtime
    app.state.credential_vault = credential_vault
    app.state.credential_router_factory = credential_router_factory
    app.state.coding_agent = coding_agent
    app.state.sandbox = sandbox
    app.state.source_file_repository = SourceFileRepository(
        repository_root=Path(__file__).resolve().parents[3]
    )
    if resolved_settings.is_sqlite:
        app.state.teaching_workflow = TutorGraph(
            evidence_retriever=hybrid_retriever,
            model_gateway=model_gateway,
            checkpointer=InMemorySaver(),
            use_specialist_agents=True,
            enable_hitl=False,
            coding_agent=coding_agent,
            sandbox=sandbox,
        )
    app.dependency_overrides[session_dependency] = app_session_dependency
    app.include_router(review_router)
    app.include_router(attachments_router)
    app.include_router(course_context_router)
    app.include_router(retrieval_router)
    app.include_router(graph_router)
    app.include_router(teaching_router)
    app.include_router(source_files_router)
    app.include_router(teacher_insights_router)
    app.include_router(auth_router)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="ok", components={"process": "ok"})

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness() -> HealthResponse:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "not_ready", "components": {"postgresql": "unavailable"}},
            ) from exc
        return HealthResponse(status="ready", components={"postgresql": "ok"})

    return app


app = create_app()


__all__ = ["app", "create_app"]
