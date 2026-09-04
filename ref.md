# Quantum Agent 参考开源项目调研报告

**文件名**：`ref.md`  
**调研日期**：2026-08-31  
**调研对象**：GitHub 上与 AI 教学、智能辅导、学习工作台、多智能体课堂、学习者建模、Teach-Back、课程 RAG、科学/代码工具执行相关的优秀开源项目  
**服务目标**：为 Quantum Agent 的 Competition Release 与赛后演进提供可直接执行的产品、交互和架构参考

---

## 0. 执行摘要

Quantum Agent 当前最需要的不是继续堆叠更多“教育功能”，而是把已经具备的 Learning-Native 教学闭环、课程证据、科学计算、Coding Agent、Verifier、Teach-Back、Transfer、Solo 和 Cognitive Mirror，组织成一个真正自然、清晰、稳定的学习产品。

本轮调研后，最值得长期跟踪的项目可以分成四类：

1. **沉浸式课堂与交互 Runtime**
   - THU-MAIC / OpenMAIC
   - OpenMAIC-Project

2. **Agent-native 个性化学习工作台**
   - HKUDS / DeepTutor
   - OpenTutor
   - LearnHouse
   - Studyield

3. **教学策略、学习者模型与目标导向 ITS**
   - GenMentor
   - Tutor CoPilot
   - EduChat / EduChat-R1
   - Pxplore

4. **特定教学机制与课程证据**
   - martius-lab / ai-tutor
   - Socratic Tutor
   - VirtuTA

如果只保留当前 Competition Release 最值得吸收的内容，建议集中在：

```text
OpenMAIC
    → Scientific Learning Stage
    → Scene / Action / Timeline
    → 低延迟交互 Runtime

DeepTutor
    → durable session
    → multi-layer memory
    → inspectable learner history

OpenTutor
    → adaptive central workspace
    → block / scene based UI
    → 让界面跟当前学习任务变化

martius-lab/ai-tutor
    → Learning by Teaching
    → 强化 Teach-Back 的真实性

Studyield
    → multi-agent solve + verification
    → Teach-Back + code sandbox 的产品组合

GenMentor / Tutor CoPilot / EduChat
    → pedagogy 成为一等对象
    → learner state / teaching strategy / goal alignment
```

Quantum Agent 不应该最终变成这些项目的“功能并集”。

更合适的定位是：

> **Quantum Agent = Learning-Native Scientific Tutor Runtime**

即：

```text
Pedagogy decides
Agents reason
Course evidence grounds
Scientific tools verify
Student actions create learning evidence
```

这仍然是 Quantum Agent 与大部分现有开源 AI Tutor 最核心的区分。

---

# 1. 调研方法与筛选标准

本报告优先使用项目的：

- 官方 GitHub repository；
- README；
- CHANGELOG；
- LICENSE；
- 官方论文/项目介绍；
- 项目实际目录和工程说明。

筛选标准不是单纯看 Star，而是看它是否对 Quantum Agent 至少一个核心问题有实质参考价值：

| 维度 | 关注问题 |
|---|---|
| 教学设计 | 是否真的控制“怎么教”，而不是只回答问题 |
| 学习过程 | 是否支持尝试、追问、反馈、迁移、记忆等闭环 |
| Agent 架构 | 是否存在明确的职责分工和运行时 |
| UI/UX | 是否超越普通聊天框 |
| 课程证据 | 是否支持材料、引用、RAG、provenance |
| 学习者模型 | 是否积累跨轮次/跨 session 学习状态 |
| 工具 | 是否支持代码、仿真、白板、可视化等教学动作 |
| 工程成熟度 | 是否有持久化、流式、沙箱、E2E、自托管等能力 |
| 可借鉴性 | 能否在不破坏 Quantum Agent 主架构的前提下吸收 |

---

# 2. Quantum Agent 当前应坚持的边界

根据当前 Competition Release，Quantum Agent 的核心已经收敛为：

```text
One Graph · One Stream · One Stage
```

即：

- **One Graph**：确定性教学政策约束的 Tutor Graph；
- **One Stream**：公开真实教学进度的 Learning Event Stream；
- **One Stage**：学生视觉中心唯一的 Scientific Learning Stage。

核心学习闭环是：

```text
Attempt / Prediction
→ Evidence
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

因此本调研的原则不是：

> “哪个项目功能最多，就抄哪个。”

而是：

> “哪个项目解决了 Quantum Agent 当前某个具体产品或工程问题，就抽取它的设计原则。”

---

# 3. 第一梯队：最值得直接研究

---

## 3.1 THU-MAIC / OpenMAIC

**GitHub**：https://github.com/THU-MAIC/OpenMAIC  
**定位**：Open Multi-Agent Interactive Classroom  
**License**：MIT  
**优先级**：S+

### 3.1.1 核心特点

OpenMAIC 的核心价值不只是“多 Agent”，而是把课堂本身抽象成一种可执行的交互 Runtime。

其公开能力包括：

- multi-agent classroom；
- slides / quiz / simulation / PBL 等多种 scene；
- whiteboard；
- AI teacher / AI classmates；
- TTS / ASR；
- Deep Interactive Mode；
- action-level playback；
- server-backed runtime storage；
- Postgres reference runtime；
- interactive HTML / simulation；
- course export；
- per-stage model routing；
- SDK / DSL / renderer。

OpenMAIC 在 2026 年的演进尤其值得注意：

```text
普通 AI 课程生成
    ↓
interactive classroom
    ↓
Deep Interactive Mode
    ↓
PBL
    ↓
durable runtime
    ↓
action-level playback
```

它已经从“生成教学内容”向“运行教学过程”演进。

### 3.1.2 最值得 Quantum Agent 吸收

#### A. Classroom is a runtime

Quantum Agent 应进一步坚持：

```text
Message
不是基本单位

Learning Episode
才是基本单位
```

一个 episode 有：

- durable state；
- ordered events；
- current scene；
- artifacts；
- required student action；
- tool execution；
- verification；
- completion condition。

#### B. Scene

OpenMAIC 的 scene 思想非常适合 Quantum Agent，但应重新解释为：

```text
Prediction Scene
Derivation Scene
Evidence Scene
Experiment Scene
Verification Scene
Teach Mode
Transfer Scene
Solo Scene
```

这些是 **presentation state**，不是 LangGraph 节点。

#### C. Action

Tutor 不只应该输出文本。

可以输出受控的 presentational actions，例如：

```text
focus_equation
highlight_term
open_source
mount_plot
mount_code
show_prediction
show_verification
focus_parameter
compare_prediction_result
```

但必须坚持：

> UI Action 可以由 Agent 提议；LearningPhase 绝不能由 Agent 自由推进。

#### D. Timeline / Playback

学生看：

```text
Predict → Understand → Test → Explain → Transfer
```

工程调试才看：

```text
Evidence Agent
Diagnosis Agent
Coding Agent
Sandbox
Verifier
```

### 3.1.3 不应该照搬

Competition Release 不应引入：

- AI classmates；
- 大量 avatar；
- TTS；
- 泛化课程生成；
- PPT 编辑器；
- 视频导出；
- 完整 PBL；
- 大型通用 Action Engine；
- 为展示“多智能体”而制造角色。

### 3.1.4 对 Quantum Agent 的结论

**ADOPT**

- Stage
- event runtime
- interactive artifacts
- action-level UI
- playback / event timeline

**ADAPT**

- classroom → scientific learning environment
- whiteboard → equation / plot / simulation / source interaction
- teacher actions → tutor presentational actions

**REJECT FOR NOW**

- AI classmates
- multimedia showmanship
- full content generation suite

---

## 3.2 HKUDS / DeepTutor

**GitHub**：https://github.com/HKUDS/DeepTutor  
**定位**：Agent-native Personalized Tutoring  
**License**：Apache-2.0  
**优先级**：S+

### 3.2.1 核心特点

DeepTutor 是目前最值得与 OpenMAIC 并列研究的项目之一。

当前设计中包含：

- unified agentic engine；
- Chat / Solve / Question / Deep Research / Visualize；
- RAG；
- code execution；
- GeoGebra；
- TutorBot；
- MCP；
- multi-user；
- CLI；
- restart-safe turn runtime；
- persistent tutor；
- 三层 Memory；
- inspectable memory graph；
- per-call cost tracking；
- tool sandbox。

### 3.2.2 三层 Memory 是最大启发

DeepTutor 的思路可以概括为：

```text
L1
raw interaction traces
      ↓
L2
surface-specific curated memory
      ↓
L3
cross-surface synthesized memory
```

这个结构和 Quantum Agent 的 Cognitive Mirror 天然互补。

Quantum Agent 可映射为：

```text
L1: Raw Learning Events
    attempt
    confidence
    tool events
    teach-back
    solo submission

L2: Concept Evidence
    prerequisite gap
    assistance level
    verified result
    transfer outcome

L3: Cognitive Mirror
    DEVELOPING
    DEMONSTRATED
    TRANSFER_READY
    calibration gap
```

关键点：

> Memory 不应该等价于“模型记得用户说过什么”。

而应该是：

> **可审计的学习证据层。**

### 3.2.3 Unified workspace

DeepTutor 允许多个能力共享 session：

```text
Chat
Solve
Question
Research
Visualize
```

Quantum Agent 可以对应：

```text
Explain
Derive
Experiment
Visualize
Teach
Transfer
Solo
```

但它们仍属于同一个 Learning Episode / learner history。

### 3.2.4 最值得吸收

**ADOPT**

- durable agent turn；
- restart-safe runtime；
- inspectable memory；
- session continuity；
- tools shared across one learning context。

**ADAPT**

- generic memory → evidence-grounded cognitive memory。

**不建议比赛前加入**

- autonomous personal TutorBot；
- 广泛 MCP ecosystem；
- Deep Research 作为主功能。

---

## 3.3 OpenTutor

**GitHub**：https://github.com/zijinz456/OpenTutor  
**定位**：Local-first block-based adaptive learning workspace  
**License**：MIT  
**优先级**：A+

### 3.3.1 核心特点

OpenTutor 的产品主张是：

> Workspace 会根据“你如何学习”进行重组。

其能力包括：

- PDF → structured learning workspace；
- notes；
- quiz；
- flashcards；
- adaptive tutor；
- FSRS；
- knowledge graph；
- cognitive load detection；
- local-first；
- self-hosted；
- 多模型 provider；
- Playwright E2E。

### 3.3.2 对 Quantum Agent 最大的启发：Adaptive Workspace

这非常直接地对应 Quantum Agent 当前前端问题。

错误设计：

```text
Chat
Evidence
Mirror
Trace
Knowledge Graph
Code
Plot
Simulation
```

全部同时占据屏幕。

更合理的是：

```text
当前是 Prediction
→ Stage 只突出 Prediction

当前是 Experiment
→ Stage 只突出 Simulation + Code + Plot

当前是 Teach-Back
→ Stage 只突出学生讲解和 AI 追问
```

这就是：

> **Learning state is UI state.**

### 3.3.3 最值得吸收

**ADOPT**

- block / scene-based workspace；
- dynamic center stage；
- context-dependent UI composition；
- 本地/自托管的产品思维。

**谨慎**

- FSRS、flashcard、quiz 等不要在当前比赛版加入。

---

## 3.4 Studyield

**GitHub**：https://github.com/studyield/studyield  
**定位**：All-in-one open-source AI learning platform  
**License**：AGPL-3.0  
**优先级**：A+

### 3.4.1 核心特点

Studyield 公开能力包括：

- exam cloning；
- multi-agent problem solver；
- knowledge graph；
- Teach-Back Evaluation；
- Deep Research；
- code sandbox；
- knowledge base；
- flashcards + SRS；
- quizzes；
- RAG chat；
- learning paths；
- analytics；
- streaming。

其多 Agent 求解器采用类似：

```text
Analysis
→ Solution
→ Verification
```

而 Teach-Back 明确作为独立学习评价能力存在。

### 3.4.2 对 Quantum Agent 的价值

它是非常好的**竞争参照物**。

因为它证明以下功能本身已经不再足够成为差异：

- multi-agent；
- knowledge graph；
- teach-back；
- code sandbox；
- RAG；
- learning path。

因此 Quantum Agent 不能把创新点写成：

> “我们有 Teach-Back。”

而应该写成：

> **Teach-Back 是受 LearningPhase 强制的状态迁移条件，不能靠 UI 按钮或模型建议跳过。**

类似地：

> Coding Agent 的结果必须经过 deterministic scientific verifier，不能把 Agent 自己的“验证”当真值。

### 3.4.3 应吸收什么

- 多 Agent solve 的 streaming UX；
- solve / verify 职责分离；
- Teach-Back 产品化；
- sandbox 作为学习工具。

### 3.4.4 不要吸收什么

- all-in-one feature explosion；
- exam/flashcard/SRS 等外围功能；
- “功能越多越完整”的产品逻辑。

---

# 4. 第二梯队：教学策略与学习者建模

---

## 4.1 GenMentor

**GitHub**：https://github.com/GeminiLight/gen-mentor  
**论文背景**：WWW 2025 Industry Track Oral  
**License**：CC0-1.0  
**优先级**：A

### 4.1.1 核心特点

GenMentor 是一个 goal-oriented ITS framework。

公开模块包括：

- Skill Gap Identification；
- Adaptive Learner Modeling；
- Personalized Content Delivery；
- goal-aligned tutoring。

它最重要的思想是：

```text
Student Goal
    ↓
Required Skills
    ↓
Skill Gap
    ↓
Learner Model
    ↓
Learning Path
    ↓
Teaching Content
```

### 4.1.2 对 Quantum Agent 的长期价值

Quantum Agent 当前已经把 **单个 Learning Episode** 做得很强。

GenMentor 提醒我们：

> Episode 之上还应存在 Goal。

例如：

```text
Goal: 学会定态微扰理论

├── 非简并一级能量修正
├── 波函数一级修正
├── 二级能量修正
├── 简并微扰
├── Stark effect
└── applicability / approximation
```

系统以后可以结合：

```text
Course KG
+
Learning Evidence
+
Goal
```

决定下一个 episode。

### 4.1.3 建议

**赛后 P1。**

当前比赛前不建议加入完整 Planner。

---

## 4.2 Tutor CoPilot

**GitHub**：https://github.com/rosewang2008/tutor-copilot  
**机构**：Stanford 相关研究团队  
**License**：Apache-2.0  
**优先级**：A

### 4.2.1 核心价值

Tutor CoPilot 不是让 AI 直接取代 tutor，而是：

```text
Human tutor
    +
AI pedagogical suggestion
```

其研究特别强调：

- guiding questions；
- expert-like tutoring strategies；
- 不直接给答案；
- 根据学生情况给 tutor 建议。

### 4.2.2 对 Quantum Agent 的启发

它说明：

> **Pedagogical Strategy 应该是一等对象。**

Quantum Agent 不应该只有：

```text
LLM prompt:
“请循循善诱”
```

而应该显式保留：

```text
ELICIT
FOCUS
MINIMAL_HINT
SOCRATIC_PROBE
CONTRAST
REPRESENTATION
EXPERIMENT
EXPLANATION
```

并记录：

```text
strategy
assistance_level
student_response
outcome
```

这样后面才能真正回答：

> 哪种 intervention 对这个概念、这个错误、这个学生有效？

### 4.2.3 适合吸收

- teaching strategy taxonomy；
- suggestion ≠ answer；
- strategy-level evaluation。

---

## 4.3 EduChat / EduChat-R1

**GitHub**：https://github.com/ECNU-ICALK/EduChat  
**机构**：华东师范大学 EduNLP / ICALK  
**优先级**：A-

### 4.3.1 核心特点

EduChat 从教育垂直模型路线出发。

EduChat-R1 提出：

> **Thinking before teaching**

其官方描述强调教师在教学前应先考虑：

```text
教什么？
怎么教？
学生现在是什么状态？
```

其“引导式教学”模板强调：

- 不直接给答案；
- 系统性提问；
- 针对认知漏洞追问；
- scaffolding；
- 反例；
- 元认知问题。

### 4.3.2 对 Quantum Agent 的启发

Quantum Agent 不需要改成教育专用模型项目。

更值得吸收的是：

```text
Diagnosis
→ Pedagogical Planning
→ Response
```

也就是：

> 先决定“教学意图”，再写“教学语言”。

### 4.3.3 关键区别

EduChat 更偏：

```text
Education-specific Model
```

Quantum Agent 应保持：

```text
Education-specific System
```

因此不要把 pedagogical correctness 全部寄托在模型 fine-tuning 上。

---

## 4.4 Pxplore

**GitHub**：https://github.com/Pxplore/pxplore-algo  
**定位**：Goal-driven learner state modeling + personalized path planning  
**优先级**：B+

### 4.4.1 核心特点

Pxplore 公开方案包括：

- learner profiling；
- learning path planning；
- hybrid retrieval；
- adaptive delivery；
- session management；
- cognitive level tracking；
- policy optimization / GRPO。

### 4.4.2 对 Quantum Agent 的价值

适合赛后研究：

```text
Course Graph
+
Learner Evidence
+
Goal
+
Pedagogical policy
```

怎样得到一个更长期的 learning path。

### 4.4.3 风险

Quantum Agent 应避免把：

- learning style；
- 人格型 profile；
- 模型主观印象

直接变成强事实。

当前的：

> **Learner State is derived, not asserted**

仍然应该优先于泛化 learner profiling。

---

# 5. 第三梯队：交互产品与教学机制

---

## 5.1 LearnHouse

**GitHub**：https://github.com/learnhouse/learnhouse  
**定位**：Next-generation open-source learning platform  
**License**：AGPL-3.0  
**优先级**：A（前端/产品）

### 5.1.1 值得看的不是 Agent，而是成熟教育产品

公开能力包括：

- courses；
- block editor；
- assignments；
- discussions；
- analytics；
- AI playgrounds；
- simulations / diagrams；
- code execution；
- auto-grading；
- collaborative whiteboards。

其工程栈也具有很高参考价值：

```text
React / Next-style web
Python / FastAPI
database
real-time collaboration
```

### 5.1.2 最值得 Quantum Agent 前端借鉴

- 学术型内容层次；
- editor / canvas；
- code playground；
- simulation surface；
- empty state；
- loading；
- navigation；
- typography；
- responsive layout；
- 教育产品而不是 admin dashboard 的视觉语言。

### 5.1.3 建议

让前端 subagent 把 LearnHouse 当作：

> **product polish reference**

而不是 architecture reference。

---

## 5.2 martius-lab / ai-tutor

**GitHub**：https://github.com/martius-lab/ai-tutor  
**机构**：University of Tübingen 相关团队  
**定位**：AI tool for learning by teaching  
**License**：AGPL-3.0  
**优先级**：A

### 5.2.1 核心机制

学生不是简单向 AI 提问，而是：

```text
Student explains
      ↓
AI asks / hints
      ↓
Student improves explanation
```

核心思想：

> **Learning by Teaching**

### 5.2.2 对 Quantum Agent 的直接价值

Quantum Agent 的 Teach-Back 不应只是：

> “请再解释一遍。”

应升级为真正的：

## Teach Mode

```text
你现在是老师。
Quantum Agent 是你的学生。
```

AI 的行为限制为：

- 追问；
- 要求澄清；
- 请求例子；
- 指出矛盾；
- 要求换一种表示。

AI 不应：

- 重新讲答案；
- 直接替学生修正完整推导；
- 学生一卡住就结束 Teach-Back。

### 5.2.3 这是当前最值得直接落地的教学改进之一

因为它：

- 改动范围可控；
- 产品辨识度高；
- 与当前 Teach-Back 基础完全兼容；
- 可以直接进入比赛 demo。

---

## 5.3 Socratic Tutor

**GitHub**：https://github.com/nealdoran/socratic-tutor  
**定位**：RAG-grounded Socratic tutor  
**优先级**：B+

### 5.3.1 核心特点

该项目把苏格拉底式教学和课程 source grounding 绑定：

```text
Student thesis
    ↓
Retrieve course text
    ↓
Ask one grounded question
```

其核心不是“RAG”，而是：

> 每一个追问都应该和课程证据有关系。

### 5.3.2 Quantum Agent 可吸收

Evidence Agent 不只是给 citation。

它还可以为 Tutor 提供：

```text
what can be safely challenged
what contrast can be introduced
which equation/source can be pointed to
```

但仍由 Pedagogical Policy 决定是否使用。

---

## 5.4 VirtuTA

**GitHub**：https://github.com/KayvanShah1/VirtuTA  
**定位**：University course virtual teaching assistant  
**License**：MIT  
**优先级**：B

### 5.4.1 核心价值

VirtuTA 更接近传统大学课程 TA：

- conceptual queries；
- logistical course queries；
- agentic workflow；
- RAG；
- university course deployment；
- Piazza integration。

### 5.4.2 对 Quantum Agent 的启发

它说明大学课程 Agent 可以真正进入：

```text
course communication environment
```

赛后如果 Quantum Agent 要推广，可以考虑：

- Moodle / Blackboard / Canvas；
- Piazza；
- 学校教学平台；
- 微信/飞书入口；

但 Competition Release 不应扩大到这些渠道。

---

# 6. 补充项目：OpenMAIC-Project

**GitHub**：https://github.com/THU-MAIC/OpenMAIC-Project  
**定位**：AI-assisted Project-Based Learning desktop workspace  
**License**：MIT

虽然不是当前量子物理答疑的直接参考，但它有一个很强的模式：

```text
chat
code
file
terminal
browser
sandbox
```

整合在一个学习工作台中。

这对 Quantum Agent 的“科学计算模式”很有启发：

```text
Tutor narrative
+
Equation
+
Code
+
Plot
+
Source
+
Verifier
```

应当在一个统一 Stage 内组织，而不是拆成很多互相竞争的面板。

---

# 7. 横向对比

| 项目 | 最强项 | 学习状态 | 交互工作台 | 多 Agent | 工具/代码 | RAG/证据 | Teach-Back | 对 QA 价值 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| OpenMAIC | Interactive Classroom Runtime | 中 | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★ | ★★ | ★★★★★ |
| DeepTutor | Agent-native + Memory | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★ | ★★★★★ |
| OpenTutor | Adaptive Workspace | ★★★★☆ | ★★★★★ | ★★★ | ★★ | ★★★★ | ★★★ | ★★★★★ |
| Studyield | AI learning toolbox | ★★★ | ★★★★ | ★★★★☆ | ★★★★☆ | ★★★★ | ★★★★☆ | ★★★★☆ |
| GenMentor | Goal-oriented ITS | ★★★★★ | ★★ | ★★★★★ | ★ | ★★ | ★★ | ★★★★☆ |
| Tutor CoPilot | Pedagogical Strategy | ★★★★ | ★ | ★★ | ★ | ★ | ★★★ | ★★★★☆ |
| EduChat-R1 | Education-specific reasoning | ★★★ | ★★ | ★★ | ★★ | ★★ | ★★★ | ★★★★ |
| LearnHouse | Mature education product UX | ★★ | ★★★★★ | ★ | ★★★★★ | ★★★ | ★ | ★★★★☆ |
| martius ai-tutor | Learning by Teaching | ★★★★ | ★★★ | ★★ | ★ | ★★ | ★★★★★ | ★★★★★ |
| Socratic Tutor | grounded questioning | ★★ | ★★ | ★ | ★ | ★★★★★ | ★★ | ★★★ |
| VirtuTA | university TA integration | ★★ | ★★ | ★★★ | ★ | ★★★★ | ★ | ★★★ |
| Pxplore | learner modeling / planning | ★★★★★ | ★★ | ★★ | ★ | ★★★ | ★ | ★★★★ |

> 星级是本报告相对于 Quantum Agent 需求的主观技术参考价值，不代表项目综合质量排名。

---

# 8. 跨项目共同趋势

调研这些项目后，可以看到优秀 AI 教学系统正在从以下旧范式：

```text
Question
→ Chatbot
→ Answer
```

转向：

```text
Learning Context
→ Learner State
→ Pedagogical Decision
→ Agent Action
→ Tool / Environment
→ Student Action
→ Evidence
→ Next Decision
```

其中最值得 Quantum Agent 坚持的趋势有七个。

---

## 8.1 Chat 不再是产品本体

优秀项目越来越把 Chat 降级为一种 interaction surface。

真正核心是：

```text
Workspace
Scene
Artifact
Timeline
State
```

因此 Quantum Agent 的主页面必须继续围绕：

> **Scientific Learning Stage**

而不是 Chat Thread。

---

## 8.2 Agent 开始“行动”，而不仅是“说话”

OpenMAIC、DeepTutor、LearnHouse 等都已经显示：

```text
Agent
→ tool
→ artifact
→ interactive state
```

是明显趋势。

Quantum Agent 最适合的动作不是 avatar 或 TTS，而是：

```text
highlight equation
open course source
run code
change parameter
show plot
verify conservation
compare prediction
```

---

## 8.3 持久状态比长 Prompt 更重要

DeepTutor、OpenMAIC runtime、GenMentor、Pxplore 都指向：

```text
session state
memory
learner model
events
```

而不是只把历史消息无限塞进 context。

Quantum Agent 应坚持：

```text
durable LearningPhase
+
LearningEvent
+
LearningEvidence
```

---

## 8.4 教学策略需要显式化

Tutor CoPilot、EduChat、GenMentor、martius ai-tutor 都表明：

```text
“怎么教”
```

不应隐含在一段 system prompt 中。

应成为可记录、可评估、可约束的对象。

---

## 8.5 Grounding 只是起点

RAG 已经是普遍能力。

真正更高级的问题是：

```text
retrieved evidence
→ diagnosis
→ pedagogical use
```

而不是：

```text
retrieved evidence
→ answer
```

这正是 Quantum Agent 应继续强化的差异。

---

## 8.6 学习完成需要行为证据

Teach-Back、transfer、practice、learner state 越来越普遍。

Quantum Agent 可以进一步坚持：

> “看到了 Teach-Back 任务” ≠ “Teach-Back Verified”

> “显示了 Transfer” ≠ “Transfer Verified”

> “AI 说掌握了” ≠ “Learning Evidence 证明掌握了”

---

## 8.7 科学教育需要真实工具

通用 AI Tutor 最容易做到的是语言。

Quantum Agent 最难复制的壁垒应该是：

```text
Prediction
→ task-specific code
→ isolated execution
→ domain verifier
→ scientific artifact
→ student explanation
```

这是一个明显强于普通 AI Tutor 的科学教育闭环。

---

# 9. Quantum Agent 应该直接采用的设计

---

## 9.1 P0：比赛版立即吸收

### A. OpenMAIC → Stage / Scene / Event

实施：

```text
Scientific Learning Stage
+
Learning Scene
+
Learning Event Stream
```

### B. OpenTutor → Adaptive Workspace

当前 phase 决定中央 UI。

禁止所有功能同时出现。

### C. DeepTutor → Inspectable Learning Memory

把：

```text
event
→ evidence
→ mirror
```

串起来。

### D. martius ai-tutor → Teach Mode

把 Teach-Back 升级成学生真的“教 AI”。

### E. Studyield → Agent / Verification 的清晰分工

在 UI 中突出：

```text
Coding Agent generated
Sandbox executed
Scientific Verifier PASS
```

而不是只给最后 Plot。

---

## 9.2 P1：Freeze 后再做

### GenMentor

加入：

```text
Learning Goal
→ Skill Gap
→ Episode Planning
```

### Pxplore

探索：

```text
learning evidence
→ next task policy
```

### Tutor CoPilot

建立 intervention-level evaluation。

---

## 9.3 P2：赛后长期扩展

可以考虑：

- PBL；
- learning plan；
- delayed retrieval scheduler；
- FSRS；
- course integrations；
- long-term TutorBot；
- collaborative learning；
- teacher dashboard；
- automated content authoring。

---

# 10. 明确不要复制的设计

为了避免项目再次失控，以下能力即使其他优秀项目拥有，也不应自动进入 Quantum Agent。

---

## 10.1 不做 AI classmates

OpenMAIC 的 AI classmates 很适合 immersive classroom。

但 Quantum Agent 的学生端应坚持：

> 一个连贯 Tutor Persona，后台多 Agent。

否则会：

- 增加认知负担；
- 破坏中央 Stage；
- 让多 Agent 变成表演。

---

## 10.2 不做“所有学习工具的集合”

Studyield / LearnHouse 功能非常丰富。

Quantum Agent 当前不应追求：

```text
flashcards
quiz
exam clone
notes
planner
forum
certificate
```

这些都会稀释：

> Learning-Native Scientific Tutor

---

## 10.3 不让 LLM 维护权威学习状态

其他项目可能更自由地由 Agent 更新 profile。

Quantum Agent 应继续坚持：

```text
LLM proposes
Policy decides
Tools verify
State persists
```

禁止模型直接：

```text
mark_mastered
transfer_verified
complete_episode
unlock_solo
```

---

## 10.4 不使用虚假精准 mastery %

不做：

```text
Mastery = 87.23%
```

优先：

```text
DEVELOPING

✓ Teach-Back verified
✓ standard problem solved
△ transfer required L3 hint
✗ no solo evidence
```

---

## 10.5 不用动画掩盖真实延迟

参考 OpenMAIC 的 streaming / runtime 思路，但：

- 不能 fake progress；
- 不能 fake percentage；
- 不能用动画伪造 Agent 已完成某一步。

只显示真实 LearningEvent。

---

# 11. 推荐的 Quantum Agent 最终产品模型

综合本轮调研，推荐产品模型为：

```text
                   STUDENT
                      │
                      ▼
        ┌──────────────────────────┐
        │ SCIENTIFIC LEARNING STAGE│
        └─────────────┬────────────┘
                      │
               Learning Events
                      │
                      ▼
        ┌──────────────────────────┐
        │ Learning-Native TutorGraph│
        │                          │
        │ Commitment               │
        │ Evidence                 │
        │ Diagnosis                │
        │ Pedagogical Policy       │
        │ Scientific Action        │
        │ Reconstruction           │
        │ Teach / Transfer / Solo  │
        └─────────────┬────────────┘
                      │
       ┌──────────────┼───────────────┐
       ▼              ▼               ▼
   Tutor Agent    Coding Agent   Evidence Agent
                      │
                   Sandbox
                      │
                   Verifier
                      │
                      ▼
               Learning Evidence
                      │
                      ▼
               Cognitive Mirror
```

其外部参考来源可以概括为：

```text
OpenMAIC
→ Interaction Runtime

DeepTutor
→ Durable Memory

OpenTutor
→ Adaptive Workspace

martius AI Tutor
→ Learning by Teaching

GenMentor
→ Goal-oriented Learner Model

Tutor CoPilot / EduChat
→ Explicit Pedagogy

Studyield
→ Integrated Solve / Verify / Teach-back

LearnHouse
→ Product Polish
```

但最终的控制原则仍然是 Quantum Agent 自己的：

```text
Pedagogy defines the constraints.
Agents provide intelligence.
Tools provide truth.
Student actions provide evidence.
```

---

# 12. 对竞赛故事的直接启发

这些项目的存在意味着，比赛材料中不应把以下内容单独当作创新：

```text
RAG
多 Agent
Knowledge Graph
Teach-Back
Code Sandbox
Personalization
```

因为这些已经在多个开源教育项目中出现。

Quantum Agent 更强的创新叙事应是：

## 12.1 Learning-Native workflow

```text
学生必须先生成
→ 系统诊断
→ 最小干预
→ 重构
→ 迁移
→ Solo
```

而不是把教学策略写在 Prompt 里。

## 12.2 Scientific truth boundary

```text
LLM
不是科学裁判

Verifier
才决定 PASS / FAIL / INCONCLUSIVE
```

## 12.3 AI-removable competence

目标不是：

```text
AI helped the student solve it
```

而是：

```text
student can solve a related new problem without AI
```

## 12.4 One Graph · One Stream · One Stage

这是非常适合作为比赛技术叙事的高层概括：

```text
One Graph
→ teaching control

One Stream
→ observable runtime

One Stage
→ focused learning UX
```

---

# 13. 推荐给 Claude Code 的参考优先级

如果后续让多个 subagent 研究这些项目，建议分工如下。

### Subagent A — OpenMAIC

重点：

```text
runtime
scene
event
streaming
playback
action
workspace
```

### Subagent B — DeepTutor

重点：

```text
memory
durable turn
session
tool runtime
inspectability
```

### Subagent C — OpenTutor + LearnHouse

重点：

```text
workspace
layout
adaptive UI
content hierarchy
artifacts
scientific playground
```

### Subagent D — GenMentor + Tutor CoPilot + EduChat

重点：

```text
pedagogical strategy
learner modeling
goal
intervention
```

### Subagent E — Studyield + martius ai-tutor

重点：

```text
teach-back
verification
learning by teaching
problem-solving workflow
```

Lead Agent 必须建立统一的：

```text
ADOPT
ADAPT
REJECT
```

矩阵。

任何新实现必须回答：

> “它解决 Quantum Agent 当前哪个具体问题？”

回答不了，就不进入 Competition Release。

---

# 14. 开源许可证与复用注意事项

当前调研中可确认：

| 项目 | License / 使用提示 |
|---|---|
| OpenMAIC | MIT |
| DeepTutor | Apache-2.0 |
| OpenTutor | MIT |
| Studyield | AGPL-3.0 |
| GenMentor | CC0-1.0 |
| LearnHouse | AGPL-3.0 |
| martius-lab/ai-tutor | AGPL-3.0 |
| Tutor CoPilot | Apache-2.0 |
| VirtuTA | MIT |
| EduChat | README 明确包含研究用途/使用限制，应单独核查完整协议 |

重要原则：

> **借鉴 architecture / interaction principle 与直接复制代码是两件不同的事。**

对于 AGPL 项目，若直接复制或形成衍生代码，应在正式复用前进行许可证兼容性检查。

对于 Quantum Agent 当前竞赛开发，更建议：

```text
study ideas
→ independent implementation
```

而不是直接拷贝外部代码。

---

# 15. 最终建议

在所有项目里，我建议 Quantum Agent 团队长期重点跟踪 6 个：

```text
1. OpenMAIC
2. DeepTutor
3. OpenTutor
4. Studyield
5. GenMentor
6. martius-lab/ai-tutor
```

其中比赛前实际吸收顺序：

```text
OpenMAIC
↓
OpenTutor
↓
DeepTutor
↓
martius AI Tutor
↓
Studyield
```

比赛后：

```text
GenMentor
+
Tutor CoPilot
+
Pxplore
```

最重要的结论是：

> **这些项目可以帮助 Quantum Agent 变得更完整，但不能替代 Quantum Agent 自己的核心思想。**

真正应该保留下来的独特中心是：

\[
\boxed{
\text{Student generation}
\rightarrow
\text{Diagnosis}
\rightarrow
\text{Minimal intervention}
\rightarrow
\text{Scientific verification}
\rightarrow
\text{Reconstruction}
\rightarrow
\text{Unaided transfer}
}
\]

以及：

\[
\boxed{
\text{Learner State is derived from evidence, not asserted by AI}
}
\]

如果这个中心不丢，再吸收 OpenMAIC 的交互、DeepTutor 的 Memory、OpenTutor 的 Workspace、martius 的 Learning-by-Teaching，Quantum Agent 会明显比“功能很多的教育 Agent”更有自己的产品范式。

---

# 16. 主要参考链接

## 核心项目

- OpenMAIC  
  https://github.com/THU-MAIC/OpenMAIC

- OpenMAIC-Project  
  https://github.com/THU-MAIC/OpenMAIC-Project

- DeepTutor  
  https://github.com/HKUDS/DeepTutor

- OpenTutor  
  https://github.com/zijinz456/OpenTutor

- Studyield  
  https://github.com/studyield/studyield

- GenMentor  
  https://github.com/GeminiLight/gen-mentor

- LearnHouse  
  https://github.com/learnhouse/learnhouse

- martius-lab AI Tutor  
  https://github.com/martius-lab/ai-tutor

- EduChat  
  https://github.com/ECNU-ICALK/EduChat

- Tutor CoPilot  
  https://github.com/rosewang2008/tutor-copilot

- Pxplore  
  https://github.com/Pxplore/pxplore-algo

- Socratic Tutor  
  https://github.com/nealdoran/socratic-tutor

- VirtuTA  
  https://github.com/KayvanShah1/VirtuTA

## 延伸索引

- THU-MAIC / Awesome-AI-Era-Edu  
  https://github.com/THU-MAIC/Awesome-AI-Era-Edu

---

**调研结论关键词**

```text
Learning Runtime
Scientific Stage
Adaptive Workspace
Durable Memory
Explicit Pedagogy
Learning by Teaching
Evidence Grounding
Tool Verification
Unaided Transfer
```
