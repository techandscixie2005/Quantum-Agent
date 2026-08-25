from __future__ import annotations

from pathlib import Path

import pytest

from quantum_agent.knowledge.ingestion import (
    LocatorType,
    OutlineEntryType,
    parse_docx_outline_seed,
    parse_pdf_document,
    parse_xlsx_hierarchy_seed,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _knowledge_file(filename: str) -> Path:
    candidates = (REPOSITORY_ROOT / "knowledge" / filename, Path("/knowledge") / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip(f"real course material is absent: {filename}")


def test_real_2026_outline_preserves_authored_structure_and_source_anomaly() -> None:
    pytest.importorskip("docx")
    source = _knowledge_file("量子物理-教学大纲.docx")

    outline = parse_docx_outline_seed(source)

    chapters = [entry for entry in outline.entries if entry.entry_type == OutlineEntryType.CHAPTER]
    assert outline.academic_year == 2026
    assert outline.term == "秋"
    assert len(chapters) == 6
    assert [chapter.hours for chapter in chapters] == [4, 28, 8, 12, 16, 12]
    duplicate_423 = [
        entry
        for entry in outline.entries
        if entry.outline_number == "4.2.3" and "DUPLICATE_OUTLINE_NUMBER" in entry.review_flags
    ]
    assert len(duplicate_423) == 2
    assert all(
        entry.source_locator.locator_type == LocatorType.PARAGRAPH for entry in outline.entries
    )
    assert all(entry.source_locator.physical_page is None for entry in outline.entries)
    assert all(entry.source_locator.page_label is None for entry in outline.entries)


def test_real_course_hierarchy_seed_has_verbatim_provenance_and_typed_edges() -> None:
    pytest.importorskip("openpyxl")
    source = _knowledge_file("量子物理-知识图谱(1).xlsx")

    seed = parse_xlsx_hierarchy_seed(source)

    assert len(seed.nodes) >= 300
    assert len(seed.relations) >= 350
    bohr = next(node for node in seed.nodes if node.verbatim_label == "玻尔假说")
    assert bohr.source_locator.locator_type == LocatorType.SHEET_ROW
    assert bohr.source_locator.sheet_name == "Sheet3"
    assert bohr.verbatim_label in bohr.source_row_text
    assert all(relation.source_chunk_id for relation in seed.relations)
    assert all(relation.evidence_snippet for relation in seed.relations)


def _require_pymupdf() -> None:
    try:
        __import__("pymupdf")
    except ImportError:
        try:
            __import__("fitz")
        except ImportError:
            pytest.skip("PyMuPDF is not installed")


def test_real_course_pdf_smoke_is_page_aware() -> None:
    _require_pymupdf()
    source = _knowledge_file("第五章 微扰理论.pdf")

    parsed = parse_pdf_document(source)

    assert parsed.units
    assert parsed.chunks
    page_count = parsed.metadata["page_count"]
    assert isinstance(page_count, int)
    assert len(parsed.units) == page_count
    assert parsed.units[0].locator.physical_page == 1
    assert all(unit.locator.locator_type == LocatorType.PAGE for unit in parsed.units)
    assert all(chunk.locator.start == chunk.locator.end for chunk in parsed.chunks)
    assert all(chunk.evidence_snippet in chunk.exact_text for chunk in parsed.chunks)
