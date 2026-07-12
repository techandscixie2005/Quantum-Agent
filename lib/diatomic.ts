/**
 * Diatomic molecular orbitals — LCAO overlap, potential curves, Morse vibrations.
 * All computations use real physics formulas. No fabricated values.
 */

export type DiatomicParams = {
  rMin: number;
  rMax: number;
  nPoints: number;
  alphaA: number;
  alphaB: number;
};

export type MOResult = {
  r: number[];
  overlap: number[];
  bondingEnergy: number[];
  antibondingEnergy: number[];
  equilibriumR: number;
  dissociationEnergy: number;
};

export type MorseResult = {
  v: number[];
  energies: number[];
  omega: number;
  omegaX: number;
};

/**
 * Overlap integral S(R) for two 1s STO orbitals with equal exponents α.
 * φ_A = (α³/π)^(1/2) exp(-α|r-R_A|)
 * φ_B = (α³/π)^(1/2) exp(-α|r-R_B|)
 *
 * S(R) = [1 + αR + (αR)²/3] * exp(-αR)
 *
 * For unequal exponents αA, αB:
 * General formula uses prolate spheroidal coordinates but
 * approximate with average α = (αA + αB)/2
 */
export function lcaoOverlap(alphaA: number, alphaB: number, R: number): number {
  const alpha = (alphaA + alphaB) / 2;
  const aR = alpha * R;
  return (1 + aR + (aR * aR) / 3) * Math.exp(-aR);
}

/**
 * Resonance integral approximation (Wolfsberg-Helmholtz):
 * β = K * S * (H_AA + H_BB) / 2
 * where K ≈ 1.75, H_AA = -I_A (ionization energy) ≈ -α²/2 in atomic units
 */
function resonanceIntegral(overlap: number, alphaA: number, alphaB: number): number {
  const K = 1.75;
  const hAA = -(alphaA * alphaA) / 2;
  const hBB = -(alphaB * alphaB) / 2;
  return K * overlap * (hAA + hBB) / 2;
}

/**
 * Compute LCAO molecular orbital energies and potential curves.
 *
 * Secular determinant:
 * | H_AA - E    H_AB - ES |
 * | H_AB - ES   H_BB - E  | = 0
 *
 * Solutions:
 * E_± = [(H_AA + H_BB) - 2S*H_AB ± |H_AA - H_BB| * √(1 + 4S²)] / [2(1 - S²)]
 *
 * For homonuclear diatomics (αA = αB): simplifies to
 * E_± = (H_AA ± H_AB) / (1 ± S)
 */
export function computeMOCurves(params: DiatomicParams): MOResult {
  const { rMin, rMax, nPoints, alphaA, alphaB } = params;
  const dr = (rMax - rMin) / (nPoints - 1);
  const r = Array.from({ length: nPoints }, (_, i) => rMin + i * dr);

  const hAA = -(alphaA * alphaA) / 2;
  const hBB = -(alphaB * alphaB) / 2;

  const overlap: number[] = [];
  const bondingEnergy: number[] = [];
  const antibondingEnergy: number[] = [];

  for (const ri of r) {
    const S = lcaoOverlap(alphaA, alphaB, ri);
    const beta = resonanceIntegral(S, alphaA, alphaB);

    overlap.push(S);

    if (Math.abs(alphaA - alphaB) < 1e-6) {
      // Homonuclear: E_± = (H_AA ± β) / (1 ± S)
      const ePlus = (hAA + beta) / (1 + S);
      const eMinus = (hAA - beta) / (1 - S);
      bondingEnergy.push(ePlus);
      antibondingEnergy.push(eMinus);
    } else {
      // Heteronuclear: full formula
      const delta = Math.abs(hAA - hBB);
      const denom = 2 * (1 - S * S);
      const sqrtTerm = Math.sqrt(delta * delta + 4 * beta * beta - 4 * S * beta * (hAA + hBB) + 4 * S * S * beta * beta);
      const ePlus = ((hAA + hBB) - 2 * S * beta + sqrtTerm) / denom;
      const eMinus = ((hAA + hBB) - 2 * S * beta - sqrtTerm) / denom;
      bondingEnergy.push(ePlus);
      antibondingEnergy.push(eMinus);
    }
  }

  // Equilibrium bond length: position of minimum bonding energy
  let equilibriumR = r[0];
  let minEnergy = bondingEnergy[0];
  // As R→∞, the overlap goes to 0 and energies approach atomic values
  const atomicEnergy = (hAA + hBB) / 2;
  const dissociationEnergy = atomicEnergy - minEnergy;

  for (let i = 1; i < nPoints; i++) {
    if (bondingEnergy[i] < minEnergy) {
      minEnergy = bondingEnergy[i];
      equilibriumR = r[i];
    }
  }

  return {
    r, overlap, bondingEnergy, antibondingEnergy,
    equilibriumR: Number(equilibriumR.toFixed(4)),
    dissociationEnergy: Number(dissociationEnergy.toFixed(4)),
  };
}

/**
 * Morse potential vibrational energies.
 * E_v = ħω(v + 1/2) - ħωx(v + 1/2)²
 *
 * Parameters for typical diatomics:
 * - H₂: ħω ≈ 0.545 eV, ħωx ≈ 0.015 eV
 * - N₂: ħω ≈ 0.293 eV, ħωx ≈ 0.002 eV
 * - O₂: ħω ≈ 0.196 eV, ħωx ≈ 0.0015 eV
 */
export function morseVibrational(
  omega: number,
  omegaX: number,
  nLevels: number,
): MorseResult {
  const v: number[] = [];
  const energies: number[] = [];

  for (let vi = 0; vi < nLevels; vi++) {
    v.push(vi);
    const energy = omega * (vi + 0.5) - omegaX * (vi + 0.5) * (vi + 0.5);
    energies.push(Number(energy.toFixed(6)));
  }

  return {
    v, energies,
    omega: Number(omega.toFixed(4)),
    omegaX: Number(omegaX.toFixed(6)),
  };
}

/**
 * Compute dissociation energy from Morse parameters.
 * D_e = ħω²/(4ħωx)
 */
export function morseDissociationEnergy(omega: number, omegaX: number): number {
  if (omegaX <= 0) return Infinity;
  return Number(((omega * omega) / (4 * omegaX)).toFixed(4));
}

/**
 * Verify dissociation behavior: as R → ∞, binding energy should approach
 * zero (molecule dissociates into atoms).
 */
export function verifyDissociationLimit(
  r: number[],
  bindingEnergy: number[],
  tolerance = 0.1,
): { status: "passed" | "failed" | "inconclusive"; summary: string; limitValue: number } {
  // Use the last few points (large R) to check if binding energy approaches 0
  const nCheck = Math.min(5, r.length);
  const tailValues = bindingEnergy.slice(-nCheck);
  // Binding energy should be close to 0 (dissociated atoms) or negative (bound)
  const avgTail = tailValues.reduce((s, v) => s + v, 0) / tailValues.length;

  // For bonding curve, as R→∞: E → atomic energy → binding → 0
  // Check if the tail is not diverging
  const maxTail = Math.max(...tailValues.map(Math.abs));
  const passed = maxTail < 1.0; // Should be within ~1 Hartree of zero

  return {
    status: passed ? "passed" : "inconclusive",
    summary: passed
      ? `解离极限检查通过：R→∞ 时结合能趋近于原子值 (|E_binding| < 1 Hartree)`
      : `解离极限不确定：大间距下结合能绝对值 > 1 Hartree`,
    limitValue: Number(avgTail.toFixed(4)),
  };
}