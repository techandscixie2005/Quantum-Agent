# Quantum Agent — PRD

**版本**：Competition Release · Final  
**目标赛事**：中国科学技术大学“一〇七杯”算力与智能体开发大赛 · 智能体赛道  
**定位**：面向中国科学技术大学《量子物理》课程的 Learning-Native 多智能体教学系统

> **不是替学生思考，而是看见学生的思考、修复学生的思考，并最终把思考还给学生。**

> **Think with AI. Think without AI.**

> **One Knowledge Graph · One Tutor Graph · One Event Stream · One Learning Stage**

---

## 1. 产品目标

Quantum Agent 不是量子物理版 ChatGPT，也不是普通课程 RAG。

系统把：

```text
Question → Answer
```

重构为：

```text
Attempt / Prediction
→ Course Evidence
→ Diagnosis
→ Minimal Intervention
→ Scientific Action
→ Verification
→ Reconstruction
→ Teach-Back
→ Transfer
→ Solo
→ Learning Evidence
```

最终优化目标：

\[
\max P(\text{学生在减少或撤除 AI 帮助后，仍能独立解决相关新问题})
\]

核心原则：

```text
Teaching experience defines the problem.
Pedagogy defines the constraints.
Agents provide intelligence.
Course evidence grounds.
Tools verify truth.
```

---

## 2. Competition Scope

### 必须完成

- Python / FastAPI 权威后端；
- LangGraph Tutor Graph；
- 多模态输入；
- Evidence Agent；
- Diagnosis Agent；
- Commitment Gate；
- deterministic pedagogical policy；
- Coding Agent；
- isolated sandbox；
- Scientific Verifier；
- Teach-Back / Transfer / Solo；
- Cognitive Mirror / Learning Evidence；
- PostgreSQL + pgvector；
- Neo4j；
- Redis；
- API Key 登录与 session credential vault；
- 真实增量 SSE；
- 完整 Golden Loop E2E；
- 一键可部署 Competition Release。

### 不做

- 泛学科平台；
- AI classmates；
- Flashcard / FSRS；
- 长期 Goal Planner；
- 通用课程生成；
- 大型白板或通用 Action Engine；
- 为展示“多智能体”增加无必要 Agent；
- 平行重写 Agent runtime；
- 用 mock 或预制函数替代关键路径。

---

## 3. 三类核心 Learning Episode

### 3.1 Reasoning Clinic

针对“学生已有思路，但结果错误或存在矛盾”。

```text
Student Attempt
→ Diagnosis
→ first consequential error
→ Minimal Intervention
→ Student Reconstruction
```

要求：

- 优先理解学生现有推理；
- 找到第一处真正导致后续偏离的错误；
- 不默认重新完整解题；
- 只提供当前需要的最小帮助。

### 3.2 Derivation Bridge

针对教材、PPT 中的跳步。

```text
Missing Step
→ Course Evidence
→ Prerequisite / Assumption
→ Minimal Derivation Bridge
→ Reconstruction
```

要求：

- 基于正式课程材料；
- 指明来源文件、章节、页码；
- 补足必要中间步骤，而不是扩写成整章讲义；
- 无法确认的内容不得伪造来源。

### 3.3 Scientific Co-Derivation

针对计算量大、容易算错、需要建立直觉的问题。

```text
Student Prediction
→ ScientificTask
→ Coding Agent
→ Sandbox
→ Scientific Verifier
→ Plot / Data / Code
→ Student Explanation
```

比赛 Golden Loop 可重点展示量子隧穿，但系统不能只支持这一类问题。

---

## 4. 总体架构

### 4.1 One Knowledge Graph

Pedagogical Knowledge Graph 是课程世界模型。

至少支持：

```text
Chapter
Concept
Principle
Equation
Derivation
Prerequisite
Misconception
Example
ScientificTask
Source
```

核心关系：

```text
PREREQUISITE_OF
DERIVED_FROM
EXPLAINS
CONTRASTS_WITH
COMMONLY_CONFUSED_WITH
APPEARS_IN
VERIFIED_BY
TRANSFER_TO
```

权威边界：

```text
Original Course Material = 科学与课程事实权威
PostgreSQL                = 文档生命周期、审核、provenance 权威
pgvector / FTS            = 检索索引
Neo4j                     = 可重建语义结构
LLM                       = 推理与生成
```

要求：

- student-visible knowledge 必须有 provenance；
- 原始 source chunk 不可变；
- 教师审核与发布状态保存在 PostgreSQL；
- Neo4j 不是原始证据；
- 比赛版允许知识 chunk 后续继续补充，但 ingestion / review / retrieval / graph 接口必须完整。

---

### 4.2 One Tutor Graph

Tutor Graph 负责“怎么教”。

```text
Input / Perception
→ Commitment
→ Evidence
→ Diagnosis
→ Pedagogical Policy
→ Tutor or Scientific Action
→ Verification
→ Reconstruction
→ Teach-Back
→ Transfer
→ Solo
→ Learning Evidence
```

核心原则：

```text
LLM proposes.
Policy decides.
Tools verify.
```

要求：

- 关键 Gate 必须由确定性代码控制；
- LearningPhase transition authority 只属于后端持久化状态；
- LLM 不得决定是否进入 TEACH_BACK / TRANSFER / SOLO / COMPLETE；
- 概念、推导、计算类 Learning Episode 不得静默跳过必要阶段；
- 简单事实查询允许短路径；
- Graph 状态必须可持久化和恢复。

---

### 4.3 One Event Stream

长流程必须通过真实 SSE 增量公开进度。

```text
LearningEvent {
  run_id
  event_id
  sequence
  phase
  actor
  type
  status
  public_summary
  artifact_refs
  evidence_refs
  timestamp
}
```

至少覆盖：

```text
workflow.started
commitment.requested
evidence.started / completed
diagnosis.started / completed
strategy.selected
coding.started / generated
sandbox.started / completed
verification.started / pass / fail / inconclusive
teachback.requested
transfer.started
solo.entered
workflow.completed
```

要求：

- 每个 run 内 sequence 严格单调；
- 重复事件必须幂等；
- 长任务必须有 heartbeat；
- 浏览器必须在 terminal event 前收到中间事件；
- 支持断线恢复或明确终止状态；
- terminal event 只发一次；
- 前端不得伪造后端未产生的进度；
- BFF 不得缓冲完整 SSE 后一次性返回。

---

### 4.4 One Learning Stage

学生页面只有一个视觉中心：**Scientific Learning Stage**。

学习状态直接驱动界面：

```text
COMMITMENT → Prediction / Attempt
EVIDENCE   → Course Evidence
DIAGNOSIS  → Reasoning Focus
INTERVENE  → Hint / Explanation
EXPERIMENT → Scientific Experiment
VERIFY     → Verification
TEACH_BACK → Teach Mode
TRANSFER   → Transfer Task
SOLO       → Solo Mode
COMPLETE   → Cognitive Mirror
```

Course / Evidence / Learning / Agents 等作为轻量悬浮入口，默认收起。

前端要求：

- 简洁、克制、现代；
- 具有量子物理、科学计算和学术教学的视觉气质；
- 数学公式、推导、代码、图像、证据引用是一等视觉对象；
- 动画只用于状态切换、物理结构和信息层级；
- 不做普通聊天机器人式布局；
- 桌面端优先，保证基础响应式；
- 可研究 OpenMAIC、DeepTutor、OpenTutor、LearnHouse、Studyield 等项目的交互思想，但不得机械复制。

---

## 5. 教学策略

### 5.1 Commitment Gate

适合学习的问题，在完整解释前要求最小认知投入，例如：

- 一个预测；
- 一步推导；
- 一个物理理由；
- 一个选项；
- 一张图；
- 或明确“不知道”。

Gate 必须 fail-closed。

---

### 5.2 Evidence

Evidence Agent 只回答：

> 课程资料中有哪些可靠依据？

输出至少包含：

```text
sources
passages
page_refs
concept_ids
coverage
conflicts
```

Evidence 不负责决定教学策略。

---

### 5.3 Diagnosis

Diagnosis Agent 输出：

```text
target_concepts
prerequisite_gaps
first_consequential_error
misconception_candidates
confidence
verification_needed
```

长推导优先处理 `first consequential error`。

---

### 5.4 Assistance Ladder

```text
L0 Student generation
L1 Attention cue
L2 Minimal hint
L3 Socratic / contrastive question
L4 Representation translation
L5 Partial worked step
L6 Full explanation
```

系统应尽量使用满足教学目标的最低帮助等级，并持久化 `assistance_level_used`。

---

## 6. Scientific Learning Environment

### Coding Agent

输入：

```text
ScientificTask {
  goal
  known_parameters
  required_outputs
  allowed_libraries
  scientific_constraints
  verification_contract
}
```

要求：

- 必须针对当前任务现场生成代码；
- 不允许 orchestrator 调预制答案函数后伪装成 Agent 输出。

### Sandbox

必须具备：

- 独立 runner；
- API 进程不直接执行生成代码；
- no network；
- non-root；
- read-only root；
- cap_drop；
- no-new-privileges；
- CPU / RAM / PID / wall-time limits；
- import allowlist / AST safety；
- bounded stdout / stderr。

### Scientific Verifier

LLM 不负责最终科学正确性裁决。

Verifier 至少检查适用的：

- 归一化；
- 守恒律；
- 边界条件；
- 量纲；
- 极限行为；
- 数值稳定性；
- 任务专属 physics oracle。

结果只有：

```text
PASS
FAIL
INCONCLUSIVE
```

---

## 7. Learning Evidence

“看懂”不是完成条件。

重要概念必须逐步进入：

```text
Reconstruction
→ Teach-Back
→ Transfer
→ Solo
```

### Teach-Back

学生反过来向系统解释关键概念或推导。

### Transfer

换一个表面不同、结构相关的问题，验证迁移。

### Solo

撤除提示与辅助。

Solo 必须：

- 在生成前锁定；
- 刷新或新标签页不能绕过；
- 服务端持久化；
- 只有明确退出或完成才能解除。

### Cognitive Mirror

只基于可观察学习证据生成学习状态，不让 LLM 主观输出“掌握度百分比”。

---

## 8. Multimodal

支持：

- 文本；
- 图片；
- 截图；
- 手写推导；
- PDF。

原则：

```text
Perception = 看到了什么
Diagnosis  = 学生哪里可能错
Verifier   = 科学结果是否成立
```

Perception 不承担科学裁决。

---

## 9. Model Gateway 与安全

所有模型通过统一 ModelGateway 调用。

要求：

- 登录页输入比赛 API Key；
- Key 不得硬编码；
- 不得写入客户端 bundle；
- 不得出现在日志、错误响应和 trace；
- session credential 加密保存；
- logout 必须清除对应凭据和缓存；
- production 不得回退到部署者密钥；
- 关键模型异常必须 fail-closed。

---

## 10. Interaction Latency SLO

目标不是只追求模型速度，而是避免学生感到系统失去响应。

```text
Time to first visible event       < 1 s target
Normal non-scientific tutor turn < 10 s target
Scientific experiment             continuous visible progress
Silent unexplained wait           < 5 s
Competition Golden Loop           ≤ 5 min target
```

优化优先级：

```text
parallel retrieval
→ capability routing
→ stream early
→ overlap independent work
→ cache immutable course artifacts
```

不得缓存学生特定的教学决策来伪造实时运行。

---

## 11. Golden Loop

Competition Release 必须真实跑通：

```text
Login
→ Student Attempt
→ Commitment
→ Evidence
→ Diagnosis
→ Minimal Intervention
→ Scientific Experiment
→ Coding Agent generates code
→ Sandbox executes
→ Scientific Verifier
→ Reconstruction
→ Teach-Back
→ Transfer
→ Solo
→ Cognitive Mirror / Learning Evidence
```

要求：

- 不使用 first-party mock；
- 不跳过必要阶段；
- 每一步在 Event Stream 中可观察；
- 状态可持久化；
- 浏览器刷新后行为正确；
- 关键 artifact 可查看；
- 最终结果来自真实模型、真实代码执行和真实验证。

---

## 12. Frontend Acceptance

首页必须首先呈现 Scientific Learning Stage。

验收：

- 主工作台占绝对视觉中心；
- 周边功能默认收起；
- 当前 LearningPhase 一眼可辨；
- Evidence、公式、代码、Plot、Verification 可直接查看；
- Teach-Back / Transfer / Solo 是真实交互，不是展示卡片；
- 长任务持续显示真实进度；
- 无明显布局溢出、阻塞或状态错乱；
- 关键流程可由 Playwright 自动验证。

---

## 13. Release Contract

Competition Release 必须包含：

```text
README.md
DEMO.md
.env.example
Docker Compose
one-command startup
health / readiness checks
database migration
course ingestion entry
model connection probe
sandbox runner
production web build
tests
```

要求：

- fresh environment 可按照文档启动；
- 不包含真实 secret；
- API、数据库、Web、Sandbox 都有健康检查；
- 发布前运行完整测试；
- 保留第三方依赖与许可证声明；
- 参考开源项目只吸收设计思想或合法兼容代码，不整体复制 UI。

---

## 14. Definition of Done

只有同时满足以下条件，才允许标记 Competition Ready：

### Product

- 三类核心 Learning Episode 均真实可用；
- Scientific Learning Stage 成为唯一视觉中心；
- Teach-Back / Transfer / Solo 真正闭环。

### Architecture

- One Knowledge Graph；
- One Tutor Graph；
- One Event Stream；
- One Learning Stage；
- 无第二套权威 Agent runtime。

### Science

- Coding Agent 真实生成代码；
- Sandbox 真执行；
- Verifier 独立验证；
- 课程结论有 provenance。

### Reliability

- Golden Loop E2E 通过；
- SSE 真增量；
- refresh / reconnect 行为正确；
- 关键状态持久化；
- 无 P0 security blocker。

### Release

- fresh-machine deployment 可复现；
- 无硬编码密钥；
- README / DEMO 完整；
- 比赛现场 5 分钟内能清楚展示核心价值。

---

## 15. 最终开发原则

比赛前只执行：

```text
Preserve
→ Integrate
→ Complete
→ Optimize
→ Demonstrate
```

禁止继续扩产品边界。

最终目标不是展示“系统用了多少 Agent”，而是让评委清楚看到：

> **Quantum Agent 能理解学生怎样思考，以课程证据约束解释，用真实科学工具验证结果，并最终通过 Teach-Back、Transfer 和 Solo 把思考能力重新交还给学生。**
