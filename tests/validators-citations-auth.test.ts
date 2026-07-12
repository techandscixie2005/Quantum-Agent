import assert from "node:assert/strict";
import test from "node:test";
import { buildCitationAllowlist, enforceCitationAllowlist, detectFabricatedCitations } from "../lib/citation-allowlist";
import { checkRateLimit } from "../lib/security";
import {
  verifyDimensionalConsistency,
  verifyEigenvalueResidual,
  verifyMatrixSymmetry,
  verifyNumericalConvergence,
  verifyShapeConsistency,
  verifyOrthogonality,
  verifyCommutator,
  verifyBoundaryContinuity,
} from "../lib/verifiers";
import { issueTeacherSession, verifyTeacherSession, setTeacherCookie, clearTeacherCookie, extractTeacherCookie } from "../lib/teacher-auth";
import type { Citation } from "../lib/types";

// --- Citation allowlist ---

test("citation allowlist includes all retrieval ids", () => {
  const citations: Citation[] = [
    { id: "qp-ch08-60", title: "Test", chapter: "第八章", pages: "60", excerpt: "...", score: 0.9 },
    { id: "qp-ch05-12", title: "Test", chapter: "第五章", pages: "12", excerpt: "...", score: 0.8 },
  ];
  const allowlist = buildCitationAllowlist(citations);
  assert.ok(allowlist.has("qp-ch08-60"));
  assert.ok(allowlist.has("chapter:第八章"));
  assert.ok(allowlist.has("chapter:第五章"));
});

test("enforceCitationAllowlist strips fabricated ids", () => {
  const citations: Citation[] = [
    { id: "qp-ch01-1", title: "Real", chapter: "第一章", pages: "1", excerpt: "...", score: 1 },
    { id: "fake-page-9999", title: "Fake", chapter: "不存在", pages: "9999", excerpt: "...", score: 0.5 },
  ];
  const allowlist = buildCitationAllowlist(citations.slice(0, 1));
  const { allowed, rejected } = enforceCitationAllowlist(citations, allowlist);
  assert.equal(allowed.length, 1);
  assert.equal(allowed[0].id, "qp-ch01-1");
  assert.deepEqual(rejected, ["fake-page-9999"]);
});

test("detectFabricatedCitations finds injected refs in model text", () => {
  const allowlist = new Set<string>(["qp-ch03-5"]);
  const text = "根据[citation:qp-ch03-5]这页，以及[citation:qp-fake]和[ref:made-up]都是假的。";
  const fabricated = detectFabricatedCitations(text, allowlist);
  assert.ok(fabricated.includes("qp-fake"));
  assert.ok(fabricated.includes("made-up"));
  assert.ok(!fabricated.includes("qp-ch03-5"));
});

// --- Rate limit ---

test("rate limit allows within budget", () => {
  const key = `test-rate-${Math.random()}`;
  for (let i = 0; i < 30; i += 1) {
    assert.ok(checkRateLimit(key, 30, 60_000).allowed);
  }
  assert.equal(checkRateLimit(key, 30, 60_000).allowed, false);
});

// --- Additional validators ---

test("matrix symmetry detects asymmetric matrix", () => {
  const symmetric = verifyMatrixSymmetry([[1, 2], [2, 3]]);
  assert.equal(symmetric.status, "passed");
  const asymmetric = verifyMatrixSymmetry([[1, 2], [4, 3]]);
  assert.equal(asymmetric.status, "failed");
});

test("eigenvalue residual passes for true eigenpair", () => {
  // [[2, 1],[1, 2]] has eigenvalue 3 with eigenvector [1, 1]
  const result = verifyEigenvalueResidual([[2, 1], [1, 2]], 3, [1, 1]);
  assert.equal(result.status, "passed");
  // Bad eigenvector fails
  const bad = verifyEigenvalueResidual([[2, 1], [1, 2]], 3, [1, -1], 1e-6);
  assert.equal(bad.status, "failed");
});

test("dimensional consistency catches mismatches", () => {
  const ok = verifyDimensionalConsistency([
    { value: 1, dimension: "energy" },
    { value: 2, dimension: "energy" },
  ]);
  assert.equal(ok.status, "passed");
  const mismatch = verifyDimensionalConsistency([
    { value: 1, dimension: "energy" },
    { value: 2, dimension: "length" },
  ]);
  assert.equal(mismatch.status, "failed");
});

test("numerical convergence detects unconverged grid", () => {
  const coarse = [1, 2, 3, 4, 5];
  const fine = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const ok = verifyNumericalConvergence(coarse, fine, 10);
  assert.equal(ok.status, "passed");
  const bad = verifyNumericalConvergence([1, 2, 3], [100, 200, 300, 400, 500], 0.1);
  assert.equal(bad.status, "failed");
});

test("shape consistency validates matrix dimensions", () => {
  const ok = verifyShapeConsistency([[1, 2], [3, 4]], 2, 2);
  assert.equal(ok.status, "passed");
  const mismatched = verifyShapeConsistency([[1, 2], [3, 4]], 3, 2);
  assert.equal(mismatched.status, "failed");
});

test("orthogonality verifies inner products", () => {
  // [1,0], [0,1] are orthogonal
  const ok = verifyOrthogonality([[1, 0], [0, 1]]);
  assert.equal(ok.status, "passed");
  // Non-orthogonal
  const bad = verifyOrthogonality([[1, 0], [1, 1]], 0.01);
  assert.equal(bad.status, "failed");
});

test("commutator computes [A,B] and validates against expected", () => {
  // [σx, σy] = 2iσz = 2i * [[1,0],[0,-1]]
  const sx: Array<Array<number | [number, number]>> = [[0, 1], [1, 0]];
  const sy: Array<Array<number | [number, number]>> = [[0, [0, -1]], [[0, 1], 0]];
  const result = verifyCommutator(sx, sy);
  assert.equal(result.status, "passed");
});

test("boundary continuity detects jump", () => {
  const ok = verifyBoundaryContinuity({ psi: 1, derivative: 0.5 }, { psi: 1, derivative: 0.5 });
  assert.equal(ok.status, "passed");
  const bad = verifyBoundaryContinuity({ psi: 0, derivative: 0 }, { psi: 10, derivative: 0 });
  assert.equal(bad.status, "failed");
});

// --- Teacher auth ---

test("teacher session issue and verify", async () => {
  const token = await issueTeacherSession();
  const valid = await verifyTeacherSession(token);
  assert.equal(valid, true);
});

test("tampered teacher session is rejected", async () => {
  const token = await issueTeacherSession();
  const tampered = token.slice(0, -10) + "0000000000";
  const valid = await verifyTeacherSession(tampered);
  assert.equal(valid, false);
});

test("set and extract teacher cookie", () => {
  const cookieHeader = setTeacherCookie("test-token-123");
  assert.ok(cookieHeader.includes("qa_teacher=test-token-123"));
  assert.ok(cookieHeader.includes("HttpOnly"));
  const request = new Request("http://localhost/", { headers: { Cookie: cookieHeader } });
  assert.equal(extractTeacherCookie(request), "test-token-123");
});

test("clearTeacherCookie expires immediately", () => {
  const cleared = clearTeacherCookie();
  assert.ok(cleared.includes("Max-Age=0"));
});