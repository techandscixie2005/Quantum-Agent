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
    potential: Literal["V0 inside [0,a]; zero outside"]
    energy: Literal["0<E<V0"]
    boundaries: Literal["constant mass; psi and derivative continuous; left incidence"]
    formula: Literal["exact flux T,R; not thick-barrier approximation"]


    @field_validator("approved_widths_m")
    @classmethod
    def supported_widths(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if any(value not in (1e-10, 1.5e-10) for value in values):
            raise ValueError("unsupported approved width")
        return values


def is_barrier_case(query: str) -> bool:
    # Include the durable scientific request kind used on continuation turns.
    return bool(re.search(
        r"势垒|隧穿|barrier|tunnell?ing|tunneling", query, re.IGNORECASE,
    ))


def has_subbarrier_scope(query: str) -> bool:
    """Ambiguous or other energy regimes cannot consume this narrow review."""
    compact = re.sub(r"\s+", "", query).casefold().replace("₀", "0")
    return "0<e<v0" in compact and not re.search(r"e(?:>=|>|=)v0", compact)


class BarrierTask(BaseModel):
    """Only the explicitly supported original and transfer tasks."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["rectangular_barrier_tunnelling"]
    energy_eV: float = Field(ge=5.0, le=5.0)
    barrier_height_eV: float = Field(ge=10.0, le=10.0)
    barrier_width_m: float
    conservation_tolerance: float = Field(default=1e-9, gt=0, le=1e-2)
    particle_mass_kg: float = Field(ge=9.1093837015e-31, le=9.1093837015e-31)


    @model_validator(mode="after")
    def supported_width(self) -> BarrierTask:
        if not any(math.isclose(self.barrier_width_m, value, rel_tol=1e-12, abs_tol=0)
                   for value in (1e-10, 1.5e-10)):
            raise ValueError("unsupported task width")
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
        return any(math.isclose(task.barrier_width_m, width, rel_tol=1e-12, abs_tol=0)
                   for width in review.approved_widths_m)
    except ValueError:
        return False


class ReviewManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    test_double: bool
    reviews: tuple[BarrierSourceReview, ...]


def load_reviews(path: Path, digest: str, *, allow_test_double: bool = False
                 ) -> tuple[BarrierSourceReview, ...]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("review manifest hash mismatch")
    manifest = ReviewManifest.model_validate(json.loads(raw))
    if manifest.test_double and not allow_test_double:
        raise ValueError("test double cannot be loaded in production")
    if any("TEST DOUBLE" in item.review_reference for item in manifest.reviews
           ) and not allow_test_double:
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
