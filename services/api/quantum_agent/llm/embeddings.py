"""Independent embedding gateway; chat compatibility never implies embeddings."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

import httpx
from pydantic import BaseModel, SecretStr


class EmbeddingProbe(BaseModel):
    available: bool
    dimensions: int | None = None
    provider: str
    detail: str | None = None


class EmbeddingGateway(Protocol):
    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def probe(self) -> EmbeddingProbe: ...


class HashingEmbeddingGateway:
    """Deterministic offline fallback for tests and degraded local search.

    This is deliberately reported as `local_hashing`, not as a learned semantic
    model.  Production readiness must remain degraded until a configured
    embedding endpoint passes its probe.
    """

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 32:
            raise ValueError("Embedding dimensions must be at least 32")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = re.sub(r"\s+", "", text.casefold())
        features = [normalized[index : index + 2] for index in range(max(0, len(normalized) - 1))]
        features.extend(re.findall(r"[a-z0-9_]+", text.casefold()))
        return features or ["<empty>"]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            values = [0.0] * self._dimensions
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
                index = int.from_bytes(digest[:8], "big") % self._dimensions
                sign = 1.0 if digest[8] & 1 else -1.0
                values[index] += sign
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            vectors.append([value / norm for value in values])
        return vectors

    async def probe(self) -> EmbeddingProbe:
        return EmbeddingProbe(
            available=True,
            dimensions=self._dimensions,
            provider="local_hashing",
            detail="Deterministic lexical fallback; not a learned semantic model",
        )


class OpenAICompatibleEmbeddingGateway:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        dimensions: int,
        base_url: str,
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("A separate embedding API key is required")
        if not model:
            raise ValueError("Embedding model must be configured explicitly")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        owned_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                json={"model": self._model, "input": list(texts)},
            )
            response.raise_for_status()
            payload = response.json()
            ordered = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
            vectors = [item.get("embedding") for item in ordered]
            if len(vectors) != len(texts) or any(
                not isinstance(vector, list) for vector in vectors
            ):
                raise RuntimeError("Embedding provider returned an invalid batch")
            if any(len(vector) != self._dimensions for vector in vectors):
                raise RuntimeError("Embedding dimension does not match configured schema")
            return [[float(value) for value in vector] for vector in vectors]
        except httpx.HTTPError as exc:
            raise RuntimeError("Embedding provider request failed") from exc
        finally:
            if owned_client:
                await client.aclose()

    async def probe(self) -> EmbeddingProbe:
        try:
            vectors = await self.embed(["量子态 normalization probe"])
            return EmbeddingProbe(
                available=True,
                dimensions=len(vectors[0]),
                provider="openai_compatible",
            )
        except Exception as exc:
            return EmbeddingProbe(
                available=False,
                provider="openai_compatible",
                detail=type(exc).__name__,
            )
