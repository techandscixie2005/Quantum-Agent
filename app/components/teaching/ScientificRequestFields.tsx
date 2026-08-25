"use client";

import type { Dispatch, SetStateAction } from "react";

import type { SupportedScientificRequest, TeachingMode } from "./contracts";
import styles from "./teaching.module.css";

export type ScientificChoice =
  | "none"
  | "symbolic_equivalence"
  | "numerical_normalization"
  | "two_level_simulation";

export type ScientificDraft = Readonly<{
  choice: ScientificChoice;
  left: string;
  right: string;
  symbols: string;
  symbolicTimeout: string;
  alphaReal: string;
  alphaImag: string;
  betaReal: string;
  betaImag: string;
  targetNorm: string;
  normalizationTolerance: string;
  rabiFrequency: string;
  detuning: string;
  duration: string;
  steps: string;
  simulationTolerance: string;
}>;

export function initialScientificDraft(mode: TeachingMode): ScientificDraft {
  const choice: ScientificChoice =
    mode === "run_experiments"
      ? "two_level_simulation"
      : mode === "review_derivations"
        ? "symbolic_equivalence"
        : "none";
  return {
    choice,
    left: "sin(x)**2 + cos(x)**2",
    right: "1",
    symbols: "x",
    symbolicTimeout: "2",
    alphaReal: "1",
    alphaImag: "0",
    betaReal: "0",
    betaImag: "0",
    targetNorm: "1",
    normalizationTolerance: "1e-10",
    rabiFrequency: "1",
    detuning: "0",
    duration: "3.141592653589793",
    steps: "101",
    simulationTolerance: "1e-8",
  };
}

function parsedNumber(value: string, label: string): number {
  if (value.trim() === "") throw new Error(`${label}不能为空。`);
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${label}必须是有限数值。`);
  return parsed;
}

function amplitude(real: string, imag: string, label: string) {
  return {
    real: parsedNumber(real, `${label}实部`),
    imag: parsedNumber(imag, `${label}虚部`),
  };
}

export function buildScientificRequest(draft: ScientificDraft): SupportedScientificRequest | null {
  if (draft.choice === "none") return null;
  if (draft.choice === "symbolic_equivalence") {
    const left = draft.left.trim();
    const right = draft.right.trim();
    if (!left || !right) throw new Error("符号等价验证需要左右两个表达式。");
    const symbols = draft.symbols
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return {
      kind: draft.choice,
      left,
      right,
      symbols,
      timeout_seconds: parsedNumber(draft.symbolicTimeout, "符号验证超时"),
    };
  }
  if (draft.choice === "numerical_normalization") {
    return {
      kind: draft.choice,
      state: [
        amplitude(draft.alphaReal, draft.alphaImag, "α"),
        amplitude(draft.betaReal, draft.betaImag, "β"),
      ],
      target_norm_squared: parsedNumber(draft.targetNorm, "目标范数平方"),
      absolute_tolerance: parsedNumber(draft.normalizationTolerance, "归一化容差"),
    };
  }
  return {
    kind: draft.choice,
    initial_state: [
      amplitude(draft.alphaReal, draft.alphaImag, "α"),
      amplitude(draft.betaReal, draft.betaImag, "β"),
    ],
    rabi_frequency: parsedNumber(draft.rabiFrequency, "Rabi 频率"),
    detuning: parsedNumber(draft.detuning, "失谐"),
    duration: parsedNumber(draft.duration, "演化时长"),
    steps: parsedNumber(draft.steps, "采样步数"),
    absolute_tolerance: parsedNumber(draft.simulationTolerance, "模拟容差"),
  };
}

function NumericField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step = "any",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
  step?: string;
}) {
  return (
    <label htmlFor={id}>
      {label}
      <input
        id={id}
        type="number"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        min={min}
        max={max}
        step={step}
        required
      />
    </label>
  );
}

export function ScientificRequestFields({
  draft,
  setDraft,
  disabled = false,
}: {
  draft: ScientificDraft;
  setDraft: Dispatch<SetStateAction<ScientificDraft>>;
  disabled?: boolean;
}) {
  const update = (key: keyof ScientificDraft, value: string) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  return (
    <fieldset className={styles.scienceFields} disabled={disabled}>
      <legend>科学验证（可选）</legend>
      <p>
        只发送下列有界、类型化参数。此页面不提供任意代码或宿主机命令执行。
      </p>
      <label htmlFor="scientific-kind">
        验证任务
        <select
          id="scientific-kind"
          value={draft.choice}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              choice: event.target.value as ScientificChoice,
            }))
          }
        >
          <option value="none">不运行科学工具</option>
          <option value="symbolic_equivalence">符号等价性（SymPy）</option>
          <option value="numerical_normalization">态矢归一化（NumPy）</option>
          <option value="two_level_simulation">双能级演化模拟（QuTiP）</option>
        </select>
      </label>

      {draft.choice === "symbolic_equivalence" ? (
        <div className={styles.scienceGrid} data-kind="symbolic">
          <label htmlFor="symbolic-left">
            左侧表达式
            <input
              id="symbolic-left"
              value={draft.left}
              onChange={(event) => update("left", event.target.value)}
              maxLength={1024}
              spellCheck={false}
              required
            />
          </label>
          <label htmlFor="symbolic-right">
            右侧表达式
            <input
              id="symbolic-right"
              value={draft.right}
              onChange={(event) => update("right", event.target.value)}
              maxLength={1024}
              spellCheck={false}
              required
            />
          </label>
          <label htmlFor="symbolic-symbols">
            符号（英文逗号分隔）
            <input
              id="symbolic-symbols"
              value={draft.symbols}
              onChange={(event) => update("symbols", event.target.value)}
              placeholder="x, n"
              spellCheck={false}
            />
          </label>
          <NumericField
            id="symbolic-timeout"
            label="最长验证时间 / s"
            value={draft.symbolicTimeout}
            onChange={(value) => update("symbolicTimeout", value)}
            min="0.1"
            max="5"
          />
        </div>
      ) : null}

      {draft.choice === "numerical_normalization" ? (
        <div className={styles.scienceGrid} data-kind="normalization">
          <NumericField id="norm-alpha-real" label="α 实部" value={draft.alphaReal} onChange={(value) => update("alphaReal", value)} />
          <NumericField id="norm-alpha-imag" label="α 虚部" value={draft.alphaImag} onChange={(value) => update("alphaImag", value)} />
          <NumericField id="norm-beta-real" label="β 实部" value={draft.betaReal} onChange={(value) => update("betaReal", value)} />
          <NumericField id="norm-beta-imag" label="β 虚部" value={draft.betaImag} onChange={(value) => update("betaImag", value)} />
          <NumericField id="norm-target" label="目标范数平方" value={draft.targetNorm} onChange={(value) => update("targetNorm", value)} min="0" max="1000000000000" />
          <NumericField id="norm-tolerance" label="绝对容差" value={draft.normalizationTolerance} onChange={(value) => update("normalizationTolerance", value)} min="1e-16" max="0.01" />
        </div>
      ) : null}

      {draft.choice === "two_level_simulation" ? (
        <>
          <p className={styles.fieldNote}>
            初态写作 α|0〉 + β|1〉。频率、失谐与时间采用同一套约定单位；结果不会自动赋予物理单位。
          </p>
          <div className={styles.scienceGrid} data-kind="simulation">
            <NumericField id="sim-alpha-real" label="α 实部" value={draft.alphaReal} onChange={(value) => update("alphaReal", value)} />
            <NumericField id="sim-alpha-imag" label="α 虚部" value={draft.alphaImag} onChange={(value) => update("alphaImag", value)} />
            <NumericField id="sim-beta-real" label="β 实部" value={draft.betaReal} onChange={(value) => update("betaReal", value)} />
            <NumericField id="sim-beta-imag" label="β 虚部" value={draft.betaImag} onChange={(value) => update("betaImag", value)} />
            <NumericField id="sim-rabi" label="Rabi 频率 Ω" value={draft.rabiFrequency} onChange={(value) => update("rabiFrequency", value)} min="-1000000" max="1000000" />
            <NumericField id="sim-detuning" label="失谐 Δ" value={draft.detuning} onChange={(value) => update("detuning", value)} min="-1000000" max="1000000" />
            <NumericField id="sim-duration" label="演化时长" value={draft.duration} onChange={(value) => update("duration", value)} min="1e-12" max="10000" />
            <NumericField id="sim-steps" label="采样步数" value={draft.steps} onChange={(value) => update("steps", value)} min="2" max="2001" step="1" />
            <NumericField id="sim-tolerance" label="绝对容差" value={draft.simulationTolerance} onChange={(value) => update("simulationTolerance", value)} min="1e-16" max="0.01" />
          </div>
        </>
      ) : null}
    </fieldset>
  );
}
