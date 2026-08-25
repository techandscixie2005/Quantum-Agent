"""Server-only USTC model capability registry and deterministic task router.

Application code supplies a task name or capability ID. Concrete provider model
names remain in this module and in backend configuration; they are never part of
the student response contract.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from quantum_agent.llm.gateway import (
    GatewayCapabilities,
    GatewayError,
    Message,
    ModelGateway,
    ModelTier,
)

T = TypeVar("T")


class ModelCapability(StrEnum):
    TEXT_INPUT = "text_input"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"
    LOW_LATENCY = "low_latency"
    VISION_INPUT = "vision_input"
    LONG_CONTEXT = "long_context"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    DOCUMENT_PARSING = "document_parsing"
    OCR = "ocr"


class ModelTask(StrEnum):
    """Stable server capability IDs; safe to use without exposing a model name."""

    REASONING = "reasoning"
    DIAGNOSIS = "diagnosis"
    LIGHTWEIGHT = "lightweight"
    VISION = "vision"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    DOCUMENT_PARSING = "document_parsing"
    DOCUMENT_REASONING = "document_reasoning"


class ModelTransport(StrEnum):
    CHAT_COMPLETIONS = "chat_completions"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"
    DOCUMENT_PARSER = "document_parser"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """Internal provider binding; never serialize this in a student response."""

    profile_id: str
    provider_model: str
    transport: ModelTransport
    capabilities: frozenset[ModelCapability]

    def supports(self, required: frozenset[ModelCapability]) -> bool:
        return required <= self.capabilities


@dataclass(frozen=True, slots=True)
class _TaskRoute:
    task: ModelTask
    transport: ModelTransport
    required: frozenset[ModelCapability]
    profile_ids: tuple[str, ...]


class CapabilityDescriptor(BaseModel):
    """Public-safe route metadata containing no provider or concrete model IDs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ModelTask
    accepts_images: bool
    transport: ModelTransport
    fallback_count: int = Field(ge=0)


_TEXT_STRUCTURED = frozenset(
    {ModelCapability.TEXT_INPUT, ModelCapability.STRUCTURED_OUTPUT}
)


def _profile(
    profile_id: str,
    provider_model: str,
    transport: ModelTransport,
    *capabilities: ModelCapability,
) -> ModelProfile:
    normalized_model = provider_model.strip()
    if not normalized_model:
        raise ValueError("provider model must not be blank")
    return ModelProfile(
        profile_id=profile_id,
        provider_model=normalized_model,
        transport=transport,
        capabilities=frozenset(capabilities),
    )


class ModelCapabilityRegistry:
    """Validated capabilities and ordered fallbacks for USTC-backed tasks."""

    _OPERATION_TASKS: Mapping[str, ModelTask] = {
        "interpret_teaching_turn": ModelTask.LIGHTWEIGHT,
        "diagnose_student_progress": ModelTask.DIAGNOSIS,
        "diagnose_student_progress_structured": ModelTask.DIAGNOSIS,
        "compose_grounded_teaching_response": ModelTask.REASONING,
        "quantum_course_knowledge_extraction": ModelTask.DOCUMENT_REASONING,
        "propose_cognitive_commitment": ModelTask.LIGHTWEIGHT,
        "analyze_teach_back_reconstruction": ModelTask.REASONING,
        "generate_transfer_task": ModelTask.REASONING,
    }

    def __init__(
        self,
        *,
        profiles: Sequence[ModelProfile],
        routes: Sequence[_TaskRoute],
    ) -> None:
        for profile in profiles:
            if not profile.profile_id.strip() or profile.profile_id != profile.profile_id.strip():
                raise ValueError("model profile ids must be non-blank normalized text")
            if not profile.provider_model.strip():
                raise ValueError("provider model must not be blank")
            if not profile.capabilities:
                raise ValueError("model profiles must declare capabilities")
        self._profiles = {profile.profile_id: profile for profile in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("model profile ids must be unique")
        self._routes = {route.task: route for route in routes}
        if len(self._routes) != len(routes):
            raise ValueError("model tasks must have exactly one route")
        if set(self._routes) != set(ModelTask):
            raise ValueError("every model task must have a route")
        self._validate_routes()

    @classmethod
    def ustc_default(
        cls,
        *,
        reasoning_model: str = "deepseek-v4-pro",
        lightweight_model: str = "deepseek-v4-flash-ascend1",
        second_pass_model: str = "qwen3.8-reasoner",
        vision_model: str = "qwen3.8-chat",
        long_context_model: str = "glm-5.2",
        embedding_model: str = "qwen3-embedding",
        rerank_model: str = "qwen3-reranker",
        document_parser_model: str = "mineru",
        ocr_model: str = "unlimited-ocr",
    ) -> ModelCapabilityRegistry:
        profiles = [
            _profile(
                "reasoning_primary",
                reasoning_model,
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.REASONING,
                ModelCapability.LONG_CONTEXT,
            ),
            _profile(
                "reasoning_second_pass",
                second_pass_model,
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.REASONING,
            ),
            _profile(
                "reasoning_secondary",
                "qwen-reasoner",
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.REASONING,
            ),
            _profile(
                "lightweight_primary",
                lightweight_model,
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.LOW_LATENCY,
            ),
            _profile(
                "lightweight_secondary",
                "deepseek-v4-flash",
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.LOW_LATENCY,
            ),
            _profile(
                "vision_primary",
                vision_model,
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.VISION_INPUT,
            ),
            _profile(
                "vision_secondary",
                "qwen-chat",
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.VISION_INPUT,
            ),
            _profile(
                "long_context_primary",
                long_context_model,
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.REASONING,
                ModelCapability.LONG_CONTEXT,
            ),
            _profile(
                "long_context_secondary",
                "glm-5.2-107",
                ModelTransport.CHAT_COMPLETIONS,
                *_TEXT_STRUCTURED,
                ModelCapability.REASONING,
                ModelCapability.LONG_CONTEXT,
            ),
            _profile(
                "embedding_primary",
                embedding_model,
                ModelTransport.EMBEDDINGS,
                ModelCapability.TEXT_INPUT,
                ModelCapability.EMBEDDING,
            ),
            _profile(
                "rerank_primary",
                rerank_model,
                ModelTransport.RERANK,
                ModelCapability.TEXT_INPUT,
                ModelCapability.RERANKING,
            ),
            _profile(
                "document_parser_primary",
                document_parser_model,
                ModelTransport.DOCUMENT_PARSER,
                ModelCapability.DOCUMENT_PARSING,
            ),
            _profile(
                "document_parser_ocr_fallback",
                ocr_model,
                ModelTransport.DOCUMENT_PARSER,
                ModelCapability.DOCUMENT_PARSING,
                ModelCapability.OCR,
            ),
        ]
        routes = [
            _TaskRoute(
                task=ModelTask.REASONING,
                transport=ModelTransport.CHAT_COMPLETIONS,
                required=_TEXT_STRUCTURED | {ModelCapability.REASONING},
                profile_ids=(
                    "reasoning_primary",
                    "reasoning_second_pass",
                    "reasoning_secondary",
                    "long_context_primary",
                ),
            ),
            _TaskRoute(
                task=ModelTask.DIAGNOSIS,
                transport=ModelTransport.CHAT_COMPLETIONS,
                required=_TEXT_STRUCTURED | {ModelCapability.REASONING},
                profile_ids=(
                    "reasoning_primary",
                    "reasoning_second_pass",
                    "reasoning_secondary",
                ),
            ),
            _TaskRoute(
                task=ModelTask.LIGHTWEIGHT,
                transport=ModelTransport.CHAT_COMPLETIONS,
                required=_TEXT_STRUCTURED | {ModelCapability.LOW_LATENCY},
                profile_ids=("lightweight_primary", "lightweight_secondary"),
            ),
            _TaskRoute(
                task=ModelTask.VISION,
                transport=ModelTransport.CHAT_COMPLETIONS,
                required=_TEXT_STRUCTURED | {ModelCapability.VISION_INPUT},
                profile_ids=("vision_primary", "vision_secondary"),
            ),
            _TaskRoute(
                task=ModelTask.EMBEDDING,
                transport=ModelTransport.EMBEDDINGS,
                required=frozenset({ModelCapability.EMBEDDING}),
                profile_ids=("embedding_primary",),
            ),
            _TaskRoute(
                task=ModelTask.RERANK,
                transport=ModelTransport.RERANK,
                required=frozenset({ModelCapability.RERANKING}),
                profile_ids=("rerank_primary",),
            ),
            _TaskRoute(
                task=ModelTask.DOCUMENT_PARSING,
                transport=ModelTransport.DOCUMENT_PARSER,
                required=frozenset({ModelCapability.DOCUMENT_PARSING}),
                profile_ids=("document_parser_primary", "document_parser_ocr_fallback"),
            ),
            _TaskRoute(
                task=ModelTask.DOCUMENT_REASONING,
                transport=ModelTransport.CHAT_COMPLETIONS,
                required=_TEXT_STRUCTURED
                | {ModelCapability.REASONING, ModelCapability.LONG_CONTEXT},
                profile_ids=(
                    "reasoning_primary",
                    "long_context_primary",
                    "long_context_secondary",
                ),
            ),
        ]
        return cls(profiles=profiles, routes=routes)

    def _validate_routes(self) -> None:
        for route in self._routes.values():
            if not route.profile_ids:
                raise ValueError(f"model task {route.task} must have a candidate")
            for profile_id in route.profile_ids:
                profile = self._profiles.get(profile_id)
                if profile is None:
                    raise ValueError(f"model task {route.task} references an unknown profile")
                if profile.transport is not route.transport:
                    raise ValueError(f"model task {route.task} mixes incompatible transports")
                if not profile.supports(route.required):
                    raise ValueError(
                        f"model task {route.task} has a candidate without required capabilities"
                    )

    def task_for_operation(self, operation: str, tier: ModelTier) -> ModelTask:
        """Resolve a fixed operation; arbitrary strings cannot select provider models."""

        normalized = operation.strip()
        if not normalized:
            raise ValueError("model operation must not be blank")
        explicit = self._OPERATION_TASKS.get(normalized)
        if explicit is not None:
            return explicit
        return ModelTask.LIGHTWEIGHT if tier is ModelTier.SMALL else ModelTask.REASONING

    def profiles_for(self, task: ModelTask) -> tuple[ModelProfile, ...]:
        """Return the internal ordered route, de-duplicated by concrete provider model."""

        route = self._routes[task]
        profiles: list[ModelProfile] = []
        seen_models: set[str] = set()
        for profile_id in route.profile_ids:
            profile = self._profiles[profile_id]
            if profile.provider_model in seen_models:
                continue
            seen_models.add(profile.provider_model)
            profiles.append(profile)
        return tuple(profiles)

    def public_catalog(self) -> tuple[CapabilityDescriptor, ...]:
        """Return student-safe capability metadata without provider routing details."""

        return tuple(
            CapabilityDescriptor(
                id=task,
                accepts_images=ModelCapability.VISION_INPUT in route.required,
                transport=route.transport,
                fallback_count=max(0, len(self.profiles_for(task)) - 1),
            )
            for task, route in self._routes.items()
        )


GatewayFactory = Callable[[ModelProfile], ModelGateway]


@dataclass(slots=True)
class _ProfileHealth:
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    recovery_probe_in_flight: bool = False


class _ProfileHealthTracker:
    """Process-local circuit breaker keyed by private model profile ID."""

    def __init__(
        self,
        *,
        cooldown_seconds: float,
        max_cooldown_seconds: float,
        clock: Callable[[], float],
    ) -> None:
        if not math.isfinite(cooldown_seconds) or cooldown_seconds <= 0:
            raise ValueError("model route cooldown must be a finite positive number")
        if (
            not math.isfinite(max_cooldown_seconds)
            or max_cooldown_seconds < cooldown_seconds
        ):
            raise ValueError("model route maximum cooldown must be finite and not below cooldown")
        self._cooldown_seconds = cooldown_seconds
        self._max_cooldown_seconds = max_cooldown_seconds
        self._clock = clock
        self._states: dict[str, _ProfileHealth] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, profile_id: str) -> bool:
        """Admit healthy calls and at most one recovery probe after a cooldown."""

        async with self._lock:
            state = self._states.get(profile_id)
            if state is None:
                return True
            if self._clock() < state.cooldown_until:
                return False
            if state.recovery_probe_in_flight:
                return False
            state.recovery_probe_in_flight = True
            return True

    async def succeeded(self, profile_id: str) -> None:
        async with self._lock:
            self._states.pop(profile_id, None)

    async def failed(self, profile_id: str) -> None:
        async with self._lock:
            state = self._states.setdefault(profile_id, _ProfileHealth())
            state.consecutive_failures += 1
            # Capping the exponent avoids unbounded integer growth during a
            # prolonged outage; the configured maximum remains authoritative.
            multiplier = 2 ** min(state.consecutive_failures - 1, 30)
            cooldown = min(
                self._max_cooldown_seconds,
                self._cooldown_seconds * multiplier,
            )
            state.cooldown_until = self._clock() + cooldown
            state.recovery_probe_in_flight = False

    async def abandoned(self, profile_id: str) -> None:
        """Release a half-open lease when cancellation interrupts its call."""

        async with self._lock:
            state = self._states.get(profile_id)
            if state is not None:
                state.recovery_probe_in_flight = False


class ModelRouter:
    """ModelGateway implementation with task routing and bounded fallback calls."""

    def __init__(
        self,
        *,
        registry: ModelCapabilityRegistry,
        gateway_factory: GatewayFactory,
        cooldown_seconds: float = 30.0,
        max_cooldown_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._registry = registry
        self._gateway_factory = gateway_factory
        self._gateways: dict[str, ModelGateway] = {}
        self._health = _ProfileHealthTracker(
            cooldown_seconds=cooldown_seconds,
            max_cooldown_seconds=max_cooldown_seconds,
            clock=clock,
        )

    def _gateway(self, profile: ModelProfile) -> ModelGateway:
        gateway = self._gateways.get(profile.profile_id)
        if gateway is None:
            gateway = self._gateway_factory(profile)
            self._gateways[profile.profile_id] = gateway
        return gateway

    async def structured_generate(
        self,
        *,
        task: str,
        messages: Sequence[Message],
        output_type: type[T],
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> T:
        if not messages:
            raise ValueError("At least one message is required")
        capability_task = self._registry.task_for_operation(task, model_tier)
        profiles = self._registry.profiles_for(capability_task)
        if not profiles or profiles[0].transport is not ModelTransport.CHAT_COMPLETIONS:
            raise GatewayError(
                f"Capability {capability_task.value!r} is not a structured chat task"
            )

        failures = 0
        cooling = 0
        for profile in profiles:
            if not await self._health.acquire(profile.profile_id):
                cooling += 1
                continue
            try:
                output = await self._gateway(profile).structured_generate(
                    task=task,
                    messages=messages,
                    output_type=output_type,
                    model_tier=ModelTier.DEFAULT,
                )
                # Defense in depth: a custom gateway implementation cannot bypass
                # the structured-output contract enforced by the router boundary.
                validated = TypeAdapter(output_type).validate_python(output)
            except (GatewayError, ValidationError):
                failures += 1
                await self._health.failed(profile.profile_id)
            except BaseException:
                await self._health.abandoned(profile.profile_id)
                raise
            else:
                await self._health.succeeded(profile.profile_id)
                return validated
        raise GatewayError(
            f"No model route completed capability {capability_task.value!r} "
            f"after {failures} bounded attempt(s); "
            f"{cooling} route(s) temporarily cooling down"
        )

    async def probe(self) -> GatewayCapabilities:
        """Probe only the primary reasoning route; avoid spending calls on every model."""

        primary = self._registry.profiles_for(ModelTask.REASONING)[0]
        return await self._gateway(primary).probe()

    def public_catalog(self) -> tuple[CapabilityDescriptor, ...]:
        return self._registry.public_catalog()


__all__ = [
    "CapabilityDescriptor",
    "ModelCapability",
    "ModelCapabilityRegistry",
    "ModelProfile",
    "ModelRouter",
    "ModelTask",
    "ModelTransport",
]
