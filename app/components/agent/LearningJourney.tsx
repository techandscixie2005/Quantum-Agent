"use client";

import { Check } from "lucide-react";

import type { LearningNativeTurnState, LearningStage } from "@/app/components/teaching/contracts";

type JourneySegment = Readonly<{
  label: string;
  stage: LearningStage;
}>;

const JOURNEY: readonly JourneySegment[] = [
  { label: "预测", stage: "predict" },
  { label: "理解", stage: "diagnose" },
  { label: "验证", stage: "verify" },
  { label: "讲解", stage: "explain" },
  { label: "迁移", stage: "transfer" },
];

function stageCompleted(state: LearningNativeTurnState, stage: LearningStage): boolean {
  return state.completed_stages.includes(stage);
}

function stageActive(state: LearningNativeTurnState, stage: LearningStage): boolean {
  return state.current_stage === stage;
}

export function LearningJourney({ state }: { state: LearningNativeTurnState | null }) {
  if (!state) return null;
  const loopDone = state.phase === "complete";
  return (
    <ol className="qa-journey" aria-label="学习旅程" data-testid="learning-journey">
      {JOURNEY.map((segment, index) => {
        const done = loopDone || stageCompleted(state, segment.stage);
        const active = !done && stageActive(state, segment.stage);
        const stateAttr = done ? "done" : active ? "active" : "idle";
        return (
          <li key={segment.stage} data-state={stateAttr} data-stage={segment.stage}>
            <span className="qa-journey-mark">
              {done ? <Check size={12} aria-hidden="true" /> : String(index + 1).padStart(2, "0")}
            </span>
            <span className="qa-journey-label">{segment.label}</span>
          </li>
        );
      })}
      <style>{`
        .qa-journey {
          list-style: none;
          display: flex;
          align-items: center;
          gap: 8px;
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
          font-size: 11px;
          letter-spacing: .02em;
        }
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
        .qa-journey li:not(:last-child)::after {
          content: "";
          width: 18px;
          height: 1px;
          background: var(--line, #dcded7);
          margin: 0 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .qa-journey li { transition: none; }
        }
      `}</style>
    </ol>
  );
}
