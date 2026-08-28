"""Central construction of model, embedding, and graph gateways."""

from __future__ import annotations

from pydantic import SecretStr

from quantum_agent.coding import CodingAgent, RemoteSandbox, SandboxDisabled, SubprocessSandbox
from quantum_agent.config import Settings
from quantum_agent.credential_router import CredentialScopedRouterFactory
from quantum_agent.credential_vault import (
    CredentialVault,
)
from quantum_agent.credential_vault import (
    build_credential_vault as _build_credential_vault,
)
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
from quantum_agent.science import ScientificToolbox


def build_model_capability_registry(settings: Settings) -> ModelCapabilityRegistry:
    """Build the server-only registry used by chat and future specialist adapters."""

    return ModelCapabilityRegistry.ustc_default(
        reasoning_model=settings.ustc_model,
        lightweight_model=settings.ustc_quick_model,
        second_pass_model=settings.ustc_second_pass_model,
        vision_model=settings.ustc_vision_model,
        long_context_model=settings.ustc_long_context_model,
        code_model=settings.ustc_code_model,
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


def build_credential_vault(settings: Settings) -> CredentialVault | None:
    """Build the encrypted session vault for user-supplied API keys.

    Returns None when ``SESSION_VAULT_KEY`` (or the ``SESSION_SECRET`` fallback)
    is unset — the caller then uses the startup ``USTC_API`` env key for all
    sessions (PRD §3.3 dev/deploy fallback).
    """

    return _build_credential_vault(
        fernet_key=settings.session_vault_key,
        redis_url=settings.effective_redis_url,
        ttl_seconds=settings.session_ttl_seconds,
    )


def build_per_credential_gateway(
    *,
    api_key: SecretStr,
    profile: ModelProfile,
    base_url: str,
) -> ModelGateway:
    """Build a ``PydanticAIModelGateway`` for one credential + profile.

    Used by :class:`CredentialScopedRouterFactory` to construct per-session
    routers whose gateways use the user-supplied API key.
    """

    return PydanticAIModelGateway(
        api_key=api_key,
        base_url=base_url,
        default_model=profile.provider_model,
        small_model=profile.provider_model,
    )


def build_credential_router_factory(
    settings: Settings,
    *,
    registry: ModelCapabilityRegistry,
    fallback_router: ModelRouter | None,
    vault: CredentialVault | None,
) -> CredentialScopedRouterFactory:
    """Build the per-session ModelRouter cache backed by the credential vault."""

    return CredentialScopedRouterFactory(
        registry=registry,
        gateway_factory=build_per_credential_gateway,
        fallback_router=fallback_router,
        vault=vault,
        base_url=settings.ustc_base_url,
    )


def build_sandbox(settings: Settings) -> SubprocessSandbox | RemoteSandbox | SandboxDisabled:
    """Build the Coding Agent subprocess sandbox (PRD V3.1 §6.2)."""

    if not settings.coding_sandbox_enabled:
        return SandboxDisabled()
    if settings.coding_sandbox_url:
        return RemoteSandbox(settings.coding_sandbox_url)
    return SubprocessSandbox()


def build_coding_agent(
    settings: Settings,
    *,
    sandbox: SubprocessSandbox | RemoteSandbox | SandboxDisabled,
    toolbox: ScientificToolbox | None = None,
) -> CodingAgent | None:
    """Build the Coding Agent.  Returns None only when the sandbox is disabled
    and the caller wants to skip the agent entirely (by default the agent is
    still built and degrades to ``INCONCLUSIVE`` when the sandbox is disabled)."""

    return CodingAgent(sandbox=sandbox, toolbox=toolbox)


__all__ = [
    "build_coding_agent",
    "build_credential_router_factory",
    "build_credential_vault",
    "build_embedding_gateway",
    "build_graph_store",
    "build_model_capability_registry",
    "build_model_gateway",
    "build_model_router",
    "build_per_credential_gateway",
    "build_sandbox",
    "build_vision_gateway",
]
