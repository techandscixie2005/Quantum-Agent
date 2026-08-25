"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  WORKFLOW_ORDER,
  assertTeachingScope,
  parseTeachingApiError,
  parseTeachingTurnRequest,
  parseTeachingTurnResult,
  type TeachingMode,
  type TeachingScope,
  type TeachingTurnResult,
} from "./contracts";
import { ModeIcon } from "./ModeIcon";
import { MODE_COPY, WORKFLOW_LABELS } from "./presentation";
import {
  ScientificRequestFields,
  buildScientificRequest,
  initialScientificDraft,
  type ScientificDraft,
} from "./ScientificRequestFields";
import { TeachingResultRecord } from "./TeachingResult";
import styles from "./teaching.module.css";

type RequestState = "idle" | "submitting" | "validating" | "complete" | "failed";

function scopedHref(scope: TeachingScope, mode: TeachingMode): string {
  const params = new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
    mode,
  });
  return `/course?${params.toString()}`;
}

function parseCompletedSse(value: string): unknown {
  const blocks = value.replace(/\r\n/g, "\n").split("\n\n");
  let completed: unknown;
  let failureCode: string | null = null;
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    let data: unknown;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      throw new Error("教学事件流包含无法解析的数据。");
    }
    if (event === "workflow.completed") completed = data;
    if (event === "workflow.failed") {
      const code =
        typeof data === "object" && data !== null && !Array.isArray(data)
          ? (data as Record<string, unknown>).code
          : null;
      failureCode = typeof code === "string" ? code : "WORKFLOW_FAILED";
    }
  }
  if (failureCode === "CONVERSATION_CONFLICT") {
    throw new Error("这段学习记录已由另一个请求更新。输入已保留，请重试或开始新记录。");
  }
  if (failureCode === "RETRIEVAL_UNAVAILABLE") {
    throw new Error("课程证据检索当前不可用。系统没有生成替代答案，请稍后重试。");
  }
  if (failureCode) throw new Error("教学工作流未完成；系统没有显示不完整结果。");
  if (completed === undefined) throw new Error("教学事件流没有返回完成记录。");
  return completed;
}

function WaitingTrace({ state }: { state: RequestState }) {
  return (
    <section className={styles.waitingTrace} aria-live="polite" aria-busy="true">
      <div>
        <span className={styles.busyMark} aria-hidden="true" />
        <div>
          <strong>{state === "validating" ? "校验完整回应" : "执行固定教学流程"}</strong>
          <small>页面只显示通过范围和证据契约校验的完成记录。</small>
        </div>
      </div>
      <ol>
        {WORKFLOW_ORDER.map((step, index) => (
          <li key={step}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            {WORKFLOW_LABELS[step]}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function TeachingWorkspace({
  scope,
  initialMode,
}: {
  scope: TeachingScope;
  initialMode: TeachingMode;
}) {
  const copy = MODE_COPY[initialMode];
  const [message, setMessage] = useState("");
  const [studentAttempt, setStudentAttempt] = useState("");
  const [scientificDraft, setScientificDraft] = useState<ScientificDraft>(() =>
    initialScientificDraft(initialMode),
  );
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [result, setResult] = useState<TeachingTurnResult | null>(null);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  function startNewRecord() {
    abortRef.current?.abort();
    setConversationId(null);
    setResult(null);
    setError(null);
    setTraceId(null);
    setRequestState("idle");
  }

  async function submitTurn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setTraceId(null);

    let payload;
    try {
      payload = parseTeachingTurnRequest({
        conversation_id: conversationId,
        mode: initialMode,
        message,
        student_attempt: studentAttempt.trim() || null,
        scientific_request: buildScientificRequest(scientificDraft),
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请检查教学请求输入。");
      setRequestState("failed");
      return;
    }

    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    setRequestState("submitting");
    try {
      const params = new URLSearchParams({
        course_id: scope.courseId,
        curriculum_edition_id: scope.curriculumEditionId,
      });
      const response = await fetch(`/api/teaching/turns/stream?${params.toString()}`, {
        method: "POST",
        headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const upstreamTrace = response.headers.get("x-trace-id");
      if (upstreamTrace) setTraceId(upstreamTrace);
      if (!response.ok) {
        const rawError: unknown = await response.json().catch(() => null);
        const apiError = parseTeachingApiError(rawError);
        throw new Error(apiError?.error.message ?? "教学请求失败，且服务未返回可验证的错误信息。");
      }
      if (!(response.headers.get("content-type") ?? "").startsWith("text/event-stream")) {
        throw new Error("教学服务没有返回预期的事件流；页面已拒绝显示。");
      }
      setRequestState("validating");
      const parsed = parseTeachingTurnResult(parseCompletedSse(await response.text()));
      assertTeachingScope(parsed, scope, initialMode);
      if (conversationId && parsed.conversation_id !== conversationId) {
        throw new Error("服务返回了另一段会话的记录；页面已拒绝显示。");
      }
      setConversationId(parsed.conversation_id);
      setResult(parsed);
      setRequestState("complete");
      window.requestAnimationFrame(() => document.getElementById("turn-result")?.focus());
    } catch (caught) {
      if (controller.signal.aborted) {
        setError("本轮请求已停止；输入仍保留在页面中。");
      } else {
        setError(caught instanceof Error ? caught.message : "教学工作流未完成。");
      }
      setRequestState("failed");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }

  const pending = requestState === "submitting" || requestState === "validating";
  return (
    <>
      <section className={styles.modeHero} aria-labelledby="course-mode-title">
        <div>
          <p className={styles.eyebrow}>{copy.index} MODE</p>
          <h1 id="course-mode-title">{copy.title}</h1>
          <p>{copy.description}</p>
        </div>
        <aside>
          <span>本轮边界</span>
          <strong>课程材料 → 教学政策 → 科学验证</strong>
          <p>LLM 负责理解与表述；权限、答案释放、证据校验和工具参数由代码控制。</p>
        </aside>
      </section>

      <nav className={styles.modeNav} aria-label="四种学习模式">
        {(Object.keys(MODE_COPY) as TeachingMode[]).map((mode) => (
          <Link
            key={mode}
            href={scopedHref(scope, mode)}
            aria-current={mode === initialMode ? "page" : undefined}
          >
            <span className={styles.modeIcon}><ModeIcon mode={mode} /></span>
            <span><strong>{MODE_COPY[mode].label}</strong><small>{MODE_COPY[mode].short}</small></span>
          </Link>
        ))}
      </nav>

      <div className={styles.workbench}>
        <form className={styles.turnForm} onSubmit={submitTurn} aria-describedby="turn-form-note">
          <div className={styles.formHeading}>
            <div>
              <p className={styles.eyebrow}>STUDENT INPUT</p>
              <h2>{conversationId ? "继续这段学习记录" : "开始一轮课程辅导"}</h2>
            </div>
            {conversationId ? (
              <button type="button" className={styles.textButton} onClick={startNewRecord}>
                新建记录
              </button>
            ) : null}
          </div>
          <label htmlFor="teaching-message">
            {copy.messageLabel} <span className={styles.required}>必填</span>
          </label>
          <textarea
            id="teaching-message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={copy.messageHint}
            minLength={1}
            maxLength={4000}
            rows={5}
            required
            disabled={pending}
          />
          <div className={styles.characterCount}>{message.length} / 4000</div>

          <label htmlFor="student-attempt">{copy.attemptLabel}</label>
          <textarea
            id="student-attempt"
            value={studentAttempt}
            onChange={(event) => setStudentAttempt(event.target.value)}
            placeholder={copy.attemptHint}
            maxLength={12000}
            rows={6}
            disabled={pending}
          />
          <div className={styles.characterCount}>{studentAttempt.length} / 12000</div>

          <ScientificRequestFields
            draft={scientificDraft}
            setDraft={setScientificDraft}
            disabled={pending}
          />

          <p id="turn-form-note" className={styles.formNote}>
            提交后，后端严格按十步状态机执行。科学工具也受答案政策约束：请求工具不代表一定会运行。
          </p>
          {error ? (
            <div className={styles.requestError} role="alert">
              <strong>本轮未完成</strong>
              <p>{error}</p>
              {traceId ? <small>Trace ID: <code>{traceId}</code></small> : null}
            </div>
          ) : null}
          <div className={styles.formActions}>
            <button type="submit" disabled={pending || message.trim().length === 0}>
              {pending ? "正在执行与校验…" : conversationId ? "提交下一轮" : "按教学流程处理"}
            </button>
            {pending ? (
              <button type="button" className={styles.secondaryButton} onClick={() => abortRef.current?.abort()}>
                停止本轮
              </button>
            ) : null}
          </div>
        </form>

        <aside className={styles.processPreview}>
          <p className={styles.eyebrow}>POLICY ENGINE</p>
          <h2>这不是自由运行的聊天机器人</h2>
          <ol>
            <li><span>01</span><div><strong>先找课程依据</strong><small>只检索教师已批准并发布的材料与图谱项。</small></div></li>
            <li><span>02</span><div><strong>再执行答案政策</strong><small>提示层级由教师策略与观察到的尝试次数决定。</small></div></li>
            <li><span>03</span><div><strong>必要时调用科学工具</strong><small>符号、数值与模拟结论有独立方法和局限标签。</small></div></li>
            <li><span>04</span><div><strong>校验后才显示</strong><small>引用、科学结果 ID 与固定流程顺序不匹配时拒绝渲染。</small></div></li>
          </ol>
        </aside>
      </div>

      {pending ? <WaitingTrace state={requestState} /> : null}
      {result ? <TeachingResultRecord result={result} /> : null}
    </>
  );
}
