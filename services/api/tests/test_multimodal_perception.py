from __future__ import annotations

from uuid import uuid4

import pytest

from quantum_agent.multimodal.perception import (
    MultimodalPerceptionService,
    PerceptionValidationError,
)


class FencedVisionOutput:
    async def transcribe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str = "image/png",
        instruction: str,
    ) -> str:
        return '```json\n{"confidence": 1}\n```'


@pytest.mark.asyncio
async def test_vision_output_is_not_silently_repaired() -> None:
    service = MultimodalPerceptionService(vision_gateway=FencedVisionOutput())

    with pytest.raises(PerceptionValidationError):
        await service.analyze(
            attachment_id=uuid4(),
            image_bytes=b"image",
            mime_type="image/png",
        )
