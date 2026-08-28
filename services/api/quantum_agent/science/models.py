"""Typed contracts for deterministic scientific verification.

The models deliberately separate a verification *kind* (the state-machine
discriminator) from the broader evidence method exposed to students and
teachers.  No model in this module accepts executable callbacks or arbitrary
tool arguments.
"""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScientificVerificationMethod(StrEnum):
    SYMBOLIC = "symbolic"
    NUMERICAL = "numerical"
    SIMULATION = "simulation"
    CODE_TEST = "code_test"
    UNVERIFIED = "unverified"


class ScientificVerificationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ScientificVerificationKind(StrEnum):
    SYMBOLIC_EQUIVALENCE = "symbolic_equivalence"
    SYMBOLIC_RESIDUAL = "symbolic_residual"
    NUMERICAL_NORMALIZATION = "numerical_normalization"
    NUMERICAL_UNITARITY = "numerical_unitarity"
    TWO_LEVEL_SIMULATION = "two_level_simulation"
    RECTANGULAR_BARRIER_TUNNELLING = "rectangular_barrier_tunnelling"
    LINE_VISUALIZATION = "line_visualization"
    CODE_TEST = "code_test"
    UNVERIFIED = "unverified"


class ToolIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)


class ComplexValue(BaseModel):
    """JSON-safe complex scalar."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    real: float = 0.0
    imag: float = 0.0

    @model_validator(mode="after")
    def finite_parts(self) -> ComplexValue:
        if not math.isfinite(self.real) or not math.isfinite(self.imag):
            raise ValueError("complex value components must be finite")
        if abs(self.real) > 1e100 or abs(self.imag) > 1e100:
            raise ValueError("complex value magnitude exceeds the numeric guard")
        return self

    def as_complex(self) -> complex:
        return complex(self.real, self.imag)


class PlotSeries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=80)
    y: list[float] = Field(min_length=2, max_length=5_000)

    @field_validator("y")
    @classmethod
    def finite_y(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) or abs(value) > 1e100 for value in values):
            raise ValueError("plot values must be finite and bounded")
        return values


class VisualizationSpec(BaseModel):
    """Data-only visualization contract; it is not a path or encoded file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    renderer: ToolIdentity
    kind: Literal["line"] = "line"
    title: str = Field(min_length=1, max_length=160)
    x_label: str = Field(min_length=1, max_length=80)
    y_label: str = Field(min_length=1, max_length=80)
    x: list[float] = Field(min_length=2, max_length=5_000)
    series: list[PlotSeries] = Field(min_length=1, max_length=8)
    rendering_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def aligned_data(self) -> VisualizationSpec:
        if any(len(series.y) != len(self.x) for series in self.series):
            raise ValueError("all plot series must align with x")
        return self


type MetricValue = float | int | str | bool


class ScientificVerificationResult(BaseModel):
    """Common auditable result returned by every scientific tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ScientificVerificationKind
    method: ScientificVerificationMethod
    status: ScientificVerificationStatus
    tool: ToolIdentity
    inputs_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observations: list[str] = Field(min_length=1, max_length=16)
    limitations: list[str] = Field(min_length=1, max_length=16)
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    visualization: VisualizationSpec | None = None
    error_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{3,64}$")

    @property
    def passed(self) -> bool | None:
        if self.status is ScientificVerificationStatus.PASS:
            return True
        if self.status is ScientificVerificationStatus.FAIL:
            return False
        return None


class _RequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


_SYMBOL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class _SymbolicRequestBase(_RequestBase):
    symbols: tuple[str, ...] = Field(default=(), max_length=16)
    timeout_seconds: float = Field(default=2.0, ge=0.1, le=5.0)

    @field_validator("symbols")
    @classmethod
    def safe_unique_symbols(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("symbol names must be unique")
        if any(not _SYMBOL_PATTERN.fullmatch(value) for value in values):
            raise ValueError("symbol name is outside the safe identifier subset")
        return values


class SymbolicEquivalenceRequest(_SymbolicRequestBase):
    kind: Literal[ScientificVerificationKind.SYMBOLIC_EQUIVALENCE] = (
        ScientificVerificationKind.SYMBOLIC_EQUIVALENCE
    )
    left: str = Field(min_length=1, max_length=1_024)
    right: str = Field(min_length=1, max_length=1_024)


class SymbolicResidualRequest(_SymbolicRequestBase):
    kind: Literal[ScientificVerificationKind.SYMBOLIC_RESIDUAL] = (
        ScientificVerificationKind.SYMBOLIC_RESIDUAL
    )
    expression: str = Field(min_length=1, max_length=1_024)


class NumericalNormalizationRequest(_RequestBase):
    kind: Literal[ScientificVerificationKind.NUMERICAL_NORMALIZATION] = (
        ScientificVerificationKind.NUMERICAL_NORMALIZATION
    )
    state: list[ComplexValue] = Field(min_length=1, max_length=4_096)
    target_norm_squared: float = Field(default=1.0, gt=0, le=1e12)
    absolute_tolerance: float = Field(default=1e-10, gt=0, le=1e-2)


class NumericalUnitarityRequest(_RequestBase):
    kind: Literal[ScientificVerificationKind.NUMERICAL_UNITARITY] = (
        ScientificVerificationKind.NUMERICAL_UNITARITY
    )
    matrix: list[list[ComplexValue]] = Field(min_length=1, max_length=64)
    absolute_tolerance: float = Field(default=1e-10, gt=0, le=1e-2)

    @model_validator(mode="after")
    def square_bounded_matrix(self) -> NumericalUnitarityRequest:
        dimension = len(self.matrix)
        if any(len(row) != dimension for row in self.matrix):
            raise ValueError("unitarity requires a square matrix")
        return self


class TwoLevelSimulationRequest(_RequestBase):
    kind: Literal[ScientificVerificationKind.TWO_LEVEL_SIMULATION] = (
        ScientificVerificationKind.TWO_LEVEL_SIMULATION
    )
    initial_state: list[ComplexValue] = Field(
        default_factory=lambda: [ComplexValue(real=1.0), ComplexValue()],
        min_length=2,
        max_length=2,
    )
    rabi_frequency: float = Field(default=1.0, ge=-1e6, le=1e6)
    detuning: float = Field(default=0.0, ge=-1e6, le=1e6)
    duration: float = Field(default=math.pi, gt=0, le=1e4)
    steps: int = Field(default=101, ge=2, le=2_001)
    absolute_tolerance: float = Field(default=1e-8, gt=0, le=1e-2)

    @model_validator(mode="after")
    def finite_parameters(self) -> TwoLevelSimulationRequest:
        values = (self.rabi_frequency, self.detuning, self.duration)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("simulation parameters must be finite")
        fastest_rate = max(abs(self.rabi_frequency), abs(self.detuning))
        if fastest_rate * self.duration > 1_000:
            raise ValueError("simulation duration and frequency exceed the evolution-work guard")
        return self


class RectangularBarrierRequest(_RequestBase):
    """A finite rectangular barrier scattering calculation.

    Models the stationary scattering of a non-relativistic particle of mass
    ``particle_mass_kg`` and kinetic energy ``energy_eV`` incident on a barrier
    of height ``barrier_height_eV`` and width ``barrier_width_m``.  The
    verifier computes the transmission coefficient ``T`` and reflection
    coefficient ``R`` from the analytically correct rectangular-barrier
    formula and checks ``abs(R + T - 1) <= conservation_tolerance``.

    The Golden Loop case ``E < V0`` uses the tunnelling formula:

        kappa = sqrt(2 m (V0 - E)) / hbar
        T = [1 + V0**2 * sinh**2(kappa * a) / (4 E (V0 - E))] ** -1
        R = 1 - T

    All parameters carry explicit SI units so the result is reproducible
    without any unit convention ambiguity.
    """

    kind: Literal[ScientificVerificationKind.RECTANGULAR_BARRIER_TUNNELLING] = (
        ScientificVerificationKind.RECTANGULAR_BARRIER_TUNNELLING
    )
    energy_eV: float = Field(gt=0, le=1e6)
    barrier_height_eV: float = Field(gt=0, le=1e6)
    barrier_width_m: float = Field(gt=0, le=1e-3)
    particle_mass_kg: float = Field(gt=0, le=1e-21)
    conservation_tolerance: float = Field(default=1e-9, gt=0, le=1e-2)

    @model_validator(mode="after")
    def finite_physical_parameters(self) -> RectangularBarrierRequest:
        values = (
            self.energy_eV,
            self.barrier_height_eV,
            self.barrier_width_m,
            self.particle_mass_kg,
            self.conservation_tolerance,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("rectangular barrier parameters must be finite")
        # The analytic formula is numerically unstable when E is extremely
        # close to V0 (the k1=kappa degenerate case).  Reject that band so the
        # verifier never reports a noisy T/R pair.
        if abs(self.energy_eV - self.barrier_height_eV) <= 1e-9 * self.barrier_height_eV:
            raise ValueError(
                "energy is too close to barrier height; the degenerate case is rejected"
            )
        return self


class LineVisualizationRequest(_RequestBase):
    kind: Literal[ScientificVerificationKind.LINE_VISUALIZATION] = (
        ScientificVerificationKind.LINE_VISUALIZATION
    )
    title: str = Field(min_length=1, max_length=160)
    x_label: str = Field(min_length=1, max_length=80)
    y_label: str = Field(min_length=1, max_length=80)
    x: list[float] = Field(min_length=2, max_length=5_000)
    series: list[PlotSeries] = Field(min_length=1, max_length=8)

    @field_validator("x")
    @classmethod
    def finite_x(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) or abs(value) > 1e100 for value in values):
            raise ValueError("plot values must be finite and bounded")
        return values

    @model_validator(mode="after")
    def aligned_data(self) -> LineVisualizationRequest:
        if any(len(series.y) != len(self.x) for series in self.series):
            raise ValueError("all plot series must align with x")
        return self


class CodeTestRequest(_RequestBase):
    kind: Literal[ScientificVerificationKind.CODE_TEST] = ScientificVerificationKind.CODE_TEST
    language: Literal["python"] = "python"
    code: str = Field(min_length=1, max_length=10_000)
    tests: list[str] = Field(min_length=1, max_length=32)

    @field_validator("tests")
    @classmethod
    def bounded_tests(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 2_000 for value in values):
            raise ValueError("each test must contain between 1 and 2000 characters")
        return values


class UnverifiedRequest(_RequestBase):
    kind: Literal[ScientificVerificationKind.UNVERIFIED] = ScientificVerificationKind.UNVERIFIED
    claim: str = Field(min_length=1, max_length=4_000)
    reason: str = Field(min_length=1, max_length=240)


ScientificVerificationRequest = Annotated[
    SymbolicEquivalenceRequest
    | SymbolicResidualRequest
    | NumericalNormalizationRequest
    | NumericalUnitarityRequest
    | TwoLevelSimulationRequest
    | RectangularBarrierRequest
    | LineVisualizationRequest
    | CodeTestRequest
    | UnverifiedRequest,
    Field(discriminator="kind"),
]


class SandboxLimits(BaseModel):
    """Fail-closed limits expected from a future isolated container executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wall_time_seconds: float = Field(default=3.0, ge=0.1, le=10.0)
    memory_megabytes: int = Field(default=512, ge=32, le=512)
    process_count: int = Field(default=1, ge=1, le=4)
    network_enabled: Literal[False] = False
    read_only_root: Literal[True] = True


class SandboxExecutionOutcome(BaseModel):
    """Sanitized outcome: raw process output is intentionally excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    completed: bool
    exit_code: int | None = None
    tests_run: int = Field(default=0, ge=0, le=32)
    tests_failed: int = Field(default=0, ge=0, le=32)
    timed_out: bool = False

    @model_validator(mode="after")
    def internally_consistent(self) -> SandboxExecutionOutcome:
        if self.tests_failed > self.tests_run:
            raise ValueError("tests_failed cannot exceed tests_run")
        return self
