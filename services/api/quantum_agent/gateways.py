"""Central construction of model, embedding, and graph gateways."""

from __future__ import annotations

from quantum_agent.config import Settings
from quantum_agent.knowledge.graph_store import GraphStore, Neo4jGraphStore
from quantum_agent.llm.embeddings import (
    EmbeddingGateway,
    HashingEmbeddingGateway,
    OpenAICompatibleEmbeddingGateway,
)
from quantum_agent.llm.gateway import ModelGateway, PydanticAIModelGateway
from quantum_agent.llm.routing import (
    ModelCapabilityRegistry,
    ModelProfile,
    ModelRouter,
    ModelTask,
)
from quantum_agent.llm.vision import VisionGateway


def build_model_capability_registry(settings: Settings) -> ModelCapabilityRegistry:
    """Build the server-only registry used by chat and future specialist adapters."""

    return ModelCapabilityRegistry.ustc_default(
        reasoning_model=settings.ustc_model,
        lightweight_model=settings.ustc_quick_model,
        second_pass_model=settings.ustc_second_pass_model,
        vision_model=settings.ustc_vision_model,
        long_context_model=settings.ustc_long_context_model,
        embedding_model=settings.ustc_embedding_route_model,
        rerank_model=settings.ustc_rerank_model,
        document_parser_model=settings.ustc_document_parser_model,
        ocr_model=settings.ustc_ocr_model,
    )


def build_model_router(settings: Settings) -> ModelRouter | None:
    api_key = settings.ustc_api
    if api_key is None:
        return None
    registry = build_model_capability_registry(settings)

    def gateway_factory(profile: ModelProfile) -> ModelGateway:
        return PydanticAIModelGateway(
            api_key=api_key,
            base_url=settings.ustc_base_url,
            default_model=profile.provider_model,
            small_model=profile.provider_model,
        )

    return ModelRouter(registry=registry, gateway_factory=gateway_factory)


def build_model_gateway(settings: Settings) -> ModelGateway | None:
    """Backward-compatible construction returning the capability-based router."""

    return build_model_router(settings)


def build_vision_gateway(settings: Settings) -> VisionGateway | None:
    if settings.ustc_api is None:
        return None
    registry = build_model_capability_registry(settings)
    vision_profile = registry.profiles_for(ModelTask.VISION)[0]
    return VisionGateway(
        api_key=settings.ustc_api,
        base_url=settings.ustc_base_url,
        model=vision_profile.provider_model,
    )


def build_embedding_gateway(settings: Settings) -> EmbeddingGateway | None:
    if settings.embedding_provider == "disabled":
        return None
    if settings.embedding_provider == "local_hashing":
        return HashingEmbeddingGateway(dimensions=settings.embedding_dimension)
    if (
        settings.embedding_api_key is None
        or settings.embedding_base_url is None
        or settings.embedding_model is None
    ):
        raise ValueError("Embedding gateway configuration is incomplete")
    return OpenAICompatibleEmbeddingGateway(
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimension,
        base_url=settings.embedding_base_url,
    )


def build_graph_store(settings: Settings) -> GraphStore | None:
    if settings.neo4j_password is None:
        return None
    return Neo4jGraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_user,
        password=settings.neo4j_password.get_secret_value(),
        database=settings.neo4j_database,
    )


__all__ = [
    "build_embedding_gateway",
    "build_graph_store",
    "build_model_capability_registry",
    "build_model_gateway",
    "build_model_router",
    "build_vision_gateway",
]
