"""Regression tests for safe-adjacent-equality normalization in derivations.

The live vision model emits ``source_text`` with a leading ``Step N:`` label and a
``latex`` field containing LaTeX escapes (``\\hbar``).  ``derive_scientific_request``
must still surface a SymbolicEquivalenceRequest for the safe ``E = ...`` pair while
never firing for genuinely unparseable latex (bra/ket, ``\\psi``).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from quantum_agent.multimodal.contracts import (
    ConfirmationState,
    DerivationStep,
    ExtractionMethod,
    VisualEvidence,
)
from quantum_agent.multimodal.teaching import _equation, derive_scientific_request


def _step(ordinal: int, source_text: str, latex: str, confidence: float = 0.95) -> DerivationStep:
    return DerivationStep(
        ordinal=ordinal,
        source_text=source_text,
        latex=latex,
        confidence=confidence,
    )


def _visual(
    steps: tuple[DerivationStep, ...],
    attachment_id: UUID,
) -> VisualEvidence:
    return VisualEvidence(
        attachment_id=attachment_id,
        original_file_reference=f"attachment:{attachment_id}",
        extraction_method=ExtractionMethod.QWEN_VISION,
        detected_text="\n".join(step.source_text for step in steps),
        derivation_steps=steps,
        confidence=0.95,
        ambiguities=(),
        confirmation_state=ConfirmationState.NOT_REQUIRED,
        requires_confirmation=False,
    )


def test_equation_strips_step_label_from_source_text() -> None:
    step = _step(
        1,
        "Step 1: E = hbar**2*k**2/(2*m)",
        r"E = \hbar^2 k^2 / (2 m)",
    )
    assert _equation(step) == ("E", "hbar**2*k**2/(2*m)")


def test_derive_scientific_request_surfaces_symbolic_equivalence_for_labeled_steps() -> None:
    attachment_id = uuid4()
    evidence = _visual(
        (
            _step(
                1,
                "Step 1: E = hbar**2*k**2/(2*m)",
                r"E = \hbar^2 k^2 / (2 m)",
            ),
            _step(
                2,
                "Step 2: E = hbar**2*k/(2*m)",
                r"E = \hbar^2 k / (2 m)",
            ),
        ),
        attachment_id,
    )
    request, derived_attachment_id, ordinals = derive_scientific_request((evidence,))
    assert request is not None
    assert request.kind.value == "symbolic_equivalence"
    assert derived_attachment_id == attachment_id
    assert ordinals == (1, 2)


def test_derive_scientific_request_ignores_unparseable_braket_latex() -> None:
    evidence = _visual(
        (
            _step(1, r"\psi = \alpha|0\rangle", r"\psi = \alpha|0\rangle"),
            _step(2, r"\psi = \beta|1\rangle", r"\psi = \beta|1\rangle"),
        ),
        uuid4(),
    )
    request, derived_attachment_id, ordinals = derive_scientific_request((evidence,))
    assert request is None
    assert derived_attachment_id is None
    assert ordinals is None


def test_equation_preserves_identifier_bearing_operator_colon() -> None:
    step = _step(1, "E = m*c^2", "E = m*c^2")
    assert _equation(step) == ("E", "m*c**2")
