"use client";

import katex from "katex";
import { useMemo } from "react";

export function AgentEquation({ latex, display = true }: { latex: string; display?: boolean }) {
  const markup = useMemo(
    () =>
      katex.renderToString(latex, {
        displayMode: display,
        output: "htmlAndMathml",
        strict: "warn",
        throwOnError: false,
        trust: false,
      }),
    [display, latex],
  );
  return (
    <span
      aria-label={`LaTeX: ${latex}`}
      dangerouslySetInnerHTML={{ __html: markup }}
    />
  );
}

