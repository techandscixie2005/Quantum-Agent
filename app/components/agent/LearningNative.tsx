"use client";

import {
  Check,
  CircleAlert,
  KeyRound,
  Lightbulb,
  Lock,
  PenLine,
  Sparkles,
  Target,
} from "lucide-react";
import { useState } from "react";

import type {
  CognitiveCommitment,
  CognitiveMirror,
  CommitmentKind,
  LearningNativeSubmission,
  LearningNativeTurnState,
  SoloMode,
  TeachBackAnalysis,
  TransferTask,
} from "@/app/components/teaching/contracts";

import styles from "./agent.module.css";

const COMMITMENT_KIND_LABELS: Readonly<Record<CommitmentKind, string>> = {
  prediction: "预测",
  first_step: "第一步",
  physical_reason: "物理理由",
  diagram: "画图",
  option_with_confidence: "选择 + 置信度",
  self_explanation: "自我解释",
};

const CONCEPT_STATE_LABELS: Readonly<Record<string, string>> = {
  unknown: "未知",
  exposed: "已接触",
  developing: "发展中",
  demonstrated: "已展示",
  transfer_ready: "可迁移",
  fragile: "脆弱",
  needs_review: "需要复习",
};

const TEACH_BACK_RELATION_LABELS: Readonly<Record<string, string>> = {
  covered: "已覆盖",
  missing: "遗漏",
  contradictory: "矛盾",
  unsupported: "无依据",
};

export function CommitmentCard({
  commitment,
  disabled,
  pending,
  error,
  onSubmit,
}: {
  commitment: CognitiveCommitment;
  disabled: boolean;
  pending: boolean;
  error: string | null;
  onSubmit: (submission: LearningNativeSubmission) => void;
}) {
  const [attemptType, setAttemptType] = useState<CommitmentKind>(
    commitment.attempt_type ?? "prediction",
  );
  const [response, setResponse] = useState("");
  const [confidence, setConfidence] = useState(80);

  function submit() {
    const trimmed = response.trim();
    if (!trimmed) return;
    onSubmit({
      commitment: {
        ...commitment,
        attempt_type: attemptType,
        candidate_prompt: trimmed,
        reason_summary: commitment.reason_summary,
        accepted: false,
        confidence: null,
      },
      confidence: attemptType === "option_with_confidence" ? confidence / 100 : null,
      teach_back: null,
      transfer_attempt: null,
      solo_attempt: null,
      request_transfer: false,
      request_solo_exit: false,
      request_teach_back: false,
      request_transfer_task: false,
    });
  }

  return (
    <section className={styles.learningCard} data-testid="commitment-card" aria-live="polite">
      <header>
        <span><KeyRound aria-hidden="true" /></span>
        <div>
          <p className={styles.kicker}>COGNITIVE COMMITMENT GATE</p>
          <h2>先做一个判断，再释放解释</h2>
        </div>
        <em>ATTEMPT REQUIRED</em>
      </header>
      <p>{commitment.candidate_prompt || commitment.reason_summary || "请先提交一个预测或第一步尝试。"}</p>
      <div className={styles.commitmentOptions}>
        {(Object.keys(COMMITMENT_KIND_LABELS) as readonly CommitmentKind[]).map((kind) => (
          <label key={kind}>
            <input
              type="radio"
              name="commitment-kind"
              value={kind}
              checked={attemptType === kind}
              onChange={() => setAttemptType(kind)}
              disabled={disabled}
            />
            <span>
              <strong>{COMMITMENT_KIND_LABELS[kind]}</strong>
              <small>
                {kind === "prediction" && "你预测会发生什么？"}
                {kind === "first_step" && "你认为第一步应该做什么？"}
                {kind === "physical_reason" && "给出一条物理理由。"}
                {kind === "diagram" && "画一个示意图或能级图。"}
                {kind === "option_with_confidence" && "选择一个选项并给出置信度。"}
                {kind === "self_explanation" && "用你自己的话解释当前概念。"}
              </small>
            </span>
          </label>
        ))}
      </div>
      <textarea
        value={response}
        onChange={(event) => setResponse(event.target.value)}
        placeholder="写下你的承诺（预测 / 第一步 / 理由）…"
        rows={3}
        maxLength={4000}
        disabled={disabled}
        aria-label="认知承诺文本"
      />
      {attemptType === "option_with_confidence" ? (
        <div className={styles.confidenceRow}>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={confidence}
            onChange={(event) => setConfidence(Number(event.target.value))}
            disabled={disabled}
            aria-label="置信度"
          />
          <strong>{confidence}%</strong>
        </div>
      ) : null}
      <footer>
        <small>系统不会替你解释；提交后才会释放下一步提示。</small>
        <button type="button" onClick={submit} disabled={disabled || pending || !response.trim()}>
          {pending ? <span className={styles.spin}>…</span> : <Check />}
          {pending ? "提交中" : "提交承诺"}
        </button>
      </footer>
      {error ? <p style={{ color: "var(--amber)", marginTop: 8 }}><CircleAlert size={12} /> {error}</p> : null}
    </section>
  );
}

export function TeachBackCard({
  analysis,
  disabled,
  pending,
  onSubmit,
}: {
  analysis: TeachBackAnalysis;
  disabled: boolean;
  pending: boolean;
  onSubmit: (submission: LearningNativeSubmission) => void;
}) {
  const [reconstruction, setReconstruction] = useState("");

  function submit() {
    const trimmed = reconstruction.trim();
    if (!trimmed) return;
    onSubmit({
      commitment: null,
      confidence: null,
      teach_back: { reconstruction: trimmed, target_concept_ids: [] },
      transfer_attempt: null,
      solo_attempt: null,
      request_transfer: false,
      request_solo_exit: false,
      request_teach_back: false,
      request_transfer_task: false,
    });
  }

  const findings = [
    ...analysis.covered_relations.map((item) => ({ ...item, relation: "covered" as const })),
    ...analysis.missing_relations.map((item) => ({ ...item, relation: "missing" as const })),
    ...analysis.contradictions.map((item) => ({ ...item, relation: "contradictory" as const })),
    ...analysis.unsupported_claims.map((item) => ({ ...item, relation: "unsupported" as const })),
  ];

  return (
    <section className={styles.learningCard} data-testid="teach-back-card">
      <header>
        <span><PenLine aria-hidden="true" /></span>
        <div>
          <p className={styles.kicker}>TEACH-BACK RECONSTRUCTION</p>
          <h2>用自己的话重新解释这个结论</h2>
        </div>
        <em>{analysis.is_model_inference ? "MODEL REVIEW" : "OBSERVATION"}</em>
      </header>
      {findings.length > 0 ? (
        <ul className={styles.teachBackFindings}>
          {findings.slice(0, 8).map((finding, index) => (
            <li key={`${finding.relation}-${index}`} data-relation={finding.relation}>
              <Check aria-hidden="true" />
              <div>
                <strong>{TEACH_BACK_RELATION_LABELS[finding.relation]}</strong>
                <span>{finding.description}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {analysis.recommended_probe ? (
        <p>{analysis.recommended_probe}</p>
      ) : null}
      <textarea
        value={reconstruction}
        onChange={(event) => setReconstruction(event.target.value)}
        placeholder="假设你在给一个第一次学这个概念的同学讲解…"
        rows={4}
        maxLength={12000}
        disabled={disabled}
        aria-label="teach-back 重构"
      />
      <footer>
        <small>系统只标注你覆盖或遗漏的关系，不会给出分数。</small>
        <button type="button" onClick={submit} disabled={disabled || pending || !reconstruction.trim()}>
          {pending ? <span className={styles.spin}>…</span> : <Check />}
          {pending ? "提交中" : "提交重构"}
        </button>
      </footer>
    </section>
  );
}

export function TransferCard({
  transfer,
  solo,
  disabled,
  pending,
  onSubmit,
}: {
  transfer: TransferTask;
  solo: SoloMode | null;
  disabled: boolean;
  pending: boolean;
  onSubmit: (submission: LearningNativeSubmission) => void;
}) {
  const [response, setResponse] = useState("");
  const [confidence, setConfidence] = useState(70);
  const isSoloActive = solo?.status === "active";

  function submit() {
    const trimmed = response.trim();
    if (!trimmed) return;
    onSubmit({
      commitment: null,
      confidence: confidence / 100,
      teach_back: null,
      transfer_attempt: null,
      solo_attempt: { response: trimmed, confidence: confidence / 100 },
      request_transfer: false,
      request_solo_exit: false,
      request_teach_back: false,
      request_transfer_task: false,
    });
  }

  function exitSolo() {
    onSubmit({
      commitment: null,
      confidence: null,
      teach_back: null,
      transfer_attempt: null,
      solo_attempt: null,
      request_transfer: false,
      request_solo_exit: true,
      request_teach_back: false,
      request_transfer_task: false,
    });
  }

  return (
    <section
      className={`${styles.learningCard} ${isSoloActive ? styles.soloModeCard : ""}`}
      data-testid="transfer-card"
    >
      <header>
        <span><Target aria-hidden="true" /></span>
        <div>
          <p className={styles.kicker}>TRANSFER TASK · {transfer.transfer_type.toUpperCase()}</p>
          <h2>把当前概念应用到新情境</h2>
        </div>
        <em>{isSoloActive ? "SOLO MODE" : "TRANSFER"}</em>
      </header>
      <p>{transfer.prompt}</p>
      {transfer.key_parameters.length > 0 ? (
        <p style={{ color: "var(--muted)", fontSize: 11 }}>
          关键参数：{transfer.key_parameters.join(" · ")}
        </p>
      ) : null}
      {isSoloActive ? (
        <div className={styles.soloLock}>
          <Lock aria-hidden="true" />
          <span>AI 辅助暂时不可用 · 你需要独立完成</span>
        </div>
      ) : null}
      <textarea
        value={response}
        onChange={(event) => setResponse(event.target.value)}
        placeholder="写下你的迁移尝试…"
        rows={4}
        maxLength={12000}
        disabled={disabled}
        aria-label="迁移尝试"
      />
      <div className={styles.confidenceRow}>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={confidence}
          onChange={(event) => setConfidence(Number(event.target.value))}
          disabled={disabled}
          aria-label="置信度"
        />
        <strong>{confidence}%</strong>
      </div>
      <footer>
        <small>
          {transfer.verifiable
            ? "提交后系统会用确定性工具检查你的答案。"
            : "提交后系统记录你的迁移证据。"}
        </small>
        <div style={{ display: "flex", gap: 8 }}>
          {isSoloActive ? (
            <button
              type="button"
              onClick={exitSolo}
              disabled={disabled || pending}
              style={{ background: "transparent", color: "var(--muted)", border: "1px solid var(--line)" }}
            >
              退出 Solo
            </button>
          ) : null}
          <button type="button" onClick={submit} disabled={disabled || pending || !response.trim()}>
            {pending ? <span className={styles.spin}>…</span> : <Check />}
            {pending ? "提交中" : "提交迁移尝试"}
          </button>
        </div>
      </footer>
    </section>
  );
}

export function CognitiveMirrorPanel({ mirror }: { mirror: CognitiveMirror }) {
  return (
    <section className={styles.cognitiveMirrorCard} data-testid="cognitive-mirror">
      <header>
        <div>
          <Sparkles aria-hidden="true" />
          <strong>Cognitive Mirror</strong>
        </div>
        <em>EVIDENCE-ONLY</em>
      </header>
      <p className={styles.mirrorSummary}>{mirror.summary}</p>
      <div className={styles.mirrorConcepts}>
        {mirror.concept_states.slice(0, 6).map((concept) => (
          <article key={concept.concept_candidate_id} data-state={concept.label} className={styles.mirrorConcept}>
            <div>
              <strong>{concept.label}</strong>
              <span className={styles.stateTag}>{CONCEPT_STATE_LABELS[concept.label] ?? concept.label}</span>
            </div>
            {concept.evidence_summary.slice(0, 2).map((line, index) => (
              <small key={index}>{line}</small>
            ))}
            {concept.misconception_candidates.slice(0, 1).map((line, index) => (
              <small key={`misconception-${index}`} style={{ color: "var(--amber)" }}>候选误解：{line}</small>
            ))}
          </article>
        ))}
      </div>
      {mirror.no_personality_profile ? (
        <p className={styles.mirrorNoProfile}>不进行人格 / 学习能力推断</p>
      ) : null}
    </section>
  );
}

export function LearningActionBadge({
  state,
}: {
  state: LearningNativeTurnState;
}) {
  if (!state.learning_action) return null;
  const label = state.learning_action.replace(/_/g, " ");
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 9px",
        margin: "6px 0 0",
        borderRadius: 999,
        border: "1px solid color-mix(in srgb, var(--green) 32%, transparent)",
        background: "color-mix(in srgb, var(--mint) 36%, transparent)",
        color: "var(--green-dark)",
        font: "700 8px var(--font-geist-mono), monospace",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
      }}
    >
      <Lightbulb size={12} />
      {label}
    </span>
  );
}

export function hasLearningNativeAction(state: LearningNativeTurnState | null): boolean {
  if (!state) return false;
  return (
    (state.commitment?.gate_decision === "attempt_required" && !state.commitment.accepted) ||
    state.teach_back !== null ||
    state.transfer !== null ||
    state.solo?.status === "active" ||
    state.minimal_intervention_prompt.trim().length > 0 ||
    state.required_action === "revision" ||
    state.required_action === "commitment"
  );
}

function MinimalInterventionCard({
  state,
  pending,
  onSubmit,
}: {
  state: LearningNativeTurnState;
  pending: boolean;
  onSubmit: (submission: LearningNativeSubmission) => void;
}) {
  const [response, setResponse] = useState("");

  function submit() {
    const trimmed = response.trim();
    if (!trimmed) return;
    onSubmit({
      commitment: null,
      confidence: null,
      teach_back: null,
      transfer_attempt: null,
      solo_attempt: null,
      request_transfer: false,
      request_solo_exit: false,
      request_teach_back: false,
      request_transfer_task: false,
    });
  }

  const probe =
    state.minimal_intervention_prompt.trim() ||
    "你的初步尝试已被记录。现在填写你的判断 / 推导 / 理由，我会给出下一步提示。";

  return (
    <section className={styles.learningCard} data-testid="minimal-intervention-card" aria-live="polite">
      <header>
        <span><Lightbulb aria-hidden="true" /></span>
        <div>
          <p className={styles.kicker}>MINIMAL INTERVENTION</p>
          <h2>基于你的尝试，完成下一步</h2>
        </div>
        <em>ATTEMPT RECEIVED</em>
      </header>
      <p>{probe}</p>
      <textarea
        value={response}
        onChange={(event) => setResponse(event.target.value)}
        placeholder="写下你的判断、推导或理由…"
        rows={3}
        maxLength={12000}
        disabled={pending}
        aria-label="最小干预回复"
      />
      <footer>
        <small>提交后会继续诊断并给出最小提示；完整解释按政策逐步释放。</small>
        <button type="button" onClick={submit} disabled={pending || !response.trim()}>
          {pending ? <span className={styles.spin}>…</span> : <Check />}
          {pending ? "提交中" : "提交下一步"}
        </button>
      </footer>
    </section>
  );
}

export function LearningNativeSurface({
  state,
  pending,
  onSubmit,
}: {
  state: LearningNativeTurnState;
  pending: boolean;
  onSubmit: (submission: LearningNativeSubmission) => void;
}) {
  const soloActive = state.solo?.status === "active";
  // Solo Mode disables the other cards: the student must submit a transfer
  // attempt or exit Solo before the tutor resumes.
  if (soloActive && state.solo?.active_transfer) {
    return (
      <>
        <LearningActionBadge state={state} />
        <TransferCard
          transfer={state.solo.active_transfer}
          solo={state.solo}
          disabled={false}
          pending={pending}
          onSubmit={onSubmit}
        />
      </>
    );
  }
  if (state.commitment && state.commitment.gate_decision === "attempt_required" && !state.commitment.accepted) {
    return (
      <>
        <LearningActionBadge state={state} />
        <CommitmentCard
          commitment={state.commitment}
          disabled={false}
          pending={pending}
          error={null}
          onSubmit={onSubmit}
        />
      </>
    );
  }
  if (state.teach_back) {
    return (
      <>
        <LearningActionBadge state={state} />
        <TeachBackCard
          analysis={state.teach_back}
          disabled={false}
          pending={pending}
          onSubmit={onSubmit}
        />
      </>
    );
  }
  if (state.transfer) {
    return (
      <>
        <LearningActionBadge state={state} />
        <TransferCard
          transfer={state.transfer}
          solo={state.solo}
          disabled={false}
          pending={pending}
          onSubmit={onSubmit}
        />
      </>
    );
  }
  // PRD V3.4: the episode holds at ATTEMPT_RECEIVED / INTERVENTION after the
  // commitment was accepted.  The accepted CommitmentCard is suppressed (it is
  // no longer actionable); surface the MINIMAL-INTERVENTION probe instead so
  // the student always has a concrete next action (no-orphan invariant).
  if (
    (state.phase === "attempt_received" || state.phase === "intervention") &&
    (state.minimal_intervention_prompt.trim().length > 0 || state.required_action === "revision")
  ) {
    return (
      <>
        <LearningActionBadge state={state} />
        <MinimalInterventionCard state={state} pending={pending} onSubmit={onSubmit} />
      </>
    );
  }
  // No active Learning-Native action; surface the action badge if present.
  if (state.learning_action) {
    return <LearningActionBadge state={state} />;
  }
  return null;
}
