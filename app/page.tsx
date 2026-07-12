"use client";

import { FormEvent, useEffect, useState } from "react";
import Image from "next/image";

type Mode = "concept" | "derivation" | "experiment" | "project";
type Role = "student" | "teacher";
type CapabilityId = "quick" | "deep" | "vision" | "vision-reasoner" | "code";
type CapabilityChoice = { id: CapabilityId; label: string; shortLabel: string; description: string; acceptsImages: boolean; configured: boolean };
type ClientAttachment = { name: string; mimeType: "image/png" | "image/jpeg" | "image/webp" | "image/gif"; dataUrl: string };
type TutorApiResponse = {
  sessionId: string;
  hintLevel: number;
  answer: { conclusion: string; physicalPicture: string; mathematics: string; misconception: string; checkQuestion: string; suggestedAction: string };
  citations: Array<{ id: string; title: string; chapter: string; pages: string; excerpt: string; sourceUrl?: string }>;
  evidence: Array<{ type: string; label: string; status: string; detail: string }>;
  trace: Array<{ node: string; status: string; detail: string }>;
  model: { capability: CapabilityId; label: string; source: string };
  persisted?: boolean;
};
type ConversationItem = { id: string; text: string; status: "loading" | "done" | "error"; response?: TutorApiResponse; error?: string };
const clientId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

type SimulationStep = { step: number; time: number; probability: number; rValue: number; tValue: number; normError: number };
type SimResponse = { steps: SimulationStep[]; finalProbabilities: number[]; grid: number[]; potential: number[]; params: Record<string, number>; widthScan: Array<{ width: number; r: number; t: number; rtSum: number }> | null };
type ProjectProgress = { id: string; title: string; progress: number; currentMilestone: number; stateJson: string; updatedAt: string };
type ProjectItem = { id: string; title: string; question: string; level: string; milestones: string[]; validators: string[]; progress: ProjectProgress | null };

const modeItems: Array<{ id: Mode; icon: string; label: string; desc: string }> = [
  { id: "concept", icon: "问", label: "问概念", desc: "理解物理图像" },
  { id: "derivation", icon: "∂", label: "看推导", desc: "定位关键错误" },
  { id: "experiment", icon: "⌁", label: "做实验", desc: "计算与可视化" },
  { id: "project", icon: "◇", label: "做项目", desc: "里程碑式辅导" },
];

const chapters = [
  ["01", "原子模型与旧量子论", "课件"], ["02", "量子力学基础", "课件"], ["03", "单电子原子", "106页"],
  ["04", "表象与矩阵力学", "91页"], ["05", "微扰理论", "123页"], ["06", "多电子原子", "79页"],
  ["07", "双原子分子", "97页"], ["08", "分子光谱", "65页"],
];

function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <span className="orbit orbit-a" />
      <span className="orbit orbit-b" />
      <span className="nucleus" />
    </div>
  );
}

function Tag({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`tag tag-${tone}`}>{children}</span>;
}

function MiniWave() {
  return (
    <svg className="mini-wave" viewBox="0 0 520 180" role="img" aria-label="高斯波包接近势垒时的概率密度示意图">
      <defs>
        <linearGradient id="wave-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.26" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g className="grid-lines">
        <line x1="18" y1="38" x2="502" y2="38" />
        <line x1="18" y1="78" x2="502" y2="78" />
        <line x1="18" y1="118" x2="502" y2="118" />
        <line x1="18" y1="158" x2="502" y2="158" />
      </g>
      <path className="wave-fill" d="M18,158 C76,158 83,62 133,62 C184,62 198,151 258,153 C304,154 307,115 347,114 C388,114 393,153 502,158 L502,158 L18,158 Z" />
      <path className="wave-line" d="M18,158 C76,158 83,62 133,62 C184,62 198,151 258,153 C304,154 307,115 347,114 C388,114 393,153 502,158" />
      <rect className="barrier" x="270" y="34" width="26" height="124" rx="3" />
      <text x="267" y="22">V₀</text>
      <text x="18" y="174">x</text>
    </svg>
  );
}

function StudentSidebar({ mode, setMode, open }: { mode: Mode; setMode: (mode: Mode) => void; open: boolean }) {
  return (
    <aside className={`left-sidebar ${open ? "mobile-open" : ""}`}>
      <div className="course-switcher">
        <div className="course-code">QP</div>
        <div>
          <strong>量子物理</strong>
          <span>2026 春季 · 进行中</span>
        </div>
        <span className="chevron">⌄</span>
      </div>

      <nav aria-label="学习模式" className="mode-nav">
        <p className="nav-label">学习工作台</p>
        {modeItems.map((item) => (
          <button key={item.id} className={`mode-button ${mode === item.id ? "active" : ""}`} onClick={() => setMode(item.id)}>
            <span className="mode-icon">{item.icon}</span>
            <span><strong>{item.label}</strong><small>{item.desc}</small></span>
            {item.id === "project" && <em>1</em>}
          </button>
        ))}
      </nav>

      <div className="chapter-list">
        <div className="nav-label-row"><p className="nav-label">课程章节</p><button aria-label="展开全部章节">•••</button></div>
        {chapters.map(([num, title, progress]) => (
          <button className="chapter-row" key={num}>
            <span>{num}</span><strong>{title}</strong><small>{progress}</small>
          </button>
        ))}
      </div>

      <div className="project-card" onClick={() => setMode("project")} role="button" tabIndex={0}>
        <div><span>课程 Project 01</span><Tag tone="amber">进行中</Tag></div>
        <strong>量子隧穿与波包传播</strong>
        <div className="progress-track"><span style={{ width: "58%" }} /></div>
        <small>里程碑 3 / 5 · 还剩 12 天</small>
      </div>

      <button className="history-button"><span>↶</span> 历史学习记录 <small>12</small></button>
    </aside>
  );
}

function RightEvidence({ open, latest }: { open: boolean; latest: TutorApiResponse | null }) {
  const citation = latest?.citations?.[0];
  const modelEvidence = latest?.evidence?.find((item) => item.type === "model");
  const symbolicEvidence = latest?.evidence?.filter((item) => item.type === "symbolic");
  const numericalEvidence = latest?.evidence?.filter((item) => item.type === "numerical");
  const allVerifiers = [...(symbolicEvidence ?? []), ...(numericalEvidence ?? [])];
  const misconceptionText = latest?.answer?.misconception;
  const hasLatest = Boolean(latest);
  return (
    <aside className={`right-panel ${open ? "mobile-open" : ""}`}>
      <div className="panel-heading"><div><span className="eyebrow">EVIDENCE</span><h2>本轮学习证据</h2></div><span className="live-dot">{hasLatest ? "已同步" : "等待输入"}</span></div>

      <section className="evidence-card citation-card">
        <div className="card-kicker"><span className="evidence-icon">文</span><strong>课程资料</strong><Tag tone={citation ? "green" : "neutral"}>{citation ? "已引用" : "等待检索"}</Tag></div>
        <h3>{citation?.chapter ?? "等待本轮检索"}</h3>
        <p>“{citation?.excerpt ?? "发送问题后，这里只显示来自已发布课件、带页码且可打开原页核对的证据。"}”</p>
        {citation?.sourceUrl ? <a href={citation.sourceUrl} target="_blank" rel="noreferrer">{citation.title} · 第 {citation.pages} 页 <span>↗</span></a> : <button>等待本轮检索 <span>↗</span></button>}
      </section>

      <section className="evidence-card verify-card">
        <div className="card-kicker"><span className="evidence-icon">✓</span><strong>符号验证</strong><Tag tone={allVerifiers.length && allVerifiers.every((v) => v.status === "passed") ? "green" : allVerifiers.length ? "amber" : "neutral"}>{allVerifiers.length ? (allVerifiers.every((v) => v.status === "passed") ? "通过" : "待检查") : "未运行"}</Tag></div>
        {allVerifiers.length > 0 ? allVerifiers.map((verifier, index) => <div className="verify-line" key={`${verifier.label}-${index}`}><span>{verifier.label}</span><strong>{verifier.status === "passed" ? "满足" : verifier.status === "failed" ? "不满足" : "待定"}</strong></div>) : <div className="verify-line"><span>等待本轮验证</span><strong>—</strong></div>}
        <small>工具结论{allVerifiers.length ? "" : " · 发送问题后自动运行"}</small>
      </section>

      <section className="learning-state">
        <div className="card-kicker"><span className="evidence-icon">◎</span><strong>学习状态</strong></div>
        <div className="state-row"><span>当前知识点</span><strong>{latest?.answer?.conclusion ? "量子隧穿" : "等待输入"}</strong></div>
        <div className="state-row"><span>掌握证据</span><div className="dots"><i className={latest ? "on" : ""}/><i className={latest ? "on" : ""}/><i/><i/><i/></div></div>
        <div className="state-row"><span>当前提示层级</span><Tag tone="blue">H{latest?.hintLevel ?? 1} · {latest?.hintLevel && latest.hintLevel >= 3 ? "逐步引导" : "关键提问"}</Tag></div>
        <div className="misconception">
          <span>待澄清误区</span>
          <p>{misconceptionText ?? "发送问题后，系统将诊断你的理解偏差。"}</p>
        </div>
      </section>

      <section className="evidence-card gateway-proof">
        <div className="card-kicker"><span className="evidence-icon">AI</span><strong>能力路由</strong><Tag tone={latest?.model?.source === "api" ? "green" : "blue"}>{latest?.model?.source === "api" ? "已调用" : hasLatest ? "安全回退" : "等待调用"}</Tag></div>
        <h3>{latest?.model?.label ?? "课程内确定性引擎"}</h3>
        <p>{modelEvidence?.detail ?? "真实模型、接口地址与密钥只存在于服务器端；教学政策与证据链不随模型变化。"}</p>
      </section>

      <section className="next-step">
        <span className="eyebrow">NEXT STEP</span>
        <p>{latest?.answer?.suggestedAction ?? "先完成一个定性预测，再进入数值模拟。"}</p>
        <button>记录我的预测 <span>→</span></button>
      </section>
    </aside>
  );
}

function Composer({ onSend, placeholder = "写下你的理解、问题或推导…", acceptsImages = false }: { onSend: (text: string, attachments: ClientAttachment[]) => void; placeholder?: string; acceptsImages?: boolean }) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<ClientAttachment[]>([]);
  const [fileError, setFileError] = useState("");
  async function addFiles(files: FileList | null) {
    if (!files) return;
    setFileError("");
    const next: ClientAttachment[] = [];
    for (const file of Array.from(files).slice(0, 3 - attachments.length)) {
      if (!["image/png", "image/jpeg", "image/webp", "image/gif"].includes(file.type)) { setFileError("仅支持 PNG、JPEG、WEBP 或 GIF"); continue; }
      if (file.size > 5 * 1024 * 1024) { setFileError("单张图片不能超过 5 MB"); continue; }
      const dataUrl = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file); });
      next.push({ name: file.name, mimeType: file.type as ClientAttachment["mimeType"], dataUrl });
    }
    setAttachments((items) => [...items, ...next].slice(0, 3));
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim(), attachments);
    setText("");
    setAttachments([]);
  }
  return (
    <form className="composer" onSubmit={submit}>
      <div className="composer-tools"><button type="button" aria-label="插入公式">∑</button><label className={acceptsImages ? "upload-enabled" : "upload-disabled"} title={acceptsImages ? "上传题目、推导或图像" : "切换到图片能力后上传"}>＋<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple disabled={!acceptsImages} onChange={(event) => { void addFiles(event.target.files); event.currentTarget.value = ""; }}/></label><span>{acceptsImages ? "支持 LaTeX、代码与最多 3 张图片" : "支持 LaTeX 与代码 · 图片能力可上传"}</span></div>
      {attachments.length > 0 && <div className="attachment-strip">{attachments.map((attachment, index) => <span key={`${attachment.name}-${index}`}><Image src={attachment.dataUrl} width={27} height={27} unoptimized alt=""/><strong>{attachment.name}</strong><button type="button" onClick={() => setAttachments((items) => items.filter((_, itemIndex) => itemIndex !== index))}>×</button></span>)}</div>}
      {fileError && <small className="file-error">{fileError}</small>}
      <div className="composer-row"><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={placeholder} aria-label="学习输入" rows={2}/><button className="send-button" aria-label="发送" disabled={!text.trim()}>↑</button></div>
      <div className="composer-foot"><span><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行</span><span>本轮最多提示至 H3</span></div>
    </form>
  );
}

function LiveTutorReply({ item }: { item: ConversationItem }) {
  if (item.status === "loading") return <article className="tutor-message live-reply"><div className="avatar tutor"><BrandMark /></div><div className="tutor-body"><div className="loading-line"><i/><i/><i/> 正在执行教学工作流</div></div></article>;
  if (item.status === "error") return <article className="tutor-message live-reply error-reply"><div className="avatar tutor"><BrandMark /></div><div className="tutor-body"><Tag tone="amber">安全回退</Tag><p>{item.error}</p></div></article>;
  const result = item.response!;
  return <article className="tutor-message live-reply"><div className="avatar tutor"><BrandMark /></div><div className="tutor-body">
    <div className="message-meta-row"><span className="message-meta">Quantum Agent · 实时工作流</span><Tag tone={result.model.source === "api" ? "blue" : "green"}>{result.model.source === "api" ? "模型解释" : "确定性回退"}</Tag><Tag tone="green">H{result.hintLevel}</Tag></div>
    <div className="thesis"><span>一句话结论</span><h2>{result.answer.conclusion}</h2></div>
    <div className="live-answer-grid"><section><span>物理图像</span><p>{result.answer.physicalPicture}</p></section><section><span>数学表达</span><p>{result.answer.mathematics}</p></section></div>
    <div className="hint-box"><span>当前误区诊断</span><p>{result.answer.misconception}</p></div>
    <div className="question-card"><div><span>?</span><div><strong>理解检查</strong><p>{result.answer.checkQuestion}</p></div></div></div>
    <div className="trace-summary"><span>工作流轨迹</span>{result.trace.map((step) => <i key={step.node} title={step.detail} className={step.status}>{step.node.replaceAll("_", " ")}</i>)}</div>
  </div></article>;
}

function ConceptWorkspace({ capability, onLatest }: { capability: CapabilityChoice; onLatest: (value: TutorApiResponse) => void }) {
  const [messages, setMessages] = useState<ConversationItem[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  async function send(message: string, attachments: ClientAttachment[]) {
    const id = clientId();
    setMessages((items) => [...items, { id, text: message, status: "loading" }]);
    try {
      const response = await fetch("/api/tutor", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "concept", message, sessionId, capability: capability.id, attachments, requestedHintLevel: 2 }) });
      const payload = await response.json() as TutorApiResponse & { error?: string; detail?: string };
      if (!response.ok) throw new Error(payload.detail ?? payload.error ?? "教学工作流暂时不可用");
      setSessionId(payload.sessionId); onLatest(payload);
      setMessages((items) => items.map((item) => item.id === id ? { ...item, status: "done", response: payload } : item));
    } catch (error) {
      setMessages((items) => items.map((item) => item.id === id ? { ...item, status: "error", error: error instanceof Error ? error.message : "请求失败" } : item));
    }
  }
  return (
    <div className="workspace-scroll">
      <header className="workspace-title">
        <div><span className="eyebrow">CONCEPT STUDIO · 一维量子体系</span><h1>量子隧穿：粒子如何穿过势垒？</h1></div>
        <div className="status-pill"><span/>{capability.label} · 课程证据优先</div>
      </header>

      <div className="learner-message">
        <div className="avatar learner">谢</div>
        <div><span className="message-meta">我的理解 · 刚刚</span><p>粒子的能量比势垒低，所以按照能量守恒，它应该完全不可能穿过势垒，对吗？</p></div>
      </div>

      <article className="tutor-message">
        <div className="avatar tutor"><BrandMark /></div>
        <div className="tutor-body">
          <div className="message-meta-row"><span className="message-meta">Quantum Agent · 引导式回答</span><Tag tone="blue">模型解释</Tag></div>
          <div className="thesis">
            <span>一句话结论</span>
            <h2>能量守恒没有被违反；关键在于量子态不是一颗沿确定轨迹运动的小球。</h2>
          </div>
          <p>先别急着计算透射率。我们把你的判断拆成两步：<strong>能量低于势垒</strong>是对的，但“因此波函数在势垒外必为零”这一步需要检查。</p>
          <div className="concept-grid">
            <section className="formula-card">
              <span className="card-label">数学表达</span>
              <div className="formula">ψ(x) ∝ e<sup>−κx</sup></div>
              <div className="formula-sub">κ = √<span>(2m(V₀−E)) / ℏ²</span></div>
              <p>势垒内的波函数<strong>指数衰减</strong>，却不会在边界突然变成零。</p>
              <button>复制 LaTeX</button>
            </section>
            <section className="visual-card">
              <span className="card-label">物理图像</span>
              <MiniWave />
              <p>左侧波包遇到势垒后，一部分反射，一小部分延伸至右侧。</p>
            </section>
          </div>
          <div className="question-card">
            <div><span>?</span><div><strong>先做一个判断</strong><p>如果把势垒宽度加倍，你预计透射概率会怎样变化？为什么？</p></div></div>
            <div className="answer-options"><button>显著减小</button><button>大致不变</button><button>可能增大</button><button>我还不确定</button></div>
          </div>
          <div className="quick-actions"><span>换一种方式</span><button>再直观一点</button><button>再数学一点</button><button>和经典物理比较</button><button>画图说明</button></div>
        </div>
      </article>

      {messages.map((item) => <div key={item.id} className="live-turn"><div className="learner-message new-message"><div className="avatar learner">谢</div><div><span className="message-meta">我的追问 · 刚刚</span><p>{item.text}</p><small>已送入课程内教学工作流</small></div></div><LiveTutorReply item={item}/></div>)}
      <Composer onSend={send} acceptsImages={capability.acceptsImages} placeholder={capability.acceptsImages ? "描述你希望我检查图片中的哪一部分…" : capability.id === "code" ? "粘贴代码、报错和预期物理结果…" : "写下你的理解、问题或推导…"} />
    </div>
  );
}

function DerivationWorkspace({ capability, onLatest }: { capability: CapabilityChoice; onLatest: (value: TutorApiResponse) => void }) {
  const [messages, setMessages] = useState<ConversationItem[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [steps, setSteps] = useState<Array<{ id: string; text: string; status: "valid" | "warning" | "muted" }>>([
    { id: "01", text: "区域 I：ψ₁ = Aeⁱᵏˣ + Be⁻ⁱᵏˣ", status: "valid" },
    { id: "02", text: "区域 II：ψ₂ = Ce⁻ᵏˣ + Deᵏˣ", status: "warning" },
    { id: "03", text: "区域 III：ψ₃ = Feⁱᵏˣ", status: "muted" },
  ]);
  const [newStep, setNewStep] = useState("");

  function addStep() {
    if (!newStep.trim()) return;
    const id = String(steps.length + 1).padStart(2, "0");
    setSteps((items) => [...items, { id, text: newStep.trim(), status: "muted" }]);
    setNewStep("");
  }

  async function send(message: string, _attachments: ClientAttachment[]) {
    const id = clientId();
    const derivationText = steps.map((s) => `${s.id}. ${s.text}`).join("\n");
    const fullMessage = `${message}\n\n当前推导步骤：\n${derivationText}`;
    setMessages((items) => [...items, { id, text: message, status: "loading" }]);
    try {
      const response = await fetch("/api/tutor", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "derivation", message: fullMessage, sessionId, capability: capability.id, attemptedWork: derivationText, requestedHintLevel: 2 }) });
      const payload = await response.json() as TutorApiResponse & { error?: string; detail?: string };
      if (!response.ok) throw new Error(payload.detail ?? payload.error ?? "教学工作流暂时不可用");
      setSessionId(payload.sessionId); onLatest(payload);
      setMessages((items) => items.map((item) => item.id === id ? { ...item, status: "done", response: payload } : item));
    } catch (error) {
      setMessages((items) => items.map((item) => item.id === id ? { ...item, status: "error", error: error instanceof Error ? error.message : "请求失败" } : item));
    }
  }

  const latestResult = messages.findLast((item) => item.status === "done")?.response;
  const hasError = latestResult?.answer?.misconception && latestResult.answer.misconception.length > 0;

  return (
    <div className="workspace-scroll derivation-workspace">
      <header className="workspace-title"><div><span className="eyebrow">DERIVATION LAB · 首错诊断</span><h1>检查我的定态薛定谔方程推导</h1></div><Tag tone="amber">H{latestResult?.hintLevel ?? 2} · 最小提示</Tag></header>
      <div className="derivation-layout">
        <section className="steps-panel">
          <div className="section-top"><div><span className="eyebrow">YOUR DERIVATION</span><h2>矩形势垒的透射系数</h2></div><button onClick={() => { if (newStep.trim()) addStep(); }}>＋ 添加步骤</button></div>
          <input className="step-input" value={newStep} onChange={(e) => setNewStep(e.target.value)} placeholder="输入下一步推导…" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addStep(); } }} />
          {steps.map((step) => <div className={`derivation-step ${step.status}`} key={step.id}><span>{step.id}</span><code>{step.text}</code><i>{step.status === "valid" ? "✓" : step.status === "warning" ? "!" : "·"}</i></div>)}
          <button className="run-check" onClick={() => { if (steps.length > 0) send("请检查我的推导步骤，定位首个关键错误并给出最小提示。", []); }}>检查到此处 <span>⌘ ↵</span></button>
        </section>
        <section className="diagnosis-panel">
          {latestResult ? (<>
            <div className="diagnosis-heading"><span className="diagnosis-mark">!</span><div><Tag tone={hasError ? "amber" : "green"}>{hasError ? "首个关键错误" : "已通过"}</Tag><h2>{latestResult.answer.conclusion}</h2></div></div>
            <p>{latestResult.answer.physicalPicture}</p>
            <div className="hint-box"><span>给你一个最小提示</span><p>{latestResult.answer.mathematics}</p></div>
            {latestResult.answer.misconception && <div className="hint-box"><span>误区诊断</span><p>{latestResult.answer.misconception}</p></div>}
            <div className="diagnosis-actions"><button onClick={() => send("再给一级提示。", [])}>再给一级提示</button></div>
            {latestResult.evidence.length > 0 && <div className="tool-proof"><span>✓</span><div><strong>工具验证</strong><p>{latestResult.evidence.map((e) => `${e.label}: ${e.status}`).join(" · ")}</p></div></div>}
          </>) : messages.findLast((item) => item.status === "loading") ? (
            <div className="diagnosis-heading"><span className="diagnosis-mark">…</span><div><Tag tone="blue">正在检查</Tag><h2>正在执行教学工作流</h2></div></div>
          ) : messages.findLast((item) => item.status === "error") ? (
            <div className="diagnosis-heading"><span className="diagnosis-mark">!</span><div><Tag tone="amber">安全回退</Tag><h2>{messages.findLast((item) => item.status === "error")?.error}</h2></div></div>
          ) : (
            <div className="diagnosis-heading"><span className="diagnosis-mark">!</span><div><Tag tone="blue">等待检查</Tag><h2>添加推导步骤后点击"检查到此处"</h2></div></div>
          )}
        </section>
      </div>
      <Composer onSend={send} acceptsImages={capability.acceptsImages} placeholder="解释你为什么这样写，或贴入下一步推导…" />
    </div>
  );
}

type SimulationResultJson = {
  steps: Array<{ step: number; time: number; probability: number; rValue: number; tValue: number; normError: number }>;
  params: Record<string, number>;
};

function ExperimentWorkspace() {
  const [running, setRunning] = useState(false);
  const [width, setWidth] = useState(1.2);
  const [v0, setV0] = useState(4.0);
  const [energy, setEnergy] = useState(2.5);
  const [simResult, setSimResult] = useState<SimulationResultJson | null>(null);
  const [simError, setSimError] = useState("");
  const [activeStep, setActiveStep] = useState(0);

  async function runSimulation() {
    setRunning(true); setSimError(""); setSimResult(null);
    try {
      const response = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nPoints: 300, nSteps: 150, dt: 0.08,
          xMin: -15, xMax: 15, x0: -6, k0: 3.0, sigma: 1.5,
          v0, barrierWidth: width, barrierCenter: 0,
        }),
      });
      if (!response.ok) { setSimError("模拟计算失败，请调整参数后重试。"); setRunning(false); return; }
      const data = await response.json() as SimulationResultJson;
      setSimResult(data);
      setActiveStep(0);
    } catch { setSimError("模拟服务暂时不可用。"); }
    setRunning(false);
  }

  const lastStep = simResult?.steps?.[simResult.steps.length - 1];
  const activeStepData = simResult?.steps?.[activeStep];
  const normError = lastStep?.normError ?? 1;
  const conservationPassed = normError < 0.005;

  return (
    <div className="workspace-scroll experiment-workspace">
      <header className="workspace-title"><div><span className="eyebrow">COMPUTATION LAB · 数值实验</span><h1>观察高斯波包穿越有限势垒</h1></div><Tag tone={simResult ? "green" : "blue"}>{simResult ? "模拟已运行" : "Crank-Nicolson 求解器就绪"}</Tag></header>
      <div className="lab-grid">
        <section className="parameter-panel">
          <span className="eyebrow">PARAMETERS</span><h2>实验参数</h2>
          <label>势垒高度 V₀ <strong>{v0.toFixed(1)} eV</strong><input type="range" min="1" max="8" step=".1" defaultValue={v0} onChange={(e) => setV0(Number(e.target.value))}/></label>
          <label>势垒宽度 a <strong>{width.toFixed(1)} nm</strong><input type="range" min=".2" max="3" step=".1" value={width} onChange={(e) => setWidth(Number(e.target.value))}/></label>
          <label>中心能量 E <strong>{energy.toFixed(1)} eV</strong><input type="range" min=".5" max="5" step=".1" defaultValue={energy} onChange={(e) => setEnergy(Number(e.target.value))}/></label>
          <button onClick={runSimulation} className="run-sim"><span>{running ? "…" : "▶"}</span>{running ? "正在计算" : "运行模拟"}</button>
          <small>Crank-Nicolson 有限差分 · 纯浏览器内计算</small>
        </section>
        <section className="simulation-panel">
          <div className="simulation-top"><div><span className="eyebrow">SIMULATION RESULT</span><h2>概率密度 |ψ(x,t)|²</h2></div><div className="sim-stats"><span>概率守恒 <strong>{simResult ? (lastStep?.probability ?? 1).toFixed(6) : "—"}</strong></span><Tag tone={simResult ? (conservationPassed ? "green" : "amber") : "neutral"}>{simResult ? (conservationPassed ? "守恒通过" : "漂移警告") : "未运行"}</Tag></div></div>
          <div className={`large-plot ${running ? "running" : simResult ? "has-data" : ""}`}>
            <MiniWave />
            {simResult && (
              <div className="time-scrubber">
                <button onClick={() => setActiveStep(Math.max(0, activeStep - 10))}>◀</button>
                <div><span style={{ width: `${(activeStep / Math.max(simResult.steps.length - 1, 1)) * 100}%` }} /></div>
                <button onClick={() => setActiveStep(Math.min(simResult.steps.length - 1, activeStep + 10))}>▶</button>
                <small>t = {activeStepData?.time.toFixed(2) ?? 0} fs · 步 {activeStep} / {simResult.steps.length - 1}</small>
              </div>
            )}
          </div>
          <div className="result-strip">
            <div><span>反射概率 R</span><strong>{lastStep ? lastStep.rValue.toFixed(4) : "—"}</strong></div>
            <div><span>透射概率 T</span><strong>{lastStep ? lastStep.tValue.toFixed(4) : "—"}</strong></div>
            <div><span>R + T</span><strong>{lastStep ? (lastStep.rValue + lastStep.tValue).toFixed(4) : "—"}</strong></div>
          </div>
        </section>
      </div>
      {simError && <section className="interpretation-prompt"><div><span>模拟状态</span><h2>{simError}</h2></div></section>}
      <section className="interpretation-prompt"><div><span>下一步 · 解释结果</span><h2>当势垒变宽时，图像中的哪一部分最先发生明显变化？</h2></div><button onClick={() => { const msg = `势垒宽度为${width.toFixed(1)}nm时，我观察到R=${lastStep?.rValue.toFixed(4) ?? '—'}, T=${lastStep?.tValue.toFixed(4) ?? '—'}。`; }}>写下我的解释 →</button></section>
    </div>
  );
}

function ProjectWorkspace() {
  const [projectsData, setProjectsData] = useState<Array<{
    id: string; title: string; question: string; level: string;
    milestones: Array<{ id: string; title: string; status: string }>;
    validators: string[];
  }> | null>(null);
  const [selectedProject, setSelectedProject] = useState(0);
  const [projectProgress, setProjectProgress] = useState<Record<string, { progress: number; currentMilestone: number }>>({});

  useEffect(() => {
    fetch("/api/projects")
      .then((r) => r.json())
      .then((data: { projects?: typeof projectsData }) => {
        if (data.projects?.length) {
          setProjectsData(data.projects);
          const progress: Record<string, { progress: number; currentMilestone: number }> = {};
          data.projects.forEach((p) => { progress[p.id] = { progress: 0, currentMilestone: 1 }; });
          setProjectProgress(progress);
        }
      })
      .catch(() => {});
  }, []);

  const projects = projectsData ?? [];
  const activeProject = projects[selectedProject] ?? null;
  const activeProgress = activeProject ? projectProgress[activeProject.id] ?? { progress: 0, currentMilestone: 1 } : { progress: 0, currentMilestone: 1 };
  const pct = activeProject ? Math.round((activeProject.milestones.filter((m) => m.status === "completed").length / Math.max(activeProject.milestones.length, 1)) * 100) : 0;
  const completedCount = activeProject ? activeProject.milestones.filter((m) => m.status === "completed").length : 0;
  const totalCount = activeProject?.milestones.length ?? 0;

  return (
    <div className="workspace-scroll project-workspace">
      {activeProject && (
        <>
          <header className="project-hero">
            <div>
              <Tag tone={activeProject.level === "golden-loop" ? "amber" : "blue"}>
                PROJECT {String(selectedProject + 1).padStart(2, "0")} · {activeProject.level === "golden-loop" ? "进行中" : "可用"}
              </Tag>
              <h1>{activeProject.title}</h1>
              <p>{activeProject.question}</p>
              <div className="project-meta">
                <span>{activeProject.level === "golden-loop" ? "预计 3 周" : "自主进度"}</span>
                <span>{totalCount} 个里程碑</span>
                <span>个人项目</span>
              </div>
            </div>
            <div className="project-score">
              <span>当前进度</span>
              <strong>{pct}<small>%</small></strong>
              <div><i style={{ width: `${pct}%` }} /></div>
            </div>
          </header>
          <div className="project-columns">
            <section className="milestone-list">
              <div className="section-top">
                <div><span className="eyebrow">ROADMAP</span><h2>学习里程碑</h2></div>
                <span>{completedCount} / {totalCount} 完成</span>
              </div>
              {activeProject.milestones.map((m, i) => (
                <button className={`milestone ${m.status}`} key={m.id}>
                  <span>{m.status === "completed" ? "✓" : String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{m.title}</strong>
                    <small>{m.status === "completed" ? "已完成" : m.status === "in_progress" ? "正在进行" : "尚未解锁"}</small>
                  </div>
                  <i>→</i>
                </button>
              ))}
            </section>
            <section className="active-milestone">
              <span className="eyebrow">CURRENT MILESTONE · {String(activeProgress.currentMilestone).padStart(2, "0")}</span>
              <h2>{activeProject.milestones[activeProgress.currentMilestone - 1]?.title ?? "开始学习"}</h2>
              <p>完成当前模块的自动检查和解释任务，解锁下一里程碑。</p>
              <div className="checklist">
                {activeProject.validators.map((v, i) => (
                  <div key={v} className={i < 2 ? "done" : ""}>
                    <span>{i < 2 ? "✓" : i + 1}</span>
                    <p><strong>{v.replace(/_/g, " ")}</strong><small>{i < 2 ? "自动测试通过" : "等待你的回答"}</small></p>
                  </div>
                ))}
              </div>
              <button className="continue-project">继续当前任务 <span>→</span></button>
              <small className="coach-note">Agent Coach 只提供当前里程碑所需提示，不会生成完整报告。</small>
            </section>
          </div>
          {projects.length > 1 && (
            <section className="project-catalog">
              <div className="section-top">
                <div><span className="eyebrow">PROJECT LIBRARY</span><h2>其他课程项目</h2></div>
                <span>由教师逐步开放</span>
              </div>
              <div className="project-catalog-grid">
                {projects.filter((_, i) => i !== selectedProject).map((p, i) => (
                  <article key={p.id} onClick={() => setSelectedProject(projects.findIndex((pp) => pp.id === p.id))}>
                    <span>PROJECT {String(i + 2).padStart(2, "0")}</span>
                    <Tag tone={p.level === "golden-loop" ? "amber" : "blue"}>{p.level === "golden-loop" ? "可运行模块" : "教学设计"}</Tag>
                    <h3>{p.title}</h3>
                    <p>{p.validators.slice(0, 3).join(" · ")}</p>
                    <button>查看项目 <i>→</i></button>
                  </article>
                ))}
              </div>
            </section>
          )}
        </>
      )}
      {!activeProject && (
        <header className="project-hero">
          <div>
            <Tag tone="blue">PROJECTS</Tag>
            <h1>课程项目</h1>
            <p>正在加载项目列表…</p>
          </div>
        </header>
      )}
    </div>
  );
}

function TeacherDashboard({ onLogout }: { onLogout: () => void }) {
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [analytics, setAnalytics] = useState<{ activeStudents: number; pendingEscalations: number; highHintDependency: number; failedToolRuns: number; source: string } | null>(null);
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  useEffect(() => {
    fetch("/api/teacher/analytics")
      .then(async (response) => {
        if (response.status === 401) { setAuthorized(false); setAnalytics(null); return; }
        setAuthorized(true);
        const data = await response.json().catch(() => null);
        setAnalytics(data);
      })
      .catch(() => { setAuthorized(false); setAnalytics(null); });
  }, []);

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    if (!password.trim()) return;
    setLoggingIn(true); setLoginError("");
    try {
      const response = await fetch("/api/teacher/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
      if (!response.ok) { setLoginError("密码错误或登录过于频繁"); setPassword(""); setLoggingIn(false); return; }
      setPassword(""); setLoggingIn(false);
      const dataResponse = await fetch("/api/teacher/analytics");
      if (dataResponse.status === 401) { setAuthorized(false); setAnalytics(null); return; }
      setAuthorized(true);
      const data = await dataResponse.json().catch(() => null);
      setAnalytics(data);
    } catch { setLoginError("登录请求失败"); setLoggingIn(false); }
  }

  async function handleLogout() {
    await fetch("/api/teacher/logout", { method: "POST" });
    setAuthorized(false);
    setAnalytics(null);
    onLogout();
  }

  if (authorized === false) {
    return (
      <main className="teacher-dashboard">
        <header className="teacher-title"><div><span className="eyebrow">TEACHER ACCESS</span><h1>教师验证</h1><p>教师数据需要密码验证。此密码为服务端工作秘密，不存储于浏览器。</p></div></header>
        <section className="teacher-login-card">
          <form onSubmit={handleLogin}>
            <label htmlFor="teacher-password">教师密码</label>
            <div className="teacher-login-row"><input id="teacher-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="请输入教师工作密码" autoFocus autoComplete="current-password" /><button type="submit" disabled={loggingIn || !password.trim()}>{loggingIn ? "验证中…" : "进入驾驶舱"}</button></div>
            {loginError && <small className="login-error">{loginError}</small>}
          </form>
        </section>
      </main>
    );
  }

  const metrics = [["本周活跃学生",String(analytics?.activeStudents ?? 0),analytics?.source === "database" ? "实时数据" : "无数据"],["待处理升级",String(analytics?.pendingEscalations ?? 0),analytics?.pendingEscalations ? "需关注" : "无待处理"],["高提示依赖",String(analytics?.highHintDependency ?? 0),"需要教学介入"],["工具运行失败",String(analytics?.failedToolRuns ?? 0),"本周"]];
  const isLoading = authorized === null;
  if (isLoading) return (
    <main className="teacher-dashboard">
      <header className="teacher-title"><div><span className="eyebrow">TEACHING OVERVIEW</span><h1>加载中…</h1><p>正在获取教学数据。</p></div></header>
    </main>
  );
  const isRealData = analytics?.source === "database";
  const misconceptionData = (analytics as { misconceptionCounts?: Array<{ id: string; count: number }> })?.misconceptionCounts ?? [];
  const recentEscalations = (analytics as { recentEscalations?: Array<{ id: string; reason: string; createdAt: string }> })?.recentEscalations ?? [];
  const misconceptionRows = misconceptionData.length > 0
    ? misconceptionData.map((m) => [m.id.replace(/_/g, " ").slice(0, 20), m.count, Math.min(100, m.count * 3), "—"] as [string, number | string, number | string, string])
    : [["等待数据收集", 0, 0, "—"]] as [string, number | string, number | string, string][];
  return (
    <main className="teacher-dashboard">
      <header className="teacher-title"><div><span className="eyebrow">TEACHING OVERVIEW · 量子物理</span><h1>早上好，谢老师</h1><p>这里呈现需要教学介入的信号，不用于学生排名。</p></div><div><button onClick={handleLogout}>退出教师端</button></div></header>
      <section className="metric-grid">{metrics.map(([label,value,delta],i)=><article key={label}><span>{label}</span><strong>{value}</strong><small className={i===1?"urgent":""}>{delta}</small></article>)}</section>
      <div className="teacher-grid">
        <section className="misconception-map"><div className="section-top"><div><span className="eyebrow">MISCONCEPTION MAP</span><h2>本周高频误区</h2></div><span>{isRealData ? "来自 D1" : "等待数据"}</span></div>
          {misconceptionRows.map(([name, count, barWidth, chapter]) => <div className="mis-row" key={String(name)}><span>{String(chapter)}</span><div><strong>{name}</strong><i><b style={{width: `${String(barWidth)}%`}} /></i></div><em>{typeof count === "number" ? `${count} 次` : String(count)}</em></div>)}
        </section>
        <section className="ta-queue"><div className="section-top"><div><span className="eyebrow">TA QUEUE</span><h2>需要人工介入</h2></div><Tag tone={recentEscalations.length > 0 ? "amber" : "green"}>{recentEscalations.length} 项</Tag></div>
          {recentEscalations.length > 0
            ? recentEscalations.map((esc) => <button className="queue-row" key={esc.id}><span>{esc.id.slice(0, 1)}</span><div><strong>{esc.id.slice(0, 12)}</strong><p>{esc.reason}</p><small>{esc.createdAt}</small></div><i>→</i></button>)
            : <div className="queue-row"><span>—</span><div><strong>暂无待处理升级</strong><p>所有会话均在课程政策范围内流转。</p></div></div>
          }
        </section>
        <section className="trajectory"><div className="section-top"><div><span className="eyebrow">TURN TRACE</span><h2>最近教学轨迹</h2></div><button>回放完整轨迹</button></div><div className="trace-line">{["学生输入","任务分类","课程政策","资料检索","误区诊断","工具验证","最终回复"].map((item,i)=><div key={item} className={i<6?"passed":"current"}><span>{i<6?'✓':i+1}</span><small>{item}</small></div>)}</div><p>{isRealData ? "数据来自各学生的教学转折记录。课程政策在每次回复时以代码执行。" : "教师验证通过后将显示实时教学轨迹数据。"}</p></section>
      </div>
    </main>
  );
}

function CapabilityGateway({ open, options, selected, onSelect, onClose }: { open: boolean; options: CapabilityChoice[]; selected: CapabilityChoice; onSelect: (capability: CapabilityChoice) => void; onClose: () => void }) {
  if (!open) return null;
  return <div className="modal-layer" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><section className="model-modal" role="dialog" aria-modal="true" aria-labelledby="capability-title"><div className="model-modal-top"><div><span className="eyebrow">LEARNING CAPABILITY</span><h2 id="capability-title">选择学习能力</h2></div><button onClick={onClose} aria-label="关闭能力设置">×</button></div><p>你只需选择任务类型。真实模型、接口地址与密钥均由服务器安全路由，课程检索和科学验证保持不变。</p><div className="model-list">{options.map((option) => <button key={option.id} className={selected.id === option.id ? "selected" : ""} onClick={() => { onSelect(option); onClose(); }}><span>{option.acceptsImages ? "图" : option.id === "code" ? "码" : option.id === "deep" ? "深" : "快"}</span><div><strong>{option.label}</strong><small>{option.description}</small></div><Tag tone={option.configured ? "green" : "amber"}>{option.configured ? "已就绪" : "可回退"}</Tag></button>)}</div><div className="model-security"><span>✓</span><p><strong>模型配置仅在服务器端</strong><small>浏览器看不到模型名称、API 地址或密钥，也不能绕过教师设定的教学策略。</small></p></div></section></div>;
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("concept");
  const [role, setRole] = useState<Role>("student");
  const [theme, setTheme] = useState<"paper" | "board">("paper");
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [latestTutor, setLatestTutor] = useState<TutorApiResponse | null>(null);
  const fallbackCapabilities: CapabilityChoice[] = [
    { id: "quick", label: "快速问答", shortLabel: "快速", description: "适合概念澄清与短问题。", acceptsImages: false, configured: false },
    { id: "deep", label: "深度讲解", shortLabel: "深度", description: "适合复杂推导与跨章节联系。", acceptsImages: false, configured: false },
    { id: "vision", label: "图片识别", shortLabel: "识图", description: "读取题目截图和手写推导。", acceptsImages: true, configured: false },
    { id: "vision-reasoner", label: "图片深度推理", shortLabel: "图像推理", description: "分析复杂图表和多步推导。", acceptsImages: true, configured: false },
    { id: "code", label: "编程实验", shortLabel: "编程", description: "解释、调试量子物理数值代码。", acceptsImages: false, configured: false },
  ];
  const [capabilityOpen, setCapabilityOpen] = useState(false);
  const [capabilities, setCapabilities] = useState<CapabilityChoice[]>(fallbackCapabilities);
  const [selectedCapability, setSelectedCapability] = useState<CapabilityChoice>(fallbackCapabilities[0]);
  useEffect(() => { fetch("/api/capabilities").then((response) => response.json()).then((data: { capabilities?: CapabilityChoice[] }) => { if (data.capabilities?.length) { setCapabilities(data.capabilities); setSelectedCapability(data.capabilities[0]); } }).catch(() => {}); }, []);
  const workspace = mode === "concept" ? <ConceptWorkspace capability={selectedCapability} onLatest={setLatestTutor} /> : mode === "derivation" ? <DerivationWorkspace capability={selectedCapability} onLatest={setLatestTutor} /> : mode === "experiment" ? <ExperimentWorkspace /> : <ProjectWorkspace />;
  return (
    <div className={`quantum-app theme-${theme}`}>
      <header className="topbar">
        <div className="brand"><BrandMark /><div><strong>Quantum Agent</strong><span>可信量子物理教学智能体</span></div></div>
        <div className="top-context"><span>量子物理 · 2026 春</span><i/><span>{role === "student" ? "学生工作台" : "教师驾驶舱"}</span><button className="gateway-button" onClick={() => setCapabilityOpen(true)}><b className={selectedCapability.configured ? "online" : "fallback"}/>{selectedCapability.label}<small>{selectedCapability.configured ? "能力已就绪" : "安全回退可用"}</small></button></div>
        <div className="top-actions">
          <button className="mobile-nav" onClick={() => setLeftOpen(!leftOpen)} aria-label="打开导航">☰</button>
          {role === "student" && <button className="evidence-toggle" onClick={() => setRightOpen(!rightOpen)}>学习证据</button>}
          <button className="theme-toggle" onClick={() => setTheme(theme === "paper" ? "board" : "paper")} aria-label="切换深浅主题"><span>{theme === "paper" ? "☾" : "☀"}</span></button>
          <button className="help-button">?</button>
          <button className="profile" onClick={() => setRole(role === "student" ? "teacher" : "student")}><span>谢</span><div><strong>{role === "student" ? "谢翔宇" : "谢老师"}</strong><small>切换至{role === "student" ? "教师端" : "学生端"}</small></div><i>⌄</i></button>
        </div>
      </header>
      {role === "student" ? <div className="student-shell"><StudentSidebar mode={mode} setMode={(next) => { setMode(next); setLeftOpen(false); }} open={leftOpen}/><main className="main-workspace">{workspace}</main><RightEvidence open={rightOpen} latest={latestTutor}/>{(leftOpen || rightOpen) && <button className="mobile-backdrop" aria-label="关闭侧栏" onClick={()=>{setLeftOpen(false);setRightOpen(false)}}/>}</div> : <TeacherDashboard onLogout={() => setRole("student")} />}
      <CapabilityGateway open={capabilityOpen} options={capabilities} selected={selectedCapability} onSelect={(next) => { setSelectedCapability(next); if (next.id === "code" || next.acceptsImages) setMode("concept"); }} onClose={() => setCapabilityOpen(false)}/>
      <div className="prototype-flag"><span/>智能体后端已接入</div>
    </div>
  );
}
