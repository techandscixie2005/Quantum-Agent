"""Fail-closed applicability gate for the finite rectangular barrier case.

This registry is separate from publication: publishing a source does not confirm
its applicability or an erratum. No production reviews are supplied by default.
"""
from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    potential: Literal["V0 inside [0,a]; zero outside"]
    energy: Literal["0<E<V0"]
    boundaries: Literal["constant mass; psi and derivative continuous; left incidence"]
    formula: Literal["exact flux T,R; not thick-barrier approximation"]


def is_barrier_case(query: str) -> bool:
    # Include the durable scientific request kind used on continuation turns.
    return bool(re.search(
        r"势垒|隧穿|barrier|tunnell?ing|tunneling", query, re.IGNORECASE,
    ))


def has_subbarrier_scope(query: str) -> bool:
    """Ambiguous or other energy regimes cannot consume this narrow review."""
    compact = re.sub(r"\s+", "", query).casefold().replace("₀", "0")
    return "0<e<v0" in compact and not re.search(r"e(?:>=|>|=)v0", compact)
