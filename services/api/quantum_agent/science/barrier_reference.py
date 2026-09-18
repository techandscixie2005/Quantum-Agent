"""Independent, bounded boundary matching; never callable by generated code."""
from __future__ import annotations

import cmath
import math

import numpy as np


def boundary_probabilities(
    energy_ev: float, height_ev: float, width_m: float, mass_kg: float,
) -> tuple[float, float]:
    """Solve four continuity equations for r, C, D, t (t at x=a).

    Evanescent bases decay from opposite interfaces to avoid growing
    exponentials. Reject opaque cases before floating-point underflow can
    masquerade as a physically exact zero transmission.
    """
    ev = 1.602176634e-19
    hbar = 1.054571817e-34
    k = math.sqrt(2 * mass_kg * energy_ev * ev) / hbar
    q = cmath.sqrt(2 * mass_kg * (energy_ev - height_ev) * ev) / hbar
    if abs(q.imag * width_m) > 300:
        raise ValueError("Opaque barrier exceeds the independently verified float64 range")
    phase = cmath.exp(1j * q * width_m)
    # Divide derivative rows by k for consistent dimensionless conditioning.
    ratio = q / k
    matrix = np.array([
        [1, -1, -phase, 0],
        [-1, -ratio, ratio * phase, 0],
        [0, phase, 1, -1],
        [0, ratio * phase, -ratio, -1],
    ], dtype=complex)
    rhs = np.array([-1, -1, 0, 0], dtype=complex)
    solution = np.linalg.solve(matrix, rhs)
    if np.linalg.norm(matrix @ solution - rhs, ord=np.inf) > 1e-9:
        raise ValueError("Boundary matching residual exceeds tolerance")
    reflection, _, _, transmission = solution
    t, r = float(abs(transmission) ** 2), float(abs(reflection) ** 2)
    if not all(math.isfinite(value) for value in (t, r)):
        raise ValueError("Non-finite boundary matching result")
    return t, r
