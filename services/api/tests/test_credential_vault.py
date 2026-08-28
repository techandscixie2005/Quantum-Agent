"""Tests for the encrypted session credential vault (PRD V3.1 §3.3)."""

from __future__ import annotations

import resource
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from quantum_agent.coding.sandbox import _rlimit_settings
from quantum_agent.config import Settings
from quantum_agent.credential_router import CredentialScopedRouterFactory
from quantum_agent.credential_vault import (
    CredentialVault,
    CredentialVaultError,
    MemoryCredentialVaultBackend,
    build_credential_vault,
    digest_api_key,
)
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.llm.routing import ModelCapabilityRegistry, ModelRouter
from quantum_agent.science.models import SandboxLimits


def _fernet_key() -> SecretStr:
    return SecretStr(Fernet.generate_key().decode("ascii"))


async def test_vault_round_trips_an_api_key() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    session_id = uuid4()
    await vault.store(session_id, SecretStr("sk-test-key-1234567890"))
    loaded = await vault.load(session_id)
    assert loaded is not None
    assert loaded.get_secret_value() == "sk-test-key-1234567890"
    await vault.close()


async def test_vault_returns_none_for_unknown_session() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    assert await vault.load(uuid4()) is None
    await vault.close()


async def test_forget_evicts_the_entry() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    session_id = uuid4()
    await vault.store(session_id, SecretStr("sk-test-key-1234567890"))
    await vault.forget(session_id)
    assert await vault.load(session_id) is None
    await vault.close()


async def test_vault_rejects_empty_key() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    with pytest.raises(CredentialVaultError):
        await vault.store(uuid4(), SecretStr(""))


async def test_vault_repr_does_not_leak_plaintext() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    session_id = uuid4()
    plaintext = "sk-super-secret-key-1234567890"
    await vault.store(session_id, SecretStr(plaintext))
    representation = repr(vault)
    assert plaintext not in representation
    assert "redacted" in representation
    await vault.close()


async def test_vault_treats_corrupt_ciphertext_as_absent() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    session_id = uuid4()
    # Store garbage bytes directly via the backend to simulate corruption.
    await vault._backend.store_raw(  # type: ignore[attr-defined]
        f"vault:session:{session_id}:ustc_api", b"not-valid-fernet", ttl_seconds=60
    )
    assert await vault.load(session_id) is None
    await vault.close()


def test_build_credential_vault_disabled_when_no_key() -> None:
    assert build_credential_vault(fernet_key=None, redis_url=None) is None


def test_build_credential_vault_uses_memory_when_no_redis() -> None:
    vault = build_credential_vault(fernet_key=_fernet_key(), redis_url=None)
    assert vault is not None
    assert isinstance(vault._backend, MemoryCredentialVaultBackend)  # type: ignore[attr-defined]


def test_digest_api_key_is_stable_and_does_not_leak() -> None:
    key = SecretStr("sk-test-key-1234567890")
    digest_a = digest_api_key(key)
    digest_b = digest_api_key(key)
    assert digest_a == digest_b
    assert len(digest_a) == 64
    assert "sk-test-key" not in digest_a


def test_plain_session_secret_fallback_builds_a_valid_vault() -> None:
    settings = Settings(
        session_vault_key=None,
        session_secret=SecretStr("ordinary-existing-session-secret"),
    )

    vault = build_credential_vault(
        fernet_key=settings.session_vault_key,
        redis_url=None,
    )

    assert vault is not None


def _fallback_router() -> ModelRouter:
    return ModelRouter(
        registry=ModelCapabilityRegistry.ustc_default(),
        gateway_factory=lambda _profile: FakeModelGateway(),
    )


async def test_authenticated_vault_miss_never_falls_back_to_another_credential() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    factory = CredentialScopedRouterFactory(
        registry=ModelCapabilityRegistry.ustc_default(),
        gateway_factory=lambda **_kwargs: FakeModelGateway(),
        fallback_router=_fallback_router(),
        vault=vault,
        base_url="https://api.llm.ustc.edu.cn/v1",
    )

    resolved = await factory.router_for_session(uuid4())

    assert resolved is None


async def test_logout_evicts_cached_decrypted_credential_router() -> None:
    vault = CredentialVault(
        backend=MemoryCredentialVaultBackend(),
        fernet_key=_fernet_key(),
    )
    session_id = uuid4()
    await vault.store(session_id, SecretStr("student-secret-key-123456789"))
    factory = CredentialScopedRouterFactory(
        registry=ModelCapabilityRegistry.ustc_default(),
        gateway_factory=lambda **_kwargs: FakeModelGateway(),
        fallback_router=None,
        vault=vault,
        base_url="https://api.llm.ustc.edu.cn/v1",
    )
    assert await factory.router_for_session(session_id) is not None
    assert factory._routers

    await factory.forget_session(session_id)

    assert not factory._routers


def test_sandbox_enforces_declared_memory_limit() -> None:
    configured = dict(_rlimit_settings(SandboxLimits(memory_megabytes=64)))

    assert resource.RLIMIT_AS in configured
    assert configured[resource.RLIMIT_AS][0] <= 64 * 1024 * 1024
