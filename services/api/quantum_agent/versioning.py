"""Content-free build and model provenance attached to durable teaching turns."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from quantum_agent.knowledge.evidence_packets import EvidencePacket
from quantum_agent.teaching.models import TeachingTurnResult

_CALLS: ContextVar[list[dict[str, str]] | None] = ContextVar("versioned_model_calls", default=None)


@contextmanager
def version_scope() -> Iterator[None]:
    token = _CALLS.set([])
    try:
        yield
    finally:
        _CALLS.reset(token)


def record_model_call(*, model: str, task: str, profile: str, outcome: str) -> None:
    """Accept server-owned route identifiers only; never accept prompt/credential text."""
    calls = _CALLS.get()
    if calls is not None and len(calls) < 128:
        calls.append(
            {
                "model": model[:160],
                "task": task[:160],
                "profile": profile[:160],
                "outcome": outcome[:40],
            }
        )


def current_model_calls() -> list[dict[str, str]]:
    return [dict(call) for call in (_CALLS.get() or [])]


def build_turn_provenance(result: TeachingTurnResult) -> dict[str, Any]:
    native = result.learning_native.model_dump(mode="json") if result.learning_native else {}
    return build_evidence_provenance(
        packet=result.evidence_packet, workflow_version=result.workflow_version,
        course_package=native.get("course_package"),
    )


def build_evidence_provenance(
    *, packet: EvidencePacket, workflow_version: str,
    course_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture provenance for a paused or rejected turn as well as a final answer."""
    revision = os.environ.get("BUILD_REVISION", "unknown")
    # A deployment injects the full source revision. Never infer an image revision
    # from the Git checkout of a running server (which may be a different tree).
    if re.fullmatch(r"[0-9a-f]{40,64}", revision) is None:
        revision = "unknown"
    return {
        "schema_version": "teaching-provenance/1",
        "code_revision": revision,
        "workflow_version": workflow_version,
        "course_package": course_package,
        "model_calls": current_model_calls(),
        "model_identity_semantics": "provider model aliases; provider weights may change",
        "content": [
            {
                "evidence_id": str(item.evidence_id),
                "document_version_id": str(item.document_version_id),
                "document_version": item.document_version,
                "source_file_sha256": item.source_file_sha256,
                "source_chunk_sha256": item.source_chunk_sha256,
                "evidence_sha256": item.evidence_sha256,
            }
            for item in packet.evidence
        ],
    }
