"use client";

import { useId } from "react";

import { locatorLabel } from "../knowledge/contracts";
import type {
  ScientificResult,
  TeachingEvidence,
  TeachingTurnResult,
  VisualizationSpec,
} from "./contracts";
import {
  RELEASE_LABELS,
  STATUS_LABELS,
  SUPPORT_LABELS,
  WORKFLOW_LABELS,
  reasonLabel,
} from "./presentation";
import styles from "./teaching.module.css";

function shortHash(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function EvidenceCard({ evidence, index }: { evidence: TeachingEvidence; index: number }) {
  return (
    <article className={styles.evidenceCard} id={`evidence-${evidence.evidence_id}`}>
      <div className={styles.evidenceLevel} aria-hidden="true">
        <span />
      </div>
      <div className={styles.evidenceHeading}>
        <span className={styles.sourceIndex}>E{String(index + 1).padStart(2, "0")}</span>
        <div>
          <h4>{evidence.document_title}</h4>
          <p>
            {evidence.source_file_name} · v{evidence.document_version} · {locatorLabel(evidence.locator)}
          </p>
        </div>
        <span className={styles.authorityBadge}>课程原文</span>
      </div>
      <blockquote>{evidence.evidence_snippet}</blockquote>
      <details>
        <summary>查看原始分块与完整溯源</summary>
        <div className={styles.sourceChunk}>
          <p>{evidence.source_chunk}</p>
          <dl>
            <div><dt>章节</dt><dd>{evidence.chapter ?? "未标注"}</dd></div>
            <div><dt>节路径</dt><dd>{evidence.section_path.length ? evidence.section_path.join(" / ") : "未标注"}</dd></div>
            <div><dt>Evidence ID</dt><dd><code>{evidence.evidence_id}</code></dd></div>
            <div><dt>Chunk ID</dt><dd><code>{evidence.chunk_id}</code></dd></div>
            <div><dt>文件 SHA-256</dt><dd><code title={evidence.source_file_sha256}>{shortHash(evidence.source_file_sha256)}</code></dd></div>
            <div><dt>分块 SHA-256</dt><dd><code title={evidence.source_chunk_sha256}>{shortHash(evidence.source_chunk_sha256)}</code></dd></div>
            <div><dt>证据 SHA-256</dt><dd><code title={evidence.evidence_sha256}>{shortHash(evidence.evidence_sha256)}</code></dd></div>
          </dl>
          <p className={styles.channelLine}>
            检索通道：{evidence.contributions.map((item) => `${item.channel} #${item.rank}`).join(" · ")}
          </p>
        </div>
      </details>
    </article>
  );
}

function sampledIndices(length: number, maxPoints: number): number[] {
  if (length <= maxPoints) return Array.from({ length }, (_, index) => index);
  const selected = new Set<number>([0, length - 1]);
  for (let index = 0; index < maxPoints; index += 1) {
    selected.add(Math.round((index * (length - 1)) / (maxPoints - 1)));
  }
  return [...selected].sort((left, right) => left - right);
}

function linePath(
  x: readonly number[],
  y: readonly number[],
  xMin: number,
  xRange: number,
  yMin: number,
  yRange: number,
): string {
  const indices = sampledIndices(x.length, 160);
  return indices
    .map((index, pathIndex) => {
      const px = 46 + ((x[index]! - xMin) / xRange) * 548;
      const py = 18 + (1 - (y[index]! - yMin) / yRange) * 174;
      return `${pathIndex === 0 ? "M" : "L"}${px.toFixed(2)} ${py.toFixed(2)}`;
    })
    .join(" ");
}

function ScientificChart({ spec }: { spec: VisualizationSpec }) {
  const titleId = useId();
  let xMin = spec.x[0] ?? 0;
  let xMax = xMin;
  let yMin = spec.series[0]?.y[0] ?? 0;
  let yMax = yMin;
  for (const value of spec.x) {
    xMin = Math.min(xMin, value);
    xMax = Math.max(xMax, value);
  }
  for (const series of spec.series) {
    for (const value of series.y) {
      yMin = Math.min(yMin, value);
      yMax = Math.max(yMax, value);
    }
  }
  const xRange = xMax === xMin ? 1 : xMax - xMin;
  const yRange = yMax === yMin ? 1 : yMax - yMin;
  const tableIndices = sampledIndices(spec.x.length, 18);
  return (
    <figure className={styles.scienceFigure}>
      <figcaption>
        <strong>{spec.title}</strong>
        <span>
          {spec.renderer.name} {spec.renderer.version} · {spec.x.length} 个数据点 · render{" "}
          <code title={spec.rendering_sha256}>{shortHash(spec.rendering_sha256)}</code>
        </span>
      </figcaption>
      <svg viewBox="0 0 620 230" role="img" aria-labelledby={titleId}>
        <title id={titleId}>
          {spec.title}；横轴 {spec.x_label}，纵轴 {spec.y_label}，包含 {spec.series.map((item) => item.label).join("、")}
        </title>
        <path className={styles.chartAxis} d="M46 18V192H594" />
        {[0, 1, 2, 3].map((line) => {
          const y = 18 + (line * 174) / 3;
          return <path key={line} className={styles.chartGrid} d={`M46 ${y}H594`} />;
        })}
        {spec.series.map((series, index) => (
          <path
            key={series.label}
            className={styles[`chartSeries${index % 4}`]}
            d={linePath(spec.x, series.y, xMin, xRange, yMin, yRange)}
          />
        ))}
        <text x="46" y="214">{xMin.toPrecision(4)}</text>
        <text x="594" y="214" textAnchor="end">{xMax.toPrecision(4)}</text>
        <text x="8" y="22">{yMax.toPrecision(4)}</text>
        <text x="8" y="192">{yMin.toPrecision(4)}</text>
      </svg>
      <div className={styles.chartLegend} aria-label="图例">
        {spec.series.map((series, index) => (
          <span key={series.label} data-series={index % 4}><i aria-hidden="true" />{series.label}</span>
        ))}
      </div>
      <details>
        <summary>查看可访问的数据抽样</summary>
        <div className={styles.chartTableWrap}>
          <table>
            <caption>
              共 {spec.x.length} 行；为控制页面大小，显示均匀抽取的 {tableIndices.length} 行。输入与渲染摘要保留完整数据的校验标识。
            </caption>
            <thead>
              <tr>
                <th scope="col">序号</th>
                <th scope="col">{spec.x_label}</th>
                {spec.series.map((series) => <th scope="col" key={series.label}>{series.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {tableIndices.map((index) => (
                <tr key={index}>
                  <th scope="row">{index + 1}</th>
                  <td>{spec.x[index]?.toPrecision(8)}</td>
                  {spec.series.map((series) => <td key={series.label}>{series.y[index]?.toPrecision(8)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function ScientificRecord({ result, index }: { result: ScientificResult; index: number }) {
  return (
    <article className={styles.scientificRecord}>
      <header>
        <span className={styles.sourceIndex}>T{String(index + 1).padStart(2, "0")}</span>
        <div>
          <h4>{result.kind.replaceAll("_", " ")}</h4>
          <p>{result.tool.name} {result.tool.version} · 方法：{result.method}</p>
        </div>
        <span className={styles[`scienceStatus_${result.status}`]}>{result.status}</span>
      </header>
      <div className={styles.scienceColumns}>
        <section>
          <h5>观察</h5>
          <ul>{result.observations.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
        <section>
          <h5>局限</h5>
          <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      </div>
      {Object.keys(result.metrics).length ? (
        <dl className={styles.metrics}>
          {Object.entries(result.metrics).map(([key, value]) => (
            <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
          ))}
        </dl>
      ) : null}
      {result.error_code ? <p className={styles.toolError}>工具错误码：<code>{result.error_code}</code></p> : null}
      {result.visualization ? <ScientificChart spec={result.visualization} /> : null}
      <p className={styles.hashLine}>输入 SHA-256 <code title={result.inputs_sha256}>{shortHash(result.inputs_sha256)}</code></p>
    </article>
  );
}

function WorkflowTrace({ result }: { result: TeachingTurnResult }) {
  return (
    <section className={styles.tracePanel} aria-labelledby="workflow-trace-title">
      <div className={styles.sectionHeading}>
        <div>
          <p className={styles.eyebrow}>DETERMINISTIC TRACE</p>
          <h3 id="workflow-trace-title">固定教学工作流</h3>
        </div>
        <div className={styles.validationSeal}>
          <strong>校验通过</strong>
          <span>引用 ID · 课程原文 · 科学结果 ID</span>
          <code>{result.workflow_version}</code>
        </div>
      </div>
      {result.validation.warnings.length ? (
        <div className={styles.validationWarnings}>
          {result.validation.warnings.map((warning) => <code key={warning}>{warning}</code>)}
        </div>
      ) : null}
      <ol>
        {result.trace.map((step, index) => (
          <li key={step.name} data-status={step.status}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{WORKFLOW_LABELS[step.name]}</strong><small>{step.detail}</small></div>
            <em>{step.status}</em>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function TeachingResultRecord({ result }: { result: TeachingTurnResult }) {
  const coverage = result.evidence_packet.coverage;
  const graphSummary = result.evidence_packet.graph_nodes.length
    ? `${result.evidence_packet.graph_nodes.length} 个课程概念、${result.evidence_packet.graph_edges.length} 条关系用于上下文；原始依据仍以右侧课程证据为准。`
    : "本轮没有返回已批准的图谱上下文。";
  return (
    <div className={styles.resultGrid}>
      <section
        className={styles.responseColumn}
        id="turn-result"
        tabIndex={-1}
        aria-label="本轮教学记录"
      >
        <section className={styles.answerSheet} aria-labelledby="answer-title">
          <header>
            <div>
              <p className={styles.eyebrow}>TEACHING RECORD</p>
              <h2 id="answer-title">本轮教学回应</h2>
            </div>
            <span className={styles[`responseStatus_${result.response.status}`]}>
              {STATUS_LABELS[result.response.status]}
            </span>
          </header>
          <p className={styles.orientation}>{result.response.orientation}</p>
          {result.response.claims.length ? (
            <ol className={styles.claimList}>
              {result.response.claims.map((claim, index) => (
                <li key={`${claim.support_basis}-${index}`}>
                  <div>
                    <span className={styles[`support_${claim.support_basis}`]}>
                      {SUPPORT_LABELS[claim.support_basis]}
                    </span>
                    <span className={styles.claimNumber}>声明 {index + 1}</span>
                  </div>
                  <p>{claim.text}</p>
                  {claim.evidence_ids.length ? (
                    <nav aria-label={`声明 ${index + 1} 的课程引用`}>
                      {claim.evidence_ids.map((id) => {
                        const evidenceIndex = result.evidence_packet.evidence.findIndex((item) => item.evidence_id === id);
                        return <a key={id} href={`#evidence-${id}`}>证据 E{String(evidenceIndex + 1).padStart(2, "0")}</a>;
                      })}
                    </nav>
                  ) : null}
                  {claim.scientific_result_ids.length ? (
                    <p className={styles.resultIds}>科学结果：{claim.scientific_result_ids.join(" · ")}</p>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <div className={styles.honestEmpty}>
              <strong>没有可显示的事实声明</strong>
              <p>系统未用模型文本填补缺少的课程证据。请缩小问题范围，或请教师检查材料发布状态。</p>
            </div>
          )}
          <aside className={styles.nextQuestion}>
            <span>下一步</span>
            <p>{result.response.next_question}</p>
          </aside>
          {result.response.limitations.length ? (
            <details className={styles.limitations} open>
              <summary>本轮局限</summary>
              <ul>{result.response.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          ) : null}
        </section>

        <section className={styles.policyDiagnosis}>
          <article>
            <p className={styles.eyebrow}>ANSWER POLICY</p>
            <h3>{RELEASE_LABELS[result.release.release_level]}</h3>
            <p>{reasonLabel(result.release.reason_code)}</p>
            <dl>
              <div><dt>原因码</dt><dd><code>{result.release.reason_code}</code></dd></div>
              <div><dt>观察到的尝试</dt><dd>{result.release.attempts_observed}</dd></div>
              <div><dt>政策来源</dt><dd>{result.policy.source === "teacher_configured" ? "教师配置" : "安全默认"}</dd></div>
              <div><dt>教学动作</dt><dd>{result.release.action}</dd></div>
            </dl>
          </article>
          <article data-diagnosis={result.diagnosis.status}>
            <p className={styles.eyebrow}>STUDENT-MODEL-LITE</p>
            <h3>
              {result.diagnosis.status === "model_inference"
                ? "模型推断（不是掌握度事实）"
                : result.diagnosis.status === "observed"
                  ? "基于本轮观察"
                  : "证据不足，暂不诊断"}
            </h3>
            <p>{result.diagnosis.summary}</p>
            {result.diagnosis.likely_misconception ? (
              <blockquote>可能的误区：{result.diagnosis.likely_misconception}</blockquote>
            ) : null}
            <small>依据：{result.diagnosis.observation_basis.length ? result.diagnosis.observation_basis.join(" · ") : "无"}</small>
          </article>
        </section>

        {result.scientific_results.length ? (
          <section className={styles.scienceResults} aria-labelledby="science-results-title">
            <div className={styles.sectionHeading}>
              <div><p className={styles.eyebrow}>TOOL-VERIFIED</p><h3 id="science-results-title">科学验证记录</h3></div>
              <span>{result.scientific_results.length} 项</span>
            </div>
            {result.scientific_results.map((item, index) => (
              <ScientificRecord key={`${item.kind}-${item.inputs_sha256}`} result={item} index={index} />
            ))}
          </section>
        ) : null}

        <WorkflowTrace result={result} />
      </section>

      <aside className={styles.evidenceRail} aria-labelledby="evidence-title">
        <div className={styles.evidenceRailHeader}>
          <div><p className={styles.eyebrow}>PROVENANCE RAIL</p><h2 id="evidence-title">课程依据</h2></div>
          <span data-coverage={coverage}>{coverage}</span>
        </div>
        <p className={styles.graphSummary}>{graphSummary}</p>
        {result.evidence_packet.degraded_channels.length ? (
          <div className={styles.degradedNotice}>
            降级通道：{result.evidence_packet.degraded_channels.join("、")}。其余通道的结果不会冒充完整检索。
          </div>
        ) : null}
        {result.evidence_packet.warnings.map((warning) => (
          <p className={styles.packetWarning} key={warning}>{warning}</p>
        ))}
        {result.evidence_packet.evidence.length ? (
          <div className={styles.evidenceList}>
            {result.evidence_packet.evidence.map((evidence, index) => (
              <EvidenceCard evidence={evidence} index={index} key={evidence.evidence_id} />
            ))}
          </div>
        ) : (
          <div className={styles.honestEmpty}>
            <strong>未找到已批准的课程证据</strong>
            <p>本轮没有原始课程片段可引用。系统不会把 Neo4j 上下文或模型文字当作来源材料。</p>
          </div>
        )}
        <footer className={styles.packetFooter}>
          <span>EvidencePacket</span>
          <code>{result.evidence_packet.id}</code>
          <span>Turn</span>
          <code>{result.turn_id}</code>
        </footer>
      </aside>
    </div>
  );
}
