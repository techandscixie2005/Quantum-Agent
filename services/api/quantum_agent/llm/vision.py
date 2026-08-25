"""Vision gateway for OCR of scanned course material.

The USTC OpenAI-compatible endpoint accepts ``image_url`` content on a
vision-capable model.  This gateway sends a single rendered page as a base64
data URI and returns the transcribed text.  It is deliberately separate from
:mod:`quantum_agent.llm.gateway` because the multimodal request shape does not
fit the text-only ``PromptedOutput`` contract, and the vision model is a
distinct configuration value.
"""

from __future__ import annotations

from typing import Any

import httpx2
from pydantic import SecretStr


class VisionGatewayError(RuntimeError):
    """Sanitized vision-provider failure safe to surface in a CLI trace."""


_TRANSIENT_MARKERS: frozenset[str] = frozenset(
    {
        "HTTP 429",
        "HTTP 500",
        "HTTP 502",
        "HTTP 503",
        "HTTP 504",
        "empty content",
    }
)


class VisionGateway:
    """A minimal vision-completion client over the USTC OpenAI-compatible API."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        timeout_seconds: float = 300.0,
        max_retries: int = 2,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("A non-empty backend API key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._http_client = http_client

    async def transcribe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str = "image/png",
        instruction: str = "Transcribe the full page text, preserving all equations in LaTeX.",
    ) -> str:
        """Return the vision model's transcription of one rendered page image."""

        if not image_bytes:
            raise ValueError("image_bytes must be non-empty")

        import base64

        encoded = base64.b64encode(image_bytes).decode("ascii")
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }
        url = f"{self._base_url}/chat/completions"

        owned_client = self._http_client is None
        client = self._http_client or httpx2.AsyncClient(timeout=self._timeout_seconds)
        last_error: Exception | None = None
        try:
            for _attempt in range(self._max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=body)
                    if not response.is_success:
                        raise VisionGatewayError(f"HTTP {response.status_code}")
                    payload = response.json()
                    content = payload["choices"][0]["message"].get("content", "")
                    if not content:
                        raise VisionGatewayError("empty content")
                    return str(content)
                except httpx2.HTTPError as exc:
                    last_error = exc
                    continue
                except VisionGatewayError as exc:
                    if str(exc) not in _TRANSIENT_MARKERS:
                        raise
                    last_error = exc
                    continue
            raise VisionGatewayError("vision provider request failed") from last_error
        finally:
            if owned_client:
                await client.aclose()
