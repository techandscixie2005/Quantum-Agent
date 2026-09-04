# Quantum Agent 参考文献调研报告

**文件名**：`articleref.md`  
**调研日期**：2026-09-01  
**项目**：Quantum Agent — 面向中国科学技术大学《量子物理》课程的 Learning-Native AI 助教  
**筛选原则**：最先进、最权威、与项目核心叙事直接相关；宁缺毋滥。

---

## 0. 执行摘要

Quantum Agent 的核心并不是“让大模型更会回答量子物理问题”，而是把一次学习从：

```text
Question → Answer
```

重构为：

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

因此，本项目真正需要的参考文献不是泛泛的“AI + 教育”论文，而应能回答三组问题：

1. **为什么不能让生成式 AI 直接把答案交给学生？**
2. **为什么需要先尝试、诊断、最小支架、自我解释、Teach-Back、Transfer，并最终撤除 AI？**
3. **为什么课程知识、科学计算与物理正确性不能完全交给 LLM，而需要检索、知识结构、程序执行和外部验证？**

经筛选，建议将参考文献分成三层：

- **A 层：教育科学核心证据**——用于作品简介、设计文档和核心叙事；
- **B 层：技术方法核心文献**——用于架构设计与技术创新说明；
- **C 层：前沿 AI Tutor 系统**——用于 Related Work / 前沿对比，不承担核心理论论证。

如果比赛材料篇幅有限，优先保留本文第 5 节列出的 **8 篇核心文献**。

---

# 1. 最重要的结论：Quantum Agent 的核心问题有强实证依据

当前最值得作为项目开篇背景的两篇文章是：

- **Bastani et al., PNAS 2025**
- **Kestin et al., Scientific Reports 2025**

二者放在一起，形成了一组非常清晰的张力。

一方面，Kestin 等在真实大学物理课程的随机对照实验中发现，经过学习科学原则设计的 AI tutor 可以让学生在更短时间内获得显著更高的学习增益；其 AI 组的中位学习增益超过课堂 active learning 组的两倍。

另一方面，Bastani 等在近千名高中数学学生的现场实验中发现：普通 GPT 辅助虽然让练习阶段成绩提高约 48%，但撤去 AI 后，学生考试表现反而比从未使用 AI 的对照组低约 17%；而加入专门“保护学习”的 tutoring guardrails 后，这种负面效应基本被消除。

这说明：

> **真正的问题不是“AI 能否帮助学生把题做出来”，而是“AI 的即时能力增益能否转化为学生脱离 AI 后仍然存在的能力”。**

这正是 Quantum Agent 中 Commitment Gate、Minimal Intervention、Teach-Back、Transfer 与 Solo Mode 的理论落点。

---

# 2. A 层：教育科学核心文献

## A1. Bastani et al. (2025) — 生成式 AI 必须有 learning guardrails

**文献**

Hamsa Bastani, Osbert Bastani, Alp Sungu, Haosen Ge, Özge Kabakcı, Rei Mariman.  
**Generative AI without guardrails can harm learning: Evidence from high school mathematics.**  
*Proceedings of the National Academy of Sciences (PNAS)*, 122(26), e2422633122, 2025.  
DOI: https://doi.org/10.1073/pnas.2422633122

**权威性**

- PNAS；
- 接近 1000 名学生的真实课堂 field experiment；
- 直接研究生成式 AI 对“即时表现”和“脱离 AI 后学习效果”的差异。

**关键结果**

- GPT Base 在 AI 可用的练习阶段使成绩提高约 **48%**；
- GPT Tutor（加入教师设计提示与学习保护机制）使练习表现提高约 **127%**；
- 撤掉 AI 后，GPT Base 组考试成绩比对照组低约 **17%**；
- 加入学习 guardrails 的 GPT Tutor 基本消除了这一负面学习效应。

**对 Quantum Agent 的意义**

这是项目最重要的外部依据之一，可直接支撑：

```text
Commitment Gate
Minimal Intervention
Answer withholding
Teach-Back
Transfer
Solo Mode
Think with AI → Think without AI
```

Quantum Agent 不应优化：

\[
\min(\text{得到答案的时间})
\]

而应优化：

\[
\max P(\text{撤除 AI 后仍能独立解决新问题})
\]

---

## A2. Kestin et al. (2025) — 教学设计良好的 AI Tutor 可以真正提高大学物理学习

**文献**

Greg Kestin, Kelly Miller, Anna Klales, Timothy Milbourne, Gregorio Ponti.  
**AI tutoring outperforms in-class active learning: an RCT introducing a novel research-based design in an authentic educational setting.**  
*Scientific Reports*, 15, 17458, 2025.  
DOI: https://doi.org/10.1038/s41598-025-97652-6

**权威性**

- Nature Portfolio 旗下 *Scientific Reports*；
- Randomized Controlled Trial；
- 真实大学物理课程；
- 与 Quantum Agent 的学科场景高度一致。

**关键结果**

- AI tutor 组学习增益显著高于课堂 active learning 组；
- AI tutor 组的中位学习增益超过课堂组的两倍；
- 学生完成学习所需时间更短；
- 论文明确指出，AI tutor 的设计基于 active learning、scaffolding、及时反馈、准确性、自定步调等学习科学原则。

**对 Quantum Agent 的意义**

这篇文章说明：

> **“AI tutor 有效”并不是因为模型会聊天，而是因为教学原则被编码进系统。**

因此可支撑：

```text
Pedagogy defines the constraints
Cognitive Governor
Assistance Ladder
Targeted feedback
Deterministic teaching policy
```

---

## A3. Miller, Miller & Lawrence (2026) — 大学物理问题求解应强调显式框架与 deliberate practice

**文献**

Kelly Miller, Olivia Miller, Georgia Lawrence.  
**Teaching problem solving in undergraduate physics courses: An endorsement for deliberate practice.**  
*Physical Review Physics Education Research*, 22, 020121, 2026.  
DOI: https://doi.org/10.1103/7pqt-gd9c

**权威性**

- American Physical Society；
- *Physical Review Physics Education Research*；
- 2026 年最新大学物理教育研究；
- 与 Quantum Agent “诊断学生解题过程”直接相关。

**主要结论**

显式教授问题求解框架，并配合有针对性的 deliberate practice 与 feedback，比简单重复刷题更能形成接近专家的解题行为。

**对 Quantum Agent 的意义**

直接支撑：

```text
Student Attempt
→ Diagnosis
→ first consequential error
→ targeted feedback
→ reconstruction
```

尤其适合解释为什么系统不是“重新给一份标准解答”，而是先理解学生当前的解题路径。

---

## A4. Sinha & Kapur (2021) — Productive Failure：先尝试，再教学

**文献**

Tanmay Sinha, Manu Kapur.  
**When Problem Solving Followed by Instruction Works: Evidence for Productive Failure.**  
*Review of Educational Research*, 91(5), 761–798, 2021.  
DOI: https://doi.org/10.3102/00346543211019105

**权威性**

- *Review of Educational Research*；
- 53 项研究、166 个比较的 meta-analysis。

**关键结果**

Problem Solving → Instruction（先问题求解，再接受教学）相对于 Instruction → Problem Solving 总体具有显著优势，meta-analysis 的总体效应约为 Hedges' \(g=0.36\)；严格遵循 Productive Failure 设计时效应更强。

**对 Quantum Agent 的意义**

这是 **Commitment Gate** 的关键理论依据。

Quantum Agent 要求学生先给出：

- 一个预测；
- 一步推导；
- 一个物理理由；
- 一个选择；
- 或明确说“不知道”。

之后才进入更完整的教学干预。

这不是人为增加交互步骤，而是符合 productive failure / preparation-for-learning 的研究传统。

---

## A5. Chi & Wylie (2014) — ICAP：从被动接受走向构建与互动

**文献**

Michelene T. H. Chi, Ruth Wylie.  
**The ICAP Framework: Linking Cognitive Engagement to Active Learning Outcomes.**  
*Educational Psychologist*, 49(4), 219–243, 2014.  
DOI: https://doi.org/10.1080/00461520.2014.965823

**核心框架**

ICAP 将学习行为分为：

```text
Passive
↓
Active
↓
Constructive
↓
Interactive
```

并提出更高层次的认知参与通常产生更好的学习结果。

**对 Quantum Agent 的意义**

传统 Chatbot 很容易把学生变成：

```text
Passive reader of AI answers
```

Quantum Agent 则通过：

```text
Prediction
Derivation
Reconstruction
Teach-Back
Interactive questioning
Transfer
```

把学生推向 Constructive / Interactive。

这也是 “Learning-Native” 比 “Answer-Native” 更准确的理论表述。

---

## A6. Chi et al. (1994) — Self-Explanation：真正理解需要学生自己解释

**文献**

Michelene T. H. Chi, Nicholas de Leeuw, Mei-Hung Chiu, Christian LaVancher.  
**Eliciting Self-Explanations Improves Understanding.**  
*Cognitive Science*, 18(3), 439–477, 1994.  
DOI: https://doi.org/10.1016/0364-0213(94)90016-7

**核心结论**

主动生成 self-explanation 能促进新知识与已有知识的整合，并提升深层理解。

**对 Quantum Agent 的意义**

直接支撑：

```text
Reconstruction
Explain why
Teach-Back
Student-generated derivation
```

Quantum Agent 不应在解释之后问一句：

> “明白了吗？”

而应要求学生重新构建或解释关键逻辑。

---

## A7. Kobayashi (2019) — Learning by Teaching：Teach-Back 有 meta-analysis 支持

**文献**

Keiichi Kobayashi.  
**Learning by Preparing-to-Teach and Teaching: A Meta-Analysis.**  
*Japanese Psychological Research*, 61(3), 192–203, 2019.  
DOI: https://doi.org/10.1111/jpr.12221

**权威性**

- 28 项研究 meta-analysis。

**关键结果**

- preparing-to-teach：Hedges' \(g \approx 0.35\)；
- teaching after preparing：\(g \approx 0.56\)；
- 互动式 teaching 的学习收益更明显。

**对 Quantum Agent 的意义**

这直接支撑 **Teach Mode**：

```text
Student = Teacher
Quantum Agent = Student
```

AI 通过追问：

- 为什么？
- 这个结论依赖什么？
- 能不能给一个反例？
- 换一种表示还能解释吗？

让学生把“会看答案”转化为“会组织、解释与捍卫知识”。

---

## A8. Butler (2010) — Transfer：真正学习要能解决新问题

**文献**

Andrew C. Butler.  
**Repeated testing produces superior transfer of learning relative to repeated studying.**  
*Journal of Experimental Psychology: Learning, Memory, and Cognition*, 36(5), 1118–1133, 2010.  
DOI: https://doi.org/10.1037/a0019902

**核心结论**

主动检索与测试不仅提升记忆，还能显著促进对新问题、新推理情境的 transfer。

**对 Quantum Agent 的意义**

支撑：

```text
Original Problem
≠ Learning Completion

Original Problem
→ Reconstruction
→ Transfer Task
→ Solo
```

学生能复现原题，并不意味着已经掌握；必须验证其是否能在表面不同但结构相似的新情境中迁移。

---

## A9. Belland et al. (2017) — STEM 计算机支架的 meta-analysis

**文献**

Brian R. Belland, Andrew E. Walker, Nam Ju Kim, Mason Lefler.  
**Synthesizing Results From Empirical Research on Computer-Based Scaffolding in STEM Education: A Meta-Analysis.**  
*Review of Educational Research*, 87(2), 309–344, 2017.  
DOI: https://doi.org/10.3102/0034654316670999

**权威性**

- 144 项实验研究；
- 333 个 outcome；
- STEM education；
- 大型 meta-analysis。

**对 Quantum Agent 的意义**

支撑 Assistance Ladder：

```text
L0 Student generation
L1 Attention cue
L2 Minimal hint
L3 Socratic / contrastive question
L4 Representation translation
L5 Partial worked step
L6 Full explanation
```

“支架”是暂时帮助学生完成当前无法独立完成的认知活动，而不是永久替代学生。

---

## A10. VanLehn (2011) — Intelligent Tutoring Systems 的经典基准

**文献**

Kurt VanLehn.  
**The Relative Effectiveness of Human Tutoring, Intelligent Tutoring Systems, and Other Tutoring Systems.**  
*Educational Psychologist*, 46(4), 197–221, 2011.  
DOI: https://doi.org/10.1080/00461520.2011.611369

**核心贡献**

系统比较 human tutoring、intelligent tutoring systems 和其他教学系统，并区分：

- answer-based；
- step-based；
- substep-based tutoring。

**对 Quantum Agent 的意义**

Quantum Agent 应尽量成为：

```text
reasoning-process-aware / step-aware tutor
```

而不是：

```text
final-answer checker
```

其 Diagnosis Agent、first consequential error 定位与推导补全，都可以放在这一 ITS 传统中理解。

---

# 3. B 层：技术方法核心文献

## B1. Lewis et al. (2020) — Retrieval-Augmented Generation

**文献**

Patrick Lewis et al.  
**Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.**  
*Advances in Neural Information Processing Systems (NeurIPS 2020)*, 33, 9459–9474.  
Official page:  
https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html

**核心意义**

RAG 将：

```text
parametric memory
+
non-parametric external memory
```

结合起来，并明确讨论了纯参数模型在知识更新、事实性与 provenance 上的局限。

**对 Quantum Agent 的意义**

直接支撑：

```text
Course material = factual authority
Retriever / pgvector = index
LLM = reasoning & explanation
EvidenceBundle = inspectable provenance
```

Quantum Agent 不应让模型凭参数记忆自由回答课程事实。

---

## B2. Hogan et al. (2021) — Knowledge Graphs 权威综述

**文献**

Aidan Hogan, Eva Blomqvist, Michael Cochez, Claudia d'Amato, Gerard de Melo, Claudio Gutierrez, Sabrina Kirrane, José Emilio Labra Gayo, Roberto Navigli, Sebastian Neumaier, Axel-Cyrille Ngonga Ngomo, Axel Polleres, Sabbir M. Rashid, Anisa Rula, Lukas Schmelzeisen, Juan Sequeda, Steffen Staab, Antoine Zimmermann.  
**Knowledge Graphs.**  
*ACM Computing Surveys*, 54(4), Article 71, 2021.  
DOI: https://doi.org/10.1145/3447772

**核心意义**

这是知识图谱领域最值得引用的综合性权威综述之一，覆盖：

- graph data models；
- ontologies；
- graph querying；
- validation；
- knowledge extraction；
- deductive / inductive reasoning；
- embeddings。

**对 Quantum Agent 的意义**

支撑 Pedagogical Knowledge Graph 的技术合理性：

```text
concept
prerequisite
derivation
misconception
evidence
cross-chapter relation
```

同时也提醒：Neo4j/Graph 本身不是事实源，知识图谱需要 provenance、validation 与治理。

---

## B3. Gao et al. (2023) — PAL：让 LLM 写程序，让解释器负责计算

**文献**

Luyu Gao, Aman Madaan, Shuyan Zhou, Uri Alon, Pengfei Liu, Yiming Yang, Jamie Callan, Graham Neubig.  
**PAL: Program-aided Language Models.**  
*Proceedings of the 40th International Conference on Machine Learning (ICML 2023)*, PMLR 202:10764–10799.  
Official page: https://proceedings.mlr.press/v202/gao23f.html

**核心思想**

LLM 擅长：

```text
understand
decompose
generate program
```

但容易在实际算术与符号推理中犯错。

因此 PAL 将最终求值交给 Python interpreter。

**对 Quantum Agent 的意义**

直接对应：

```text
ScientificTask
→ Coding Agent
→ task-specific Python
→ isolated runtime
```

Quantum Agent 在此基础上进一步加入：

```text
Static Safety
Sandbox
Scientific Verifier
PASS / FAIL / INCONCLUSIVE
```

因此比一般 Program-Aided Reasoning 更适合科学教学。

---

## B4. Gou et al. (2024) — CRITIC：外部工具比纯语言自我反思更可靠

**文献**

Zhibin Gou, Zhihong Shao, Yeyun Gong, Yelong Shen, Yujiu Yang, Nan Duan, Weizhu Chen.  
**CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing.**  
*International Conference on Learning Representations (ICLR 2024).*  
OpenReview: https://openreview.net/forum?id=Sx038qxjek

**核心思想**

让模型访问外部工具，对事实、代码或推理结果进行交互式检查，而不是完全依赖模型自身“反思”。

**对 Quantum Agent 的意义**

直接支撑：

```text
LLM proposes
Policy decides
Tools verify
```

尤其对应 Scientific Verifier：

```text
PASS
FAIL
INCONCLUSIVE
```

并支持一个重要设计原则：

> Tutor Agent 没有权把科学工具的 FAIL 或 INCONCLUSIVE 改写成 PASS。

---

# 4. C 层：前沿 AI Tutor / Human-AI 教育系统

这一层值得研究，但不建议替代 A 层同行评审教育科学论文作为主理论依据。

---

## C1. LearnLM (Google DeepMind / Google Research)

**文献**

LearnLM Team et al.  
**LearnLM: Improving Gemini for Learning.**  
arXiv:2412.16429, 2024.  
https://arxiv.org/abs/2412.16429

**前沿价值**

LearnLM 将“让大模型会教学”表述为：

> **pedagogical instruction following**

其核心思想不是让模型默认呈现信息，而是让开发者/教师显式规定：

- 如何给提示；
- 如何维持学习目标；
- 如何调整难度；
- 如何促进主动参与；
- 如何避免直接替学生完成认知工作。

Google 后续继续将 LearnLM 能力整合进 Gemini，并发布了多轮教育评测与 RCT 报告。

**对 Quantum Agent 的意义**

LearnLM 与 Quantum Agent 的共同点：

```text
Pedagogy must be first-class
```

不同点在于：

- LearnLM 更强调模型层面的 pedagogical behavior；
- Quantum Agent 更强调 **系统层面的 deterministic pedagogical governance**。

这反而可以成为 Quantum Agent 的一个技术辨识度：

> 教学规则不只写在 prompt 里，而进入 Tutor Graph、Gate、Policy、LearningPhase 和后端状态机。

---

## C2. Tutor CoPilot (Stanford)

**文献**

Rose E. Wang, Ana T. Ribeiro, Carly D. Robinson, Susanna Loeb, Dorottya Demszky.  
**Tutor CoPilot: A Human-AI Approach for Scaling Real-Time Expertise.**  
Working paper / Stanford SCALE & National Student Support Accelerator, 2024–2025.  
arXiv: https://arxiv.org/abs/2410.03017

**主要价值**

真实 tutoring RCT 表明，AI 可以通过建议更好的教学策略来帮助 tutor，而不仅仅生成答案；系统促使 tutor：

- 更多使用 probing / guiding questions；
- 更少直接给答案；
- 更接近高质量教师的教学行为。

**对 Quantum Agent 的意义**

支撑：

```text
AI as pedagogy-supporting system
rather than answer engine
```

但由于其当前主要以 working paper / technical report 形式存在，建议放在 Related Work，而非最核心文献列表。

---

# 5. 比赛材料篇幅有限时：只保留这 8 篇

如果“作品简介”只允许出现很短的参考文献列表，推荐如下：

### 教育科学 6 篇

1. **Bastani et al., PNAS 2025**  
   AI without guardrails can harm learning  
   → 为什么必须有 Commitment / Solo / guardrails。

2. **Kestin et al., Scientific Reports 2025**  
   AI tutoring in university physics RCT  
   → 为什么 research-based AI tutor 可以真正提高学习。

3. **Miller et al., PRPER 2026**  
   deliberate practice in undergraduate physics  
   → 为什么要诊断解题过程并做 targeted feedback。

4. **Sinha & Kapur, Review of Educational Research 2021**  
   Productive Failure meta-analysis  
   → 为什么学生应先尝试，再接受教学。

5. **Chi & Wylie, Educational Psychologist 2014**  
   ICAP  
   → 为什么要从 Passive answer consumption 走向 Constructive / Interactive learning。

6. **Kobayashi, Japanese Psychological Research 2019**  
   Learning by Teaching meta-analysis  
   → 为什么 Teach-Back 有理论与实证基础。

### 技术 2 篇

7. **Lewis et al., NeurIPS 2020**  
   Retrieval-Augmented Generation  
   → 为什么课程知识需要外部、可追溯证据。

8. **Gao et al., ICML 2023**  
   Program-Aided Language Models  
   → 为什么 LLM 应生成程序，而把科学计算交给 runtime。

如果设计文档篇幅允许，再加入：

- Butler 2010 — Transfer；
- Belland et al. 2017 — Scaffolding；
- VanLehn 2011 — ITS；
- Hogan et al. 2021 — Knowledge Graph；
- Gou et al. 2024 — Tool-based verification。

---

# 6. 建议在 Quantum Agent 文档中的引用位置

## 6.1 项目背景

推荐引用：

```text
Bastani et al. 2025
Kestin et al. 2025
```

推荐论述：

> 生成式 AI 可以显著提升学生在获得 AI 支持时的即时表现，但未经教学约束的直接答案式交互并不必然带来真实学习，甚至可能削弱撤除 AI 后的独立表现；另一方面，遵循学习科学原则设计的 AI tutor 已在真实大学物理课程中展现出显著学习增益。因此，AI 教育系统的核心问题不是“是否使用大模型”，而是“如何设计学习过程”。

---

## 6.2 Commitment Gate

推荐引用：

```text
Sinha & Kapur 2021
Bastani et al. 2025
```

关键词：

```text
productive failure
attempt before instruction
learning guardrails
```

---

## 6.3 Diagnosis / Minimal Intervention

推荐引用：

```text
Miller et al. 2026
Belland et al. 2017
VanLehn 2011
```

关键词：

```text
deliberate practice
targeted feedback
scaffolding
step-based tutoring
```

---

## 6.4 Reconstruction / Teach-Back

推荐引用：

```text
Chi et al. 1994
Chi & Wylie 2014
Kobayashi 2019
```

关键词：

```text
self-explanation
constructive engagement
learning by teaching
interactive teaching
```

---

## 6.5 Transfer / Solo

推荐引用：

```text
Butler 2010
Bastani et al. 2025
```

关键词：

```text
transfer
retrieval
unaided performance
AI withdrawal
```

---

## 6.6 Course Evidence / Knowledge Graph

推荐引用：

```text
Lewis et al. 2020
Hogan et al. 2021
```

关键词：

```text
provenance
non-parametric memory
knowledge graph
ontology
validation
```

---

## 6.7 Coding Agent / Scientific Verifier

推荐引用：

```text
Gao et al. 2023
Gou et al. 2024
```

关键词：

```text
program-aided reasoning
external runtime
tool verification
self-correction with tools
```

---

# 7. 不建议作为正式核心参考的资料

## 7.1 不以 GitHub Star 代替学术依据

OpenMAIC、DeepTutor、OpenTutor 等项目非常值得作为：

```text
engineering inspiration
UI/UX reference
runtime reference
```

但不要用它们替代：

```text
PNAS
Scientific Reports
Review of Educational Research
Educational Psychologist
PRPER
NeurIPS / ICML / ICLR
```

等同行评审文献来论证“为什么这样教学”。

---

## 7.2 不为了“新”而大量加入未经验证的 arXiv AI Tutor

2024–2026 年出现了大量：

```text
LLM Tutor
Socratic LLM
Multi-Agent Education
Personalized Tutor
```

论文。

其中很多：

- 样本很小；
- 只有自动指标；
- 依赖 GPT judge；
- 没有真实学生；
- 没有 withdrawal / transfer test；
- 没有长期或外部效度；
- 架构复杂但教育问题不明确。

Quantum Agent 的比赛材料应避免这种“参考文献堆叠”。

---

# 8. 推荐的项目学术叙事

这些文献最终可以收敛成一条非常完整的链条：

```text
Generative AI can improve assisted performance
        │
        │ Bastani 2025
        ▼
But assistance ≠ learning
        │
        ▼
Student must generate first
        │ Productive Failure
        │ Sinha & Kapur 2021
        ▼
Diagnose the student's reasoning
        │ Miller 2026 / VanLehn 2011
        ▼
Provide the minimum necessary scaffold
        │ Belland 2017
        ▼
Require constructive explanation
        │ Chi 1994 / ICAP 2014
        ▼
Teach it back
        │ Kobayashi 2019
        ▼
Transfer to a new situation
        │ Butler 2010
        ▼
Remove AI assistance
        │ Bastani 2025
        ▼
Observe independent learning evidence
```

技术上则对应：

```text
Course Evidence
        │
        │ Lewis 2020
        ▼
Retrieval-grounded Generation
        │
        ▼
Pedagogical Knowledge Graph
        │ Hogan 2021
        ▼
Agent Reasoning
        │
        ▼
Task-specific Program Generation
        │ Gao 2023
        ▼
Isolated Scientific Runtime
        │
        ▼
External Tool Verification
        │ Gou 2024
        ▼
Verified Learning Artifact
```

因此 Quantum Agent 最适合用一句话概括为：

> **The LLM provides intelligence; pedagogy constrains assistance; course evidence grounds explanations; scientific tools verify truth; and student actions provide the evidence of learning.**

---

# 9. 参考文献（建议正式采用）

1. Bastani, H., Bastani, O., Sungu, A., Ge, H., Kabakcı, Ö., & Mariman, R. (2025). Generative AI without guardrails can harm learning: Evidence from high school mathematics. *Proceedings of the National Academy of Sciences*, 122(26), e2422633122. https://doi.org/10.1073/pnas.2422633122

2. Kestin, G., Miller, K., Klales, A., Milbourne, T., & Ponti, G. (2025). AI tutoring outperforms in-class active learning: an RCT introducing a novel research-based design in an authentic educational setting. *Scientific Reports*, 15, 17458. https://doi.org/10.1038/s41598-025-97652-6

3. Miller, K., Miller, O., & Lawrence, G. (2026). Teaching problem solving in undergraduate physics courses: An endorsement for deliberate practice. *Physical Review Physics Education Research*, 22, 020121. https://doi.org/10.1103/7pqt-gd9c

4. Sinha, T., & Kapur, M. (2021). When Problem Solving Followed by Instruction Works: Evidence for Productive Failure. *Review of Educational Research*, 91(5), 761–798. https://doi.org/10.3102/00346543211019105

5. Chi, M. T. H., & Wylie, R. (2014). The ICAP Framework: Linking Cognitive Engagement to Active Learning Outcomes. *Educational Psychologist*, 49(4), 219–243. https://doi.org/10.1080/00461520.2014.965823

6. Chi, M. T. H., de Leeuw, N., Chiu, M.-H., & LaVancher, C. (1994). Eliciting Self-Explanations Improves Understanding. *Cognitive Science*, 18(3), 439–477. https://doi.org/10.1016/0364-0213(94)90016-7

7. Kobayashi, K. (2019). Learning by Preparing-to-Teach and Teaching: A Meta-Analysis. *Japanese Psychological Research*, 61(3), 192–203. https://doi.org/10.1111/jpr.12221

8. Butler, A. C. (2010). Repeated testing produces superior transfer of learning relative to repeated studying. *Journal of Experimental Psychology: Learning, Memory, and Cognition*, 36(5), 1118–1133. https://doi.org/10.1037/a0019902

9. Belland, B. R., Walker, A. E., Kim, N. J., & Lefler, M. (2017). Synthesizing Results From Empirical Research on Computer-Based Scaffolding in STEM Education: A Meta-Analysis. *Review of Educational Research*, 87(2), 309–344. https://doi.org/10.3102/0034654316670999

10. VanLehn, K. (2011). The Relative Effectiveness of Human Tutoring, Intelligent Tutoring Systems, and Other Tutoring Systems. *Educational Psychologist*, 46(4), 197–221. https://doi.org/10.1080/00461520.2011.611369

11. Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-t., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems*, 33, 9459–9474. https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html

12. Hogan, A., Blomqvist, E., Cochez, M., d'Amato, C., de Melo, G., Gutierrez, C., Kirrane, S., Labra Gayo, J. E., Navigli, R., Neumaier, S., Ngomo, A.-C. N., Polleres, A., Rashid, S. M., Rula, A., Schmelzeisen, L., Sequeda, J., Staab, S., & Zimmermann, A. (2021). Knowledge Graphs. *ACM Computing Surveys*, 54(4), Article 71. https://doi.org/10.1145/3447772

13. Gao, L., Madaan, A., Zhou, S., Alon, U., Liu, P., Yang, Y., Callan, J., & Neubig, G. (2023). PAL: Program-aided Language Models. *Proceedings of the 40th International Conference on Machine Learning*, PMLR 202, 10764–10799. https://proceedings.mlr.press/v202/gao23f.html

14. Gou, Z., Shao, Z., Gong, Y., Shen, Y., Yang, Y., Duan, N., & Chen, W. (2024). CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing. *International Conference on Learning Representations (ICLR 2024).* https://openreview.net/forum?id=Sx038qxjek

---

# 10. 前沿工作（建议在 Related Work 中单列）

15. LearnLM Team et al. (2024). LearnLM: Improving Gemini for Learning. arXiv:2412.16429. https://arxiv.org/abs/2412.16429

16. Wang, R. E., Ribeiro, A. T., Robinson, C. D., Loeb, S., & Demszky, D. (2024–2025). Tutor CoPilot: A Human-AI Approach for Scaling Real-Time Expertise. arXiv:2410.03017. https://arxiv.org/abs/2410.03017

---

## 最终建议

Quantum Agent 的参考文献不应该追求数量，而应该形成一个非常明确的证据结构：

```text
PNAS 2025
    → AI 没有 guardrails 会伤害真正学习

Scientific Reports 2025
    → 设计得当的 AI Tutor 在真实大学物理中可以有效

Productive Failure / ICAP / Self-Explanation
    → 为什么学生必须先产生、再解释

Learning by Teaching / Transfer
    → 为什么 Teach-Back 和新情境迁移是学习证据

RAG / Knowledge Graph
    → 为什么课程事实必须可追溯

PAL / CRITIC
    → 为什么科学计算与正确性需要工具执行和验证
```

这套文献已经足以支撑 Quantum Agent 的核心叙事，而且比堆叠大量低质量“LLM + Education”论文更有说服力。
