/**
 * Hydrogen atom orbitals — radial wavefunctions, Stark effect, Zeeman splitting.
 * All computations use real physics formulas. No fabricated values.
 */

export type OrbitalParams = {
  n: number;
  l: number;
  Z: number;
  rMin: number;
  rMax: number;
  nPoints: number;
};

export type RadialResult = {
  r: number[];
  rnl: number[];
  probability: number[];
  normalization: number;
  peakPosition: number;
  expectationR: number;
};

// Bohr radius in Å
const A0 = 0.529177;

// Normalized hydrogen radial wavefunctions R_nl(r)
// R_10 = 2 * Z^(3/2) * exp(-Z*r)
// R_20 = (1/√2) * Z^(3/2) * (1 - Z*r/2) * exp(-Z*r/2)
// R_21 = (1/(2√6)) * Z^(3/2) * Z*r * exp(-Z*r/2)
// R_30 = (2/(3√3)) * Z^(3/2) * (1 - 2*Z*r/3 + 2*(Z*r)²/27) * exp(-Z*r/3)

function factorial(n: number): number {
  let result = 1;
  for (let i = 2; i <= n; i++) result *= i;
  return result;
}

function laguerre(n: number, alpha: number, x: number): number {
  // Associated Laguerre polynomial L_n^α(x) computed via recurrence
  if (n === 0) return 1;
  if (n === 1) return 1 + alpha - x;
  let L0 = 1;
  let L1 = 1 + alpha - x;
  for (let k = 1; k < n; k++) {
    const L2 = ((2 * k + 1 + alpha - x) * L1 - (k + alpha) * L0) / (k + 1);
    L0 = L1;
    L1 = L2;
  }
  return L1;
}

function radialFunction(n: number, l: number, Z: number, r: number): number {
  const rho = 2 * Z * r / (n * A0);
  const norm = Math.sqrt(
    Math.pow(2 * Z / (n * A0), 3) * factorial(n - l - 1) / (2 * n * factorial(n + l))
  );
  const poly = laguerre(n - l - 1, 2 * l + 1, rho);
  return norm * Math.pow(rho, l) * Math.exp(-rho / 2) * poly;
}

export function computeRadialWavefunction(params: OrbitalParams): RadialResult {
  const { n, l, Z, rMin, rMax, nPoints } = params;
  const dr = (rMax - rMin) / (nPoints - 1);
  const r = Array.from({ length: nPoints }, (_, i) => rMin + i * dr);
  const rnl = r.map((ri) => radialFunction(n, l, Z, ri));
  const probability = rnl.map((v, i) => r[i] * r[i] * v * v);

  // Normalization: ∫_0^∞ r²|R|² dr = 1
  const integral = probability.reduce((sum, p, i) =>
    sum + p * (i === 0 || i === nPoints - 1 ? 0.5 : 1) * dr, 0);

  let peakPosition = r[0];
  let maxProb = probability[0];
  for (let i = 1; i < nPoints; i++) {
    if (probability[i] > maxProb) {
      maxProb = probability[i];
      peakPosition = r[i];
    }
  }

  const expectationR = r.reduce((sum, ri, i) =>
    sum + ri * probability[i] * (i === 0 || i === nPoints - 1 ? 0.5 : 1) * dr, 0);

  return {
    r, rnl, probability,
    normalization: integral,
    peakPosition,
    expectationR,
  };
}

// Stark effect: matrix elements for hydrogen n=2 manifold
// Basis: |200>, |210>, |211>, |21-1>
// Only <200|eEz|210> is non-zero = -3ea₀
const EA0 = 1.0; // e*a₀ in convenient units; use as scaling factor

export function starkMatrixN2(fieldStrength: number): number[][] {
  const F = fieldStrength * EA0;
  // Matrix elements in the n=2 basis (|200>, |210>, |211>, |21-1>)
  // <200|z|210> = 3a₀
  const z12 = 3.0;
  return [
    [0,        -F * z12,  0,  0],
    [-F * z12,  0,         0,  0],
    [0,         0,         0,  0],
    [0,         0,         0,  0],
  ];
}

export function zeemanSplitting(l: number, s: number, j: number, B: number): {
  mj: number[];
  energies: number[];
  landeG: number;
} {
  // Landé g-factor
  let landeG: number;
  if (j === 0) {
    landeG = 0;
  } else {
    landeG = 1 + (j * (j + 1) + s * (s + 1) - l * (l + 1)) / (2 * j * (j + 1));
  }

  // Bohr magneton in eV/T
  const muB = 5.7883818e-5; // eV/T

  const mj: number[] = [];
  const energies: number[] = [];
  for (let m = -j; m <= j; m += 1) {
    mj.push(m);
    energies.push(landeG * muB * B * m);
  }

  return { mj, energies, landeG: Number(landeG.toFixed(6)) };
}