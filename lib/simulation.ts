/**
 * Crank-Nicolson wavepacket tunneling simulation.
 *
 * Solves the 1D time-dependent Schrödinger equation:
 *   iħ ∂ψ/∂t = -ħ²/(2m) ∂²ψ/∂x² + V(x)ψ
 *
 * Uses Crank-Nicolson finite-difference scheme with a tridiagonal solver.
 * All computations are deterministic and produce real numerical values.
 */

export type SimulationParams = {
  /** Spatial grid points */
  nPoints: number;
  /** Spatial extent (nm) */
  xMin: number;
  xMax: number;
  /** Time step (fs) */
  dt: number;
  /** Number of time steps */
  nSteps: number;
  /** Barrier height (eV) */
  v0: number;
  /** Barrier center (nm) */
  barrierCenter: number;
  /** Barrier width (nm) */
  barrierWidth: number;
  /** Initial wavepacket center (nm) */
  x0: number;
  /** Initial wavepacket momentum (nm⁻¹) */
  k0: number;
  /** Initial wavepacket width (nm) */
  sigma: number;
};

export type SimulationStep = {
  step: number;
  time: number;
  probability: number;
  rValue: number;
  tValue: number;
  normError: number;
};

export type SimulationResult = {
  params: SimulationParams;
  steps: SimulationStep[];
  finalProbabilities: number[];
  finalWavefunction: { re: number; im: number }[];
  grid: number[];
  potential: number[];
};

// Physical constants in convenient units
const HBAR = 0.6582119; // eV·fs
const MASS = 511000.0; // electron mass in eV/c², use natural units
const HBAR2_OVER_2M = 0.0380997; // ħ²/(2m) in eV·nm² for electron

function buildPotential(
  grid: number[],
  v0: number,
  barrierCenter: number,
  barrierWidth: number
): number[] {
  const halfWidth = barrierWidth / 2;
  return grid.map((x) =>
    Math.abs(x - barrierCenter) < halfWidth ? v0 : 0
  );
}

/**
 * Solve tridiagonal linear system Ax = d using Thomas algorithm.
 * a: sub-diagonal, b: diagonal, c: super-diagonal, d: right-hand side
 */
function thomas(
  a: number[],
  b: number[],
  c: number[],
  d: { re: number; im: number }[]
): { re: number; im: number }[] {
  const n = b.length;
  const cPrime = new Array(n).fill(0);
  const dPrime = new Array(n).fill({ re: 0, im: 0 });

  // Forward sweep
  cPrime[0] = c[0] / b[0];
  dPrime[0] = { re: d[0].re / b[0], im: d[0].im / b[0] };

  for (let i = 1; i < n; i++) {
    const m = 1.0 / (b[i] - a[i] * cPrime[i - 1]);
    cPrime[i] = (i < n - 1 ? c[i] : 0) * m;
    dPrime[i] = {
      re: (d[i].re - a[i] * dPrime[i - 1].re) * m,
      im: (d[i].im - a[i] * dPrime[i - 1].im) * m,
    };
  }

  // Back substitution
  const x = new Array(n).fill(null).map(() => ({ re: 0, im: 0 }));
  x[n - 1] = dPrime[n - 1];
  for (let i = n - 2; i >= 0; i--) {
    x[i] = {
      re: dPrime[i].re - cPrime[i] * x[i + 1].re,
      im: dPrime[i].im - cPrime[i] * x[i + 1].im,
    };
  }

  return x;
}

/**
 * Compute R and T values from wavefunction.
 * R = probability left of barrier, T = probability right of barrier.
 */
function computeRT(
  psi: { re: number; im: number }[],
  grid: number[],
  barrierLeft: number,
  barrierRight: number,
  dx: number
): { r: number; t: number } {
  let rProb = 0;
  let tProb = 0;
  for (let i = 0; i < psi.length; i++) {
    const prob = (psi[i].re * psi[i].re + psi[i].im * psi[i].im) * dx;
    if (grid[i] < barrierLeft) {
      rProb += prob;
    } else if (grid[i] > barrierRight) {
      tProb += prob;
    }
  }
  return { r: rProb, t: tProb };
}

/**
 * Run the Crank-Nicolson simulation.
 */
export function runSimulation(params: Partial<SimulationParams> = {}): SimulationResult {
  const p: SimulationParams = {
    nPoints: params.nPoints ?? 400,
    xMin: params.xMin ?? -20,
    xMax: params.xMax ?? 20,
    dt: params.dt ?? 0.05,
    nSteps: params.nSteps ?? 200,
    v0: params.v0 ?? 4.0,
    barrierCenter: params.barrierCenter ?? 0,
    barrierWidth: params.barrierWidth ?? 1.2,
    x0: params.x0 ?? -8,
    k0: params.k0 ?? 3.0,
    sigma: params.sigma ?? 1.5,
  };

  const dx = (p.xMax - p.xMin) / (p.nPoints - 1);
  const grid = Array.from({ length: p.nPoints }, (_, i) => p.xMin + i * dx);
  const potential = buildPotential(grid, p.v0, p.barrierCenter, p.barrierWidth);

  // Initialize Gaussian wavepacket
  let psi = grid.map((x) => {
    const arg = -((x - p.x0) ** 2) / (4 * p.sigma ** 2);
    const re = Math.exp(arg) * Math.cos(p.k0 * x);
    const im = Math.exp(arg) * Math.sin(p.k0 * x);
    return { re, im };
  });

  // Normalize
  const norm = Math.sqrt(
    psi.reduce((sum, v) => sum + (v.re * v.re + v.im * v.im), 0) * dx
  );
  psi = psi.map((v) => ({ re: v.re / norm, im: v.im / norm }));

  // Crank-Nicolson coefficients
  const alpha = HBAR2_OVER_2M * p.dt / (2 * dx * dx);
  const barrierLeft = p.barrierCenter - p.barrierWidth / 2;
  const barrierRight = p.barrierCenter + p.barrierWidth / 2;

  const steps: SimulationStep[] = [];
  const n = p.nPoints;

  for (let step = 0; step <= p.nSteps; step++) {
    const time = step * p.dt;

    // Compute total probability
    const totalProb = psi.reduce(
      (sum, v) => sum + (v.re * v.re + v.im * v.im),
      0
    ) * dx;

    const { r, t } = computeRT(psi, grid, barrierLeft, barrierRight, dx);

    steps.push({
      step,
      time: Number(time.toFixed(3)),
      probability: Number(totalProb.toFixed(8)),
      rValue: Number(r.toFixed(6)),
      tValue: Number(t.toFixed(6)),
      normError: Number(Math.abs(totalProb - 1).toFixed(8)),
    });

    if (step === p.nSteps) break;

    // Crank-Nicolson time step
    // (I + iHΔt/2ħ) ψ^{n+1} = (I - iHΔt/2ħ) ψ^n
    // For tridiagonal system: a*ψ_{j-1}^{n+1} + b*ψ_j^{n+1} + a*ψ_{j+1}^{n+1} = d_j

    const aDiag = new Array(n).fill(-alpha);
    const bDiag = new Array(n).fill(1 + 2 * alpha);
    const cDiag = new Array(n).fill(-alpha);

    // Modify diagonal for potential term
    for (let j = 0; j < n; j++) {
      const vTerm = potential[j] * p.dt / (2 * HBAR);
      bDiag[j] += vTerm;
    }

    // Build RHS: (I - iHΔt/2ħ) ψ^n
    const d = new Array(n).fill(null).map(() => ({ re: 0, im: 0 }));
    for (let j = 0; j < n; j++) {
      const vTerm = potential[j] * p.dt / (2 * HBAR);
      // (1 - 2i*alpha - i*vTerm) * psi[j] + i*alpha * (psi[j-1] + psi[j+1])
      const psiIm = psi[j].im;
      const psiRe = psi[j].re;

      // Contribution from ψ_j^n
      d[j].re = psiRe - 2 * alpha * psiIm + vTerm * psiIm;
      d[j].im = psiIm + 2 * alpha * psiRe - vTerm * psiRe;

      // Contribution from neighbors
      if (j > 0) {
        d[j].re += alpha * psi[j - 1].im;
        d[j].im -= alpha * psi[j - 1].re;
      }
      if (j < n - 1) {
        d[j].re += alpha * psi[j + 1].im;
        d[j].im -= alpha * psi[j + 1].re;
      }
    }

    psi = thomas(aDiag, bDiag, cDiag, d);
  }

  return {
    params: p,
    steps,
    finalProbabilities: psi.map(
      (v) => v.re * v.re + v.im * v.im
    ),
    finalWavefunction: psi,
    grid,
    potential,
  };
}

/**
 * Run parameter scan across barrier widths.
 */
export function runWidthScan(
  widths: number[],
  baseParams: Partial<SimulationParams> = {}
): Array<{ width: number; r: number; t: number; rtSum: number }> {
  return widths.map((width) => {
    const result = runSimulation({ ...baseParams, barrierWidth: width });
    const lastStep = result.steps[result.steps.length - 1];
    return {
      width: Number(width.toFixed(2)),
      r: lastStep.rValue,
      t: lastStep.tValue,
      rtSum: Number((lastStep.rValue + lastStep.tValue).toFixed(6)),
    };
  });
}