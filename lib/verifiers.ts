export type VerificationResult = {
  tool: string;
  status: "passed" | "failed" | "inconclusive";
  summary: string;
  details: Record<string, unknown>;
  tolerance?: number;
  inputs?: Record<string, unknown>;
  timestamp?: string;
  provenance?: string;
};

type Complex = { re: number; im: number };
type MatrixInput = Array<Array<number | [number, number] | Complex>>;

function complex(value: number | [number, number] | Complex): Complex {
  if (typeof value === "number") return { re: value, im: 0 };
  if (Array.isArray(value)) return { re: Number(value[0]), im: Number(value[1]) };
  return { re: Number(value.re), im: Number(value.im) };
}

function distance(a: Complex, b: Complex) { return Math.hypot(a.re - b.re, a.im - b.im); }

function withMeta(result: VerificationResult, inputs?: Record<string, unknown>): VerificationResult {
  return { ...result, tolerance: result.tolerance ?? (result.details?.tolerance as number | undefined), inputs, timestamp: new Date().toISOString(), provenance: "deterministic" };
}

export function verifyHermiticity(matrix: MatrixInput, tolerance = 1e-9): VerificationResult {
  if (!Array.isArray(matrix) || !matrix.length || matrix.some((row) => !Array.isArray(row) || row.length !== matrix.length)) {
    return withMeta({ tool: "hermiticity", status: "inconclusive", summary: "输入必须是方阵。", details: {} });
  }
  let maxDeviation = 0;
  for (let i = 0; i < matrix.length; i += 1) for (let j = 0; j < matrix.length; j += 1) {
    const a = complex(matrix[i][j]);
    const b = complex(matrix[j][i]);
    maxDeviation = Math.max(maxDeviation, distance(a, { re: b.re, im: -b.im }));
  }
  const passed = maxDeviation <= tolerance;
  return withMeta({ tool: "hermiticity", status: passed ? "passed" : "failed", summary: passed ? "矩阵在给定容差内为厄米矩阵。" : "矩阵不满足 H = H†。", details: { maxDeviation, tolerance } }, { tolerance, size: matrix.length });
}

export function verifyNormalization(values: number[], dx: number, tolerance = 1e-3): VerificationResult {
  if (!Array.isArray(values) || values.length < 2 || !Number.isFinite(dx) || dx <= 0) return withMeta({ tool: "normalization", status: "inconclusive", summary: "需要至少两个概率密度采样点和正的 dx。", details: {} });
  const integral = values.reduce((sum, value, index) => sum + value * (index === 0 || index === values.length - 1 ? 0.5 : 1), 0) * dx;
  const error = Math.abs(integral - 1);
  return withMeta({ tool: "normalization", status: error <= tolerance ? "passed" : "failed", summary: error <= tolerance ? "数值波函数通过归一化检查。" : "归一化积分偏离 1。", details: { integral, error, tolerance } }, { dx, points: values.length });
}

export function verifyProbabilityConservation(probabilities: number[], tolerance = 1e-3): VerificationResult {
  if (!Array.isArray(probabilities) || probabilities.length < 2) return withMeta({ tool: "probability_conservation", status: "inconclusive", summary: "需要至少两个时间步的总概率。", details: {} });
  const initial = probabilities[0];
  const maxDrift = Math.max(...probabilities.map((value) => Math.abs(value - initial)));
  return withMeta({ tool: "probability_conservation", status: maxDrift <= tolerance ? "passed" : "failed", summary: maxDrift <= tolerance ? "整个传播过程满足概率守恒。" : "总概率随时间发生了超出容差的漂移。", details: { initial, final: probabilities.at(-1), maxDrift, tolerance } }, { steps: probabilities.length });
}

export function verifyCommutator(a: MatrixInput, b: MatrixInput, expected?: MatrixInput, tolerance = 1e-9): VerificationResult {
  const n = a.length;
  if (!n || b.length !== n || a.some((r) => r.length !== n) || b.some((r) => r.length !== n)) return withMeta({ tool: "commutator", status: "inconclusive", summary: "A 与 B 必须是同阶方阵。", details: {} });
  const multiply = (x: MatrixInput, y: MatrixInput) => Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => {
    let re = 0; let im = 0;
    for (let k = 0; k < n; k += 1) { const p = complex(x[i][k]); const q = complex(y[k][j]); re += p.re * q.re - p.im * q.im; im += p.re * q.im + p.im * q.re; }
    return { re, im };
  }));
  const ab = multiply(a, b); const ba = multiply(b, a);
  const commutator = ab.map((row, i) => row.map((value, j) => ({ re: value.re - ba[i][j].re, im: value.im - ba[i][j].im })));
  if (!expected) return withMeta({ tool: "commutator", status: "passed", summary: "已计算对易子 [A,B]。", details: { commutator } }, { size: n });
  let maxDeviation = 0;
  for (let i = 0; i < n; i += 1) for (let j = 0; j < n; j += 1) maxDeviation = Math.max(maxDeviation, distance(commutator[i][j], complex(expected[i][j])));
  return withMeta({ tool: "commutator", status: maxDeviation <= tolerance ? "passed" : "failed", summary: maxDeviation <= tolerance ? "对易子与目标结果一致。" : "对易子与目标结果不一致。", details: { commutator, maxDeviation, tolerance } }, { size: n });
}

export function verifyBoundaryContinuity(left: { psi: number; derivative: number }, right: { psi: number; derivative: number }, tolerance = 1e-6): VerificationResult {
  const psiJump = Math.abs(left.psi - right.psi); const derivativeJump = Math.abs(left.derivative - right.derivative);
  const passed = Math.max(psiJump, derivativeJump) <= tolerance;
  return withMeta({ tool: "boundary_continuity", status: passed ? "passed" : "failed", summary: passed ? "波函数及其一阶导数在边界连续。" : "边界条件不连续。", details: { psiJump, derivativeJump, tolerance } }, { left: { psi: left.psi, derivative: left.derivative }, right: { psi: right.psi, derivative: right.derivative } });
}

// --- Additional validators ---

export function verifyMatrixSymmetry(matrix: MatrixInput, tolerance = 1e-9): VerificationResult {
  if (!Array.isArray(matrix) || !matrix.length || matrix.some((row) => !Array.isArray(row) || row.length !== matrix.length)) {
    return withMeta({ tool: "matrix_symmetry", status: "inconclusive", summary: "输入必须是方阵。", details: {} });
  }
  let maxDeviation = 0;
  for (let i = 0; i < matrix.length; i += 1) for (let j = 0; j < matrix.length; j += 1) {
    maxDeviation = Math.max(maxDeviation, distance(complex(matrix[i][j]), complex(matrix[j][i])));
  }
  const passed = maxDeviation <= tolerance;
  return withMeta({ tool: "matrix_symmetry", status: passed ? "passed" : "failed", summary: passed ? "矩阵在给定容差内为对称矩阵。" : "矩阵不对称。", details: { maxDeviation, tolerance } }, { size: matrix.length });
}

export function verifyEigenvalueResidual(matrix: MatrixInput, eigenvalue: number | [number, number], eigenvector: Array<number | [number, number]>, tolerance = 1e-6): VerificationResult {
  const n = matrix.length;
  if (!n || eigenvector.length !== n) return withMeta({ tool: "eigenvalue_residual", status: "inconclusive", summary: "矩阵与特征向量维度不匹配。", details: {} });
  const lambda = typeof eigenvalue === "number" ? { re: eigenvalue, im: 0 } : { re: eigenvalue[0], im: eigenvalue[1] };
  let normResidualSq = 0; let normVectorSq = 0;
  for (let i = 0; i < n; i += 1) {
    const vi = complex(eigenvector[i]);
    let avRe = 0; let avIm = 0;
    for (let j = 0; j < n; j += 1) { const m = complex(matrix[i][j]); const vj = complex(eigenvector[j]); avRe += m.re * vj.re - m.im * vj.im; avIm += m.re * vj.im + m.im * vj.re; }
    const residualRe = avRe - (lambda.re * vi.re - lambda.im * vi.im);
    const residualIm = avIm - (lambda.re * vi.im + lambda.im * vi.re);
    normResidualSq += residualRe * residualRe + residualIm * residualIm;
    normVectorSq += vi.re * vi.re + vi.im * vi.im;
  }
  const residual = Math.sqrt(normResidualSq) / Math.sqrt(Math.max(normVectorSq, 1e-30));
  const passed = residual <= tolerance;
  return withMeta({ tool: "eigenvalue_residual", status: passed ? "passed" : "failed", summary: passed ? "特征值-特征向量关系成立。" : "残差 ‖Aψ−λψ‖/‖ψ‖ 超出容差。", details: { residual, tolerance, eigenvalue: lambda } }, { size: n });
}

const unitDimensions: Record<string, Record<string, number>> = {
  energy: { M: 1, L: 2, T: -2 },
  length: { M: 0, L: 1, T: 0 },
  time: { M: 0, L: 0, T: 1 },
  mass: { M: 1, L: 0, T: 0 },
  frequency: { M: 0, L: 0, T: -1 },
  momentum: { M: 1, L: 1, T: -1 },
  angular_momentum: { M: 1, L: 2, T: -1 },
  planck_constant: { M: 1, L: 2, T: -1 },
};

export function verifyDimensionalConsistency(terms: Array<{ value: number; dimension: string }>, tolerance = 1e-3): VerificationResult {
  if (terms.length < 2) return withMeta({ tool: "dimensional_consistency", status: "inconclusive", summary: "需要至少两个量纲描述项进行比较。", details: {} });
  const dims = terms.map((t) => unitDimensions[t.dimension]);
  if (dims.some((d) => d === undefined)) return withMeta({ tool: "dimensional_consistency", status: "inconclusive", summary: "未识别量纲类型；支持的类型：energy, length, time, mass, frequency, momentum, angular_momentum, planck_constant。", details: { provided: terms.map((t) => t.dimension) } });
  const reference = dims[0];
  const mismatches: Array<{ index: number; dimension: string }> = [];
  for (let i = 1; i < dims.length; i += 1) {
    if (dimensionsDiffer(reference, dims[i], tolerance)) mismatches.push({ index: i, dimension: terms[i].dimension });
  }
  const passed = mismatches.length === 0;
  return withMeta({ tool: "dimensional_consistency", status: passed ? "passed" : "failed", summary: passed ? "所有量纲一致。" : `${mismatches.length} 个量纲不匹配。`, details: { reference: terms[0].dimension, mismatches } }, { terms: terms.map((t) => t.dimension) });
}

function dimensionsDiffer(a: Record<string, number>, b: Record<string, number>, tolerance: number): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) if (Math.abs((a[key] ?? 0) - (b[key] ?? 0)) > tolerance) return true;
  return false;
}

export function verifyNumericalConvergence(coarse: number[], fine: number[], tolerance = 1e-3): VerificationResult {
  if (coarse.length < 2 || fine.length < 2) return withMeta({ tool: "numerical_convergence", status: "inconclusive", summary: "需要粗、细两套网格的采样点各至少两个。", details: {} });
  const nCoarse = coarse.length;
  const maxDiff = Math.max(...coarse.map((v, i) => Math.abs(v - fine[Math.min(Math.round(i * (fine.length - 1) / (nCoarse - 1)), fine.length - 1)])));
  const passed = maxDiff <= tolerance;
  return withMeta({ tool: "numerical_convergence", status: passed ? "passed" : "failed", summary: passed ? "粗细网格差值在容差内，数值解趋于收敛。" : "粗细网格差值超出容差，数值解可能未收敛。", details: { maxDiff, tolerance, coarsePoints: nCoarse, finePoints: fine.length } }, { coarseLength: nCoarse, fineLength: fine.length });
}

export function verifyShapeConsistency(matrix: MatrixInput, expectedRows?: number, expectedCols?: number): VerificationResult {
  const rows = matrix.length;
  if (!rows) return withMeta({ tool: "shape_consistency", status: "inconclusive", summary: "矩阵不能为空。", details: {} });
  const cols = matrix[0]?.length ?? 0;
  const uniform = matrix.every((row) => row.length === cols);
  if (!uniform) return withMeta({ tool: "shape_consistency", status: "failed", summary: "矩阵行长度不一致。", details: { rows, cols } });
  if (expectedRows !== undefined && rows !== expectedRows) return withMeta({ tool: "shape_consistency", status: "failed", summary: `需要 ${expectedRows} 行，实际 ${rows} 行。`, details: { rows, expectedRows } });
  if (expectedCols !== undefined && cols !== expectedCols) return withMeta({ tool: "shape_consistency", status: "failed", summary: `需要 ${expectedCols} 列，实际 ${cols} 列。`, details: { cols, expectedCols } });
  return withMeta({ tool: "shape_consistency", status: "passed", summary: `矩阵形状 ${rows}×${cols} 符合要求。`, details: { rows, cols } }, { rows, cols });
}

export function verifyOrthogonality(vectors: Array<Array<number | [number, number]>>, tolerance = 1e-6): VerificationResult {
  const n = vectors.length;
  if (n < 2) return withMeta({ tool: "orthogonality", status: "inconclusive", summary: "需要至少两个向量。", details: {} });
  const overlaps: Array<{ i: number; j: number; inner: number }> = [];
  for (let i = 0; i < n; i += 1) for (let j = i + 1; j < n; j += 1) {
    let re = 0; let im = 0;
    const vi = vectors[i]; const vj = vectors[j];
    if (!vi || !vj) return withMeta({ tool: "orthogonality", status: "inconclusive", summary: `向量 ${i} 或 ${j} 无效。`, details: {} });
    for (let k = 0; k < Math.min(vi.length, vj.length); k += 1) {
      const a = complex(vi[k]); const b = complex(vj[k]);
      re += a.re * b.re + a.im * b.im;
      im += a.re * b.im - a.im * b.re;
    }
    const inner = Math.hypot(re, im);
    if (inner > tolerance) overlaps.push({ i, j, inner });
  }
  const passed = overlaps.length === 0;
  return withMeta({ tool: "orthogonality", status: passed ? "passed" : "failed", summary: passed ? "所有向量互相正交。" : `${overlaps.length} 对向量内积超出容差。`, details: { overlaps, tolerance } }, { vectorCount: n });
}

export function runVerifier(tool: string, input: Record<string, unknown>): VerificationResult {
  switch (tool) {
    case "hermiticity": return verifyHermiticity(input.matrix as MatrixInput, Number(input.tolerance ?? 1e-9));
    case "normalization": return verifyNormalization(input.values as number[], Number(input.dx), Number(input.tolerance ?? 1e-3));
    case "probability_conservation": return verifyProbabilityConservation(input.probabilities as number[], Number(input.tolerance ?? 1e-3));
    case "commutator": return verifyCommutator(input.a as MatrixInput, input.b as MatrixInput, input.expected as MatrixInput | undefined, Number(input.tolerance ?? 1e-9));
    case "boundary_continuity": return verifyBoundaryContinuity(input.left as { psi: number; derivative: number }, input.right as { psi: number; derivative: number }, Number(input.tolerance ?? 1e-6));
    case "matrix_symmetry": return verifyMatrixSymmetry(input.matrix as MatrixInput, Number(input.tolerance ?? 1e-9));
    case "eigenvalue_residual": return verifyEigenvalueResidual(input.matrix as MatrixInput, input.eigenvalue as number | [number, number], input.eigenvector as Array<number | [number, number]>, Number(input.tolerance ?? 1e-6));
    case "dimensional_consistency": return verifyDimensionalConsistency(input.terms as Array<{ value: number; dimension: string }>, Number(input.tolerance ?? 1e-3));
    case "numerical_convergence": return verifyNumericalConvergence(input.coarse as number[], input.fine as number[], Number(input.tolerance ?? 1e-3));
    case "shape_consistency": return verifyShapeConsistency(input.matrix as MatrixInput, input.expectedRows as number | undefined, input.expectedCols as number | undefined);
    case "orthogonality": return verifyOrthogonality(input.vectors as Array<Array<number | [number, number]>>, Number(input.tolerance ?? 1e-6));
    default: return withMeta({ tool, status: "inconclusive", summary: `未知验证器：${tool}`, details: {} });
  }
}

