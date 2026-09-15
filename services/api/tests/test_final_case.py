"""Offline only: local ledger, mock HTTP, and explicitly labelled review substitutes."""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from pydantic import SecretStr

from quantum_agent.knowledge.barrier_scope import (
    BarrierTask,
    ReviewManifest,
    load_reviews,
    source_task,
    task_is_barrier,
)
from quantum_agent.llm.gateway import GatewayError, Message, PydanticAIModelGateway
from quantum_agent.llm.observability import turn_scope
from quantum_agent.llm.recording_budget import RecordingBudget, RecordingBudgetError
from tests.test_llm_gateway import StructuredProbe, _chat_response


def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, requests: int = 2,
           seconds: float = 30) -> RecordingBudget:
    run = str(uuid4())
    path = tmp_path / 'ledger.sqlite'
    budget = RecordingBudget.provision(path, run, requests=requests, seconds=seconds,
                                       output_tokens=100, request_bytes=65536)
    monkeypatch.setenv('QUANTUM_AGENT_RECORDING_RUN_ID', run)
    monkeypatch.setenv('QUANTUM_AGENT_RECORDING_LEDGER', str(path))
    return budget


async def test_cross_turn_failed_requests_and_restart_never_refill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = ledger(tmp_path, monkeypatch)
    sent = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(500, json={'error': {'message': 'mock failure'}})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        gateway = PydanticAIModelGateway(api_key=SecretStr('TEST'), model_http_client=client)
        for _ in range(2):
            with turn_scope(uuid4(), uuid4()), pytest.raises(GatewayError):
                await gateway.structured_generate(task='interpret_teaching_turn',
                                                  messages=[Message(role='user',
                                                  content='test')], output_type=StructuredProbe)
        with pytest.raises(RecordingBudgetError):
            await gateway.structured_generate(task='interpret_teaching_turn',
                                                  messages=[Message(role='user',
                                              content='test')], output_type=StructuredProbe)
    assert len(sent) == 2  # SDK and transport retries disabled, failures consume slots.
    assert all(p.get('max_completion_tokens', p.get('max_tokens')) == 100 for p in sent)
    restarted = RecordingBudget(budget.path, budget.run_id)
    with pytest.raises(RecordingBudgetError):
        restarted.reserve(b'{"max_tokens":100}')
    with pytest.raises(FileExistsError):
        RecordingBudget.provision(budget.path, budget.run_id, requests=2, seconds=30,
                                  output_tokens=100, request_bytes=1000)


async def test_deadline_cancels_inflight_and_blocks_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger(tmp_path, monkeypatch, seconds=0.2)
    cancelled = asyncio.Event()
    sent = 0

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal sent
        sent += 1
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
        return httpx2.Response(200, json=_chat_response('{"value":7}'))

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        gateway = PydanticAIModelGateway(api_key=SecretStr('TEST'), model_http_client=client)
        for _ in range(2):
            with pytest.raises(RecordingBudgetError):
                await gateway.structured_generate(task='interpret_teaching_turn',
                                                  messages=[Message(role='user',
                                                  content='test')], output_type=StructuredProbe)
    assert cancelled.is_set()
    assert sent == 1


def test_manifest_hash_version_and_production_test_double_rejection(tmp_path: Path) -> None:
    path = tmp_path / 'reviews.json'
    manifest = ReviewManifest(schema_version=1, test_double=True, reviews=())
    path.write_text(manifest.model_dump_json())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_reviews(path, digest, allow_test_double=True) == ()
    with pytest.raises(ValueError, match='test double'):
        load_reviews(path, digest)
    with pytest.raises(ValueError, match='hash mismatch'):
        load_reviews(path, '0' * 64)
    path.write_text('{"schema_version":2,"test_double":false,"reviews":[]}')
    with pytest.raises(ValueError):
        load_reviews(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_structured_scope_original_transfer_and_topic_switch() -> None:
    original = dict(kind='rectangular_barrier_tunnelling', energy_eV=5.0,
                    barrier_height_eV=10.0, barrier_width_m=1e-10,
                    particle_mass_kg=9.1093837015e-31)
    for width in (1e-10, 1.5e-10, 1e-10 * 1.5):
        assert BarrierTask.model_validate({**original, 'barrier_width_m': width})
    for change in ({'energy_eV': 12}, {'barrier_width_m': 2e-10},
                   {'particle_mass_kg': 1e-30}, {'potential': 'semi-infinite'}):
        with pytest.raises(ValueError):
            BarrierTask.model_validate({**original, **change})
    with source_task(original):
        assert task_is_barrier()
        with source_task(None):
            assert not task_is_barrier()
        assert task_is_barrier()
    assert not task_is_barrier()


async def test_budget_failure_never_enters_route_fallback() -> None:
    from tests.test_model_routing import StrictOutput, _router_with_outcomes

    router, constructed, _ = _router_with_outcomes({
        "reasoning_primary": RecordingBudgetError("stop"),
        "reasoning_second_pass": {"value": 7},
    })
    with pytest.raises(RecordingBudgetError):
        await router.structured_generate(task="diagnose_student_progress",
                                        messages=[Message(role="user", content="test")],
                                        output_type=StrictOutput)
    assert constructed == ["reasoning_primary"]


def test_corrupt_missing_and_wrong_run_ledgers_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "absent.sqlite"
    with pytest.raises(RecordingBudgetError):
        RecordingBudget(path, "missing").limits()
    assert not path.exists()
    budget = RecordingBudget.provision(path, "one", requests=1, seconds=10,
                                       output_tokens=100, request_bytes=100)
    for body in (b'{"max_tokens":101}', b'{"messages":[]}'):
        with pytest.raises(RecordingBudgetError):
            budget.reserve(body)
    with pytest.raises(RecordingBudgetError):
        RecordingBudget(path, "two").reserve(b'{"max_tokens":100}')
    budget.reserve(b'{"max_tokens":100}')
    with pytest.raises(RecordingBudgetError):
        budget.reserve(b'{"max_tokens":100}')


async def test_same_retriever_switches_topics_without_bypassing_barrier_gate(
    tmp_path: Path,
) -> None:
    from quantum_agent.knowledge.barrier_scope import BarrierSourceReview, configured_reviews
    from quantum_agent.knowledge.retrieval import (
        HybridEvidenceRetriever,
        HybridRetrievalConfig,
        RetrievalScope,
    )
    from tests.test_retrieval import (
        CHUNK_ONE,
        COURSE,
        EDITION,
        EVIDENCE_ONE,
        StaticRepository,
        record,
    )

    text = 'TEST DOUBLE finite rectangular barrier wave function statistical interpretation.'
    evidence = record(CHUNK_ONE, EVIDENCE_ONE, text, text)
    review = BarrierSourceReview(
        **{key: getattr(evidence, key) for key in (
            'course_id', 'curriculum_edition_id', 'document_version_id', 'evidence_id',
            'source_file_sha256', 'source_chunk_sha256', 'evidence_sha256',
        )},
        review_reference='TEST DOUBLE ONLY', approved_widths_m=(1e-10, 1.5e-10),
        potential='V0 inside [0,a]; zero outside', energy='0<E<V0',
        boundaries='constant mass; psi and derivative continuous; left incidence',
        formula='exact flux T,R; not thick-barrier approximation',
    )
    path = tmp_path / 'test-review.json'
    path.write_text(ReviewManifest(schema_version=1, test_double=True,
                                   reviews=(review,)).model_dump_json())
    loaded = load_reviews(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                          allow_test_double=True)
    assert configured_reviews() == ()
    repository = StaticRepository()
    repository.records = {CHUNK_ONE: (evidence,)}
    retriever = HybridEvidenceRetriever(repository=repository, embedding_gateway=None,
                                       graph_store=None,
                                       config=HybridRetrievalConfig(barrier_source_reviews=loaded))
    scope = RetrievalScope(course_id=COURSE, curriculum_edition_id=EDITION)
    original = dict(kind='rectangular_barrier_tunnelling', energy_eV=5.0,
                    barrier_height_eV=10.0, barrier_width_m=1e-10,
                    particle_mass_kg=9.1093837015e-31)
    for width in (1e-10, 1e-10 * 1.5):
        with source_task({**original, 'barrier_width_m': width}):
            packet = await retriever.retrieve(scope, 'finite rectangular barrier 0<E<V0')
            assert packet.evidence[0].evidence_snippet == text
    with source_task({**original, 'energy_eV': 12}):
        assert not (await retriever.retrieve(scope, 'wave function')).evidence
    with source_task(None):
        assert (await retriever.retrieve(scope, 'wave function')).evidence
        assert not (await retriever.retrieve(scope, 'finite barrier 0<E<V0')).evidence
