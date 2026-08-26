"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Atom,
  BookOpen,
  Braces,
  Check,
  ChevronDown,
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
  parseTeachingApiError,
  parseTeachingTurnRequest,
  parseTeachingWorkflowOutcome,
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
import styles from "./agent.module.css";

const AgentCodeEditor = dynamic(() => import("./AgentCodeEditor"), {
  ssr: false,
  loading: () => <div className={styles.moduleLoading}>正在载入项目编辑器…</div>,
});
const AgentPlot = dynamic(() => import("./AgentPlot"), {
  ssr: false,
  loading: () => <div className={styles.moduleLoading}>正在载入科学绘图…</div>,
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

function terminalEvent(document: string): unknown {
  let terminal: unknown;
  let terminalCount = 0;
  let failure: string | null = null;
  for (const block of document.replace(/\r\n/g, "\n").split("\n\n")) {
    if (!block.trim()) continue;
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    const payload: unknown = JSON.parse(data.join("\n"));
    if (event === "workflow.completed" || event === "workflow.interrupted") {
      terminal = payload;
      terminalCount += 1;
    }
    if (event === "workflow.failed") {
      const code =
        typeof payload === "object" && payload !== null
          ? (payload as Record<string, unknown>).code
          : null;
      failure = typeof code === "string" ? code : "WORKFLOW_FAILED";
    }
  }
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

function EvidenceSpine({
  uploads,
  result,
  interrupt,
  pending,
}: {
  uploads: readonly UploadRecord[];
  result: TeachingTurnResult | null;
  interrupt: HitlInterruptResponse | null;
  pending: boolean;
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
    { label: "输入", done: uploads.length > 0 || Boolean(reviewed), detail: uploads.length ? `${uploads.length} 个附件` : "文本" },
    { label: "感知", done: perceptionReady, detail: uploads.length ? "结构化提取" : "无需调用" },
    { label: "证据", done: Boolean(reviewed), detail: reviewed ? reviewed.evidence_packet.coverage : "课程检索" },
    { label: "诊断", done: Boolean(reviewed), detail: reviewed ? reviewed.diagnosis.status : "首错定位" },
    { label: "验证", done: Boolean(reviewed), detail: reviewed?.scientific_results.length ? "工具证据" : "按需运行" },
    { label: "提示", done: Boolean(result), detail: interrupt ? "等待人工确认" : result?.release.release_level ?? "政策门控" },
  ];
  return (
    <ol className={styles.evidenceSpine} aria-label="本轮证据链">
      {stages.map((stage, index) => (
        <li key={stage.label} data-state={stage.done ? "done" : pending && index < 5 ? "active" : "idle"}>
          <span>{stage.done ? <Check size={12} /> : String(index + 1).padStart(2, "0")}</span>
          <div><strong>{stage.label}</strong><small>{stage.detail}</small></div>
        </li>
      ))}
    </ol>
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
  error,
}: {
  onReload: () => void;
  error: unknown;
}) {
  const [secret, setSecret] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function submitDemoLogin(event: FormEvent) {
    event.preventDefault();
    if (!secret.trim() || submitting) return;
    setSubmitting(true);
    setLoginError(null);
    try {
      const response = await fetch("/api/auth/demo-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret: secret.trim() }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        setLoginError(detail.error ?? "Demo 登录被拒绝。");
        return;
      }
      setSecret("");
      onReload();
    } catch {
      setLoginError("无法连接 demo 登录服务。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.bootError}>
      <Atom size={34} />
      <p className={styles.kicker}>QUANTUM AGENT / SESSION REQUIRED</p>
      <h1>无法进入课程工作台</h1>
      <p>{error instanceof Error ? error.message : "课程会话不可用。"}</p>
      <form onSubmit={submitDemoLogin} className={styles.demoLogin} aria-label="Demo 登录表单">
        <p className={styles.kicker}>COMPETITION DEMO LOGIN</p>
        <label htmlFor="demo-secret">Demo 密钥</label>
        <input
          id="demo-secret"
          type="password"
          autoComplete="off"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          maxLength={256}
          placeholder="输入竞赛组织者提供的 demo 密钥"
          aria-label="Demo 登录密钥"
        />
        <button type="submit" disabled={submitting || secret.trim().length < 8}>
          {submitting ? "正在登录…" : "使用 demo 密钥进入"}
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
  const [projectCode, setProjectCode] = useState("# 在这里放置当前里程碑的最小可运行代码\n");
  const [dragging, setDragging] = useState(false);
  const [rabiFrequency, setRabiFrequency] = useState(1);
  const [detuning, setDetuning] = useState(0);
  const [duration, setDuration] = useState(8);
  const [goldenTunnelling, setGoldenTunnelling] = useState(false);
  const [barrierEnergy, setBarrierEnergy] = useState(5);
  const [barrierHeight, setBarrierHeight] = useState(10);
  const [barrierWidth, setBarrierWidth] = useState(1e-10);
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
  useEffect(() => {
    if (conversationId) {
      try {
        window.localStorage.setItem("qa_conversation_id", conversationId);
      } catch {
        // localStorage may be unavailable (private mode); fail silently.
      }
    } else {
      try {
        window.localStorage.removeItem("qa_conversation_id");
      } catch {
        // ignore
      }
    }
  }, [conversationId]);
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
  const activeCourse =
    courses.find(
      (course) => `${course.course_id}:${course.curriculum_edition_id}` === courseKey,
    ) ?? courses[0] ?? null;
  const scope = activeCourse ? scopeFromCourse(activeCourse) : null;

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
      const response = await fetch(`/api/teaching/turns/stream?${query.toString()}`, {
        method: "POST",
        headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "教学工作流不可用。"));
      const parsed = parseTeachingWorkflowOutcome(terminalEvent(await response.text()));
      if (isHitlOutcome(parsed)) assertHitlScope(parsed, input.scope, input.mode);
      else assertTeachingScope(parsed, input.scope, input.mode);
      return parsed;
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
      setRightOpen(true);
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
      setRightOpen(true);
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
  const answerWithheldByGate = Boolean(
    result?.learning_native?.commitment?.gate_decision === "attempt_required"
    && !result.learning_native.commitment.accepted,
  );

  if (contextQuery.isPending) {
    return <main className={styles.boot}><Atom /><p>正在建立课程边界与证据索引…</p></main>;
  }
  if (contextQuery.isError || !contextQuery.data) {
    return <SessionRequiredView onReload={() => void contextQuery.refetch()} error={contextQuery.error} />;
  }
  if (!activeCourse || !scope) {
    return <main className={styles.bootError}><h1>尚无已发布课程</h1><p>请联系任课教师开通课程版本。</p></main>;
  }

  return (
    <div className={styles.agentShell} data-testid="agent-experience">
      <a className={styles.skipLink} href="#agent-main">跳到教学工作区</a>
      <header className={styles.topbar}>
        <button className={styles.mobileButton} onClick={() => setLeftOpen(true)} aria-label="打开课程导航"><Menu /></button>
        <div className={styles.brand}><span><Atom /></span><div><strong>Quantum Agent</strong><small>USTC · COURSE-BOUNDED LAB</small></div></div>
        <div className={styles.courseTitle}>
          <span>{activeCourse.course_code}</span><i />
          <strong>{activeCourse.course_title}</strong><i />
          <small>{activeCourse.edition_title}</small>
        </div>
        <div className={styles.topActions}>
          <span className={styles.liveState}><i /> {interrupt ? "工作流已暂停" : "课程证据在线"}</span>
          <button onClick={() => setRightOpen(true)} aria-label="打开证据面板"><PanelRight /></button>
          <span className={styles.userMark}>{contextQuery.data.display_name.slice(0, 1)}</span>
        </div>
      </header>

      {(leftOpen || rightOpen) ? <button className={styles.backdrop} onClick={() => { setLeftOpen(false); setRightOpen(false); }} aria-label="关闭面板" /> : null}
      <aside className={`${styles.leftPanel} ${leftOpen ? styles.panelOpen : ""}`}>
        <div className={styles.mobilePanelTitle}><strong>课程导航</strong><button onClick={() => setLeftOpen(false)}><X /></button></div>
        <label className={styles.coursePicker}>
          <span>{activeCourse.institution}</span>
          <select
            aria-label="选择课程版本"
            value={courseKey ?? ""}
            onChange={(event) => {
              setCourseKey(event.target.value);
              setConversationId(null);
              setResult(null);
              setInterrupt(null);
              setConfirmedTranscription("");
            }}
          >
            {courses.map((course) => (
              <option key={`${course.course_id}:${course.curriculum_edition_id}`} value={`${course.course_id}:${course.curriculum_edition_id}`}>
                {course.course_code} · {course.edition_title}
              </option>
            ))}
          </select>
          <ChevronDown aria-hidden="true" />
        </label>

        <p className={styles.navLabel}>学习模式</p>
        <nav className={styles.modeList} aria-label="教学模式">
          {MODES.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={mode === item.id ? styles.activeMode : ""}
                onClick={() => {
                  setMode(item.id);
                  setConversationId(null);
                  setResult(null);
                  setInterrupt(null);
                  setConfirmedTranscription("");
                  setLeftOpen(false);
                }}
              >
                <span><Icon /></span><div><strong>{item.label}</strong><small>{item.short}</small></div>
              </button>
            );
          })}
        </nav>

        <div className={styles.navLabelRow}><p className={styles.navLabel}>课程章节</p><button aria-label="知识图谱"><Network /></button></div>
        <nav className={styles.chapterList} aria-label="课程章节">
          {activeCourse.chapters.length ? activeCourse.chapters.map((chapter) => (
            <button key={chapter.id} onClick={() => setMessage(`我想复习“${chapter.title}”中的核心概念。`)}>
              <span>{String(chapter.ordinal).padStart(2, "0")}</span><strong>{chapter.title}</strong><small>{chapter.canonical_path}</small>
            </button>
          )) : <p className={styles.emptyChapters}>课程目录将在教师发布后出现。</p>}
        </nav>

        <div className={styles.sidebarProject}>
          <span>PROJECT MILESTONE</span>
          <strong>当前工作只解锁下一步</strong>
          <div><i /></div><small>不会一次生成可提交项目</small>
        </div>
        <button className={styles.newThread} onClick={() => { setConversationId(null); setResult(null); setInterrupt(null); setConfirmedTranscription(""); }}><Plus /> 新建学习记录</button>
      </aside>

      <main className={styles.mainPanel} id="agent-main">
        <div className={styles.workspaceScroll}>
          <section className={styles.workspaceHead}>
            <div><p className={styles.kicker}>{activeMode.label.toUpperCase()} / SPECIALIST WORKFLOW</p><h1>{activeMode.label}工作台</h1></div>
            <span><i /> {conversationId ? "线程已持续" : "新线程"}</span>
          </section>

          <EvidenceSpine
            uploads={uploads}
            result={result}
            interrupt={interrupt}
            pending={turnMutation.isPending || resumeMutation.isPending}
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

          {result?.learning_native ? (
            <LearningNativeSurface
              state={result.learning_native}
              pending={turnMutation.isPending || resumeMutation.isPending}
              onSubmit={submitLearningNative}
            />
          ) : null}

          {result && !answerWithheldByGate && !result.learning_native?.solo?.assistance_locked ? (
            <section className={styles.learningNativeActions} aria-label="Learning-Native 阶段切换">
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
            </section>
          ) : null}

          {!result && !interrupt ? (
            <section className={styles.emptyCanvas}>
              <ModeMark mode={mode} />
              <p className={styles.kicker}>START WITH EVIDENCE</p>
              <h2>{mode === "review_derivations" ? "上传手写推导，先确认转录，再定位首错。" : mode === "run_experiments" ? "上传结果图，并用数值不变量约束解释。" : mode === "work_on_projects" ? "提交当前里程碑，而不是索取完整项目。" : "从课程概念、截图或一段困惑开始。"}</h2>
              <p>系统只在需要时调用感知、证据、诊断与专业导师节点；答案范围始终由后端政策决定。</p>
              <button type="button" className={styles.goldenLoopToggle} onClick={startGoldenTunnelingLoop}>
                <FlaskConical size={13} />
                启动黄金学习循环 · 量子隧穿
              </button>
            </section>
          ) : result ? (
            <article className={styles.tutorRecord} tabIndex={-1} data-testid="agent-tutor-result">
              <header><span><Atom /></span><div><small>QUANTUM AGENT · GROUNDED TURN</small><strong>{result.interpretation.relevant_concepts.join(" · ") || "课程辅导"}</strong></div><em>{result.release.release_level.replaceAll("_", " ")}</em></header>
              <div className={styles.orientation}><span>本轮方向</span><h2>{result.response.orientation}</h2></div>
              <div className={styles.claims}>{result.response.claims.map((claim, index) => <section key={`${claim.text}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><p>{claim.text}</p><small>{claim.support_basis.replaceAll("_", " ")}</small></section>)}</div>
              <blockquote><Sparkles /><div><span>请你接着做</span><p>{result.response.next_question}</p></div></blockquote>
            </article>
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
              rows={3}
              maxLength={4_000}
              aria-label="给 Quantum Agent 的问题"
              disabled={Boolean(interrupt)}
            />
            {mode === "review_derivations" || mode === "learn_concepts" ? <textarea className={styles.attemptInput} value={attempt} onChange={(event) => setAttempt(event.target.value)} placeholder="可选：粘贴当前尝试或 LaTeX 推导" rows={2} maxLength={12_000} aria-label="学生当前尝试" disabled={Boolean(interrupt)} /> : null}
            <footer>
              <div>
                <input ref={fileInputRef} type="file" hidden multiple disabled={Boolean(interrupt)} accept="image/png,image/jpeg,image/webp,application/pdf,.pptx,.docx,.txt,.md" onChange={(event) => addFiles([...(event.target.files ?? [])])} />
                <button onClick={() => fileInputRef.current?.click()} disabled={Boolean(interrupt)}><Paperclip /><span>图像 / 文档</span></button>
                <button onClick={() => fileInputRef.current?.click()} disabled={Boolean(interrupt)}><ImageIcon /><span>粘贴截图</span></button>
                <small>PNG · JPG · WEBP · PDF · PPTX · DOCX · 25 MiB</small>
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
        {result?.learning_native?.cognitive_mirror ? (
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
            <section className={styles.sideCard}>
              <div className={styles.cardTitle}><span><Check /></span><strong>验证器</strong><em>{scientificResults.length}</em></div>
              {scientificResults.length ? scientificResults.map((tool) => {
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
                        <span data-testid="tunnelling-regime">{String(metrics.regime ?? "")}</span>
                      </div>
                    ) : null}
                    <small>{tool.tool.name} {tool.tool.version}</small>
                  </article>
                );
              }) : <p className={styles.noEvidence}>本轮没有需要运行的确定性工具。</p>}
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
    </div>
  );
}
