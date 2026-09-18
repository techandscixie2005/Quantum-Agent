"use client";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import { AgentExperience } from "../AgentExperience";
import { AgentQueryProvider } from "../AgentQueryProvider";
import { AgentEquation } from "../AgentEquation";
import { createDemoAdapter } from "./adapter";
import calculation from "./calculation.json";
import handoutMeta from "./handout-meta.json";
import "./offline.css";

const badge = "离线功能演示｜预设教学样例，非实时模型推理";
const tabs = ["课程与复核", "输入与确认", "来源与图谱", "推导桥", "实验与代码", "学习记录与活动", "帮助与范围"];
const formula = String.raw`T=\left[1+\frac{V_0^2\sinh^2(\kappa a)}{4E(V_0-E)}\right]^{-1},\quad\kappa=\frac{\sqrt{2m(V_0-E)}}{\hbar}`;
function transmission(a: number) { const k = Math.sqrt(2*9.1093837015e-31*5*1.602176634e-19)/1.054571817e-34;return 1/(1+Math.sinh(k*a*1e-9)**2); }
const code = `# 示例代码：本轮在本地 Python / NumPy 实际执行\n# 独立匹配 psi 与 psi'，并与解析式交叉核对\np = exp(kappa*a); q = exp(-kappa*a); z = exp(1j*k*a)\nM = [[1,-1,-1,0], [-1j*k,-kappa,kappa,0],\n     [0,p,q,-z], [0,kappa*p,-kappa*q,-1j*k*z]]\nr,A,B,t = numpy.linalg.solve(M, [-1,-1j*k,0,0])\nT = abs(t)**2; R = abs(r)**2\nassert abs(T + R - 1) < 1e-12\nassert abs(T - analytic_T) < 1e-12`;
const subscribeReady = () => () => {};
const subscribePhase = (notify: () => void) => { window.addEventListener("qa-offline-stage", notify); return () => window.removeEventListener("qa-offline-stage", notify); };
const readPhase = () => JSON.parse(sessionStorage.getItem("qa_offline_v1") ?? "null")?.last?.learning_native?.phase ?? "";
export function OfflineDemo() {
  const isClient = useSyncExternalStore(subscribeReady, () => true, () => false);
  const demo = useMemo(() => isClient ? createDemoAdapter() : null, [isClient]);
  const phase = useSyncExternalStore(subscribePhase, readPhase, () => "");
  const [tab, setTab] = useState<string | null>(null);
  const [caption,setCaption]=useState("量子隧穿：从错误预测走向独立迁移");
  const [chapter,setChapter]=useState("定态散射");
  const [review,setReview]=useState("");
  const [preview,setPreview]=useState("推导图像");
  const [confirmed,setConfirmed]=useState(false);
  const [text,setText]=useState("E < V₀，所以 T = 0。");
  const [width,setWidth]=useState(0.1);
  const [node,setNode]=useState("边界连续");
  const [expanded,setExpanded]=useState(false);
  const [uploaded,setUploaded]=useState("");
  const [localFile,setLocalFile]=useState<File | null>(null);
  const [localUrl,setLocalUrl]=useState("");
  const [knownPdf,setKnownPdf]=useState(false);
  const localUrlRef = useRef("");
  useEffect(() => () => { if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current); }, []);
  async function selectFile(file: File) {
    if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
    const url = URL.createObjectURL(file);
    localUrlRef.current = url;
    setLocalUrl(url); setLocalFile(file); setUploaded(file.name); setPreview("本地附件"); setKnownPdf(false);
    if (file.type === "application/pdf") {
      const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
      if (localUrlRef.current === url) setKnownPdf(Array.from(new Uint8Array(hash), v => v.toString(16).padStart(2, "0")).join("") === handoutMeta.sha256);
    }
  }
  const row=calculation[width===0.1?0:1];
  const history=demo && typeof window!=="undefined" ? JSON.parse(sessionStorage.getItem("qa_offline_v1")??"null") : null;
  return <div className="offline-demo">
    <header className="offline-banner"><strong>{badge}</strong><span>依据用户本次确认批准演示</span><button onClick={()=>{demo?.reset();location.reload();}}>重置演示</button></header>
    <nav className="offline-tools" aria-label="离线辅助功能">{tabs.map(t=><button key={t} disabled={phase==="solo_active" && t!=="学习记录与活动"} onClick={()=>{setTab(t);setCaption(t);}}>{t}</button>)}</nav>
    {demo ? <AgentQueryProvider><AgentExperience demo={demo}/></AgentQueryProvider> : <p>载入隔离样例…</p>}
    {tab ? <section role="dialog" aria-modal="true" aria-label={tab} className="offline-dialog">
      <header><div><small>{badge}</small><h1>{tab}</h1></div><button onClick={()=>setTab(null)}>返回教学工作台</button></header>
      {tab==="课程与复核" ? <div className="offline-columns"><article><h2>课程 / 章节导航 · 离线交互原型</h2><label>课程版本<select aria-label="离线课程版本"><option>量子物理 · 离线演示讲义</option></select></label><p>本演示提供一个课程版本、两个样例章节。</p><label>章节<select aria-label="离线章节" value={chapter} onChange={e=>setChapter(e.target.value)}><option>定态散射</option><option>宽度变化与迁移</option></select></label><div className="offline-result" data-testid="chapter-detail"><strong>{chapter}</strong><p>{chapter==="定态散射"?"学习目标：识别经典禁阻误用，建立两端边界条件。":"学习目标：比较0.10与0.15 nm的透射率，在Solo中独立迁移。"}</p></div><h2>学习统计 · 本地操作计数</h2><p>已完成样例动作：{(history?.index??-1)+1} / 6</p><p>当前教学阶段：{history?.last?.learning_native?.phase??"尚未开始"}</p></article><article><h2>教师辅助入口 · 只读交互原型</h2><p>对应真实产品的知识候选复核与 Agent Trace 复核。这里仅预览样例，不形成审核决定、不发布课程。</p><div className="offline-actions"><button onClick={()=>setReview("知识候选：边界连续 → 非零透射。来源为离线演示讲义第1节；须检查适用条件与证据。")}>查看知识候选样例</button><button onClick={()=>setReview("Trace 样例：预测 → 最小提示 → 数值检查 → 重构 → Solo。复核重点：先尝试后解释、引文定位、错误答案不推进。")}>查看 Trace 复核样例</button></div>{review?<div className="offline-result" data-testid="review-detail">{review}</div>:null}<p>正式教师认证、批准/拒绝/接管、课程发布与 PostgreSQL 留痕均保留在真实入口；本片不声称这些已离线验收。</p></article></div>:null}
      {tab==="输入与确认" ? <div className="offline-columns"><article><h2>输入样例与预览</h2><p>演示识别为预设转录；上传文件仅在本地预览，不发送服务器。</p><div className="offline-actions">{["文本","推导图像","PDF讲义"].map(p=><button key={p} onClick={()=>setPreview(p)}>{p}</button>)}</div><label className="offline-upload">选择本地图片 / PDF<input type="file" accept="image/*,application/pdf,text/plain" onChange={e=>{const f=e.target.files?.[0];if(f)void selectFile(f);}}/></label>{uploaded ? <p role="status">已选择：{uploaded}（本地预览样例，不执行 OCR）</p>:null}<div className="offline-preview" data-testid="offline-preview">{preview==="本地附件" && localUrl ? (localFile?.type.startsWith("image/")?<Image unoptimized width={1131} height={1600} src={localUrl} alt="本地附件预览"/>:<div>{knownPdf ? <><p>PDF 第1页 · 同文件哈希匹配的预渲染预览</p><Image unoptimized width={1131} height={1600} className="offline-pdf-page" src="/offline/handout-page.png" alt="PDF 第1页预渲染预览"/></> : <p>此 PDF 没有预计算页图；演示预览仅支持随附的 handout.pdf。</p>}</div>):preview==="推导图像"?<Image unoptimized width={1131} height={1600} src="/offline/attempt.svg" alt="学生推导样例：E小于V零，因此T等于零"/>:preview==="PDF讲义"?<Image unoptimized width={1131} height={1600} className="offline-pdf-page" src="/offline/handout-page.png" alt="离线讲义PDF第1页预渲染预览"/>:<blockquote>我预测 E &lt; V₀ 时无法穿越势垒，透射概率为零。</blockquote>}</div></article><article><h2>识别结果确认 · 交互原型</h2><p>核对图中的 V₀ 下标和不等号，再确认当前尝试。此处保留错误预测供下一阶段诊断。</p><label>确认后的转录<textarea value={text} onChange={e=>{setText(e.target.value);setConfirmed(false);}}/></label><button onClick={()=>setConfirmed(true)} disabled={!text.trim()}>确认识别结果</button>{confirmed?<div role="status" className="offline-result">已确认当前尝试：{text}<p>回到工作台，使用下一步样例提交预测。</p></div>:null}<AgentEquation latex={String.raw`E<V_0\ \overset{\text{待诊断}}{\Longrightarrow}\ T=0`}/></article></div>:null}
      {tab==="来源与图谱"?<div className="offline-columns"><article><h2>离线演示讲义 · 第1节，1–9行</h2><p>本次编写，可本地定位；不是原始课件。</p><iframe title="来源片段定位" src="/offline/handout.txt"/><a href="/offline/handout.pdf" target="_blank" rel="noreferrer">打开讲义 PDF 原文（第1页）</a></article><article><h2>知识图谱 · 预设概念关系</h2><div className="offline-graph">{["经典禁阻","边界连续","指数衰减","非零透射"].map((n,i)=><div key={n}><button aria-pressed={node===n} onClick={()=>setNode(n)}>{n}</button>{i<3?<p>↓ {['不能直接推出','约束振幅系数','有限宽度连接'][i]}</p>:null}</div>)}</div><div className="offline-result" data-testid="graph-detail">{node}：{node==="经典禁阻"?"经典粒子结论不能直接代替量子边界匹配。":node==="边界连续"?"ψ 与 ψ′ 在 x=0 和 x=a 两端连续。":node==="指数衰减"?"势垒内包含两个指数项；匹配两端后确定系数。":"有限宽度下右侧振幅通常非零，T=|t|²。"}</div></article></div>:null}
      {tab==="推导桥"?<article className="offline-bridge"><h2>从薛定谔方程到透射率 · 预设推导样例</h2><AgentEquation latex={String.raw`-\frac{\hbar^2}{2m}\psi''+V_0\psi=E\psi`}/><button onClick={()=>setExpanded(!expanded)}>{expanded?"收起缺失步骤":"展开缺失步骤：势垒内通解与边界匹配"}</button>{expanded?<div data-testid="offline-bridge-steps"><AgentEquation latex={String.raw`\psi''=\kappa^2\psi,\quad\psi_{II}=Ae^{\kappa x}+Be^{-\kappa x}`}/><AgentEquation latex={String.raw`\psi_I(0)=\psi_{II}(0),\quad\psi'_I(0)=\psi'_{II}(0)`}/><AgentEquation latex={String.raw`\psi_{II}(a)=\psi_{III}(a),\quad\psi'_{II}(a)=\psi'_{III}(a)`}/><p>缺失的是两端的四个匹配条件；不是把波函数在势垒内直接设为零。</p></div>:null}<AgentEquation latex={formula}/><p>适用：一维定态、有限矩形势垒、等质量、两侧势能为零、0 &lt; E &lt; V₀。来源：离线演示讲义第1节。</p></article>:null}
      {tab==="实验与代码"?<div className="offline-columns"><article><h2>矩形势垒 · E=5 eV，V₀=10 eV</h2><label>预计算参数选项：宽度 a<select aria-label="离线势垒宽度" value={width} onChange={e=>setWidth(Number(e.target.value))}><option value="0.1">0.10 nm</option><option value="0.15">0.15 nm</option></select></label><svg viewBox="0 0 720 340" className="offline-plot" role="img" aria-label={`透射率曲线，当前宽度${width}纳米`}><line x1="65" y1="285" x2="690" y2="285" stroke="#8b9c99"/><line x1="65" y1="25" x2="65" y2="285" stroke="#8b9c99"/>{[0,.25,.5,.75,1].map(y=><g key={y}><text x="18" y={290-250*y}>{y}</text><line x1="65" x2="690" y1={285-250*y} y2={285-250*y} stroke="#e1e8e6"/></g>)}<polyline fill="none" stroke="#187760" strokeWidth="4" points={Array.from({length:101},(_,i)=>`${65+i*6.25},${285-250*transmission(i*.003)}`).join(' ')}/><circle cx={65+width/.3*625} cy={285-row.T*250} r="8" fill="#ce633e"/><text x="320" y="330">势垒宽度 a (nm) · 0 → 0.30</text><text x="76" y="23">透射概率 T（无量纲）</text></svg><div className="offline-metrics" data-testid="offline-metrics"><strong>T = {row.T.toFixed(9)}</strong><strong>R = {row.R.toFixed(9)}</strong><span>a = {width.toFixed(2)} nm</span></div><p>曲线由浏览器实时计算解析式；选中点与表格来自本轮独立 Python 边界匹配的预计算结果。</p><AgentEquation latex={formula}/></article><article><h2>示例代码与真实计算核对</h2><pre>{code}</pre><div className="offline-result"><strong>本轮本地计算通过 · 两组参数</strong><p>|T + R − 1| = {row.conservation_error.toExponential(2)}</p><p>|T − T解析| = {Math.abs(row.T-row.exact_T).toExponential(2)} &lt; 10⁻¹²</p><p>实际执行：NumPy 线性方程求解；不是模型生成，不是本轮在线沙箱调用。</p></div><p>局限：非波包动画，不描述穿越时间；R=1−T 的曲线本身不作为独立守恒验证。</p></article></div>:null}
      {tab==="学习记录与活动"?<div className="offline-columns"><article><h2>学习证据 · 本标签页隔离记录</h2><p>当前阶段：<strong data-testid="offline-saved-phase">{history?.last?.learning_native?.phase??"尚未提交"}</strong></p><ol className="offline-timeline">{["提出问题，保留预测门","错误预测：T=0；记录经典直觉","修正：右侧振幅非零；比对数值","Teach-Back：指数衰减；反馈遗漏边界连接","补全关系，进入迁移与 Solo","独立提交 0.15 nm 的透射率与趋势"].slice(0,(history?.index??-1)+1).map(t=><li key={t}>{t}</li>)}</ol><p>这些是已操作的样例事件，不写入真实学习证据数据库。</p></article><article><h2>Agent Activity · 脚本化事件流</h2><ol className="offline-timeline">{history?.last?.trace.map((t:{name:string;detail:string})=><li key={t.name}>{t.name}<small>{t.detail}</small></li>)}</ol><p>workflow.started → progress → workflow.completed；每轮终态经过现有前端合同解析。</p></article></div>:null}
      {tab==="帮助与范围"?<article><h2>可复现的功能演示</h2><p>按“填入下一步样例 → 发送”完成六轮教学；辅助面板可随时打开。重置演示创建独立新会话。</p><p>四种工作模式、命令面板、当前尝试、教学卡片与 Cognitive Mirror 复用现有工作台。</p><p>附件确认、图谱点击、推导桥和实验代码面板为本次离线交互原型。教师治理、账户凭据、课程发布与真实持久化未在此离线入口模拟通过。</p><p>自由输入仅支持明确列出的教学样例；错误迁移答案不推进。</p><p>依据用户本次确认批准演示；历史待审核稿保持不变。</p></article>:null}
    </section>:null}
    <footer className="offline-caption">{caption} · 预设样例演示</footer>
  </div>;
}
