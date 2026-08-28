"""Per-session ModelRouter resolution backed by the credential vault.

PRD V3.1 §3.2: every agent call flows through the central ``ModelGateway``.
When a student logs in with their own API key, the vault stores the
Fernet-encrypted key keyed by ``session_id``.  This module builds and caches
a :class:`ModelRouter` per credential (LRU-bounded, keyed by SHA-256 digest)
so repeated turns on the same session reuse the router without re-decrypting
the key on every call.

When the vault has no entry for a session (e.g. the startup ``USTC_API`` env
key is being used), the fallback router is returned unchanged — this is the
PRD §3.3 last-bullet dev/deploy fallback.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Protocol
from uuid import UUID

from pydantic import SecretStr

from quantum_agent.credential_vault import CredentialVault, digest_api_key
from quantum_agent.llm.gateway import ModelGateway
from quantum_agent.llm.routing import (
    ModelCapabilityRegistry,
    ModelProfile,
    ModelRouter,
    ModelTask,
)
from quantum_agent.llm.vision import VisionGateway

logger = logging.getLogger(__name__)

_LRU_MAX = 32


class ModelGatewayFactory(Protocol):
    """Builds a ``ModelGateway`` for one credential + profile.

    The ``api_key`` is the per-session credential decrypted from the vault;
    ``base_url`` is the shared USTC endpoint.  The factory is stateless beyond
    these arguments so routers can be built on demand and cached by digest.
    """

    def __call__(
        self,
        *,
        api_key: SecretStr,
        profile: ModelProfile,
        base_url: str,
    ) -> ModelGateway: ...


class CredentialScopedRouterFactory:
    """Caches a ``ModelRouter`` per API-key digest.

    The cache key is the SHA-256 digest of the plaintext key, never the
    plaintext itself.  ``forget`` evicts a single digest; ``forget_session``
    looks up the digest via the vault and evicts it.  The cache is bounded by
    an LRU policy so a flood of distinct keys cannot grow it unboundedly.
    """

    def __init__(
        self,
        *,
        registry: ModelCapabilityRegistry,
        gateway_factory: ModelGatewayFactory,
        fallback_router: ModelRouter | None,
        vault: CredentialVault | None,
        base_url: str,
    ) -> None:
        self._registry = registry
        self._gateway_factory = gateway_factory
        self._fallback_router = fallback_router
        self._vault = vault
        self._base_url = base_url.rstrip("/")
        self._routers: OrderedDict[str, ModelRouter] = OrderedDict()
        self._session_digests: OrderedDict[UUID, str] = OrderedDict()
        self._lock = asyncio.Lock()

    def _build_router(self, api_key: SecretStr) -> ModelRouter:
        def factory(profile: ModelProfile) -> ModelGateway:
            return self._gateway_factory(
                api_key=api_key, profile=profile, base_url=self._base_url
            )

        return ModelRouter(registry=self._registry, gateway_factory=factory)

    async def router_for_session(
        self,
        session_id: UUID,
    ) -> ModelRouter | None:
        """Return the per-credential router for a session, or the fallback.

        Returns None when neither a vault entry nor a fallback router exists
        (the caller then surfaces a 503/401 rather than silently degrading).
        """

        if self._vault is None:
            return self._fallback_router
        api_key = await self._vault.load(session_id)
        if api_key is None or not api_key.get_secret_value():
            # An authenticated session must never silently bill the deployment
            # credential.  Fallback is reserved for unauthenticated/dev use.
            return None
        digest = digest_api_key(api_key)
        async with self._lock:
            router = self._routers.pop(digest, None)
            if router is None:
                router = self._build_router(api_key)
            self._routers[digest] = router
            self._session_digests.pop(session_id, None)
            self._session_digests[session_id] = digest
            self._evict_if_needed()
        return router

    async def vision_gateway_for_session(self, session_id: UUID) -> VisionGateway | None:
        """Build a vision/OCR gateway from the same logged-in credential."""

        if self._vault is None:
            return None
        api_key = await self._vault.load(session_id)
        if api_key is None or not api_key.get_secret_value():
            return None
        digest = digest_api_key(api_key)
        async with self._lock:
            self._session_digests.pop(session_id, None)
            self._session_digests[session_id] = digest
            self._evict_session_digests_if_needed()
        profile = self._registry.profiles_for(ModelTask.VISION)[0]
        return VisionGateway(
            api_key=api_key,
            base_url=self._base_url,
            model=profile.provider_model,
        )

    async def forget_session(self, session_id: UUID) -> None:
        """Evict the vault entry, drop the session→digest mapping, and remove
        the cached router for that digest **only if no other live session
        still maps to it**.

        Two sessions sharing the same API key share one cached router; logout
        of one must not tear down the other's router.  The vault entry is
        always removed (each session has its own vault slot).
        """

        if self._vault is not None:
            await self._vault.forget(session_id)
        async with self._lock:
            digest = self._session_digests.pop(session_id, None)
            if digest is None:
                return
            still_in_use = any(
                other_digest == digest for other_digest in self._session_digests.values()
            )
            if not still_in_use:
                self._routers.pop(digest, None)

    async def forget_digest(self, digest: str) -> None:
        async with self._lock:
            self._routers.pop(digest, None)

    def _evict_if_needed(self) -> None:
        while len(self._routers) > _LRU_MAX:
            digest, _router = self._routers.popitem(last=False)
            stale_sessions = [
                session_id
                for session_id, cached_digest in self._session_digests.items()
                if cached_digest == digest
            ]
            for session_id in stale_sessions:
                self._session_digests.pop(session_id, None)
        self._evict_session_digests_if_needed()

    def _evict_session_digests_if_needed(self) -> None:
        while len(self._session_digests) > _LRU_MAX * 4:
            self._session_digests.popitem(last=False)

    def __repr__(self) -> str:
        return "CredentialScopedRouterFactory(cache=<redacted>)"


__all__ = ["CredentialScopedRouterFactory", "ModelGatewayFactory"]
