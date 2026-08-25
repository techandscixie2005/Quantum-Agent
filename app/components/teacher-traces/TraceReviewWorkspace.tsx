"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  FileSearch,
  FlaskConical,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import {
  assertHitlScope,
  parseHitlInterruptResponse,
  type HitlInterruptResponse,
} from "@/app/components/teaching/contracts";
import {
  parseAgentTraceDetail,
  parseAgentTracePage,
  parseReviewDecision,
  parseReviewResolution,
  teachingResponseSchema,
  type AgentTraceDetail,
  type AgentTraceSummary,
  type EvidenceBundle,
  type ReviewDecision,
  type TeachingResponse,
  type TraceScope,
} from "@/app/components/teacher-traces/contracts";
import styles from "@/app/components/teacher-traces/trace-review.module.css";

const PAGE_SIZE = 25;

const MODE_LABELS: Record<AgentTraceSummary["mode"], string> = {
  learn_concepts: "概念",
  review_derivations: "推导",
  run_experiments: "实验",
  work_on_projects: "项目",
};

const WORKFLOW_LABELS: Record<string, string> = {
  classify_task: "识别任务",
  identify_concepts: "定位概念",
  retrieve_evidence: "检索证据",
  diagnose_progress: "诊断进展",
  choose_teaching_action: "选择教学动作",
  apply_answer_policy: "应用回答策略",
  run_scientific_tools: "运行科学工具",
  generate_response: "生成候选响应",
  validate_response: "验证响应",
  record_learning_evidence: "记录学习证据",
};

const HITL_REASON_LABELS: Record<string, string> = {
  ta_requested: "学生请求助教",
  ambiguous_transcription: "转录存在歧义",
  evidence_conflict: "课程证据冲突",
  insufficient_coverage: "课程覆盖不足",
  verifier_model_disagreement: "验证器与模型不一致",
  repeated_no_progress: "连续尝试无进展",
  teacher_approval_required: "需要教师批准",
  project_milestone_review: "项目里程碑审阅",
  safety_condition: "触发安全条件",
};

const RELEASE_LABELS: Record<string, string> = {
  question_only: "仅追问",
  hint: "最小提示",
  scaffold: "分步脚手架",
  full_explanation: "完整解释",
  full_solution: "完整解答",
};

const REVIEW_ACTION_LABELS: Record<ReviewDecision["action"], string> = {
  approve: "已批准并恢复",
  reject: "已拒绝本回合",
  edit: "已编辑并恢复",
  take_over: "已由教师接管",
};

class TraceApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "TraceApiError";
  }
}

function scopeParams(scope: TraceScope, additions: Record<string, string> = {}): string {
  return new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
    ...additions,
  }).toString();
}

async function responsePayload(response: Response): Promise<unknown> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new TraceApiError("服务返回了无法解析的响应。", response.status || 502);
  }
  if (!response.ok) {
    let message = "教学治理服务拒绝了请求。";
    if (typeof payload === "object" && payload !== null && !Array.isArray(payload)) {
      const error = (payload as Record<string, unknown>).error;
      if (typeof error === "object" && error !== null && !Array.isArray(error)) {
        const candidate = (error as Record<string, unknown>).message;
        if (typeof candidate === "string" && candidate.length > 0 && candidate.length <= 1_000) {
          message = candidate;
        }
      }
    }
    throw new TraceApiError(message, response.status);
  }
  return payload;
}

function shortId(value: string): string {
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
}

function formatTime(value: string | null): string {
  if (!value) return "尚未完成";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatLocator(locator: EvidenceBundle["citations"][number]["locator"]): string {
  if (locator.locator_type === "pdf_page") {
    return locator.printed_page_label
      ? `PDF 第 ${locator.physical_page} 页 · 书页 ${locator.printed_page_label}`
      : `PDF 第 ${locator.physical_page} 页`;
  }
  if (locator.locator_type === "slide") return `幻灯片 ${locator.slide_number}`;
  if (locator.locator_type === "docx_paragraph") {
    return `段落 ${locator.paragraph_start}${locator.paragraph_end ? `–${locator.paragraph_end}` : ""}`;
  }
  if (locator.locator_type === "xlsx_row") {
    return `${locator.sheet_name} · 行 ${locator.row_start}${locator.row_end ? `–${locator.row_end}` : ""}`;
  }
  return `文本行 ${locator.line_start}${locator.line_end ? `–${locator.line_end}` : ""}`;
}

function sourceHref(
  citation: EvidenceBundle["citations"][number],
  scope: TraceScope,
): string {
  const page = citation.locator.physical_page ?? citation.locator.slide_number;
  return (
    `/api/agent/sources/${citation.document_version_id}/original?${scopeParams(scope)}` +
    (page ? `#page=${page}` : "")
  );
}

function StatusMark({ status }: Readonly<{ status: AgentTraceSummary["turn_status"] }>) {
  return (
    <span className={`${styles.statusMark} ${styles[`status_${status}`]}`}>
      <i aria-hidden="true" />
      {status === "running" ? "运行 / 暂停" : status === "completed" ? "已完成" : "失败"}
    </span>
  );
}

function PanelState({ children, danger = false }: Readonly<{ children: ReactNode; danger?: boolean }>) {
  return (
    <div className={`${styles.panelState} ${danger ? styles.panelStateDanger : ""}`}>
      {danger ? <AlertTriangle size={17} aria-hidden="true" /> : <Circle size={13} aria-hidden="true" />}
      <span>{children}</span>
    </div>
  );
}

function Section({
  eyebrow,
  title,
  icon,
  children,
  className = "",
}: Readonly<{
  eyebrow: string;
  title: string;
  icon: ReactNode;
  children: ReactNode;
  className?: string;
}>) {
  return (
    <section className={`${styles.auditSection} ${className}`}>
      <header className={styles.sectionHeader}>
        <span className={styles.sectionIcon}>{icon}</span>
        <div>
          <span>{eyebrow}</span>
          <h2>{title}</h2>
        </div>
      </header>
      {children}
    </section>
  );
}

function TraceQueue({
  items,
  total,
  activeTraceId,
  offset,
  hasMore,
  onSelect,
  onOffset,
  onRefresh,
  refreshing,
}: Readonly<{
  items: readonly AgentTraceSummary[];
  total: number;
  activeTraceId: string | null;
  offset: number;
  hasMore: boolean;
  onSelect: (traceId: string) => void;
  onOffset: (offset: number) => void;
  onRefresh: () => void;
  refreshing: boolean;
}>) {
  const [mode, setMode] = useState<"all" | AgentTraceSummary["mode"]>("all");
  const [status, setStatus] = useState<"all" | AgentTraceSummary["turn_status"]>("all");
  const visible = items.filter(
    (item) => (mode === "all" || item.mode === mode) && (status === "all" || item.turn_status === status),
  );

  return (
    <aside className={styles.queuePanel} aria-label="Agent trace 队列">
      <header className={styles.queueHeader}>
        <div>
          <span className={styles.sectionLabel}>TRACE QUEUE</span>
          <h1>待查工作流</h1>
          <p>{total} 条课程内执行记录</p>
        </div>
        <button className={styles.iconButton} type="button" onClick={onRefresh} aria-label="刷新 trace 队列">
          <RefreshCw size={15} className={refreshing ? styles.spinning : ""} />
        </button>
      </header>
      <div className={styles.queueFilters}>
        <label>
          <span>模式</span>
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="all">全部模式</option>
            {Object.entries(MODE_LABELS).map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>
            <option value="all">全部状态</option>
            <option value="running">运行 / 暂停</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
          </select>
        </label>
      </div>
      <div className={styles.queueList}>
        {visible.length === 0 ? (
          <PanelState>本页没有符合筛选条件的 trace。</PanelState>
        ) : (
          visible.map((item) => {
            const unresolved = item.turn_status === "running";
            return (
              <button
                key={item.id}
                type="button"
                className={`${styles.queueItem} ${item.id === activeTraceId ? styles.queueItemActive : ""}`}
                onClick={() => onSelect(item.id)}
                aria-pressed={item.id === activeTraceId}
              >
                <span className={styles.queueOrdinal}>{String(item.sequence_number).padStart(2, "0")}</span>
                <span className={styles.queueCopy}>
                  <span>
                    <strong>{MODE_LABELS[item.mode]}</strong>
                    {unresolved ? <em>需检查</em> : null}
                  </span>
                  <b>{item.task_kind?.replaceAll("_", " ") ?? "尚未分类"}</b>
                  <small>{formatTime(item.created_at)} · {shortId(item.student_user_id)}</small>
                </span>
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            );
          })
        )}
      </div>
      <footer className={styles.queuePager}>
        <button type="button" disabled={offset === 0} onClick={() => onOffset(Math.max(0, offset - PAGE_SIZE))}>
          <ArrowLeft size={13} /> 上一页
        </button>
        <span>{offset + 1}–{Math.min(offset + items.length, total)}</span>
        <button type="button" disabled={!hasMore} onClick={() => onOffset(offset + PAGE_SIZE)}>
          下一页 <ArrowRight size={13} />
        </button>
      </footer>
    </aside>
  );
}

function EvidenceRecord({ detail, scope }: Readonly<{ detail: AgentTraceDetail; scope: TraceScope }>) {
  const bundle = detail.evidence_bundle;
  const packet = detail.evidence_packet;
  if (!bundle && !packet) return <PanelState>该 trace 未保存检索证据。</PanelState>;
  const citations = bundle?.citations ?? [];
  const coverage = bundle?.coverage ?? packet?.coverage ?? "not_found";
  const rationale = bundle?.coverage_rationale ?? "旧版检索包未保存独立覆盖理由。";

  return (
    <>
      <div className={styles.coverageStrip}>
        <span className={`${styles.coverageCode} ${styles[`coverage_${coverage}`]}`}>{coverage.toUpperCase()}</span>
        <p>{rationale}</p>
        <small>{bundle?.source_chunks.length ?? packet?.evidence.length ?? 0} 个原始片段</small>
      </div>
      {bundle ? (
        <div className={styles.evidenceGrid}>
          <div>
            <h3>相关概念</h3>
            <div className={styles.tagCloud}>
              {bundle.relevant_concepts.length ? bundle.relevant_concepts.map((node) => (
                <span key={node.id}>{node.name}</span>
              )) : <small>未返回图谱概念</small>}
            </div>
          </div>
          <div>
            <h3>公式节点</h3>
            <div className={styles.formulaStack}>
              {bundle.formulas.length ? bundle.formulas.map((formula) => (
                <code key={formula.id}>{formula.name}</code>
              )) : <small>无显式公式节点</small>}
            </div>
          </div>
        </div>
      ) : null}
      {citations.length ? (
        <div className={styles.citationList}>
          {citations.map((citation, index) => (
            <article key={citation.evidence_id} className={styles.citation}>
              <span className={styles.citationIndex}>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <header>
                  <strong>{citation.document_title}</strong>
                  <span>v{citation.document_version} · {formatLocator(citation.locator)}</span>
                </header>
                <blockquote>{citation.evidence_snippet}</blockquote>
                <footer>
                  <code>{shortId(citation.evidence_sha256)}</code>
                  <a href={sourceHref(citation, scope)} target="_blank" rel="noreferrer">
                    <BookOpen size={13} /> 打开原始页 / 幻灯片
                  </a>
                </footer>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <PanelState>当前 EvidenceBundle 没有可打开的课程引用。</PanelState>
      )}
      {bundle ? (
        <div className={styles.connectionGrid}>
          <div>
            <h3>为什么相连？</h3>
            {bundle.prerequisite_paths.length ? (
              <ul>
                {bundle.prerequisite_paths.map((path) => (
                  <li key={path.relation_id}><span>{path.prerequisite.name}</span><ArrowRight size={12} /><strong>{path.target.name}</strong></li>
                ))}
              </ul>
            ) : <small>无直接先修路径</small>}
          </div>
          <div>
            <h3>误概念关系</h3>
            {bundle.misconception_links.length ? (
              <ul>
                {bundle.misconception_links.map((link) => (
                  <li key={link.relation_id}><span>{link.source.name}</span><ArrowRight size={12} /><strong>{link.misconception.name}</strong></li>
                ))}
              </ul>
            ) : <small>无直接误概念链接</small>}
          </div>
        </div>
      ) : null}
      {bundle?.conflicts.length || bundle?.warnings.length || packet?.warnings.length ? (
        <div className={styles.alertLedger}>
          {bundle?.conflicts.map((conflict) => (
            <div className={styles.conflictRow} key={`${conflict.summary}-${conflict.evidence_ids.join("-")}`}>
              <AlertTriangle size={14} /><span><strong>证据冲突</strong>{conflict.summary}</span>
            </div>
          ))}
          {(bundle?.warnings ?? packet?.warnings ?? []).map((warning) => (
            <div className={styles.warningRow} key={warning}>
              <Circle size={8} /><span><strong>检索警告</strong>{warning}</span>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

function DiagnosisRecord({ detail }: Readonly<{ detail: AgentTraceDetail }>) {
  const diagnosis = detail.diagnosis;
  if (!diagnosis) return <PanelState>该 trace 未保存诊断输出。</PanelState>;
  return (
    <div className={styles.diagnosisRecord}>
      <div className={styles.diagnosisLead}>
        <div className={styles.confidenceDial} style={{ "--confidence": `${diagnosis.confidence * 100}%` } as React.CSSProperties}>
          <strong>{Math.round(diagnosis.confidence * 100)}</strong><span>%</span>
        </div>
        <div>
          <span>{diagnosis.status.replaceAll("_", " ")} · {diagnosis.progress_state}</span>
          <h3>{diagnosis.summary}</h3>
          <p>{diagnosis.reason}</p>
        </div>
      </div>
      <dl className={styles.diagnosisFacts}>
        <div><dt>首个关键错误</dt><dd>{diagnosis.first_error ? `步骤 ${diagnosis.first_error.step_index ?? "?"} · ${diagnosis.first_error.kind} · ${diagnosis.first_error.description || "无附加说明"}` : "未定位"}</dd></div>
        <div><dt>目标概念</dt><dd>{diagnosis.target_concepts.join("、") || "未标注"}</dd></div>
        <div><dt>缺失先修</dt><dd>{diagnosis.missing_prerequisites.join("、") || "未发现"}</dd></div>
        <div><dt>需验证器</dt><dd>{diagnosis.verification_needed ? "是，模型未自行执行工具" : "否"}</dd></div>
      </dl>
      {diagnosis.misconception_candidates.length ? (
        <div className={styles.candidateRows}>
          {diagnosis.misconception_candidates.map((candidate) => (
            <div key={candidate.statement}><span style={{ width: `${candidate.confidence * 100}%` }} /><strong>{candidate.statement}</strong><small>{Math.round(candidate.confidence * 100)}%</small></div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PolicyRecord({ detail }: Readonly<{ detail: AgentTraceDetail }>) {
  const policy = detail.policy_snapshot;
  const release = detail.release_decision;
  return (
    <div className={styles.policyGrid}>
      <div>
        <span>POLICY SNAPSHOT</span>
        <h3>{policy.source === "teacher_configured" ? "教师配置" : "安全默认"}</h3>
        <dl>
          <div><dt>最大提示级别</dt><dd>{policy.max_hint_level}</dd></div>
          <div><dt>脚手架尝试阈值</dt><dd>{policy.minimum_attempts_for_scaffold}</dd></div>
          <div><dt>完整解答阈值</dt><dd>{policy.minimum_attempts_for_full_solution}</dd></div>
          <div><dt>允许完整解答</dt><dd>{policy.allow_full_solution ? "是" : "否"}</dd></div>
        </dl>
      </div>
      <div className={styles.releaseCard}>
        <span>DETERMINISTIC RELEASE</span>
        {release ? (
          <>
            <h3>{RELEASE_LABELS[release.release_level] ?? release.release_level}</h3>
            <p>{release.action.replaceAll("_", " ")}</p>
            <dl>
              <div><dt>观测尝试数</dt><dd>{release.attempts_observed}</dd></div>
              <div><dt>原因码</dt><dd><code>{release.reason_code}</code></dd></div>
            </dl>
          </>
        ) : <p>尚未形成回答释放决定。</p>}
      </div>
    </div>
  );
}

function ResponseRecord({ detail, current }: Readonly<{ detail: AgentTraceDetail; current: HitlInterruptResponse | null }>) {
  const response = current?.artifacts.proposed_response ?? detail.response;
  const validation = current?.artifacts.validation ?? detail.validation;
  if (!response) return <PanelState>工作流尚未生成候选响应。</PanelState>;
  return (
    <div className={styles.responseRecord}>
      <div className={styles.responseStatus}>
        <span>{current ? "CHECKPOINT PROPOSAL" : "PERSISTED RESPONSE"}</span>
        <strong>{response.status.replaceAll("_", " ")}</strong>
      </div>
      <p className={styles.orientation}>{response.orientation}</p>
      <ol className={styles.claimList}>
        {response.claims.map((claim, index) => (
          <li key={`${index}-${claim.text}`}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><p>{claim.text}</p><small>{claim.support_basis} · {claim.evidence_ids.length} citations · {claim.scientific_result_ids.length} tool refs</small></div>
          </li>
        ))}
      </ol>
      <div className={styles.nextQuestion}><span>下一步问题</span><p>{response.next_question}</p></div>
      {response.limitations.length ? <ul className={styles.limitations}>{response.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : null}
      {validation ? (
        <div className={`${styles.validationStrip} ${validation.passed ? styles.validationPass : styles.validationFail}`}>
          {validation.passed ? <ShieldCheck size={18} /> : <XCircle size={18} />}
          <div><strong>{validation.passed ? "响应契约通过" : "响应契约未通过"}</strong><span>引用 {validation.citation_ids_valid ? "✓" : "×"} · 字面证据 {validation.literal_course_claims_valid ? "✓" : "×"} · 科学引用 {validation.scientific_references_valid ? "✓" : "×"}</span></div>
        </div>
      ) : null}
    </div>
  );
}

function ToolRecord({ detail, current }: Readonly<{ detail: AgentTraceDetail; current: HitlInterruptResponse | null }>) {
  const results = current?.artifacts.scientific_results ?? detail.scientific_results;
  if (!results.length) return <PanelState>该回合未调用确定性科学工具。</PanelState>;
  return (
    <div className={styles.toolList}>
      {results.map((result) => (
        <article key={`${result.kind}:${result.inputs_sha256}`}>
          <header><span className={styles[`tool_${result.status}`]}>{result.status}</span><strong>{result.kind.replaceAll("_", " ")}</strong><code>{result.tool.name} · {result.tool.version}</code></header>
          <p>{result.observations.join("；")}</p>
          <dl>{Object.entries(result.metrics).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
          <small>{result.limitations.join("；")}</small>
        </article>
      ))}
    </div>
  );
}

function WorkflowRecord({ detail }: Readonly<{ detail: AgentTraceDetail }>) {
  return (
    <ol className={styles.workflowSpine}>
      {detail.workflow_steps.map((step, index) => (
        <li key={step.name} className={styles[`step_${step.status}`]}>
          <span className={styles.spineNode}>{step.status === "completed" ? <Check size={13} /> : step.status === "failed" ? <XCircle size={13} /> : <Circle size={9} />}</span>
          <div><span>{String(index + 1).padStart(2, "0")} / {step.name}</span><strong>{WORKFLOW_LABELS[step.name] ?? step.name}</strong><p>{step.detail}</p></div>
        </li>
      ))}
    </ol>
  );
}

function HitlHistory({ detail }: Readonly<{ detail: AgentTraceDetail }>) {
  if (!detail.hitl_events.length) return <PanelState>该回合未产生人工复核中断。</PanelState>;
  return (
    <div className={styles.hitlLedger}>
      {detail.hitl_events.map((event, index) => (
        <article key={event.interrupt.interrupt_id}>
          <span className={styles.ledgerIndex}>{String(index + 1).padStart(2, "0")}</span>
          <div>
            <header><strong>{event.interrupt.reasons.map((reason) => HITL_REASON_LABELS[reason] ?? reason).join(" / ")}</strong><span>{event.resolution ? "已裁决" : "等待裁决"}</span></header>
            <p>{event.interrupt.prompt}</p>
            {event.resolution ? <small>{event.resolution.actor_role} · {shortId(event.resolution.actor_user_id)} · {event.resolution.action}{event.resolution.note ? ` · ${event.resolution.note}` : ""}</small> : <small>interrupt {shortId(event.interrupt.interrupt_id)}</small>}
          </div>
        </article>
      ))}
    </div>
  );
}

function TraceRecord({ detail, scope, current }: Readonly<{ detail: AgentTraceDetail; scope: TraceScope; current: HitlInterruptResponse | null }>) {
  return (
    <main className={styles.recordPanel}>
      <header className={styles.recordHeader}>
        <div>
          <span className={styles.sectionLabel}>CAUSAL RECORD / TURN {String(detail.sequence_number).padStart(2, "0")}</span>
          <h1>{MODE_LABELS[detail.mode]}教学工作流</h1>
          <p><code>{detail.workflow_version}</code> · trace {shortId(detail.id)} · student {shortId(detail.student_user_id)}</p>
        </div>
        <StatusMark status={detail.turn_status} />
      </header>

      <Section eyebrow="01 / STUDENT SIGNAL" title="学生输入与尝试" icon={<FileSearch size={17} />}>
        <div className={styles.studentSignal}>
          <div><span>QUESTION</span><p>{detail.user_message}</p></div>
          <div><span>ATTEMPT</span><p>{detail.student_attempt ?? "未提交独立尝试"}</p></div>
        </div>
      </Section>
      <Section eyebrow="02 / EVIDENCE" title="课程证据与来源定位" icon={<BookOpen size={17} />}>
        <EvidenceRecord detail={detail} scope={scope} />
      </Section>
      <Section eyebrow="03 / DIAGNOSIS" title="诊断代理输出" icon={<GitBranch size={17} />}>
        <DiagnosisRecord detail={detail} />
      </Section>
      <Section eyebrow="04 / POLICY" title="策略边界与释放决定" icon={<ShieldCheck size={17} />}>
        <PolicyRecord detail={detail} />
      </Section>
      <Section eyebrow="05 / PROPOSAL" title="候选教学响应与验证" icon={<CheckCircle2 size={17} />}>
        <ResponseRecord detail={detail} current={current} />
      </Section>
      <Section eyebrow="06 / TOOLS" title="确定性科学工具" icon={<FlaskConical size={17} />}>
        <ToolRecord detail={detail} current={current} />
      </Section>
      <Section eyebrow="07 / STATE MACHINE" title="LangGraph 因果执行链" icon={<GitBranch size={17} />} className={styles.workflowSection}>
        <WorkflowRecord detail={detail} />
      </Section>
      <Section eyebrow="08 / HUMAN LOOP" title="人工复核历史" icon={<Clock3 size={17} />}>
        <HitlHistory detail={detail} />
      </Section>
    </main>
  );
}

function ConstrainedResponseEditor({
  response,
  disabled,
  onChange,
}: Readonly<{
  response: TeachingResponse;
  disabled: boolean;
  onChange: (response: TeachingResponse) => void;
}>) {
  function updateClaim(index: number, text: string): void {
    onChange({
      ...response,
      claims: response.claims.map((claim, claimIndex) =>
        claimIndex === index ? { ...claim, text } : claim,
      ),
    });
  }

  return (
    <div className={styles.responseEditor}>
      <header>
        <span>BOUNDED RESPONSE EDITOR</span>
        <strong>{response.status.replaceAll("_", " ")}</strong>
      </header>
      <p>
        引用、工具结果、支持类型、声明数量与响应状态已锁定。修改后的课程事实仍须逐字受原证据支持。
      </p>
      <label>
        <span>引导语</span>
        <textarea
          value={response.orientation}
          maxLength={1_200}
          disabled={disabled}
          onChange={(event) => onChange({ ...response, orientation: event.target.value })}
        />
      </label>
      <div className={styles.claimEditors}>
        {response.claims.map((claim, index) => (
          <label key={`${index}-${claim.support_basis}`}>
            <span>声明 {String(index + 1).padStart(2, "0")}</span>
            <textarea
              value={claim.text}
              maxLength={4_000}
              disabled={disabled}
              onChange={(event) => updateClaim(index, event.target.value)}
            />
            <small>
              {claim.support_basis} · refs locked: {claim.evidence_ids.map(shortId).join(", ") || "none"} · tools: {claim.scientific_result_ids.map(shortId).join(", ") || "none"}
            </small>
          </label>
        ))}
      </div>
      <label>
        <span>下一步问题</span>
        <textarea
          value={response.next_question}
          maxLength={1_000}
          disabled={disabled}
          onChange={(event) => onChange({ ...response, next_question: event.target.value })}
        />
      </label>
      {response.limitations.map((limitation, index) => (
        <label key={`limitation-${index}`}>
          <span>限制说明 {String(index + 1).padStart(2, "0")}</span>
          <textarea
            value={limitation}
            maxLength={4_000}
            disabled={disabled}
            onChange={(event) =>
              onChange({
                ...response,
                limitations: response.limitations.map((item, itemIndex) =>
                  itemIndex === index ? event.target.value : item,
                ),
              })
            }
          />
        </label>
      ))}
    </div>
  );
}

function ReviewRail({
  traceId,
  detail,
  current,
  currentError,
  scope,
}: Readonly<{
  traceId: string;
  detail: AgentTraceDetail;
  current: HitlInterruptResponse | null;
  currentError: Error | null;
  scope: TraceScope;
}>) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<ReviewDecision["action"] | null>(null);
  const [note, setNote] = useState("");
  const [editedResponse, setEditedResponse] = useState<TeachingResponse | null>(null);
  const mutation = useMutation({
    mutationFn: async () => {
      if (!current || !action) throw new Error("请选择复核动作。");
      const rawDecision =
        action === "edit" || action === "take_over"
          ? {
              interrupt_id: current.interrupt.interrupt_id,
              action,
              note: note.trim() || null,
              edited_response: editedResponse,
            }
          : {
              interrupt_id: current.interrupt.interrupt_id,
              action,
              note: note.trim() || null,
            };
      const decision = parseReviewDecision(rawDecision);
      const response = await fetch(`/api/teacher/traces/${traceId}/review?${scopeParams(scope)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decision),
      });
      return parseReviewResolution(await responsePayload(response));
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["teacher-trace-list", scope.courseId, scope.curriculumEditionId] }),
        queryClient.invalidateQueries({ queryKey: ["teacher-trace", scope.courseId, scope.curriculumEditionId, traceId] }),
        queryClient.invalidateQueries({ queryKey: ["teacher-trace-review", scope.courseId, scope.curriculumEditionId, traceId] }),
      ]);
    },
  });
  const requiresNote = action === "reject" || action === "take_over";
  const missingRequiredNote = requiresNote && !note.trim();
  const usesEditor = action === "edit" || action === "take_over";

  function chooseAction(nextAction: ReviewDecision["action"]): void {
    setAction(nextAction);
    if ((nextAction === "edit" || nextAction === "take_over") && current) {
      setEditedResponse(
        (existing) =>
          existing ?? teachingResponseSchema.parse(current.artifacts.proposed_response),
      );
    }
  }

  return (
    <aside className={styles.reviewRail} aria-label="人工复核裁决">
      <header>
        <span className={styles.sectionLabel}>ADJUDICATION</span>
        <h2>人工裁决</h2>
        <p>决定只恢复同一条 LangGraph 线程；策略、引用与科学事实不能在此覆盖。</p>
      </header>
      {!detail.hitl_events.some((event) => event.resolution === null) ? (
        <div className={styles.readOnlyStamp}><CheckCircle2 size={20} /><strong>只读 trace</strong><span>当前没有待处理 checkpoint</span></div>
      ) : current ? (
        <>
          <div className={styles.interruptCard}>
            <span>ACTIVE INTERRUPT</span>
            <code>{shortId(current.interrupt.interrupt_id)}</code>
            <h3>{current.interrupt.reasons.map((reason) => HITL_REASON_LABELS[reason] ?? reason).join(" / ")}</h3>
            <p>{current.interrupt.prompt}</p>
          </div>
          <div className={styles.checkpointFacts}>
            <div><span>Coverage</span><strong>{current.artifacts.evidence_bundle?.coverage ?? current.artifacts.evidence_packet.coverage}</strong></div>
            <div><span>Diagnosis</span><strong>{Math.round(current.artifacts.diagnosis.confidence * 100)}%</strong></div>
            <div><span>Release</span><strong>{RELEASE_LABELS[current.artifacts.release.release_level] ?? current.artifacts.release.release_level}</strong></div>
            <div><span>Validation</span><strong>{current.artifacts.validation.passed ? "PASS" : "FAIL"}</strong></div>
          </div>
          <fieldset className={styles.decisionSet} disabled={mutation.isPending || mutation.isSuccess}>
            <legend>裁决动作</legend>
            <button type="button" className={action === "approve" ? styles.decisionActiveApprove : ""} onClick={() => chooseAction("approve")}>
              <CheckCircle2 size={18} /><span><strong>批准并继续</strong><small>使用已验证候选响应恢复线程</small></span>
            </button>
            <button type="button" className={action === "reject" ? styles.decisionActiveReject : ""} onClick={() => chooseAction("reject")}>
              <XCircle size={18} /><span><strong>拒绝本回合</strong><small>停止释放并写入审计原因</small></span>
            </button>
            <button type="button" className={action === "edit" ? styles.decisionActiveEdit : ""} onClick={() => chooseAction("edit")}>
              <FileSearch size={18} /><span><strong>受约束编辑</strong><small>保留引用与工具权限，只修改措辞</small></span>
            </button>
            <button type="button" className={action === "take_over" ? styles.decisionActiveTakeover : ""} onClick={() => chooseAction("take_over")}>
              <ShieldCheck size={18} /><span><strong>教师接管</strong><small>用受验证的教师响应恢复线程</small></span>
            </button>
          </fieldset>
          {usesEditor && editedResponse ? (
            <ConstrainedResponseEditor
              response={editedResponse}
              disabled={mutation.isPending || mutation.isSuccess}
              onChange={setEditedResponse}
            />
          ) : null}
          <label className={styles.reviewNote}>
            <span>审阅说明 {requiresNote ? "· 必填" : "· 可选"}</span>
            <textarea maxLength={4_000} value={note} onChange={(event) => setNote(event.target.value)} disabled={mutation.isPending || mutation.isSuccess} placeholder="记录批准依据，或说明拒绝原因…" />
            <small>{note.length} / 4000</small>
          </label>
          <button className={styles.commitButton} type="button" disabled={!action || missingRequiredNote || (usesEditor && !editedResponse) || mutation.isPending || mutation.isSuccess} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "正在重新检查 checkpoint…" : mutation.isSuccess ? "裁决已写入" : "提交裁决并恢复线程"}
          </button>
          {mutation.isError ? <PanelState danger>{mutation.error.message}</PanelState> : null}
          {mutation.isSuccess ? <div className={styles.successNote} role="status"><CheckCircle2 size={16} />{REVIEW_ACTION_LABELS[mutation.data.action]}；结果：{mutation.data.outcome}</div> : null}
          <div className={styles.deferredActions}>
            <span>权限边界</span>
            <small>所有动作恢复同一 conversation / turn。RBAC、Policy Gate、引用有效性与科学事实仍由后端确定性校验控制。</small>
          </div>
        </>
      ) : currentError ? (
        <PanelState danger>{currentError.message}</PanelState>
      ) : (
        <PanelState>正在核对当前 checkpoint…</PanelState>
      )}
    </aside>
  );
}

export function TraceReviewWorkspace({ scope }: Readonly<{ scope: TraceScope }>) {
  const [offset, setOffset] = useState(0);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["teacher-trace-list", scope.courseId, scope.curriculumEditionId, offset],
    queryFn: async () => {
      const response = await fetch(`/api/teacher/traces?${scopeParams(scope, { limit: String(PAGE_SIZE), offset: String(offset) })}`);
      return parseAgentTracePage(await responsePayload(response), scope);
    },
  });
  const activeTraceId =
    selectedTraceId && list.data?.items.some((item) => item.id === selectedTraceId)
      ? selectedTraceId
      : list.data?.items[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["teacher-trace", scope.courseId, scope.curriculumEditionId, activeTraceId],
    enabled: activeTraceId !== null,
    queryFn: async () => {
      if (!activeTraceId) throw new Error("trace id is missing");
      const response = await fetch(`/api/teacher/traces/${activeTraceId}?${scopeParams(scope)}`);
      return parseAgentTraceDetail(await responsePayload(response), scope, activeTraceId);
    },
  });
  const unresolved = detail.data?.hitl_events.some((event) => event.resolution === null) ?? false;
  const review = useQuery({
    queryKey: ["teacher-trace-review", scope.courseId, scope.curriculumEditionId, activeTraceId],
    enabled: activeTraceId !== null && detail.data !== undefined && unresolved,
    queryFn: async () => {
      if (!activeTraceId || !detail.data) throw new Error("trace review context is missing");
      const response = await fetch(`/api/teacher/traces/${activeTraceId}/review?${scopeParams(scope)}`);
      const current = parseHitlInterruptResponse(await responsePayload(response));
      assertHitlScope(current, scope, detail.data.mode);
      if (current.turn_id !== detail.data.teaching_turn_id) throw new Error("复核 checkpoint 与 trace 回合不一致。");
      return current;
    },
  });

  if (list.isPending) {
    return <div className={styles.workspaceState}><RefreshCw className={styles.spinning} size={20} /><span>正在读取课程内 Agent traces…</span></div>;
  }
  if (list.isError) {
    return <div className={styles.workspaceState}><AlertTriangle size={20} /><span>{list.error.message}</span><button type="button" onClick={() => list.refetch()}>重试</button></div>;
  }
  if (!list.data.items.length) {
    return <div className={styles.workspaceState}><FileSearch size={21} /><span>这个课程版本还没有 Agent trace。</span><button type="button" onClick={() => list.refetch()}>刷新</button></div>;
  }

  return (
    <div className={styles.scopeFrame}>
      <div className={styles.scopeStamp}>
        <span>COURSE</span><code>{shortId(scope.courseId)}</code><i />
        <span>EDITION</span><code>{shortId(scope.curriculumEditionId)}</code><i />
        <span>AUTH</span><strong>qa_session / staff RBAC</strong>
      </div>
      <div className={styles.workspaceGrid}>
        <TraceQueue
          items={list.data.items}
          total={list.data.total}
          activeTraceId={activeTraceId}
          offset={offset}
          hasMore={list.data.has_more}
          onSelect={setSelectedTraceId}
          onOffset={setOffset}
          onRefresh={() => void list.refetch()}
          refreshing={list.isFetching}
        />
        {detail.isPending ? (
          <div className={styles.recordLoading}><RefreshCw className={styles.spinning} size={18} />正在重建 trace 因果记录…</div>
        ) : detail.isError ? (
          <div className={styles.recordLoading}><AlertTriangle size={18} />{detail.error.message}</div>
        ) : detail.data && activeTraceId ? (
          <>
            <TraceRecord detail={detail.data} scope={scope} current={review.data ?? null} />
            <ReviewRail
              key={`${activeTraceId}:${review.data?.interrupt.interrupt_id ?? "pending"}`}
              traceId={activeTraceId}
              detail={detail.data}
              current={review.data ?? null}
              currentError={review.error ?? null}
              scope={scope}
            />
          </>
        ) : null}
      </div>
    </div>
  );
}
