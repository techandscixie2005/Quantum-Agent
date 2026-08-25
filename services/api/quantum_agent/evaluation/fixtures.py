"""Small deterministic fixture for offline B0-B4 regression checks.

This fixture is intentionally not presented as the production 200-case golden
set.  It exercises every calculator without external services and gives CI a
stable, non-placeholder architecture report.
"""

from __future__ import annotations

from quantum_agent.evaluation.models import (
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
)


def _course_locator() -> ProvenanceLocator:
    return ProvenanceLocator(
        document_id="griffiths-introduction-qm",
        document_version="3e-course-release",
        page_number=12,
        section="1.2 The Statistical Interpretation",
        paragraph_index=2,
        bbox=BoundingBox(x_min=72, y_min=180, x_max=515, y_max=246),
    )


def _citation() -> ExpectedCitation:
    return ExpectedCitation(
        citation_id="griffiths-p12-c4",
        excerpt="The probability density is |psi|^2 and the wave function must be normalized.",
        locator=_course_locator(),
        supported_claims=["The probability density is |psi|^2."],
    )


def _expected(*, checkpoint: bool, interrupt: bool = False) -> ExpectedOutcome:
    return ExpectedOutcome(
        citations=[_citation()],
        coverage=CoverageLabel.SUFFICIENT,
        diagnosis=DiagnosisExpectation(
            target_concepts=["wavefunction normalization"],
            misconception_labels=["probability amplitude treated as probability"],
            missing_prerequisites=["Born rule"],
            first_error_applicable=True,
            first_error_step=1,
        ),
        policy=PolicyExpectation(
            maximum_hint_level=HintLevel.H2,
            forbidden_answer_fragments=["psi = 1/sqrt(L)"],
        ),
        verifier=VerifierExpectation(verdict=VerifierVerdict.FAIL),
        checkpoint_recovery_required=checkpoint,
        interrupt_resume_required=interrupt,
    )


def _observed(
    *,
    citation: bool,
    supported_claim: bool,
    coverage: CoverageLabel,
    diagnosis: DiagnosisObservation | None,
    policy: PolicyObservation,
    response_verdict: VerifierVerdict,
    latency_ms: float,
    tokens: int,
    cost: float,
    agent_calls: int,
    checkpoint_recovered: bool | None,
    interrupt: bool = False,
) -> ObservedOutcome:
    citation_observations = (
        [CitationObservation(citation_id="griffiths-p12-c4", locator=_course_locator())]
        if citation
        else []
    )
    claims = (
        [
            ClaimObservation(
                text=(
                    "The probability density is |psi|^2."
                    if supported_claim
                    else "Every normalized state has zero energy."
                ),
                citation_ids=["griffiths-p12-c4"] if citation else [],
            )
        ]
        if supported_claim or citation
        else []
    )
    return ObservedOutcome(
        citations=citation_observations,
        claims=claims,
        coverage=coverage,
        diagnosis=diagnosis,
        policy=policy,
        verifier=VerifierObservation(
            tool_verdict=VerifierVerdict.FAIL,
            response_verdict=response_verdict,
        ),
        latency_ms=latency_ms,
        token_count=tokens,
        token_cost_usd=cost,
        agent_calls=agent_calls,
        checkpoint_recovered=checkpoint_recovered,
        interrupt_triggered=interrupt,
        interrupt_resumed=interrupt,
        interrupt_same_thread=interrupt,
    )


def _architecture_cases() -> list[EvaluationCase]:
    correct_diagnosis = DiagnosisObservation(
        target_concepts=["wavefunction normalization"],
        misconception_labels=["probability amplitude treated as probability"],
        missing_prerequisites=["Born rule"],
        first_error_step=1,
    )
    partial_diagnosis = DiagnosisObservation(
        target_concepts=["wavefunction normalization"],
        misconception_labels=[],
        missing_prerequisites=[],
        first_error_step=2,
    )
    compliant_policy = PolicyObservation(
        hint_level=HintLevel.H2,
        response_text="Check what quantity must integrate to one before solving for the constant.",
    )
    return [
        EvaluationCase(
            case_id="normalization-b0",
            scenario_id="normalization-first-error",
            variant=EvaluationVariant.B0,
            expected=_expected(checkpoint=False),
            observed=_observed(
                citation=False,
                supported_claim=False,
                coverage=CoverageLabel.PARTIAL,
                diagnosis=DiagnosisObservation(
                    target_concepts=["energy eigenvalues"],
                    misconception_labels=[],
                    missing_prerequisites=[],
                    first_error_step=3,
                ),
                policy=PolicyObservation(
                    hint_level=HintLevel.H4,
                    released_full_solution=True,
                    response_text="The complete answer is psi = 1/sqrt(L).",
                ),
                response_verdict=VerifierVerdict.PASS,
                latency_ms=410,
                tokens=680,
                cost=0.0068,
                agent_calls=1,
                checkpoint_recovered=None,
            ),
            tags=["text", "baseline"],
        ),
        EvaluationCase(
            case_id="normalization-b1",
            scenario_id="normalization-first-error",
            variant=EvaluationVariant.B1,
            expected=_expected(checkpoint=True),
            observed=_observed(
                citation=True,
                supported_claim=True,
                coverage=CoverageLabel.SUFFICIENT,
                diagnosis=partial_diagnosis,
                policy=compliant_policy,
                response_verdict=VerifierVerdict.FAIL,
                latency_ms=520,
                tokens=720,
                cost=0.0072,
                agent_calls=1,
                checkpoint_recovered=True,
            ),
            tags=["text", "langgraph"],
        ),
        EvaluationCase(
            case_id="normalization-b2",
            scenario_id="normalization-first-error",
            variant=EvaluationVariant.B2,
            expected=_expected(checkpoint=True),
            observed=_observed(
                citation=True,
                supported_claim=True,
                coverage=CoverageLabel.SUFFICIENT,
                diagnosis=partial_diagnosis,
                policy=compliant_policy,
                response_verdict=VerifierVerdict.FAIL,
                latency_ms=610,
                tokens=790,
                cost=0.0079,
                agent_calls=2,
                checkpoint_recovered=True,
            ),
            tags=["text", "evidence-agent"],
        ),
        EvaluationCase(
            case_id="normalization-b3",
            scenario_id="normalization-first-error",
            variant=EvaluationVariant.B3,
            expected=_expected(checkpoint=True),
            observed=_observed(
                citation=True,
                supported_claim=True,
                coverage=CoverageLabel.SUFFICIENT,
                diagnosis=correct_diagnosis,
                policy=compliant_policy,
                response_verdict=VerifierVerdict.FAIL,
                latency_ms=735,
                tokens=930,
                cost=0.0093,
                agent_calls=3,
                checkpoint_recovered=True,
            ),
            tags=["text", "diagnosis-agent"],
        ),
        EvaluationCase(
            case_id="normalization-b4",
            scenario_id="normalization-first-error",
            variant=EvaluationVariant.B4,
            expected=_expected(checkpoint=True, interrupt=True),
            observed=_observed(
                citation=True,
                supported_claim=True,
                coverage=CoverageLabel.SUFFICIENT,
                diagnosis=correct_diagnosis,
                policy=compliant_policy,
                response_verdict=VerifierVerdict.FAIL,
                latency_ms=820,
                tokens=1_010,
                cost=0.0101,
                agent_calls=4,
                checkpoint_recovered=True,
                interrupt=True,
            ),
            tags=["text", "specialist", "interrupt"],
        ),
    ]


def _multimodal_cases() -> list[EvaluationCase]:
    handwritten_locator = ProvenanceLocator(
        document_id="student-upload-handwriting-01",
        document_version="sha256:fixture",
        page_number=1,
        bbox=BoundingBox(x_min=40, y_min=65, x_max=960, y_max=720),
    )
    plot_locator = ProvenanceLocator(
        document_id="student-upload-rabi-plot-01",
        document_version="sha256:plot-fixture",
        page_number=1,
        figure_id="figure-1",
    )
    return [
        EvaluationCase(
            case_id="handwritten-derivation-b4",
            scenario_id="handwritten-normalization",
            variant=EvaluationVariant.B4,
            expected=ExpectedOutcome(
                policy=PolicyExpectation(maximum_hint_level=HintLevel.H2),
                verifier=VerifierExpectation(verdict=VerifierVerdict.FAIL),
                multimodal=MultimodalExpectation(
                    kind=MultimodalKind.HANDWRITTEN_DERIVATION,
                    transcription="psi(x)=A sin(pi x/L); integral |psi|^2 dx = A^2 L",
                    formulas=["psi(x)=A\\sin(\\pi x/L)", "\\int_0^L|psi|^2dx=A^2L"],
                    derivation_step_count=2,
                    concepts=["normalization"],
                    provenance=handwritten_locator,
                    ambiguous=True,
                ),
            ),
            observed=ObservedOutcome(
                policy=PolicyObservation(
                    hint_level=HintLevel.H1,
                    response_text="Recheck the integral of sine squared before isolating A.",
                ),
                verifier=VerifierObservation(
                    tool_verdict=VerifierVerdict.FAIL,
                    response_verdict=VerifierVerdict.FAIL,
                ),
                latency_ms=1_450,
                token_count=1_280,
                token_cost_usd=0.0128,
                agent_calls=3,
                multimodal=MultimodalObservation(
                    transcription="psi(x)=A sin(pi x/L); integral |psi|^2 dx = A^2 L",
                    formulas=["psi(x)=A\\sin(\\pi x/L)", "\\int_0^L|psi|^2dx=A^2L"],
                    derivation_step_count=2,
                    concepts=["normalization"],
                    provenance=handwritten_locator,
                    confidence=0.62,
                    confirmation_requested=True,
                ),
            ),
            tags=["handwriting", "formula", "confirmation"],
        ),
        EvaluationCase(
            case_id="simulation-plot-b4",
            scenario_id="rabi-plot-interpretation",
            variant=EvaluationVariant.B4,
            expected=ExpectedOutcome(
                multimodal=MultimodalExpectation(
                    kind=MultimodalKind.PLOT,
                    concepts=["Rabi oscillation"],
                    axis_labels=["time", "excited-state probability"],
                    provenance=plot_locator,
                    ambiguous=False,
                )
            ),
            observed=ObservedOutcome(
                latency_ms=980,
                token_count=610,
                token_cost_usd=0.0061,
                agent_calls=2,
                multimodal=MultimodalObservation(
                    concepts=["Rabi oscillation"],
                    axis_labels=["time", "excited-state probability"],
                    provenance=plot_locator,
                    confidence=0.94,
                    confirmation_requested=False,
                ),
            ),
            tags=["plot", "axes", "simulation"],
        ),
    ]


def build_offline_fixture() -> EvaluationDataset:
    """Return a deterministic dataset that exercises B0-B4 and multimodal metrics."""

    return EvaluationDataset(
        dataset_id="quantum-agent-v2.1-offline-smoke",
        cases=[*_architecture_cases(), *_multimodal_cases()],
    )
