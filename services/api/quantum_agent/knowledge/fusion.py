"""Deterministic rank fusion shared by retrieval repositories and tests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from quantum_agent.knowledge.evidence_packets import RetrievalChannel


@dataclass(frozen=True, slots=True)
class RankedChunk:
    chunk_id: UUID
    raw_score: float | None = None


@dataclass(frozen=True, slots=True)
class ChannelContribution:
    channel: RetrievalChannel
    rank: int
    raw_score: float | None
    weighted_rrf: float


@dataclass(frozen=True, slots=True)
class FusedChunk:
    chunk_id: UUID
    score: float
    authority_priority: int
    contributions: tuple[ChannelContribution, ...]


DEFAULT_WEIGHTS: Mapping[RetrievalChannel, float] = {
    RetrievalChannel.FULL_TEXT: 1.0,
    RetrievalChannel.SEMANTIC: 1.0,
    RetrievalChannel.GRAPH: 1.1,
}


def reciprocal_rank_fusion(
    rankings: Mapping[RetrievalChannel, Sequence[RankedChunk]],
    *,
    authority_priorities: Mapping[UUID, int] | None = None,
    weights: Mapping[RetrievalChannel, float] = DEFAULT_WEIGHTS,
    rrf_k: int = 60,
    limit: int = 6,
) -> list[FusedChunk]:
    """Fuse channels without normalizing incomparable provider scores.

    Course priority is a small deterministic tie-break contribution, capped so
    it cannot make an irrelevant source appear without a retrieval hit.
    """

    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if limit < 1:
        return []

    priorities = authority_priorities or {}
    scores: defaultdict[UUID, float] = defaultdict(float)
    details: defaultdict[UUID, list[ChannelContribution]] = defaultdict(list)
    for channel in sorted(rankings, key=lambda value: value.value):
        weight = weights.get(channel, 1.0)
        seen: set[UUID] = set()
        for rank, hit in enumerate(rankings[channel], start=1):
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            contribution = weight / (rrf_k + rank)
            scores[hit.chunk_id] += contribution
            details[hit.chunk_id].append(
                ChannelContribution(
                    channel=channel,
                    rank=rank,
                    raw_score=hit.raw_score,
                    weighted_rrf=contribution,
                )
            )

    fused = [
        FusedChunk(
            chunk_id=chunk_id,
            score=score + min(max(priorities.get(chunk_id, 0), 0), 100) * 1e-7,
            authority_priority=priorities.get(chunk_id, 0),
            contributions=tuple(sorted(details[chunk_id], key=lambda item: item.channel.value)),
        )
        for chunk_id, score in scores.items()
    ]
    return sorted(
        fused,
        key=lambda item: (-item.score, -item.authority_priority, str(item.chunk_id)),
    )[:limit]
