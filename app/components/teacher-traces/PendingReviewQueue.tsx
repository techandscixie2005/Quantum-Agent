"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { parseHitlInterruptResponse, assertHitlScope } from "@/app/components/teaching/contracts";
import type { TraceScope } from "./contracts";
import { parsePendingReviews, type PendingReview } from "./pending-contracts";
import styles from "./trace-review.module.css";

async function payload(response: Response): Promise<unknown> {
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message ?? "无法读取或恢复人工复核。");
  return data;
}

/** Real SQL pauses, including the first turn before a completed trace exists. */
export function PendingReviewQueue({ scope }: Readonly<{ scope: TraceScope }>) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<PendingReview | null>(null);
  const [note, setNote] = useState("");
  const [receipt, setReceipt] = useState("");
  const client = useQueryClient();
  const params = new URLSearchParams({ course_id: scope.courseId, curriculum_edition_id: scope.curriculumEditionId });
  const list = useQuery({
    queryKey: ["teacher-pending-reviews", scope.courseId, scope.curriculumEditionId, offset],
    queryFn: async () => parsePendingReviews(await payload(await fetch(`/api/teacher/pending-reviews?${params}&offset=${offset}`)), scope),
    refetchInterval: 15_000,
  });
  const detail = useQuery({
    queryKey: ["teacher-pending-interrupt", scope.courseId, scope.curriculumEditionId, selected?.interrupt_id],
    enabled: selected !== null,
    queryFn: async () => {
      if (!selected) throw new Error("请选择待复核回合。");
      const value = parseHitlInterruptResponse(await payload(await fetch(
        `/api/teacher/conversations/${selected.conversation_id}/interrupt?${params}`,
      )));
      assertHitlScope(value, scope, selected.mode);
      if (value.turn_id !== selected.turn_id || value.interrupt.interrupt_id !== selected.interrupt_id) {
        throw new Error("暂停状态已变化，请刷新队列。");
      }
      return value;
    },
    retry: false,
  });
  const decision = useMutation({
    mutationFn: async (input: { item: PendingReview; action: "approve" | "reject"; note: string }) => {
      await payload(await fetch(`/api/teacher/conversations/${input.item.conversation_id}/resume?${params}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interrupt_id: input.item.interrupt_id, action: input.action, note: input.note }),
      }));
    },
    onSuccess: () => {
      setReceipt("复核决定已保存。请检查更新后的学习记录与后续教学动作。");
      setSelected(null); setNote("");
      void client.invalidateQueries({ queryKey: ["teacher-pending-reviews"] });
      void client.invalidateQueries({ queryKey: ["teacher-trace-list"] });
    },
  });
  return <section className={styles.pendingQueue} aria-label="待人工复核队列">
    <h2>待人工复核</h2>
    <p>包含尚未生成完成 trace 的首轮暂停。批准或拒绝均需填写理由；审批会恢复实际教学执行。</p>
    <button type="button" onClick={() => void list.refetch()}>刷新待复核队列</button>
    {list.error ? <p role="alert">{list.error.message}</p> : null}
    {list.isPending ? <p role="status">读取已保存的暂停…</p> : null}
    {list.data?.items.length === 0 ? <p>当前课程版本没有待处理暂停。</p> : null}
    <ul>{list.data?.items.map((item) => <li key={item.interrupt_id}>
      <button type="button" disabled={decision.isPending} onClick={() => {
        setSelected(item); setNote(""); setReceipt(""); decision.reset();
      }}>{item.student_display_name} · {item.reasons.join(" / ")} · {item.turn_id.slice(0, 8)}</button>
    </li>)}</ul>
    <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>上一页</button>{" "}
    <button disabled={!list.data?.has_more} onClick={() => setOffset(offset + 25)}>下一页</button>
    {selected ? <div>
      <h3>回合 {selected.turn_id}</h3>
      {detail.isPending ? <p>读取拟议响应与检查结果…</p> : null}
      {detail.error ? <p role="alert">{detail.error.message}</p> : null}
      {detail.data ? <>
        <p>{detail.data.interrupt.reasons.join(" / ")}</p>
        <h4>拟议说明</h4>
        <p>{detail.data.artifacts.proposed_response.orientation || "没有额外说明。"}</p>
        <ul>{detail.data.artifacts.proposed_response.claims.map((claim, index) =>
          <li key={index}>{claim.text}</li>)}</ul>
        <p><strong>下一步追问：</strong>{detail.data.artifacts.proposed_response.next_question}</p>
        <h4>课程依据</h4>
        {detail.data.artifacts.evidence_packet.evidence.map((source) => <blockquote key={source.evidence_id}>
          <strong>{source.document_title}</strong><p>{source.evidence_snippet}</p>
        </blockquote>)}
        {detail.data.artifacts.evidence_packet.evidence.length === 0 ? <p>没有足够课程依据，请先核实来源。</p> : null}
        <p>自动约束检查：{detail.data.artifacts.validation.passed ? "通过当前检查范围" : "未通过"}。这不代表所有物理表述正确。</p>
        <a href={`/api/teaching/threads/${selected.conversation_id}/export?${params}`} download>导出原答与执行证据（JSON）</a>
        <details><summary>检查拟议响应、来源与验证</summary><pre>{JSON.stringify(detail.data.artifacts, null, 2)}</pre></details>
        <label>复核理由<textarea maxLength={4000} value={note} disabled={decision.isPending || Boolean(decision.error)} onChange={(event) => setNote(event.target.value)} /></label>
        {(["approve", "reject"] as const).map((action) => <button key={action} type="button"
          disabled={!note.trim() || decision.isPending || Boolean(decision.error) || !detail.data?.interrupt.staff_allowed_actions.includes(action)}
          onClick={() => decision.mutate({ item: selected, action, note: note.trim() })}>
          {action === "approve" ? "批准并恢复执行" : "拒绝本回合"}
        </button>)}
      </> : null}
      {decision.error ? <p role="alert">{decision.error.message} 输入与原决定已保留。
        <button type="button" disabled={decision.isPending} onClick={() => {
          if (decision.variables) decision.mutate(decision.variables);
        }}>重试同一复核决定</button>
        <button type="button" onClick={() => decision.reset()}>重新检查后编辑决定</button>
      </p> : null}
    </div> : null}
    {receipt ? <p role="status">{receipt}</p> : null}
  </section>;
}
