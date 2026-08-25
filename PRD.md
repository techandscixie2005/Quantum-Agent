# QUANTUM AGENT

## 产品需求文档 PRD · V3.0 — Learning-Native Edition

**面向大学量子物理深度自学的可信、多模态、Learning-Native 教学智能体系统**

| 项目 | 定义 |
|---|---|
| 文档状态 | V3.0 — Learning-Native 产品升级与最终工程规范 |
| 权威基线 | PRD V2.1 + `progress.md` + 当前 Python/LangGraph 实现 |
| 产品对象 | 以大学量子物理学生为核心学习者 |
| 首发场景 | 中国科学技术大学《量子物理》课程 |
| 核心开发 | 1 名核心开发者，课程教师提供内容审核 |
| 比赛截止 | 2026-09-06 |
| API 网关 | `https://api.llm.ustc.edu.cn/v1/chat/completions` |
| API Key | 环境变量 `USTC_API`，仅允许服务端读取 |
| 产品原则 | **Learning-native · Learner-first · Course-bounded · Workflow-first · Tool-verified · Evidence-grounded · Productive-struggle-preserving · Metacognition-by-design · AI-removable competence** |

---

# 0. 文档定位与执行原则

本 PRD 是后续开发的**权威产品和工程规范**。

后续开发不得重新设计一个与当前仓库平行的新项目，也不得因为 V3.0 引入 Learning-Native 概念而推翻当前已经验证的后端基础设施。

当前项目已经具备：

- Python/FastAPI 权威后端；
- LangGraph 教学工作流；
- Evidence Agent；
- Diagnosis Agent；
- 多模态感知与文档解析；
- PostgreSQL / pgvector / Neo4j / Redis 基础设施；
- 科学 verifier；
- HITL interrupt/resume 后端能力；
- evaluation 框架；
- 独立 `/agent` 页面；
- 图片、文档上传相关前端组件；
- Monaco、公式、Plot 等教学组件；
- typed API contracts。

最新仓库审计中 Python 测试为 **190 passed / 2 skipped**，前端 `tsc --noEmit` 为 **0 errors**。因此本轮工作原则必须是：

> **Preserve → Integrate → Extend → Verify**

而不是：

> Rewrite → Replace → Rebuild

允许重构明显错误或无法维护的局部模块，但任何大规模重写必须有明确工程理由。

可以并且鼓励检查项目文件夹中遗留的旧前端代码，复用其中已经成熟的：

- 页面布局；
- Agent 工作台；
- Composer；
- Equation；
- Plot；
- Code Editor；
- Knowledge Graph；
- Evidence Panel；
- 文件上传；
- 动效；
- Design System；
- Responsive Layout。

但：

> **只复用视觉组件和经过验证的逻辑，不得把旧 mock data、旧 TypeScript Agent runtime 或已经废弃的业务逻辑重新带回主系统。**

---

# 1. 产品重新定义：从 Agent-Native 到 Learning-Native

## 1.1 Quantum Agent 不是什么

Quantum Agent 不是：

- ChatGPT 的量子物理皮肤；
- 课程资料 RAG 聊天机器人；
- 拍照搜题工具；
- 自动作业完成器；
- 自动标准答案生成器；
- 给学生无限解释的聊天框；
- 多个 Agent 互相聊天的演示系统；
- 教师教学管理后台的 AI 扩展；
- 用“使用时长”“会话轮数”优化的产品。

尤其禁止把：

> “学生在 AI 帮助下把题做对”

等价于：

> “学生学会了”。

---

# 2. 产品第一性原理

## 2.1 真正目标函数

普通 AI 产品通常优化：

\[
\min(\text{task completion time})
\]

Quantum Agent 应优化：

\[
\boxed{
\max P(
\text{student solves related novel problems without AI}
)
}
\]

系统最终关心的是：

- 独立提取；
- 延迟保持；
- 新情境迁移；
- 表征转换；
- 自我解释；
- 元认知校准；
- 低提示依赖；
- 科学推理能力。

因此产品 North Star Metric 不得是：

- 日活；
- 消息数；
- Session 时长；
- 学生满意度；
- AI-assisted accuracy。

核心指标应逐渐转向：

```text
Unaided Transfer
Delayed Retrieval
Calibration Accuracy
Hint Dependency
Self-Explanation Quality
Representation Fluency
Scientific Verification Success
```

无护栏生成式 AI 已有随机实验显示，它可能提高练习阶段表现，却降低撤除 AI 后的独立表现；加入 tutoring safeguards 可显著缓解这一问题。

另一方面，经过研究性脚手架设计的大学物理 AI tutor 在真实 RCT 中能够以更短时间取得比课堂 active learning 更高的即时学习增益，说明问题不在“是否使用 AI”，而在于**如何设计学习过程**。

---

# 3. Learning-Native 核心定义

传统 AI Tutor 的基本计算：

```text
Question
→ Retrieve
→ Reason
→ Answer
```

Quantum Agent V3.0 的基本计算必须升级为：

```text
COMMIT
   ↓
ATTEMPT
   ↓
DIAGNOSE
   ↓
INTERVENE
   ↓
RECONSTRUCT
   ↓
VERIFY
   ↓
CALIBRATE
   ↓
TRANSFER
   ↓
RETRIEVE LATER
```

即：

\[
\boxed{
\text{Learning Loop}
=
C \rightarrow A \rightarrow D \rightarrow I
\rightarrow R \rightarrow V \rightarrow C'
\rightarrow T
}
\]

系统的基本单位不再是 **Answer**。

而是：

> **Cognitive Intervention**

每一轮系统必须尽量回答：

1. 学生现在正在构建什么知识？
2. 学生认为自己知道什么？
3. 学生实际表现出什么？
4. 当前最值得让学生进行哪一种认知操作？
5. 现在真的需要 AI 解释吗？
6. 有没有更好的行动：
   - 预测；
   - 尝试；
   - 自我解释；
   - 比较；
   - 模拟；
   - 反驳；
   - 表征转换；
   - 检索；
   - 迁移？
7. 学生离开 AI 后是否仍然能完成？

---

# 4. Learning-Native 设计公理

## Axiom 1 — Learner generates before AI completes

只要教学目标允许，学生应先：

- 预测；
- 尝试；
- 判断；
- 画图；
- 写一步推导；
- 给出解释；

再获得较完整 AI 支持。

Productive Failure 的 meta-analysis 纳入 53 项研究、166 个比较，整体支持 Problem Solving → Instruction 的顺序在合适条件下优于 Instruction → Problem Solving。

---

## Axiom 2 — AI assistance must be reversible

好的 AI 教学最终应该让学生越来越少需要 AI。

系统必须主动创造：

```text
AI assisted mode
       ↓
reduced assistance
       ↓
Solo Mode
       ↓
transfer
```

---

## Axiom 3 — Confidence is data

学生回答：

> “我觉得是 B。”

与：

> “我 95% 确信是 B。”

不是同一个教学状态。

系统应记录：

```text
answer
confidence
actual correctness
later correctness
```

用于元认知校准。

---

## Axiom 4 — Explanation is not mastery

学生能够看懂 AI 解释，不代表能够：

- 自己解释；
- 自己推导；
- 换一种表征；
- 三天后重新提取；
- 解决新问题。

---

## Axiom 5 — Verification outranks fluent language

LLM 可以提出：

> “这里可能违反归一化条件。”

是否真的违反，必须交给：

- SymPy；
- NumPy；
- SciPy；
- QuTiP；
- deterministic verifier。

---

## Axiom 6 — Knowledge Graph is a cognitive model substrate

知识图谱不仅用于 Retrieval。

还必须支持：

```text
prerequisite
representation_of
derived_from
contrasts_with
commonly_confused_with
tested_by
transfers_to
```

从而连接：

\[
\text{Course Knowledge Graph}
\leftrightarrow
\text{Learner Evidence}
\]

---

# 5. 产品结构

Quantum Agent V3.0 的学生产品由六个核心系统组成：

```text
1. Learning Workspace
2. Cognitive State Engine
3. Pedagogical Policy Engine
4. Knowledge & Evidence Engine
5. Scientific Verification Engine
6. Learning Evidence Engine
```

它们之上的最终用户体验是：

```text
             Student
                │
                ▼
        Learning Workspace
                │
        Cognitive Commitment
                │
                ▼
       Cognitive State Engine
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
 Evidence   Diagnosis  Metacognition
     │          │          │
     └──────────┼──────────┘
                ▼
       Pedagogical Policy
                │
  ┌───────┬─────┼─────┬────────┐
  ▼       ▼     ▼     ▼        ▼
 Hint   Debate Sim   Teach   Transfer
                    Back
  │       │     │     │        │
  └───────┴─────┴─────┴────────┘
                │
                ▼
          Verification
                │
                ▼
        Learner Evidence
                │
                └────────↺
```

---

# 6. P0 — Learning-Native 核心壁垒

这些能力缺失时，Quantum Agent 将退化为普通 AI Tutor。

---

## 6.1 Cognitive Commitment Gate

### 功能

AI 不应默认立即回答。

对于适合学生尝试的问题，首先要求最小认知投入：

```text
你的预测是什么？
你认为第一步应该怎么做？
你最不确定的是哪一步？
你对此有多大把握？
```

学生至少需要提交以下之一：

- 一个预测；
- 一步推导；
- 一个物理理由；
- 一个图；
- 一个选项 + confidence；
- 一个自己认为可能正确的方法。

### 示例

学生：

> 为什么无限深势阱基态平均动量为零？

系统先问：

```text
在看解释前，先做一个判断：

A. 粒子没有动量
B. 正负动量贡献抵消
C. 因为能量最低
D. 其他

你的置信度：___ %
```

随后才进入 Diagnosis / Tutor。

### 实现

新增：

```text
CognitiveGate
```

它应该主要是 deterministic policy。

LLM 只负责输出：

```text
attempt_required
attempt_type
minimum_commitment
candidate_prompt
reason_summary
```

最终是否阻止直接答案由代码决定。

---

# 7. Cognitive Mirror — 元认知镜像

## 7.1 目标

把：

> “我感觉我会”

与：

> “行为证据表明我会”

明确区分。

---

## 7.2 Learner Concept State

每个重要 Concept 不显示虚假的“83.72% 掌握度”。

使用证据化状态：

```text
UNKNOWN
EXPOSED
DEVELOPING
DEMONSTRATED
TRANSFER_READY
FRAGILE
NEEDS_REVIEW
```

同时保存不同维度：

```yaml
concept_id:
  evidence_strength:
  confidence_history:
  calibration_gap:
  unaided_retrieval:
  transfer_evidence:
  representation_fluency:
  hint_dependency:
  misconception_candidates:
  last_demonstrated_at:
```

禁止推断：

- IQ；
- 人格；
- 心理疾病；
- 性格类型；
- “学习能力分数”。

---

## 7.3 UI

知识图谱应允许切换：

### Course Map

课程知识结构。

### My Learning Map

当前学生经过证据支持的学习状态。

例如：

```text
角动量

当前状态：FRAGILE

✓ 可以解释 [L²,Lz]=0
✓ 可以完成标准本征值问题
× 图像→算符表征转换失败
× 两次迁移题失败
本人信心：92%
行为证据：中等

→ 存在明显 calibration gap
```

这就是：

> Cognitive Mirror

---

# 8. Teach-Back Engine

AI 教完不能默认结束。

重要学习节点进入：

```text
RECONSTRUCTION
```

要求学生：

- 用自己的话解释；
- 给同学讲；
- 重新写关键推导；
- 画图解释；
- 从数学翻译成物理；
- 从物理翻译成数学。

---

## 8.1 示例

Agent：

> 不看上面的解释，现在用自己的话告诉一个第一次学隧穿效应的同学：为什么 \(E<V_0\) 仍可能透射？

学生回答。

TeachBack Agent 输出：

```yaml
covered_relations:
missing_relations:
contradictions:
unsupported_claims:
recommended_probe:
```

前端显示：

```text
✓ 已说明势垒内为指数衰减
✓ 已说明波函数不立即变为 0
△ 尚未连接到非零透射概率
```

而不是：

```text
82/100
```

---

# 9. Transfer & Solo Engine

这是 Learning-Native 产品必须具备的能力。

## 9.1 Solo Mode

进入 Transfer Check 后：

```text
SOLO MODE
AI assistance temporarily unavailable
```

此阶段：

- 不给 hint；
- 不给答案；
- 不开放 Ask AI；
- 可以使用允许的基本计算工具；
- 完成后才恢复 Tutor。

---

## 9.2 Transfer 类型

系统至少支持：

```text
Near Transfer
Parameter Transfer
Representation Transfer
Conceptual Transfer
Far Transfer
Delayed Retrieval
```

示例：

原题：

> 一维矩形势垒。

Transfer：

> 给出不同宽度下透射率曲线，要求解释趋势。

再 Transfer：

> 双势垒共振透射。

不是简单换数值。

---

## 9.3 学习判据

Mastery 必须优先由：

\[
M=f(
U,T,R
)
\]

定义，其中：

- \(U\)：unaided performance；
- \(T\)：transfer；
- \(R\)：retrieval after delay。

Retrieval practice 对长期记忆的促进具有成熟研究基础。

---

# 10. P1 — Representation Translation Studio

量子力学天然依赖多表征。

一个状态可能表现为：

\[
|\psi\rangle
\]

\[
\psi(x)
\]

\[
\mathbf c
\]

\[
|\psi(x)|^2
\]

能级图、概率分布、Bloch sphere 等。

因此新增：

> **Representation Translation Studio**

---

## 10.1 交互

系统给出：

```text
波函数图
```

要求：

```text
→ 判断奇偶性
→ 判断 <x>
→ 用积分表达
→ 写成 Dirac notation
→ 解释测量含义
```

或者：

```text
公式
→ 图像
→ 物理解释
```

---

## 10.2 Agent

新增逻辑角色：

```text
Representation Tutor
```

模型：

- `qwen3.8-chat`：图像；
- `qwen3.8-reasoner`：复杂视觉推理；
- `deepseek-v4-pro`：数学/物理跨表征推理。

Verifier 验证最终数学关系。

---

# 11. Prediction → Simulation → Explanation

这是 Quantum Agent 的核心体验原语，不再仅属于某一个 Project。

统一模式：

```text
PREDICT
   ↓
COMMIT
   ↓
SIMULATE
   ↓
COMPARE
   ↓
EXPLAIN
   ↓
TRANSFER
```

---

## 11.1 示例：量子隧穿

学生先预测：

```text
增加势垒宽度 →
透射概率如何变化？
```

学生可：

- 选择趋势；
- 画预测曲线；
- 输入公式；
- 上传手绘图。

再执行真实模拟。

前端同时展示：

```text
Your Prediction
Actual Simulation
```

最后要求：

> 哪一个原先假设与你看到的结果冲突？

不允许 AI 第一时间替学生解释。

---

# 12. Misconception Arena

新增：

> **Misconception Arena**

系统生成一个有代表性的错误观点，让学生反驳。

例如：

> “基态的平均动量为零，所以基态中的粒子是静止的。”

学生必须指出：

\[
\langle p\rangle=0
\]

不代表：

\[
\langle p^2\rangle=0
\]

---

## 12.1 实现

```text
Misconception Challenger
       ↓
Student
       ↓
Socratic Probe
       ↓
Verifier
       ↓
Diagnosis
```

禁止让多个 Agent 自己长时间辩论。

> **学生必须始终是认知冲突的参与者。**

---

# 13. Learning Frontier

利用知识图谱给学生显示：

```text
Mastered
Fragile
Ready to Learn
Blocked
Needs Review
Transfer Ready
```

而不是：

```text
第一章 80%
第二章 52%
```

例如：

```text
角动量
  │
  ├─ 对易关系 ✓
  │
  ├─ 共同本征态 △
  │
  └─ CG 耦合 🔒
              ↑
      缺少 prerequisite evidence
```

点击锁定节点时说明：

> 为什么当前还不适合学。

Learning Frontier 的目标不是替学生规划人生，而是减少：

> 不知道自己接下来该理解什么

的认知摩擦。

---

# 14. P2 — 后续研究方向

这些功能设计接口，但比赛版本不得因此推迟 P0。

---

## 14.1 Cognitive Digital Twin

Student-model-lite 长期演进为：

```text
Learning Digital Twin
```

只表示学习相关状态：

\[
S_t=(K,M,C,R,H,T,F)
\]

其中：

- K = knowledge evidence；
- M = misconception；
- C = calibration；
- R = retrieval；
- H = hint dependency；
- T = transfer；
- F = representation fluency。

禁止构建人格画像。

---

## 14.2 Live Multimodal Thought Workspace

未来允许学生：

- 实时手写；
- 画能级；
- 画波函数；
- 拖动参数；
- 修改公式；
- 圈出某一步。

系统基于增量输入进行辅助。

原则：

> AI should observe thinking, not constantly interrupt thinking.

只有在：

```text
persistent dead end
repeated misconception
explicit request
high-confidence critical error
```

时主动介入。

未来可考虑：

- Canvas/SVG；
- tldraw 等 whiteboard；
- incremental vision；
- WebSocket。

本比赛版本不作为阻塞项。

---

# 15. Pedagogical Policy Learning

长期研究目标不是微调“更会讲话”的 LLM。

而是学习：

\[
\pi(a|s)
\]

即：

> 针对当前 learner state，哪种 intervention 最有效？

动作：

```text
hint
question
counterexample
simulation
worked example
teach-back
retrieval
representation switch
solo transfer
```

未来 reward 应优先基于：

\[
R=
\alpha T_{unaided}
+\beta R_{delayed}
+\gamma C_{calibration}
-\lambda H_{dependency}
\]

禁止优化：

```text
session length
click
likes
immediate assisted correctness
```

比赛版本不实施 RL。

---

# 16. 多智能体体系

## 16.1 原则

Quantum Agent 使用：

> **specialist agents inside deterministic educational workflows**

而不是：

> peer-to-peer autonomous swarm。

Anthropic 的生产经验明确建议对定义清晰任务优先使用简单、可组合、可预测的 workflow，只在复杂性带来明确收益时增加 agent autonomy。

---

## 16.2 Agent 角色

### Evidence Agent

只回答：

> 有什么可靠课程证据？

输出：

```text
EvidenceBundle
```

无权直接回答学生。

---

### Diagnosis Agent

回答：

> 学生现在卡在哪里？

输出：

```text
target_concepts
first_consequential_error
misconception_candidates
missing_prerequisites
confidence
verification_required
```

无权选择最终 hint level。

---

### Learning Policy Agent

提出教学动作候选：

```text
ASK_COMMITMENT
ASK_PREDICTION
ASK_SELF_EXPLANATION
GIVE_CUE
GIVE_HINT
SHOW_COUNTEREXAMPLE
START_SIMULATION
START_TEACH_BACK
START_TRANSFER
ENTER_SOLO
SHOW_WORKED_EXAMPLE
```

最终动作仍经过 deterministic Policy Gate。

---

### Concept Tutor

概念澄清。

---

### Derivation Tutor

推导过程与 first consequential error。

---

### Experiment Tutor

预测—模拟—解释。

---

### Project Coach

Project milestone 辅导。

---

### Metacognition Agent

负责：

```text
confidence
calibration
reflection prompt
```

不得给出心理诊断。

---

### Teach-Back Agent

评价学生解释覆盖的概念关系。

---

### Transfer Agent

构造真正的迁移任务。

---

### Representation Tutor

跨文字、公式、图像、Dirac notation 等表征转换。

---

### Misconception Challenger

P1，用于受控认知冲突。

---

# 17. 哪些东西绝对不是 Agent

以下组件必须保持 deterministic service：

```text
RBAC
Policy Gate
Answer Release
Citation Validator
Retriever
Embedding
Reranker
Document Parser
OCR Pipeline
Sandbox
SymPy Verifier
Numerical Verifier
Learning Evidence Writer
Rate Limiter
File Validator
```

不要为了“多智能体”标签把 service 包装成 Agent。

---

# 18. USTC 模型路由

统一经过：

```text
ModelGateway
ModelCapabilityRegistry
ModelRouter
ModelHealthRegistry
```

所有模型调用：

```text
https://api.llm.ustc.edu.cn/v1/chat/completions
Authorization: Bearer ${USTC_API}
```

Key：

- 不进入浏览器；
- 不打印；
- 不提交 Git；
- 不写 trace payload；
- 不进入错误页面。

---

## 18.1 推荐能力路由

| 能力 | Primary | Fallback |
|---|---|---|
| 深度量子推理 | `deepseek-v4-pro` | `qwen3.8-reasoner` |
| Diagnosis | `deepseek-v4-pro` | `qwen3.8-reasoner` |
| Learning Policy proposal | `deepseek-v4-pro` | `deepseek-v4-flash` |
| Concept Tutor | `deepseek-v4-pro` | `qwen3.8-reasoner` |
| Teach-back analysis | `deepseek-v4-pro` | `qwen3.8-reasoner` |
| Transfer generation | `deepseek-v4-pro` | `qwen3.8-reasoner` |
| 分类/路由 | `deepseek-v4-flash-ascend` | `deepseek-v4-flash` |
| 摘要/压缩 | `deepseek-v4-flash` | `deepseek-v4-flash-ascend` |
| Vision | `qwen3.8-chat` | `qwen-chat` |
| Vision reasoning | `qwen3.8-reasoner` | `qwen-reasoner` |
| 编程 | `glm-5.2` | `glm-5.2-107` |
| Embedding | `qwen3-embedding` | configured local fallback |
| Rerank | `qwen3-reranker` | deterministic fusion |
| OCR | `unlimited-ocr` | `qwen3.8-chat` |
| Document Intelligence | `mineru` | native parser + OCR |

`smart/default`、`smart/reasoning` 可用于非关键 fallback，但不得作为正式 benchmark 的唯一 model identifier。

所有实验必须记录实际：

```text
model_alias
capability
latency
fallback
```

---

# 19. Prompt Architecture

禁止巨型通用 System Prompt。

使用：

```text
Global Learning Constitution
        ↓
Specialist Role Prompt
        ↓
Learner State
        ↓
EvidenceBundle
        ↓
Task Context
        ↓
Strict Structured Output
```

---

## 19.1 Global Learning Constitution

所有 Tutor 必须遵守：

1. Protect productive struggle.
2. Prefer elicitation before explanation.
3. Never claim verification without tool evidence.
4. Distinguish evidence from model inference.
5. Encourage reconstruction.
6. Test transfer.
7. Do not fabricate citations.
8. Do not expose hidden reasoning.
9. Do not infer sensitive psychological traits.
10. Obey Policy Gate.

---

# 20. 知识系统

课程知识由：

```text
PostgreSQL
+
PostgreSQL FTS
+
pgvector
+
Neo4j
+
qwen3-reranker
```

联合支持。

---

## 20.1 Hybrid Retrieval

```text
Question
   │
   ├── FTS
   │
   ├── Vector
   │
   └── Graph
         │
         ▼
       Fusion
         │
         ▼
      Reranker
         │
         ▼
   EvidenceBundle
```

Neo4j 官方 GraphRAG Python 包目前提供 Vector、VectorCypher、Hybrid、HybridCypher、Text2Cypher 等 retriever，可按课程查询类型受控使用。

GraphRAG 不成为事实权威。

> 原始课程材料始终是事实来源。

---

# 21. 多模态体系

输入：

```text
Text
Image
Handwriting
PDF
DOCX
PPTX
Mixed Input
```

流程：

```text
Attachment Validator
      ↓
Native Parser
      ↓
MinerU
      ↓
OCR fallback
      ↓
Vision enrichment
      ↓
MultimodalEvidence
```

所有证据应尽量保留：

```text
source_file
page
slide
bbox
extraction_method
confidence
```

低置信度 OCR 不得悄悄进入 Diagnosis。

---

# 22. 科学验证层

这是核心竞争壁垒。

技术：

```text
SymPy
NumPy
SciPy
QuTiP
Matplotlib
Docker Sandbox
```

首版至少支持：

```text
algebra equivalence
normalization
Hermiticity
commutator
boundary conditions
dimensions
eigenvalue checks
probability conservation
numerical convergence
code tests
```

统一：

```yaml
ToolResult:
  status: verified | contradicted | inconclusive | error
  summary:
  evidence:
  numeric_values:
  artifacts:
  warnings:
  runtime_ms:
```

LLM 无权把：

```text
inconclusive
```

改写成：

```text
verified
```

---

# 23. 技术架构

```text
┌─────────────────────────────────────────────┐
│           Next.js Learning Workspace        │
│ text / image / document / equation / code   │
└────────────────────┬────────────────────────┘
                     │ HTTPS + SSE
                     ▼
┌─────────────────────────────────────────────┐
│                   FastAPI                   │
│ auth / course / upload / agent / learning   │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│             LangGraph Runtime               │
│                                             │
│ Input Router                                │
│      ↓                                      │
│ Multimodal Evidence                         │
│      ↓                                      │
│ Evidence Agent                              │
│      ↓                                      │
│ Diagnosis Agent                             │
│      ↓                                      │
│ Cognitive State                             │
│      ↓                                      │
│ Pedagogical Policy                          │
│      ↓                                      │
│ Specialist Tutor Subgraph                   │
│      ↓                                      │
│ Policy Gate                                 │
│      ↓                                      │
│ Verifier / Simulation / Sandbox             │
│      ↓                                      │
│ Teach-back / Transfer / Calibration         │
│      ↓                                      │
│ Learning Evidence Update                    │
└──────────────┬──────────────┬───────────────┘
               │              │
        PostgreSQL         Neo4j
        + pgvector          KG
               │
             Redis
```

LangGraph 负责：

```text
state
workflow
checkpoint
subgraph
interrupt
resume
recovery
```

官方 persistence 机制本身提供 checkpoint、HITL、memory、time-travel debugging 和 fault tolerance；生产 HITL 应使用持久化 checkpointer。

---

# 24. 完整技术栈

## Frontend

```text
Next.js
React
TypeScript strict
Tailwind CSS
shadcn/ui
TanStack Query
Zod
KaTeX
Monaco Editor
Plotly.js
Cytoscape.js
PDF.js / react-pdf
SSE
```

可根据当前项目依赖和遗留组件保留：

```text
CSS Modules
existing design system
existing animation utilities
```

必要时允许：

```text
Framer Motion
GSAP
```

但不得为了动画重写页面。

---

## Backend

```text
Python 3.12
FastAPI
LangGraph
Pydantic v2
PydanticAI
SQLAlchemy 2
Alembic
psycopg 3
```

---

## Knowledge

```text
PostgreSQL 15+
PostgreSQL FTS
pgvector
Neo4j
neo4j-graphrag
qwen3-embedding
qwen3-reranker
```

---

## Multimodal

```text
PyMuPDF
python-docx
python-pptx
MinerU
unlimited-ocr
qwen3.8-chat
qwen3.8-reasoner
```

---

## Scientific Computing

```text
SymPy
NumPy
SciPy
QuTiP
Matplotlib
```

---

## Infrastructure

```text
Docker Compose
PostgreSQL
Neo4j
Redis
sandbox worker
reverse proxy
local storage with S3-compatible abstraction
```

比赛阶段：

> **不要迁移 Kubernetes。**

---

## Observability

```text
structured JSON logs
OpenTelemetry-compatible traces
run_id
thread_id
node
model
latency
fallback
retrieval ids
tool result
policy action
learning action
```

不得存储 hidden chain-of-thought。

只允许：

```text
decision_summary
```

---

## Quality

```text
pytest
Ruff
mypy
TypeScript strict
Playwright
frontend production build
live infra regression
live model smoke
live E2E
secret scanning
```

---

# 25. 前端产品要求

前端不是管理后台。

它必须让用户第一眼感觉：

> **这是一个真正用于思考、推导、实验和构建理解的学习工作台。**

而不是：

> ChatGPT clone。

---

# 26. 页面总体结构

Desktop 推荐：

```text
┌─────────────────────────────────────────────────────────┐
│ Quantum Agent          Course / Mode        User        │
├─────────────┬───────────────────────────┬───────────────┤
│             │                           │               │
│ Learning    │                           │ Cognitive     │
│ Map         │     Learning Canvas       │ Mirror /      │
│             │                           │ Evidence      │
│ Concepts    │                           │               │
│ Sessions    │                           │               │
│ Projects    │                           │               │
├─────────────┴───────────────────────────┴───────────────┤
│ Multimodal Composer                                    │
│ + text + image + document + equation + code            │
└─────────────────────────────────────────────────────────┘
```

但不要机械照搬三栏。

如果已有 `AgentExperience` 架构成熟，可在其基础上优化。

---

# 27. Learning Canvas

中心区域不是纯聊天记录。

它需要支持专门的 Learning Blocks：

```text
ExplanationBlock
CommitmentCard
PredictionCard
DerivationCard
EvidenceCard
SimulationCard
TeachBackCard
TransferCard
SoloModeCard
RepresentationCard
MisconceptionCard
VerificationCard
ReflectionCard
```

不同教学动作必须有明显 UI 差异。

---

# 28. Frontend Visual Direction

视觉风格：

> **Modern Scientific · Calm · Premium · Academic · Human**

避免：

- 传统教务系统；
- 企业 BI dashboard；
- 花哨游戏化；
- 卡通儿童风；
- 密密麻麻数据表；
- 大面积机器人插画；
- ChatGPT 完全复刻。

---

## 28.1 视觉原则

### 层次清晰

学生永远能知道：

```text
我现在在做什么？
为什么 Agent 暂时不给答案？
下一步要做什么？
哪些是教材证据？
哪些是模拟结果？
哪些只是 AI 推断？
```

### 大量留白

学习区域必须具有足够空间。

### 数学优先

公式、推导、图形必须是一级 UI 对象。

### Evidence subtle but accessible

引用不能喧宾夺主，但点击即可：

```text
来源
章节
页码
原页
bbox highlight
```

### 动效

可以使用：

```text
Framer Motion / GSAP
```

实现：

- mode transition；
- graph focus；
- panel expand；
- evidence reveal；
- simulation transition；
- knowledge node transition。

动画时间应短、自然，并遵守：

```text
prefers-reduced-motion
```

禁止无意义漂浮元素。

---

# 29. 必须复用现有前端资产

首先审计：

```text
app/agent/page.tsx
app/components/agent/AgentExperience.tsx
AgentQueryProvider
AgentEquation
AgentPlot
AgentCodeEditor
agent.module.css
contracts.ts
app/api/agent/*
app/api/teaching/*
```

如果能够满足新 UI：

> 优先修改和复用。

也必须搜索项目中以前遗留的：

```text
components
pages
layouts
graph
animations
upload
chat
code
plot
equation
cards
```

优秀的旧 UI 可以迁移。

但：

1. 不复制旧 mock backend；
2. 不恢复废弃业务逻辑；
3. 不引入重复 Design System；
4. 不保留无法解释的 dead code。

---

# 30. 前后端必须真正接通

这是本轮最高工程要求之一。

最终页面：

> **不得依赖假数据完成主要演示。**

任何核心按钮必须有真实行为。

---

## 30.1 Frontend API Layer

所有后端调用经过统一 typed client。

禁止组件内部散落：

```typescript
fetch(...)
```

推荐：

```text
lib/api/
  client.ts
  agent.ts
  attachments.ts
  learning.ts
  evidence.ts
  projects.ts
```

前端：

```text
Zod
```

验证 runtime response。

后端：

```text
Pydantic
```

作为权威 schema。

---

# 31. Streaming

Agent 对话必须使用 SSE。

事件建议标准化：

```text
run.started
perception.started
perception.completed
evidence.ready
diagnosis.ready
learning_action.required
tutor.delta
tool.started
tool.completed
artifact.ready
teachback.required
transfer.required
learner_state.updated
interrupt.required
run.completed
run.error
```

前端不得通过：

```text
setTimeout + fake typing
```

伪造模型 streaming。

---

# 32. Attachment UX

Composer 必须支持：

```text
Paste image
Drag image
Upload image
Upload PDF
Upload DOCX
Upload PPTX
```

上传后必须显示：

```text
filename
type
processing state
success
failure
```

解析失败必须对用户可见。

禁止 silent failure。

---

# 33. Evidence UX

任何课程材料引用应支持：

```text
Citation Chip
        ↓
Evidence Drawer
        ↓
Original Page
        ↓
Highlighted Region
```

手机端：

> Drawer / Bottom Sheet

桌面端：

> Side Panel

---

# 34. Cognitive Mirror UI

右侧面板应优先显示：

```text
Current Concept
Current Learning State
Confidence
Observed Evidence
Hint Dependency
Transfer Status
```

但避免仪表盘化。

核心表达应该是自然语言 + 少量视觉提示。

例如：

```text
角动量耦合

状态：Developing

你已经：
✓ 能解释两个角动量如何组成总角动量

还没有证据证明：
○ 能独立使用 CG 系数
○ 能迁移到光谱选律

你的信心：高
当前证据：中等
```

---

# 35. Student Modes

保留并升级：

```text
Learn
Derive
Experiment
Project
```

同时允许系统动态进入：

```text
Teach Back
Transfer
Solo
Representation
Debate
```

学生不应选择：

```text
deepseek
qwen
glm
```

模型路由完全隐藏。

---

# 36. Golden Learning Loop

比赛必须有一个真正 Learning-Native 的完整故事。

建议继续使用：

> **量子隧穿 / 波包传播**

因为已有基础。

演示：

```text
学生进入量子隧穿
        ↓
Agent 要求预测
        ↓
学生提交错误预测 + 80% confidence
        ↓
Diagnosis 检测经典直觉误区
        ↓
只给最小提示
        ↓
学生修改预测
        ↓
运行真实 simulation
        ↓
Verifier 验证概率守恒
        ↓
显示 Prediction vs Reality
        ↓
学生解释差异
        ↓
Teach-back
        ↓
Representation switch
        ↓
Solo transfer problem
        ↓
更新 Cognitive Mirror
```

这一个演示必须证明：

> Quantum Agent 在改变学习过程，而不仅仅是在回答量子物理问题。

---

# 37. Course Scope

首版仍严格绑定 USTC《量子物理》课程。

教学知识结构应覆盖现有课程大纲中的：

```text
旧量子论
量子力学基础
表象理论
原子结构
近似方法
双原子分子
分子光谱
```

所有关键课程事实必须可追溯到已审核语料。

---

# 38. Project 模块

比赛至少维持四个 Project 的产品入口。

其中：

## Project 1

**量子隧穿与波包传播**

必须完整。

其他三个允许骨架 + 可运行核心。

每个 Project 按：

```text
Predict
Build
Run
Verify
Explain
Reflect
Transfer
```

设计。

不要做：

```text
任务列表
→ 写代码
→ 自动检查
```

式普通在线实验平台。

---

# 39. 安全代码运行

学生 Python 进入 Sandbox。

必须：

```text
non-root
resource limit
timeout
network disabled by default
package whitelist
filesystem isolation
artifact-only output
```

禁止：

```text
pip install arbitrary package
host filesystem access
Docker socket access
secret access
```

---

# 40. Learning Evidence 数据模型

核心表应至少表达：

```text
learning_event
concept_id
task_id
run_id
action
attempt
confidence
hint_level
result
verification
transfer_type
independence
timestamp
```

Evidence 类型：

```text
CORRECT_SELF_EXPLANATION
CORRECT_TRANSFER_RESPONSE
FAILED_TRANSFER_RESPONSE
CORRECTED_DERIVATION
PASSED_TOOL_CHECK
FAILED_TOOL_CHECK
MISCONCEPTION_OBSERVED
REPEATED_MISCONCEPTION
HIGH_HINT_DEPENDENCY
SUCCESSFUL_RETRIEVAL
FAILED_RETRIEVAL
REPRESENTATION_TRANSLATION_SUCCESS
TEACH_BACK_SUCCESS
```

---

# 41. Memory 架构

严格分为：

| Memory | Store |
|---|---|
| Run / Conversation | LangGraph Checkpointer |
| Student Learning | PostgreSQL |
| Course Knowledge | PostgreSQL + pgvector + Neo4j |
| Files | attachment storage |

不得把：

> LLM conversation summary

直接作为正式学生知识状态。

---

# 42. Evaluation

现有 B0–B4 evaluation 框架保持。

不要为了 V3.0 重写现有 evaluation。

新增：

> **Learning-Native Evaluation**

---

## 42.1 LN Metrics

### LN-1 Cognitive Engagement

```text
attempt-before-answer rate
prediction rate
self-explanation completion
```

### LN-2 Dependency

```text
average hint level
full-solution request rate
high-hint dependency
```

### LN-3 Transfer

```text
unaided transfer accuracy
```

### LN-4 Calibration

比较：

```text
confidence
vs
actual performance
```

### LN-5 Reconstruction

Teach-back correctness。

### LN-6 Representation Fluency

跨表征成功率。

### LN-7 Scientific Correctness

```text
verifier agreement
tool success
false verification rate
```

### LN-8 Grounding

```text
citation precision
citation coverage
source validity
```

---

# 43. Learning-Native Ablation

在现有 B0–B4 之外增加：

```text
LN-A baseline tutoring
LN-B + commitment
LN-C + teach-back
LN-D + transfer/solo
LN-E + cognitive mirror
```

比赛不要求真实学习效果 RCT。

但必须证明：

> 技术上系统已经可以测量未来真实学习效果。

---

# 44. Observability

每个 run 至少记录：

```text
run_id
thread_id
user_role
course_id
input_modality
model_capability
actual_model
prompt_version
retrieval_ids
graph_path
learning_action
hint_level
tool_calls
tool_results
citations
latency
fallback
interrupt
learning_events
```

不得记录 API Key。

---

# 45. 当前必须完成的工程工作

基于现有 progress，不重新完成已经完成的 P0/P1/P2/P3。

当前执行顺序：

## Phase A — Preserve & Audit

- 跑全量现有 tests；
- 标记已有功能；
- 审计旧 frontend；
- 禁止无理由重写。

---

## Phase B — Real Stack

完成：

```text
make up
make test-live-infra
make test-live-model
```

解决真实：

```text
PostgreSQL
Neo4j
Redis
USTC API
```

问题。

---

## Phase C — Frontend ↔ Backend Integration

逐项证明：

```text
Text → backend → SSE → UI
Image → perception → backend → UI
PDF → parser → evidence → UI
Code → sandbox → artifact → UI
HITL → interrupt → resume → UI
```

不得用 mock 假装成功。

---

## Phase D — Learning-Native P0

优先实现：

1. Cognitive Commitment；
2. Teach-back；
3. Transfer / Solo；
4. Cognitive Mirror MVP。

---

## Phase E — Learning-Native UX

实现：

```text
CommitmentCard
PredictionCard
TeachBackCard
TransferCard
SoloMode
LearningStatePanel
```

---

## Phase F — Golden Loop

完整打通隧穿 Demo。

---

## Phase G — Final Quality

执行：

```text
pytest
ruff
mypy
tsc
frontend build
Playwright
live infra
live model
live E2E
secret scan
```

---

# 46. Definition of Done

V3.0 Competition Release 只有同时满足以下条件才能称为完成。

## Backend

- [ ] 当前已有单元测试不得显著回退
- [ ] live PostgreSQL 可用
- [ ] live Neo4j 可用
- [ ] live Redis 可用
- [ ] USTC model gateway 可用
- [ ] capability routing 可用
- [ ] LangGraph checkpoint 可用
- [ ] HITL resume 可用
- [ ] scientific verifier 可用

## Multimodal

- [ ] 图片真实解析
- [ ] PDF 真实解析
- [ ] bbox/page provenance 可展示
- [ ] OCR failure 可见
- [ ] unsupported capability 有 fallback

## Learning-Native

- [ ] Commitment Gate
- [ ] confidence capture
- [ ] Teach-back
- [ ] Transfer
- [ ] Solo Mode
- [ ] Cognitive Mirror MVP
- [ ] Learning Evidence persistence

## Frontend

- [ ] `/agent` 是完整真实工作台
- [ ] 前端视觉达到产品展示质量
- [ ] 无核心 mock data
- [ ] SSE 真流式
- [ ] 图片上传可用
- [ ] 文档上传可用
- [ ] Equation 可用
- [ ] Plot 可用
- [ ] Monaco 可用
- [ ] Evidence 可点击回原页
- [ ] Responsive
- [ ] 无严重 console error
- [ ] loading / empty / error states 完整

## Golden Loop

完整完成：

```text
Predict
→ Diagnose
→ Hint
→ Simulate
→ Verify
→ Explain
→ Teach-back
→ Transfer
→ Cognitive Mirror Update
```

## Engineering

- [ ] Python tests pass
- [ ] Ruff pass
- [ ] mypy pass
- [ ] TypeScript strict pass
- [ ] production build pass
- [ ] Playwright golden loop pass
- [ ] live infra test pass
- [ ] live model smoke pass
- [ ] no leaked secrets

---

# 47. 明确禁止事项

开发过程中禁止：

1. 为追求“多智能体”数量增加无意义 Agent；
2. 推翻当前 Python/LangGraph 后端重写；
3. 恢复旧 TypeScript Agent runtime；
4. 用 mock data 完成正式演示；
5. 把 OCR 输出默认当作事实；
6. 让 LLM 宣称未经工具验证的数学结论“已验证”；
7. 把知识图谱作为唯一 Retrieval；
8. 学生直接选择底层模型；
9. 前端出现 API Key；
10. 让 `smart/*` 模型别名破坏正式实验可复现性；
11. 用聊天 Session 长度作为学习 KPI；
12. 生成长期人格/心理画像；
13. 自动给最终成绩；
14. 无限制泄露标准答案；
15. 为炫技加入 autonomous web agent；
16. 在比赛阶段迁移 Kubernetes；
17. 为 UI 重构整个应用；
18. 为动画牺牲可访问性或性能。

---

# 48. 产品最终愿景

Quantum Agent 不以：

> “拥有多少 Agent”

作为先进性的证明。

也不以：

> “回答有多聪明”

作为最终价值。

Quantum Agent 真正要构建的是：

\[
\boxed{
\text{Course Knowledge}
+
\text{Multimodal Perception}
+
\text{Cognitive State}
+
\text{Pedagogical Policy}
+
\text{Scientific Verification}
+
\text{Learning Evidence}
}
\]

其终极目标不是让学生越来越擅长向 AI 提问。

而是：

\[
\boxed{
\textbf{让学生越来越有能力在没有 AI 的情况下思考。}
}
\]

因此产品应从：

```text
Chat with AI
```

演进为：

```text
Think with AI
```

再最终达到：

```text
Think independently.
```

这就是 Quantum Agent 所定义的：

# Learning-Native AI Education

---

# 49. 给工程智能体的最终执行要求

在开始编码之前：

1. 阅读本 PRD；
2. 阅读 `progress.md`；
3. 阅读当前仓库 `README / CLAUDE.md / AGENTS.md`；
4. 审计当前 Python 后端；
5. 审计 `/agent` 页面；
6. 搜索历史 frontend 资产；
7. 列出：
   - 已实现；
   - 部分实现；
   - 缺失；
   - 可复用旧代码；
   - 应删除 dead code；
8. 再开始修改。

开发过程中必须：

```text
inspect before rewrite
reuse before replace
integrate before redesign
test before claim
```

每完成一个功能必须验证真实端到端链路。

尤其禁止只根据源码判断：

> “应该可以运行”。

必须实际运行：

```text
Browser
→ Frontend
→ API
→ LangGraph
→ Model / Tool
→ Database
→ SSE
→ Browser
```

最终交付报告必须包含：

```text
1. 实际修改文件
2. 架构变化
3. Learning-native 功能
4. 前端复用情况
5. USTC 模型路由
6. 前后端真实联调结果
7. 测试结果
8. Playwright 结果
9. live infra 结果
10. live model 结果
11. 已知剩余问题
12. 最终运行命令
```

不得以“代码已实现但未运行”作为完成。

---

# 50. 研究与工程依据

本 PRD 的工程理念与现有 V2.1 保持连续：workflow 包围少量 specialist agents，而身份、Policy、Verifier 与 evidence writing 保持 deterministic。当前仓库已经采用这一结构，因此 V3.0 的重点是增加 Learning-Native cognitive runtime，而非重做底层 Agent 框架。

LangGraph 的持久化机制为 checkpoint、HITL、故障恢复和可恢复工作流提供了适合当前系统的基础。

Neo4j GraphRAG 官方 Python 包支持 hybrid 与 graph-enhanced retrieval，因此知识图谱适合作为课程语义骨架，而不是取代全文与向量检索。

Learning-Native 层主要依据以下学习原则：

- Productive Failure / Problem Solving before Instruction；
- Retrieval Practice；
- 结构化、脚手架化 AI tutoring；
- 防止无护栏 GenAI 形成依赖、损害 AI-removal performance。

最终技术策略仍遵循：

> **最小必要自治 + 最大可验证性 + 学习过程优先。**