from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
from pydantic import ValidationError

from quantum_agent.knowledge.evidence_packets import (
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidencePacket,
    LocatorType,
    RetrievalChannel,
    RetrievalContribution,
    RetrievalCoverage,
)


def _item(snippet: str = "波函数的统计解释") -> EvidenceItem:
    source_chunk = "本节讨论波函数的统计解释以及概率密度。"
    return EvidenceItem(
        evidence_id=uuid4(),
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_title="第1–2章",  # noqa: RUF001 - exact course typography
        document_version=1,
        source_file_name="第1-2章.pdf",
        source_file_sha256="a" * 64,
        source_chunk_sha256=hashlib.sha256(source_chunk.encode()).hexdigest(),
        evidence_sha256=hashlib.sha256(snippet.encode()).hexdigest(),
        chapter="第二章",
        section_path=["2-3 波函数及其统计解释"],
        locator=EvidenceLocator(locator_type=LocatorType.PDF_PAGE, physical_page=75),
        source_chunk=source_chunk,
        evidence_snippet=snippet,
        kind=EvidenceKind.COURSE_MATERIAL,
        authority_priority=90,
        contributions=[
            RetrievalContribution(
                channel=RetrievalChannel.FULL_TEXT,
                rank=1,
                raw_score=0.8,
                fused_score=1 / 61,
            )
        ],
    )


def test_evidence_requires_exact_source_support_after_whitespace_normalization() -> None:
    item = _item("波函数 的统计解释")
    assert item.locator.physical_page == 75
    with pytest.raises(ValidationError, match="not grounded"):
        _item("模型自己补写的结论")


def test_not_found_packet_cannot_smuggle_evidence() -> None:
    with pytest.raises(ValidationError, match="cannot contain evidence"):
        EvidencePacket(
            course_id=uuid4(),
            curriculum_edition_id=uuid4(),
            query="课程没有覆盖的问题",
            coverage=RetrievalCoverage.NOT_FOUND,
            evidence=[_item()],
        )


def test_covered_packet_exposes_allowlisted_citation_ids() -> None:
    item = _item()
    packet = EvidencePacket(
        course_id=uuid4(),
        curriculum_edition_id=uuid4(),
        query="什么是波函数的统计解释？",  # noqa: RUF001 - Chinese punctuation
        coverage=RetrievalCoverage.SUFFICIENT,
        evidence=[item],
    )
    assert packet.citation_ids() == {item.evidence_id}
