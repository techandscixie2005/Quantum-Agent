from __future__ import annotations

import io
import struct
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from quantum_agent.config import Settings
from quantum_agent.llm.routing import ModelCapability, ModelCapabilityRegistry, ModelProfile
from quantum_agent.multimodal.contracts import (
    Ambiguity,
    BoundingBox,
    ConfirmationState,
    CoordinateSystem,
    DocumentBlock,
    DocumentEvidence,
    DocumentLocator,
    ExtractionMethod,
    NormalizedDocumentUnit,
)
from quantum_agent.multimodal.document_capabilities import (
    DocumentCapabilityRequest,
    DocumentCapabilityTransport,
    DocumentTransportProbe,
    build_registry_document_adapters,
)
from quantum_agent.multimodal.documents import (
    DocumentIntelligenceService,
    LegacyOfficeConversionRequest,
    LegacyOfficeConversionResult,
    LegacyOfficeDocumentAdapter,
)
from quantum_agent.multimodal.runtime import build_attachment_runtime


@pytest.mark.asyncio
async def test_native_pptx_preserves_slide_reading_order_and_bounding_boxes(
    tmp_path: Path,
) -> None:
    pptx = pytest.importorskip("pptx")
    path = tmp_path / "lecture-attempt.pptx"
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Spin measurement"
    slide.placeholders[
        1
    ].text = "The student predicts the Stern-Gerlach output before inspecting the experiment."
    presentation.save(path)

    attachment_id = uuid4()
    result = await DocumentIntelligenceService().analyze(
        path=path,
        attachment_id=attachment_id,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    evidence = result.evidence
    assert evidence.attachment_id == attachment_id
    assert evidence.extraction_method == ExtractionMethod.NATIVE
    assert evidence.slide_count == 1
    assert evidence.page_count is None
    assert evidence.units[0].locator.slide_number == 1
    assert [block.reading_order for block in evidence.units[0].blocks] == sorted(
        block.reading_order for block in evidence.units[0].blocks
    )
    located = [block.bounding_box for block in evidence.units[0].blocks if block.bounding_box]
    assert located
    assert all(box.coordinate_system == CoordinateSystem.EMU for box in located)
    assert all(box.slide_number == 1 for box in located)
    assert evidence.fallback_chain[0].method == ExtractionMethod.NATIVE


def _structured_unit() -> NormalizedDocumentUnit:
    page_box = BoundingBox(
        x_min=10,
        y_min=20,
        x_max=200,
        y_max=80,
        coordinate_system=CoordinateSystem.POINTS,
        page_number=1,
        region_id="page-1-formula",
    )
    return NormalizedDocumentUnit(
        ordinal=0,
        locator=DocumentLocator(page_number=1, page_label="i"),
        headings=("Spin", "Measurement"),
        blocks=(
            DocumentBlock(
                reading_order=0,
                kind="text",
                exact_text="Measure along z.",
            ),
            DocumentBlock(
                reading_order=1,
                kind="formula",
                exact_text="S_z|+>=hbar/2|+>",
                latex=r"S_z|+\rangle=\frac{\hbar}{2}|+\rangle",
                bounding_box=page_box,
            ),
            DocumentBlock(
                reading_order=2,
                kind="table",
                exact_text="outcome | probability",
            ),
            DocumentBlock(
                reading_order=3,
                kind="figure",
                exact_text="Stern-Gerlach apparatus",
            ),
            DocumentBlock(
                reading_order=4,
                kind="caption",
                exact_text="Figure 1",
            ),
        ),
        exact_text="Measure along z.",
        formulas_latex=(r"S_z|+\rangle=\frac{\hbar}{2}|+\rangle",),
        tables=("outcome | probability",),
        figures=("Stern-Gerlach apparatus",),
        captions=("Figure 1",),
    )


class PartialNative:
    method = ExtractionMethod.NATIVE
    name = "partial-native"

    async def parse(
        self,
        *,
        path: Path,
        attachment_id: UUID,
        filename: str,
        media_type: str,
    ) -> DocumentEvidence:
        return DocumentEvidence(
            attachment_id=attachment_id,
            original_file_reference=f"attachment:{attachment_id}",
            filename=filename,
            media_type=media_type,
            extraction_method=ExtractionMethod.NATIVE,
            parser_name="partial-native",
            parser_version="1",
            units=(),
            page_count=1,
            confidence=0.5,
            ambiguities=(
                Ambiguity(
                    ambiguity_id="native-scan",
                    field_path="units",
                    reason="No embedded text was found.",
                ),
            ),
            confirmation_state=ConfirmationState.REQUIRED,
            requires_confirmation=True,
        )


class StructuredCapabilityTransport(DocumentCapabilityTransport):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.probe = DocumentTransportProbe(
            supports_document_parsing=True,
            supports_ocr=True,
            max_bytes=25 * 1024 * 1024,
            max_pages=500,
        )

    async def parse_document(
        self,
        *,
        profile: ModelProfile,
        request: DocumentCapabilityRequest,
    ) -> object:
        self.calls.append(profile.profile_id)
        assert request.content == b"scanned-course-page"
        assert request.content_sha256 == sha256(request.content).hexdigest()
        assert ModelCapability.OCR not in profile.capabilities
        return {
            "parser_name": "structured-parser",
            "parser_version": "2026.1",
            "units": [_structured_unit().model_dump(mode="json")],
            "page_count": 1,
            "slide_count": None,
            "confidence": 0.92,
            "ambiguities": [
                {
                    "ambiguity_id": "formula-glyph",
                    "field_path": "units[0].formulas_latex[0]",
                    "reason": "One glyph should be confirmed.",
                    "candidates": [],
                    "bounding_boxes": [],
                    "requires_confirmation": True,
                }
            ],
        }


@pytest.mark.asyncio
async def test_registry_mineru_preserves_structure_and_skips_ocr_when_usable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"scanned-course-page")
    registry = ModelCapabilityRegistry.ustc_default()
    transport = StructuredCapabilityTransport()
    adapters = build_registry_document_adapters(
        registry=registry,
        transport=transport,
    )
    attachment_id = uuid4()
    result = await DocumentIntelligenceService(
        native_adapter=PartialNative(),
        mineru_adapter=adapters.mineru,
        ocr_adapter=adapters.unlimited_ocr,
    ).analyze(
        path=path,
        attachment_id=attachment_id,
        filename="scan.pdf",
        media_type="application/pdf",
    )

    evidence = result.evidence
    assert transport.calls == ["document_parser_primary"]
    assert evidence.extraction_method == ExtractionMethod.MINERU
    assert evidence.requires_confirmation is True
    assert evidence.units[0].headings == ("Spin", "Measurement")
    assert evidence.units[0].formulas_latex
    assert evidence.units[0].tables == ("outcome | probability",)
    assert evidence.units[0].figures == ("Stern-Gerlach apparatus",)
    assert evidence.units[0].captions == ("Figure 1",)
    assert evidence.units[0].blocks[1].bounding_box is not None
    assert evidence.fallback_chain[2].method == ExtractionMethod.UNLIMITED_OCR
    assert evidence.fallback_chain[2].status == "not_needed"


@pytest.mark.asyncio
async def test_runtime_records_unprobed_registry_transports_as_unavailable(
    tmp_path: Path,
) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    path = tmp_path / "blank-scan.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()
    runtime = build_attachment_runtime(
        Settings(
            ENVIRONMENT="test",
            DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path / 'runtime.sqlite3'}",
            ATTACHMENT_STORAGE_ROOT=tmp_path / "attachments",
        ),
        vision_gateway=None,
        auto_process=False,
    )
    result = await runtime.documents.analyze(
        path=path,
        attachment_id=uuid4(),
        filename=path.name,
        media_type="application/pdf",
    )

    attempts = {attempt.method: attempt for attempt in result.evidence.fallback_chain}
    assert attempts[ExtractionMethod.MINERU].status == "unavailable"
    assert attempts[ExtractionMethod.UNLIMITED_OCR].status == "unavailable"
    assert "no file transport" in attempts[ExtractionMethod.MINERU].detail
    assert result.evidence.extraction_method == ExtractionMethod.NATIVE


def _legacy_word_cfb() -> bytes:
    header = bytearray(512)
    header[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", header, 26, 3)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 9)
    return bytes(header) + b"\x00" * 1024


class FakeLegacyWordConverter:
    def __init__(self, converted: bytes) -> None:
        self._converted = converted
        self.request: LegacyOfficeConversionRequest | None = None

    async def convert(
        self,
        request: LegacyOfficeConversionRequest,
    ) -> LegacyOfficeConversionResult:
        self.request = request
        return LegacyOfficeConversionResult(
            output_extension=".docx",
            content=self._converted,
            content_sha256=sha256(self._converted).hexdigest(),
            converter_name="isolated-office-converter",
            converter_version="1.0",
        )


@pytest.mark.asyncio
async def test_typed_legacy_conversion_boundary_reuses_native_docx_parser(
    tmp_path: Path,
) -> None:
    docx = pytest.importorskip("docx")
    output = io.BytesIO()
    document = docx.Document()
    document.add_heading("Spin", level=1)
    document.add_paragraph("The converted student note preserves this exact text.")
    document.save(output)
    converter = FakeLegacyWordConverter(output.getvalue())
    source = tmp_path / "student-note.doc"
    source.write_bytes(_legacy_word_cfb())
    attachment_id = uuid4()
    result = await DocumentIntelligenceService(
        legacy_adapter=LegacyOfficeDocumentAdapter(converter=converter),
    ).analyze(
        path=source,
        attachment_id=attachment_id,
        filename=source.name,
        media_type="application/msword",
    )

    assert converter.request is not None
    assert converter.request.source_extension == ".doc"
    assert converter.request.target_extension == ".docx"
    assert result.evidence.extraction_method == ExtractionMethod.LEGACY_CONVERSION
    assert result.evidence.filename == source.name
    assert result.evidence.media_type == "application/msword"
    assert "isolated-office-converter" in result.evidence.parser_name
    assert result.evidence.units[0].headings == ("Spin",)
    assert "converted student note" in result.evidence.units[1].exact_text
