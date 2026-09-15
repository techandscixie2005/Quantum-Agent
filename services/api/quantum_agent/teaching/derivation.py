"""Source-linked derivation scaffolds, bounded by deterministic release policy.

Generated algebra remains explicitly model inference. A valid source pointer
does not establish that a generated step is a teacher-approved course assertion.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from quantum_agent.db_models import AnswerReleaseLevel
from quantum_agent.knowledge.evidence_packets import EvidencePacket


class BridgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    quote: str = Field(min_length=1, max_length=2000)


class DerivationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula: str = Field(min_length=1, max_length=2000)
    justification: str = Field(min_length=1, max_length=1000)
    source_refs: list[BridgeSource] = Field(min_length=1, max_length=6)


BridgeLabel = Annotated[str, Field(min_length=1, max_length=2000)]


class DerivationBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_step: str = Field(min_length=1, max_length=2000)
    target_step: str = Field(min_length=1, max_length=2000)
    missing_steps: list[DerivationStep] = Field(min_length=1, max_length=8)
    used_definitions: list[BridgeLabel] = Field(default_factory=list, max_length=8)
    assumptions: list[BridgeLabel] = Field(default_factory=list, max_length=8)
    prerequisites: list[BridgeLabel] = Field(default_factory=list, max_length=8)
    validity_conditions: list[BridgeLabel] = Field(default_factory=list, max_length=8)
    source_refs: list[BridgeSource] = Field(min_length=1, max_length=6)
    support_basis: Literal["unverified_model_inference"] = "unverified_model_inference"
    # This is set by policy, never trusted from generation.
    partial: bool = True


def constrain_bridge(
    bridge: DerivationBridge | None,
    packet: EvidencePacket,
    release: AnswerReleaseLevel,
) -> DerivationBridge | None:
    if bridge is None or release in {AnswerReleaseLevel.QUESTION_ONLY, AnswerReleaseLevel.HINT}:
        return None
    evidence = {item.evidence_id: item.evidence_snippet for item in packet.evidence}
    def align(ref: BridgeSource) -> BridgeSource:
        source = evidence.get(ref.evidence_id, "")
        positions = [i for i, char in enumerate(source) if not char.isspace()]
        needle = "".join(ref.quote.split())
        start = "".join(source[i] for i in positions).find(needle)
        if not needle or start < 0:
            raise ValueError("derivation bridge requires exact published source spans")
        return BridgeSource(
            evidence_id=ref.evidence_id,
            quote=source[positions[start]:positions[start + len(needle) - 1] + 1],
        )

    references = [align(ref) for ref in bridge.source_refs]
    steps = [step.model_copy(update={"source_refs": [align(r) for r in step.source_refs]})
             for step in bridge.missing_steps]
    partial = release is AnswerReleaseLevel.SCAFFOLD
    return bridge.model_copy(update={
        "source_refs": references,
        "missing_steps": steps[:1] if partial else steps,
        "partial": partial,
    })
