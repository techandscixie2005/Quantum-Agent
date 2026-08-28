from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import TypeVar, cast

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from quantum_agent.config import Settings
from quantum_agent.gateways import (
    build_model_capability_registry,
    build_model_gateway,
    build_model_router,
)
from quantum_agent.llm.gateway import (
    GatewayCapabilities,
    GatewayError,
    Message,
    ModelGateway,
    ModelTier,
    PermanentGatewayError,
)
from quantum_agent.llm.routing import (
    ModelCapability,
    ModelCapabilityRegistry,
    ModelProfile,
    ModelRouter,
    ModelTask,
    ModelTransport,
)

T = TypeVar("T")


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: int


class StubGateway:
    def __init__(self, outcome: object | Exception) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, ModelTier]] = []

    async def structured_generate(
        self,
        *,
        task: str,
        messages: Sequence[Message],
        output_type: type[T],
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> T:
        del messages, output_type
        self.calls.append((task, model_tier))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return cast(T, self.outcome)

    async def probe(self) -> GatewayCapabilities:
        return GatewayCapabilities(chat_completions=True, prompted_json=True)


def _router_with_outcomes(
    outcomes: dict[str, object | Exception],
    *,
    cooldown_seconds: float = 30.0,
    max_cooldown_seconds: float = 300.0,
    clock: Callable[[], float] | None = None,
) -> tuple[ModelRouter, list[str], dict[str, StubGateway]]:
    registry = ModelCapabilityRegistry.ustc_default()
    constructed: list[str] = []
    gateways: dict[str, StubGateway] = {}

    def factory(profile: ModelProfile) -> ModelGateway:
        constructed.append(profile.profile_id)
        gateway = StubGateway(
            outcomes.get(profile.profile_id, GatewayError("route unavailable"))
        )
        gateways[profile.profile_id] = gateway
        return gateway

    if clock is None:
        router = ModelRouter(
            registry=registry,
            gateway_factory=factory,
            cooldown_seconds=cooldown_seconds,
            max_cooldown_seconds=max_cooldown_seconds,
        )
    else:
        router = ModelRouter(
            registry=registry,
            gateway_factory=factory,
            cooldown_seconds=cooldown_seconds,
            max_cooldown_seconds=max_cooldown_seconds,
            clock=clock,
        )
    return router, constructed, gateways


def test_registry_has_capability_checked_routes_for_every_required_task() -> None:
    registry = ModelCapabilityRegistry.ustc_default()

    diagnosis = registry.profiles_for(ModelTask.DIAGNOSIS)
    lightweight = registry.profiles_for(ModelTask.LIGHTWEIGHT)
    vision = registry.profiles_for(ModelTask.VISION)
    embedding = registry.profiles_for(ModelTask.EMBEDDING)
    rerank = registry.profiles_for(ModelTask.RERANK)
    document = registry.profiles_for(ModelTask.DOCUMENT_PARSING)

    assert [profile.provider_model for profile in diagnosis] == [
        "deepseek-v4-pro",
        "qwen3.8-reasoner",
        "qwen-reasoner",
    ]
    assert [profile.provider_model for profile in lightweight] == [
        "deepseek-v4-flash-ascend1",
        "deepseek-v4-flash",
    ]
    assert [profile.provider_model for profile in vision] == ["qwen3.8-chat", "qwen-chat"]
    assert all(ModelCapability.VISION_INPUT in profile.capabilities for profile in vision)
    assert all("deepseek" not in profile.provider_model for profile in vision)
    assert embedding[0].provider_model == "qwen3-embedding"
    assert embedding[0].transport is ModelTransport.EMBEDDINGS
    assert rerank[0].provider_model == "qwen3-reranker"
    assert rerank[0].transport is ModelTransport.RERANK
    assert [profile.provider_model for profile in document] == ["mineru", "unlimited-ocr"]
    assert document[0].transport is ModelTransport.DOCUMENT_PARSER
    assert ModelCapability.OCR in document[1].capabilities


def test_operation_mapping_cannot_be_used_to_select_a_model_name() -> None:
    registry = ModelCapabilityRegistry.ustc_default()

    assert (
        registry.task_for_operation("interpret_teaching_turn", ModelTier.DEFAULT)
        is ModelTask.LIGHTWEIGHT
    )
    assert (
        registry.task_for_operation("diagnose_student_progress_structured", ModelTier.SMALL)
        is ModelTask.DIAGNOSIS
    )
    assert (
        registry.task_for_operation("deepseek-v4-pro", ModelTier.SMALL)
        is ModelTask.LIGHTWEIGHT
    )
    assert (
        registry.task_for_operation("qwen3.8-chat", ModelTier.DEFAULT)
        is ModelTask.REASONING
    )


def test_public_catalog_contains_no_provider_model_endpoint_or_secret() -> None:
    registry = ModelCapabilityRegistry.ustc_default()
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in registry.public_catalog()],
        sort_keys=True,
    )

    assert {item.id for item in registry.public_catalog()} == set(ModelTask)
    for forbidden in (
        "deepseek",
        "qwen",
        "glm",
        "mineru",
        "unlimited-ocr",
        "api.llm.ustc.edu.cn",
        "secret-token",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_diagnosis_router_uses_ordered_fallback_and_validates_output() -> None:
    router, constructed, gateways = _router_with_outcomes(
        {
            "reasoning_primary": GatewayError("primary unavailable"),
            "reasoning_second_pass": {"value": 7},
        }
    )

    output = await router.structured_generate(
        task="diagnose_student_progress_structured",
        messages=[Message(role="user", content="bounded attempt")],
        output_type=StrictOutput,
    )

    assert output == StrictOutput(value=7)
    assert constructed == ["reasoning_primary", "reasoning_second_pass"]
    assert gateways["reasoning_primary"].calls == [
        ("diagnose_student_progress_structured", ModelTier.DEFAULT)
    ]


@pytest.mark.asyncio
async def test_router_skips_recent_failure_and_keeps_using_healthy_fallback() -> None:
    router, _, gateways = _router_with_outcomes(
        {
            "reasoning_primary": GatewayError("primary unavailable"),
            "reasoning_second_pass": {"value": 7},
        }
    )
    messages = [Message(role="user", content="student attempt")]

    first = await router.structured_generate(
        task="diagnose_student_progress",
        messages=messages,
        output_type=StrictOutput,
    )
    second = await router.structured_generate(
        task="diagnose_student_progress",
        messages=messages,
        output_type=StrictOutput,
    )

    assert first.value == second.value == 7
    assert len(gateways["reasoning_primary"].calls) == 1
    assert len(gateways["reasoning_second_pass"].calls) == 2


@pytest.mark.asyncio
async def test_router_retries_primary_after_cooldown_and_resets_health() -> None:
    now = [100.0]
    router, _, gateways = _router_with_outcomes(
        {
            "reasoning_primary": GatewayError("primary unavailable"),
            "reasoning_second_pass": {"value": 7},
        },
        cooldown_seconds=5.0,
        clock=lambda: now[0],
    )
    messages = [Message(role="user", content="student attempt")]

    await router.structured_generate(
        task="diagnose_student_progress",
        messages=messages,
        output_type=StrictOutput,
    )
    gateways["reasoning_primary"].outcome = {"value": 9}
    now[0] += 5.0

    recovered = await router.structured_generate(
        task="diagnose_student_progress",
        messages=messages,
        output_type=StrictOutput,
    )
    next_call = await router.structured_generate(
        task="diagnose_student_progress",
        messages=messages,
        output_type=StrictOutput,
    )

    assert recovered.value == next_call.value == 9
    assert len(gateways["reasoning_primary"].calls) == 3
    assert len(gateways["reasoning_second_pass"].calls) == 1


@pytest.mark.asyncio
async def test_router_does_not_retry_any_route_while_all_are_cooling_down() -> None:
    router, _, gateways = _router_with_outcomes({})
    messages = [Message(role="user", content="student attempt")]

    with pytest.raises(GatewayError):
        await router.structured_generate(
            task="diagnose_student_progress",
            messages=messages,
            output_type=StrictOutput,
        )
    call_counts = {profile_id: len(gateway.calls) for profile_id, gateway in gateways.items()}

    with pytest.raises(GatewayError) as caught:
        await router.structured_generate(
            task="diagnose_student_progress",
            messages=messages,
            output_type=StrictOutput,
        )

    retry_call_counts = {
        profile_id: len(gateway.calls) for profile_id, gateway in gateways.items()
    }
    assert retry_call_counts == call_counts
    assert "0 bounded attempt(s)" in str(caught.value)
    assert "3 route(s) temporarily cooling down" in str(caught.value)
    assert "deepseek" not in str(caught.value)
    assert "qwen" not in str(caught.value)


@pytest.mark.asyncio
async def test_router_rejects_invalid_structured_output_then_falls_back() -> None:
    router, constructed, _ = _router_with_outcomes(
        {
            "reasoning_primary": {"value": "7"},
            "reasoning_second_pass": {"value": 8},
        }
    )

    output = await router.structured_generate(
        task="diagnose_student_progress",
        messages=[Message(role="user", content="student attempt")],
        output_type=StrictOutput,
    )

    assert output.value == 8
    assert constructed == ["reasoning_primary", "reasoning_second_pass"]


@pytest.mark.asyncio
async def test_lightweight_operation_uses_only_low_latency_route() -> None:
    router, constructed, _ = _router_with_outcomes(
        {"lightweight_primary": {"value": 3}}
    )

    output = await router.structured_generate(
        task="interpret_teaching_turn",
        messages=[Message(role="user", content="classify only")],
        output_type=StrictOutput,
        model_tier=ModelTier.SMALL,
    )

    assert output.value == 3
    assert constructed == ["lightweight_primary"]


@pytest.mark.asyncio
async def test_exhausted_route_error_is_bounded_and_does_not_leak_model_names() -> None:
    router, constructed, _ = _router_with_outcomes({})

    with pytest.raises(GatewayError) as caught:
        await router.structured_generate(
            task="diagnose_student_progress",
            messages=[Message(role="user", content="student attempt")],
            output_type=StrictOutput,
        )

    assert constructed == [
        "reasoning_primary",
        "reasoning_second_pass",
        "reasoning_secondary",
    ]
    assert "diagnosis" in str(caught.value)
    assert "deepseek" not in str(caught.value)
    assert "qwen" not in str(caught.value)


def test_settings_build_server_only_override_routes_and_reject_blank_names() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USTC_API="secret-token",
        USTC_MODEL="reasoning-override",
        USTC_MODEL_QUICK="quick-override",
        USTC_VISION_MODEL="vision-override",
        USTC_MODEL_MINERU="mineru-override",
        USTC_MODEL_OCR="ocr-override",
    )
    registry = build_model_capability_registry(settings)

    assert registry.profiles_for(ModelTask.REASONING)[0].provider_model == "reasoning-override"
    assert registry.profiles_for(ModelTask.LIGHTWEIGHT)[0].provider_model == "quick-override"
    assert registry.profiles_for(ModelTask.VISION)[0].provider_model == "vision-override"
    assert [
        profile.provider_model for profile in registry.profiles_for(ModelTask.DOCUMENT_PARSING)
    ] == ["mineru-override", "ocr-override"]
    assert isinstance(build_model_router(settings), ModelRouter)
    assert isinstance(build_model_gateway(settings), ModelRouter)

    with pytest.raises(ValidationError, match="must not be blank"):
        Settings(
            _env_file=None,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            USTC_MODEL_QUICK="   ",
        )


def test_router_is_disabled_without_server_secret_but_registry_remains_available() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USTC_API=None,
    )

    assert build_model_router(settings) is None
    assert build_model_gateway(settings) is None
    assert build_model_capability_registry(settings).public_catalog()


async def test_router_fail_fast_on_permanent_error_does_not_try_next_profile() -> None:
    """PRD V3.1 P1-2: 401/403 must NOT be retried across router profiles.

    A credential/authorization error (401/403) on one profile is almost
    certainly permanent on every other profile (same upstream key), so the
    router short-circuits and surfaces the PermanentGatewayError instead of
    burning latency on the remaining profiles.  400 is NOT permanent: a bad
    request may be profile-specific, so the router still tries the next.
    """

    router, constructed, _ = _router_with_outcomes(
        {
            "reasoning_primary": PermanentGatewayError("HTTP 401"),
            "reasoning_second_pass": {"value": 7},
        }
    )

    with pytest.raises(PermanentGatewayError):
        await router.structured_generate(
            task="diagnose_student_progress",
            messages=[Message(role="user", content="student attempt")],
            output_type=StrictOutput,
        )

    # The router must NOT have attempted the second profile.
    assert constructed == ["reasoning_primary"]


async def test_router_fallback_budget_caps_total_cross_profile_latency() -> None:
    """PRD V3.1 P1-2: the cross-profile fallback budget caps total latency.

    When the budget is exhausted before the next profile attempt starts,
    the router surfaces the last error instead of starting a call that
    cannot complete under the proxy limit.
    """

    now = [0.0]

    def clock() -> float:
        return now[0]

    class _ClockAdvancingGateway:
        def __init__(self, outcome: object | Exception, *, advance: float) -> None:
            self._outcome = outcome
            self._advance = advance
            self.calls: list[tuple[str, ModelTier]] = []

        async def structured_generate(
            self,
            *,
            task: str,
            messages: Sequence[Message],
            output_type: type[T],
            model_tier: ModelTier = ModelTier.DEFAULT,
        ) -> T:
            del messages, output_type
            self.calls.append((task, model_tier))
            now[0] += self._advance
            if isinstance(self._outcome, Exception):
                raise self._outcome
            return cast(T, self._outcome)

        async def probe(self) -> GatewayCapabilities:
            return GatewayCapabilities(chat_completions=True, prompted_json=True)

    registry = ModelCapabilityRegistry.ustc_default()
    constructed: list[str] = []

    def factory(profile: ModelProfile) -> ModelGateway:
        constructed.append(profile.profile_id)
        if profile.profile_id == "reasoning_primary":
            outcome: object | Exception = GatewayError("primary unavailable")
        elif profile.profile_id == "reasoning_second_pass":
            outcome = {"value": 7}
        else:
            outcome = GatewayError("route unavailable")
        return _ClockAdvancingGateway(outcome, advance=1.0)  # type: ignore[return-value]

    router = ModelRouter(
        registry=registry,
        gateway_factory=factory,
        cooldown_seconds=0.1,
        max_cooldown_seconds=0.1,
        fallback_budget_seconds=0.5,
        clock=clock,
    )

    with pytest.raises(GatewayError):
        await router.structured_generate(
            task="diagnose_student_progress",
            messages=[Message(role="user", content="student attempt")],
            output_type=StrictOutput,
        )

    # Only the first profile was attempted; the budget was exhausted
    # before the second attempt started (the first call advanced the
    # clock from 0.0 to 1.0, crossing the 0.5s deadline).
    assert constructed == ["reasoning_primary"]
