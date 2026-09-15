"""Offline counterexamples; all source approvals and gateways are test doubles."""
from __future__ import annotations

import json
import logging
from typing import cast
from uuid import uuid4

import pytest

from quantum_agent.coding.agent import CodingAgent
from quantum_agent.coding.models import CodeVerificationStatus
from quantum_agent.coding.sandbox import SubprocessSandbox
from quantum_agent.knowledge.barrier_scope import BarrierSourceReview
from quantum_agent.knowledge.evidence_packets import EvidencePacket, RetrievalCoverage
from quantum_agent.knowledge.retrieval import (
    HybridEvidenceRetriever,
    HybridRetrievalConfig,
    RetrievalScope,
)
from quantum_agent.llm.gateway import FakeModelGateway, _retry_transient
from quantum_agent.llm.observability import event, failure_category, traced_call, turn_scope
from tests.test_coding_agent import _tunnelling_artifact, _tunnelling_task
from tests.test_retrieval import (
    CHUNK_ONE,
    COURSE,
    EDITION,
    EVIDENCE_ONE,
    StaticRepository,
    record,
)


async def barrier_packet(text: str, *, reviewed: bool = False, changed: bool = False,
                         query: str = "finite rectangular barrier 0<E<V0") -> EvidencePacket:
    source = record(CHUNK_ONE, EVIDENCE_ONE, text, text)
    reviews: tuple[BarrierSourceReview, ...] = ()
    if reviewed:
        reviews = (BarrierSourceReview(
            **{key: getattr(source, key) for key in (
                "course_id", "curriculum_edition_id", "document_version_id", "evidence_id",
                "source_file_sha256", "source_chunk_sha256", "evidence_sha256",
            )},
            review_reference="TEST DOUBLE ONLY: no teacher approval",
            potential="V0 inside [0,a]; zero outside", energy="0<E<V0",
            boundaries="constant mass; psi and derivative continuous; left incidence",
            formula="exact flux T,R; not thick-barrier approximation",
        ),)
    if changed:
        source = source.model_copy(update={"document_version_id": uuid4()})
    repository = StaticRepository()
    repository.records = {CHUNK_ONE: (source,)}
    return await HybridEvidenceRetriever(
        repository=repository, embedding_gateway=None, graph_store=None,
        config=HybridRetrievalConfig(barrier_source_reviews=reviews),
    ).retrieve(RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION), query)


@pytest.mark.parametrize("text", [
    "For the semi-infinite barrier x>0, E<V0: R=1; T=0.",
    "Harmonic oscillator tunnelling wave function.",
    "Radial resonance barrier transmission.",
    "Finite rectangular barrier T formula without boundary conditions.",
])
async def test_unreviewed_comparison_is_not_direct_formula_evidence(text: str) -> None:
    packet = await barrier_packet(text)
    assert packet.coverage is RetrievalCoverage.NOT_FOUND
    assert not packet.evidence
    assert "source_insufficient:barrier_applicability_review_missing" in packet.warnings


async def test_review_binding_preserves_exact_text_and_rejects_new_version() -> None:
    text = "TEST FIXTURE: finite rectangular barrier, V0 inside [0,a], zero outside."
    packet = await barrier_packet(text, reviewed=True)
    assert packet.evidence[0].evidence_snippet == text
    assert not (await barrier_packet(text, reviewed=True, changed=True)).evidence
    assert not (await barrier_packet(text, reviewed=True, query="barrier E>V0")).evidence


async def test_conflicting_prose_does_not_become_verified_metrics() -> None:
    artifact = _tunnelling_artifact().model_copy(update={
        "code": _tunnelling_artifact().code + "\n# r=1-t (incorrect amplitude claim)\n",
        "expected_outputs": ["T=2.55e-9"], "verification_plan": "T=2.55e-9",
    })
    run = await CodingAgent(sandbox=SubprocessSandbox()).solve(
        _tunnelling_task(), gateway=FakeModelGateway({
            "generate_coding_artifact": artifact.model_dump(mode="json"),
        }),
    )
    assert run.verification.status is CodeVerificationStatus.PASS
    assert float(run.verification.agent_metrics["T"]) == pytest.approx(0.3336822872167467)
    assert "prose_and_code_unverified" in run.verification.certification_scope
    # Keep raw artifacts for audit; the presentation test verifies blocking.
    assert run.artifact.expected_outputs == ["T=2.55e-9"]


async def test_thick_barrier_approximation_does_not_pass_exact_scoring() -> None:
    artifact = _tunnelling_artifact()
    code = artifact.code.replace("sinh_sq = math.sinh(kappa * a) ** 2",
                                 "sinh_sq = math.exp(2 * kappa * a) / 4")
    run = await CodingAgent(sandbox=SubprocessSandbox(), max_repairs=0).solve(
        _tunnelling_task(), gateway=FakeModelGateway({
            "generate_coding_artifact": artifact.model_copy(update={"code": code}).model_dump(),
        }),
    )
    assert run.verification.status is CodeVerificationStatus.FAIL


async def test_retry_correlation_and_no_exception_content(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="quantum_agent.capability_events")
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("SECRET_MUST_NOT_APPEAR")
        return "ok"

    @traced_call
    async def capability(*, task: str) -> str:
        return cast(str, await _retry_transient(operation, max_attempts=2, base_delay=0,
                                                max_delay=0, label=task))

    session_id, turn_id = uuid4(), uuid4()
    with turn_scope(session_id, turn_id):
        assert await capability(task="test_capability") == "ok"
        event("draft", "citation_contract")
        event("draft", "source_insufficient")
        event("diagnosis", "expected_skip:no_student_attempt")
    rows = [json.loads(item.message) for item in caplog.records
            if item.name == "quantum_agent.capability_events"]
    assert all(row["session_id"] == str(session_id) for row in rows)
    assert all(row["turn_id"] == str(turn_id) for row in rows)
    assert len({row["run_id"] for row in rows}) == 1
    calls = [row for row in rows if row["capability"] == "test_capability"]
    assert len({row["call_id"] for row in calls}) == 1
    assert {row["attempt"] for row in calls} == {0, 1, 2}
    assert "SECRET_MUST_NOT_APPEAR" not in caplog.text
    assert failure_category(ValueError("private")) == "parse"
    assert failure_category(RuntimeError("private")) == "upstream_failure"


async def test_sdk_parse_retries_have_individual_request_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import httpx2
    from pydantic import SecretStr

    from quantum_agent.llm.gateway import Message, PydanticAIModelGateway
    from tests.test_llm_gateway import StructuredProbe, _chat_response

    caplog.set_level(logging.INFO, logger="quantum_agent.capability_events")
    count = 0

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(200, json=_chat_response(
            'not-json' if count == 1 else '{"value": 7}',
        ))

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        gateway = PydanticAIModelGateway(
            api_key=SecretStr("PRIVATE_TEST_CREDENTIAL"), model_http_client=client,
            max_retries=1,
        )
        with turn_scope(uuid4(), uuid4()):
            result = await gateway.structured_generate(
                task="test_sdk_retry", messages=[Message(role="user", content="PRIVATE_PROMPT")],
                output_type=StructuredProbe,
            )
    assert result.value == 7
    assert count == 2
    rows = [json.loads(row.message) for row in caplog.records
            if row.name == "quantum_agent.capability_events"]
    requests = [row for row in rows if row["reason"] == "request_started"]
    assert len({row["request_id"] for row in requests}) == 2
    assert len({row["call_id"] for row in requests}) == 1
    assert len({row["turn_id"] for row in requests}) == 1
    assert "PRIVATE_TEST_CREDENTIAL" not in caplog.text
    assert "PRIVATE_PROMPT" not in caplog.text
