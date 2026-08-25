"""Validated model and embedding gateways.

Business services depend on these protocols instead of vendor SDKs.  The USTC
credential is accepted only by the backend gateway and is never serialized in
public configuration or responses.
"""

from .embeddings import (
    EmbeddingGateway,
    EmbeddingProbe,
    HashingEmbeddingGateway,
    OpenAICompatibleEmbeddingGateway,
)
from .gateway import (
    FakeModelGateway,
    GatewayCapabilities,
    GatewayError,
    Message,
    ModelGateway,
    ModelTier,
    PydanticAIModelGateway,
)
from .routing import (
    CapabilityDescriptor,
    ModelCapability,
    ModelCapabilityRegistry,
    ModelProfile,
    ModelRouter,
    ModelTask,
    ModelTransport,
)

__all__ = [
    "CapabilityDescriptor",
    "EmbeddingGateway",
    "EmbeddingProbe",
    "FakeModelGateway",
    "GatewayCapabilities",
    "GatewayError",
    "HashingEmbeddingGateway",
    "Message",
    "ModelCapability",
    "ModelCapabilityRegistry",
    "ModelGateway",
    "ModelProfile",
    "ModelRouter",
    "ModelTask",
    "ModelTier",
    "ModelTransport",
    "OpenAICompatibleEmbeddingGateway",
    "PydanticAIModelGateway",
]
