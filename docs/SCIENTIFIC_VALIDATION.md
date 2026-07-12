# Scientific Validation

Quantum Agent performs **deterministic** scientific validation. Validator results are computed by
pure TypeScript functions; no LLM is involved in deciding pass/fail.

## Architecture

All validators live in `lib/verifiers.ts` and are exposed via `POST /api/verify` (`app/api/verify/route.ts`).
Each validator accepts typed input and returns a `VerificationResult`:

```typescript
type VerificationResult = {
  tool: string;                    // validator identifier
  status: "passed" | "failed" | "inconclusive";
  summary: string;                 // human-readable explanation
  details: Record<string, unknown>; // machine-readable details
  tolerance?: number;
  inputs?: Record<string, unknown>;
  timestamp?: string;
  provenance: "deterministic";
};
```

## Available validators (11 total)

### 1. Hermiticity (`hermiticity`)
Checks H = H† for a square complex matrix. Compares each element pair (i,j) against the complex conjugate of (j,i). Default tolerance: 1e-9.

### 2. Normalization (`normalization`)
Numerical integration of probability density using trapezoidal rule. Checks |∫|ψ|²dx − 1| ≤ tolerance. Input: array of |ψ|² samples and dx. Default tolerance: 1e-3.

### 3. Probability Conservation (`probability_conservation`)
Compares total probability across time steps. Checks max|P(t) − P(0)| ≤ tolerance. Input: array of per-step total probabilities. Default tolerance: 1e-3.

### 4. Commutator (`commutator`)
Computes [A,B] = AB − BA with complex matrix multiplication. Optionally validates against an expected commutator matrix. Returns the computed commutator in details. Default tolerance: 1e-9.

### 5. Boundary Continuity (`boundary_continuity`)
Checks ψ and dψ/dx continuity at a boundary point. Compares absolute differences in ψ and its derivative between left and right limit values. Default tolerance: 1e-6.

### 6. Matrix Symmetry (`matrix_symmetry`)
Checks A = A^T (not Hermiticity — this is real/matrix symmetry). Useful for verifying real symmetric matrices like discretized kinetic energy operators. Default tolerance: 1e-9.

### 7. Eigenvalue Residual (`eigenvalue_residual`)
Computes ‖Aψ − λψ‖ / ‖ψ‖ for a given matrix, eigenvalue, and eigenvector. If the residual is within tolerance, the eigenpair is verified. Default tolerance: 1e-6.

### 8. Dimensional Consistency (`dimensional_consistency`)
Checks that all terms in a physical expression have matching dimensional exponents (M, L, T). Supports dimensions: energy, length, time, mass, frequency, momentum, angular_momentum, planck_constant. Default tolerance: 1e-3.

### 9. Numerical Convergence (`numerical_convergence`)
Compares coarse and fine grid solutions. If the maximum point-wise difference is within tolerance, the solution is likely converged. Input: two arrays of values at corresponding spatial positions. Default tolerance: 1e-3.

### 10. Shape Consistency (`shape_consistency`)
Validates matrix shape. Checks uniform row lengths and optionally enforces expected dimensions. Useful as a pre-check before matrix operations.

### 11. Orthogonality (`orthogonality`)
Computes inner products between pairs of vectors. Checks |⟨v_i|v_j⟩| ≤ tolerance for all i ≠ j. Supports complex vectors.

## Usage pattern

The experiment workspace in the frontend calls `/api/verify` after running a simulation:

```typescript
fetch("/api/verify", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    tool: "probability_conservation",
    input: { probabilities: [1.0, 0.9998, 1.0001], tolerance: 0.001 }
  })
});
```

The course project definitions (`lib/projects.ts`) specify which validators apply to each project:

| Project | Required Validators |
|---|---|
| 量子隧穿与波包传播 | normalization, probability_conservation, boundary_continuity, convergence |
| 氢原子轨道与微扰 | normalization, orthogonality, hermiticity, eigenvalue_residual |
| 变分法与氦原子 | normalization, variational_bound, numerical_stability |
| 双原子分子轨道与光谱 | normalization, symmetry, dissociation_limit, spectrum_index |

## Principles

1. **Deterministic only**: Validator code is pure TypeScript. No LLM decides pass/fail.
2. **Transparent**: Each result includes inputs, tolerance, and provenance.
3. **Persisted**: Tool runs are stored in D1 (`toolRuns` table) for audit and trajectory replay.
4. **Unexecuted ≠ verified**: The UI distinguishes "validator passed" from "not run."

## Adding a new validator

1. Add the function to `lib/verifiers.ts`.
2. Register it in the `runVerifier` switch statement.
3. Add a test case in `tests/validators-citations-auth.test.ts`.
4. Add the tool name to the `/api/verify` input validation if desired.
5. Add documentation in this file.

## Limitations

- Validators are synthetic correctness checks; they cannot verify physical correctness of a model.
- Passing all validators does not guarantee the student's answer is physically correct — only that it meets mathematical consistency criteria.
- Validators for `variational_bound`, `dissociation_limit`, and `spectrum_index` are referenced in project definitions but not yet implemented as standalone verification functions (they are project-specific checks).