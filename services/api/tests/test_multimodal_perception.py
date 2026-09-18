from __future__ import annotations

from uuid import uuid4

import pytest

from quantum_agent.multimodal.perception import (
    MultimodalPerceptionService,
    PerceptionValidationError,
)


class FencedVisionOutput:
    content = '{"confidence": 1}'
    async def transcribe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str = "image/png",
        instruction: str,
    ) -> str:
        return f"```json\n{self.content}\n```"


@pytest.mark.asyncio
async def test_vision_output_is_not_silently_repaired() -> None:
    service = MultimodalPerceptionService(vision_gateway=FencedVisionOutput())

    with pytest.raises(PerceptionValidationError):
        await service.analyze(
            attachment_id=uuid4(),
            image_bytes=b"image",
            mime_type="image/png",
        )


@pytest.mark.asyncio
async def test_single_json_fence_is_an_envelope_not_a_symbol_correction() -> None:
    vision = FencedVisionOutput()
    vision.content = '{"confidence": 0.5, "detected_text": "H psi = ?"}'
    result = await MultimodalPerceptionService(vision_gateway=vision).analyze(
        attachment_id=uuid4(), image_bytes=b"image", mime_type="image/png",
    )
    assert result.evidence.detected_text == "H psi = ?"
    assert result.evidence.requires_confirmation
