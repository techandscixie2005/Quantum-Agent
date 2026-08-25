"""Fail-closed admission of student attachments into the tutor workflow.

Perception output is untrusted student context, never authoritative course
evidence.  This boundary performs scope checks, validates persisted JSON back
through the typed contracts, and admits only successful or explicitly
confirmed extraction.  Confirmation-required evidence may be checkpointed for
HITL inspection, but is never copied into the diagnosis attempt.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import CourseActor
from quantum_agent.db_models import (
    AttachmentKind,
    AttachmentStatus,
    MultimodalExtraction,
    MultimodalExtractionKind,
    MultimodalExtractionStatus,
    UserAttachment,
)
from quantum_agent.multimodal.contracts import (
    ConfirmationState,
    ConfirmedEvidence,
    DerivationStep,
    DocumentEvidence,
    VisualEvidence,
)
from quantum_agent.science import SymbolicEquivalenceRequest

if TYPE_CHECKING:
    from quantum_agent.teaching.models import TeachingTurnInput

_EVIDENCE_ADAPTER: TypeAdapter[ConfirmedEvidence] = TypeAdapter(ConfirmedEvidence)
_MAX_ATTEMPT_CHARACTERS = 12_000
_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_ALLOWED_FUNCTIONS = frozenset(
    {
        "Abs",
        "acos",
        "asin",
        "atan",
        "conjugate",
        "cos",
        "cosh",
        "exp",
        "im",
        "log",
        "re",
        "sin",
        "sinh",
        "sqrt",
        "tan",
        "tanh",
    }
)
_KNOWN_CONSTANTS = frozenset({"pi", "E", "I"})


class TeachingAttachmentNotFoundError(LookupError):
    """An opaque attachment id is unavailable in the authenticated scope."""


class TeachingAttachmentConflictError(RuntimeError):
    """An attachment exists but has no safely admissible extraction."""


class UnconfirmedPerceptionError(TeachingAttachmentConflictError):
    """Ambiguous perception requires HITL before tutor use."""


class PerceptionTraceEntry(BaseModel):
    """Small, serializable provenance record carried through checkpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attachment_id: UUID
    extraction_id: UUID
    evidence_type: Literal["visual", "document"]
    extraction_status: MultimodalExtractionStatus
    confidence: float = Field(ge=0, le=1)
    confirmation_state: ConfirmationState
    admitted_to_diagnosis: bool
    exact_context_characters: int = Field(default=0, ge=0, le=_MAX_ATTEMPT_CHARACTERS)
    context_truncated: bool = False
    scientific_request_derived: bool = False
    scientific_derivation_ordinals: tuple[int, int] | None = None
    confirmed_ambiguity_resolutions: dict[str, str] = Field(
        default_factory=dict,
        max_length=100,
    )
    confirmation_source: Literal[
        "pending", "not_required", "attachment_api", "teaching_hitl"
    ]

    @model_validator(mode="after")
    def scientific_pair_matches_flag(self) -> Self:
        if self.scientific_request_derived != (
            self.scientific_derivation_ordinals is not None
        ):
            raise ValueError("scientific derivation pair and derived flag disagree")
        for ambiguity_id, resolution in self.confirmed_ambiguity_resolutions.items():
            if not ambiguity_id or len(ambiguity_id) > 160:
                raise ValueError("ambiguity-resolution ids must be 1-160 characters")
            if not resolution.strip() or len(resolution) > 4_000:
                raise ValueError(
                    "ambiguity resolutions must be nonblank and at most 4000 characters"
                )
        return self


@dataclass(frozen=True, slots=True)
class ResolvedTeachingAttachments:
    """Validated effective request plus checkpoint-safe perception context."""

    request: TeachingTurnInput
    multimodal_evidence: tuple[ConfirmedEvidence, ...] = ()
    perception_trace: tuple[PerceptionTraceEntry, ...] = ()
    has_unconfirmed_evidence: bool = False


def _confirmed_evidence(extraction: MultimodalExtraction) -> ConfirmedEvidence:
    payload: object = extraction.evidence_json
    corrected = extraction.confirmation_json.get("corrected_evidence")
    if extraction.status is MultimodalExtractionStatus.CONFIRMED and corrected is not None:
        payload = corrected
    try:
        evidence = _EVIDENCE_ADAPTER.validate_python(payload)
    except (ValidationError, ValueError, TypeError) as error:
        raise TeachingAttachmentConflictError(
            "attachment extraction failed its typed evidence contract"
        ) from error

    if extraction.status is MultimodalExtractionStatus.CONFIRMED:
        evidence = _EVIDENCE_ADAPTER.validate_python(
            {
                **evidence.model_dump(mode="python"),
                "confirmation_state": ConfirmationState.CONFIRMED,
                "requires_confirmation": False,
            }
        )
    return evidence


def _validate_binding(
    attachment: UserAttachment,
    extraction: MultimodalExtraction,
    evidence: ConfirmedEvidence,
) -> None:
    if evidence.attachment_id != attachment.id:
        raise TeachingAttachmentConflictError("extraction is bound to another attachment")
    if evidence.original_file_reference != f"attachment:{attachment.id}":
        raise TeachingAttachmentConflictError("extraction has an invalid original-file reference")
    expected_kind = (
        MultimodalExtractionKind.VISION
        if isinstance(evidence, VisualEvidence)
        else MultimodalExtractionKind.DOCUMENT
    )
    if extraction.kind is not expected_kind:
        raise TeachingAttachmentConflictError("extraction kind conflicts with typed evidence")
    if isinstance(evidence, VisualEvidence) and attachment.kind is not AttachmentKind.IMAGE:
        raise TeachingAttachmentConflictError("visual evidence is not backed by an image")
    if isinstance(evidence, DocumentEvidence) and attachment.kind is AttachmentKind.IMAGE:
        raise TeachingAttachmentConflictError("document evidence is not backed by a document")


def _context_for(
    evidence: ConfirmedEvidence,
    ambiguity_resolutions: dict[str, str],
) -> str:
    if isinstance(evidence, VisualEvidence):
        if evidence.derivation_steps:
            original = "\n".join(step.source_text for step in evidence.derivation_steps)
        elif evidence.equations:
            original = "\n".join(equation.source_text for equation in evidence.equations)
        else:
            original = evidence.detected_text
    else:
        original = "\n".join(unit.exact_text for unit in evidence.units if unit.exact_text)
    if not ambiguity_resolutions:
        return original
    resolution_text = "\n".join(
        f"{ambiguity_id}: {resolution}"
        for ambiguity_id, resolution in ambiguity_resolutions.items()
    )
    separator = "\n" if original else ""
    return (
        f"{original}{separator}[Student-confirmed ambiguity resolutions; "
        f"attachment={evidence.attachment_id}]\n{resolution_text}\n"
        "[End student-confirmed ambiguity resolutions]"
    )


def _bounded_attempt(
    original: str | None,
    evidence_with_trace: list[tuple[ConfirmedEvidence, PerceptionTraceEntry]],
) -> tuple[str | None, list[PerceptionTraceEntry]]:
    parts: list[str] = []
    remaining = _MAX_ATTEMPT_CHARACTERS
    if original:
        exact = original[:remaining]
        parts.append(exact)
        remaining -= len(exact)

    traces: list[PerceptionTraceEntry] = []
    for evidence, trace in evidence_with_trace:
        context = _context_for(evidence, trace.confirmed_ambiguity_resolutions)
        if not context or remaining <= 0:
            traces.append(trace)
            continue
        separator = "\n\n" if parts else ""
        marker = (
            f"[Untrusted {evidence.evidence_type} transcription; "
            f"attachment={evidence.attachment_id}]\n"
        )
        available = max(0, remaining - len(separator) - len(marker))
        exact = context[:available]
        if exact:
            parts.append(f"{separator}{marker}{exact}")
            remaining -= len(separator) + len(marker) + len(exact)
        traces.append(
            trace.model_copy(
                update={
                    "admitted_to_diagnosis": bool(exact),
                    "exact_context_characters": len(exact),
                    "context_truncated": len(exact) < len(context),
                }
            )
        )
    combined = "".join(parts).strip()
    return combined or None, traces


def _normalize_expression(source: str) -> tuple[str, set[str]] | None:
    if not source or len(source) > 1_024 or not source.isascii():
        return None
    normalized = "".join(source.split()).replace("^", "**")
    if not normalized or any(token in normalized for token in ("\\", "{", "}", "'", '"')):
        return None
    try:
        parsed = ast.parse(normalized, mode="eval")
    except (SyntaxError, ValueError, MemoryError):
        return None

    names: set[str] = set()
    nodes = list(ast.walk(parsed))
    try:
        too_deep = _ast_depth(parsed) > 24
    except RecursionError:
        return None
    if len(nodes) > 128 or too_deep:
        return None
    call_nodes = [node for node in nodes if isinstance(node, ast.Call)]
    called_functions = {
        node.func.id
        for node in call_nodes
        if isinstance(node.func, ast.Name)
    }
    if len(call_nodes) > 12:
        return None
    for node in nodes:
        if isinstance(node, ast.Expression | ast.Load):
            continue
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                return None
            if abs(node.value) > 10**12:
                return None
            continue
        if isinstance(node, ast.Name):
            if not _SAFE_NAME.fullmatch(node.id):
                return None
            if node.id in _ALLOWED_FUNCTIONS and node.id not in called_functions:
                return None
            if node.id not in called_functions and node.id not in _KNOWN_CONSTANTS:
                names.add(node.id)
            continue
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, ast.UAdd | ast.USub):
                return None
            continue
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div | ast.Pow):
                return None
            if isinstance(node.op, ast.Pow):
                exponent = node.right
                sign = -1 if isinstance(exponent, ast.UnaryOp) else 1
                value = exponent.operand if isinstance(exponent, ast.UnaryOp) else exponent
                if not isinstance(value, ast.Constant) or not isinstance(value.value, int):
                    return None
                if not -12 <= sign * value.value <= 12:
                    return None
            continue
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _ALLOWED_FUNCTIONS
                or len(node.args) != 1
                or node.keywords
            ):
                return None
            continue
        if isinstance(node, ast.operator | ast.unaryop):
            continue
        return None
    if len(names) > 16:
        return None
    return normalized, names


def _ast_depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)


def _strip_line_label(left: str) -> str:
    """Remove a leading ``Label:`` such as ``Step 1:`` from the LHS.

    Only acts when the remainder after the label is a bare identifier or dotted
    name (the LHS of an equation), so an equation with a genuine ``:`` in the
    expression is never misread as a line label.
    """
    match = re.match(r"^[^=]{0,64}?:\s*([A-Za-z_][A-Za-z0-9_.]*)\s*$", left)
    if match is None:
        return left
    return match.group(1)


def _equation(step: DerivationStep) -> tuple[str, str] | None:
    for source in (step.source_text, step.latex):
        if source.count("=") != 1 or any(token in source for token in ("==", "<=", ">=")):
            continue
        left, right = source.split("=", 1)
        left = _strip_line_label(left)
        normalized_left = _normalize_expression(left)
        normalized_right = _normalize_expression(right)
        if normalized_left is not None and normalized_right is not None:
            return normalized_left[0], normalized_right[0]
    return None


def derive_scientific_request(
    evidence: tuple[ConfirmedEvidence, ...],
) -> tuple[SymbolicEquivalenceRequest | None, UUID | None, tuple[int, int] | None]:
    """Derive one verifier request only from an explicit safe adjacent equality."""

    for item in evidence:
        if (
            not isinstance(item, VisualEvidence)
            or item.requires_confirmation
            or item.ambiguities
        ):
            continue
        steps = item.derivation_steps
        for previous, current in pairwise(steps):
            previous_equation = _equation(previous)
            current_equation = _equation(current)
            if previous_equation is None or current_equation is None:
                continue
            previous_left, previous_right = previous_equation
            current_left, current_right = current_equation
            if previous_left != current_left or previous_right == current_right:
                continue
            parsed_previous = _normalize_expression(previous_right)
            parsed_current = _normalize_expression(current_right)
            if parsed_previous is None or parsed_current is None:
                continue
            symbols = tuple(sorted(parsed_previous[1] | parsed_current[1]))
            return (
                SymbolicEquivalenceRequest(
                    left=parsed_previous[0],
                    right=parsed_current[0],
                    symbols=symbols,
                ),
                item.attachment_id,
                (previous.ordinal, current.ordinal),
            )
    return None, None, None


def _ambiguity_resolutions(extraction: MultimodalExtraction) -> dict[str, str]:
    """Validate and preserve explicit attachment-API resolutions verbatim."""

    if extraction.confirmation_json.get("corrected_evidence") is not None:
        return {}
    raw = extraction.confirmation_json.get("ambiguity_resolutions", {})
    if not isinstance(raw, dict):
        raise TeachingAttachmentConflictError(
            "attachment confirmation has malformed ambiguity resolutions"
        )
    resolutions: dict[str, str] = {}
    for ambiguity_id, resolution in raw.items():
        if not isinstance(ambiguity_id, str) or not isinstance(resolution, str):
            raise TeachingAttachmentConflictError(
                "attachment confirmation has malformed ambiguity resolutions"
            )
        resolutions[ambiguity_id] = resolution
    try:
        # Reuse the checkpoint contract for the exact key/value constraints.
        PerceptionTraceEntry(
            attachment_id=extraction.attachment_id,
            extraction_id=extraction.id,
            evidence_type=(
                "visual"
                if extraction.kind is MultimodalExtractionKind.VISION
                else "document"
            ),
            extraction_status=extraction.status,
            confidence=extraction.confidence or 0,
            confirmation_state=ConfirmationState.CONFIRMED,
            admitted_to_diagnosis=False,
            confirmation_source="attachment_api",
            confirmed_ambiguity_resolutions=resolutions,
        )
    except ValidationError as error:
        raise TeachingAttachmentConflictError(
            "attachment confirmation has invalid ambiguity resolutions"
        ) from error
    return resolutions


async def resolve_teaching_attachments(
    session: AsyncSession,
    *,
    actor: CourseActor,
    curriculum_edition_id: UUID,
    request: TeachingTurnInput,
) -> ResolvedTeachingAttachments:
    """Resolve opaque ids without leaking cross-account attachment existence."""

    if not request.attachment_ids:
        return ResolvedTeachingAttachments(request=request)

    attachments = list(
        await session.scalars(
            select(UserAttachment).where(
                UserAttachment.id.in_(request.attachment_ids),
                UserAttachment.course_id == actor.course_id,
                UserAttachment.curriculum_edition_id == curriculum_edition_id,
                UserAttachment.owner_user_id == actor.user_id,
                UserAttachment.status == AttachmentStatus.READY,
            )
        )
    )
    by_id = {attachment.id: attachment for attachment in attachments}
    if len(by_id) != len(request.attachment_ids):
        raise TeachingAttachmentNotFoundError(
            "one or more attachments are unavailable in this course scope"
        )

    rows = list(
        await session.scalars(
            select(MultimodalExtraction)
            .where(
                MultimodalExtraction.attachment_id.in_(request.attachment_ids),
                MultimodalExtraction.course_id == actor.course_id,
                MultimodalExtraction.curriculum_edition_id == curriculum_edition_id,
                MultimodalExtraction.owner_user_id == actor.user_id,
            )
            .order_by(
                MultimodalExtraction.attachment_id,
                MultimodalExtraction.created_at.desc(),
                MultimodalExtraction.id.desc(),
            )
        )
    )
    latest: dict[UUID, MultimodalExtraction] = {}
    for extraction in rows:
        latest.setdefault(extraction.attachment_id, extraction)
    if any(attachment_id not in latest for attachment_id in request.attachment_ids):
        raise TeachingAttachmentConflictError("attachment extraction is not available")

    evidence_items: list[ConfirmedEvidence] = []
    trace_pairs: list[tuple[ConfirmedEvidence, PerceptionTraceEntry]] = []
    base_traces: dict[UUID, PerceptionTraceEntry] = {}
    pending = False
    for attachment_id in request.attachment_ids:
        attachment = by_id[attachment_id]
        extraction = latest[attachment_id]
        if extraction.status not in {
            MultimodalExtractionStatus.SUCCEEDED,
            MultimodalExtractionStatus.CONFIRMED,
            MultimodalExtractionStatus.NEEDS_CONFIRMATION,
        }:
            raise TeachingAttachmentConflictError("attachment extraction is not usable")
        evidence = _confirmed_evidence(extraction)
        _validate_binding(attachment, extraction, evidence)
        is_pending = extraction.status is MultimodalExtractionStatus.NEEDS_CONFIRMATION
        if is_pending != evidence.requires_confirmation:
            raise TeachingAttachmentConflictError(
                "extraction status conflicts with its confirmation contract"
            )
        if extraction.requires_confirmation != is_pending:
            raise TeachingAttachmentConflictError(
                "persisted extraction confirmation state is inconsistent"
            )
        pending = pending or is_pending
        evidence_items.append(evidence)
        confirmation_source: Literal[
            "pending", "not_required", "attachment_api", "teaching_hitl"
        ]
        if is_pending:
            confirmation_source = "pending"
        elif extraction.status is MultimodalExtractionStatus.CONFIRMED:
            confirmation_source = "attachment_api"
        else:
            confirmation_source = "not_required"
        trace = PerceptionTraceEntry(
            attachment_id=attachment_id,
            extraction_id=extraction.id,
            evidence_type=evidence.evidence_type,
            extraction_status=extraction.status,
            confidence=evidence.confidence,
            confirmation_state=evidence.confirmation_state,
            admitted_to_diagnosis=False,
            confirmation_source=confirmation_source,
            confirmed_ambiguity_resolutions=(
                _ambiguity_resolutions(extraction)
                if extraction.status is MultimodalExtractionStatus.CONFIRMED
                else {}
            ),
        )
        base_traces[attachment_id] = trace
        if not is_pending:
            trace_pairs.append((evidence, trace))

    attempt, admitted_traces = _bounded_attempt(request.student_attempt, trace_pairs)
    trace_by_attachment = {trace.attachment_id: trace for trace in admitted_traces}
    all_traces = [
        trace_by_attachment.get(item.attachment_id, base_traces[item.attachment_id])
        for item in evidence_items
    ]

    derived = request.scientific_request
    if derived is None:
        derived_request, derived_attachment_id, ordinals = derive_scientific_request(
            tuple(item for item in evidence_items if not item.requires_confirmation)
        )
        derived = derived_request
        if derived_attachment_id is not None and ordinals is not None:
            all_traces = [
                trace.model_copy(
                    update={
                        "scientific_request_derived": trace.attachment_id
                        == derived_attachment_id,
                        "scientific_derivation_ordinals": (
                            ordinals if trace.attachment_id == derived_attachment_id else None
                        ),
                    }
                )
                for trace in all_traces
            ]

    effective = type(request).model_validate(
        {
            **request.model_dump(mode="python"),
            "student_attempt": attempt,
            "scientific_request": derived,
        }
    )
    return ResolvedTeachingAttachments(
        request=effective,
        multimodal_evidence=tuple(evidence_items),
        perception_trace=tuple(all_traces),
        has_unconfirmed_evidence=pending,
    )


def confirm_checkpoint_perception(
    evidence: list[ConfirmedEvidence],
    traces: list[PerceptionTraceEntry],
    confirmed_student_attempt: str,
) -> tuple[list[ConfirmedEvidence], list[PerceptionTraceEntry]]:
    """Replace ambiguous OCR with exact student-confirmed text in checkpoint state."""

    pending_indexes = [index for index, item in enumerate(evidence) if item.requires_confirmation]
    target_index = next(
        (
            index
            for index in pending_indexes
            if isinstance(evidence[index], VisualEvidence)
        ),
        pending_indexes[0] if pending_indexes else None,
    )
    result: list[ConfirmedEvidence] = []
    for index, item in enumerate(evidence):
        if index not in pending_indexes:
            result.append(item)
            continue
        if isinstance(item, VisualEvidence):
            text = confirmed_student_attempt if index == target_index else ""
            lines = [line for line in text.splitlines() if line.strip()]
            steps = tuple(
                DerivationStep(
                    ordinal=ordinal,
                    source_text=line,
                    latex=line,
                    confidence=1.0,
                )
                for ordinal, line in enumerate(lines, start=1)
            )
            result.append(
                _EVIDENCE_ADAPTER.validate_python(
                    {
                        **item.model_dump(mode="python"),
                        "detected_text": text,
                        "equations": (),
                        "derivation_steps": steps,
                        "diagram_interpretation": None,
                        "plot_axes": (),
                        "plot_interpretation": None,
                        "figure_description": None,
                        "bounding_boxes": (),
                        "ambiguities": (),
                        "confirmation_state": ConfirmationState.CONFIRMED,
                        "requires_confirmation": False,
                    }
                )
            )
        else:
            result.append(
                _EVIDENCE_ADAPTER.validate_python(
                    {
                        **item.model_dump(mode="python"),
                        "units": (),
                        "ambiguities": (),
                        "confirmation_state": ConfirmationState.CONFIRMED,
                        "requires_confirmation": False,
                    }
                )
            )

    trace_by_id = {trace.attachment_id: trace for trace in traces}
    target_attachment_id = (
        evidence[target_index].attachment_id if target_index is not None else None
    )
    updated_traces: list[PerceptionTraceEntry] = []
    for item in result:
        trace = trace_by_id[item.attachment_id]
        if trace.confirmation_state is ConfirmationState.REQUIRED:
            is_target = item.attachment_id == target_attachment_id
            trace = PerceptionTraceEntry.model_validate(
                {
                    **trace.model_dump(mode="python"),
                    "confirmation_state": ConfirmationState.CONFIRMED,
                    "admitted_to_diagnosis": is_target,
                    "exact_context_characters": (
                        len(confirmed_student_attempt) if is_target else 0
                    ),
                    "context_truncated": False,
                    "confirmation_source": "teaching_hitl",
                }
            )
        updated_traces.append(trace)
    return result, updated_traces


__all__ = [
    "PerceptionTraceEntry",
    "ResolvedTeachingAttachments",
    "TeachingAttachmentConflictError",
    "TeachingAttachmentNotFoundError",
    "UnconfirmedPerceptionError",
    "confirm_checkpoint_perception",
    "derive_scientific_request",
    "resolve_teaching_attachments",
]
