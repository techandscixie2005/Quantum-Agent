"""Structured image perception over an injectable vision gateway."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from quantum_agent.multimodal.contracts import (
    ConfirmationState,
    ExtractionMethod,
    VisualEvidence,
    VisualModelEvidence,
)


class VisionTranscriber(Protocol):
    async def transcribe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str = "image/png",
        instruction: str,
    ) -> str: ...


class PerceptionError(RuntimeError):
    pass


class PerceptionUnavailableError(PerceptionError):
    pass


class PerceptionValidationError(PerceptionError):
    """Provider output did not exactly satisfy the Pydantic evidence contract."""


@dataclass(frozen=True, slots=True)
class PerceptionResult:
    evidence: VisualEvidence
    raw_provider_output: str
    model_name: str


class MultimodalPerceptionService:
    """Extract visual evidence without resolving uncertain transcription."""

    pipeline_name = "student-visual-perception"
    pipeline_version = "1.0.0"

    def __init__(
        self,
        *,
        vision_gateway: VisionTranscriber | None,
        model_name: str = "qwen3.8-chat",
        confirmation_threshold: float = 0.80,
    ) -> None:
        if not 0 < confirmation_threshold <= 1:
            raise ValueError("confirmation_threshold must be within (0, 1]")
        self._vision_gateway = vision_gateway
        self._model_name = model_name
        self._confirmation_threshold = confirmation_threshold

    def _instruction(self) -> str:
        schema = json.dumps(
            VisualModelEvidence.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "Transcribe and describe only what is visible. Preserve equations in LaTeX and "
            "student derivation steps verbatim. Never correct, complete, or silently choose an "
            "uncertain symbol. Record every uncertainty in ambiguities with alternatives and "
            "confidence. Return exactly one JSON object with no Markdown fence or commentary "
            f"that validates against this schema: {schema}"
        )

    async def analyze(
        self,
        *,
        attachment_id: UUID,
        image_bytes: bytes,
        mime_type: str,
    ) -> PerceptionResult:
        if self._vision_gateway is None:
            raise PerceptionUnavailableError("vision perception is unavailable")
        raw = await self._vision_gateway.transcribe(
            image_bytes=image_bytes,
            mime_type=mime_type,
            instruction=self._instruction(),
        )
        try:
            model_evidence = VisualModelEvidence.model_validate_json(raw)
        except (ValidationError, ValueError) as error:
            raise PerceptionValidationError(
                "vision output failed the structured evidence contract"
            ) from error

        low_confidence_item = any(
            equation.confidence < self._confirmation_threshold
            for equation in model_evidence.equations
        ) or any(
            step.confidence < self._confirmation_threshold
            for step in model_evidence.derivation_steps
        )
        requires_confirmation = (
            model_evidence.confidence < self._confirmation_threshold
            or low_confidence_item
            or any(ambiguity.requires_confirmation for ambiguity in model_evidence.ambiguities)
        )
        evidence = VisualEvidence(
            **model_evidence.model_dump(),
            attachment_id=attachment_id,
            original_file_reference=f"attachment:{attachment_id}",
            extraction_method=ExtractionMethod.QWEN_VISION,
            confirmation_state=(
                ConfirmationState.REQUIRED
                if requires_confirmation
                else ConfirmationState.NOT_REQUIRED
            ),
            requires_confirmation=requires_confirmation,
        )
        return PerceptionResult(
            evidence=evidence,
            raw_provider_output=raw,
            model_name=self._model_name,
        )


__all__ = [
    "MultimodalPerceptionService",
    "PerceptionError",
    "PerceptionResult",
    "PerceptionUnavailableError",
    "PerceptionValidationError",
    "VisionTranscriber",
]
