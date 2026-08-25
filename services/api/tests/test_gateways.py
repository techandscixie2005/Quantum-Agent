from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantum_agent.config import Settings
from quantum_agent.gateways import (
    build_embedding_gateway,
    build_graph_store,
    build_model_gateway,
)
from quantum_agent.llm.embeddings import HashingEmbeddingGateway


def test_chat_and_embedding_credentials_are_independent() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USTC_API="chat-only-secret",
        EMBEDDING_PROVIDER="disabled",
    )

    assert build_model_gateway(settings) is not None
    assert build_embedding_gateway(settings) is None


def test_local_hashing_is_an_explicit_degraded_provider() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        EMBEDDING_PROVIDER="local_hashing",
    )

    gateway = build_embedding_gateway(settings)
    assert isinstance(gateway, HashingEmbeddingGateway)


def test_openai_compatible_embeddings_require_separate_complete_config() -> None:
    with pytest.raises(ValidationError, match="their own URL, API key, and model"):
        Settings(
            _env_file=None,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            EMBEDDING_PROVIDER="openai_compatible",
            USTC_API="chat-secret-is-not-an-embedding-secret",
        )


def test_graph_store_is_disabled_without_server_secret() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        NEO4J_PASSWORD=None,
    )
    assert build_graph_store(settings) is None
