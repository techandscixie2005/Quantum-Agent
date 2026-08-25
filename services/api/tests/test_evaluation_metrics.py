from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantum_agent.evaluation import (
    BoundingBox,
    CitationObservation,
    ClaimObservation,
    CoverageLabel,
    DiagnosisExpectation,
    DiagnosisObservation,
    EvaluationCase,
    EvaluationDataset,
    EvaluationVariant,
    ExpectedCitation,
    ExpectedOutcome,
    HintLevel,
    MultimodalExpectation,
    MultimodalKind,
    MultimodalObservation,
    ObservedOutcome,
    PolicyExpectation,
    PolicyObservation,
    ProvenanceLocator,
    VerifierExpectation,
    VerifierObservation,
    VerifierVerdict,
    build_offline_fixture,
    evaluate_case,
    evaluate_dataset,
)


def _locator(*, page: int = 4, bbox: BoundingBox | None = None) -> ProvenanceLocator:
    return ProvenanceLocator(
        document_id="course-notes",
        document_version="v2",
        page_number=page,
        section="Spin measurements",
        bbox=bbox,
    )


def _case(
    *,
    expected: ExpectedOutcome,
    observed: ObservedOutcome,
    variant: EvaluationVariant = EvaluationVariant.B2,
) -> EvaluationCase:
    return EvaluationCase(
        case_id="case-1",
        scenario_id="scenario-1",
        variant=variant,
        expected=expected,
        observed=observed,
    )


def _observed(**overrides: object) -> ObservedOutcome:
    values: dict[str, object] = {
        "latency_ms": 100,
        "token_count": 50,
        "token_cost_usd": 0.0005,
        "agent_calls": 1,
    }
    values.update(overrides)
    return ObservedOutcome.model_validate(values)


def test_citation_correctness_penalizes_missing_invented_and_wrong_locator() -> None:
    first = ExpectedCitation(
        citation_id="c1",
        excerpt="A spin-half measurement has two possible outcomes.",
        locator=_locator(),
        supported_claims=["A spin-half measurement has two outcomes."],
    )
    second = ExpectedCitation(
        citation_id="c2",
        excerpt="The probabilities sum to one.",
        locator=_locator(page=5),
    )
    case = _case(
        expected=ExpectedOutcome(citations=[first, second]),
        observed=_observed(
            citations=[
                CitationObservation(citation_id="c1", locator=_locator()),
                CitationObservation(citation_id="c2", locator=_locator(page=99)),
            ],
            claims=[
                ClaimObservation(
                    text="A spin-half measurement has two outcomes.", citation_ids=["c1"]
                ),
                ClaimObservation(text="All outcomes are equally likely.", citation_ids=["c2"]),
            ],
        ),
    )

    result = evaluate_case(case)

    assert result.metrics.citation_correctness.score == pytest.approx(0.5)
    assert result.metrics.citation_correctness.passed is False
    assert result.metrics.citation_support.score == pytest.approx(0.5)


def test_coverage_diagnosis_prerequisite_and_first_error_metrics_are_independent() -> None:
    case = _case(
        expected=ExpectedOutcome(
            coverage=CoverageLabel.PARTIAL,
            diagnosis=DiagnosisExpectation(
                target_concepts=["spin", "basis"],
                misconception_labels=["basis confusion"],
                missing_prerequisites=["inner product"],
                first_error_applicable=True,
                first_error_step=2,
            ),
        ),
        observed=_observed(
            coverage=CoverageLabel.PARTIAL,
            diagnosis=DiagnosisObservation(
                target_concepts=["spin"],
                misconception_labels=["basis confusion"],
                missing_prerequisites=["inner product"],
                first_error_step=2,
            ),
        ),
    )

    metrics = evaluate_case(case).metrics

    assert metrics.coverage_calibration.score == 1
    assert metrics.diagnosis_accuracy.score == pytest.approx((2 / 3 + 1) / 2)
    assert metrics.diagnosis_accuracy.passed is False
    assert metrics.missing_prerequisite_accuracy.score == 1
    assert metrics.first_error_localization.score == 1


def test_policy_metric_detects_hint_and_fragment_leakage() -> None:
    case = _case(
        expected=ExpectedOutcome(
            policy=PolicyExpectation(
                maximum_hint_level=HintLevel.H2,
                forbidden_answer_fragments=["final coefficient is 1/sqrt(2)"],
            )
        ),
        observed=_observed(
            policy=PolicyObservation(
                hint_level=HintLevel.H3,
                released_full_solution=True,
                response_text="Therefore the final coefficient is 1/sqrt(2).",
            )
        ),
    )

    metrics = evaluate_case(case).metrics

    assert metrics.policy_compliance.score == 0
    assert metrics.answer_leakage_detected is True
    assert metrics.leakage_reasons == [
        "full_solution_released",
        "forbidden_fragment:final coefficient is 1/sqrt(2)",
    ]


def test_missing_policy_observation_fails_compliance_without_claiming_no_leakage() -> None:
    case = _case(
        expected=ExpectedOutcome(
            policy=PolicyExpectation(maximum_hint_level=HintLevel.H2)
        ),
        observed=_observed(),
    )

    metrics = evaluate_case(case).metrics

    assert metrics.policy_compliance.score == 0
    assert metrics.answer_leakage_detected is None


def test_verifier_metric_preserves_inconclusive_tool_result() -> None:
    case = _case(
        expected=ExpectedOutcome(
            verifier=VerifierExpectation(verdict=VerifierVerdict.INCONCLUSIVE)
        ),
        observed=_observed(
            verifier=VerifierObservation(
                tool_verdict=VerifierVerdict.INCONCLUSIVE,
                response_verdict=VerifierVerdict.PASS,
            )
        ),
    )

    metric = evaluate_case(case).metrics.verifier_correctness

    assert metric.applicable is True
    assert metric.score == 0
    assert "INCONCLUSIVE" in metric.detail


def test_checkpoint_and_interrupt_require_same_thread_resume() -> None:
    case = _case(
        expected=ExpectedOutcome(
            checkpoint_recovery_required=True,
            interrupt_resume_required=True,
        ),
        observed=_observed(
            checkpoint_recovered=True,
            interrupt_triggered=True,
            interrupt_resumed=True,
            interrupt_same_thread=False,
        ),
    )

    metrics = evaluate_case(case).metrics

    assert metrics.checkpoint_recovery.score == 1
    assert metrics.interrupt_resume_success.score == 0


def test_multimodal_transcription_formula_structure_and_locator_are_scored() -> None:
    bbox = BoundingBox(x_min=10, y_min=20, x_max=200, y_max=100)
    expected_locator = _locator(page=7, bbox=bbox)
    case = _case(
        expected=ExpectedOutcome(
            multimodal=MultimodalExpectation(
                kind=MultimodalKind.HANDWRITTEN_DERIVATION,
                transcription="psi equals A sine x",
                formulas=["\\psi=A\\sin(x)"],
                derivation_step_count=2,
                concepts=["normalization"],
                axis_labels=["x", "psi"],
                provenance=expected_locator,
                ambiguous=True,
            )
        ),
        observed=_observed(
            multimodal=MultimodalObservation(
                transcription="psi equals A sine x",
                formulas=["\\psi = A \\sin(x)"],
                derivation_step_count=2,
                concepts=["normalization"],
                axis_labels=["psi", "x"],
                provenance=expected_locator,
                confidence=0.55,
                confirmation_requested=True,
            )
        ),
    )

    metrics = evaluate_case(case).metrics

    assert metrics.multimodal_transcription.score == 1
    assert metrics.multimodal_formula_transcription.score == 1
    assert metrics.multimodal_provenance.score == 1
    assert metrics.multimodal_structure.score == 1


def test_multimodal_provenance_reports_partial_field_accuracy() -> None:
    case = _case(
        expected=ExpectedOutcome(
            multimodal=MultimodalExpectation(
                kind=MultimodalKind.LECTURE_SCREENSHOT,
                provenance=ProvenanceLocator(document_id="lecture-3", slide_number=8),
            )
        ),
        observed=_observed(
            multimodal=MultimodalObservation(
                provenance=ProvenanceLocator(document_id="lecture-3", slide_number=9)
            )
        ),
    )

    metric = evaluate_case(case).metrics.multimodal_provenance

    assert metric.score == pytest.approx(0.5)
    assert metric.denominator == 2


def test_offline_fixture_produces_real_b0_b4_aggregates() -> None:
    report = evaluate_dataset(build_offline_fixture())

    assert [aggregate.variant for aggregate in report.variants] == list(EvaluationVariant)
    by_variant = {aggregate.variant: aggregate for aggregate in report.variants}
    assert by_variant[EvaluationVariant.B0].answer_leakage_rate == 1
    assert by_variant[EvaluationVariant.B0].coverage_calibration.mean_score == 0
    assert by_variant[EvaluationVariant.B3].diagnosis_accuracy.mean_score == 1
    assert by_variant[EvaluationVariant.B4].case_count == 3
    assert by_variant[EvaluationVariant.B4].interrupt_resume_success.pass_rate == 1
    assert by_variant[EvaluationVariant.B4].multimodal_transcription.mean_score == 1
    assert by_variant[EvaluationVariant.B4].latency_ms.p95 == 1450
    assert by_variant[EvaluationVariant.B4].agent_calls.total == 9


def test_contracts_reject_duplicate_cases_citations_and_unknown_fields() -> None:
    case = _case(expected=ExpectedOutcome(), observed=_observed())
    with pytest.raises(ValidationError, match="evaluation case ids must be unique"):
        EvaluationDataset(dataset_id="duplicate", cases=[case, case])

    with pytest.raises(ValidationError, match="expected citation ids must be unique"):
        ExpectedOutcome(
            citations=[
                ExpectedCitation(citation_id="same", excerpt="one", locator=_locator()),
                ExpectedCitation(citation_id="same", excerpt="two", locator=_locator()),
            ]
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationDataset.model_validate(
            {
                "dataset_id": "invalid",
                "cases": [case.model_dump(mode="json")],
                "model_name": "must-not-be-routed-by-evaluator",
            }
        )
