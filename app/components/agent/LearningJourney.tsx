"use client";

import { Check } from "lucide-react";

import type { LearningNativeTurnState, LearningStage } from "@/app/components/teaching/contracts";

type JourneySegment = Readonly<{
  label: string;
  stage: LearningStage;
  id?: string;
}>;

const JOURNEY: readonly JourneySegment[] = [
  { label: "材料与判断", stage: "predict" },
  { label: "课程依据", stage: "diagnose", id: "sources" },
  { label: "推导补桥", stage: "diagnose", id: "bridge" },
  { label: "科学计算", stage: "verify" },
  { label: "解释与重建", stage: "explain" },
  { label: "Teach-Back", stage: "teach_back" },
  { label: "Transfer", stage: "transfer" },
  { label: "Solo", stage: "solo" },
];

function stageCompleted(state: LearningNativeTurnState, stage: LearningStage): boolean {
  return state.completed_stages.includes(stage);
}

function stageActive(state: LearningNativeTurnState, stage: LearningStage): boolean {
  return state.current_stage === stage;
}

export function LearningJourney({ state, hasSources = false, hasBridge = false, onReview, selected }: {
  state: LearningNativeTurnState | null; hasSources?: boolean; hasBridge?: boolean;
  onReview?: (stage: string) => void; selected?: string | null;
}) {
  const loopDone = state?.phase === "complete";
  return (
    <ol className="qa-journey" aria-label="学习旅程" data-testid="learning-journey">
      {JOURNEY.map((segment, index) => {
        const done = segment.id === "sources" ? hasSources : segment.id === "bridge" ? hasBridge : Boolean(state && stageCompleted(state, segment.stage));
        const active = !done && (state ? stageActive(state, segment.stage) && !segment.id : segment.stage === "predict");
        const stateAttr = done ? "done" : active ? "active" : "idle";
        return (
          <li key={segment.id ?? segment.stage} data-state={stateAttr} data-stage={segment.stage}>
            <button type="button" onClick={() => onReview?.(segment.id ?? segment.stage)}
              disabled={!onReview || !done || state?.solo?.status === "active"}
              aria-label={`回看${segment.label}`} aria-pressed={selected === (segment.id ?? segment.stage)}>
            <span className="qa-journey-mark">
              {done ? <Check size={12} aria-hidden="true" /> : String(index + 1).padStart(2, "0")}
            </span>
            <span className="qa-journey-label">{segment.label}</span>
            </button>
          </li>
        );
      })}
      <li data-state={loopDone ? "done" : "idle"} data-stage="evidence">
        <button type="button" onClick={() => onReview?.("evidence")}
          disabled={!onReview || state?.solo?.status === "active"}
          aria-label="回看学习证据" aria-pressed={selected === "evidence"}>
        <span className="qa-journey-mark">{loopDone ? <Check size={12} /> : "09"}</span>
        <span className="qa-journey-label">学习证据</span>
        </button>
      </li>
      <style>{`
        .qa-journey {
          list-style: none;
          display: flex;
          align-items: center;
          gap: 6px;
          justify-content: space-between;
          flex-wrap: wrap;
          margin: 14px 0 22px;
          padding: 0;
          font-family: var(--font-geist-mono, ui-monospace, monospace);
        }
        .qa-journey li {
          display: flex;
          align-items: center;
          gap: 7px;
          min-width: 0;
          color: var(--muted, #68746f);
          font-size: clamp(11px, 1vw, 16px);
          letter-spacing: .02em;
        }
        .qa-journey button {
          display: flex; align-items: center; gap: 7px; color: inherit;
          background: transparent; border: 0; padding: 4px 0; font: inherit;
          cursor: pointer;
        }
        .qa-journey button:disabled { cursor: default; }
        .qa-journey button:focus-visible { outline: 2px solid #17634d; outline-offset: 4px; }
        .qa-journey button[aria-pressed="true"] { text-decoration: underline; }
        .qa-journey li[data-state="done"] { color: var(--green, #17634d); }
        .qa-journey li[data-state="active"] { color: var(--ink, #14231f); }
        .qa-journey-mark {
          width: 24px;
          height: 24px;
          flex: none;
          display: grid;
          place-items: center;
          border-radius: 50%;
          border: 1px solid var(--line, #dcded7);
          background: var(--surface, #fbfaf7);
          font-size: 10px;
        }
        .qa-journey li[data-state="done"] .qa-journey-mark {
          background: var(--mint, #e5f0ea);
          border-color: var(--green, #17634d);
          color: var(--green, #17634d);
        }
        .qa-journey li[data-state="active"] .qa-journey-mark {
          border-color: var(--green, #17634d);
          color: var(--green, #17634d);
        }
        @media (min-width: 1100px) and (max-width: 1450px) {
          .qa-journey li { font-size: 12px; gap: 4px; }
          .qa-journey-mark { width: 21px; height: 21px; }
        }
        @media (prefers-reduced-motion: reduce) {
          .qa-journey li { transition: none; }
        }
      `}</style>
    </ol>
  );
}
