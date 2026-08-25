from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from quantum_agent.knowledge.source_manifest import (
    CourseSourceManifest,
    load_manifest,
    verify_sources,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = REPOSITORY_ROOT / "content" / "quantum_course" / "manifest.toml"


def _valid_manifest_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "course_key": "quantum-test",
        "course_title": "Quantum Test",
        "knowledge_root": "knowledge",
        "governance": {
            "canonical_curriculum_edition": "edition-a",
            "student_visibility_rule": "published_only",
            "unmatched_extraction_status": "REVIEW_REQUIRED",
            "chapter_merge_rule": "never_merge_by_number_alone",
        },
        "curriculum_editions": [
            {"key": "edition-a", "title": "A", "chapter_count": 6, "canonical": True},
            {"key": "edition-b", "title": "B", "chapter_count": 8, "canonical": False},
        ],
        "sources": [],
        "alignment_hints": [
            {
                "from": "edition-a:chapter-1",
                "to": "edition-b:chapter-2",
                "reason": "teacher review seed",
                "status": "REVIEW_REQUIRED",
            }
        ],
    }


def test_real_course_manifest_reconciles_all_authoritative_files() -> None:
    if not (REPOSITORY_ROOT / "knowledge").exists():
        pytest.skip("private course materials are not mounted")
    manifest = load_manifest(MANIFEST)
    results = verify_sources(manifest, repository_root=REPOSITORY_ROOT)
    assert len(results) == 12
    assert all(item.exists for item in results)
    assert all(item.checksum_matches for item in results)
    assert sum(item.source.requires_ocr for item in results) == 1
    assert manifest.governance.chapter_merge_rule == "never_merge_by_number_alone"


def test_manifest_has_one_canonical_six_chapter_edition() -> None:
    manifest = load_manifest(MANIFEST)
    canonical = [edition for edition in manifest.curriculum_editions if edition.canonical]
    assert [(edition.key, edition.chapter_count) for edition in canonical] == [
        ("syllabus-2026-fall", 6)
    ]
    assert any(edition.chapter_count == 8 for edition in manifest.curriculum_editions)


@pytest.mark.parametrize(
    "unsafe_root",
    ["../knowledge", "/knowledge", r"C:\knowledge", "."],
)
def test_manifest_rejects_unsafe_knowledge_root(unsafe_root: str) -> None:
    payload = _valid_manifest_payload()
    payload["knowledge_root"] = unsafe_root
    with pytest.raises(ValidationError, match="safe non-root relative path"):
        CourseSourceManifest.model_validate(payload)


def test_manifest_requires_canonical_flag_to_match_governance_key() -> None:
    payload = _valid_manifest_payload()
    governance = payload["governance"]
    assert isinstance(governance, dict)
    governance["canonical_curriculum_edition"] = "edition-b"
    with pytest.raises(ValidationError, match=r"canonical=true.*must match"):
        CourseSourceManifest.model_validate(payload)


def test_manifest_rejects_approved_or_same_edition_alignment_hints() -> None:
    approved = _valid_manifest_payload()
    approved_hints = approved["alignment_hints"]
    assert isinstance(approved_hints, list)
    approved_hints[0]["status"] = "APPROVED"
    with pytest.raises(ValidationError, match="REVIEW_REQUIRED"):
        CourseSourceManifest.model_validate(approved)

    same_edition = _valid_manifest_payload()
    same_edition_hints = same_edition["alignment_hints"]
    assert isinstance(same_edition_hints, list)
    same_edition_hints[0]["to"] = "edition-a:chapter-2"
    with pytest.raises(ValidationError, match="distinct curriculum editions"):
        CourseSourceManifest.model_validate(same_edition)


def test_resolved_knowledge_root_must_remain_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    (repository / "knowledge").symlink_to(outside, target_is_directory=True)
    manifest = CourseSourceManifest.model_validate(_valid_manifest_payload())
    with pytest.raises(ValueError, match="repository boundary"):
        verify_sources(manifest, repository_root=repository)
