"""Deterministic metric calculators for captured tutor runs."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Callable, Iterable
from difflib import SequenceMatcher

from quantum_agent.evaluation.models import (
    AggregateMetric,
    BoundingBox,
    CaseMetrics,
    CitationObservation,
    DistributionSummary,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationReport,
    EvaluationVariant,
    ExpectedCitation,
    HintLevel,
    MetricResult,
    MultimodalObservation,
    ProvenanceLocator,
    VariantAggregate,
)

_HINT_RANK = {level: index for index, level in enumerate(HintLevel)}


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _normalize_formula(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _not_applicable(detail: str) -> MetricResult:
    return MetricResult(applicable=False, detail=detail)


def _scored(
    score: float,
    *,
    numerator: float,
    denominator: float,
    detail: str,
    threshold: float = 1.0,
) -> MetricResult:
    bounded = min(1.0, max(0.0, score))
    return MetricResult(
        applicable=True,
        score=bounded,
        passed=bounded >= threshold,
        numerator=numerator,
        denominator=denominator,
        threshold=threshold,
        detail=detail,
    )


def _exact(success: bool, detail: str) -> MetricResult:
    return _scored(
        float(success),
        numerator=float(success),
        denominator=1,
        detail=detail,
    )


def _normalized_set(values: Iterable[str]) -> set[str]:
    return {_normalize_text(value) for value in values}


def _set_f1(expected: Iterable[str], observed: Iterable[str]) -> tuple[float, int, int, int]:
    expected_set = _normalized_set(expected)
    observed_set = _normalized_set(observed)
    true_positive = len(expected_set & observed_set)
    denominator = len(expected_set) + len(observed_set)
    if denominator == 0:
        return 1.0, true_positive, len(expected_set), len(observed_set)
    return 2 * true_positive / denominator, true_positive, len(expected_set), len(observed_set)


def _sequence_similarity(expected: str, observed: str, *, formula: bool = False) -> float:
    normalize = _normalize_formula if formula else _normalize_text
    left = normalize(expected)
    right = normalize(observed)
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    # Exact edit similarity for ordinary equations/transcriptions.  The bounded
    # fallback prevents pathological long documents from allocating quadratic
    # work while remaining deterministic.
    if len(left) * len(right) > 4_000_000:
        return SequenceMatcher(None, left, right, autojunk=False).ratio()
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (left_character != right_character)
            current.append(min(insertion, deletion, substitution))
        previous = current
    distance = previous[-1]
    return 1 - distance / max(len(left), len(right))


def _bbox_iou(expected: BoundingBox, observed: BoundingBox) -> float:
    intersection_width = max(
        0.0, min(expected.x_max, observed.x_max) - max(expected.x_min, observed.x_min)
    )
    intersection_height = max(
        0.0, min(expected.y_max, observed.y_max) - max(expected.y_min, observed.y_min)
    )
    intersection = intersection_width * intersection_height
    expected_area = (expected.x_max - expected.x_min) * (expected.y_max - expected.y_min)
    observed_area = (observed.x_max - observed.x_min) * (observed.y_max - observed.y_min)
    union = expected_area + observed_area - intersection
    return intersection / union if union else 0.0


def _locator_score(
    expected: ProvenanceLocator, observed: ProvenanceLocator | None
) -> tuple[float, int]:
    fields = (
        "document_id",
        "document_version",
        "page_number",
        "slide_number",
        "section",
        "paragraph_index",
        "figure_id",
    )
    expected_values = expected.model_dump()
    observed_values = observed.model_dump() if observed is not None else {}
    components: list[float] = []
    for field_name in fields:
        expected_value = expected_values[field_name]
        if expected_value is not None:
            components.append(float(observed_values.get(field_name) == expected_value))
    if expected.bbox is not None:
        observed_bbox = observed.bbox if observed is not None else None
        components.append(_bbox_iou(expected.bbox, observed_bbox) if observed_bbox else 0.0)
    return sum(components) / len(components), len(components)


def citation_correctness(case: EvaluationCase) -> MetricResult:
    required = {item.citation_id: item for item in case.expected.citations if item.required}
    if not required:
        return _not_applicable("No required course citations in the gold case.")
    available = {item.citation_id: item for item in case.expected.citations}
    valid_observed: set[str] = set()
    for citation in case.observed.citations:
        expected = available.get(citation.citation_id)
        if expected is not None and citation.locator == expected.locator:
            valid_observed.add(citation.citation_id)
    precision = (
        len(valid_observed) / len(case.observed.citations)
        if case.observed.citations
        else 0.0
    )
    required_hits = len(valid_observed & required.keys())
    recall = required_hits / len(required)
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return _scored(
        score,
        numerator=score,
        denominator=1,
        detail=(
            f"{len(valid_observed)}/{len(case.observed.citations)} emitted locators valid; "
            f"{required_hits}/{len(required)} required citations recovered."
        ),
    )


def _valid_observed_citation_ids(
    expected: dict[str, ExpectedCitation], observed: list[CitationObservation]
) -> set[str]:
    return {
        item.citation_id
        for item in observed
        if item.citation_id in expected and item.locator == expected[item.citation_id].locator
    }


def citation_support(case: EvaluationCase) -> MetricResult:
    claims = [claim for claim in case.observed.claims if claim.requires_course_evidence]
    if not claims:
        return _not_applicable("No observed course-fact claims require citation support.")
    expected = {item.citation_id: item for item in case.expected.citations}
    valid_ids = _valid_observed_citation_ids(expected, case.observed.citations)
    supported = 0
    for claim in claims:
        normalized_claim = _normalize_text(claim.text)
        claim_supported = False
        for citation_id in claim.citation_ids:
            if citation_id not in valid_ids:
                continue
            source = expected[citation_id]
            labeled_claims = {_normalize_text(item) for item in source.supported_claims}
            excerpt = _normalize_text(source.excerpt)
            if normalized_claim in labeled_claims or normalized_claim in excerpt:
                claim_supported = True
                break
        supported += int(claim_supported)
    return _scored(
        supported / len(claims),
        numerator=supported,
        denominator=len(claims),
        detail=f"{supported}/{len(claims)} course-fact claims have labeled source support.",
    )


def coverage_calibration(case: EvaluationCase) -> MetricResult:
    expected = case.expected.coverage
    if expected is None:
        return _not_applicable("Coverage was not labeled for this case.")
    observed = case.observed.coverage
    return _exact(observed == expected, f"Expected {expected}; observed {observed}.")


def diagnosis_accuracy(case: EvaluationCase) -> MetricResult:
    expected = case.expected.diagnosis
    if expected is None:
        return _not_applicable("Diagnosis was not labeled for this case.")
    observed = case.observed.diagnosis
    if observed is None:
        return _scored(0, numerator=0, denominator=1, detail="No diagnosis was observed.")
    target_score, target_hits, target_expected, target_observed = _set_f1(
        expected.target_concepts, observed.target_concepts
    )
    misconception_score, misconception_hits, misconception_expected, misconception_observed = (
        _set_f1(expected.misconception_labels, observed.misconception_labels)
    )
    components: list[float] = []
    if target_expected or target_observed:
        components.append(target_score)
    if misconception_expected or misconception_observed:
        components.append(misconception_score)
    if not components:
        components.append(1.0)
    score = sum(components) / len(components)
    return _scored(
        score,
        numerator=sum(components),
        denominator=len(components),
        detail=(
            f"Targets {target_hits}/{target_expected} gold with {target_observed} emitted; "
            f"misconceptions {misconception_hits}/{misconception_expected} gold with "
            f"{misconception_observed} emitted."
        ),
    )


def missing_prerequisite_accuracy(case: EvaluationCase) -> MetricResult:
    expected = case.expected.diagnosis
    if expected is None:
        return _not_applicable("Missing prerequisites were not labeled for this case.")
    observed_values = (
        case.observed.diagnosis.missing_prerequisites if case.observed.diagnosis else []
    )
    if not expected.missing_prerequisites and not observed_values:
        return _not_applicable("No missing prerequisites were expected or emitted.")
    score, hits, expected_count, observed_count = _set_f1(
        expected.missing_prerequisites, observed_values
    )
    return _scored(
        score,
        numerator=2 * hits,
        denominator=expected_count + observed_count,
        detail=f"{hits}/{expected_count} gold prerequisites matched with {observed_count} emitted.",
    )


def first_error_localization(case: EvaluationCase) -> MetricResult:
    expected = case.expected.diagnosis
    if expected is None or not expected.first_error_applicable:
        return _not_applicable("First-error localization was not labeled for this case.")
    if case.observed.diagnosis is None:
        return _scored(0, numerator=0, denominator=1, detail="No diagnosis was observed.")
    observed = case.observed.diagnosis.first_error_step
    return _exact(
        observed == expected.first_error_step,
        f"Expected first error at step {expected.first_error_step}; observed {observed}.",
    )


def answer_leakage(case: EvaluationCase) -> tuple[bool | None, list[str]]:
    """Return detected leakage and auditable exact-match reasons, or ``None`` if unscored."""

    expected = case.expected.policy
    if expected is None:
        return None, []
    observed = case.observed.policy
    if observed is None:
        return None, []
    reasons: list[str] = []
    if observed.released_full_solution and not expected.full_solution_allowed:
        reasons.append("full_solution_released")
    response = _normalize_text(observed.response_text)
    for fragment in expected.forbidden_answer_fragments:
        if _normalize_text(fragment) in response:
            reasons.append(f"forbidden_fragment:{fragment}")
    return bool(reasons), reasons


def policy_compliance(case: EvaluationCase) -> MetricResult:
    expected = case.expected.policy
    if expected is None:
        return _not_applicable("Policy was not labeled for this case.")
    observed = case.observed.policy
    leakage, _ = answer_leakage(case)
    if observed is None:
        return _scored(
            0,
            numerator=0,
            denominator=1,
            detail="No policy outcome was captured.",
        )
    hint_allowed = _HINT_RANK[observed.hint_level] <= _HINT_RANK[expected.maximum_hint_level]
    compliant = hint_allowed and not bool(leakage)
    detail = (
        f"Observed {observed.hint_level} under maximum {expected.maximum_hint_level}; "
        f"leakage={bool(leakage)}."
    )
    return _exact(compliant, detail)


def verifier_correctness(case: EvaluationCase) -> MetricResult:
    expected = case.expected.verifier
    if expected is None:
        return _not_applicable("Verifier behavior was not labeled for this case.")
    observed = case.observed.verifier
    if observed is None:
        return _scored(0, numerator=0, denominator=1, detail="No verifier outcome was captured.")
    correct = (
        observed.tool_verdict == expected.verdict
        and observed.response_verdict == expected.verdict
    )
    return _exact(
        correct,
        f"Expected {expected.verdict}; tool={observed.tool_verdict}, "
        f"response={observed.response_verdict}.",
    )


def checkpoint_recovery(case: EvaluationCase) -> MetricResult:
    if not case.expected.checkpoint_recovery_required:
        return _not_applicable("Checkpoint recovery was not exercised in this case.")
    return _exact(
        case.observed.checkpoint_recovered is True,
        f"checkpoint_recovered={case.observed.checkpoint_recovered}.",
    )


def interrupt_resume_success(case: EvaluationCase) -> MetricResult:
    if not case.expected.interrupt_resume_required:
        return _not_applicable("Interrupt/resume was not exercised in this case.")
    observed = case.observed
    success = (
        observed.interrupt_triggered is True
        and observed.interrupt_resumed is True
        and observed.interrupt_same_thread is True
    )
    return _exact(
        success,
        "triggered="
        f"{observed.interrupt_triggered}, resumed={observed.interrupt_resumed}, "
        f"same_thread={observed.interrupt_same_thread}.",
    )


def multimodal_transcription(case: EvaluationCase) -> MetricResult:
    expected = case.expected.multimodal
    if expected is None or expected.transcription is None:
        return _not_applicable("No multimodal transcription gold label is present.")
    observed = case.observed.multimodal
    value = observed.transcription if observed and observed.transcription is not None else ""
    score = _sequence_similarity(expected.transcription, value)
    return _scored(
        score,
        numerator=score,
        denominator=1,
        threshold=0.95,
        detail=f"Normalized transcription edit similarity={score:.6f}.",
    )


def multimodal_formula_transcription(case: EvaluationCase) -> MetricResult:
    expected = case.expected.multimodal
    if expected is None or not expected.formulas:
        return _not_applicable("No formula transcription gold labels are present.")
    observed = case.observed.multimodal
    observed_formulas = observed.formulas if observed else []
    count = max(len(expected.formulas), len(observed_formulas))
    scores = [
        _sequence_similarity(
            expected.formulas[index] if index < len(expected.formulas) else "",
            observed_formulas[index] if index < len(observed_formulas) else "",
            formula=True,
        )
        for index in range(count)
    ]
    score = sum(scores) / count
    return _scored(
        score,
        numerator=sum(scores),
        denominator=count,
        threshold=0.95,
        detail=(
            f"{len(observed_formulas)} formulas emitted for "
            f"{len(expected.formulas)} gold formulas; "
            f"mean edit similarity={score:.6f}."
        ),
    )


def multimodal_provenance(case: EvaluationCase) -> MetricResult:
    expected = case.expected.multimodal
    if expected is None or expected.provenance is None:
        return _not_applicable("No multimodal page/slide provenance label is present.")
    observed = case.observed.multimodal
    score, component_count = _locator_score(
        expected.provenance, observed.provenance if observed else None
    )
    return _scored(
        score,
        numerator=score * component_count,
        denominator=component_count,
        detail=f"Locator field accuracy={score:.6f} across {component_count} labeled fields.",
    )


def multimodal_structure(case: EvaluationCase) -> MetricResult:
    expected = case.expected.multimodal
    if expected is None:
        return _not_applicable("No multimodal structure labels are present.")
    observed: MultimodalObservation | None = case.observed.multimodal
    components: list[float] = []
    labels: list[str] = []
    if expected.derivation_step_count is not None:
        value = observed.derivation_step_count if observed else None
        components.append(float(value == expected.derivation_step_count))
        labels.append("step_count")
    if expected.concepts:
        score, _, _, _ = _set_f1(expected.concepts, observed.concepts if observed else [])
        components.append(score)
        labels.append("concepts")
    if expected.axis_labels:
        score, _, _, _ = _set_f1(expected.axis_labels, observed.axis_labels if observed else [])
        components.append(score)
        labels.append("axis_labels")
    if expected.ambiguous is not None:
        confidence = observed.confidence if observed else None
        confirmation = observed.confirmation_requested if observed else False
        if expected.ambiguous:
            calibrated = confidence is not None and confidence < 0.8 and confirmation
        else:
            calibrated = confidence is not None and confidence >= 0.8 and not confirmation
        components.append(float(calibrated))
        labels.append("confidence_confirmation")
    if not components:
        return _not_applicable("The multimodal case has no structure labels to score.")
    score = sum(components) / len(components)
    return _scored(
        score,
        numerator=sum(components),
        denominator=len(components),
        detail=f"Scored structure components: {', '.join(labels)}.",
    )


def evaluate_case(case: EvaluationCase) -> EvaluationCaseResult:
    leakage, leakage_reasons = answer_leakage(case)
    metrics = CaseMetrics(
        citation_correctness=citation_correctness(case),
        citation_support=citation_support(case),
        coverage_calibration=coverage_calibration(case),
        diagnosis_accuracy=diagnosis_accuracy(case),
        missing_prerequisite_accuracy=missing_prerequisite_accuracy(case),
        first_error_localization=first_error_localization(case),
        policy_compliance=policy_compliance(case),
        verifier_correctness=verifier_correctness(case),
        checkpoint_recovery=checkpoint_recovery(case),
        interrupt_resume_success=interrupt_resume_success(case),
        multimodal_transcription=multimodal_transcription(case),
        multimodal_formula_transcription=multimodal_formula_transcription(case),
        multimodal_provenance=multimodal_provenance(case),
        multimodal_structure=multimodal_structure(case),
        answer_leakage_detected=leakage,
        leakage_reasons=leakage_reasons,
    )
    observed = case.observed
    return EvaluationCaseResult(
        case_id=case.case_id,
        scenario_id=case.scenario_id,
        variant=case.variant,
        metrics=metrics,
        latency_ms=observed.latency_ms,
        token_count=observed.token_count,
        token_cost_usd=observed.token_cost_usd,
        agent_calls=observed.agent_calls,
    )


def _aggregate_metric(
    results: list[EvaluationCaseResult], selector: Callable[[CaseMetrics], MetricResult]
) -> AggregateMetric:
    metrics = [selector(result.metrics) for result in results]
    applicable = [metric for metric in metrics if metric.applicable]
    if not applicable:
        return AggregateMetric(applicable_cases=0, passed_cases=0)
    scores = [metric.score for metric in applicable if metric.score is not None]
    passed_cases = sum(metric.passed is True for metric in applicable)
    return AggregateMetric(
        applicable_cases=len(applicable),
        passed_cases=passed_cases,
        mean_score=sum(scores) / len(scores),
        pass_rate=passed_cases / len(applicable),
    )


def _distribution(values: Iterable[float | int]) -> DistributionSummary:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return DistributionSummary(count=0, total=0)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return DistributionSummary(
        count=len(ordered),
        total=sum(ordered),
        minimum=ordered[0],
        mean=sum(ordered) / len(ordered),
        p95=ordered[p95_index],
        maximum=ordered[-1],
    )


def aggregate_variant(
    variant: EvaluationVariant, results: list[EvaluationCaseResult]
) -> VariantAggregate:
    if not results:
        raise ValueError("cannot aggregate an empty variant")
    leakage_values = [
        result.metrics.answer_leakage_detected
        for result in results
        if result.metrics.answer_leakage_detected is not None
    ]
    leakage_cases = sum(value is True for value in leakage_values)
    return VariantAggregate(
        variant=variant,
        case_count=len(results),
        citation_correctness=_aggregate_metric(
            results, lambda metrics: metrics.citation_correctness
        ),
        citation_support=_aggregate_metric(results, lambda metrics: metrics.citation_support),
        coverage_calibration=_aggregate_metric(
            results, lambda metrics: metrics.coverage_calibration
        ),
        diagnosis_accuracy=_aggregate_metric(results, lambda metrics: metrics.diagnosis_accuracy),
        missing_prerequisite_accuracy=_aggregate_metric(
            results, lambda metrics: metrics.missing_prerequisite_accuracy
        ),
        first_error_localization=_aggregate_metric(
            results, lambda metrics: metrics.first_error_localization
        ),
        policy_compliance=_aggregate_metric(results, lambda metrics: metrics.policy_compliance),
        verifier_correctness=_aggregate_metric(
            results, lambda metrics: metrics.verifier_correctness
        ),
        checkpoint_recovery=_aggregate_metric(results, lambda metrics: metrics.checkpoint_recovery),
        interrupt_resume_success=_aggregate_metric(
            results, lambda metrics: metrics.interrupt_resume_success
        ),
        multimodal_transcription=_aggregate_metric(
            results, lambda metrics: metrics.multimodal_transcription
        ),
        multimodal_formula_transcription=_aggregate_metric(
            results, lambda metrics: metrics.multimodal_formula_transcription
        ),
        multimodal_provenance=_aggregate_metric(
            results, lambda metrics: metrics.multimodal_provenance
        ),
        multimodal_structure=_aggregate_metric(
            results, lambda metrics: metrics.multimodal_structure
        ),
        answer_leakage_applicable_cases=len(leakage_values),
        answer_leakage_cases=leakage_cases,
        answer_leakage_rate=(leakage_cases / len(leakage_values) if leakage_values else None),
        latency_ms=_distribution(result.latency_ms for result in results),
        token_count=_distribution(result.token_count for result in results),
        token_cost_usd=_distribution(result.token_cost_usd for result in results),
        agent_calls=_distribution(result.agent_calls for result in results),
    )


def evaluate_dataset(dataset: EvaluationDataset) -> EvaluationReport:
    """Evaluate every captured case and aggregate present variants in B0-B4 order."""

    case_results = [evaluate_case(case) for case in dataset.cases]
    variants = [
        aggregate_variant(variant, [result for result in case_results if result.variant == variant])
        for variant in EvaluationVariant
        if any(result.variant == variant for result in case_results)
    ]
    return EvaluationReport(
        schema_version=dataset.schema_version,
        dataset_id=dataset.dataset_id,
        case_results=case_results,
        variants=variants,
    )
