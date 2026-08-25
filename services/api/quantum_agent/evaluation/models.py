"""Typed, provider-free contracts for architecture and multimodal evaluation.

The evaluator consumes captured observations.  It never calls a model, a
retriever, or a verifier while scoring, so the same fixture always produces the
same report.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvaluationVariant(StrEnum):
    """Architecture ablations defined by PRD section 23.2."""

    B0 = "B0"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"


class CoverageLabel(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class HintLevel(StrEnum):
    H0 = "H0"
    H1 = "H1"
    H2 = "H2"
    H3 = "H3"
    H4 = "H4"
    H5 = "H5"


class VerifierVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class MultimodalKind(StrEnum):
    PRINTED_EQUATION = "printed_equation"
    HANDWRITTEN_DERIVATION = "handwritten_derivation"
    LECTURE_SCREENSHOT = "lecture_screenshot"
    FIGURE = "figure"
    PLOT = "plot"
    SCANNED_PDF = "scanned_pdf"
    COURSE_DOCUMENT = "course_document"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BoundingBox(StrictModel):
    """A source-coordinate rectangle; units are preserved from the parser."""

    x_min: float = Field(ge=0)
    y_min: float = Field(ge=0)
    x_max: float = Field(gt=0)
    y_max: float = Field(gt=0)

    @model_validator(mode="after")
    def has_positive_area(self) -> BoundingBox:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("bounding box must have positive area")
        return self


class ProvenanceLocator(StrictModel):
    """Stable document locator used for citation and multimodal provenance."""

    document_id: str = Field(min_length=1, max_length=200)
    document_version: str | None = Field(default=None, max_length=200)
    page_number: int | None = Field(default=None, ge=1)
    slide_number: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=300)
    paragraph_index: int | None = Field(default=None, ge=0)
    figure_id: str | None = Field(default=None, max_length=200)
    bbox: BoundingBox | None = None

    @field_validator("document_id", "document_version", "section", "figure_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("locator text fields must not be blank")
        return normalized


class ExpectedCitation(StrictModel):
    citation_id: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=20_000)
    locator: ProvenanceLocator
    required: bool = True
    supported_claims: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("citation_id", "excerpt")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("citation text must not be blank")
        return normalized

    @field_validator("supported_claims")
    @classmethod
    def normalize_supported_claims(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(item.strip().split()) for item in value]
        if any(not item for item in normalized):
            raise ValueError("supported claims must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("supported claims must be unique")
        return normalized


class CitationObservation(StrictModel):
    citation_id: str = Field(min_length=1, max_length=200)
    locator: ProvenanceLocator


class ClaimObservation(StrictModel):
    text: str = Field(min_length=1, max_length=4_000)
    citation_ids: list[str] = Field(default_factory=list, max_length=20)
    requires_course_evidence: bool = True

    @field_validator("text")
    @classmethod
    def normalize_claim(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("claim must not be blank")
        return normalized


class DiagnosisExpectation(StrictModel):
    target_concepts: list[str] = Field(default_factory=list, max_length=20)
    misconception_labels: list[str] = Field(default_factory=list, max_length=20)
    missing_prerequisites: list[str] = Field(default_factory=list, max_length=20)
    first_error_applicable: bool = False
    first_error_step: int | None = Field(default=None, ge=0)

    @field_validator("target_concepts", "misconception_labels", "missing_prerequisites")
    @classmethod
    def labels_are_unique_and_nonblank(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(item.strip().split()) for item in value]
        if any(not item for item in normalized):
            raise ValueError("diagnosis labels must not be blank")
        if len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("diagnosis labels must be unique")
        return normalized


class DiagnosisObservation(StrictModel):
    target_concepts: list[str] = Field(default_factory=list, max_length=20)
    misconception_labels: list[str] = Field(default_factory=list, max_length=20)
    missing_prerequisites: list[str] = Field(default_factory=list, max_length=20)
    first_error_step: int | None = Field(default=None, ge=0)


class PolicyExpectation(StrictModel):
    maximum_hint_level: HintLevel
    full_solution_allowed: bool = False
    forbidden_answer_fragments: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("forbidden_answer_fragments")
    @classmethod
    def fragments_are_nonblank(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(item.strip().split()) for item in value]
        if any(not item for item in normalized):
            raise ValueError("forbidden answer fragments must not be blank")
        return normalized


class PolicyObservation(StrictModel):
    hint_level: HintLevel
    released_full_solution: bool = False
    response_text: str = Field(default="", max_length=50_000)


class VerifierExpectation(StrictModel):
    verdict: VerifierVerdict


class VerifierObservation(StrictModel):
    """Both fields are scored so a model cannot overwrite a tool verdict."""

    tool_verdict: VerifierVerdict
    response_verdict: VerifierVerdict


class MultimodalExpectation(StrictModel):
    kind: MultimodalKind
    transcription: str | None = Field(default=None, max_length=50_000)
    formulas: list[str] = Field(default_factory=list, max_length=100)
    derivation_step_count: int | None = Field(default=None, ge=0)
    concepts: list[str] = Field(default_factory=list, max_length=50)
    axis_labels: list[str] = Field(default_factory=list, max_length=20)
    provenance: ProvenanceLocator | None = None
    ambiguous: bool | None = None


class MultimodalObservation(StrictModel):
    transcription: str | None = Field(default=None, max_length=50_000)
    formulas: list[str] = Field(default_factory=list, max_length=100)
    derivation_step_count: int | None = Field(default=None, ge=0)
    concepts: list[str] = Field(default_factory=list, max_length=50)
    axis_labels: list[str] = Field(default_factory=list, max_length=20)
    provenance: ProvenanceLocator | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    confirmation_requested: bool = False


class ExpectedOutcome(StrictModel):
    citations: list[ExpectedCitation] = Field(default_factory=list, max_length=100)
    coverage: CoverageLabel | None = None
    diagnosis: DiagnosisExpectation | None = None
    policy: PolicyExpectation | None = None
    verifier: VerifierExpectation | None = None
    checkpoint_recovery_required: bool = False
    interrupt_resume_required: bool = False
    multimodal: MultimodalExpectation | None = None

    @model_validator(mode="after")
    def citation_ids_are_unique(self) -> ExpectedOutcome:
        citation_ids = [citation.citation_id for citation in self.citations]
        if len(set(citation_ids)) != len(citation_ids):
            raise ValueError("expected citation ids must be unique")
        return self


class ObservedOutcome(StrictModel):
    citations: list[CitationObservation] = Field(default_factory=list, max_length=100)
    claims: list[ClaimObservation] = Field(default_factory=list, max_length=100)
    coverage: CoverageLabel | None = None
    diagnosis: DiagnosisObservation | None = None
    policy: PolicyObservation | None = None
    verifier: VerifierObservation | None = None
    latency_ms: float = Field(ge=0)
    token_count: int = Field(ge=0)
    token_cost_usd: float = Field(ge=0)
    agent_calls: int = Field(ge=0)
    checkpoint_recovered: bool | None = None
    interrupt_triggered: bool | None = None
    interrupt_resumed: bool | None = None
    interrupt_same_thread: bool | None = None
    multimodal: MultimodalObservation | None = None

    @model_validator(mode="after")
    def observed_citation_ids_are_unique(self) -> ObservedOutcome:
        citation_ids = [citation.citation_id for citation in self.citations]
        if len(set(citation_ids)) != len(citation_ids):
            raise ValueError("observed citation ids must be unique")
        return self


class EvaluationCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=200)
    scenario_id: str = Field(min_length=1, max_length=200)
    variant: EvaluationVariant
    expected: ExpectedOutcome
    observed: ObservedOutcome
    tags: list[str] = Field(default_factory=list, max_length=30)


class EvaluationDataset(StrictModel):
    schema_version: str = Field(default="1.0", pattern=r"^\d+\.\d+$")
    dataset_id: str = Field(min_length=1, max_length=200)
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> EvaluationDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("evaluation case ids must be unique")
        return self


class MetricResult(StrictModel):
    applicable: bool
    score: float | None = Field(default=None, ge=0, le=1)
    passed: bool | None = None
    numerator: float = Field(default=0, ge=0)
    denominator: float = Field(default=0, ge=0)
    threshold: float = Field(default=1.0, ge=0, le=1)
    detail: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def applicability_is_consistent(self) -> MetricResult:
        if self.applicable:
            if self.denominator <= 0 or self.score is None or self.passed is None:
                raise ValueError("applicable metrics require score, pass, and denominator")
        elif self.score is not None or self.passed is not None or self.denominator != 0:
            raise ValueError("non-applicable metrics cannot carry a score")
        return self


class CaseMetrics(StrictModel):
    citation_correctness: MetricResult
    citation_support: MetricResult
    coverage_calibration: MetricResult
    diagnosis_accuracy: MetricResult
    missing_prerequisite_accuracy: MetricResult
    first_error_localization: MetricResult
    policy_compliance: MetricResult
    verifier_correctness: MetricResult
    checkpoint_recovery: MetricResult
    interrupt_resume_success: MetricResult
    multimodal_transcription: MetricResult
    multimodal_formula_transcription: MetricResult
    multimodal_provenance: MetricResult
    multimodal_structure: MetricResult
    answer_leakage_detected: bool | None = None
    leakage_reasons: list[str] = Field(default_factory=list)


class EvaluationCaseResult(StrictModel):
    case_id: str
    scenario_id: str
    variant: EvaluationVariant
    metrics: CaseMetrics
    latency_ms: float = Field(ge=0)
    token_count: int = Field(ge=0)
    token_cost_usd: float = Field(ge=0)
    agent_calls: int = Field(ge=0)


class AggregateMetric(StrictModel):
    applicable_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    mean_score: float | None = Field(default=None, ge=0, le=1)
    pass_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> AggregateMetric:
        if self.passed_cases > self.applicable_cases:
            raise ValueError("passed cases cannot exceed applicable cases")
        empty_has_scores = self.mean_score is not None or self.pass_rate is not None
        if self.applicable_cases == 0 and empty_has_scores:
            raise ValueError("empty aggregates cannot carry scores")
        if self.applicable_cases > 0 and (self.mean_score is None or self.pass_rate is None):
            raise ValueError("non-empty aggregates require scores")
        return self


class DistributionSummary(StrictModel):
    count: int = Field(ge=0)
    total: float = Field(ge=0)
    minimum: float | None = Field(default=None, ge=0)
    mean: float | None = Field(default=None, ge=0)
    p95: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)


class VariantAggregate(StrictModel):
    variant: EvaluationVariant
    case_count: int = Field(ge=1)
    citation_correctness: AggregateMetric
    citation_support: AggregateMetric
    coverage_calibration: AggregateMetric
    diagnosis_accuracy: AggregateMetric
    missing_prerequisite_accuracy: AggregateMetric
    first_error_localization: AggregateMetric
    policy_compliance: AggregateMetric
    verifier_correctness: AggregateMetric
    checkpoint_recovery: AggregateMetric
    interrupt_resume_success: AggregateMetric
    multimodal_transcription: AggregateMetric
    multimodal_formula_transcription: AggregateMetric
    multimodal_provenance: AggregateMetric
    multimodal_structure: AggregateMetric
    answer_leakage_applicable_cases: int = Field(ge=0)
    answer_leakage_cases: int = Field(ge=0)
    answer_leakage_rate: float | None = Field(default=None, ge=0, le=1)
    latency_ms: DistributionSummary
    token_count: DistributionSummary
    token_cost_usd: DistributionSummary
    agent_calls: DistributionSummary


class EvaluationReport(StrictModel):
    schema_version: str
    dataset_id: str
    case_results: list[EvaluationCaseResult]
    variants: list[VariantAggregate]


# Short aliases make the public contract vocabulary convenient for downstream tools.
EvalCase = EvaluationCase
EvalResult = EvaluationCaseResult
EvalAggregate = VariantAggregate
