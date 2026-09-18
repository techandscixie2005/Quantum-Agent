"""Fail-closed applicability gate for the finite rectangular barrier case.

This registry is separate from publication: publishing a source does not confirm
its applicability or an erratum. No production reviews are supplied by default.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BarrierSourceReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: UUID
    curriculum_edition_id: UUID
    document_version_id: UUID
    evidence_id: UUID
    source_file_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_chunk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_reference: str = Field(min_length=1)
    approved_widths_m: tuple[float, ...] = Field(min_length=1)
    energy_range_eV: tuple[float, float] = (5.0, 5.0)
    height_range_eV: tuple[float, float] = (10.0, 10.0)
    width_range_m: tuple[float, float] | None = None
    potential: Literal["V0 inside [0,a]; zero outside"]
    energy: Literal["0<E<V0"]
    boundaries: Literal["constant mass; psi and derivative continuous; left incidence"]
    formula: Literal["exact flux T,R; not thick-barrier approximation"]

    @field_validator("approved_widths_m")
    @classmethod
    def supported_widths(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("approved widths must be finite and positive")
        return values

    @field_validator("energy_range_eV", "height_range_eV", "width_range_m")
    @classmethod
    def ordered_range(cls, values: tuple[float, float] | None) -> tuple[float, float] | None:
        if values is not None and (
            not all(math.isfinite(value) and value > 0 for value in values) or values[0] > values[1]
        ):
            raise ValueError("review ranges must be finite, positive and ordered")
        return values


def is_barrier_case(query: str) -> bool:
    # Include the durable scientific request kind used on continuation turns.
    return bool(
        re.search(
            r"势垒|隧穿|barrier|tunnell?ing|tunneling",
            query,
            re.IGNORECASE,
        )
    )


def has_subbarrier_scope(query: str) -> bool:
    """Ambiguous or other energy regimes cannot consume this narrow review."""
    compact = re.sub(r"\s+", "", query).casefold().replace("₀", "0")
    return "0<e<v0" in compact and not re.search(r"e(?:>=|>|=)v0", compact)


class BarrierTask(BaseModel):
    """Electron subbarrier contract; applicability comes from the pinned review."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["rectangular_barrier_tunnelling"]
    energy_eV: float = Field(gt=0, allow_inf_nan=False)
    barrier_height_eV: float = Field(gt=0, allow_inf_nan=False)
    barrier_width_m: float = Field(gt=0, allow_inf_nan=False)
    conservation_tolerance: float = Field(default=1e-9, gt=0, le=1e-2)
    particle_mass_kg: float = Field(ge=9.1093837015e-31, le=9.1093837015e-31)

    @model_validator(mode="after")
    def supported_width(self) -> BarrierTask:
        if self.energy_eV >= self.barrier_height_eV:
            raise ValueError("review requires 0<E<V0")
        return self


_TASK: ContextVar[dict[str, Any] | None] = ContextVar("barrier_task", default=None)


@contextmanager
def source_task(task: dict[str, Any] | None) -> Iterator[None]:
    token = _TASK.set(task)
    try:
        yield
    finally:
        _TASK.reset(token)


def task_is_barrier() -> bool:
    return (_TASK.get() or {}).get("kind") == "rectangular_barrier_tunnelling"


def task_matches(review: BarrierSourceReview) -> bool:
    try:
        task = BarrierTask.model_validate(_TASK.get())
        width_matches = any(
            math.isclose(task.barrier_width_m, width, rel_tol=1e-12, abs_tol=0)
            for width in review.approved_widths_m
        ) or (
            review.width_range_m is not None
            and review.width_range_m[0] <= task.barrier_width_m <= review.width_range_m[1]
        )
        return (
            width_matches
            and review.energy_range_eV[0] <= task.energy_eV <= review.energy_range_eV[1]
            and review.height_range_eV[0] <= task.barrier_height_eV <= review.height_range_eV[1]
        )
    except ValueError:
        return False


class ReviewManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    test_double: bool
    reviews: tuple[BarrierSourceReview, ...]


def load_reviews(
    path: Path, digest: str, *, allow_test_double: bool = False
) -> tuple[BarrierSourceReview, ...]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("review manifest hash mismatch")
    manifest = ReviewManifest.model_validate(json.loads(raw))
    if manifest.test_double and not allow_test_double:
        raise ValueError("test double cannot be loaded in production")
    if (
        any("TEST DOUBLE" in item.review_reference for item in manifest.reviews)
        and not allow_test_double
    ):
        raise ValueError("test review cannot be loaded in production")
    return manifest.reviews


def configured_reviews() -> tuple[BarrierSourceReview, ...]:
    path = os.environ.get("QUANTUM_AGENT_BARRIER_REVIEWS")
    digest = os.environ.get("QUANTUM_AGENT_BARRIER_REVIEWS_SHA256")
    if not path and not digest:
        return ()
    if not path or not digest:
        raise ValueError("both review path and pinned hash are required")
    return load_reviews(Path(path), digest)
