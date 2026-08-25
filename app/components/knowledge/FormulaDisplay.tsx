"use client";

import katex from "katex";
import { useEffect, useRef } from "react";

import styles from "./phase-one.module.css";

export function FormulaDisplay({ latex }: { latex: string }) {
  const formulaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = formulaRef.current;
    if (!element) return;
    element.textContent = latex;
    katex.render(latex, element, {
      throwOnError: false,
      strict: "warn",
      trust: false,
      displayMode: true,
    });
  }, [latex]);

  return (
    <div className={styles.formulaBlock}>
      <div ref={formulaRef} aria-label={`LaTeX 公式：${latex}`} />
      <code>{latex}</code>
    </div>
  );
}
