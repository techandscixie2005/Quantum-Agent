# QUANTUM AGENT

## PRD V3.1 — Competition Freeze Edition

**面向大学量子物理深度自学的 Learning-Native 多智能体系统**  
**目标版本：一〇七杯智能体赛道 Competition Release**  
**框架冻结日期：2026-08-28**  
**比赛截止：2026-09-06 23:59**

> 本 PRD 自冻结后作为比赛版本的权威执行规范。  
> 在提交前，优先级只有一个：**把已经确定的完整学习流程真实跑通、稳定跑通、可演示地跑通。**
>
> 教学方法本身仍是 open question；比赛阶段不再持续改写教育理论框架，而是在一个合理、可解释、可验证的 Learning-Native 框架下完成工程闭环。

---

# 1. 产品定义

Quantum Agent 不是课程 RAG 聊天机器人，也不是拍照搜题或答案生成器。

它面向学生本人，目标是把一次学习从：

```text
Question → Answer
```

改造成：

```text
Connect
→ Understand Input
→ Commit / Attempt
→ Retrieve Evidence
→ Diagnose
→ Choose Intervention
→ Act / Compute
→ Verify
→ Reconstruct
→ Transfer
→ Update Learning Evidence
```

核心目标不是让学生“在 AI 帮助下做对”，而是逐步提高：

```text
独立作答能力
迁移能力
自我解释能力
元认知校准
低提示依赖
科学验证能力
```

比赛版本不声称已经找到“最优 AI 教学法”。

只要求：

> **教学决策有学习科学依据；每一步有明确教育意义；完整流程能够真实运行。**

---

# 2. Competition Freeze：从现在开始不再扩张范围

当前项目已有：

- Python / FastAPI 权威后端；
- LangGraph Workflow；
- Evidence Agent；
- Diagnosis Agent；
- 多模态解析；
- 课程知识图谱；
- Scientific Verifier；
- Commitment Gate；
- Teach-Back；
- Transfer / Solo；
- Cognitive Mirror；
- PostgreSQL / Neo4j / Redis；
- 真实 Live Golden Loop。

因此比赛前固定执行：

```text
Preserve → Integrate → Complete → Optimize → Demonstrate
```

禁止：

- 为了显得“多智能体”继续增加无必要 Agent；
- 重新设计整套教学方法论；
- 推翻当前 Python / LangGraph 后端；
- 用 mock 数据替代正式演示；
- 为新功能破坏已经通过的 Golden Loop；
- 在 P0 流程未全绿前开发大量 P1/P2 功能。

---

# 3. 用户入口：词元计划 / 一〇七杯 API Login

## 3.1 前端入口

首次进入系统显示：

```text
Quantum Agent

连接中国科大
「词元计划 / 一〇七杯」模型服务

[ API Key __________________ ]

[ 连接并进入学习空间 ]
```

它是 **Model Credential Login**，不是统一身份认证的替代。

连接成功后进入 `/agent`。

右上角只显示：

```text
● 模型服务已连接
```

不得再次展示完整 API Key。

## 3.2 模型入口

统一经过：

```text
https://api.llm.ustc.edu.cn/v1/chat/completions
Authorization: Bearer <user key>
```

所有 Agent 必须通过统一：

```text
ModelGateway
    ↓
ModelRouter
```

调用模型。

不得在业务代码中散落 HTTP / SDK 调用。

内部根据任务自动路由：

```text
复杂诊断 / 教学推理 → 强推理模型

短反馈 / 分类 / Gate → 快速模型

程序生成 → Coding-oriented model

图片 / 手写 / 图表 → multimodal-capable model
```

具体模型必须通过 capability probe 与实际 benchmark 决定，而不是写死在 Agent 中。

学生不需要手动选择模型。

## 3.3 API Key 安全

允许前端输入 API Key，但 Key 只能经历：

```text
Browser
→ HTTPS POST
→ backend credential endpoint
→ validate / probe
→ server-side session vault
→ HttpOnly session reference
```

硬约束：

- 不写 `localStorage`；
- 不写日志；
- 不进入 Agent trace；
- 不回传前端；
- 不提交 Git；
- logout / session expiration 后删除；
- 服务端使用短生命周期加密 Redis / memory vault；
- 原 `USTC_API` 环境变量保留为开发和部署 fallback。

---

# 4. 冻结后的 Learning-Native 主流程

所有普通教学 Turn 都由统一的 **Cognitive Governor** 决定下一步。

学生始终面对一个连贯的 AI Tutor，多个 Agent 只在后台协作。

```text
Student Input
   │
   ├─ Text
   ├─ Image / Handwriting
   └─ PDF / Document
   ↓
Perception / Document Agent
   ↓
Cognitive Commitment Gate
   ↓
Evidence Agent
   ↓
Diagnosis Agent
   ↓
Cognitive Governor
   ↓
选择 ONE 教学动作
   ├─ Minimal Hint
   ├─ Contrast / Counterexample
   ├─ Explanation
   ├─ Representation Translation
   ├─ Simulation / Computation
   ├─ Teach-Back
   └─ Transfer / Solo
   ↓
Scientific Verification
   ↓
Learner Evidence
   ↓
Cognitive Mirror
```

## 固定教育原则

### 1. Learner generates before AI completes

适合学生自己尝试的问题，先要求：

- 预测；
- 一步推导；
- 判断；
- 图像；
- 物理解释；
- confidence。

再提供支持。

### 2. Minimum necessary assistance

默认给予最小必要帮助。

只有学生持续失败时才逐步增加提示。

### 3. Explanation ≠ Mastery

重要概念不能以“学生看完解释”为结束。

必须至少进入一次：

```text
Teach-Back
或
Reconstruction
或
Transfer
```

### 4. Verification outranks fluent language

数学、数值、代码结果必须由真实工具或测试验证。

### 5. AI assistance must fade

最终应该进入：

```text
AI-assisted
→ reduced assistance
→ Solo
→ Transfer
```

### 6. Confidence is learning evidence

同时记录：

```text
student answer
student confidence
actual performance
hint dependency
later performance
```

用于 Cognitive Mirror。

这些原则在比赛版本冻结，不再频繁修改。

---

# 5. 多智能体职责：少而清楚

| 模块 | 核心职责 | 类型 |
|---|---|---|
| Cognitive Governor | 决定下一教学动作 | Policy + LLM proposal |
| Evidence Agent | 获取课程证据与出处 | Agent |
| Diagnosis Agent | 找第一关键错误和误区 | Agent |
| Tutor Agent | Hint / Explain / Contrast / Teach-Back / Transfer | Agent |
| **Coding Agent** | 为当前计算任务现场编写程序 | **Agent / P0** |
| Perception / Document Agent | 图像、手写、文档理解 | 按需 Agent |
| Scientific Verifier | 数学、数值、程序验证 | Deterministic Tool |
| Security / Sandbox / RBAC | 权限和执行安全 | Deterministic System |

原则：

> **Agent 是职责，不是数量。**

---

# 6. P0 核心：真正的 Coding Agent

这是比赛版本必须强化的 Agentic 能力。

当教学过程需要：

- 数值计算；
- 仿真；
- 绘图；
- 参数扫描；
- 数学验证；

主系统**不能直接选择预先写好的计算程序返回答案**。

必须经过：

```text
Pedagogical Task
        ↓
Coding Agent
        ↓
理解计算目标
        ↓
现场生成 task-specific Python
        ↓
Static Safety Check
        ↓
Sandbox Execution
        ↓
stdout / data / figure / error
        ↓
Verifier / Tests
        ↓
失败？
 ├─ Yes → Coding Agent repair
 └─ No
        ↓
Artifact
        ↓
Tutor
        ↓
Student compares prediction with result
```

## 6.1 Coding Agent 的定义

Coding Agent 可以使用：

```text
Python
NumPy
SciPy
SymPy
Matplotlib
QuTiP
```

等白名单科学库。

但：

> **针对当前教学问题的计算程序必须由 Coding Agent 现场生成。**

允许使用成熟科学库。

不允许 orchestrator 偷偷调用：

```text
solve_tunneling()
solve_harmonic_oscillator()
solve_stark_effect()
```

这类预制答案函数，再把结果伪装成 Agent 完成。

## 6.2 执行安全

生成代码必须：

- 禁止网络；
- 禁止任意 shell；
- 文件系统隔离；
- import 白名单；
- CPU 限制；
- RAM 限制；
- wall-time 限制；
- 保存 code artifact；
- 保存 stdout / stderr；
- 保存 figure / data；
- 保存 verifier result。

Coding Agent 自动 repair 最多两次。

仍然失败时：

> 明确告诉学生计算失败，不伪造结果。

## 6.3 Verifier

可检查：

```text
Normalization
Probability range
Conservation law
Dimensions / units
Boundary conditions
Numerical stability
pytest assertions
```

LLM 不得把：

```text
failed
inconclusive
timeout
```

改写成“已经验证”。

---

# 7. 多模态必须服务于认知过程

多模态不是为了“支持上传图片”。

而是为了让学生直接提交自己的认知产物。

核心场景：

```text
手写推导
→ OCR / Vision
→ step structure
→ first consequential error
```

```text
学生画的曲线
→ perception
→ prediction representation
→ 与真实仿真比较
```

```text
PDF / 课件
→ page-aware retrieval
→ Evidence
→ original page
```

```text
题目截图
→ structured problem
→ same Learning Loop
```

Perception Agent 只负责：

> “看见了什么”。

科学正确性仍由 Diagnosis / Verifier 判断。

---

# 8. 前端产品结构

比赛版本只保留一个核心学生空间：

```text
/agent
```

结构：

```text
┌──────────────────────────────────┐
│ Quantum Agent     ● Model Online │
├────────┬─────────────────┬───────┤
│ Course │ Learning Space  │Evidence│
│ Map    │                 │Mirror │
│        │                 │Trace  │
├────────┴─────────────────┴───────┤
│ Text | Image | PDF | Screenshot │
└──────────────────────────────────┘
```

## Main Workspace

显示：

- 对话；
- Commitment Card；
- Prediction Card；
- Equation；
- Plot；
- Code Artifact；
- Teach-Back；
- Transfer；
- Solo。

## Right Panel

三种视图：

```text
Evidence
Cognitive Mirror
Agent Trace
```

Agent Trace 只展示：

```text
Evidence Agent
↓
Diagnosis Agent
↓
Tutor / Coding Agent
↓
Verifier
```

及耗时、工具、结果摘要。

不展示隐藏思维链。

## Coding UX

学生应能看到：

```text
Planning
→ Writing code
→ Running
→ Verifying
→ Result
```

以及最终生成的代码。

这样评委能明确看到：

> 这是 Agent 在完成一个计算任务，而不是后端调用固定函数。

---

# 9. Golden Demo：只讲一个完整故事

比赛五分钟不展示“功能菜单”。

只展示一次完整学习。

继续推荐：

# Quantum Tunneling

完整故事：

```text
1. 用户输入一〇七杯 API Key
   ↓
2. 模型连接成功
   ↓
3. 学生提出隧穿问题 / 上传题目
   ↓
4. Commitment Gate
   预测：势垒变宽后透射率怎样变化？
   Confidence = 80%
   ↓
5. Evidence Agent
   从课程资料检索证据
   ↓
6. Diagnosis Agent
   识别学生误区
   ↓
7. Tutor
   只给最小提示
   ↓
8. 学生修改预测
   ↓
9. 需要数值实验
   ↓
10. Coding Agent 现场写 Python
   ↓
11. Sandbox 真执行
   ↓
12. Verifier 检查
   ↓
13. 前端显示：
   Prediction vs Simulation
   ↓
14. 学生解释
   为什么 E < V0 仍然存在透射
   ↓
15. Teach-Back
   ↓
16. 双势垒 / 参数变化 Transfer
   ↓
17. Solo Mode
   ↓
18. Cognitive Mirror 更新
   ↓
19. 打开 Agent Trace
```

这一条流程同时证明：

```text
Learning-Native
Knowledge Graph / RAG
Multimodal
Multi-Agent Workflow
Model Routing
Coding Agent
Sandbox
Scientific Verification
Learning Evidence
Persistent State
Real E2E
```

---

# 10. P0 / P1 / P2

## P0 — 9 月 6 日前必须完成

1. API Login 与 credential security；
2. 所有 Agent 使用 session 中的词元计划 API；
3. Cognitive Governor 主链稳定；
4. Coding Agent → Sandbox → Verifier → Artifact；
5. 文本 / 图片 / PDF 真实输入；
6. Evidence → Diagnosis → Intervention → Teach-Back → Transfer → Mirror；
7. Golden Demo 完全无 mock；
8. timeout / model failure / code failure 有 fallback；
9. latency 优化；
10. Docker / README / 演示材料可复现。

## P1 — P0 全绿以后才允许开发

- Learner-generated Knowledge Graph；
- Contrastive Concept Clinic；
- Interactive Cognitive Canvas；
- Delayed Retrieval；
- 更细粒度 adaptive intervention。

## P2 — 比赛以后

- Cognitive Digital Twin；
- 基于真实数据优化 Intervention Policy；
- Contextual Bandit / Sequential Policy；
- AI-mediated Peer Learning；
- 正式教育实验与 RCT。

---

# 11. 开发顺序

从本 PRD 冻结后严格按照：

```text
Phase 1
API Login + Credential Security

Phase 2
Coding Agent + Sandbox + Verifier

Phase 3
Coding Agent 接入现有 LangGraph

Phase 4
Golden Demo 完整 Live E2E

Phase 5
Latency + Fallback + Frontend Polish

Phase 6
Regression + Deployment + Competition Materials
```

任何新需求首先问：

> **它是否直接提高 9 月 6 日前 Golden Loop 的完整性、教育意义、可靠性或演示竞争力？**

如果答案不是明确的 Yes：

> 比赛后再做。

---

# 12. Definition of Done

Competition Release 必须满足：

- [ ] 首次进入能够输入词元计划 / 一〇七杯 API Key；
- [ ] API Key 可真实连接学校模型服务；
- [ ] Key 不进入日志、localStorage、trace、Git；
- [ ] ModelGateway 使用 session credential；
- [ ] Text live E2E；
- [ ] Image live E2E；
- [ ] PDF live E2E；
- [ ] Commitment Gate 真实运行；
- [ ] Evidence Agent 真实运行；
- [ ] Diagnosis Agent 真实运行；
- [ ] Tutor Intervention 真实运行；
- [ ] Teach-Back 真实运行；
- [ ] Transfer / Solo 真实运行；
- [ ] Cognitive Mirror 真实更新；
- [ ] 计算任务必经 Coding Agent；
- [ ] Coding Agent 现场生成代码；
- [ ] Sandbox 真实执行；
- [ ] Verifier / tests 真实验证；
- [ ] 代码、图、数据返回前端成为 Artifact；
- [ ] Learning Evidence 写入 PostgreSQL；
- [ ] Agent Trace 可审计；
- [ ] Golden Demo 核心链路无 mock；
- [ ] live USTC model E2E 通过；
- [ ] Playwright Golden Demo 一键通过；
- [ ] pytest 全绿；
- [ ] Ruff 全绿；
- [ ] mypy 全绿；
- [ ] TypeScript strict 全绿；
- [ ] production build 全绿；
- [ ] secret scan 全绿；
- [ ] Docker / 部署说明可由新环境复现；
- [ ] 五分钟演示能够从 API Login 开始完整跑完。

---

# 13. 比赛竞争力表达

Quantum Agent 不应宣传：

> “我们用了很多 Agent。”

而应该宣传：

> **我们把学习科学约束写进了 Agent Workflow。**

学生不是向 AI 索取答案。

而是在：

```text
课程证据
+
认知诊断
+
教学策略
+
Coding Agent
+
科学验证
+
Teach-Back
+
Transfer / Solo
+
Learning Evidence
```

构成的闭环中完成真实学习。

与通用 Study Mode 相比，重点强调：

```text
Course-bounded Knowledge
Page-level Evidence
Auditable Multi-Agent Workflow
Learner Cognitive Evidence
Agent-generated Scientific Computation
Real Sandbox + Verifier
AI Assistance → Solo / Transfer
Quantum-specific Multimodal Workspace
```

最终产品命题：

> **不是让 AI 更快地替学生完成问题，而是让 AI 编排学生真正完成一次学习。**