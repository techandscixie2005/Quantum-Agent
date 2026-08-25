from __future__ import annotations

# Test fixtures intentionally reproduce course-authored Chinese punctuation.
# ruff: noqa: RUF001
import hashlib
from pathlib import Path
from typing import Protocol, cast

import pytest

from quantum_agent.knowledge.ingestion import (
    IngestionConfig,
    LocatorType,
    OutlineEntryType,
    SeedRelationType,
    parse_document,
    parse_docx_outline_seed,
    parse_pdf_document,
    parse_xlsx_hierarchy_seed,
)


def test_markdown_is_exact_deterministic_and_section_aware(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source_bytes = (
        "# 波函数\n\n原样保留  两个空格与 $\\psi$。\n"
        "## 统计解释\nBorn 解释。\n" + ("量子态内容。" * 30)
    ).encode()
    source.write_bytes(source_bytes)
    config = IngestionConfig(max_chunk_chars=128, chunk_overlap_chars=16)

    first = parse_document(source, config=config)
    second = parse_document(source, config=config)

    assert first.sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert first.document_id == second.document_id
    assert [chunk.id for chunk in first.chunks] == [chunk.id for chunk in second.chunks]
    assert [chunk.checksum for chunk in first.chunks] == [chunk.checksum for chunk in second.chunks]
    assert first.units[0].section_path == ("波函数",)
    assert first.units[1].section_path == ("波函数", "统计解释")
    assert "原样保留  两个空格" in first.units[0].content_text
    assert any("Born 解释" in chunk.exact_text for chunk in first.chunks)
    assert all(chunk.locator.locator_type == LocatorType.LINE for chunk in first.chunks)
    assert all(
        chunk.evidence_snippet
        == chunk.exact_text[chunk.evidence_char_start : chunk.evidence_char_end]
        for chunk in first.chunks
    )


def test_docx_outline_uses_paragraph_ordinals_and_flags_duplicate_numbers(
    tmp_path: Path,
) -> None:
    docx = pytest.importorskip("docx")
    source = tmp_path / "outline.docx"
    document = docx.Document()
    document.add_paragraph("《量子物理》教学大纲")
    document.add_paragraph("---2026，秋---")
    document.add_paragraph("")
    document.add_paragraph("第四章  原子结构 (12学时)")
    document.add_paragraph("4.2.3 塞曼效应")
    document.add_paragraph("4.2.3 自旋-轨道作用")
    document.save(source)

    outline = parse_docx_outline_seed(source)

    assert outline.academic_year == 2026
    assert outline.term == "秋"
    chapter = next(
        entry for entry in outline.entries if entry.entry_type == OutlineEntryType.CHAPTER
    )
    assert chapter.hours == 12
    assert chapter.source_locator.start == 4  # blank paragraphs still count in the ordinal
    duplicates = [
        entry for entry in outline.entries if "DUPLICATE_OUTLINE_NUMBER" in entry.review_flags
    ]
    assert [entry.source_locator.start for entry in duplicates] == [5, 6]
    assert all(entry.review_required for entry in duplicates)
    assert all(
        entry.source_locator.locator_type == LocatorType.PARAGRAPH for entry in outline.entries
    )
    assert all(entry.source_locator.physical_page is None for entry in outline.entries)
    assert all(entry.source_locator.page_label is None for entry in outline.entries)
    assert all(
        entry.verbatim_label in outline.document.chunks[index].exact_text
        for index, entry in enumerate(outline.entries)
    )


def test_xlsx_hierarchy_seed_preserves_labels_aliases_and_relation_direction(
    tmp_path: Path,
) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "seed.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "图谱"
    sheet.append(["模板说明"])
    sheet.append(
        [
            "节点类型*",
            "节点名称",
            "节点名称",
            "节点名称",
            "节点名称",
            "节点名称",
            "节点名称",
            "节点名称",
            "前置节点",
            "后置节点",
            "关联节点",
            "标签",
            "知识点分类",
            "节点说明",
        ]
    )
    sheet.append(["分类", "量子力学基础"])
    sheet.append(["知识点", None, "电子组态（电子构型）", None, None, None, None, None, "先修概念"])
    sheet.append(["知识点", None, "先修概念"])
    sheet.append(["知识点", None, "待核验概念", None, None, None, None, None, "不存在的节点"])
    workbook.save(source)

    seed = parse_xlsx_hierarchy_seed(source)

    target = next(node for node in seed.nodes if node.verbatim_label == "电子组态（电子构型）")
    assert target.canonical_label == "电子组态(电子构型)"
    assert target.aliases == ("电子组态", "电子构型")
    assert "AUTHORED_PARENTHETICAL_ALIAS" in target.review_flags
    prerequisite = next(
        relation
        for relation in seed.relations
        if relation.relation_type == SeedRelationType.PREREQUISITE_OF
        and relation.verbatim_target_label == target.verbatim_label
    )
    source_node = next(node for node in seed.nodes if node.id == prerequisite.source_node_id)
    assert source_node.verbatim_label == "先修概念"
    assert prerequisite.target_node_id == target.id
    unresolved = next(
        relation for relation in seed.relations if relation.verbatim_source_label == "不存在的节点"
    )
    assert unresolved.source_node_id is None
    assert unresolved.review_required
    assert "UNRESOLVED_REFERENCE" in unresolved.review_flags
    assert "不存在的节点" in unresolved.evidence_snippet


def test_pptx_chunks_never_cross_slide_boundaries(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    source = tmp_path / "lecture.pptx"
    presentation = pptx.Presentation()
    slide_one = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide_one.shapes.title.text = "叠加原理"
    slide_one.placeholders[1].text = "态矢量的线性组合仍是允许态。"
    slide_two = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide_two.shapes.title.text = "测量"
    slide_two.placeholders[1].text = "测量结果是厄米算符本征值。"
    presentation.save(source)

    parsed = parse_document(source, config=IngestionConfig(slide_low_text_characters=0))

    assert len(parsed.units) == 2
    assert {int(chunk.locator.start) for chunk in parsed.chunks} == {1, 2}
    assert all(chunk.locator.start == chunk.locator.end for chunk in parsed.chunks)
    assert all(chunk.locator.locator_type == LocatorType.SLIDE for chunk in parsed.chunks)
    assert all(
        "叠加原理" not in chunk.exact_text for chunk in parsed.chunks if chunk.locator.start == 2
    )


class _PyMuPDFPage(Protocol):
    def insert_text(self, point: tuple[int, int], text: str) -> object: ...


class _PyMuPDFDocument(Protocol):
    def new_page(self) -> _PyMuPDFPage: ...

    def save(self, filename: str | Path) -> object: ...

    def close(self) -> object: ...


class _PyMuPDFModule(Protocol):
    def open(self) -> _PyMuPDFDocument: ...


def _pymupdf_or_skip() -> _PyMuPDFModule:
    try:
        import pymupdf

        return cast(_PyMuPDFModule, pymupdf)
    except ImportError:
        try:
            import fitz  # type: ignore[import-untyped]

            return cast(_PyMuPDFModule, fitz)
        except ImportError:
            pytest.skip("PyMuPDF is not installed")


def test_pdf_has_physical_pages_no_invented_labels_and_conservative_margins(
    tmp_path: Path,
) -> None:
    pymupdf = _pymupdf_or_skip()
    source = tmp_path / "lecture.pdf"
    document = pymupdf.open()
    for page_number in range(1, 5):
        page = document.new_page()
        page.insert_text((72, 20), "Quantum Physics Course")
        page.insert_text((72, 200), f"Evidence on physical page {page_number}: wave function")
        page.insert_text((300, 820), str(page_number))
    document.save(source)
    document.close()

    parsed = parse_pdf_document(source, config=IngestionConfig(pdf_low_text_characters=1))

    assert [unit.locator.physical_page for unit in parsed.units] == [1, 2, 3, 4]
    assert all(unit.locator.page_label is None for unit in parsed.units)
    assert all("Evidence on physical page" in unit.content_text for unit in parsed.units)
    assert all("Quantum Physics Course" not in unit.content_text for unit in parsed.units)
    assert all("Quantum Physics Course" in unit.raw_text for unit in parsed.units)
    assert all(unit.removed_marginalia for unit in parsed.units)
    assert all(chunk.locator.start == chunk.locator.end for chunk in parsed.chunks)
