"use client";

import Plot from "react-plotly.js";

import type { VisualizationSpec } from "@/app/components/teaching/contracts";

export default function AgentPlot({ spec }: { spec: VisualizationSpec }) {
  return (
    <Plot
      data={spec.series.map((series) => ({
        x: [...spec.x],
        y: [...series.y],
        name: series.label,
        mode: "lines" as const,
        type: "scatter" as const,
        line: { width: 2 },
      }))}
      layout={{
        autosize: true,
        height: 330,
        margin: { l: 58, r: 18, t: 32, b: 50 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { family: "Geist, sans-serif", color: "#53615b", size: 11 },
        xaxis: { title: { text: spec.x_label }, gridcolor: "#e5e4dd" },
        yaxis: { title: { text: spec.y_label }, gridcolor: "#e5e4dd" },
        legend: { orientation: "h", y: 1.12 },
        showlegend: spec.series.length > 1,
      }}
      config={{ displaylogo: false, responsive: true, scrollZoom: false }}
      style={{ width: "100%" }}
      useResizeHandler
    />
  );
}

