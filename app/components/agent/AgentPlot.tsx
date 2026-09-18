"use client";

import PlotModule from "react-plotly.js";
import { useState, type ComponentType } from "react";
import type { PlotParams } from "react-plotly.js";

import type { VisualizationSpec } from "@/app/components/teaching/contracts";

// react-plotly.js publishes a Babel CommonJS default. Production bundlers can
// retain that namespace wrapper; React needs the actual component constructor.
const Plot = (typeof PlotModule === "object" && "default" in PlotModule
  ? (PlotModule as unknown as { default: ComponentType<PlotParams> }).default
  : PlotModule) as ComponentType<PlotParams>;

export default function AgentPlot({ spec, current }: {
  spec: VisualizationSpec;
  current?: { x: number; y: number };
}) {
  const [view, setView] = useState<"plot" | "data">("plot");
  const widthScan = spec.x_label === "barrier width (m)";
  const scale = widthScan ? 1e9 : 1;
  const xLabel = widthScan ? "完整势垒宽度 a (nm)" : spec.x_label;
  return <section aria-label={spec.title}>
    <div role="group" aria-label="计算产物视图" style={{ display: "flex", gap: 8 }}>
      <button type="button" aria-pressed={view === "plot"} onClick={() => setView("plot")}>Plot</button>
      <button type="button" aria-pressed={view === "data"} onClick={() => setView("data")}>Data</button>
    </div>
    {view === "data" ? <div style={{ maxHeight: 330, overflow: "auto" }}>
      <table><caption>同一核验产物的扫描数据</caption><thead><tr><th>{xLabel}</th>
        {spec.series.map(series => <th key={series.label}>{series.label}</th>)}
      </tr></thead><tbody>{spec.x.map((x, index) => <tr key={index}>
        <td>{(x * scale).toPrecision(6)}</td>
        {spec.series.map(series => <td key={series.label}>{series.y[index].toPrecision(8)}</td>)}
      </tr>)}</tbody></table>
    </div> : <Plot
      data={[...spec.series.map((series) => ({
        x: spec.x.map(x => x * scale),
        y: [...series.y],
        name: series.label,
        mode: "lines" as const,
        type: "scatter" as const,
        line: { width: 2, color: "#1c6b56" },
      })), ...(current ? [{ x: [current.x * scale], y: [current.y],
        name: "当前任务", mode: "markers" as const, type: "scatter" as const,
        marker: { color: "#123e32", size: 10 },
      }] : [])]}
      layout={{
        autosize: true,
        height: 330,
        margin: { l: 58, r: 18, t: 32, b: 50 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { family: "Geist, sans-serif", color: "#53615b", size: 11 },
        xaxis: { title: { text: xLabel }, gridcolor: "#e5e4dd" },
        yaxis: { title: { text: spec.y_label }, gridcolor: "#e5e4dd" },
        legend: { orientation: "h", y: 1.12 },
        showlegend: spec.series.length > 1,
      }}
      config={{ displaylogo: false, responsive: true, scrollZoom: false }}
      style={{ width: "100%" }}
      useResizeHandler
    /> }
  </section>;
}
