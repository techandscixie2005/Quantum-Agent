# Quantum Agent：收敛后的核心方案
## 面向中国科学技术大学《量子物理》课程的 Learning-Native 多智能体教学系统

**版本**：Competition Core Plan · 2026-08-31  
**目标赛事**：中国科学技术大学“一〇七杯”算力与智能体开发大赛 · 智能体赛道  
**目标用户**：中国科学技术大学《量子物理》课程学生；辅助用户为助教与主讲教师  
**一句话定位**：

> **Quantum Agent 是一个从真实量子物理教学经验出发，先理解学生怎么想，再基于课程知识图谱进行诊断、补全推导、协助科学计算，并最终把思考能力重新交还给学生的 Learning-Native AI 助教。**

**教育口号**：

> **Think with AI. Think without AI.**

**技术口号**：

> **One Knowledge Graph · One Tutor Graph · One Event Stream · One Learning Stage**

**系统原则**：

> **Teaching experience defines the problem. Pedagogy defines the constraints. Agents provide intelligence. Course evidence grounds. Tools verify truth.**

---

# 0. 执行摘要

Quantum Agent 不是“量子物理版 ChatGPT”，也不是一个简单的 RAG 问答系统，更不是为了展示“多智能体”而让多个 Agent 互相聊天的 Demo。

它的出发点来自真实教学现场。

项目开发者在担任中国科学技术大学《量子物理》课程助教时发现，学生真正需要帮助的地方，往往不是“完全不会、想直接拿答案”，而是以下三类高频问题：

1. **学生已经有思路，但思路得不到正确结果，或者推导中出现矛盾。**  
   他们需要的不是另一份标准答案，而是有人理解其推理过程，找到第一处真正导致后续错误的关键步骤，并给予最小必要帮助。

2. **教材和 PPT 为了课堂节奏经常存在跳步。**  
   老师能凭经验补上的中间逻辑，学生未必能自动补全。学生真正缺的是从“这一行”到“下一行”的推导桥，以及它依赖的定义、假设和前置知识。

3. **量子物理存在许多计算量大、容易算错、但非常值得亲手推导和观察的内容。**  
   学生并不希望只记忆结论，而是希望有人陪他建立模型、写出公式、做数值计算、画出图像，并检查结果是否满足物理约束。

与此同时，主讲教师拥有约 20 年一线教学经验。他希望把课程长期积累的知识结构、先修关系、易错点、推导链和跨章节联系显式化为一个**可审核的课程知识图谱**，让学生不仅“会做一道题”，还能够看见整门量子物理课程的结构。

因此，Quantum Agent 的核心不是某个模型、某个框架或者某项 AI 技术，而是：

```text
一线教学经验
    ↓
教学问题抽象
    ↓
课程知识图谱
    ↓
Learning-Native 教学工作流
    ↓
多智能体 + 科学工具
    ↓
学生独立能力的证据
```

其最终优化目标不是：

\[
\min(\text{得到答案的时间})
\]

而是：

\[
\boxed{
\max P(\text{学生在减少或撤除 AI 帮助后，仍能独立解决相关新问题})
}
\]

Quantum Agent 将传统 AI 学习产品常见的：

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

项目因此形成四个互相咬合的核心：

1. **Pedagogical Knowledge Graph**：先构建课程的教学知识图谱；
2. **Tutor Graph**：用确定性教学政策约束多智能体工作流；
3. **Scientific Learning Environment**：让公式、图像、代码、实验、验证进入教学；
4. **Learning Evidence**：用学生真实行为证明“是否逐渐会了”，而不是让模型主观打一个掌握度分数。

---

# 1. 项目缘起：这不是“为了参赛想出来的 AI 功能”

## 1.1 第一性问题：学生缺的到底是什么？

传统搜索、题解网站和通用聊天模型擅长解决：

> “答案是什么？”

但真实教学中的更困难问题是：

> “这个学生为什么会这样想？”

> “他的推理从哪一步开始偏离？”

> “这里究竟缺了哪一个中间步骤？”

> “他是概念没懂，还是只算错了？”

> “他看懂解释之后，能不能自己重新做？”

> “换一个表面不同的问题，他还会不会？”

这意味着，一个真正的教学智能体不应该首先优化“回答能力”，而应该优化：

```text
理解学生
→ 定位认知状态
→ 决定此刻最合适的帮助
→ 验证学生是否真的获得能力
```

---

## 1.2 一线教学经验是 Quantum Agent 最重要的“私有数据”

项目最有价值的资产不是 Prompt，也不是模型列表，而是：

- 助教真实答疑中观察到的学生行为；
- 主讲教师多年形成的课程结构理解；
- 哪些推导容易卡住；
- 哪些概念最容易混淆；
- 哪些题目适合用反例；
- 哪些地方只需要一个小提示；
- 哪些地方必须做计算才能真正理解；
- 哪些跨章节关系决定了学生能否迁移。

Quantum Agent 的目标之一，就是把这些原本存在于教师脑中的**隐性教学知识**，逐渐变成：

```text
Knowledge Graph relations
Misconception candidates
Derivation bridges
Pedagogical policies
Transfer tasks
Verifier contracts
Teacher-reviewed learning patterns
```

这也是本项目与通用 AI Tutor 最大的差异来源。

---

# 2. 核心叙事

Quantum Agent 的比赛叙事必须非常简单。

## 2.1 30 秒版本

> 我们在中国科大量子物理教学和答疑中发现，学生真正的问题往往不是没有思路，而是已有思路中存在一处关键矛盾；教材和 PPT 中又经常存在教师能看懂、学生补不出的跳步；而很多量子现象只有真正算一遍、画出来，学生才能形成直觉。  
>
> 因此我们和长期从事课程教学的主讲老师一起，把这些一线经验编码成一个 Learning-Native AI 助教：它先基于课程资料构建教学知识图谱，再理解学生自己的推理，定位第一处关键错误，补全必要推导，调用 Coding Agent 和科学工具做真实计算，并通过 Teach-Back、Transfer 和 Solo 验证学生能否最终脱离 AI 独立完成。

---

## 2.2 一句话价值主张

> **不是替学生思考，而是看见学生的思考、修复学生的思考，并最终把思考还给学生。**

---

## 2.3 四个记忆点

### 1. Understand how the student thinks
先看学生已经怎么想，而不是直接重新解题。

### 2. Reconstruct what the textbook skips
把教材/PPT 隐含的中间逻辑、假设和前置知识显式化。

### 3. Compute what is too tedious to compute by hand
让学生真正看到量子模型“算起来是什么样”，而不是死记结论。

### 4. Give thinking back to the student
通过重构、Teach-Back、Transfer、Solo 逐步撤除 AI 帮助。

---

# 3. 项目边界

收敛的关键不是“还能加什么”，而是明确“不做什么”。

## 3.1 Competition Release 必须解决的核心问题

比赛版只聚焦：

1. 中国科大《量子物理》课程；
2. 课程材料驱动的教学知识图谱；
3. 学生文本、截图、手写推导、PDF 等输入；
4. 学生已有思路的诊断；
5. 推导跳步补全；
6. 最小必要教学干预；
7. 真实量子物理计算、代码生成、沙箱执行与科学验证；
8. Teach-Back、Transfer、Solo；
9. 可解释 Learning Evidence / Cognitive Mirror；
10. 简洁、科学、沉浸的学生工作台；
11. 教师/助教对知识、证据和异常流程的审核治理；
12. 真实可部署、可复现、可演示的 Golden Loop。

---

## 3.2 明确不做

比赛前不做：

- 泛学科 AI 学习平台；
- 自动生成完整课程；
- AI 同学/大量虚拟角色聊天；
- Avatar、TTS、花哨角色扮演作为核心卖点；
- Flashcard/FSRS/背单词系统；
- 长期日程 Planner；
- 自动代做作业；
- 自动提交教务系统；
- 面向学生开放任意网页浏览；
- Agent swarm 自由协商；
- 让 Agent 自己修改教学政策；
- 让 LLM 自己裁定科学正确性；
- 让模型主观输出“掌握度 87%”；
- 为了技术栈复杂而增加新的 Engine/Service；
- 与比赛主线无关的教师大数据平台。

---

## 3.3 项目产品单位：Learning Episode，不是 Message

一次学习不是“一问一答”，而是围绕一个学习目标持续推进的 Episode：

```text
一个概念
一个题目
一段推导
一个实验问题
一个迁移目标
```

Episode 有：

- 当前学习阶段；
- 学生尝试；
- 课程证据；
- 诊断；
- 已使用的帮助等级；
- 科学工具结果；
- Teach-Back；
- Transfer；
- Solo；
- Learning Evidence；
- completion condition。

---

# 4. 核心教学思想

## 4.1 先尝试，再解释

对于适合学习的问题，在完整解释之前，先要求最低限度的认知投入：

- 一个预测；
- 一步推导；
- 一个理由；
- 一个选项；
- 一张草图；
- 或明确回答“我不知道”。

这不是为了为难学生，而是为了让系统获得诊断依据，并让学习从“被动阅读”转成“主动生成”。

---

## 4.2 找到第一处真正改变后续结果的错误

对于长推导，Quantum Agent 不应该逐行挑错，更不应该直接重写。

核心对象：

> **First Consequential Error**

即：

> 第一处一旦修正，就可能让后续推理重新回到正确轨道的关键错误。

典型诊断输出：

```text
target_concepts
prerequisite_gaps
first_consequential_error
misconception_candidates
confidence
verification_needed
```

---

## 4.3 最小必要帮助，而不是一次讲透

Assistance Ladder：

```text
L0  Student generation
L1  Attention cue
L2  Minimal hint
L3  Socratic / contrastive question
L4  Representation translation
L5  Partial worked step
L6  Full explanation
```

系统目标：

> 能用 L2 解决，就不要直接使用 L6。

---

## 4.4 推导桥：补教材真正缺失的中间结构

教材/PPT 常见：

```text
A
↓
D
```

学生需要：

```text
A
↓  使用定义 X
B
↓  隐含假设 Y
C
↓  使用定理 / 近似 Z
D
```

因此系统需要正式的 **Derivation Bridge**：

```text
source_step
target_step
missing_steps[]
used_definitions[]
assumptions[]
prerequisites[]
validity_conditions[]
source_refs[]
```

Derivation Bridge 不是让 AI 自由脑补，而是由课程资料、知识图谱和教师审核共同约束。

---

## 4.5 学生“看懂”不是结束

一个概念真正完成学习至少需要更强证据：

```text
Reconstruction
→ Teach-Back
→ Transfer
→ Solo
```

其中：

- **Reconstruction**：学生自己重新生成关键推理；
- **Teach-Back**：学生反过来教 Quantum Agent；
- **Transfer**：换一个表面不同、结构相似的问题；
- **Solo**：撤除提示后独立完成。

---

# 5. 三个旗舰教学场景

整个产品围绕三个一线教学场景设计，而不是围绕“Agent 数量”设计。

---

## 5.1 Reasoning Clinic：我有思路，但为什么算不对？

### 输入

- 文本推导；
- 作业截图；
- 手写公式；
- PDF 某一页；
- “我从这里开始不对”。

### 流程

```text
Perception
→ Reconstruct Student Reasoning
→ Evidence
→ Diagnosis
→ First Consequential Error
→ Minimal Intervention
→ Student Revision
```

### 产品行为

不要：

> “正确解法如下……”

而是：

> “你的总体路线成立。真正让后续结果发生偏差的是第三行：这里隐含使用了某个对易条件，但当前哈密顿量下它并不成立。先只检查这一行。”

### 核心价值

这是最能体现“真正理解学生思路”的功能。

---

## 5.2 Derivation Bridge：PPT 这里为什么突然就到下一步了？

### 输入

学生选中：

- PPT 两行；
- 教材某一公式；
- “为什么这里等号成立？”

### 流程

```text
Current Formula
→ KG prerequisite lookup
→ Evidence retrieval
→ Hidden assumptions
→ Missing algebra / operator steps
→ Interactive derivation bridge
→ Student reconstructs
```

### 输出不是长篇解释，而是结构化桥梁

```text
原式
↓
[补：完备性关系]
中间式 1
↓
[补：代入本征方程]
中间式 2
↓
[补：利用正交归一]
课件下一行
```

---

## 5.3 Scientific Co-Derivation：这个结论我不想背，我想自己算一遍

适用内容例如：

- 势垒隧穿；
- 一维势阱；
- 谐振子；
- 波函数概率密度；
- 微扰修正；
- Stark / Zeeman 分裂；
- 角动量耦合；
- 分子振转能级；
- 光谱选择定则的数值例子；
- 波包演化。

### 流程

```text
Student Prediction
→ Define Physical Model
→ Parameters / Assumptions / Boundary Conditions
→ ScientificTask
→ Coding Agent
→ Generated Python
→ Static Safety
→ Isolated Sandbox
→ Deterministic Verifier
→ Plot / Table / Simulation
→ Student Explains Observation
→ Transfer
```

### 关键原则

计算不是“替学生做”。

计算必须成为认知闭环的一部分：

> “你原来预测什么？”  
> “结果是什么？”  
> “为什么不同？”  
> “哪个参数最敏感？”  
> “如果换一个条件呢？”

---

# 6. 先构建教学知识图谱，再构建智能体

这是 Quantum Agent 的核心架构顺序。

\[
\boxed{
Course Materials
\rightarrow
Pedagogical Knowledge Graph
\rightarrow
Agent Runtime
}
\]

而不是：

```text
LLM
→ 问答
→ 后面再补一个知识图谱可视化
```

---

# 7. Pedagogical Knowledge Graph

## 7.1 知识图谱不是事实权威，而是课程的可审核语义骨架

权威边界：

```text
Original Course Material
    = 科学与课程事实的最终来源

PostgreSQL
    = 文档版本、候选知识、教师审核、provenance 的 system of record

Neo4j
    = 可重建的课程语义结构与关系索引

pgvector / FTS
    = 检索索引

LLM
    = 抽取候选、理解、诊断和生成
```

原则：

> **GraphRAG 负责“找到关系”，不负责宣布事实为真。**

---

## 7.2 图谱节点

### 课程结构

```text
Course
Chapter
Section
```

### 知识对象

```text
Concept
Principle
PhysicalSystem
MathematicalObject
Operator
QuantumState
Approximation
```

### 教学对象

```text
Formula
Symbol
Derivation
DerivationStep
Example
Exercise
Misconception
Hint
Assumption
ValidityCondition
```

### 科学实验对象

```text
Experiment
Visualization
Simulation
ScientificTask
Verifier
```

### 证据对象

```text
SourceDocument
SourceChunk
Evidence
Assertion
```

---

## 7.3 最重要的关系

```text
PART_OF
PREREQUISITE_OF
DEFINES
USES
DEPENDS_ON
DERIVES_FROM
APPLIES_TO
ACTS_ON
COMMUTES_WITH
HAS_EIGENSTATE
APPROXIMATES
VALID_UNDER
CONTRASTS_WITH
EQUIVALENT_REPRESENTATION
HAS_MISCONCEPTION
REMEDIATED_BY
VISUALIZED_BY
VERIFIED_BY
SUPPORTED_BY
EXTRACTED_FROM
```

其中对教学最重要的是：

```text
PREREQUISITE_OF
DERIVES_FROM
HAS_MISCONCEPTION
REMEDIATED_BY
VALID_UNDER
```

---

## 7.4 教师经验如何真正进入图谱

教师不是简单写一个 system prompt。

主讲教师真正需要审核和补充的是：

- 哪些概念必须先学；
- 哪两个概念学生经常混淆；
- 一条推导中最容易跳过的步骤；
- 某个近似在哪些条件下成立；
- 某个错误最适合用什么反例纠正；
- 某个知识点适合哪一种计算实验；
- 哪个新问题最适合用于迁移测试。

这使得：

\[
\text{20 年教学经验}
\rightarrow
\text{可持续积累的课程教学结构}
\]

---

## 7.5 Provenance 规则

所有学生可见课程断言必须满足：

```text
Assertion
→ Evidence
→ SourceChunk
→ Document Version
→ Page / Slide
```

LLM 自动抽取：

```text
REVIEW_REQUIRED
```

教师审核后：

```text
APPROVED
```

学生端只使用：

```text
PUBLISHED document
+
APPROVED assertion
```

---

# 8. Learning-Native Tutor Graph

## 8.1 核心原则

\[
\boxed{
\text{LLM proposes}
\quad
\text{Policy decides}
\quad
\text{Tools verify}
}
\]

### LLM 擅长

- 理解开放输入；
- 重建学生推理；
- 诊断复杂误区；
- 生成追问；
- 生成教学表达；
- 生成 task-specific scientific code。

### 确定性代码负责

- 是否必须先尝试；
- 是否允许释放完整答案；
- 当前 Learning Phase；
- 是否进入 Solo；
- 科学结果是否通过；
- 学习状态怎样迁移；
- 安全和权限。

---

## 8.2 Tutor Graph

```text
Input / Perception
        ↓
Commitment / Attempt
        ↓
Course Evidence
        ↓
Diagnosis
        ↓
Cognitive Governor
        ↓
┌───────────────────────────────────┐
│ Minimal Hint / Socratic / Explain │
│ Representation / Experiment       │
└───────────────────────────────────┘
        ↓
Scientific Verification (when needed)
        ↓
Reconstruction
        ↓
Teach-Back
        ↓
Transfer
        ↓
Solo
        ↓
Learning Evidence
        ↓
Cognitive Mirror
```

图是稳定的，但并非每个问题机械走全部节点。

例如：

- “什么是厄米算符？”可短路径；
- “我这个微扰推导为什么错？”进入诊断闭环；
- “隧穿概率为什么随势垒宽度下降这么快？”进入实验闭环。

---

# 9. 多智能体：少而清晰，不做 Agent Theatre

Quantum Agent 不追求 Agent 数量。

比赛版核心智能角色建议只有：

## 9.1 Perception Agent

负责：

> “学生给了什么？”

提取：

```text
text
equations
diagram_elements
derivation_steps
page / bbox
confidence
ambiguities
```

不负责判断正确性。

---

## 9.2 Evidence Agent

负责：

> “课程中有哪些可靠依据？”

输出：

```text
sources
passages
page_refs
concept_ids
graph_paths
coverage
conflicts
```

不决定怎么教。

---

## 9.3 Diagnosis Agent

负责：

> “学生现在的问题本质是什么？”

输出：

```text
target_concepts
prerequisite_gaps
first_consequential_error
misconception_candidates
confidence
verification_needed
```

---

## 9.4 Tutor Agent

负责：

> 在 policy 允许的帮助等级内，怎样把干预表达得最合适？

它不能：

- 绕过 Commitment Gate；
- 绕过 Solo；
- 把 FAIL 改成 PASS；
- 自己修改学习阶段。

---

## 9.5 Coding Agent

负责：

> 针对当前 ScientificTask 现场生成可执行代码。

必须生成 task-specific code，而不是调用预制答案伪装成“Agent 写的”。

---

## 9.6 哪些东西绝不 Agent 化

```text
Policy Gate
Permissions
Evidence approval
Scientific Verifier
Learning phase transition
Credential security
Database authority
```

---

# 10. 科学计算与验证

## 10.1 ScientificTask

统一任务合同：

```text
goal
known_parameters
required_outputs
allowed_libraries
scientific_constraints
verification_contract
```

---

## 10.2 Sandbox

生成代码的执行环境必须：

- 与 API 主进程隔离；
- no network；
- non-root；
- read-only root；
- cap_drop；
- no-new-privileges；
- import allowlist；
- AST safety；
- CPU / RAM / PID / wall-time 限制；
- bounded stdout / stderr。

---

## 10.3 Scientific Verifier

Verifier 输出只能是：

```text
PASS
FAIL
INCONCLUSIVE
```

可检查：

- finite；
- units；
- shape；
- normalization；
- probability conservation；
- boundary conditions；
- Hermiticity；
- commutator；
- symmetry；
- known limiting behavior；
- domain oracle。

关键规则：

> **Tutor 没有权力把科学验证失败包装成成功。**

---

# 11. Learning Evidence 与 Cognitive Mirror

## 11.1 不做虚假的“AI 掌握度”

不保存：

```text
mastery = 87.4%
```

保存真实行为：

```text
attempt
confidence
assistance_level
revision
answer_result
teach_back
transfer
solo
verification
source_interaction
timestamp
```

---

## 11.2 状态是推导出来的

```text
UNKNOWN
EXPOSED
DEVELOPING
DEMONSTRATED
TRANSFER_READY
```

原则：

> **Learner State is derived, not asserted.**

示例：

```text
Quantum Tunnelling — DEVELOPING

✓ 已完成一次正确的物理图像解释
✓ 能说明势垒内波函数为何指数衰减
✓ 完成 Teach-Back
△ 新参数条件下仍使用 L2 提示
✗ 尚无 Solo Transfer 证据
```

---

# 12. Teach-Back / Transfer / Solo

## 12.1 Teach Mode

角色反转：

```text
学生 = 老师
Quantum Agent = 学生
```

AI 可以：

- 追问“为什么”；
- 要求澄清；
- 要求给例子；
- 指出不一致；
- 要求换一种表示。

AI 不可以：

- 学生一卡住就自己讲完；
- 偷偷补全核心推导。

---

## 12.2 Transfer

给出：

> 表面不同，但依赖相同结构的新问题。

Transfer 不是“再做一道类似题”，而是验证概念是否迁移。

---

## 12.3 Solo

Solo 是真正撤除 AI 的阶段。

要求：

- 后端持久锁；
- 禁止提示；
- 禁止完整答案；
- Evidence 不主动展开；
- 刷新不能逃逸；
- 学生提交后才给反馈。

只有这样，系统才能产生：

```text
unaided evidence
```

---

# 13. 多模态：给教学系统“眼睛”

Quantum Agent 支持：

```text
Text
Image / Screenshot
Handwriting
PDF / Document
```

典型用途：

- 上传手写推导；
- 截图教材/PPT；
- 上传作业；
- 选择 PDF 某一页；
- 看图判断波函数/势能曲线。

职责分离：

> **Perception 判断“看到了什么”；Diagnosis / Verifier 判断“是否正确”。**

低置信度必须明确告诉学生并请求确认，不能假装识别成功。

---

# 14. USTC_API 与 Capability Router

## 14.1 核心思想

业务代码不绑定模型名。

```text
Task
 ↓
Capability
 ↓
Capability Router
 ↓
health / latency / quality / fallback
 ↓
USTC_API model
```

业务模块只声明自己需要：

```text
FAST_CLASSIFICATION
FAST_CHAT
DEEP_REASONING
CODING
VISION
OCR
DOCUMENT_PARSE
EMBEDDING
RERANK
```

---

## 14.2 为什么不能固定“一个 Agent = 一个模型”

不同模型在以下维度不断变化：

- 推理质量；
- 图像理解；
- 代码生成；
- 延迟；
- 稳定性；
- 限流；
- 格式遵从。

因此真实路由应该基于 Quantum Agent 自己的量子物理评测集：

\[
score =
f(
accuracy,
latency,
format\ adherence,
tool\ success,
stability
)
\]

---

## 14.3 当前可用模型池

当前项目可通过 `USTC_API` 调用的模型包括：

```text
glm-5.2-107
deepseek-v4-pro
deepseek-v4-flash
smart/default
smart/reasoning
qwen3.6-chat
qwen-reasoner
qwen-chat
deepseek-v4-flash-ascend
qwen3.6-reasoner
glm-reasoner
glm-chat
deepseek-reasoner
deepseek-chat
unlimited-ocr
qwen3-embedding
qwen3-reranker
mineru
glm-5.2
deepseek-v4-flash-ascend1
qwen3.8-chat
qwen3.8-reasoner
glm-5.3-flash
```

这些模型不是产品卖点本身。

真正的卖点是：

> **统一能力路由让模型可以替换，而教学逻辑、课程证据和学习状态不会跟着某个模型一起消失。**

---

# 15. One Event Stream：让学生看见系统在“工作”，但不泄露内部思维链

长任务不能让学生盯着 Spinner。

公开：

```text
workflow.started
evidence.started
evidence.completed
diagnosis.started
diagnosis.completed
strategy.selected
coding.started
coding.generated
sandbox.started
sandbox.completed
verification.started
verification.pass
teachback.requested
transfer.started
solo.entered
workflow.completed
```

公开的是：

- 当前阶段；
- 当前 Agent / 工具职责；
- 简要结果；
- 耗时；
- Artifact；
- 来源。

不公开：

- hidden chain-of-thought；
- 内部模型推理草稿；
- 安全敏感 trace。

---

# 16. One Learning Stage：前端设计原则

## 16.1 视觉核心只有一个

整个学生端中央 75%–85% 视觉区域：

# **Scientific Learning Stage**

它根据当前 Learning Phase 自动变形。

例如：

```text
COMMITMENT
→ Prediction / Attempt

DIAGNOSIS
→ Highlight student reasoning

DERIVATION
→ Equation bridge

EXPERIMENT
→ Plot / Code / Simulation

TEACH_BACK
→ Teach Mode

TRANSFER
→ New problem

SOLO
→ Distraction-free workspace

COMPLETE
→ Cognitive Mirror
```

---

## 16.2 其他模块全部退到第二层

默认收起/悬浮：

```text
Course Graph
Sources
Learning Evidence
Agent Activity
Settings
```

学生不应该面对后台 Dashboard。

---

## 16.3 视觉风格

关键词：

```text
academic
scientific
quiet
precise
modern
instrument-like
mathematical
```

避免：

- 霓虹赛博朋克；
- 大量等权卡片；
- 发光边框；
- 机器人头像；
- 多 Agent 表演；
- 无意义动画。

科学美感来自：

- 大量留白；
- 高质量数学排版；
- 方程；
- 图；
- 能级；
- 谱线；
- 状态变化；
- 清晰的信息层级。

---

## 16.4 知识图谱不能默认画成“大毛线球”

默认展示：

# Concept Neighborhood

只显示当前概念附近：

- 1–2 层 prerequisite；
- 当前依赖；
- downstream；
- 易混淆节点；
- 当前学生状态。

需要时再展开。

---

# 17. 课程覆盖边界

Competition Release 的知识边界以中国科学技术大学 2026 秋《量子物理》教学大纲和提供的课程资料为主。

课程主线覆盖：

```text
原子模型与旧量子论
→ 量子力学基础
→ 表象理论与矩阵力学
→ 原子结构
→ 近似理论方法
→ 双原子分子
→ 分子光谱
```

典型重点：

- 波粒二象性；
- 不确定性；
- 波函数；
- Schrödinger 方程；
- 势箱；
- 谐振子；
- 隧穿；
- 算符与测量；
- 角动量；
- Hilbert 空间与表象；
- 单电子与多电子原子；
- 自旋与角动量耦合；
- 微扰；
- 变分；
- MO；
- 分子振转光谱；
- 电子光谱与选择定则。

参考教材可以帮助解释，但**课程正式材料优先于模型记忆**。

---

# 18. 当前工程底座与比赛版收敛

## 18.1 已形成的主技术栈

```text
Frontend
Next.js / React

Backend
Python 3.12
FastAPI
LangGraph

Data
PostgreSQL
pgvector
Neo4j
Redis

AI
USTC OpenAI-compatible API
Capability Router
Vision / OCR / Embedding / Rerank

Scientific
Coding Agent
Python
NumPy / SciPy / SymPy / QuTiP
Isolated Sandbox
Deterministic Verifier

Learning
Commitment Gate
Evidence
Diagnosis
Teach-Back
Transfer
Solo
Learning Evidence
Cognitive Mirror
```

---

## 18.2 当前架构权威

只保留一个业务权威：

> **Python / FastAPI / LangGraph backend**

TypeScript 层只作为 Web UI 与必要 adapter，不再维护平行教学业务逻辑。

---

## 18.3 比赛前原则

```text
Preserve
→ Integrate
→ Complete
→ Optimize
→ Demonstrate
```

不再大规模扩张功能。

比赛前的工程工作只围绕：

1. 真正跑通全部 Golden Loop；
2. 提高每一步可见性；
3. 降低等待时间；
4. 确保流式事件；
5. 确保多模态真实可用；
6. 确保知识图谱和来源真实展示；
7. 确保 Coding Agent 真生成代码；
8. 确保 Sandbox / Verifier 真执行；
9. 确保 Teach-Back / Transfer / Solo 真能进入；
10. 做好 5 分钟演示。

---

# 19. 外部优秀项目：只吸收精髓，不复制产品

Quantum Agent 的核心叙事来自自己的教学实践。外部项目只用于验证和改进工程/教学方法。

## 19.1 OpenMAIC

值得吸收：

- Classroom as runtime；
- Stage / Scene；
- interactive simulation；
- action-level playback；
- 科学交互组件；
- 集中的工作台体验。

不照搬：

- AI classmates；
- 大量 Avatar/TTS；
- 泛课程自动生成作为主线。

OpenMAIC 2026 年版本持续强化 interactive scenes、simulation、PBL、server-backed runtime、action-level playback 和 agent workbench，这说明“教学过程作为可执行 Runtime”是一个有价值的方向。

---

## 19.2 DeepTutor

值得吸收：

- agent-native runtime；
- restart-safe turn；
- 持久学习上下文；
- 三层 memory / inspectable history；
- RAG、工具、代码共享同一个学习空间。

Quantum Agent 的进一步改造：

> memory 不是“模型记住学生说过什么”，而是“系统保留可审计的学习证据”。

---

## 19.3 Tutor CoPilot

其随机对照研究的关键启发不是某个 UI，而是：

- 高质量 tutoring 更强调 guiding questions / scaffolding；
- 更少直接泄露答案；
- AI 可以帮助教学者采用更好的教学策略。

这与 Quantum Agent 的：

```text
Commitment
→ Diagnosis
→ Minimal Intervention
```

高度一致。

---

## 19.4 Physics Education Research

物理教育中的 worked example / self-explanation 研究支持：

- 学生自己解释解题步骤；
- 识别每一步的 principle / goal / condition；
- 通过自我解释和迁移，而不是只被动阅读完整解答。

因此 Teach-Back、Derivation Bridge、Reconstruction 不应该是“附加功能”，而是核心学习机制。

---

# 20. 核心创新与主要卖点

## 卖点 1：一线教学经验驱动，而不是技术堆叠驱动

```text
Real teaching problem
→ product design
→ technical architecture
```

这是项目最难复制的部分。

---

## 卖点 2：先理解学生的思路，再给答案

大多数 AI：

```text
Question → Solution
```

Quantum Agent：

```text
Student Reasoning
→ Diagnosis
→ First Consequential Error
→ Minimal Help
```

---

## 卖点 3：知识图谱不是展示，而是智能体的课程世界模型

用于：

- prerequisite reasoning；
- derivation path；
- misconception；
- cross-chapter relation；
- evidence grounding；
- transfer generation。

---

## 卖点 4：真正补教材/PPT 的“跳步”

Derivation Bridge 将教师隐含的中间逻辑变成学生可交互的学习结构。

---

## 卖点 5：真正生成并执行科学代码

不是“模型说这里可以画图”。

而是：

```text
Coding Agent
→ Code
→ Sandbox
→ Scientific Verifier
→ Artifact
```

---

## 卖点 6：科学正确性不由 LLM 裁决

```text
LLM proposes
Tools verify
```

这是科研/理工类教育 Agent 的可信基础。

---

## 卖点 7：Learning-Native，而不是 Answer-Native

真正的结束条件不是：

> AI 回答完毕。

而是：

```text
Student reconstructed
Student taught it back
Student transferred it
Student solved unaided
```

---

## 卖点 8：多模态真正服务于教学诊断

“眼睛”不是为了展示“支持图片”，而是为了：

> 直接看学生写的东西。

---

## 卖点 9：后台复杂，前台极简

```text
Deep system
Simple experience
```

中央永远只有一个 Scientific Learning Stage。

---

## 卖点 10：适合量子物理，而不是把通用 Tutor 换一个 Logo

量子物理本身高度适合：

```text
概念关系
+ 数学推导
+ 多表示
+ 可视化
+ 数值计算
+ 科学验证
```

因此 Quantum Agent 的技术组合来自学科本身。

---

# 21. 与“一〇七杯”评分标准的对应关系

## 创新性

### 场景创新
来自真实本科量子物理课程的一线助教问题，而非抽象 AI 教育命题。

### 交互创新
不是聊天框，而是动态 Scientific Learning Stage。

### 多智能体协作
Evidence / Diagnosis / Tutor / Coding Agent 分工明确，Policy 与 Verifier 保持确定性。

---

## 实用性

### 真实场景
直接服务中国科大学生当前课程。

### 解决方案有效性
对应三个最常见困难：

```text
思路有问题
PPT 有跳步
计算量太大
```

### 可推广性
框架可迁移至：

- 数学；
- 理论物理；
- 物理化学；
- 量子化学；
- 电动力学；
- 统计物理；
- 其他高推导密度 STEM 课程。

---

## 技术难度

- 多模态；
- RAG；
- 知识图谱；
- LangGraph；
- 多 Agent；
- streaming；
- code generation；
- sandbox；
- scientific verifier；
- learning state；
- session credential routing；
- PostgreSQL / pgvector / Neo4j / Redis。

关键是这些技术有明确教育功能，不是堆栈。

---

## 完成度

比赛演示必须展示真实：

```text
登录
→ 上传/输入
→ Commitment
→ Evidence
→ Diagnosis
→ Scientific Action
→ Verification
→ Teach-Back
→ Transfer
→ Solo
→ Cognitive Mirror
```

---

# 22. Golden Demo：5 分钟只讲三个故事

## Demo A：我的推导错在哪里？

学生上传手写推导。

展示：

```text
Vision
→ reasoning reconstruction
→ evidence
→ first consequential error
→ minimal hint
```

证明：

> Quantum Agent 看的是学生的思路，不只是题目。

---

## Demo B：PPT 为什么突然跳到这里？

学生选中两行公式。

展示：

```text
Knowledge Graph
→ prerequisite
→ source page
→ missing steps
→ derivation bridge
```

证明：

> Knowledge Graph 不是装饰。

---

## Demo C：隧穿到底有多小？

学生先预测势垒宽度变化会怎样。

展示：

```text
Prediction
→ Coding Agent
→ generated Python
→ Sandbox
→ Verifier PASS
→ Plot
→ change parameter
→ explain observation
```

证明：

> Agent 真的在做科学计算。

最后：

```text
Teach-Back
→ Transfer
→ Solo
→ Cognitive Mirror
```

落在一句话：

> **我们不因为 AI 给出了正确答案就认为教学结束。只有当学生能够自己解释、迁移，并在撤去 AI 后独立完成，Quantum Agent 才认为这次 Learning Episode 真正完成。**

---

# 23. 成功指标

不要把核心 KPI 定义成：

- 回答长度；
- 聊天次数；
- token 数；
- AI 使用时长。

优先指标：

```text
first consequential error localization accuracy
source grounding accuracy
answer leakage rate
hint level used
student revision success
teach-back success
transfer success
solo success
scientific verifier pass rate
model latency
time to first useful event
end-to-end Golden Loop completion
```

长期教育指标：

```text
independent post-test
delayed retention
transfer
self-explanation quality
hint dependence
confidence calibration
```

---

# 24. 产品哲学：四种权威必须分离

| 权威 | 回答的问题 | 裁决者 |
|---|---|---|
| 课程知识权威 | 课程里究竟讲了什么？ | Published course materials + teacher-reviewed KG |
| 教学权威 | 此刻应该帮助到什么程度？ | Teacher policy + deterministic Cognitive Governor |
| 科学权威 | 数值、代码、公式约束是否成立？ | Deterministic tools / Sandbox / Verifier |
| 语言智能 | 怎样理解、诊断、追问和表达？ | LLM / specialist agents |

核心思想：

> **不要把四种权威都交给一个大模型。**

---

# 25. 最终项目公式

可以用一个公式完整描述 Quantum Agent：

\[
\boxed{
\text{Quantum Agent}
=
\text{Frontline Teaching Experience}
+
\text{Pedagogical Knowledge Graph}
+
\text{Learning-Native Tutor Graph}
+
\text{Multimodal Agents}
+
\text{Scientific Computing}
+
\text{Deterministic Verification}
+
\text{Learning Evidence}
}
\]

更适合比赛答辩的一句话：

> **Quantum Agent 把中国科大量子物理一线教学经验编码成一个以课程知识图谱为认知骨架、以 Learning-Native 工作流为教学约束、以多智能体为智能执行单元、以科学工具为事实裁判，并最终以学生无辅助能力为目标的 AI 教学系统。**

---

# 26. 最终核心原则

如果未来所有功能发生争论，只问十个问题：

1. 它是否来自真实教学问题？
2. 它是否让系统更理解学生怎么想？
3. 它是否利用了课程材料和知识图谱？
4. 它是否帮助补全学生真正缺失的推理？
5. 它是否避免不必要的答案泄漏？
6. 它是否让量子物理从“文字”变成“可计算、可观察”？
7. 它的科学结论是否可以被工具验证？
8. 它是否产生了新的学习证据？
9. 它是否让学生更接近脱离 AI 独立完成？
10. 它是否值得占据比赛前宝贵的开发时间？

如果前九个都是否，而第十个是“只是看起来更炫”，就不做。

---

# 27. 项目结束语

Quantum Agent 的真正价值不在于：

> “我们使用了 LangGraph、Neo4j、pgvector、Redis、RAG、多模态和多个大模型。”

而在于：

> **我们把真实教师和助教在一线教学中最宝贵的判断——什么时候先让学生想、怎样判断他错在哪里、哪些步骤必须补、什么时候应该算一遍、怎样确认他最终真的会了——第一次尝试编码成了一个可运行、可验证、可持续积累的 AI 教学系统。**

技术最终应该退到背景。

学生看到的只有一件事：

> **眼前这个系统，真的在教我学会量子物理。**

---

# 附录 A：Competition Freeze 清单

## 必须保留

- Python / FastAPI 权威后端
- LangGraph Tutor Graph
- 课程知识图谱
- PostgreSQL + pgvector
- Neo4j
- Redis
- Evidence Agent
- Diagnosis Agent
- Perception / Multimodal
- Commitment Gate
- Cognitive Governor
- Tutor Agent
- Coding Agent
- Isolated Sandbox
- Scientific Verifier
- Teach-Back
- Transfer
- Solo
- Learning Evidence
- Cognitive Mirror
- USTC Model Gateway / Capability Router
- Server-side credential vault
- Real E2E Golden Loop
- Scientific Learning Stage

## 比赛前停止扩张

- 新 Agent
- 新学习功能
- 新通用平台能力
- AI classmates
- Flashcards
- FSRS
- Planner
- 课程自动生成
- 大型教师 BI
- 复杂动画体系
- 与 Golden Loop 无关的重构

---

# 附录 B：方案依据

本方案由以下材料共同收敛而来：

## 项目内部材料

- 当前 `核心方案.md`
- 当前 `PRD.md`
- `CLAUDE.md`
- 独立 Final Review
- 开源项目调研 `ref.md`
- “一〇七杯”智能体赛道提交与评分说明

## 课程材料

- 《量子物理》2026 秋教学大纲
- 第一至第八章课程 PPT / 讲义
- Yan, *Quantum Physics*
- Griffiths, *Introduction to Quantum Mechanics*
- Weinberg, *Lectures on Quantum Mechanics*
- 课程知识图谱 taxonomy

## 外部方法与工程参考

- THU-MAIC / OpenMAIC
- HKUDS / DeepTutor
- Tutor CoPilot
- Physics Education Research 关于 worked examples / self-explanation 的研究

原则：

> **外部项目提供工程和教育方法启发；Quantum Agent 的核心问题定义、核心叙事和产品边界来自中国科大量子物理真实教学实践。**
