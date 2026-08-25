"""Typed, untrusted multimodal evidence and attachment processing.

Student uploads intentionally live outside the teacher-published course-knowledge
tables.  Perception output can inform a teaching turn, but never becomes course
evidence without the existing review and publication workflow.
"""

from quantum_agent.multimodal.contracts import (
    Ambiguity,
    AmbiguityCandidate,
    BoundingBox,
    DerivationStep,
    DocumentEvidence,
    VisualEvidence,
)

__all__ = [
    "Ambiguity",
    "AmbiguityCandidate",
    "BoundingBox",
    "DerivationStep",
    "DocumentEvidence",
    "VisualEvidence",
]
