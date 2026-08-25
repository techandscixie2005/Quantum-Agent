import assert from "node:assert/strict";
import test from "node:test";
import { coursewareManifest, seedKnowledge } from "../lib/course-knowledge";
import { enforceHintLevel } from "../lib/policy";
import { providerConfigForCapability } from "../lib/providers";
import { retrieveKnowledge } from "../lib/retrieval";
import { validateAttachments } from "../lib/security";
import { projectDefinitions } from "../lib/projects";
import { inspectSandboxCode } from "../lib/sandbox";
import { runTutorWorkflow } from "../lib/tutor-engine";
import { verifyHermiticity, verifyProbabilityConservation } from "../lib/verifiers";

test("courseware index contains all seven PDFs and hundreds of page chunks", () => {
  assert.equal(coursewareManifest.length, 7);
  assert.ok(seedKnowledge.length > 700);
});

test("retrieval returns a page-grounded Franck-Condon citation", () => {
  const citations = retrieveKnowledge("Franck-Condon 原理是什么？", seedKnowledge);
  assert.ok(citations.length > 0);
  assert.match(citations[0].chapter, /第八章/);
  assert.equal(citations[0].pages, "60");
  assert.match(citations[0].sourceUrl ?? "", /08-molecular-spectroscopy\.pdf#page=60/);
});

test("retrieval does not fabricate a courseware citation for uncovered tunneling content", () => {
  assert.equal(retrieveKnowledge("能量低于势垒为什么还能隧穿？", seedKnowledge).length, 0);
});

test("policy gate never exceeds the course hint ceiling", () => {
  assert.equal(enforceHintLevel(5, true, 3), 3);
  assert.equal(enforceHintLevel(undefined, false, 3), 1);
});

test("Hermiticity verifier handles complex conjugation", () => {
  const result = verifyHermiticity([[1, [0, 1]], [[0, -1], 2]]);
  assert.equal(result.status, "passed");
});

test("probability verifier detects excessive drift", () => {
  assert.equal(verifyProbabilityConservation([1, 0.9998, 1.0001]).status, "passed");
  assert.equal(verifyProbabilityConservation([1, 0.95]).status, "failed");
});

test("demo tutor completes the bounded workflow without an API key", async () => {
  const result = await runTutorWorkflow(
    { mode: "concept", capability: "quick", message: "Franck-Condon 原理是什么？" },
    { provider: "demo", model: "quantum-tutor-rules-v1" },
  );
  assert.equal(result.model.source, "deterministic-fallback");
  assert.ok(result.citations.length > 0);
  assert.ok(result.trace.some((step) => step.node === "POLICY_GATE"));
  assert.match(result.answer.conclusion, /课件/);
  assert.equal(result.model.label, "快速问答");
});

test("server capability routing uses USTC defaults without exposing a client model selector", () => {
  const quick = providerConfigForCapability("quick", { USTC_API: "test-key" });
  const code = providerConfigForCapability("code", { USTC_API: "test-key" });
  assert.equal(quick.provider, "ustc");
  assert.equal(quick.model, "deepseek-v4-flash-ascend1");
  assert.equal(code.model, "glm-5.2");
});

test("image validation rejects unsupported attachment types", () => {
  assert.throws(() => validateAttachments([{ name: "x.svg", mimeType: "image/svg+xml", dataUrl: "data:image/svg+xml;base64,AAAA" }]));
});

test("all four course projects are represented", () => {
  assert.equal(projectDefinitions.length, 4);
  assert.equal(projectDefinitions[0].level, "golden-loop");
  assert.ok(projectDefinitions.every((project) => project.milestones.length >= 7));
});

test("sandbox preflight rejects network and filesystem access", () => {
  assert.equal(inspectSandboxCode("import requests\nrequests.get('https://example.com')").safe, false);
  assert.equal(inspectSandboxCode("import numpy as np\nprint(np.linalg.norm([3,4]))").safe, true);
});
