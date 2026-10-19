"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import type { AgentTraceDetail, TraceScope } from "./contracts";
import styles from "./trace-review.module.css";

const reviewSchema = z.object({
  review_id: z.string().uuid(), conversation_id: z.string().uuid(), source_turn_id: z.string().uuid(),
  reviewer_user_id: z.string().uuid(), reason: z.string(), follow_up: z.string(), probe: z.string(),
  decision: z.string(), created_at: z.string(),
});
const packageSchema = z.object({
  package_id: z.string(), version: z.string(), title: z.string(), validation_status: z.string(),
  objectives: z.array(z.object({ objective_id: z.string(), description: z.string() })),
  rubric: z.array(z.object({ criterion_id: z.string(), description: z.string(), meets: z.string(), partial: z.string(), needs_revision: z.string() })),
});

async function json(response: Response) {
  if (!response.ok) throw new Error(response.status === 403
    ? "只有本课程教师或管理员可以提交教学决定。" : "课程审阅请求失败，请刷新后重试。");
  return response.json();
}

export function ClassroomReviewPanel({ detail, scope }: { detail: AgentTraceDetail; scope: TraceScope }) {
  const query = new URLSearchParams({ course_id: scope.courseId, curriculum_edition_id: scope.curriculumEditionId });
  const url = `/api/teacher/conversations/${detail.conversation_id}/reviews?${query}`;
  const [reason, setReason] = useState("");
  const [decision, setDecision] = useState("needs_follow_up");
  const [followUp, setFollowUp] = useState("request_revision");
  const [probe, setProbe] = useState("");
  const [ratings, setRatings] = useState<Record<string, string>>({});
  const reviews = useQuery({ queryKey: ["classroom-reviews", scope, detail.conversation_id], queryFn: async () => {
    const parsed = z.array(reviewSchema).max(500).parse(await json(await fetch(url)));
    if (parsed.some(item => item.conversation_id !== detail.conversation_id)) throw new Error("审阅记录不属于当前学习过程。");
    return parsed;
  } });
  const packages = useQuery({ queryKey: ["classroom-packages", scope], queryFn: async () =>
    z.array(packageSchema).max(100).parse(await json(await fetch(`/api/teacher/course-packages?${query}`))),
  });
  const coursePackage = packages.data?.find(item => item.package_id === detail.course_package?.package_id
    && item.version === detail.course_package.version);
  const mutation = useMutation({ mutationFn: async () => {
    const saved = reviewSchema.parse(await json(await fetch(url, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        source_turn_id: detail.teaching_turn_id, decision, reason: reason.trim(), follow_up: followUp,
        probe: followUp === "continue" ? "" : probe.trim(), criterion_ratings: ratings,
      }) })));
    if (saved.conversation_id !== detail.conversation_id) throw new Error("审阅记录范围不匹配。");
    return saved;
  }, onSuccess: () => { setReason(""); setProbe(""); void reviews.refetch(); } });

  return <div className={styles.classroomReview} data-testid="classroom-review">
    <p>记录判断依据和下一次教学动作。模型诊断是待核实的假设；此处只保存教师实际提交的决定。</p>
    <a href={`/api/teaching/threads/${detail.conversation_id}/export?${query}`} download>导出本次完整证据链（JSON）</a>
    {coursePackage ? <details><summary>{coursePackage.title} · v{coursePackage.version} · 目标与量规</summary>
      <p>{coursePackage.validation_status}</p>
      {coursePackage.objectives.map(item => <p key={item.objective_id}>{item.objective_id} · {item.description}</p>)}
      {coursePackage.rubric.map(item => <label key={item.criterion_id}>
        <span>{item.criterion_id} · {item.description}</span>
        <small>达到：{item.meets}；部分达到：{item.partial}；需修订：{item.needs_revision}</small>
        <select aria-label={item.criterion_id} value={ratings[item.criterion_id] ?? "not_assessed"}
          onChange={event => setRatings(current => ({ ...current, [item.criterion_id]: event.target.value }))}>
          <option value="not_assessed">未评阅</option><option value="meets">达到</option>
          <option value="partial">部分达到</option><option value="needs_revision">需修订</option>
        </select>
      </label>)}
    </details> : null}
    <form onSubmit={event => { event.preventDefault(); mutation.mutate(); }}>
      <label>教师判断<select value={decision} onChange={event => setDecision(event.target.value)}>
        <option value="needs_follow_up">需要追问</option><option value="revise">需要修订</option><option value="confirmed">确认本次表现</option>
      </select></label>
      <label>判断依据（必填）<textarea aria-label="教师判断依据" maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label>后续教学动作<select aria-label="后续教学动作" value={followUp} onChange={event => setFollowUp(event.target.value)}>
        <option value="request_revision">要求修订作答</option><option value="revisit_prerequisite">核实先修概念</option><option value="continue">继续当前流程</option>
      </select></label>
      {followUp !== "continue" ? <label>下一轮具体追问（必填）<textarea aria-label="下一轮具体追问" maxLength={1000} value={probe} onChange={event => setProbe(event.target.value)} /></label> : null}
      <button disabled={mutation.isPending || detail.turn_status === "running" || !reason.trim() || (followUp !== "continue" && !probe.trim())}>
        {mutation.isPending ? "记录中…" : "记录教师决定"}
      </button>
    </form>
    {mutation.isError || reviews.isError ? <p role="alert">{mutation.error?.message ?? reviews.error?.message}</p> : null}
    {mutation.isSuccess ? <p role="status">教师决定已记录，将用于下一轮教学。</p> : null}
    {reviews.data?.map(item => <details key={item.review_id}><summary>{item.created_at} · {item.decision}</summary>
      <p>{item.reason}</p><p>{item.follow_up} · {item.probe}</p><small>教师 {item.reviewer_user_id} · 决定 {item.review_id}</small>
    </details>)}
  </div>;
}
