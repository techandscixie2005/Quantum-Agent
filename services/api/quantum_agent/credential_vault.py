"""Server-side encrypted vault for user-supplied USTC API keys (PRD V3.1 §3.3).

The student enters their 词元计划/一〇七杯 API key once.  The backend probes the
USTC model service to validate it, mints an opaque session token, and stores
the Fernet-encrypted key keyed by ``session_id``.  The plaintext key never
enters PostgreSQL, logs, agent traces, or the frontend beyond the initial
POST.  The ``ModelGateway`` resolves the per-session credential from the vault
at request time and falls back to the startup ``USTC_API`` env key when the
vault has no entry for a session (dev/deploy fallback).

Two backends: ``RedisCredentialVault`` (production; TTL matches the session
lifetime) and ``MemoryCredentialVault`` (dev/test; process-local dict).  The
factory ``build_credential_vault`` selects Redis when a URL is configured and
falls back to memory otherwise.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

logger = logging.getLogger(__name__)

_VAULT_KEY_PREFIX = "vault:session:"
_VAULT_KEY_SUFFIX = ":ustc_api"


class CredentialVaultError(RuntimeError):
    """Sanitized vault failure; never carries the plaintext key."""


class CredentialVaultBackend(Protocol):
    async def store_raw(self, key: str, ciphertext: bytes, ttl_seconds: int) -> None: ...
    async def load_raw(self, key: str) -> bytes | None: ...
    async def delete_raw(self, key: str) -> None: ...
    async def close(self) -> None: ...


def _vault_key(session_id: UUID) -> str:
    return f"{_VAULT_KEY_PREFIX}{session_id}{_VAULT_KEY_SUFFIX}"


def _require_fernet(key: SecretStr) -> Fernet:
    raw = key.get_secret_value().encode("utf-8")
    try:
        return Fernet(raw)
    except (ValueError, TypeError) as exc:
        raise CredentialVaultError(
            "SESSION_VAULT_KEY is not a valid Fernet key; generate one with "
            "cryptography.fernet.Fernet.generate_key()"
        ) from exc


class CredentialVault:
    """Encrypts API keys at rest and delegates storage to a backend.

    The vault never logs or exposes the plaintext key.  ``__repr__`` is
    overridden to avoid leaking the Fernet instance's internal state.
    """

    def __init__(
        self,
        *,
        backend: CredentialVaultBackend,
        fernet_key: SecretStr,
        ttl_seconds: int = 28_800,
    ) -> None:
        self._backend = backend
        self._fernet = _require_fernet(fernet_key)
        self._ttl_seconds = max(60, min(86_400, ttl_seconds))

    async def store(self, session_id: UUID, api_key: SecretStr) -> None:
        plaintext = api_key.get_secret_value().encode("utf-8")
        if not plaintext:
            raise CredentialVaultError("refusing to store an empty API key")
        ciphertext = self._fernet.encrypt(plaintext)
        await self._backend.store_raw(
            _vault_key(session_id), ciphertext, self._ttl_seconds
        )

    async def load(self, session_id: UUID) -> SecretStr | None:
        ciphertext = await self._backend.load_raw(_vault_key(session_id))
        if ciphertext is None:
            return None
        try:
            plaintext = self._fernet.decrypt(ciphertext)
        except InvalidToken:
            logger.warning(
                "vault entry for session %s failed decryption; treating as absent",
                session_id,
            )
            return None
        return SecretStr(plaintext.decode("utf-8"))

    async def forget(self, session_id: UUID) -> None:
        await self._backend.delete_raw(_vault_key(session_id))

    async def close(self) -> None:
        await self._backend.close()

    def __repr__(self) -> str:
        return "CredentialVault(backend=<redacted>, ttl=<redacted>)"


class MemoryCredentialVaultBackend:
    """Process-local dict backend for dev/test; cleared on process restart."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def store_raw(self, key: str, ciphertext: bytes, ttl_seconds: int) -> None:
        self._store[key] = ciphertext

    async def load_raw(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def delete_raw(self, key: str) -> None:
        self._store.pop(key, None)

    async def close(self) -> None:
        self._store.clear()


class RedisCredentialVaultBackend:
    """Async Redis backend; TTL matches the session lifetime."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def store_raw(self, key: str, ciphertext: bytes, ttl_seconds: int) -> None:
        await self._client.set(key, ciphertext, ex=ttl_seconds)

    async def load_raw(self, key: str) -> bytes | None:
        result: bytes | None = await self._client.get(key)
        return result

    async def delete_raw(self, key: str) -> None:
        await self._client.delete(key)

    async def close(self) -> None:
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result


def build_credential_vault(
    *,
    fernet_key: SecretStr | None,
    redis_url: str | None,
    ttl_seconds: int = 28_800,
) -> CredentialVault | None:
    """Construct a vault with a Redis or memory backend.

    Returns None when ``fernet_key`` is unset or empty — the caller then uses
    the startup ``USTC_API`` env key for all sessions (dev/deploy fallback).
    """

    if fernet_key is None or not fernet_key.get_secret_value().strip():
        logger.info("session vault disabled (SESSION_VAULT_KEY unset); using startup USTC_API")
        return None
    if redis_url:
        try:
            import redis.asyncio

            client = redis.asyncio.from_url(
                redis_url, decode_responses=False, socket_timeout=5.0
            )
            backend: CredentialVaultBackend = RedisCredentialVaultBackend(client)
        except ImportError:
            logger.warning("redis package unavailable; falling back to in-memory vault")
            backend = MemoryCredentialVaultBackend()
    else:
        backend = MemoryCredentialVaultBackend()
    return CredentialVault(
        backend=backend, fernet_key=fernet_key, ttl_seconds=ttl_seconds
    )


def digest_api_key(api_key: SecretStr) -> str:
    """SHA-256 digest of an API key, suitable as a cache key or log-safe id."""

    return hashlib.sha256(api_key.get_secret_value().encode("utf-8")).hexdigest()


__all__ = [
    "CredentialVault",
    "CredentialVaultBackend",
    "CredentialVaultError",
    "MemoryCredentialVaultBackend",
    "RedisCredentialVaultBackend",
    "build_credential_vault",
    "digest_api_key",
]
