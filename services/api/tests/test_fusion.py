from __future__ import annotations

from uuid import UUID

from quantum_agent.knowledge.evidence_packets import RetrievalChannel
from quantum_agent.knowledge.fusion import RankedChunk, reciprocal_rank_fusion

ONE = UUID("00000000-0000-0000-0000-000000000001")
TWO = UUID("00000000-0000-0000-0000-000000000002")
THREE = UUID("00000000-0000-0000-0000-000000000003")


def test_rrf_rewards_cross_channel_support() -> None:
    fused = reciprocal_rank_fusion(
        {
            RetrievalChannel.FULL_TEXT: [RankedChunk(ONE, 0.8), RankedChunk(TWO, 0.7)],
            RetrievalChannel.SEMANTIC: [RankedChunk(TWO, 0.95), RankedChunk(THREE, 0.9)],
            RetrievalChannel.GRAPH: [RankedChunk(TWO, None)],
        }
    )
    assert fused[0].chunk_id == TWO
    assert {item.channel for item in fused[0].contributions} == {
        RetrievalChannel.FULL_TEXT,
        RetrievalChannel.SEMANTIC,
        RetrievalChannel.GRAPH,
    }


def test_rrf_deduplicates_a_chunk_inside_each_channel() -> None:
    fused = reciprocal_rank_fusion(
        {RetrievalChannel.FULL_TEXT: [RankedChunk(ONE), RankedChunk(ONE)]}
    )
    assert len(fused) == 1
    assert len(fused[0].contributions) == 1


def test_authority_is_only_a_tie_breaker_not_a_recall_channel() -> None:
    fused = reciprocal_rank_fusion(
        {RetrievalChannel.FULL_TEXT: [RankedChunk(ONE), RankedChunk(TWO)]},
        authority_priorities={ONE: 50, TWO: 100, THREE: 100},
    )
    assert {item.chunk_id for item in fused} == {ONE, TWO}
    assert THREE not in {item.chunk_id for item in fused}
