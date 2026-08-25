"""Versioned course-source manifest and immutable file verification."""

from __future__ import annotations

import hashlib
import tomllib
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceAuthority(StrEnum):
    COURSE_POLICY = "course_policy"
    COURSE_STRUCTURE = "course_structure"
    COURSE_MATERIAL = "course_material"
    COURSE_REFERENCE = "course_reference"
    REFERENCE = "reference"


class ManifestSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    kind: str = Field(min_length=1)
    authority: SourceAuthority
    priority: int = Field(ge=0, le=100)
    locator: str = Field(min_length=1)
    curriculum_edition: str | None = None
    claim_scope: str | None = None
    requires_ocr: bool = False
    initial_status: str | None = None

    @model_validator(mode="after")
    def require_review_for_ocr(self) -> ManifestSource:
        candidate = Path(self.path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("manifest source paths must be safe relative paths")
        if self.requires_ocr and self.initial_status != "REVIEW_REQUIRED":
            raise ValueError("OCR sources must begin in REVIEW_REQUIRED")
        return self


class CurriculumEditionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    chapter_count: int = Field(ge=1)
    canonical: bool = False


class AlignmentHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    status: Literal["REVIEW_REQUIRED"]


class CourseGovernance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_curriculum_edition: str
    student_visibility_rule: str
    unmatched_extraction_status: str
    chapter_merge_rule: str


class CourseSourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    course_key: str
    course_title: str
    knowledge_root: str = Field(min_length=1)
    governance: CourseGovernance
    curriculum_editions: list[CurriculumEditionManifest]
    sources: list[ManifestSource]
    alignment_hints: list[AlignmentHint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_curriculum_references(self) -> CourseSourceManifest:
        knowledge_root = Path(self.knowledge_root)
        windows_root = PureWindowsPath(self.knowledge_root)
        if (
            knowledge_root.is_absolute()
            or windows_root.is_absolute()
            or bool(windows_root.drive)
            or ".." in knowledge_root.parts
            or ".." in windows_root.parts
            or knowledge_root == Path(".")
            or not self.knowledge_root.strip()
        ):
            raise ValueError("knowledge_root must be a safe non-root relative path")

        keys = {edition.key for edition in self.curriculum_editions}
        if len(keys) != len(self.curriculum_editions):
            raise ValueError("curriculum edition keys must be unique")
        if self.governance.canonical_curriculum_edition not in keys:
            raise ValueError("canonical curriculum edition is missing")
        canonical_keys = [edition.key for edition in self.curriculum_editions if edition.canonical]
        if len(canonical_keys) != 1:
            raise ValueError("exactly one curriculum edition must be canonical")
        if canonical_keys[0] != self.governance.canonical_curriculum_edition:
            raise ValueError(
                "canonical=true curriculum edition must match "
                "governance.canonical_curriculum_edition"
            )
        missing = {
            source.curriculum_edition
            for source in self.sources
            if source.curriculum_edition and source.curriculum_edition not in keys
        }
        if missing:
            raise ValueError(f"unknown curriculum editions: {sorted(missing)}")
        paths = [source.path for source in self.sources]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest source paths must be unique")

        for hint in self.alignment_hints:
            source_edition, separator, source_locator = hint.from_.partition(":")
            target_references = [item.strip() for item in hint.to.split(",")]
            parsed_targets = [item.partition(":") for item in target_references]
            if (
                not separator
                or not source_locator
                or any(
                    not target_separator or not locator
                    for _, target_separator, locator in parsed_targets
                )
            ):
                raise ValueError("alignment hints require edition-qualified from/to references")
            target_editions = {edition for edition, _, _ in parsed_targets}
            referenced_editions = {source_edition, *target_editions}
            unknown_editions = referenced_editions - keys
            if unknown_editions:
                raise ValueError(
                    f"alignment hint references unknown editions: {sorted(unknown_editions)}"
                )
            if source_edition in target_editions:
                raise ValueError("alignment hints must connect distinct curriculum editions")
        return self


class SourceVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ManifestSource
    resolved_path: Path
    exists: bool
    checksum_matches: bool
    actual_sha256: str | None = None
    size_bytes: int | None = None


def load_manifest(path: Path) -> CourseSourceManifest:
    with path.open("rb") as stream:
        return CourseSourceManifest.model_validate(tomllib.load(stream))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sources(
    manifest: CourseSourceManifest,
    *,
    repository_root: Path,
) -> list[SourceVerification]:
    resolved_repository_root = repository_root.resolve()
    source_root = (resolved_repository_root / manifest.knowledge_root).resolve()
    try:
        source_root.relative_to(resolved_repository_root)
    except ValueError as exc:
        raise ValueError("knowledge_root escapes the repository boundary") from exc
    results: list[SourceVerification] = []
    for source in manifest.sources:
        resolved = (source_root / source.path).resolve()
        try:
            resolved.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"Source escapes knowledge root: {source.path}") from exc
        if not resolved.is_file():
            results.append(
                SourceVerification(
                    source=source,
                    resolved_path=resolved,
                    exists=False,
                    checksum_matches=False,
                )
            )
            continue
        actual = sha256_file(resolved)
        results.append(
            SourceVerification(
                source=source,
                resolved_path=resolved,
                exists=True,
                checksum_matches=actual == source.sha256,
                actual_sha256=actual,
                size_bytes=resolved.stat().st_size,
            )
        )
    return results
