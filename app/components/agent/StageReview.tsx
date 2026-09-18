"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import {
  assertTeachingScope, parseTeachingTurnResult,
  type TeachingEvidence, type TeachingScope,
} from "@/app/components/teaching/contracts";
import { DerivationBridgePanel } from "./DerivationBridgePanel";
import styles from "./agent.module.css";

const AgentPlot = dynamic(() => import("./AgentPlot"), {
  ssr: false, loading: () => <p role="status">正在载入科学绘图…</p>,
});
const CodingArtifactPanel = dynamic(() => import("./CodingArtifactPanel"), {
  ssr: false, loading: () => <p role="status">正在载入计算产物…</p>,
});

export function StageReview({ scope, conversationId, stage, onSource, onReturn }: {
  scope: TeachingScope; conversationId: string; stage: string;
  onSource: (source: TeachingEvidence) => void; onReturn: () => void;
}) {
  const query = useQuery({
    queryKey: ["stage-review", scope.courseId, scope.curriculumEditionId, conversationId, stage],
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const search = new URLSearchParams({ course_id: scope.courseId,
        curriculum_edition_id: scope.curriculumEditionId, review_stage: stage });
      const response = await fetch(`/api/teaching/threads/${conversationId}/state?${search}`, {
        signal, cache: "no-store",
      });
      if (!response.ok) throw new Error(response.status === 423
        ? "Solo 期间不能回看解答。" : "该阶段没有可回看的持久记录，或当前无权访问。");
      const body = await response.json();
      const result = parseTeachingTurnResult(body.result);
      assertTeachingScope(result, scope, result.policy.mode);
      if (result.conversation_id !== conversationId || body.review_stage !== stage) {
        throw new Error("回看记录与当前学习过程不匹配。");
      }
      return { result, sequence: Number(body.sequence), attempt: typeof body.student_attempt === "string" ? body.student_attempt : "" };
    },
    retry: false,
  });
  const data = query.data;
  const result = data?.result;
  const scientific = result?.scientific_results ?? [];
  return <section className={styles.historyStage} aria-label="已完成阶段回看" data-testid="stage-review">
    <header><p>持久记录回看{data ? ` · 第 ${data.sequence} 轮 · ${result?.turn_id}` : ""}</p>
      <button type="button" onClick={onReturn}>返回当前任务</button></header>
    {query.isPending ? <p role="status">读取本次学习记录…</p> : null}
    {query.error ? <p role="alert">{query.error.message} <button onClick={() => void query.refetch()}>重试</button></p> : null}
    {result ? <>
      {data?.attempt ? <blockquote><strong>学生提交</strong><p>{data.attempt}</p></blockquote> : null}
      {stage === "sources" ? result.evidence_packet.evidence.map(source => <article key={source.evidence_id}>
        <h2>{source.document_title}</h2><button onClick={() => onSource(source)}>打开课程来源</button>
      </article>) : null}
      {stage === "bridge" && result.response.derivation_bridge ? <DerivationBridgePanel
        bridge={result.response.derivation_bridge} evidence={result.evidence_packet} /> : null}
      {stage === "verify" ? <div className={styles.reviewComputation}>
        {result.code_artifact ? <CodingArtifactPanel run={result.code_artifact} /> : null}
        {scientific.map(item => <article key={item.inputs_sha256}>
          <h2>{item.kind === "rectangular_barrier_tunnelling" ? "有限矩形势垒" : item.kind} · {item.status.toUpperCase()}</h2>
          {item.visualization ? <AgentPlot spec={item.visualization} current={typeof item.metrics.T === "number" && typeof item.metrics.barrier_width_m === "number" ? { x: item.metrics.barrier_width_m, y: item.metrics.T } : undefined} /> : null}
          {typeof item.metrics.T === "number" && typeof item.metrics.R === "number" ?
            <div className={styles.tunnellingMetrics}><span>透射 T = <strong>{item.metrics.T.toPrecision(6)}</strong></span>
              <span>反射 R = <strong>{item.metrics.R.toPrecision(6)}</strong></span></div> : null}
          <details><summary>核验记录与任务版本</summary><small>{item.inputs_sha256}</small>
            <pre>{JSON.stringify(item.metrics, null, 2)}</pre></details>
        </article>)}
      </div> : null}
      {!["sources", "bridge", "verify"].includes(stage) ? <>
        {result.learning_native?.transfer ? <blockquote>{result.learning_native.transfer.prompt}</blockquote> : null}
        {result.learning_native?.teach_back ? <section aria-label="当时的解释评价">
          <h2>解释评价 · 模型判断</h2>
          <p>{result.learning_native.completed_stages.includes("teach_back") ? "通过当时的解释评价 · 非数值科学证明" : "已记录，仍需补充"}</p>
          {result.learning_native.teach_back.covered_relations.map((finding, index) => <p key={`covered-${index}`}>{finding.description}</p>)}
          {result.learning_native.teach_back.missing_relations.map((finding, index) => <p key={`missing-${index}`}>待补充：{finding.description}</p>)}
          <p>{result.learning_native.teach_back.recommended_probe}</p>
        </section> : null}
        <h2>{result.response.orientation}</h2>
        {result.response.claims.map((claim, index) => <p key={index}>{claim.text}</p>)}
        <p>{result.response.next_question}</p>
      </> : null}
      <p>这是当时记录，不会推进当前阶段或重新提交作答。</p>
    </> : null}
  </section>;
}
