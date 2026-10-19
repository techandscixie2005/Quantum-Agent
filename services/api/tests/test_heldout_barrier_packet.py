"""Offline scientific/traceability checks; the teacher packet is not classroom data."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType

import pytest

from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest, ScientificVerificationStatus

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "docs/teacher-packets/finite-barriers-heldout/1.0.0"
SCRIPT = ROOT / "scripts/verify-heldout-barriers.py"


@pytest.fixture(scope="module")
def reference_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("heldout_barrier_reference", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packet_manifest_covers_actual_bytes_and_separates_student_keys() -> None:
    manifest = json.loads((PACKET / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "unreviewed_no_classroom_results"
    assert manifest["teacher_approvals"] == []
    listed = {item["path"]: item for item in manifest["files"]}
    actual = {path.relative_to(PACKET).as_posix() for path in PACKET.rglob("*")
              if path.is_file() and path.name != "manifest.json"}
    assert set(listed) == actual
    for relative, item in listed.items():
        data = (PACKET / relative).read_bytes()
        assert item["sha256"] == hashlib.sha256(data).hexdigest()
        assert item["bytes"] == len(data)
        assert item["audience"] == ("student_question_form" if relative.startswith("student-forms/")
                                    else "teacher_or_operator")
    assert manifest["reference_script"]["sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    canonical = {key: manifest[key]
                 for key in ("packet_id", "version", "files", "reference_script")}
    assert manifest["packet_content_sha256"] == hashlib.sha256(json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    for path in (PACKET / "student-forms").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "teacher-only/answer-key" not in text
        assert "T=0.072499631" not in text


def test_high_precision_report_is_reproducible_and_covers_all_regimes(
    reference_script: ModuleType,
) -> None:
    saved = json.loads((PACKET / "teacher-only/reference-results.json").read_text(encoding="utf-8"))
    assert reference_script.report() == saved
    assert len(saved["cases"]) == 23
    assert {case["regime"] for case in saved["cases"]} == {"below", "equal", "above"}
    assert "NO CLASSROOM RESULTS" in saved["label"]
    for case in saved["cases"]:
        assert float(case["relative_reference_error"]) < 1e-80
        assert float(case["dimensionless_boundary_residual"]) < 1e-80
        assert float(case["conservation_error"]) < 1e-80


def test_threshold_two_sided_limit_and_unequal_channel_reciprocity(
    reference_script: ModuleType,
) -> None:
    # Independently important limits, using cases outside the student forms.
    base = {"case_id": "test-only", "energy_eV": "5", "height_eV": "5", "width_nm": ".2"}
    threshold = float(reference_script.check_case(base)["T"])
    for energy in ["4.999999999999", "5.000000000001"]:
        nearby = float(reference_script.check_case({**base, "energy_eV": energy})["T"])
        assert math.isclose(nearby, threshold, rel_tol=1e-11)
    forward = {**base, "energy_eV": "5", "height_eV": "9", "left_eV": "0", "right_eV": "2"}
    reverse = {**forward, "left_eV": "2", "right_eV": "0"}
    first = reference_script.check_case(forward)
    second = reference_script.check_case(reverse)
    assert math.isclose(float(first["T"]), float(second["T"]), rel_tol=1e-14)
    assert not math.isclose(float(first["amplitude_squared"]),
                            float(second["amplitude_squared"]), rel_tol=1e-3)
    transparent = reference_script.check_case({**base, "height_eV": "0"})
    assert float(transparent["T"]) == 1


def test_runtime_supported_packet_numbers_match_independent_reference_relatively() -> None:
    report = json.loads((PACKET / "teacher-only/reference-results.json").read_text(
        encoding="utf-8",
    ))
    supported = [case for case in report["cases"]
                 if case["runtime_support"] == "within_reference_parameter_scope"]
    assert len(supported) == 16
    toolbox = ScientificToolbox()
    for case in supported:
        inputs = case["inputs"]
        result = toolbox.verify(RectangularBarrierRequest(
            energy_eV=float(inputs["energy_eV"]), barrier_height_eV=float(inputs["height_eV"]),
            barrier_width_m=float(case["width_nm"]) * 1e-9, particle_mass_kg=9.1093837015e-31,
        ))
        assert result.status is ScientificVerificationStatus.PASS
        assert float(result.metrics["T"]) > 0
        assert math.isclose(float(result.metrics["T"]), float(case["T"]), rel_tol=1e-8, abs_tol=0)


def test_opaque_underflow_is_positive_in_reference_but_not_certified_by_runtime() -> None:
    report = json.loads((PACKET / "teacher-only/reference-results.json").read_text(
        encoding="utf-8",
    ))
    case = next(item for item in report["cases"]
                if item["runtime_support"] == "not_supported_opaque_float64_range")
    # The decimal reference is nonzero but cannot be represented by float64.
    assert not case["T"].startswith("0") and float(case["T"]) == 0
    assert float(case["log10_T"]) < -5000
    result = ScientificToolbox().verify(RectangularBarrierRequest(
        energy_eV=float(case["inputs"]["energy_eV"]),
        barrier_height_eV=float(case["inputs"]["height_eV"]),
        barrier_width_m=float(case["width_nm"]) * 1e-9, particle_mass_kg=9.1093837015e-31,
    ))
    assert result.status is ScientificVerificationStatus.INCONCLUSIVE
    assert "T" not in result.metrics
