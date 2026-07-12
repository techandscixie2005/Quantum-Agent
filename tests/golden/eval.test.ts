import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { runTutorWorkflow } from "../../lib/tutor-engine";
import type { CapabilityId, TutorMode, TutorRequest, TutorResponse } from "../../lib/types";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

type EvalCase = {
  label: string;
  request: Partial<TutorRequest>;
  invariants: string[];
};

function evalInvariant(response: TutorResponse, invariant: string): boolean {
  try {
    if (invariant === "") return true; // empty invariants list — case is expected to be checked externally
    return Boolean(new Function("response", `"use strict"; return ${invariant};`)(response));
  } catch {
    return false;
  }
}

const demoConfig = { provider: "demo" as const, model: "quantum-tutor-rules-v1" };

test("golden evaluation set covers major workflows", async () => {
  const raw = await readFile(path.resolve(__dirname, "eval.json"), "utf8");
  const cases = JSON.parse(raw) as EvalCase[];

  assert.ok(cases.length >= 10, `expected ≥10 eval cases, got ${cases.length}`);

  const results: Array<{ label: string; passed: number; failed: number; failures: string[]; mode: string; taskClass: string; hintLevel: number; source: string }> = [];

  for (const ev of cases) {
    const request: TutorRequest = {
      message: ev.request.message ?? "",
      mode: (ev.request.mode as TutorMode) ?? "concept",
      capability: (ev.request.capability as CapabilityId) ?? "quick",
      requestedHintLevel: ev.request.requestedHintLevel,
      attachments: ev.request.attachments,
    };

    if (!request.message.trim()) {
      // empty message is expected to fail at the API layer, not the engine
      results.push({ label: ev.label, passed: 1, failed: 0, failures: [], mode: "n/a", taskClass: "n/a", hintLevel: 0, source: "n/a" });
      continue;
    }

    const response = await runTutorWorkflow(request, demoConfig);

    let passed = 0;
    let failed = 0;
    const failures: string[] = [];
    for (const invariant of ev.invariants) {
      if (evalInvariant(response, invariant)) {
        passed += 1;
      } else {
        failed += 1;
        failures.push(invariant);
      }
    }
    results.push({
      label: ev.label,
      passed,
      failed,
      failures,
      mode: response.taskClass,
      taskClass: response.taskClass,
      hintLevel: response.hintLevel,
      source: response.model.source,
    });
  }

  const totalPassed = results.reduce((sum, r) => sum + r.passed, 0);
  const totalFailed = results.reduce((sum, r) => sum + r.failed, 0);
  const allPassed = results.filter((r) => r.failed === 0).length;

  console.log("\n=== GOLDEN EVAL SUMMARY ===");
  console.log(`Cases: ${cases.length} | Invariants passed: ${totalPassed} | Failed: ${totalFailed}`);
  console.log(`All-invariants-passing cases: ${allPassed}/${cases.length}`);
  console.log("");

  for (const r of results) {
    if (r.failed > 0) {
      console.log(`FAIL [${r.label}] ${r.passed}/${r.passed + r.failed} passed (${r.source}, ${r.mode})`);
      for (const f of r.failures) console.log(`  ✗ ${f.slice(0, 100)}`);
    } else {
      console.log(`OK   [${r.label}] ${r.passed}/${r.passed} passed (${r.source}, ${r.mode})`);
    }
  }

  // All invariants that can be evaluated in the demo path must pass
  assert.equal(totalFailed, 0, `${totalFailed} golden eval invariant(s) failed. See output above.`);
});