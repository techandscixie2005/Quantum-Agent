"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Atom,
  BookOpen,
  Braces,
  Check,
  CircleAlert,
  FileText,
  FlaskConical,
  FolderKanban,
  Image as ImageIcon,
  Link2,
  LoaderCircle,
  Lock,
  Menu,
  Network,
  PanelRight,
  Paperclip,
  PenLine,
  Plus,
  Search,
  Send,
  Sigma,
  Sparkles,
  Target,
  Upload,
  X,
} from "lucide-react";
import dynamic from "next/dynamic";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type FormEvent } from "react";

import {
  assertHitlScope,
  assertTeachingScope,
  parseHitlInterruptResponse,
  parseTeachingApiError,
  parseTeachingTurnRequest,
  parseTeachingWorkflowOutcome,
  redactHitlProposedResponse,
  type HitlInterruptResponse,
  type LearningNativeSubmission,
  type TeachingEvidence,
  type TeachingMode,
  type TeachingScope,
  type TeachingTurnResult,
  type TeachingWorkflowOutcome,
} from "@/app/components/teaching/contracts";
import {
  parseAgentAttachment,
  parseStudentCourseContext,
  scopeFromCourse,
  type AgentAttachment,
} from "./contracts";
import { AgentEquation } from "./AgentEquation";
import {
  CognitiveMirrorPanel,
  LearningNativeSurface,
} from "./LearningNative";
import { LearningJourney } from "./LearningJourney";
import styles from "./agent.module.css";

const AgentCodeEditor = dynamic(() => import("./AgentCodeEditor"), {
  ssr: false,
  loading: () => <div className={styles.moduleLoading}>正在载入项目编辑器…</div>,
});
const AgentPlot = dynamic(() => import("./AgentPlot"), {
  ssr: false,
  loading: () => <div className={styles.moduleLoading}>正在载入科学绘图…</div>,
});
const CodingArtifactPanel = dynamic(() => import("./CodingArtifactPanel"), {
  ssr: false,
  loading: () => <div className={styles.moduleLoading}>正在载入 Coding Agent…</div>,
});

const MODES: ReadonlyArray<{
  id: TeachingMode;
  label: string;
  short: string;
  icon: typeof Atom;
}> = [
  { id: "learn_concepts", label: "概念", short: "解释与迁移", icon: Atom },
  { id: "review_derivations", label: "推导", short: "首错定位", icon: Sigma },
  { id: "run_experiments", label: "实验", short: "预测与验证", icon: FlaskConical },
  { id: "work_on_projects", label: "项目", short: "里程碑辅导", icon: FolderKanban },
];

type UploadRecord = Readonly<{
  key: string;
  file: File;
  previewUrl: string | null;
  state: "uploading" | "ready" | "failed";
  remote: AgentAttachment | null;
  error: string | null;
}>;

// PRD V3.0 P1-2: generate a client-side idempotency key for each turn so a
// browser retry after a lost response cannot create duplicate AgentTrace or
// LearningEvidence rows.  crypto.randomUUID is available in all modern
// browsers and in the Node server runtime.
function newClientRequestId(): string {
  return crypto.randomUUID();
}

type TurnRequest = Readonly<{
  scope: TeachingScope;
  mode: TeachingMode;
  conversationId: string | null;
  message: string;
  attempt: string;
  attachmentIds: readonly string[];
  scientificRequest: Record<string, unknown> | null;
  learningNative: LearningNativeSubmission | null;
  clientRequestId: string | null;
}>;

function isHitlOutcome(value: TeachingWorkflowOutcome): value is HitlInterruptResponse {
  return "status" in value && value.status === "interrupted";
}

// PRD V3.2 streaming: the latest per-stage progress event surfaced by the
// BFF stream.  ``step`` is the stage label (interpret, retrieve, diagnose,
// policy, scientific_tools, generate, learning_native, assemble, ...) or a
// lifecycle marker (workflow_started, workflow_running, workflow_completed,
// workflow_paused).  ``elapsed_seconds`` is the backend-reported wall clock
// since the workflow started.
type StageProgress = Readonly<{
  step: string;
  status: string;
  detail: string;
  elapsed_seconds: number;
}>;

// Human-readable labels for the canonical Golden Loop stages emitted by the
// backend ``progress`` events.  Unknown steps fall back to the raw label.
const STAGE_LABELS: Readonly<Record<string, string>> = {
  workflow_started: "教学流程已启动",
  workflow_running: "教学流程执行中",
  interpret: "理解你的问题",
  commitment_gate: "承诺门控（先思考再解释）",
  retrieve: "检索课程证据",
  diagnose: "诊断学习状态",
  policy: "应用答案政策",
  scientific_tools: "运行科学工具 / Coding Agent",
  generate: "生成教学回应",
  learning_native: "学习原生策略（教学回返 / 迁移）",
  hitl_gate: "等待人工复核",
  assemble: "汇总本轮结果",
  workflow_completed: "教学流程完成",
  workflow_paused: "教学流程暂停等待复核",
};

/**
 * PRD V3.2 streaming: consume the BFF SSE stream incrementally.
 *
 * The BFF now forwards ``workflow.started``, ``progress``, and keepalive
 * comments as they arrive, then the validated terminal event.  This helper
 * reads the response body with a ``ReadableStream`` reader, splits on
 * ``\n\n`` block boundaries, and invokes ``onProgress`` for each
 * ``progress`` event so the UI can render a live stage indicator.  It
 * returns the validated terminal payload (the same shape ``terminalEvent``
 * returns) and throws on ``workflow.failed`` or a missing terminal.
 *
 * The terminal contract is unchanged: exactly one terminal event is
 * expected, and it is validated by the BFF before forwarding.  This helper
 * only parses what the BFF already validated.
 */
async function consumeTeachingStream(
  response: Response,
  onProgress: (progress: StageProgress) => void,
): Promise<unknown> {
  if (!response.body) throw new Error("教学事件流缺少响应体。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal: unknown;
  let terminalCount = 0;
  let failure: string | null = null;

  const flushBlock = (block: string): "continue" | "done" => {
    if (!block.trim()) return "continue";
    // SSE comment blocks (": keepalive" heartbeats emitted on slow turns) carry
    // no event/data lines; per the SSE spec they must be ignored, not parsed.
    if (block.trimStart().startsWith(":")) return "continue";
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (event === "progress") {
      try {
        const payload = JSON.parse(data.join("\n")) as Record<string, unknown>;
        const step = typeof payload.step === "string" ? payload.step : "workflow";
        const status = typeof payload.status === "string" ? payload.status : "in_flight";
        const detail = typeof payload.detail === "string" ? payload.detail : "";
        const elapsed =
          typeof payload.elapsed_seconds === "number" ? payload.elapsed_seconds : 0;
        onProgress({ step, status, detail, elapsed_seconds: elapsed });
      } catch {
        // Ignore malformed progress events; the terminal contract is unaffected.
      }
      return "continue";
    }
    let payload: unknown;
    try {
      payload = JSON.parse(data.join("\n"));
    } catch {
      failure = "INVALID_UPSTREAM_CONTRACT";
      return "done";
    }
    if (event === "workflow.completed" || event === "workflow.interrupted") {
      terminal = payload;
      terminalCount += 1;
      return "done";
    }
    if (event === "workflow.failed") {
      const code =
        typeof payload === "object" && payload !== null
          ? (payload as Record<string, unknown>).code
          : null;
      failure = typeof code === "string" ? code : "WORKFLOW_FAILED";
      return "done";
    }
    // workflow.started and keepalive comments: no terminal action.
    return "continue";
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let separatorIndex: number;
    while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      if (flushBlock(block) === "done") {
        // Drain remaining buffered input without forwarding; the terminal
        // (or failure) has been observed.
        try {
          await reader.cancel("terminal event received");
        } catch {
          // already cancelled
        }
        if (failure) throw new Error(`教学工作流中止（${failure}）。`);
        if (terminal === undefined || terminalCount !== 1) {
          throw new Error("教学工作流没有返回唯一的完成或暂停记录。");
        }
        return terminal;
      }
    }
  }
  // Flush any trailing partial block.
  if (buffer.trim()) flushBlock(buffer);
  if (failure) throw new Error(`教学工作流中止（${failure}）。`);
  if (terminal === undefined || terminalCount !== 1) {
    throw new Error("教学工作流没有返回唯一的完成或暂停记录。");
  }
  return terminal;
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const payload: unknown = await response.json().catch(() => null);
  return parseTeachingApiError(payload)?.error.message ?? fallback;
}

function safeString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function safeObjects(value: unknown): ReadonlyArray<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          typeof item === "object" && item !== null && !Array.isArray(item),
      )
    : [];
}

function extractedEquations(attachments: readonly UploadRecord[]): string[] {
  const equations: string[] = [];
  for (const record of attachments) {
    const evidence = record.remote?.extraction?.evidence;
    for (const item of safeObjects(evidence?.derivation_steps)) {
      const latex = safeString(item.latex);
      if (latex) equations.push(latex);
    }
    for (const item of safeObjects(evidence?.equations)) {
      const latex = safeString(item.latex);
      if (latex) equations.push(latex);
    }
  }
  return [...new Set(equations)].slice(0, 20);
}

function interruptTranscription(interrupt: HitlInterruptResponse): string {
  for (const evidence of interrupt.artifacts.multimodal_evidence) {
    const steps = safeObjects(evidence.derivation_steps)
      .map((step) => safeString(step.source_text) ?? safeString(step.latex))
      .filter((item): item is string => item !== null);
    const equations = safeObjects(evidence.equations)
      .map((equation) => safeString(equation.source_text) ?? safeString(equation.latex))
      .filter((item): item is string => item !== null);
    const detected = safeString(evidence.detected_text);
    const units = safeObjects(evidence.units)
      .map((unit) => safeString(unit.exact_text))
      .filter((item): item is string => item !== null);
    let candidateParts = units;
    if (detected) candidateParts = [detected];
    if (equations.length) candidateParts = equations;
    if (steps.length) candidateParts = steps;
    const candidate = candidateParts.join("\n");
    if (candidate.trim()) return candidate.slice(0, 12_000);
  }
  return "";
}

function sourceLocator(evidence: TeachingEvidence): string {
  const locator = evidence.locator;
  if (locator.slide_number) return `幻灯片 ${locator.slide_number}`;
  if (locator.physical_page) return `第 ${locator.physical_page} 页`;
  if (locator.paragraph_start) return `段落 ${locator.paragraph_start}`;
  if (locator.line_start) return `行 ${locator.line_start}`;
  return "原文定位";
}

function sourceHref(scope: TeachingScope, evidence: TeachingEvidence): string {
  const query = new URLSearchParams({
    course_id: scope.courseId,
    curriculum_edition_id: scope.curriculumEditionId,
  });
  return `/api/agent/sources/${evidence.document_version_id}/original?${query.toString()}`;
}

function ModeMark({ mode }: { mode: TeachingMode }) {
  const item = MODES.find((candidate) => candidate.id === mode) ?? MODES[0]!;
  const Icon = item.icon;
  return <Icon aria-hidden="true" />;
}

// Canonical order of the tutor-graph stages emitted by backend ``progress``
// events.  The spine maps each of its steps onto one or more of these stages
// so step states derive from REAL streaming events, never from a pending flag.
const PROGRESS_ORDER: readonly string[] = [
  "workflow_started",
  "interpret",
  "commitment_gate",
  "retrieve",
  "diagnose",
  "policy",
  "scientific_tools",
  "generate",
  "learning_native",
  "hitl_gate",
  "assemble",
];

function EvidenceSpine({
  uploads,
  result,
  interrupt,
  progressStep,
}: {
  uploads: readonly UploadRecord[];
  result: TeachingTurnResult | null;
  interrupt: HitlInterruptResponse | null;
  progressStep: string | null;
}) {
  const perceptionReady =
    uploads.length === 0 ||
    uploads.every(
      (item) =>
        item.state === "ready" &&
        item.remote?.extraction?.status !== "needs_confirmation",
    );
  const reviewed = result ?? interrupt?.artifacts ?? null;
  const stages = [
    { label: "输入", graphStages: [] as readonly string[], done: uploads.length > 0 || Boolean(reviewed), detail: uploads.length ? `${uploads.length} 个附件` : "文本" },
    { label: "感知", graphStages: ["interpret"] as readonly string[], done: perceptionReady, detail: uploads.length ? "结构化提取" : "无需调用" },
    { label: "证据", graphStages: ["retrieve"] as readonly string[], done: Boolean(reviewed), detail: reviewed ? reviewed.evidence_packet.coverage : "课程检索" },
    { label: "诊断", graphStages: ["commitment_gate", "diagnose"] as readonly string[], done: Boolean(reviewed), detail: reviewed ? reviewed.diagnosis.status : "首错定位" },
    { label: "验证", graphStages: ["scientific_tools"] as readonly string[], done: Boolean(reviewed), detail: reviewed?.scientific_results.length ? "工具证据" : "按需运行" },
    { label: "提示", graphStages: ["policy", "generate", "learning_native", "assemble"] as readonly string[], done: Boolean(result), detail: interrupt ? "等待人工确认" : result?.release.release_level ?? "政策门控" },
  ];
  // While a turn is running, each step's state comes from the latest real
  // ``progress`` event: stages before the current one are done, the current
  // one is active.  No event yet → all pending steps stay idle (no fake
  // progress).
  const currentIndex = progressStep ? PROGRESS_ORDER.indexOf(progressStep) : -1;
  const stateFor = (stage: (typeof stages)[number], index: number): string => {
    if (stage.done) return "done";
    if (currentIndex < 0) return "idle";
    const stageIndexes = stage.graphStages.map((step) => PROGRESS_ORDER.indexOf(step));
    if (stageIndexes.some((stepIndex) => stepIndex === currentIndex)) return "active";
    if (stageIndexes.some((stepIndex) => stepIndex >= 0 && stepIndex < currentIndex)) return "done";
    return index === 0 && progressStep ? "done" : "idle";
  };
  return (
    <ol className={styles.evidenceSpine} aria-label="本轮证据链" data-testid="evidence-spine">
      {stages.map((stage, index) => (
        <li key={stage.label} data-state={stateFor(stage, index)}>
          <span>{stage.done ? <Check size={12} /> : String(index + 1).padStart(2, "0")}</span>
          <div><strong>{stage.label}</strong><small>{stage.detail}</small></div>
        </li>
      ))}
    </ol>
  );
}

/** Renders tutor prose with inline ``$...$`` math as first-class KaTeX. */
function MathText({ text }: { text: string }) {
  const parts = text.split(/(\$[^$\n]+\$)/g).filter((part) => part.length > 0);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("$") && part.endsWith("$") && part.length > 2 ? (
          <AgentEquation key={`${index}-${part}`} latex={part.slice(1, -1)} display={false} />
        ) : (
          <span key={`${index}-t`}>{part}</span>
        ),
      )}
    </>
  );
}

const HITL_REASON_LABELS: Readonly<Record<string, string>> = {
  ta_requested: "已请求助教",
  ambiguous_transcription: "转录存在歧义",
  evidence_conflict: "课程证据冲突",
  insufficient_coverage: "课程覆盖不足",
  verifier_model_disagreement: "模型与验证器结论不一致",
  repeated_no_progress: "多次尝试仍未推进",
  teacher_approval_required: "需要教师批准",
  project_milestone_review: "里程碑需要审阅",
  safety_condition: "安全条件触发",
};

function HitlReviewCard({
  interrupt,
  confirmedText,
  setConfirmedText,
  pending,
  error,
  confirm,
}: {
  interrupt: HitlInterruptResponse;
  confirmedText: string;
  setConfirmedText: (value: string) => void;
  pending: boolean;
  error: string | null;
  confirm: () => void;
}) {
  const canConfirm = interrupt.interrupt.student_allowed_actions.includes(
    "confirm_transcription",
  );
  return (
    <section className={styles.hitlCard} aria-live="polite" data-testid="hitl-interrupt">
      <header>
        <span><CircleAlert aria-hidden="true" /></span>
        <div>
          <p className={styles.kicker}>WORKFLOW PAUSED / SAME THREAD</p>
          <h2>{canConfirm ? "请确认转录，再继续诊断" : "本轮正在等待助教或教师复核"}</h2>
        </div>
        <em>PAUSED</em>
      </header>
      <div className={styles.hitlReasons}>
        {interrupt.interrupt.reasons.map((reason) => (
          <span key={reason}>{HITL_REASON_LABELS[reason] ?? reason}</span>
        ))}
      </div>
      <p className={styles.hitlPrompt}>{interrupt.interrupt.prompt}</p>
      <p className={styles.hitlExplanation}>
        {canConfirm
          ? "系统不会自动修正低置信度符号。请核对下面的推导文本；确认后会在同一线程重新运行诊断、验证器与政策门。"
          : "拟议回答不会提前显示。证据、诊断、政策决定与工具结果已锁定在右侧证据台，只有教学人员可以批准、编辑、拒绝或接管。"}
      </p>
      <dl className={styles.hitlAudit}>
        <div><dt>证据覆盖</dt><dd>{interrupt.artifacts.evidence_packet.coverage}</dd></div>
        <div><dt>诊断状态</dt><dd>{interrupt.artifacts.diagnosis.status}</dd></div>
        <div><dt>政策上限</dt><dd>{interrupt.artifacts.release.release_level}</dd></div>
        <div><dt>验证器</dt><dd>{interrupt.artifacts.scientific_results.length} 项</dd></div>
      </dl>
      {canConfirm ? (
        <div className={styles.hitlConfirmation}>
          <label htmlFor="hitl-confirmed-transcription">确认后的推导或尝试</label>
          <textarea
            id="hitl-confirmed-transcription"
            value={confirmedText}
            onChange={(event) => setConfirmedText(event.target.value)}
            rows={6}
            maxLength={12_000}
            spellCheck={false}
          />
          <footer>
            <small>{confirmedText.length.toLocaleString()} / 12,000</small>
            <button
              type="button"
              onClick={confirm}
              disabled={pending || !confirmedText.trim()}
            >
              {pending ? <LoaderCircle className={styles.spin} /> : <Check />}
              {pending ? "正在继续同一线程" : "确认转录并继续"}
            </button>
          </footer>
        </div>
      ) : null}
      {error ? <p className={styles.hitlError}><CircleAlert /> {error}</p> : null}
      <small className={styles.hitlIdentity}>Interrupt {interrupt.interrupt.interrupt_id.slice(0, 8)}</small>
    </section>
  );
}

function SourcePreview({
  evidence,
  scope,
  close,
}: {
  evidence: TeachingEvidence;
  scope: TeachingScope;
  close: () => void;
}) {
  const href = sourceHref(scope, evidence);
  const isPdf = evidence.source_file_name.toLowerCase().endsWith(".pdf");
  return (
    <Dialog.Portal>
      <Dialog.Overlay className={styles.dialogOverlay} />
      <Dialog.Content
        className={styles.sourceDialog}
        aria-describedby="source-preview-description"
        data-testid="source-preview"
      >
        <header>
          <div>
            <Dialog.Title>{evidence.document_title}</Dialog.Title>
            <Dialog.Description id="source-preview-description">
              {sourceLocator(evidence)} · v{evidence.document_version} · 完整性已由后端校验
            </Dialog.Description>
          </div>
          <Dialog.Close onClick={close} aria-label="关闭原文预览"><X size={18} /></Dialog.Close>
        </header>
        {isPdf ? (
          <iframe src={`${href}#page=${evidence.locator.physical_page ?? 1}`} title={`${evidence.document_title} 原文`} />
        ) : (
          <div className={styles.downloadSource}>
            <FileText size={32} />
            <p>该来源格式由浏览器下载后在本地应用中打开。</p>
            <a href={href}>打开原始文件</a>
          </div>
        )}
      </Dialog.Content>
    </Dialog.Portal>
  );
}

function SessionRequiredView({
  onReload,
}: {
  onReload: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function submitApiKeyLogin(event: FormEvent) {
    event.preventDefault();
    const trimmed = apiKey.trim();
    if (!trimmed || submitting || trimmed.length < 16) return;
    setSubmitting(true);
    setLoginError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: trimmed }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        if (response.status === 401) {
          setLoginError(detail.error ?? "API Key 被模型服务拒绝或模型服务不可用。");
        } else if (response.status === 429) {
          setLoginError(detail.error ?? "登录尝试过于频繁，请稍后再试。");
        } else {
          setLoginError(detail.error ?? "登录被拒绝。");
        }
        return;
      }
      setApiKey("");
      onReload();
    } catch {
      setLoginError("无法连接教学服务。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.bootError}>
      <Atom size={34} />
      <p className={styles.kicker}>QUANTUM AGENT / 连接中国科大</p>
      <h1>词元计划 · 一〇七杯</h1>
      <p>输入你的 API Key，连接学校模型服务并进入学习空间。Key 只会经 HTTPS 发送到后端保险库，不会写入浏览器、日志或 Agent Trace。</p>
      <form onSubmit={submitApiKeyLogin} className={styles.demoLogin} aria-label="API Key 登录表单">
        <p className={styles.kicker}>MODEL SERVICE LOGIN</p>
        <label htmlFor="ustc-api-key">API Key</label>
        <input
          id="ustc-api-key"
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          maxLength={256}
          placeholder="粘贴词元计划 / 一〇七杯 API Key"
          aria-label="USTC API Key"
        />
        <button type="submit" disabled={submitting || apiKey.trim().length < 16}>
          {submitting ? "正在连接…" : "连接并进入学习空间"}
        </button>
        {loginError ? (
          <p className={styles.hitlError} aria-live="polite"><CircleAlert /> {loginError}</p>
        ) : null}
      </form>
      <button onClick={onReload}>重新检查会话</button>
    </main>
  );
}

export function AgentExperience() {
  const contextQuery = useQuery({
    queryKey: ["agent-course-context"],
    queryFn: async () => {
      const response = await fetch("/api/agent/context", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "无法读取课程范围。"));
      return parseStudentCourseContext(await response.json());
    },
  });
  const [courseKey, setCourseKey] = useState<string | null>(null);
  const [mode, setMode] = useState<TeachingMode>("review_derivations");
  const [message, setMessage] = useState("");
  const [attempt, setAttempt] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [result, setResult] = useState<TeachingTurnResult | null>(null);
  const [interrupt, setInterrupt] = useState<HitlInterruptResponse | null>(null);
  const [confirmedTranscription, setConfirmedTranscription] = useState("");
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [selectedSource, setSelectedSource] = useState<TeachingEvidence | null>(null);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdQuery, setCmdQuery] = useState("");
  const [expandedClaim, setExpandedClaim] = useState<number | null>(null);
  const [showAttempt, setShowAttempt] = useState(false);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCmdOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const [projectCode, setProjectCode] = useState("# 在这里放置当前里程碑的最小可运行代码\n");
  const [dragging, setDragging] = useState(false);
  const [rabiFrequency, setRabiFrequency] = useState(1);
  const [detuning, setDetuning] = useState(0);
  const [duration, setDuration] = useState(8);
  const [goldenTunnelling, setGoldenTunnelling] = useState(false);
  const [barrierEnergy, setBarrierEnergy] = useState(5);
  const [barrierHeight, setBarrierHeight] = useState(10);
  const [barrierWidth, setBarrierWidth] = useState(1e-10);
  // PRD V3.2 streaming: per-stage progress surfaced to the user while the
  // teaching workflow runs.  The BFF now streams ``progress`` SSE events as
  // each graph node begins; we render the latest stage + elapsed_seconds so
  // the user sees useful activity within ~1s instead of a blank loading
  // period.  Cleared on the next turn submit and on terminal.
  const [stageProgress, setStageProgress] = useState<StageProgress | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewUrlsRef = useRef(new Set<string>());

  const courses = useMemo(() => contextQuery.data?.courses ?? [], [contextQuery.data?.courses]);
  useEffect(() => {
    if (!courseKey && courses[0]) {
      setCourseKey(`${courses[0].course_id}:${courses[0].curriculum_edition_id}`);
    }
  }, [courseKey, courses]);
  // PRD V3.0 P0-2: persist the conversation ID across refresh / new tab so
  // Solo Mode and the durable Learning Phase survive a page reload.  The
  // backend is the source of truth; this only restores the thread identity.
  //
  // On mount ``conversationId`` is null, so a naive persist effect would call
  // ``removeItem`` before restore reads the stored id and the thread would
  // never survive reload.  ``hasConversationRef`` gates the remove branch so
  // the key is only cleared when the user explicitly starts a new thread
  // AFTER having one, never on a bare initial mount.
  const hasConversationRef = useRef(false);
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("qa_conversation_id");
      if (stored && !conversationId) {
        setConversationId(stored);
      }
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (conversationId) {
      hasConversationRef.current = true;
      try {
        window.localStorage.setItem("qa_conversation_id", conversationId);
      } catch {
        // localStorage may be unavailable (private mode); fail silently.
      }
    } else if (hasConversationRef.current) {
      // Explicit "new thread": clear the stored id only after we had one.
      try {
        window.localStorage.removeItem("qa_conversation_id");
      } catch {
        // ignore
      }
      hasConversationRef.current = false;
    }
  }, [conversationId]);
  const activeCourse =
    courses.find(
      (course) => `${course.course_id}:${course.curriculum_edition_id}` === courseKey,
    ) ?? courses[0] ?? null;
  const scope = activeCourse ? scopeFromCourse(activeCourse) : null;

  // Release-review P1 fix: recover a pending HITL pause after a refresh.
  // The interrupt is persisted server-side; re-fetch it once per restored
  // conversation so the transcription-confirmation card is not lost.
  const interruptRecoveryRef = useRef<string | null>(null);
  useEffect(() => {
    if (!scope || !conversationId || interrupt) return;
    if (interruptRecoveryRef.current === conversationId) return;
    interruptRecoveryRef.current = conversationId;
    const controller = new AbortController();
    const query = new URLSearchParams({
      course_id: scope.courseId,
      curriculum_edition_id: scope.curriculumEditionId,
    });
    fetch(`/api/teaching/threads/${conversationId}/interrupt?${query.toString()}`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) return;
        const pause = redactHitlProposedResponse(
          parseHitlInterruptResponse(await response.json()),
        );
        assertHitlScope(pause, scope, pause.artifacts.policy.mode);
        if (pause.conversation_id !== conversationId) return;
        setInterrupt(pause);
        setConfirmedTranscription(interruptTranscription(pause));
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [scope, conversationId, interrupt]);

  useEffect(() => () => {
    for (const previewUrl of previewUrlsRef.current) URL.revokeObjectURL(previewUrl);
  }, []);

  const turnMutation = useMutation({
    mutationFn: async (input: TurnRequest) => {
      const body = parseTeachingTurnRequest({
        conversation_id: input.conversationId,
        mode: input.mode,
        message: input.message,
        student_attempt: input.attempt || null,
        attachment_ids: input.attachmentIds,
        scientific_request: input.scientificRequest,
        learning_native: input.learningNative,
        client_request_id: input.clientRequestId,
      });
      const query = new URLSearchParams({
        course_id: input.scope.courseId,
        curriculum_edition_id: input.scope.curriculumEditionId,
      });
      setStageProgress({
        step: "workflow_started",
        status: "started",
        detail: "教学流程已启动",
        elapsed_seconds: 0,
      });
      const response = await fetch(`/api/teaching/turns/stream?${query.toString()}`, {
        method: "POST",
        headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "教学工作流不可用。"));
      // PRD V3.2 streaming: consume the SSE stream incrementally so the UI
      // renders per-stage progress as each ``progress`` event arrives.  The
      // terminal event is still validated by the BFF before forwarding, and
      // ``consumeTeachingStream`` enforces the exactly-one-terminal contract
      // on the client side too.
      const parsed = parseTeachingWorkflowOutcome(
        await consumeTeachingStream(response, (progress) => setStageProgress(progress)),
      );
      if (isHitlOutcome(parsed)) assertHitlScope(parsed, input.scope, input.mode);
      else assertTeachingScope(parsed, input.scope, input.mode);
      return parsed;
    },
    onMutate: () => {
      setStageProgress(null);
    },
    onSuccess: (next, variables) => {
      setConversationId(next.conversation_id);
      if (isHitlOutcome(next)) {
        setInterrupt(next);
        setResult(null);
        setConfirmedTranscription(interruptTranscription(next) || variables.attempt);
      } else {
        setResult(next);
        setInterrupt(null);
        setConfirmedTranscription("");
      }
      // Do NOT auto-open the right Evidence panel on every turn.  The spec
      // says evidence may be *suggested* when new evidence arrives, but the
      // panel must never steal focus or intercept the composer / commitment
      // controls.  Auto-opening here caused the expanded right rail to
      // overlay the "提交承诺" button (pointer-events intercepted), blocking
      // the student from submitting.  The student opens Evidence via the
      // topbar "打开证据面板" button on demand.
    },
    onSettled: () => {
      // Keep the final stage visible briefly so the user sees "完成"; it is
      // cleared on the next submit via ``onMutate``.
    },
  });

  const resumeMutation = useMutation({
    mutationFn: async (input: {
      scope: TeachingScope;
      mode: TeachingMode;
      conversationId: string;
      interruptId: string;
      confirmedAttempt: string;
    }) => {
      const query = new URLSearchParams({
        course_id: input.scope.courseId,
        curriculum_edition_id: input.scope.curriculumEditionId,
      });
      const response = await fetch(
        `/api/teaching/threads/${input.conversationId}/resume?${query.toString()}`,
        {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({
            interrupt_id: input.interruptId,
            mode: input.mode,
            action: "confirm_transcription",
            confirmed_student_attempt: input.confirmedAttempt,
          }),
        },
      );
      if (!response.ok) {
        throw new Error(await responseMessage(response, "无法继续当前教学线程。"));
      }
      const parsed = parseTeachingWorkflowOutcome(await response.json());
      if (isHitlOutcome(parsed)) assertHitlScope(parsed, input.scope, input.mode);
      else assertTeachingScope(parsed, input.scope, input.mode);
      if (parsed.conversation_id !== input.conversationId) {
        throw new Error("继续执行后教学线程标识发生变化。");
      }
      return parsed;
    },
    onSuccess: (next) => {
      setConversationId(next.conversation_id);
      if (isHitlOutcome(next)) {
        setInterrupt(next);
        setResult(null);
        setConfirmedTranscription((current) => interruptTranscription(next) || current);
      } else {
        setResult(next);
        setInterrupt(null);
        setConfirmedTranscription("");
      }
      // Do NOT auto-open the right Evidence panel after HITL resume either;
      // the expanded rail overlays the composer / commitment controls and
      // blocks pointer events (see turnMutation.onSuccess note above).
    },
  });

  async function uploadFile(record: UploadRecord, uploadScope: TeachingScope) {
    const query = new URLSearchParams({
      course_id: uploadScope.courseId,
      curriculum_edition_id: uploadScope.curriculumEditionId,
    });
    const body = new FormData();
    body.set("file", record.file, record.file.name);
    try {
      const response = await fetch(`/api/agent/attachments?${query.toString()}`, {
        method: "POST",
        body,
      });
      if (!response.ok) throw new Error(await responseMessage(response, "附件处理失败。"));
      const remote = parseAgentAttachment(await response.json());
      setUploads((current) =>
        current.map((item) =>
          item.key === record.key ? { ...item, state: "ready", remote, error: null } : item,
        ),
      );
    } catch (error) {
      setUploads((current) =>
        current.map((item) =>
          item.key === record.key
            ? {
                ...item,
                state: "failed",
                error: error instanceof Error ? error.message : "附件处理失败。",
              }
            : item,
        ),
      );
    }
  }

  function addFiles(files: readonly File[]) {
    if (!scope || interrupt) return;
    for (const file of files.slice(0, Math.max(0, 6 - uploads.length))) {
      const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : null;
      if (previewUrl) previewUrlsRef.current.add(previewUrl);
      const record: UploadRecord = {
        key: crypto.randomUUID(),
        file,
        previewUrl,
        state: "uploading",
        remote: null,
        error: null,
      };
      setUploads((current) => [...current, record]);
      void uploadFile(record, scope);
    }
  }

  function removeUpload(record: UploadRecord) {
    if (record.previewUrl) {
      URL.revokeObjectURL(record.previewUrl);
      previewUrlsRef.current.delete(record.previewUrl);
    }
    setUploads((current) => current.filter((item) => item.key !== record.key));
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const images = [...event.clipboardData.items]
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null);
    if (images.length) addFiles(images);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles([...event.dataTransfer.files]);
  }

  function submit() {
    if (!scope || interrupt || turnMutation.isPending || resumeMutation.isPending) return;
    const ready = uploads.filter((item) => item.remote && item.state === "ready");
    const codeAttempt = mode === "work_on_projects" ? `\n\n[当前代码]\n${projectCode}` : "";
    const combinedAttempt = [attempt.trim(), codeAttempt]
      .filter(Boolean)
      .join("\n\n")
      .slice(0, 12_000);
    const fallbackMessage = {
      learn_concepts: "请结合我上传的材料，帮助我理解其中的课程概念。",
      review_derivations: "请检查我上传的推导，定位第一个有后果的错误并只给最小提示。",
      run_experiments: "请结合我上传的图与数值验证，检查我的物理解释。",
      work_on_projects: "请审查当前里程碑，只给完成下一小步所需的指导。",
    }[mode];
    const scientificRequest =
      mode === "run_experiments"
        ? goldenTunnelling
          ? {
              kind: "rectangular_barrier_tunnelling",
              energy_eV: barrierEnergy,
              barrier_height_eV: barrierHeight,
              barrier_width_m: barrierWidth,
              particle_mass_kg: 9.1093837015e-31,
              conservation_tolerance: 1e-9,
            }
          : {
              kind: "two_level_simulation",
              initial_state: [
                { real: 1, imag: 0 },
                { real: 0, imag: 0 },
              ],
              rabi_frequency: rabiFrequency,
              detuning,
              duration,
              steps: 400,
              absolute_tolerance: 1e-7,
            }
        : null;
    turnMutation.mutate({
      scope,
      mode,
      conversationId,
      message: message.trim() || fallbackMessage,
      attempt: combinedAttempt,
      attachmentIds: ready.flatMap((item) => (item.remote ? [item.remote.id] : [])),
      scientificRequest,
      learningNative: null,
      clientRequestId: newClientRequestId(),
    });
  }

  function submitLearningNative(submission: LearningNativeSubmission) {
    if (!scope || interrupt || turnMutation.isPending || resumeMutation.isPending) return;
    turnMutation.mutate({
      scope,
      mode,
      conversationId,
      message: message.trim() || "继续 Learning-Native 学习循环。",
      attempt: "",
      attachmentIds: [],
      scientificRequest: null,
      learningNative: submission,
      clientRequestId: newClientRequestId(),
    });
  }

  function startGoldenTunnelingLoop() {
    if (!scope || interrupt || turnMutation.isPending) return;
    setMessage("我想学习量子隧穿：为什么 E<V0 时粒子仍可能透射？请用 Learning-Native 循环引导我。");
    setMode("run_experiments");
    setGoldenTunnelling(true);
    setResult(null);
    setInterrupt(null);
    setConversationId(null);
    setConfirmedTranscription("");
  }

  function confirmInterruptedTranscription() {
    if (
      !scope ||
      !interrupt ||
      !conversationId ||
      !interrupt.interrupt.student_allowed_actions.includes("confirm_transcription") ||
      !confirmedTranscription.trim()
    ) {
      return;
    }
    resumeMutation.mutate({
      scope,
      mode,
      conversationId,
      interruptId: interrupt.interrupt.interrupt_id,
      confirmedAttempt: confirmedTranscription.trim(),
    });
  }

  const equations = useMemo(() => extractedEquations(uploads), [uploads]);
  const uploading = uploads.some((item) => item.state === "uploading");
  const reviewed = result ?? interrupt?.artifacts ?? null;
  const evidencePacket = reviewed?.evidence_packet ?? null;
  const diagnosis = reviewed?.diagnosis ?? null;
  const release = reviewed?.release ?? null;
  const scientificResults = reviewed?.scientific_results ?? [];
  const validation = reviewed?.validation ?? null;
  const interpretation = reviewed?.interpretation ?? null;
  const reviewedVisualSpec = scientificResults.find((item) => item.visualization)?.visualization;
  const activeMode = MODES.find((item) => item.id === mode) ?? MODES[0]!;
  // PRD V3.3: the answer is withheld whenever the authoritative durable
  // LearningPhase requires a student action the turn has not satisfied.  This
  // is driven by the backend's ``required_action`` (a pure function of the
  // persisted phase), not by a heuristic on the commitment card.  The loop is
  // complete only when the backend says so via ``learning_loop_completed`` —
  // never inferred from the SSE ``workflow.completed`` lifecycle event.
  const nativeState = result?.learning_native ?? null;
  const requiredAction = nativeState?.required_action ?? "none";
  const answerWithheldByGate =
    requiredAction !== "none" && nativeState?.phase !== "complete";
  const loopDone = result?.learning_loop_completed === true;

  // Phase-driven Stage title + tag.  The Stage itself is the visual center;
  // this quiet label is the only orienting text.  Everything else is the
  // scientific object (equation / plot / code / verification / evidence).
  const stageTitle = useMemo(() => {
    if (interrupt) return "等待确认转录";
    if (loopDone) return "学习闭环 · Cognitive Mirror";
    if (nativeState?.solo?.status === "active") return "Solo Mode · 独立迁移";
    if (nativeState?.transfer) return "迁移任务";
    if (nativeState?.teach_back) return "Teach-Back · 用你的话讲一遍";
    if (nativeState?.commitment && !nativeState.commitment.accepted) return "先做一个预测";
    if (result) return result.interpretation.relevant_concepts.join(" · ") || "课程辅导";
    return activeMode.short;
  }, [interrupt, loopDone, nativeState, result, activeMode.short]);
  const stagePhaseLabel = useMemo(() => {
    if (interrupt) return "PAUSED";
    if (loopDone) return "COMPLETE";
    if (nativeState) {
      const map: Record<string, string> = {
        commitment_required: "COMMITMENT",
        attempt_received: "ATTEMPT",
        intervention: "INTERVENE",
        awaiting_revision: "REVISE",
        verifying: "VERIFY",
        reconstruction_required: "TEACH-BACK",
        transfer_required: "TRANSFER",
        solo_active: "SOLO",
        complete: "COMPLETE",
        aborted: "ABORTED",
        open: "OPEN",
      };
      return map[nativeState.phase] ?? nativeState.phase.toUpperCase();
    }
    return activeMode.label.toUpperCase();
  }, [interrupt, loopDone, nativeState, activeMode.label]);

  if (contextQuery.isPending) {
    return <main className={styles.boot}><Atom /><p>正在建立课程边界与证据索引…</p></main>;
  }
  if (contextQuery.isError || !contextQuery.data) {
    return <SessionRequiredView onReload={() => void contextQuery.refetch()} />;
  }
  if (!activeCourse || !scope) {
    return <main className={styles.bootError}><h1>尚无已发布课程</h1><p>请联系任课教师开通课程版本。</p></main>;
  }

  return (
    <div className={styles.agentShell} data-testid="agent-experience">
      <a className={styles.skipLink} href="#agent-main">跳到教学工作区</a>
      <header className={styles.topbar}>
        <button className={styles.mobileButton} onClick={() => setLeftOpen(true)} aria-label="打开课程导航"><Menu /></button>
        <div className={styles.brand}><span><Atom /></span></div>
        <div className={styles.courseTitle}>
          <span>{activeCourse.course_code}</span><i />
          <strong>{activeCourse.course_title}</strong><i />
          <small>{activeCourse.edition_title}</small>
        </div>
        <div className={styles.topActions}>
          <span className={styles.liveState} data-testid="model-service-status"><i /> {interrupt ? "工作流已暂停" : "模型服务已连接"}</span>
          <button className={styles.cmdHint} onClick={() => setCmdOpen(true)} aria-label="打开命令面板">
            <Search size={14} /><kbd>⌘K</kbd>
          </button>
          <button onClick={() => setRightOpen(true)} aria-label="打开证据面板"><PanelRight size={15} /><span>证据</span></button>
          <span className={styles.userMark}>{contextQuery.data.display_name.slice(0, 1)}</span>
        </div>
      </header>

      {(leftOpen || rightOpen) ? <button className={`${styles.backdrop} ${styles.visible}`} onClick={() => { setLeftOpen(false); setRightOpen(false); }} aria-label="关闭面板" /> : null}
      <aside className={`${styles.leftPanel} ${leftOpen ? styles.panelOpen : ""}`}>
        <div className={styles.mobilePanelTitle}><strong>课程导航</strong><button onClick={() => setLeftOpen(false)}><X /></button></div>
        {MODES.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={styles.railIconButton}
              data-active={mode === item.id ? "true" : "false"}
              onClick={() => {
                setMode(item.id);
                setConversationId(null);
                setResult(null);
                setInterrupt(null);
                setConfirmedTranscription("");
                setLeftOpen(false);
              }}
              aria-label={`${item.label}模式 · ${item.short}`}
              title={`${item.label} · ${item.short}`}
            >
              <Icon />
            </button>
          );
        })}
        <div className={styles.railDivider} />
        <button
          className={styles.railIconButton}
          onClick={() => setRightOpen(true)}
          aria-label="打开证据面板"
          title="证据与验证"
        >
          <PanelRight />
        </button>
        <button
          className={styles.railIconButton}
          onClick={() => setRightOpen(true)}
          aria-label="课程知识图谱"
          title="课程关系图谱"
        >
          <Network />
        </button>
        <button
          className={styles.railIconButton}
          onClick={() => setCmdOpen(true)}
          aria-label="命令面板"
          title="命令面板 ⌘K"
        >
          <Search />
        </button>
        <div className={styles.railSpacer} />
        <button
          className={styles.railIconButton}
          onClick={() => { setConversationId(null); setResult(null); setInterrupt(null); setConfirmedTranscription(""); }}
          aria-label="新建学习记录"
          title="新建学习记录"
        >
          <Plus />
        </button>
      </aside>

      <main className={styles.mainPanel} id="agent-main">
        <div className={styles.workspaceScroll}>
          <section className={styles.stageHead}>
            <h1>{stageTitle}</h1>
            <span className={styles.phaseTag}><i />{stagePhaseLabel}</span>
          </section>

          <LearningJourney state={nativeState} />

          {nativeState ? (
            <span
              className={styles.kicker}
              data-testid="learning-phase"
              data-phase={nativeState.phase}
              data-required-action={nativeState.required_action}
              data-loop-completed={loopDone ? "true" : "false"}
              aria-hidden="true"
              style={{ position: "absolute", left: "-9999px" }}
            >
              phase={nativeState.phase}
            </span>
          ) : null}

          <EvidenceSpine
            uploads={uploads}
            result={result}
            interrupt={interrupt}
            progressStep={
              turnMutation.isPending || resumeMutation.isPending
                ? stageProgress?.step ?? null
                : null
            }
          />

          {interrupt ? (
            <HitlReviewCard
              interrupt={interrupt}
              confirmedText={confirmedTranscription}
              setConfirmedText={setConfirmedTranscription}
              pending={resumeMutation.isPending}
              error={resumeMutation.error?.message ?? null}
              confirm={confirmInterruptedTranscription}
            />
          ) : null}

          {mode === "review_derivations" && equations.length ? (
            <section className={styles.derivationSheet}>
              <header><div><p className={styles.kicker}>VISION TRANSCRIPTION</p><h2>学生推导转录</h2></div><span>{equations.length} steps</span></header>
              <ol>{equations.map((equation, index) => <li key={`${equation}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><AgentEquation latex={equation} /><i>{diagnosis?.first_error?.step_index === index ? <CircleAlert /> : <Check />}</i></li>)}</ol>
            </section>
          ) : null}

          {mode === "run_experiments" ? (
            <section className={styles.experimentGrid}>
              <div className={styles.parameterPanel}>
                <p className={styles.kicker}>NUMERICAL INPUT</p>
                <div className={styles.experimentModeToggle}>
                  <label>
                    <input
                      type="checkbox"
                      checked={goldenTunnelling}
                      onChange={(event) => setGoldenTunnelling(event.target.checked)}
                      aria-label="切换到量子隧穿矩势垒模拟"
                    />
                    <span>矩势垒隧穿（Golden Loop）</span>
                  </label>
                </div>
                {goldenTunnelling ? (
                  <>
                    <h2>矩势垒散射</h2>
                    <label>粒子能量 E (eV) <strong>{barrierEnergy.toFixed(2)}</strong><input type="range" min="0.5" max="9" step="0.1" value={barrierEnergy} onChange={(event) => setBarrierEnergy(Number(event.target.value))} /></label>
                    <label>势垒高度 V₀ (eV) <strong>{barrierHeight.toFixed(2)}</strong><input type="range" min="1" max="20" step="0.1" value={barrierHeight} onChange={(event) => setBarrierHeight(Number(event.target.value))} /></label>
                    <label>势垒宽度 a (nm) <strong>{(barrierWidth * 1e9).toFixed(3)}</strong><input type="range" min="0.05" max="5" step="0.05" value={barrierWidth * 1e9} onChange={(event) => setBarrierWidth(Number(event.target.value) * 1e-9)} /></label>
                    <small data-testid="tunnelling-regime-hint">
                      {barrierEnergy < barrierHeight
                        ? "E < V₀：量子隧穿区（解析 T 公式）"
                        : "E > V₀：自由传播区（振荡 T 公式）"}
                    </small>
                  </>
                ) : (
                  <>
                    <h2>二能级系统</h2>
                    <label>Rabi 频率 <strong>{rabiFrequency.toFixed(2)}</strong><input type="range" min="0.1" max="4" step="0.1" value={rabiFrequency} onChange={(event) => setRabiFrequency(Number(event.target.value))} /></label>
                    <label>失谐量 <strong>{detuning.toFixed(2)}</strong><input type="range" min="-4" max="4" step="0.1" value={detuning} onChange={(event) => setDetuning(Number(event.target.value))} /></label>
                    <label>演化时间 <strong>{duration.toFixed(1)}</strong><input type="range" min="1" max="20" step="0.5" value={duration} onChange={(event) => setDuration(Number(event.target.value))} /></label>
                  </>
                )}
              </div>
              <div className={styles.plotPanel}>
                <p className={styles.kicker}>VERIFIED PLOT</p>
                {reviewedVisualSpec ? <AgentPlot spec={reviewedVisualSpec} /> : <div className={styles.plotEmpty}><FlaskConical /><strong>先预测，再运行数值验证</strong><small>图像解释将与真实计算结果并列显示。</small></div>}
              </div>
            </section>
          ) : null}

          {mode === "work_on_projects" ? (
            <section className={styles.codePanel}><header><div><p className={styles.kicker}>MILESTONE ARTIFACT</p><h2>当前可运行片段</h2></div><span>Python</span></header><AgentCodeEditor value={projectCode} onChange={setProjectCode} /></section>
          ) : null}

          {result?.code_artifact ? (
            <CodingArtifactPanel run={result.code_artifact} />
          ) : null}

          {result?.learning_native ? (
            <LearningNativeSurface
              state={result.learning_native}
              pending={turnMutation.isPending || resumeMutation.isPending}
              onSubmit={submitLearningNative}
            />
          ) : null}

          {loopDone ? (
            <section className={styles.learningNativeActions} aria-label="Learning-Native 完成">
              <div className={styles.phaseButton} data-testid="learning-loop-complete">
                <Check size={13} />
                学习闭环完成：承诺 → 解释 → 重构 → 迁移 → Solo 均已通过确定性验证。
              </div>
              {result?.learning_native?.cognitive_mirror ? (
                <CognitiveMirrorPanel mirror={result.learning_native.cognitive_mirror} />
              ) : null}
            </section>
          ) : result && (result.learning_native?.solo?.status ?? "inactive") !== "active" ? (
            <section className={styles.learningNativeActions} aria-label="Learning-Native 阶段切换">
              {nativeState?.phase === "awaiting_revision" && !nativeState.completed_stages.includes("teach_back") ? (
                <button
                  type="button"
                  className={styles.phaseButton}
                  onClick={() => submitLearningNative({ commitment: null, confidence: null, teach_back: null, transfer_attempt: null, solo_attempt: null, request_transfer: false, request_solo_exit: false, request_teach_back: true, request_transfer_task: false })}
                  disabled={turnMutation.isPending || resumeMutation.isPending}
                  aria-label="请求 Teach-Back 重构"
                  data-testid="request-teach-back-button"
                >
                  <PenLine size={13} />
                  进入 Teach-Back
                </button>
              ) : null}
              {nativeState?.phase === "transfer_required" ? (
                <button
                  type="button"
                  className={styles.phaseButton}
                  onClick={() => submitLearningNative({ commitment: null, confidence: null, teach_back: null, transfer_attempt: null, solo_attempt: null, request_transfer: false, request_solo_exit: false, request_teach_back: false, request_transfer_task: true })}
                  disabled={turnMutation.isPending || resumeMutation.isPending}
                  aria-label="请求迁移任务并进入 Solo Mode"
                  data-testid="request-transfer-button"
                >
                  <Target size={13} />
                  进入迁移 / Solo
                </button>
              ) : null}
            </section>
          ) : null}

          {!result && !interrupt ? (
            <section className={styles.emptyCanvas}>
              <ModeMark mode={mode} />
              <h2>{mode === "review_derivations" ? "上传手写推导，先确认转录，再定位首错。" : mode === "run_experiments" ? "先预测，再用数值不变量约束解释。" : mode === "work_on_projects" ? "提交当前里程碑的下一步。" : "从一个困惑或一张截图开始。"}</h2>
              {turnMutation.isPending && stageProgress ? (
                <div
                  className={styles.stageProgress}
                  data-testid="teaching-stage-progress"
                  role="status"
                  aria-live="polite"
                >
                  <LoaderCircle className={styles.spin} size={14} />
                  <div>
                    <strong>{STAGE_LABELS[stageProgress.step] ?? stageProgress.step}</strong>
                    <small>
                      {stageProgress.elapsed_seconds > 0
                        ? `已运行 ${stageProgress.elapsed_seconds.toFixed(1)}s`
                        : "教学流程已启动"}
                    </small>
                  </div>
                </div>
              ) : (
                <button type="button" className={styles.goldenLoopToggle} onClick={startGoldenTunnelingLoop}>
                  <FlaskConical size={15} />
                  启动黄金学习循环 · 量子隧穿
                </button>
              )}
            </section>
          ) : result ? (
            <article className={styles.tutorRecord} tabIndex={-1} data-testid="agent-tutor-result">
              <header><span><Atom /></span><div><small>QUANTUM AGENT · GROUNDED TURN</small><strong>{result.interpretation.relevant_concepts.join(" · ") || "课程辅导"}</strong></div><em>{result.release.release_level.replaceAll("_", " ")}</em></header>
              <div className={styles.orientation}><span>本轮方向</span><h2><MathText text={result.response.orientation} /></h2></div>
              <div className={styles.claims}>{result.response.claims.map((claim, index) => {
                const linkedEvidence = evidencePacket?.evidence.filter((evidence) => claim.evidence_ids.includes(evidence.evidence_id)) ?? [];
                const linkedResults = scientificResults.filter((tool) => claim.scientific_result_ids.includes(`${tool.kind}:${tool.inputs_sha256}`));
                const isOpen = expandedClaim === index;
                return (
                  <section key={`${claim.text}-${index}`} data-open={isOpen ? "true" : "false"}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <p><MathText text={claim.text} /></p>
                    <button
                      type="button"
                      className={styles.whyToggle}
                      onClick={() => setExpandedClaim(isOpen ? null : index)}
                      aria-expanded={isOpen}
                      aria-label={isOpen ? "收起依据" : "展开依据"}
                    >
                      {isOpen ? "收起" : "为什么？"}
                    </button>
                    {isOpen ? (
                      <div className={styles.claimBasis}>
                        <p className={styles.kicker}>SUPPORT BASIS · {claim.support_basis.replaceAll("_", " ")}</p>
                        {linkedResults.length ? (
                          <ul className={styles.basisList}>
                            {linkedResults.map((tool) => (
                              <li key={`${tool.kind}:${tool.inputs_sha256}`}>
                                <Check size={12} /> {tool.kind.replaceAll("_", " ")} · <span data-status={tool.status}>{tool.status}</span>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {linkedEvidence.length ? (
                          <ul className={styles.basisList}>
                            {linkedEvidence.map((evidence, evidenceIndex) => (
                              <li key={evidence.evidence_id}>
                                <BookOpen size={12} /> {evidence.document_title} · {sourceLocator(evidence)} · {evidence.chapter ?? "课程材料"}
                                <button type="button" className={styles.basisLink} onClick={() => setSelectedSource(evidence)} aria-label={`查看引文 ${evidenceIndex + 1}`}>查看原文</button>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        <button type="button" className={styles.basisLink} onClick={() => setRightOpen(true)}>在证据面板查看全部 →</button>
                      </div>
                    ) : (
                      <small>{claim.support_basis.replaceAll("_", " ")}</small>
                    )}
                  </section>
                );
              })}</div>
              <blockquote><Sparkles /><div><span>请你接着做</span><p><MathText text={result.response.next_question} /></p></div></blockquote>
            </article>
          ) : null}

          {scientificResults.length ? (
            <section className={styles.stageVerification} aria-label="科学验证结果">
              <p className={styles.kicker}>DETERMINISTIC VERIFICATION</p>
              {scientificResults.map((tool) => {
                const isBarrier = tool.kind === "rectangular_barrier_tunnelling";
                const metrics = tool.metrics ?? {};
                return (
                  <article className={styles.toolResult} key={`${tool.kind}:${tool.inputs_sha256}`} data-testid="scientific-tool-result" data-tool-kind={tool.kind}>
                    <strong>{tool.kind.replaceAll("_", " ")}</strong>
                    <span data-status={tool.status}>{tool.status}</span>
                    <p>{tool.observations[0] ?? "验证已运行"}</p>
                    {isBarrier && typeof metrics.T === "number" && typeof metrics.R === "number" ? (
                      <div data-testid="tunnelling-metrics" className={styles.tunnellingMetrics}>
                        <span>透射 T = <strong>{Number(metrics.T).toPrecision(6)}</strong></span>
                        <span>反射 R = <strong>{Number(metrics.R).toPrecision(6)}</strong></span>
                        <span>守恒 |R+T−1| = <strong>{Number(metrics.conservation_error ?? 0).toExponential(3)}</strong></span>
                        <span data-testid="tunnelling-regime">tunnelling</span>
                      </div>
                    ) : null}
                    <small>{tool.tool.name} {tool.tool.version}</small>
                  </article>
                );
              })}
            </section>
          ) : null}

          <section
            className={`${styles.composer} ${dragging ? styles.dragging : ""}`}
            data-disabled={interrupt ? "true" : "false"}
            onDragEnter={(event) => { event.preventDefault(); if (!interrupt) setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {dragging ? <div className={styles.dropNotice}><Upload /> 松开以上传到当前课程线程</div> : null}
            {uploads.length ? (
              <div className={styles.attachmentStrip}>
                {uploads.map((record) => (
                  <article
                    key={record.key}
                    data-state={record.state}
                    data-attachment-status={record.remote?.extraction?.status ?? record.state}
                    data-testid="agent-attachment"
                    aria-label={`${record.file.name}：${record.remote?.extraction?.status ?? record.state}`}
                  >
                    {record.previewUrl ? <Image src={record.previewUrl} alt="" width={34} height={34} unoptimized /> : <span>{record.file.type.includes("pdf") ? <FileText /> : <Braces />}</span>}
                    <div><strong>{record.remote?.filename ?? record.file.name}</strong><small>{record.state === "uploading" ? "安全校验与结构化提取…" : record.error ?? record.remote?.extraction?.status.replaceAll("_", " ") ?? "已就绪"}</small></div>
                    {record.state === "uploading" ? <LoaderCircle className={styles.spin} /> : <button onClick={() => removeUpload(record)} aria-label={`移除 ${record.file.name}`}><X /></button>}
                    {record.remote?.extraction?.status === "needs_confirmation" ? (
                      <div className={styles.confirmBar}><CircleAlert /><span>转录存在歧义；发送后会在同一线程逐字确认，不会自动采用候选。</span></div>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : null}
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onPaste={onPaste}
              placeholder={mode === "review_derivations" ? "描述你卡住的位置；也可以直接粘贴截图或上传手写推导…" : "写下问题、预测或当前里程碑…"}
              rows={2}
              maxLength={4_000}
              aria-label="给 Quantum Agent 的问题"
              disabled={Boolean(interrupt)}
            />
            {showAttempt && (mode === "review_derivations" || mode === "learn_concepts") ? <textarea className={styles.attemptInput} value={attempt} onChange={(event) => setAttempt(event.target.value)} placeholder="可选：粘贴当前尝试或 LaTeX 推导" rows={2} maxLength={12_000} aria-label="学生当前尝试" disabled={Boolean(interrupt)} /> : null}
            <footer>
              <div>
                <input ref={fileInputRef} type="file" hidden multiple disabled={Boolean(interrupt)} accept="image/png,image/jpeg,image/webp,application/pdf,.pptx,.docx,.txt,.md" onChange={(event) => addFiles([...(event.target.files ?? [])])} />
                <button onClick={() => fileInputRef.current?.click()} disabled={Boolean(interrupt)}><Paperclip /><span>图像 / 文档</span></button>
                <button onClick={() => fileInputRef.current?.click()} disabled={Boolean(interrupt)}><ImageIcon /><span>粘贴截图</span></button>
                {mode === "review_derivations" || mode === "learn_concepts" ? (
                  <button onClick={() => setShowAttempt((v) => !v)} disabled={Boolean(interrupt)} aria-pressed={showAttempt}><PenLine /><span>{showAttempt ? "收起尝试" : "附上尝试"}</span></button>
                ) : null}
                <small>PNG · JPG · PDF · 25 MiB</small>
              </div>
              <button
                className={styles.sendButton}
                onClick={submit}
                disabled={Boolean(interrupt) || turnMutation.isPending || resumeMutation.isPending || uploading || (!message.trim() && uploads.length === 0)}
              >
                {turnMutation.isPending || resumeMutation.isPending ? <LoaderCircle className={styles.spin} /> : <Send />}
                <span>{interrupt ? "先完成上方复核" : turnMutation.isPending ? "执行工作流" : "发送 / 运行"}</span>
              </button>
            </footer>
            {turnMutation.error ? <p className={styles.composerError}><CircleAlert /> {turnMutation.error.message}</p> : null}
          </section>
        </div>
      </main>

      <aside className={`${styles.rightPanel} ${rightOpen ? styles.panelOpen : ""}`}>
        <div className={styles.mobilePanelTitle}><strong>证据与验证</strong><button onClick={() => setRightOpen(false)}><X /></button></div>
        <header className={styles.evidenceHead}><div><p className={styles.kicker}>EVIDENCE DESK</p><h2>本轮依据</h2></div><span><i /> LIVE</span></header>
        {!loopDone && result?.learning_native?.cognitive_mirror ? (
          <CognitiveMirrorPanel mirror={result.learning_native.cognitive_mirror} />
        ) : null}
        {evidencePacket && diagnosis && release && validation && interpretation ? (
          <>
            <section className={styles.sideCard}>
              <div className={styles.cardTitle}><span><Network /></span><strong>课程关系</strong><em>{evidencePacket.graph_edges.length}</em></div>
              <div className={styles.conceptTags}>{evidencePacket.graph_nodes.slice(0, 8).map((node) => <span key={node.id}>{node.name}</span>)}</div>
              {evidencePacket.graph_edges.slice(0, 4).map((edge) => {
                const source = evidencePacket.graph_nodes.find((node) => node.id === edge.source_id)?.name;
                const target = evidencePacket.graph_nodes.find((node) => node.id === edge.target_id)?.name;
                return <p className={styles.relation} key={edge.id}>{source ?? "概念"}<small>{edge.relation_type}</small>{target ?? "概念"}</p>;
              })}
            </section>
            <section className={styles.sideCard}>
              <div className={styles.cardTitle}><span><BookOpen /></span><strong>课程引文</strong><em>{evidencePacket.evidence.length}</em></div>
              {answerWithheldByGate ? (
                <p className={styles.gatedEvidence} data-testid="evidence-gated-notice" role="status" aria-live="polite">
                  <Lock aria-hidden="true" /> 承诺门激活期间，答案级引文已脱敏；提交预测后释放完整内容。
                </p>
              ) : null}
              {evidencePacket.evidence.map((evidence, index) => (
                <button
                  className={styles.citation}
                  key={evidence.evidence_id}
                  onClick={() => setSelectedSource(evidence)}
                  data-testid="agent-citation"
                  aria-label={`引文 ${index + 1}：${evidence.document_title}${answerWithheldByGate ? "（已脱敏）" : ""}`}
                >
                  <span>E{String(index + 1).padStart(2, "0")}</span><div><strong>{evidence.document_title}</strong><small>{sourceLocator(evidence)} · {evidence.chapter ?? "课程材料"}</small><p>{evidence.evidence_snippet}</p></div><Link2 />
                </button>
              ))}
              {!evidencePacket.evidence.length ? <p className={styles.noEvidence}>未找到足够课程证据；系统不会补写来源。</p> : null}
            </section>
            <section className={styles.sideCard}>
              <div className={styles.cardTitle}><span><CircleAlert /></span><strong>诊断</strong><em>{Math.round((interpretation.confidence ?? 0) * 100)}%</em></div>
              <h3>{diagnosis.summary}</h3>
              {diagnosis.likely_misconception ? <p className={styles.misconception}>候选误解：{diagnosis.likely_misconception}</p> : null}
              <dl><div><dt>进展</dt><dd>{diagnosis.progress_state ?? diagnosis.status}</dd></div><div><dt>首错</dt><dd>{diagnosis.first_error?.kind ?? "尚未定位"}</dd></div></dl>
            </section>
            <section className={styles.policyCard}>
              <p className={styles.kicker}>POLICY GATE</p><h3>{interrupt ? "拟议回答正在等待复核" : `回答已限制为 ${release.release_level.replaceAll("_", " ")}`}</h3><p>{release.reason_code}</p><div><span>引用</span><strong>{validation.citation_ids_valid ? "通过" : "失败"}</strong></div><div><span>科学引用</span><strong>{validation.scientific_references_valid ? "通过" : "失败"}</strong></div>
            </section>
          </>
        ) : (
          <div className={styles.sideEmpty}><Network /><h3>证据会在这里聚合</h3><p>课程原文、页码、知识图谱关系、公式与验证器结果不会混入聊天气泡。</p></div>
        )}
      </aside>

      <Dialog.Root open={selectedSource !== null} onOpenChange={(open) => { if (!open) setSelectedSource(null); }}>
        {selectedSource ? <SourcePreview evidence={selectedSource} scope={scope} close={() => setSelectedSource(null)} /> : null}
      </Dialog.Root>

      <Dialog.Root open={cmdOpen} onOpenChange={(open) => { if (!open) { setCmdOpen(false); setCmdQuery(""); } }}>
        <Dialog.Portal>
          <Dialog.Overlay className={styles.cmdOverlay} />
          <Dialog.Content
            className={styles.cmdPalette}
            aria-label="命令面板"
            onOpenAutoFocus={(event) => { event.preventDefault(); const input = document.getElementById("qa-cmd-input") as HTMLInputElement | null; input?.focus(); }}
          >
            <header className={styles.cmdSearch}>
              <Search size={15} />
              <input
                id="qa-cmd-input"
                value={cmdQuery}
                onChange={(event) => setCmdQuery(event.target.value)}
                placeholder="搜索模式、课程或操作…"
                autoComplete="off"
                spellCheck={false}
              />
              <kbd>ESC</kbd>
            </header>
            <div className={styles.cmdList}>
              <div className={styles.cmdGroup}>
                <p className={styles.cmdGroupLabel}>学习模式</p>
                {MODES.filter((item) => item.label.includes(cmdQuery) || item.short.includes(cmdQuery) || !cmdQuery).map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      className={styles.cmdItem}
                      data-active={mode === item.id ? "true" : "false"}
                      onClick={() => {
                        setMode(item.id);
                        setConversationId(null);
                        setResult(null);
                        setInterrupt(null);
                        setConfirmedTranscription("");
                        setCmdOpen(false);
                        setCmdQuery("");
                      }}
                    >
                      <Icon size={15} />
                      <span><strong>{item.label}</strong><small>{item.short}</small></span>
                    </button>
                  );
                })}
              </div>
              <div className={styles.cmdGroup}>
                <p className={styles.cmdGroupLabel}>课程</p>
                {courses.filter((course) => course.course_title.includes(cmdQuery) || course.course_code.includes(cmdQuery) || !cmdQuery).slice(0, 6).map((course) => (
                  <button
                    key={`${course.course_id}:${course.curriculum_edition_id}`}
                    className={styles.cmdItem}
                    data-active={`${course.course_id}:${course.curriculum_edition_id}` === courseKey ? "true" : "false"}
                    onClick={() => {
                      setCourseKey(`${course.course_id}:${course.curriculum_edition_id}`);
                      setConversationId(null);
                      setResult(null);
                      setInterrupt(null);
                      setConfirmedTranscription("");
                      setCmdOpen(false);
                      setCmdQuery("");
                    }}
                  >
                    <BookOpen size={15} />
                    <span><strong>{course.course_title}</strong><small>{course.course_code} · {course.edition_title}</small></span>
                  </button>
                ))}
              </div>
              <div className={styles.cmdGroup}>
                <p className={styles.cmdGroupLabel}>操作</p>
                <button
                  className={styles.cmdItem}
                  onClick={() => { setRightOpen(true); setCmdOpen(false); setCmdQuery(""); }}
                >
                  <PanelRight size={15} />
                  <span><strong>打开证据面板</strong><small>课程引文 · 诊断 · 政策门</small></span>
                </button>
                <button
                  className={styles.cmdItem}
                  onClick={() => { startGoldenTunnelingLoop(); setCmdOpen(false); setCmdQuery(""); }}
                >
                  <FlaskConical size={15} />
                  <span><strong>启动黄金学习循环</strong><small>量子隧穿 · 真实模型与验证</small></span>
                </button>
                <button
                  className={styles.cmdItem}
                  onClick={() => { setConversationId(null); setResult(null); setInterrupt(null); setConfirmedTranscription(""); setCmdOpen(false); setCmdQuery(""); }}
                >
                  <Plus size={15} />
                  <span><strong>新建学习记录</strong><small>清空当前会话</small></span>
                </button>
              </div>
              {!MODES.some((item) => item.label.includes(cmdQuery) || item.short.includes(cmdQuery))
                && !courses.some((course) => course.course_title.includes(cmdQuery) || course.course_code.includes(cmdQuery))
                && cmdQuery ? (
                <p className={styles.cmdEmpty}>未匹配“{cmdQuery}”</p>
              ) : null}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
