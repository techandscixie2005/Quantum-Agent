import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CodingArtifactPanel from "../app/components/agent/CodingArtifactPanel";
import type { CodeArtifactRun } from "../app/components/teaching/contracts";

test("unverified model prose/code/figure never inherit the metric PASS", () => {
  const run = {
    artifact: { language: "python", purpose: "WRONG_PURPOSE", code: "# r=1-t WRONG_CODE",
      expected_outputs: ["T=2.55e-9 WRONG_EXPECTED"], verification_plan: "WRONG_PLAN" },
    execution: { completed: true, stdout_bounded: "WRONG_STDOUT_PROSE" },
    verification: { status: "pass", agent_metrics: { T: 0.3336822872, R: 0.6663177128 },
      oracle_metrics: { T: 0.3336822872 }, observations: [] },
    repairs: [], progress: "result", figure_png_base64: "UNVERIFIED_FIGURE",
  } as unknown as CodeArtifactRun;
  const html = renderToStaticMarkup(createElement(CodingArtifactPanel, { run }));
  assert.match(html, /0.333682/);
  assert.match(html, /PASS 仅表示/);
  assert.match(html, /不认证解释/);
  assert.doesNotMatch(html, /WRONG_|UNVERIFIED_FIGURE/);
});
