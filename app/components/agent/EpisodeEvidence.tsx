"use client";

import { useState } from "react";
import type { TeachingScope } from "@/app/components/teaching/contracts";
import styles from "./agent.module.css";

interface Observation {
  id: string;
  kind: string;
  sequence: number;
  observation: string;
  timestamp: string;
  payload: unknown;
  turn_id?: string;
}

const EVENT_LABELS: Record<string, string> = {
  commitment: "最初的判断", student_attempt: "学生补充与修正",
  diagnosis_inference: "推理诊断 · 模型判断", teach_back: "回讲与解释评价",
  transfer_assigned: "迁移任务指派", solo_assigned: "独立任务指派",
  transfer_attempted: "迁移作答", transfer_failed: "任务评价 · 尚未通过",
  transfer_verified: "任务评价 · 通过当前合同", solo_verified: "独立作答评价",
  solo_exited: "退出独立模式", tool_observation: "确定性工具记录",
};

export function EpisodeEvidence({ scope, conversationId }: {
  scope: TeachingScope;
  conversationId: string;
}) {
  const [records, setRecords] = useState<Observation[] | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function open() {
    setPending(true);
    setError("");
    setRecords(null);
    try {
      const query = new URLSearchParams({
        course_id: scope.courseId, curriculum_edition_id: scope.curriculumEditionId,
      });
      const response = await fetch(`/api/teaching/threads/${conversationId}/state?${query}`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error("无法读取后端学习证据，请稍后重试。");
      const body = await response.json();
      if (body.conversation_id !== conversationId || !Array.isArray(body.learning_evidence)) {
        throw new Error("后端没有返回本次过程的学习证据。");
      }
      setRecords(body.learning_evidence.filter((item: Observation) =>
        item && typeof item.id === "string" && typeof item.observation === "string"
        && typeof item.kind === "string" && typeof item.timestamp === "string",
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "读取失败。");
    } finally {
      setPending(false);
    }
  }

  return <section className={styles.episodeEvidence} aria-label="本次原始学习证据" data-testid="episode-evidence">
    <button type="button" onClick={open} disabled={pending}>
      {pending ? "读取中…" : "回看本次原始学习证据"}
    </button>
    {error ? <p role="alert">{error}</p> : null}
    {records ? <>
      <p>后端持久记录 · {records.length} 条（最多展示 250 条）。未记录的内容不计为完成证据。</p>
      <p>学生原话是行动记录；诊断和解释评价包含模型判断；数值核验仅覆盖对应计算合同。</p>
      {records.map(record => <details key={record.id}>
        <summary>第 {record.sequence} 轮 · {EVENT_LABELS[record.kind] ?? record.kind}</summary>
        <p>{record.observation}</p>
        <time>{record.timestamp}</time>
        <small>事件 {record.id}{record.turn_id ? ` · 轮次 ${record.turn_id}` : ""} · {record.kind}</small>
        <pre>
          {JSON.stringify(record.payload, null, 2)}
        </pre>
      </details>)}
    </> : null}
  </section>;
}
