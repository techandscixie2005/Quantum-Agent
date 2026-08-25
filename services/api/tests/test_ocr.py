"""Tests for the vision OCR path that turns a scanned PDF into chunks.

The full vision call is deterministic; a fake `transcribe` stands in for the
vision model so tests never spend model tokens or hit the network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from quantum_agent.knowledge.ingestion import (
    OCR_PARSER_NAME,
    parse_scanned_pdf_document,
)


def _make_scanned_pdf(directory: Path) -> Path:
    pymupdf = _pymupdf_or_skip()
    source = directory / "scanned.pdf"
    document = pymupdf.open()
    for _ in range(3):
        # Blank rendered pages mimic a scan with no text layer.
        document.new_page()
    document.save(source)
    document.close()
    return source


@pytest.mark.asyncio
async def test_scanned_pdf_ocr_produces_chunks(tmp_path: Path) -> None:
    source = _make_scanned_pdf(tmp_path)
    calls: list[bytes] = []

    async def transcribe(image_bytes: bytes) -> str:
        calls.append(image_bytes)
        return "波函数的统计解释 $\\int |\\Psi|^2 = 1$"

    parsed = await parse_scanned_pdf_document(source, transcribe=transcribe)

    assert parsed.parser_name == OCR_PARSER_NAME
    assert len(parsed.units) == 3
    assert len(calls) == 3
    assert any("$\\int" in text for text in [u.content_text for u in parsed.units])
    assert all(u.status.value == "READY" for u in parsed.units)


def _pymupdf_or_skip() -> Any:
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        try:
            import fitz  # type: ignore[import-untyped]

            return fitz
        except ImportError:
            pytest.skip("PyMuPDF is not installed")
