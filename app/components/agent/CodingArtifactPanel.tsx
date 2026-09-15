"use client";

import { Braces, Check, CircleAlert, LoaderCircle, ShieldCheck } from "lucide-react";
import type { CodeArtifactRun, CodingProgress } from "../teaching/contracts";

const PROGRESS_STEPS: ReadonlyArray<{ key: CodingProgress; label: string }> = [
  { key: "planning", label: "Planning" },
  { key: "writing", label: "Writing code" },
  { key: "running", label: "Running" },
  { key: "verifying", label: "Verifying" },
  { key: "result", label: "Result" },
];

function progressIndex(progress: CodingProgress): number {
  const idx = PROGRESS_STEPS.findIndex((step) => step.key === progress);
  return idx < 0 ? PROGRESS_STEPS.length - 1 : idx;
}

function VerificationBadge({ status }: { status: CodeArtifactRun["verification"]["status"] }) {
  if (status === "pass") {
    return (
      <span className="qa-coding-badge qa-coding-pass" data-testid="coding-verification-status">
        <Check /> Verifier PASS
      </span>
    );
  }
  if (status === "fail") {
    return (
      <span className="qa-coding-badge qa-coding-fail" data-testid="coding-verification-status">
        <CircleAlert /> Verifier FAIL
      </span>
    );
  }
  if (status === "no_oracle") {
    return (
      <span className="qa-coding-badge qa-coding-none" data-testid="coding-verification-status">
        <ShieldCheck /> No oracle
      </span>
    );
  }
  return (
    <span className="qa-coding-badge qa-coding-inconclusive" data-testid="coding-verification-status">
      <CircleAlert /> Verifier inconclusive
    </span>
  );
}

export default function CodingArtifactPanel({ run }: { run: CodeArtifactRun }) {
  const currentIdx = progressIndex(run.progress);
  const agentT = run.verification.agent_metrics.T;
  const oracleT = run.verification.oracle_metrics.T;
  return (
    <section className="qa-coding-panel" data-testid="coding-artifact" aria-label="Coding Agent artifact">
      <header>
        <Braces />
        <div>
          <strong>Coding Agent</strong>
          <small>已执行程序的指标核验</small>
        </div>
        <VerificationBadge status={run.verification.status} />
      </header>

      <ol className="qa-coding-progress" aria-label="Coding Agent progress">
        {PROGRESS_STEPS.map((step, idx) => {
          const state = idx < currentIdx ? "done" : idx === currentIdx ? "active" : "pending";
          return (
            <li key={step.key} data-state={state} data-testid={`coding-progress-${step.key}`}>
              {state === "active" ? <LoaderCircle size={11} /> : <span className="qa-coding-dot" />}
              <span>{step.label}</span>
            </li>
          );
        })}
      </ol>

      {run.repairs.length > 0 ? (
        <p className="qa-coding-repairs" data-testid="coding-repairs">
          经过 {run.repairs.length} 次自动修复（上限 2 次）。
        </p>
      ) : null}

      <p data-testid="coding-verification-scope">
        PASS 仅表示本次执行的结构化数值在容差内匹配指定核验器。
        不认证解释、引文、推导、生成计划或代码注释；这些未核验内容暂停展示。
        T/R 是透射/反射概率；r/t 是复振幅，不能用 r=1-t。
        精确判分不采用厚势垒近似。
      </p>

      <dl className="qa-coding-metrics" data-testid="coding-metrics">
        {agentT !== undefined ? (
          <>
            <dt>Agent T</dt>
            <dd data-testid="coding-agent-T">{formatMetric(agentT)}</dd>
          </>
        ) : null}
        {oracleT !== undefined ? (
          <>
            <dt>Oracle T</dt>
            <dd data-testid="coding-oracle-T">{formatMetric(oracleT)}</dd>
          </>
        ) : null}
        {run.verification.agent_metrics.R !== undefined ? (
          <>
            <dt>Agent R</dt>
            <dd>{formatMetric(run.verification.agent_metrics.R)}</dd>
          </>
        ) : null}
        {run.verification.oracle_metrics.R !== undefined ? (
          <>
            <dt>Oracle R</dt>
            <dd>{formatMetric(run.verification.oracle_metrics.R)}</dd>
          </>
        ) : null}
      </dl>

      {run.verification.observations.length > 0 ? (
        <ul className="qa-coding-observations" data-testid="coding-observations">
          {run.verification.observations.map((observation, idx) => (
            <li key={idx}>{observation}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function formatMetric(value: string | number | boolean): string {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(6) : String(value);
  }
  return String(value);
}
