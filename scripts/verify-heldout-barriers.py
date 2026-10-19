"""Offline high-precision checks for the unreviewed teacher-only barrier packet.

No runtime oracle, prompt, provider, or classroom record is imported. Two
independently expressed solutions are checked: interface matching and the
closed transfer amplitude, including the linear E=V0 interior solution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import mpmath as mp  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "docs/teacher-packets/finite-barriers-heldout/1.0.0"


def check_case(case: dict[str, Any]) -> dict[str, Any]:
    with mp.workdps(100):
        electron_volt = mp.mpf("1.602176634e-19")
        hbar = mp.mpf("1.054571817e-34")
        mass = mp.mpf("9.1093837015e-31")
        energy = mp.mpf(case["energy_eV"])
        height = mp.mpf(case["height_eV"])
        left = mp.mpf(case.get("left_eV", "0"))
        right = mp.mpf(case.get("right_eV", "0"))
        if min(energy - left, energy - right) <= 0:
            raise ValueError("packet cases require propagating asymptotic channels")
        k_left = mp.sqrt(2 * mass * (energy - left) * electron_volt) / hbar
        k_right = mp.sqrt(2 * mass * (energy - right) * electron_volt) / hbar
        q = mp.sqrt(2 * mass * (energy - height) * electron_volt) / hbar
        width = (mp.mpf(case["inside_phase_pi"]) * mp.pi / q if "inside_phase_pi" in case
                 else mp.mpf(case["width_nm"]) * mp.mpf("1e-9"))
        if not mp.im(width) == 0 or width <= 0:
            raise ValueError("packet width must be real and positive")
        if q == 0:
            # psi_inside = C + D*x/a. Unknowns: r,C,D,t_at_a.
            matrix = mp.matrix([
                [1, -1, 0, 0],
                [-1j * k_left, 0, -1 / width, 0],
                [0, 1, 1, -1],
                [0, 0, 1 / width, -1j * k_right],
            ])
            rhs = mp.matrix([-1, -1j * k_left, 0, 0])
            denominator = k_left + k_right - 1j * k_left * k_right * width
        else:
            # Two interface-centered bases avoid growing exponentials in the
            # linear solve even when float64 transmission would underflow.
            phase = mp.exp(1j * q * width)
            matrix = mp.matrix([
                [1, -1, -phase, 0],
                [-k_left, -q, q * phase, 0],
                [0, phase, 1, -1],
                [0, q * phase, -q, -k_right],
            ])
            rhs = mp.matrix([-1, -k_left, 0, 0])
            denominator = ((k_left + k_right) * mp.cos(q * width)
                           - 1j * (q + k_left * k_right / q) * mp.sin(q * width))
        solution = mp.lu_solve(matrix, rhs)
        reflection = abs(solution[0]) ** 2
        amplitude_squared = abs(solution[3]) ** 2
        transmission = k_right / k_left * amplitude_squared
        transfer_transmission = k_right / k_left * abs(2 * k_left / denominator) ** 2
        relative_error = abs(transmission - transfer_transmission) / transmission
        conservation_error = abs(reflection + transmission - 1)
        # Normalize derivative residuals before comparing unlike SI units.
        residual = matrix * solution - rhs
        boundary_error = max(abs(residual[0]), abs(residual[2]),
                             abs(residual[1] / k_left), abs(residual[3] / k_left))
        if not (0 < transmission <= 1 and relative_error < mp.mpf("1e-80")
                and conservation_error < mp.mpf("1e-80")
                and boundary_error < mp.mpf("1e-80")):
            raise AssertionError(f"independent boundary/transfer checks failed: {case['case_id']}")
        opaque = mp.im(q) * width
        return {
            "case_id": case["case_id"], "inputs": case,
            "width_nm": mp.nstr(width * mp.mpf("1e9"), 40),
            "T": mp.nstr(transmission, 40), "R": mp.nstr(reflection, 40),
            "amplitude_squared": mp.nstr(amplitude_squared, 40),
            "velocity_ratio": mp.nstr(k_right / k_left, 40),
            "log10_T": mp.nstr(mp.log10(transmission), 40),
            "kappa_a": mp.nstr(opaque, 40),
            "relative_reference_error": mp.nstr(relative_error, 6),
            "conservation_error": mp.nstr(conservation_error, 6),
            "dimensionless_boundary_residual": mp.nstr(boundary_error, 6),
            "regime": "below" if energy < height else "equal" if energy == height else "above",
            "runtime_support": (
                "not_supported_unequal_asymptotes" if left != right else
                "not_supported_threshold" if q == 0 else
                "not_supported_opaque_float64_range" if opaque > 300 else
                "within_reference_parameter_scope"
            ),
        }


def report() -> dict[str, Any]:
    path = PACKET / "teacher-only/reference-cases.json"
    source = path.read_bytes()
    cases = json.loads(source)["cases"]
    return {
        "schema_version": "heldout-barrier-reference/1.0.0",
        "label": "AUTOMATED REFERENCE CHECKS; UNREVIEWED; NO CLASSROOM RESULTS",
        "precision_decimal_digits": 100,
        "mpmath_version": mp.__version__,
        "case_file_sha256": hashlib.sha256(source).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "constants": {"electron_volt_J": "1.602176634e-19", "hbar_J_s": "1.054571817e-34",
                      "electron_mass_kg": "9.1093837015e-31"},
        "method": "interface-centered boundary solve versus closed transfer amplitude",
        "limitations": (
            "Constants are supplied approximations; numerical agreement is not teacher approval."
        ),
        "cases": [check_case(case) for case in cases],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    serialized = json.dumps(report(), ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        arguments.output.write_text(serialized, encoding="utf-8", newline="\n")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
