# Quantum Agent 证据审计与工程决策报告

## 研究方法与总判断

本报告把你上传的上一版报告视为“待审计的战略综合”，而不是权威来源；所有关键结论都尽量回到官方工程文档、原始研究论文、系统综述、部署记录和可核验的产品材料。检索覆盖生产级 agent 官方资料、开放框架文档、经典 ITS 文献、现代 LLM 教育代理研究、物理与量子物理教育研究，以及中国高校与治理环境材料；时间重点放在经典奠基文献与 2023 年后快速演化的 agent/教育 AI 证据。对于产品现状，优先采用截至 **2026-07-11** 仍可公开访问的官方文档、官方公告或主流一手报道；对于教育效果，优先采用随机对照、准实验、纵向跟踪、系统综述和元分析。对少数上一版报告提及但缺乏可公开核验材料的案例，本报告明确标注 **“No reliable public evidence was found”**。fileciteturn0file0 citeturn48view3turn48view4turn49view1turn51view3turn42academia2turn43academia0turn44academia0turn15academia1turn16academia0turn23academia0turn23academia2turn24academia0turn31news2turn30news3

本报告采用两条彼此独立的评级轴。**技术成熟度**方面，T5 表示有持续规模化生产部署且具备可信运营证据，T4 为有重复真实部署且有可靠性文档，T3 为有真实用户的功能性 pilot，T2 为经评估原型，T1 为概念或极小规模演示。**教育有效性**方面，E5 表示有可复制的高质量因果证据且包含保持或迁移，E4 表示至少一项强随机试验并以学习结果为核心，E3 为可信准实验或纵向证据，E2 为小规模学习证据或观察性研究，E1 仅有可用性/满意度/任务完成证据，E0 则没有学习效果证据。一个系统完全可能同时是 **T5/E0** 或 **T2/E4**；这正是上一版报告最需要被拆开的地方。citeturn42academia2turn43academia0turn44academia0turn15academia1turn16academia0turn40academia0

先给出本次调查最重要的判断。第一，**成熟 agent 不是“会连续说很多步”的聊天机器人，而是能在受控工具、可恢复状态、明确权限、可审计轨迹、持续评测之下稳定完成反复有价值任务的系统**。OpenAI 把 Responses API、内建工具、tracing 与 evals 放在同一套 agent 基础设施中；Agents SDK 明确把“循环、handoff、审批、session、guardrails”视作运行时责任；Anthropic 则把“workflow”和“agent”清楚区分，并反复强调：对定义明确的任务，先做最简单的组合式 workflow，而不是默认追求自治和多代理。Google ADK 同样把 graph workflows、sessions/memory、trace view、evaluation、action confirmation 和安全治理并列为生产特性，而不是 demo 附件。citeturn48view3turn48view5turn49view1turn49view2turn51view2turn51view3

第二，**教育代理的成功标准不能套用生产力代理**。生产力代理追求“把任务更快做完”；教育代理必须回答“学生是否在 AI 拿走后学得更独立、更可迁移、更能自我解释”。目前最强的现代教育证据并不支持“让 AI 直接代做练习”路线。Tutor CoPilot 的随机对照试验显示，AI 作为真人 tutor 的实时助教可把学生掌握率提升 4 个百分点，且对低评分 tutor 的帮助达到 9 个百分点；CodeAid 的真实课堂部署说明“不给完整代码、给伪代码/注释/局部指导”的设计更贴近教学需要；LLM-Tutor 在数学证明上改善作业表现，但对考试成绩没有显著提升，并揭示了聊天式帮助可能放大学生的低自我效能与依赖风险；编程教育研究也发现，当学生把 LLM 当作“解释者”而不是“代答者”时才更可能获益，而主观感受往往高估真实学习收益。citeturn42academia2turn43academia0turn44academia0turn15academia3

第三，**量子物理尤其适合“LLM 负责解释与策略，验证工具负责真值约束”的教育代理**。量子力学学习困难并不只是内容抽象，而是概念语义、数学形式、表征转换和物理可解释性之间频繁错位；上层量子力学研究表明，学生在波函数合法性、边界条件、归一化、测量后态、束缚态与散射态、哈密顿量角色、时间演化和期望值等方面长期存在系统性误解。与此同时，这个学科又天然拥有大量可计算、可验证、可可视化的中间对象：符号推导、边界条件、Hermiticity、维度分析、数值积分、波包演化、Bloch 球、自旋动力学、微扰展开、变分结果等。Jupyter 的开放 notebook 文档模型、QuTiP 的量子模拟能力以及 QuILT 等研究验证过的“预测—仿真—解释”脚本，为 Quantum Agent 提供了比一般课程更清晰的“可信教学闭环”。citeturn23academia0turn23academia2turn24academia0turn24academia1turn25view1turn24academia3turn23academia3

第四，**本项目第一年最合理的定义不是“通用研究型多代理”，而是“课程内、教师控制、workflow-first、tool-verified、student-model-lite 的量子课程助教系统”**。它最该优先解决的不是“能否像研究员一样自走”，而是四条完整且高频的垂直闭环：课程问答与概念澄清、推导步骤诊断与分层提示、代码/模拟辅导、教师/TA 侧误区分析与会话分诊。上一版报告关于“确定性工作流 + LLM 策略层 + 验证工具 + 教师治理”的主公式，整体方向是对的，但若把它误解为“只要加 RAG 和几套工具就能自动成为 tutor”，那就是错误的。真正重要的是：**工作流定义、学生帮助边界、教师配置权、可执行验证、日志和评测**。fileciteturn0file0 citeturn49view1turn48view5turn51view3turn42academia2turn43academia0turn44academia0

下面先给出面向决策的浓缩结论。

### 执行层面的关键发现

| 发现 | 结论 |
|---|---|
| 真正成熟的 agent 都把工具、状态、评测、权限、审批、追踪视为一等公民 | Quantum Agent 不应从“提示词工程”起步，而应从“工作流与工具接口”起步 |
| 现代教育证据最强的是 **human-in-the-loop** 辅导增强，而不是完全自动代教 | 学生端之外，TA Copilot 和教师分析台必须是首发功能 |
| “不给答案、只给支架”不是道德姿态，而是学习上更稳的设计原则 | 必须实现 hint gating、answer release 条件、teacher override |
| 量子课程拥有比大多数学科更好的可验证对象和可视化基础设施 | 符号检查、数值模拟、notebook、图形反馈应是主系统而非附属功能 |
| 多代理只有在开放项目、跨文件代码、长时任务才明显合理 | 日常课程问答、推导纠错、基础练习应坚持单编排器 workflow |
| RAG 不等于正确性 | 数学、代码、物理约束检查必须交给外部 verifier/executor |
| 教育效果与产品热度高度可分离 | 第一年的 KPI 不应是使用时长，而应是独立作答、泄漏率、延迟保持、教师续用意愿 |
| 大型教育 AI 失败常死于治理、供应商和运维，而不是模型本身 | 先做课程级 pilot，再扩到院系级；不要先做全校宣传式平台 |
| 中国高校环境正在鼓励 AI 进课堂，但公共服务与学生数据治理约束都在增强 | USTC 最稳妥路径是“校内有限对象、限定课程、明示日志和权限边界”的内部部署 |
| Quantum Agent 的长期护城河不是“更聪明”，而是“更可信、更会教、更会诊断、更易被教师纳入课程” | 长期资产应围绕课程知识、量子误区图谱、验证工具链、教师工作流和评测数据积累 |

这些判断综合了上一版报告、官方工程文档、教育试验和量子教育研究。fileciteturn0file0 citeturn48view3turn48view5turn49view1turn51view3turn42academia2turn43academia0turn44academia0turn23academia2turn25view1turn24academia3turn31news2turn30news3turn47news5

## 前一版报告审计

上一版报告最有价值的地方，是它已经把项目从“量子聊天机器人”抬升到了“生产级、教师可控、工具增强的课程内教育代理”。但它的问题也很明显：若干产品案例停留在文档层或推荐层；若干教育结论混淆了学习效果与可用性；若干“最近很火”的系统缺少公开可核验的实证；若干框架建议还没有真正落到“哪个 runtime 最适合小型大学团队”的层面；还有一些有关量子教育、教学误区和“现有系统是否真正覆盖所有组件”的判断需要更严谨地区分“事实”“推断”“尚无公开证据”。fileciteturn0file0

### 前一版报告审计表

下表选取了上一版报告中最负重的 25 条主张或建议，按“确认 / 需重要限定 / 部分支持 / 无支持 / 被反驳 / 过时 / 不可经验检验”审计。表中的“原主张”均来自你上传的上一版报告。fileciteturn0file0

| 前一版主张 | 类型 | 原暗示来源 | 独立核验来源 | 审计状态 | 证据强度 | 资格限定或修正 | 对 Quantum Agent 含义 |
|---|---|---|---|---|---|---|---|
| 应以确定性教学工作流为骨架，而非默认多代理 | 架构建议 | Anthropic/框架文档 | Anthropic《Building Effective Agents》；OpenAI Agents SDK；Google ADK | 确认 | 强 | 对定义明确任务尤其成立；开放项目类任务可局部代理化 | 作为首年默认原则 |
| 多代理不是天然更好 | 架构建议 | Anthropic/AutoGen 类经验 | Anthropic 明确区分 workflow 与 agent；OpenAI SDK 也把 bounded workflow 列为更适用场景 | 确认 | 强 | 对开放式研究/代码任务仍可有价值 | 多代理只做增强模式 |
| 教育代理要区分“完成任务”与“学会了” | 教学原则 | 现代教育 AI 研究 | Tutor CoPilot；LLM-Tutor；编程课堂因果研究 | 确认 | 强 | 需要在评测中加入 AI 移除后的独立表现 | 评测设计必须脱离“有 AI 时表现” |
| Tutor CoPilot 证明 AI 提示可提升真实学习 | 实证结论 | 论文/摘要 | Tutor CoPilot RCT | 确认 | 强 | 它增强的是 **真人 tutor**，不是纯自动 tutor | 应优先建设 TA Copilot |
| Tutor CoPilot 总体提升约 4 个百分点，低评分 tutor 约 9 个百分点 | 实证量化 | 论文/摘要 | Tutor CoPilot RCT | 确认 | 强 | 指标是 topic mastery，不是长期迁移 | 说明“先补弱 TA”比“直接替代 TA”更稳 |
| 无约束生成式 AI 会伤害学习 | 实证结论 | 编程教育研究 | AI Meets the Classroom；LLM-Tutor | 确认但需重要限定 | 中强 | 不是“任何 AI 都有害”，而是“代做/外包式使用”更危险 | 需要 help policy 与答案释放控制 |
| LLM 作为“讲解型私人导师”可能有益 | 实证结论 | 编程教育研究 | AI Meets the Classroom | 确认 | 中强 | 益处取决于学生如何使用 | 解释模式要鼓励自我解释与对话 |
| Khanmigo 体现了 teacher-first 的教育产品化路线 | 产品判断 | Khan Academy 页面 | Khanmigo 官方产品页 | 确认 | 中 | 公开强因果学习证据仍有限 | 可学习其教师集成，不可把它当学习效果证明 |
| Khanmigo 有公开充分的学习增益证据 | 实证结论 | 产品印象 | 当前公开材料 | 不支持 | 弱 | 公开材料主要是产品描述和使用场景，不足以支撑强学习结论 | 不能把 Khanmigo 当 E4/E5 案例 |
| Rori 证明窄域、低带宽、频繁练习可有效 | 实证结论 | 论文/摘要 | Rori RCT 摘要 | 确认 | 中强 | 证据来自数学；不自动外推到量子课程 | 窄域脚本化 tutor 值得做 |
| Rori 效应量约 0.37 | 实证量化 | 论文/摘要 | Rori 摘要 | 部分支持 | 中 | 当前可公开摘要支持显著正效应，但完整设计细节仍应看正式发表版本 | 可作为“窄任务先行”的支持，不宜夸大 |
| CodeAid 证明“不给完整代码”的编程助教更贴近教学需求 | 教育设计 | 课堂部署研究 | CodeAid | 确认 | 中强 | 部署研究强于产品反馈，但仍非大规模 RCT | Quantum Agent 代码辅导应禁止直接代写整题 |
| LLM-Tutor 证明 proof-review tutor 比泛聊天更可信 | 教育设计 | 数学证明研究 | LLM-Tutor | 确认但需重要限定 | 中 | 作业提升不等于考试提升 | 推导反馈应优先做“review + next step”，非开放解题 |
| aiPlato 说明物理作业的 step-wise feedback 有潜力 | 课堂 pilot | 物理论文 | aiPlato | 确认但需重要限定 | 中 | 目前是真实课堂 pilot，非因果证据，存在自选择偏差 | 值得借鉴交互形态，不足以直接宣传学习增益 |
| AI Peer 说明“可能出错的 AI 同伴”也能促学 | RCT 结果 | 物理论文 | AI Peer | 确认 | 中强 | 研究对象是牛顿力学概念误解，不是量子课程 | 说明“权威 tutor”不是唯一角色，可实验同伴模式 |
| Harvard 结构化物理 AI tutor 有明确公开强证据 | 实证案例 | 上一版报告点名 | 当前公开检索 | 不支持 | 弱 | **No reliable public evidence was found** | 不应用作当前决策锚点 |
| ITAS 已经非常接近 Quantum Agent | 系统比较 | 上一版报告点名 | 当前公开检索 | 不支持 | 弱 | **No reliable public evidence was found** | 不能据此做差异化论证 |
| 量子课程非常依赖误区诊断而非单纯答疑 | 学科判断 | 量子教育研究 | 上层量子力学困难综述；QMCS/QMFPS | 确认 | 强 | 误区图谱需要针对 USTC 课程再本地化 | 应优先投资误区 taxonomy |
| 现有通用 LLM 不可靠于数学/代码/评分验证 | 工程/教育判断 | 现代评测研究 | 数学评分研究；数学认知层级分类研究；CodeAid/LLM-Tutor 问题暴露 | 确认 | 中强 | 不等于“完全不能用”，而是不能担任唯一裁决器 | verifier/executor 必须外置 |
| RAG 可以提高课程 grounding，但不能保证正确 | 工程判断 | RAG 常识 | AI-TA；USP RAG Assistant；OpenAI/Anthropic 文档 | 确认 | 强 | 检索失败仍是关键瓶颈 | grounding 与 verification 必须分开设计 |
| 教师控制是部署合法性核心 | 产品/治理判断 | 注意事项与产品经验 | Khanmigo；Tutor CoPilot；Google ADK/Agents 文档 | 确认 | 中强 | 还要加上 TA 接管与 conversation review | 教师台必须进入 MVP |
| “没有现有系统覆盖全部目标组件” | 系统比较 | 上一版推断 | 现有公开系统对比 | 确认但需重要限定 | 中 | 应说“未找到公开、成熟、单一系统把全部八类组件同时整合并有可靠部署证据”；不能写成绝对不存在 | Quantum Agent 有真实整合型创新空间 |
| LangGraph 是更合适的中后期状态化骨架 | 框架判断 | 上一版推荐 | LangGraph 平台能力；Google ADK 对图工作流的相似方向；OpenAI SDK 对 resumable run/approval 的强调 | 部分支持 | 中 | 它确实适合长时状态/HITL，但对首年 MVP 未必比自定义状态机更优 | 可作为迁移目标，不一定是首发底座 |
| PydanticAI 适合 verifier/tool schema 层 | 框架判断 | 上一版推荐 | PydanticAI 官方总览 | 确认 | 中 | 更适合作为 typed model interface，而不是全系统编排器 | 适合嵌入节点，不适合单独当总 runtime |
| Google ADK/Agents SDK 的评测与治理经验对教育代理有用 | 工程判断 | 上一版推荐 | ADK evaluate/trace/action confirmation；OpenAI tracing/guardrails/sessions | 确认 | 强 | 这些是工程成熟度证据，不是教育有效性证据 | 直接复制工程能力，不能复制教学主张 |

从这张表可以看出，上一版报告最大的优点是战略方向大体正确；最大的缺点则是 **把“工程可行”“产品可用”“教育有效”在少数地方说得过于接近**。这一点在 Khanmigo、部分量子相关系统、“现有系统是否全覆盖”、以及未能公开核验的点名案例上最明显。fileciteturn0file0 citeturn49view1turn48view5turn42academia2turn43academia0turn44academia0turn16academia0turn15academia1turn41view2turn35view2turn51view3

## 生产级代理系统案例与综合

### 什么把成熟 agent 与聊天机器人、炫技 demo、失控循环区分开来

成熟 agent 与普通聊天机器人之间最关键的分界，不是“会不会自言自语规划”，而是 **是否拥有受控行动界面、环境反馈、可恢复中间状态、明确终止条件、失败恢复和可审计 runtime**。OpenAI Responses API 把多轮工具调用、web/file/computer use、tracing 与 evals 放在统一 API 原语上；Agents SDK 明确区分“你自己管理 orchestration”与“交给 SDK 管理循环和审批”；Anthropic 则进一步指出，许多实际场景里优化单次 LLM 调用、结合检索和例子就足够，只有当灵活决策真正带来收益时才应该走向 agent。Google ADK 也把 graph routes、human input、sessions/state/memory、trace view 和 conformance/eval 放入核心产品面。换句话说，成熟 agent 是 **runtime 设计问题**，不只是 prompt 设计问题。citeturn48view3turn48view5turn49view1turn51view2turn51view3

第二个分界是 **用户控制与信任校准**。OpenAI 在 ChatGPT agent 的公开材料中把 prompt injection、数据连接器、网页 takeover 和审批风险单独拿出来讨论；Anthropic 在 Claude Code 里把 MCP、auto memory、skills、hooks、background agents 与跨 surface session 管理放在同一套产品体验之中，但同时强调权限、控制和可组合；Google ADK 明确提供 action confirmations。也就是说，成熟系统接受一个现实：**越能行动，越需要用户看得见、停得下、接得回**。这恰好与教育场景高度一致，因为课堂里最不可接受的不是“模型偶尔不够聪明”，而是“模型在不透明状态下替学生做了本不该代做的事”。citeturn48view4turn50view2turn51view2

### 生产级案例速览

下表覆盖 15 个对 Quantum Agent 最有参考价值的生产级或高影响案例。对于部分闭源产品，架构细节按“公开事实 / 合理推断 / 未知”分开处理；对于“当前状态”，以 2026-07-11 可公开访问资料为准。citeturn48view3turn48view4turn50view2turn51view2turn35view4

| 系统 | 组织 | 当前形态 | 主要用户 | 任务边界 | 技术成熟度 | 对 Quantum Agent 的主要启示 |
|---|---|---|---|---|---|---|
| OpenAI Deep Research | OpenAI | 商业产品功能 | 知识工作者 | 多步信息搜集与综合 | T4 | 深度研究模式适合教师备课/项目辅导，不适合默认答疑 |
| ChatGPT agent | OpenAI | 商业产品功能 | 付费 ChatGPT 用户 | 浏览、连接器、网页行动、终端任务 | T3-T4 | 行动能力越强，越要强化审批和注入防护 |
| Responses API | OpenAI | 开发平台 | 开发者 | 工具增强应用/agents | T4 | “工具即能力”比“人格即能力”更重要 |
| Agents SDK | OpenAI | 开发框架 | 开发者 | 有定义边界的会话/事务式 workflow | T4 | 审批、session、handoff、guardrails 值得借鉴 |
| Claude Code | Anthropic | 商业开发工具 | 开发者 | 代码修改、命令执行、PR/CI | T4 | 受控代码环境与 auto memory 非常适合项目辅导参考 |
| Anthropic workflow/agent 方法论 | Anthropic | 官方工程指南 | 开发者 | agent 设计方法 | T4 影响力 | “workflow-first”是最可迁移原则 |
| GitHub Copilot coding agent | GitHub/Microsoft | 商业产品 | 软件团队 | repo research, plan, change, PR | T4 | 云端受控执行、PR 生命周期指标、Actions 环境很关键 |
| Copilot Agent Mode | GitHub/Microsoft | 商业产品 | 软件开发者 | IDE 内工具化协作 | T4 | 人在 IDE 主导、代理局部自治，是更稳健的交互模式 |
| AutoGen | Microsoft Research | 开源框架 | 研究者/开发者 | 单/多代理原型与系统 | T3 | 适合研究，不适合首发课堂 runtime |
| Magentic-One | Microsoft Research | 研究系统 | 研究者 | 通用复杂任务编排 | T2 | 多代理可展示复杂任务分解，但默认成本高 |
| Google ADK | Google | 开源/平台式框架 | 开发者/企业 | graph workflow、多代理、评测 | T3-T4 | 功能完整，但对小团队略重 |
| LangGraph | LangChain | 开源/托管平台 | 开发者 | 长时、状态化、HITL agent | T3-T4 | 中后期非常适合长时状态与恢复 |
| PydanticAI | Pydantic | 开源框架 | Python 开发者 | 类型安全 agent 与 evals | T3 | 更像“强类型 agent SDK”，很适合 verifier 接口 |
| CrewAI | CrewAI | 开源/商业化平台 | 开发者 | crews、flows、自动化 | T3 | 对企业自动化友好，但教育主控逻辑仍需自写 |
| LlamaIndex AgentWorkflow | LlamaIndex | 开源/平台组件 | 开发者 | docs/knowledge-heavy agent systems | T3 | 对 document-centric 系统友好，但对课堂治理不是现成解 |
| OpenHands | 开源社区 | 开源软件工程 agent | 开发者 | 代码修改与执行 | T3 | 代码沙箱、长期会话、model-agnostic 值得借鉴 |
| Cursor | Anysphere | 商业开发工具 | 开发者 | IDE 内代码协作/agents | T4 | “用户在回路中”的交互很强，但教育控制策略不足 |
| Replit Agent | Replit | 商业开发工具 | 学习者/开发者 | 从需求到应用生成/修改 | T4 | time-to-first-value 很强，但易滑向“代做” |
| Perplexity Deep Research | Perplexity | 商业研究功能 | 知识工作者 | 多步检索与报告 | T4 | 研究模式对教师有吸引力，但学习场景需更强边界 |
| Salesforce Agentforce / Intercom Fin / Sierra / Harvey | 企业软件商 | 商业企业 agent | 客服/销售/法律等 | 高边界、高流程任务 | T4-T5 | 真正成功的 agent 多在流程边界清楚的垂直领域 |

来源主要为官方产品/框架文档、工程博客和研究原始材料。citeturn48view3turn48view4turn48view5turn49view1turn50view2turn34view0turn51view2turn35view4turn35view5turn34view1

### 对 Quantum Agent 最关键的生产级案例解剖

**OpenAI Deep Research** 之所以值得研究，不是因为它“像研究员”，而是因为它把复杂检索与综合任务包装成一个有时间跨度、可追踪来源、带安全治理的 bounded mode。OpenAI 公开材料把它定位成适合需要多步网页搜集与综合的任务，并在安全附注中特别说明了对 web browsing 风险的额外测试和缓解。对 Quantum Agent，这一案例最可复制的不是“自动写长报告”，而是“研究模式作为教师备课、课程更新、项目资料搜集的专门入口”，并且要与日常学生问答完全分开。对学生端来说，默认把所有问题都送入“deep research 模式”只会增加成本、时延和越界答案泄漏风险。citeturn48view1turn48view4

**ChatGPT agent** 揭示了行动型 agent 的真正难点：连接器、网页接管、终端和 prompt injection 的组合让能力上升，也让风险急剧上升。OpenAI 在公开材料里直接承认 prompt injection 对 agent 系统一般都构成重要风险，并指出当 agent 能采取网页行动时，攻击成功的后果会更严重。对 Quantum Agent，这意味着“浏览器级代理”绝不应进入学生默认工作流；真正需要的可能是 **教师或 TA 的受控研究模式**，并且必须强制审批。任何能替学生点击、下载、提交作业、访问 LMS 的能力，都应列入首年禁区。citeturn48view4

**Responses API 与 Agents SDK** 提供了两个很好的工程边界样板。Responses API 更适合自己控制状态、循环和路由；Agents SDK 更适合让框架管理 recurring orchestration、session、guardrails 和 approval。这个区分对 Quantum Agent 很重要，因为它直接对应两种系统边界：课程内高风险教学工作流，最好由应用代码自己控制；而一些低风险、可复用的局部会话节点，可以交给 SDK 或 typed wrapper 来管理。也因此，Quantum Agent 不该把“选一个框架全包”当作目标，而应把“哪些责任交给 runtime，哪些责任交给业务状态机”先说清楚。citeturn48view3turn48view5

**Anthropic 的 workflow-first 原则** 是本报告认为最适合直接迁移到 Quantum Agent 的生产经验。Anthropic 明确指出：workflow 是预定义代码路径；agent 则让模型动态决定流程和工具；对定义明确的任务，workflow 更可预测一致，而很多任务甚至只需优化单次 LLM 调用。对教育场景尤其如此。因为多数课堂高频任务并不需要自由探索，而需要 **可重复、可审计、可控的帮助边界**。因此，课程问答、推导点评、提示释放、会话升级等，都更应写成确定性节点图而不是“请模型自己想办法”。citeturn49view1turn49view2

**Claude Code 与 GitHub Copilot coding agent** 则共同说明：软件工程是 agent 最有价值的原生场景之一，因为代码有可执行反馈、自动测试和客观验收标准。Anthropic 把代码任务定义为 agent 特别有效的场景，原因包括输出可验证、问题空间结构化、质量可客观测量；Claude Code 又把 auto memory、MCP、skills、hooks、background agents 和跨设备 session 结合起来。GitHub 的 coding agent/agent mode 把这种能力放进受控开发环境和 PR 生命周期里。对 Quantum Agent，这两类证据直接指向一个设计结论：**代码/模拟辅导应是后续高价值壁垒，但必须在沙箱、测试和日志下进行**；不能做成“给我一段量子模拟题，Agent 直接把整个项目写完提交”的教学破坏器。citeturn49view1turn50view2turn9view2turn9view3

**Google ADK、LangGraph、PydanticAI** 代表三种非常不同的工程姿势。ADK 把 graph workflows、多代理、session/state/memory、trace、evaluation、action confirmations 放在完整平台内，适合做中后期“可观测 agent 平台”；LangGraph 的核心强项是 durability、HITL 和长时状态，更适合复杂任务；PydanticAI 则在类型安全、结构化输出、工具参数校验和人类审批上表现突出，更像“稳健的 typed interface 层”。这三者对 Quantum Agent 的合适位置，并不是互斥选择，而是：**首年靠自定义状态机明确教学工作流，局部节点用 PydanticAI 这类强类型代理包装；一旦长时项目、跨会话恢复和人工中断队列变成高频需求，再迁移到 LangGraph 式 runtime；若未来需要校级平台化和更大规模评测，再借鉴 ADK 的平台层能力**。citeturn51view2turn51view3turn35view2turn34view1

**AutoGen、Magentic-One、CrewAI** 的共性是：它们很有启发性，也很容易让团队过早爱上多代理。AutoGen 强在研究与原型，Magentic-One 强在复杂任务展示，CrewAI 强在企业自动化叙事与 flows。但教学系统与客户服务/内部自动化不同，课堂里每一次“多说一步、多调用一次、多委派一层”都会增加解释负担、延迟和成本。对 Quantum Agent 来说，这类框架更适合做 **研究支线和长项目实验**，不适合作为首发课堂底座。citeturn34view0turn35view4turn35view5

### 生产级模式目录与反模式目录

真正成功的生产级系统普遍共享以下模式。其一，是 **bounded autonomy**：只在边界清楚、有明确工具接口、有退出条件的任务中放权。其二，是 **tool-first reliability**：通过 schema、参数校验、输出约束、审批和环境反馈让模型“借助工具变可靠”，而不是让模型“凭语言自证正确”。其三，是 **stateful but inspectable**：系统有会话状态、记忆、压缩和恢复能力，但这些状态要可回放、可调试、可清理。其四，是 **human interruptibility**：用户或管理员可插入、可审批、可否决、可接管。其五，是 **evaluation as runtime hygiene**：上线前后持续用 trajectory、tool choice、latency、regression 和 human review 监控系统。Quantum Agent 几乎应该逐条照抄这些做法。citeturn48view5turn49view1turn50view2turn51view3turn35view2

相反，常见反模式也很清楚。其一，是 **先上多代理，再找价值**。其二，是 **把 RAG 当正确性担保**。其三，是 **把高风险动作藏在黑盒循环里**。其四，是 **把 demo benchmark 当成真实采用证据**。其五，是 **把产品热度或用户赞叹误写成教育效果**。对 Quantum Agent，这些反模式会分别表现为：默认多代理课堂助手、只做“量子知识库聊天框”、开放学生自动运行全部 notebook/提交作业、只看满意度和点赞、不做 AI 移除后的独立测验。citeturn49view2turn48view4turn51view3turn15academia3

## 经典 ITS 与现代教育代理证据

### 经典 ITS 已经把哪些问题研究得很清楚

如果把 ITS 历史从 ChatGPT 才算开始，Quantum Agent 会失去最重要的设计遗产。经典 ITS 传统长期关注四个核心模型：**领域模型、学生模型、教学模型、界面模型**。Cognitive Tutor/MATHia 一类的 model-tracing tutor 通过显式技能和步骤约束提供细粒度反馈；AutoTutor 展示了自然语言教学对话的可能性，但也暴露了 authoring burden 与对话策略设计困难；ALEKS 代表知识空间与 mastery learning 的持续产品化；ASSISTments 不只是教学平台，还是“在线 A/B 实验基础设施”；Andes 则是物理问题求解 tutor 的重要先例。今天许多 LLM tutor 把“会聊天”当成创新，但经典 ITS 观点提醒我们：**自然语言只是界面；真正决定学习的是技能表示、帮助策略、错误处理和任务序列**。citeturn19search6turn17search0turn22search6turn19academia1

关于学习效果，稳健的历史结论并不支持“所有智能辅导都神奇有效”，而是支持更谨慎的判断：高质量 ITS 通常可以产生 **中等大小、强烈依赖测量方式与实现质量** 的收益；步骤级反馈、worked example、example fading、 mastery learning、自适应 sequencing 和 metacognitive prompting 都有较强研究积累；但 standardized tests 上的效果往往弱于与系统高度对齐的局部测验，而 authoring cost 和课堂整合成本始终很高。对 Quantum Agent 最重要的启示是：**不要为了“更像对话”而牺牲 skill representation、帮助边界、以及教师维护能力**。如果首年做不出复杂学生模型，也至少要做 student-model-lite：记录概念簇、提示依赖、错误类型、最近尝试和验证失败点。citeturn22search6turn19search4turn19academia1

### 现代教育代理案例矩阵

下表给出 15 个对 Quantum Agent 最相关的现代教育代理/研究系统，按技术成熟度与教育有效性分开评级。评级依据是公开证据，不以品牌知名度加分。citeturn42academia2turn43academia0turn44academia0turn15academia1turn16academia0turn40academia1turn40academia0turn42academia0turn44academia2turn41view2turn45view0turn46search1

| 系统/研究 | 场景 | 主要机制 | 技术成熟度 | 教育有效性 | 样本/时长 | 主要证据 | 对 Quantum Agent 的直接启示 |
|---|---|---|---|---|---|---|---|
| Tutor CoPilot | K-12 在线真人辅导 | AI 给 tutor 实时建议，不替学生作答 | T3 | E4 | 900 tutors / 1800 students | RCT，掌握率 +4pp，低评分 tutor +9pp | 首先增强 TA，而不是先替代 TA |
| Rori | 加纳数学、低带宽 WhatsApp tutor | 高频窄域对话练习 | T3 | E4 | 长期学校干预 | 正向显著学习效应 | 窄任务、强频率、强边界更有机会 |
| CodeAid | 大班编程课 | 避免泄漏完整代码，给伪代码/注释 | T3 | E2-E3 | 700 学生 / 12 周 | 真实课堂部署与质性分析 | 代码辅导必须控制答案泄漏 |
| LLM-Tutor | 数学证明 | proof-review tutor + chatbot | T2 | E3 | 148 学生 | 作业提升、考试不显著 | “review tutor”强于泛聊天，但仍需警惕依赖 |
| LeanTutor | 数学证明 | Lean 形式验证 + 自然语言 hint | T2 | E1-E2 | 实验型系统 | 形式验证强，课堂证据仍弱 | 形式验证路线对推导反馈很重要 |
| aiPlato | 大学物理作业 | step-wise feedback + AI tutor chat | T3 | E2 | 真实课程 pilot | 高参与组与期末相关，但非因果 | 可借鉴逐步反馈 UI，不可直接夸大学习增益 |
| AI Peer | 物理误解纠正 | 非权威 AI 同伴对话 | T2 | E4 | 165 学生 | RCT，post-test +10.5pp | “同伴而非权威”值得做实验分支 |
| AI-TA | 编程课程问答 | 开源 LLM + RAG + 偏好优化 | T2 | E1 | Piazza 历史数据 | 答案质量提升 | 说明 RAG 对课程问答有效，但不等于学习提升 |
| Motion Picture Engineering AI-TA | 硕士课程 | RAG TA + 可在开卷考试中使用 | T3 | E2 | 43 学生 / 7 周 | 满意度高，考试无显著差异 | 可把“保学术效度”的 assessment design 纳入实验 |
| AstroTutor | 高年级天文学 | 域特化资料 + 反思性使用记录 | T2 | E2 | 一门本科课程 | 结构化使用与 AI literacy 发展 | 要把“如何用 AI”纳入课程设计 |
| Physics-STAR | 中学物理 | personality/adaptive tutoring | T1-T2 | E2 | 12 名学生 | 极小样本对照 | 只能视为启发，不可作部署证据 |
| Khanmigo | 学生/教师多学科产品 | 支架式辅导 + 教师工具 | T4 | E0-E1 | 产品化持续中 | 官方产品材料丰富，公开因果证据弱 | 学其产品体验，不学其“证据过度解读” |
| Duolingo Max | 语言学习产品 | roleplay / video call / AI feedback | T5 | E0-E1 | 产品级 | 官方产品介绍强，学习因果证据有限 | “互动练习”有吸引力，但不是高等物理模板 |
| Shiksha Copilot | 低资源学校教师 | lesson plan 共创 | T3 | E2 | 1043 教师 | 大规模混合方法 | 教师协作产品可能比学生端更快落地 |
| TriQuest | 课程设计 copilot | 知识图谱 + 课程共创 | T2 | E2 | 43 教师 | 设计效率、质量改善 | 可借鉴课程 authoring 工具 |
| LAUSD Ed | 学区级聊天式学生助手 | 个人助理/数据整合 | T1-T2 | E0 | 短命部署 | 供应商失败与治理危机 | 典型反面案例：先治理、后宣传 |
| QANDA AI Tutor | 大规模亚洲教育产品 | OCR 解题、AI tutor | T5 | E0-E1 | 大规模产品 | 规模和采用强，学习因果证据弱 | 规模不等于学习价值 |

### 现代教育代理中最有价值的设计规律

**Tutor CoPilot** 是当前最值得 Quantum Agent 团队认真学习的现代教育案例，因为它恰好击中了高校课程中最现实的资源瓶颈：不是没有教师，而是 **高质量 TA / tutor 稀缺且水平参差**。Tutor CoPilot 并没有承诺让 AI 单独完成辅导，而是给真人在实时互动中提供更像专家的下一步建议，结果是学生掌握率提升，且对低评分 tutor 的提升最大。这说明 AI 最稳健的教育角色之一，是 **把专业教学策略向人类辅导员扩散**。对 Quantum Agent，这比“先造一个全自动量子 tutor”更值得首发。citeturn42academia2

**Rori** 则说明另一条路径：当任务边界足够窄、频率足够高、媒介足够轻、对话结构足够受控时，聊天式 tutor 可以真的进入学习成效区间，而不是只停留在新奇体验。它的重要性不在于“用 WhatsApp”，而在于它把 agent 的能力压缩进了一个 **明确教学语法**：练习、反馈、下一题。对 Quantum Agent，这意味着不要幻想首年就做覆盖整门量子课程的一站式智能体；更现实的方式是先选择 2–3 个高频概念簇或典型推导，做窄而深的工作流。citeturn15academia1

**CodeAid 与 LLM-Tutor** 一起揭示了“现代 LLM tutor 的最大分界线是答案控制”。CodeAid 通过伪代码、代码注释和概念解释避免直接泄漏整段作业代码；LLM-Tutor 则把 proof-review tutor 与通用数学聊天拆开，结果说明：在正式考核与独立表现上，review/tutor 组件比纯聊天更可信。对于量子推导和数值作业，这几乎是直接可迁移的。Quantum Agent 最需要的不是“会完整解题的量子大脑”，而是“会判断你哪一步错了、为什么错、下一步最小可行提示是什么、何时该交给 TA”。citeturn43academia0turn44academia0

**aiPlato 与 AI Peer** 对物理教育尤其重要。aiPlato 说明 step-wise feedback 与 AI tutor chat 能进入真实大班物理课程，并且学生似乎更依赖形成性反馈而不是直接要答案；AI Peer 更激进，它甚至把“AI 可能会错”前置告诉学生，却仍在随机试验里看到 post-test 提升。这提示 Quantum Agent 并不一定非要扮演“绝对正确的权威 tutor”角色。在概念冲突型任务里，一个“会反问、会给反例、会逼学生检验直觉”的 AI 同伴，可能比一个“总想把正确答案讲清楚”的 AI 老师更符合学习科学。citeturn16academia0turn15academia1

**Khanmigo、Duolingo Max、QANDA** 则提醒我们把“技术成熟”“产品规模”“教育有效性”严格拆开。Khanmigo 是成熟度高、产品体验被认真雕琢、教师价值叙事清晰的教育产品；Duolingo Max 展示了 Roleplay/Video Call 这种高留存交互形态；QANDA 代表了亚洲大规模拍照解题/AI tutor 路线的普及能力。但这些案例在公开层面并没有提供与 Tutor CoPilot 或 Rori 同等级的学习因果证据。对 Quantum Agent，它们是 **产品经验、交互经验和采用经验** 的来源，而不是“已证实会提高量子学习”的来源。citeturn41view2turn45view0turn44search4

### 教育证据矩阵

| 研究/系统 | T 评级 | E 评级 | 样本 | 时长 | 对照 | 立即效果 | 延迟效果 | 迁移 | 移除 AI 后独立表现 | 教师结果 | 主要限制 |
|---|---:|---:|---:|---|---|---|---|---|---|---|---|
| Tutor CoPilot | T3 | E4 | 1800 学生 | 实时辅导期 | 无 AI tutor support | 明显正向 | 未充分公开 | 部分 | 未完全公开 | 降低 novice tutor 能力差距 | 主要是 K-12 在线辅导 |
| Rori | T3 | E4 | 学校级 | 多月 | 常规教学 | 正向显著 | 有一定保持 | 有限 | 未公开充分 | 低资源场景可行 | 学科窄、媒介特殊 |
| CodeAid | T3 | E2-E3 | 700 | 12 周 | 无同等受控对照 | 使用与感知积极 | 未充分公开 | 有限 | 未充分公开 | 教师认可设计约束 | 非强因果 |
| LLM-Tutor | T2 | E3 | 148 | 一个学期片段 | 无工具对照 | 作业正向 | 考试不显著 | 弱 | 风险提示强 | 无 | 依赖/自我效能影响明显 |
| aiPlato | T3 | E2 | 大班课程 | 4 次作业 | 观察性 | 高使用相关更好期末 | 未公开 | 未公开 | 未公开 | 可集成交互数据 | 自选择偏差 |
| AI Peer | T2 | E4 | 165 | 短期干预 | 讨论历史而非误解 | post-test +10.5pp | 未公开 | 概念纠正强 | 未公开 | 无 | 学科是经典力学 |
| Motion Picture Engineering AI-TA | T3 | E2 | 43 | 7 周 | 有/无 AI-TA | 满意度高 | 考试差异不显著 | 未公开 | 开卷考试未破坏效度 | 教学可接受 | 样本小 |
| AstroTutor | T2 | E2 | 一门课 | 一个学期 | 课程内观察 | 结构化使用改进 | 未公开 | AI literacy 正向 | 间接有利 | 教师可整合 | 非因果 |
| Khanmigo | T4 | E0-E1 | 多学校/地区产品 | 持续 | 公开强对照缺乏 | 采用与好评强 | 未知 | 未知 | 未知 | 教师工具较强 | 公开实证不足 |
| Duolingo Max | T5 | E0-E1 | 大规模产品 | 持续 | 公开强对照缺乏 | 产品使用强 | 未知 | 未知 | 未知 | 不适用 | 非高等 STEM 案例 |
| QANDA AI Tutor | T5 | E0-E1 | 大规模产品 | 持续 | 公开强对照缺乏 | 大规模采用 | 未知 | 未知 | 未知 | 不适用 | 更像解题平台 |
| LAUSD Ed | T1-T2 | E0 | 学区部署 | 极短 | 无 | 无可信公开学习证据 | 无 | 无 | 无 | 治理失败 | 供应商与数据治理崩溃 |

核心证据主要来自原始研究摘要、官方产品文档和独立报道。citeturn42academia2turn15academia1turn43academia0turn44academia0turn16academia0turn15academia1turn40academia0turn16academia3turn41view2turn45view0turn44search4turn47news5

## 量子物理教育与中国部署环境

### 量子物理误区与困难 taxonomy

量子课程最负重的设计工作，不是再做一个“问啥答啥”的知识库，而是建立可操作的 **误区—诊断—最小提示—可视化/反例—迁移题** 链条。上层量子力学研究反复显示，学生常在以下区域出现系统困难：把“形式上可写的函数”误当成物理可接受态；把概率振幅和概率密度混为一谈；不理解边界条件和归一化的物理意义；将测量误解为“读出现成值”；把哈密顿量、定态、时间演化与期望值之间的关系断裂开来；在 tunneling、bound/scattering、superposition、spin、degeneracy、perturbation、variational reasoning 中用经典直觉硬套量子表征。QMCS 和 QMFPS 提供了可直接借鉴的测评框架。citeturn23academia0turn23academia2turn24academia0turn24academia1

| 主题 | 错误学生模型 | 常见可观察答案/步骤 | 诊断问题 | 最小有效提示 | 可用反例或仿真 | 迁移问题 | 证据来源 |
|---|---|---|---|---|---|---|---|
| 波函数合法性 | 任何光滑函数都可做态 | 忽略边界、不可归一化也照用 | “这个函数为什么是/不是允许态？” | 先问边界与可积性，再问物理域 | 无限深势阱、散射态对比 | 换势阱/坐标区间再判定 | Singh & Marshman；Zhu & Singh citeturn23academia2turn23academia0 |
| 概率振幅/概率密度 | 复振幅等于概率 | 直接把 ψ 当概率读 | “测量概率与 ψ 的什么量相关？” | 先画图，再要求写出 \|ψ\|² | 双缝或波包可视化 | 相位变而 \|ψ\|² 不变的题 | QuILT 双缝；QMCS citeturn23academia3turn24academia0 |
| 测量与塌缩 | 测量只是读取已有值 | 把任意态都当本征态处理 | “测量后态一定不变吗？” | 区分测量前展开与测量后态 | 自旋测量动画 | 换可兼容/不兼容观测量 | QMFPS；量子困难综述 citeturn24academia1turn23academia2 |
| 时间演化 | 波函数随时间变但期望值总不变/总会变 | 定态与非定态混淆 | “哈密顿量本征态的时间依赖特征是什么？” | 先判是否定态，再谈 observable | 波包/定态并排演示 | 改测量量后再问期望值时间依赖 | Zhu & Singh；QMFPS citeturn23academia0turn24academia1 |
| 隧穿 | 粒子穿障后能量损失 | 错画透射后波长/能量 | “势能图里哪条线表示什么？” | 把 E 与 U(x) 分开解释 | tunneling PhET/QuILT | 换 barrier 宽度并比较 | QMCS 隧穿研究 citeturn24academia2 |
| 自旋/角动量 | 三维空间旋转直观直接等同 ket 旋转 | 用经典箭头替代 Hilbert 空间推理 | “Sx 的本征态与 Sz 的关系？” | 切换到基矢与矩阵表示 | Bloch 球可视化 | 连续两次不同轴测量 | QMFPS citeturn24academia1 |
| 微扰/简并 | 公式机械套用，不看条件 | 忽略简并/近简并条件 | “这个近似为什么可用？” | 先问对称性与能隙 | Zeeman/Stark 数值扫参 | 换能级结构再判是否可用 | 量子困难综述与课程推断 citeturn23academia2 |
| 变分/多电子 | 把 trial function 当任意代数技巧 | 不理解上界和物理参数意义 | “为什么结果一定从上方逼近？” | 要求说明 trial 选择的物理含义 | He 变分 notebook | 改 trial family 再比较 | 部分为课程推断，需本地验证 citeturn23academia2 |
| 计算模拟 | 代码跑通即代表物理正确 | 单位、归一化、守恒量全不查 | “你验证了哪些物理不变量？” | 强制列出 sanity checks | QuTiP/Jupyter notebook | 换步长/边界后稳定性如何 | QuTiP；Jupyter；课程推断 citeturn24academia3turn25view1 |

其中前六类属于研究证据较强的“已实验记录误区”；后两类更多是基于研究结论与课程任务形态做出的 **可检验推断**，需要在 USTC 试点中继续本地化验证。citeturn23academia0turn23academia2turn24academia0turn24academia1turn24academia2

### 最接近 Quantum Agent 的现有系统，究竟还差什么

上一版报告主张“未见现有系统同时覆盖课程 grounding、误区诊断、步骤级推导反馈、符号验证、数值模拟、可视化、学生状态跟踪、教师分析”。这一主张不能靠直觉，需要拆解。公开证据显示，**单一系统常常只能解决其中 2–4 项**。Andes 解决了步骤级物理解题反馈和部分学生建模，但不具备现代 LLM 对话、数值模拟或教师分析闭环；QuILT 强在脚本化概念冲突与仿真，但不是通用 course-grounded tutor；LeanTutor/LLM-Tutor 强在步骤反馈与形式验证，但不覆盖物理内容、可视化或教师分析；aiPlato 强在物理作业的 step-wise feedback，但缺少强验证和成熟学生模型；Jupyter/QuTiP/Quantum Composer 强在仿真、执行和可视化，但真空缺的是 tutoring logic、误区诊断、会话状态与教学分析。因而，当前更准确的说法是：**未发现有公开、成熟、单一系统把上述八个组件在大学量子课程中整合并伴随可靠真实部署证据**。citeturn23academia3turn44academia2turn44academia0turn16academia0turn25view1turn24academia3

| 系统 | grounding | 误区诊断 | 步骤反馈 | 符号/形式验证 | 数值模拟 | 可视化 | 学生状态 | 教师分析 | 评价 |
|---|---|---|---|---|---|---|---|---|---|
| Andes | 中 | 低-中 | 高 | 低 | 低 | 低 | 中 | 低 | 经典 ITS，非现代整合 |
| QuILT | 中 | 中 | 中 | 低 | 中 | 高 | 低 | 低 | 概念主题强，通用性弱 |
| LeanTutor | 低 | 低 | 高 | 高 | 低 | 低 | 低 | 低 | 形式验证强，不是量子系统 |
| LLM-Tutor | 中 | 低 | 高 | 中 | 低 | 低 | 低 | 低 | 作业改善，考试不显著 |
| aiPlato | 中 | 低-中 | 高 | 低 | 低 | 低 | 中 | 中 | 贴近物理作业，但仍 early |
| Khanmigo | 高 | 低 | 中 | 低 | 低 | 低 | 中 | 中 | 产品成熟，学科验证弱 |
| Jupyter + QuTiP | 低 | 无 | 无 | 中 | 高 | 高 | 无 | 无 | 计算媒介，不是 tutor |
| Quantum Composer | 低 | 无 | 无 | 中 | 高 | 高 | 无 | 无 | 量子计算教学工具，不是量子力学 tutor |

综合判断，Quantum Agent 最清晰的创新机会不是“又一个会聊量子的机器人”，而是 **把量子课程的误区 taxonomy、步骤级反馈、验证型工具链、notebook/simulation、以及教师台整合成单一课程产品与研究平台**。citeturn23academia2turn23academia3turn44academia2turn44academia0turn16academia0turn25view1turn24academia3

### 中国与 USTC 部署环境

中国高校的外部环境对“课程内 AI 助教”总体上是机会与约束并存。一方面，教育部推动教育数字化和 AI 进课堂的信号非常明确，2025 年中国还公开提出要把 AI 融入教学方法、教材与课程体系；高校围绕 DeepSeek 等本土模型开设课程的报道，也表明教师与院校层面对 AI 教学工具的兴趣显著上升。另一方面，中国的生成式 AI 公共服务要面对算法/安全评估、备案、内容合规、用户保护和数据治理要求；路透等报道也显示，中国监管对“公共可访问生成式 AI 服务”的治理尤其关注。对 USTC 来说，这意味着 **校内限定对象、课程限定用途、日志留痕、教师审核、最小化学生数据、尽可能本地化或受控部署** 是更稳妥的切入路径。citeturn31news2turn30news3turn30search1turn31news0

更现实地说，本报告没有找到充分公开证据证明 USTC 目前已经在大学量子物理课程中部署了成熟 AI tutor；因此最合理的定位不是“追赶已存在校内平台”，而是 **建设一个课程级、可研究、可扩展的内部 pilot**。USTC 的独特机会，在于学校本身具有强物理学科基础、强计算传统、对 notebook/仿真/编程项目接受度高。如果 Quantum Agent 首年就把“量子误区 + 受控验证 + 教师工作流 + notebook 实验”做深，它在校内的差异化将明显高于一个通用 LMS 插件。citeturn31news2turn30news3

| 系统或倡议 | 机构/公司 | 实际部署 | 用户 | 技术细节公开度 | 教育证据 | 与 USTC 相关性 | 证据限制 |
|---|---|---|---|---|---|---|---|
| AI 进入教学改革总方针 | 中国教育主管部门 | 政策方向明确 | 学校/教师/学生 | 中 | 非学习效果证据 | 高 | 政策不是实证 |
| 高校 DeepSeek 课程热潮 | 多所中国高校 | 有真实课程动作 | 教师/学生 | 低-中 | 非学习效果证据 | 中高 | 多为新闻，缺少课堂评测 |
| 公共生成式 AI 服务备案/安全评估 | 中国监管框架 | 已实施 | 公共 AI 服务商 | 中 | 不适用 | 高 | 面向 public-facing 服务，校内内部工具边界需进一步法律确认 |
| 国家智慧教育平台生态 | 国家级平台 | 已运行 | 教师/学生 | 中 | 平台存在证据 > 学习证据 | 中 | 缺乏对量子课程 AI tutor 的直接证据 |
| 学堂在线/XuetangX 类高教平台 | 高校平台生态 | 长期运营 | 高教课程用户 | 中 | 平台级证据强，学习因果弱 | 中 | 更像内容/LMS 生态，不是量子 agent |
| 课程级内部 AI 助教 pilot | 高校自建 | 国内多地探索中 | 单课程/单院系 | 低 | 各异 | 很高 | 公开技术细节与评估普遍不足 |

结论很直接：**USTC 最适合的部署策略不是先做面向公众的大而全服务，而是先做校内、课程内、教师责任清晰的受控工具**。citeturn31news2turn30search1turn30news3

## 架构与框架决策

### 最简单但足以扩展的目标架构

Quantum Agent 最简单、同时又能支撑后续扩展的架构，不是一个不断 self-loop 的大代理，而是一个 **确定性状态机编排器**，其节点分别调用：课程检索器、误区分类器、提示策略器、符号/数值验证器、代码执行沙箱、可视化生成器、会话日志器、教师/TA 队列。LLM 在这里主要扮演三类角色：输入分类与任务分流、面向学生的解释与提示生成、面向教师的摘要与模式归纳。所有“真值判断”尽量落在外部工具上：公式合法性、边界条件、归一化、维度分析、代码执行、数值稳定性、测试结果、图表输出。这样才能把 **会教** 与 **可信** 分开治理。citeturn49view1turn48view5turn35view2turn25view1turn24academia3

建议首年默认只做四条 workflow。其一，**课程问答 workflow**：问题意图分类 → 课程检索 → 只回答课程范围内内容 → 给出处与不确定性。其二，**推导诊断 workflow**：识别题型与目标量 → 要求学生给出当前步骤 → 调用规则/符号检查器 → 返回最小提示，而不是完整解。其三，**代码/模拟 workflow**：接收代码或 notebook 片段 → 在沙箱中运行 → 提取报错/数值失真/物理不变量问题 → 解释并给下一步调试建议。其四，**教师/TA workflow**：聚合同类误区、低置信度会话、异常高提示依赖、常见代码错误，并生成助教处理队列。任何一条流程越界，都必须能人工接管。citeturn50view2turn51view3turn35view2turn43academia0turn42academia2

### 框架加权决策矩阵

下面的矩阵针对 Quantum Agent 的特殊约束打分：小型大学团队、首年必须强控制、可维护、多学期运行、教师可审计、后续可扩。分值 1–5，权重总和 152。最重的标准是显式 deterministic workflow、小团队可维护性、长期部署稳定性、持久状态、恢复能力、追踪和安全。该矩阵不是“通用最好框架”排名，而是 **对 Quantum Agent 这个问题的适配排名**。citeturn48view5turn51view2turn51view3turn35view2turn34view1turn35view4

| 框架 | 加权总分 | 归一化 | 主要优点 | 主要弱点 | 结论 |
|---|---:|---:|---|---|---|
| 自定义确定性状态机 | 657 | 86.4 | 控制力极高、零锁定、最符合教学工作流、最易写死答案边界 | 许多 tracing/eval/HITL 设施需自建 | **首年最佳** |
| LangGraph | 653 | 85.9 | 长时状态、HITL、durability、恢复强 | 学习曲线较高，首年略重 | **最佳迁移目标/次优首发** |
| Google ADK | 594 | 78.2 | graph workflows、eval、trace、sessions 全 | 平台感强，对小团队偏重 | 中后期平台化可考虑 |
| PydanticAI | 591 | 77.8 | 类型安全、工具参数校验、结构化输出、审批友好 | 不是长时工作流总编排器 | 非常适合嵌入节点 |
| OpenAI Agents SDK | 559 | 73.6 | sessions、guardrails、approval、tracing 成熟 | 提供商锁定更强；课堂业务逻辑仍要自写 | 适合局部/实验性接入 |
| LlamaIndex Workflows | 533 | 70.1 | 文档与 retrieval 场景友好 | 教学治理和长期状态不是强项 | 可做知识层，不宜做总 runtime |
| CrewAI | 496 | 65.3 | crews/flows 叙事清晰，企业自动化快 | 多代理色彩重，首年易过度复杂 | 不推荐首发 |
| AutoGen | 435 | 57.2 | 研究灵活、原型快 | 调试与治理成本高 | 研究支线可用，不宜首发 |

### 推荐方案、迁移路径与失效条件

**MVP 推荐**：采用 **自定义确定性状态机 + PydanticAI 式强类型 model wrapper + 独立工具服务**。这意味着总编排不交给 agent 框架，而写在业务代码里；LLM 节点通过强类型接口调用；知识检索、符号检查、数值模拟、代码沙箱、日志和教师台都做成独立服务。这样做最符合“课程内教育工作流”的本质，也最容易明确 answer gating 与 teacher override。PydanticAI 之所以适合嵌入，是因为它能把工具参数、输出 schema、审批点和依赖注入做得比较稳，而且对后续换模型/换 provider 比较友好。citeturn35view2turn35view1

**成熟系统推荐**：当项目进入长学期、多项目 notebook、会话暂停/恢复、高频人工审批队列的阶段，再迁移到 **LangGraph 风格 runtime**。LangGraph 的价值不在“多代理”，而在于 long-running、resume、HITL、memory/checkpoint 这些教育工作流迟早需要的能力。若未来需要面向院系或校级平台统一做 trace/eval/conformance，再吸收 Google ADK 的平台层思路。citeturn34view1turn51view3turn51view2

**失效条件** 也必须说清楚。如果以下条件发生，当前推荐应被重新审视：一，课程任务很快演化为大量开放式长时项目，且恢复/中断比例高到自定义状态机维护困难；二，团队决定深度押注单一云生态并需要框架内置 sessions/guardrails/approval 以极快交付；三，教学研究表明某些多代理结构在量子项目辅导上显著优于单编排器 workflow；四，校内要求强统一 agent 平台与合规层，对自定义 runtime 形成组织阻力。达到这些条件时，LangGraph 或 ADK 的吸引力将超过纯自定义。citeturn48view5turn51view3turn34view1

### 能力与实现路径映射

| 能力 | 用户问题 | 教育证据 | 工程先例 | MVP 实现 | 成熟实现 | 决策类型 | 主风险 | 评测 | 优先级 |
|---|---|---|---|---|---|---|---|---|---|
| 课程 grounding Q&A | 学生问“课上这句话是什么意思” | RAG 类课程 TA 有用，但不等于学习提升 | Responses API / AI-TA / institutional assistant | 检索 + 引文 + teacher-curated corpus | 多源冲突消解 + provenance UI | Build | 检索错配 | citation 完整率、教师准确率 | 高 |
| 误区诊断 | 学生概念对了还是错了 | 量子困难研究强 | ITS/BKT/AI Peer | 规则 + LLM 分类到误区簇 | 数据驱动 student model | Research+Build | 误分类 | 教师标注一致性 | 高 |
| 解释模式选择 | 同一内容该反问、类比还是直讲 | Tutor CoPilot/LLM-Tutor 提示不同策略重要 | PydanticAI typed policy nodes | policy table + 少量 LLM 变体 | 个性化 pedagogy policy | Build | 风格漂移 | session rubric | 高 |
| 步骤级推导反馈 | “我这一步哪里错了” | Andes/LLM-Tutor/aiPlato 支持强 | verifier + typed wrapper | 规则检查 + 最小提示 | 形式化/符号混合验证 | Build+Research | 误判正确步骤 | step precision/recall | 高 |
| hint gating | 避免直接泄漏答案 | CodeAid/LLM-Tutor/Tutor CoPilot 强支持 | deterministic FSM | hint level 1–3 + teacher config | adaptive gating by mastery | Build | 学生绕过 | leakage tests | 高 |
| 符号验证 | 公式是否满足约束 | 研究和工程都强需要 | 外部 CAS/规则引擎 | 基础合法性/归一化/边界检查 | 更深层 operator algebra checks | Build | 覆盖不全 | verifier pass/fail audit | 高 |
| 维度检查 | 单位/量纲错误 | 工程常识强，教育上有价值 | deterministic checker | 基础 dimension parser | 题型特化检查器 | Build | 解析困难 | known-error benchmark | 中高 |
| 代码执行 | 程序到底哪里坏了 | 编程教育研究支持受控反馈 | Claude Code/OpenHands | 容器沙箱、时间/内存限制 | notebook worker pool | Integrate | 安全/资源 | sandbox regression | 高 |
| 代码调试 | 报错/数值不稳定 | CodeAid 强支持 | Copilot/Claude Code | test harness + diff explanation | multi-file project assist | Build | 变相代写 | independent coding performance | 高 |
| 数值模拟 | 波包/微扰/变分实验 | Jupyter/QuTiP/QuILT 强 | QuTiP/Jupyter | teacher-authored notebooks | parameterized lab generator | Integrate | 数值错误被当物理结论 | physical sanity tests | 高 |
| 交互可视化 | 学生看不见抽象对象 | QuILT/PhET 强 | Jupyter widgets/plots | notebook plots + saved figures | rich interactive dashboards | Integrate | 视觉吸引盖过思考 | explanation transfer | 中高 |
| 项目脚手架 | 学生不知如何开始 | 项目式学习需结构支持 | coding agents | project template + milestone checks | agent-assisted project board | Build | 代做风险 | milestone independence | 中高 |
| student-model-lite | 系统是否记得最近错误与提示依赖 | ITS 基础强 | sessions/state | 误区簇 + 最近尝试 + hint 依赖 | mastery/uncertainty model | Build+Research | 假精确 | predictive validity | 中高 |
| 教师分析台 | 教师想看全班误区 | ASSISTments/teacher tools 支持 | trace/eval dashboards | 高频误区、低置信度会话、升级队列 | 周报 + 干预建议 | Build | 信息噪声 | teacher usefulness | 高 |
| TA 分诊 | TA 不知先处理谁 | Tutor CoPilot 直接支持 | queue + summarizer | 会话摘要 + risk tags | routing by difficulty | Build | 摘要失真 | triage accuracy | 高 |
| 人工升级 | 谁该接手 | 生产 agent 通用刚需 | approval/handoff | teacher/TA one-click takeover | SLA/role routing | Build | 阶段转换断层 | escalation latency | 高 |
| 课程 authoring | 教师如何维护知识 | teacher copilot 研究支持 | TriQuest/Shiksha | 文档 ingestion + policy UI | versioned content QA | Build | 维护负担 | authoring time | 中高 |
| 自动形成性评估 | 小测/exit ticket/变体题 | 有价值但风险高 | Khanmigo teacher tools | 仅生成题目草案，教师审 | 自动实验平台集成 | Postpone | 质量与泄漏 | item review accuracy | 中 |
| LMS 集成 | 课程流程衔接 | 工程必要但非首价值 | connectors/APIs | 先只做链接与导入导出 | 深度单点登录与成绩同步 | Postpone | 治理复杂 | admin overhead | 中低 |

### Build–Buy–Integrate–Research 决策

| 子系统 | 决策 | 理由 |
|---|---|---|
| 编排状态机 | **内部构建** | 这是教学策略与边界控制核心，不应外包给黑盒 runtime |
| typed model wrapper | **开源集成** | PydanticAI 一类组件可降低 schema/validation 工作量 |
| 课程检索/RAG | **内部构建 + 开源集成** | 检索器可用成熟库，但 chunk/policy/citation 必须课程化 |
| 数学/物理 verifier | **原型内部构建** | 这是长期差异化关键研究资产 |
| Python 沙箱 / notebook 执行 | **开源集成** | 容器、Jupyter、worker 基础设施不必重复造轮子 |
| QuTiP 模拟层 | **集成** | 已有成熟量子模拟能力，直接复用最划算 |
| 可视化层 | **集成** | 用 Jupyter/Matplotlib/widgets 即可起步 |
| 教师/TA 仪表盘 | **内部构建** | 高度课程与组织流程相关 |
| 追踪/日志/评测 | **内部构建为主，吸收框架经验** | 需要与教学事件深度绑定 |
| 通用多代理调度 | **推迟** | 首年机会成本高，价值未证 |
| 自动评分 | **推迟/研究** | 公开证据不足以支持高风险真实使用 |
| 校级 LMS 深耦合 | **推迟** | 首年不应把工程资源耗在行政集成上 |
| 教师备课/课程作者助手 | **逐步构建** | 会提升维护性并沉淀课程资产 |
| 公网级公共服务化 | **推迟** | 中国治理与学生数据边界都不支持首年直接放大 |

## Quantum Agent 决策备忘录与阅读清单

### 第一年的产品定义与用户旅程

**第一年 Quantum Agent 应该是什么？** 它应是一套校内、课程内、教师控制的量子课程助教系统，而不是通用作业求解器，也不是多代理研究平台。最优先用户不是“所有学生同时”，而是 **量子课程教师团队 + TA + 愿意持续使用的课程内学生**。最先要做通的完整垂直工作流，则应是：**学生提交一个概念疑问或错误推导步骤 → 系统检索课程资料并分类误区 → 调用基础 verifier → 给出最小有效提示和下一步建议 → 记录事件 → 进入教师/TA 面板复盘**。这是最能同时锻炼课程 grounding、误区 taxonomy、工具验证、教师控制和日志评测的一条闭环。fileciteturn0file0 citeturn42academia2turn43academia0turn23academia2turn24academia1

下面给出七条核心旅程的建议蓝图。

| 场景 | 用户动作 | 系统状态 | 工具调用 | 教师策略 | 用户可见反馈 | 日志 | 失败恢复 | 升级 |
|---|---|---|---|---|---|---|---|---|
| 概念问题 | 学生问“测量后为什么态变了” | 新会话/概念簇未定 | 检索课程资料 + 误区分类 | 不给完整答案，先诊断 | 一问一答 + 图示建议 + 引文 | 问题簇、引用、提示层级 | 检索冲突时显式不确定 | 低置信度进 TA 队列 |
| 错误推导 | 学生上传某一步 | 步骤求助态 | 规则/符号检查器 | 只返最小有效 hint | 指出错误类型，不给全解 | 错误步、hint level、是否二次求助 | verifier 不足则回到人工 | 连续三次失败升级 |
| 代码调试 | 学生贴报错/代码 | 调试态 | 沙箱运行 + 测试 | 禁止直接重写全题 | 报错解释 + 最小 patch 建议 | 执行轨迹、资源占用、修复尝试 | 超时/危险调用终止 | 高风险代码交 TA |
| 计算项目 | 学生请求项目帮助 | 长任务态 | notebook 模板 + sandbox + QuTiP | 先脚手架，后里程碑检查 | 分阶段建议与 sanity checks | milestone、依赖、验证结果 | 可暂停恢复 | 需要时预约 TA |
| 教师看误区 | 教师打开面板 | 周报态 | 会话聚类 + 摘要 | 教师可标记误区和修正策略 | 班级热图、典型对话 | 误区统计、低置信度列表 | 可追溯到原会话 | 一键推送 TA 清单 |
| TA 分诊 | TA 看队列 | triage 态 | 摘要生成 + 会话回放 | TA 可接手或退回系统 | 简洁摘要、建议回复草案 | 接手时间、处理结果 | 摘要失真可回放原文 | 教师复核高风险会话 |
| 学期间更新 | 课程组更新知识 | authoring 态 | 文档 ingest + version diff | 新增内容需教师审核发布 | 版本说明与影响范围 | 文档版本、命中率变化 | 发布失败回滚 | 无 |

### 评测与课堂研究计划

首年评测必须分层。**离线层** 建立四套 benchmark：课程 grounding/citation、误区分类、步骤提示质量、代码/模拟 verifier。**系统层** 建立 tool trajectory、citation correctness、answer leakage、prompt injection、sandbox safety、latency/cost、session recovery 测试。**人机层** 用学生和教师 rubrics 评估“是否给了恰当难度的最小帮助”“是否过早泄漏答案”“是否可解释且可信”。**课堂层** 先做小样本 usability 和 teacher/TA study，再做有对照的 pilot，最后才谈学习增益。特别要加入 **AI 移除后的独立测验** 与 **延迟保持/迁移**，否则任何“成绩上升”都可能只是 AI 在场下的替代表现。citeturn51view3turn48view5turn42academia2turn44academia0turn15academia3

建议的试验序列如下。先进行约 20–30 名学生的可用性与 help-policy 研究，让量子教师和 TA 对 100–150 条典型会话做双人标注，建立误区 taxonomy 和 hint rubric。接着在单一章节内做 50–100 名学生的课程内 pilot，对照条件可设置为：普通课程资料与 office hour、课程 grounding Q&A only、grounding + step-wise tutoring。再往后若 pilot 表现稳定，进入一个小规模随机或准实验：核心结果包括章节测验、延迟测验、迁移题表现、AI 移除后独立解题、提示依赖率、教师工作量变化和高风险会话比例。没有这些证据前，不应对外宣称“提高了学习”，最多只能说“提高了课程支持效率/覆盖率”。citeturn42academia2turn44academia0turn40academia0turn15academia3

### 最终决策 memo

| 问题 | 直接回答 |
|---|---|
| 第一年的 Quantum Agent 应该是什么 | 课程内、教师控制、workflow-first、tool-verified 的量子课程助教 |
| 第一优先用户是谁 | 课程教师与 TA，其次是有持续使用意愿的学生 |
| 第一条完整垂直工作流是什么 | 概念/推导求助 → 检索/误区诊断 → verifier → 最小提示 → 日志 → TA/教师复盘 |
| 应使用什么总体架构 | 自定义确定性状态机 + typed model wrapper + 独立工具服务 |
| 应使用什么 MVP 框架 | **不选“大而全 agent 框架”**；首年用自定义状态机，节点层可用 PydanticAI |
| 哪些工具必须 deterministic | 答案释放策略、会话路由、权限、日志、citation、基础 verifier、代码沙箱、升级机制 |
| 哪些环节可以 model-driven | 误区初判、解释措辞、提示改写、教师摘要、项目规划草案 |
| 哪些内容必须在教师控制下 | 课程知识发布、答案边界、自动生成题/评估、低置信度会话、内容更新 |
| 首年绝对不该做什么 | 默认多代理、自动评分、LMS 深耦合、学生端浏览器代理、全校级公共服务化 |
| 哪些是已建立的工程问题 | 编排状态机、检索、日志、沙箱、QuTiP/Jupyter 集成、教师台基础设施 |
| 哪些是原创教育研究问题 | 量子误区 taxonomy、本学科步骤反馈策略、help policy、项目式 notebook 教学评价 |
| 真正部署前至少需要什么证据 | 准确率/泄漏率/安全回归、人机可用性、教师续用意愿、pilot 稳定运行 |
| 宣称“改善学习”前至少需要什么证据 | 对照设计 + 延迟/迁移 + AI 移除后独立表现 |
| 最可防守的长期优势是什么 | 量子课程语义与误区图谱 + 验证型工具链 + 教师工作流与评测数据 |
| 最佳长期形态是什么 | **课程产品 → 校内教学平台 → 研究平台/开源组件** 的阶段组合 |

### 接下来的十个具体动作

1. 选定一门 USTC 量子课程与一位主讲教师作为首个责任人。  
2. 采集并整理课程允许进入系统的知识资产，建立版本库。  
3. 与教师/TA 共建首版量子误区 taxonomy 与 100–150 条标注样例。  
4. 定义首年四条 workflow 的状态图和终止条件。  
5. 先做最基础 verifier：归一化、边界条件、Hermiticity、维度检查、数值 sanity checks。  
6. 搭建容器化 Python/Jupyter/QuTiP 沙箱，建立资源限制和审计日志。  
7. 做教师/TA 面板最小版：低置信度会话、同类误区聚合、接管按钮。  
8. 建立离线 benchmark 与 leakage/injection/sandbox 安全测试。  
9. 运行 20–30 人可用性研究，迭代提示释放策略。  
10. 只在一个章节或一个项目中做首个课程 pilot，不扩到整校。  

### 校正后的阅读清单

下面先给出 **Quantum Agent 团队最应该优先读的前 30 项**，随后给出按主题分组的扩展清单。为遵守响应规范，文中不直接写原始网页链接；论文给出 DOI 或 arXiv 编号，产品/文档以官方页面标题与最后核验日期标识。

#### 团队前 30 必读

| 优先级 | 资料 | 为什么重要 | 主要决策 | 证据级别 | 阅读对象 |
|---|---|---|---|---|---|
| 高 | Anthropic. *Building Effective AI Agents*. 2024，官方工程指南。最后核验：2026-07-11。 | 最清晰的 workflow/agent 边界定义 | 首年架构原则 | 工程一手 | 全队 |
| 高 | OpenAI. *New tools for building agents*. 2025，官方文档/公告。 | 工具、tracing、evals 如何进入生产 runtime | 工具层与追踪层 | 工程一手 | 工程负责人 |
| 高 | OpenAI. *Agents SDK Guide*. 2025–2026，官方文档。 | 审批、sessions、handoffs 的具体形态 | 审批/恢复设计 | 工程一手 | 工程负责人 |
| 高 | Google ADK. *Why evaluate agents*. 2026，官方文档。 | Agent 评测从输出扩展到轨迹 | QA 与回归体系 | 工程一手 | 工程/评测 |
| 高 | Wang et al. *Tutor CoPilot: A Human-AI Approach for Scaling Real-Time Expertise*. 2024，arXiv:2410.03017。 | 最强的现代教育 AI 因果证据之一 | TA Copilot 优先级 | E4 | 全队 |
| 高 | Kazemitabaar et al. *CodeAid*. 2024，arXiv:2401.11314。 | 说明代码助教必须控制答案泄漏 | 代码辅导边界 | E2-E3 | 工程/教学设计 |
| 高 | Chen et al. *Generative AI alone may not be enough: Evaluating AI Support for Learning Mathematical Proof*. 2025，arXiv:2509.16778。 | 说明作业提升不等于考试提升 | 推导帮助策略 | E3 | 教学研究/工程 |
| 高 | Weijers et al. *Using AI Peers to Overcome Physics Misconceptions*. 2025，arXiv:2504.00408。 | “AI 同伴”路线的物理教育证据 | 概念对话模式 | E4 | 学习科学/物理教育 |
| 高 | Singh & Marshman. *A Review of Student Difficulties in Upper-Level Quantum Mechanics*. 2015，广泛公开版本。 | 建立量子误区 taxonomy 的起点 | 误区库建设 | 综述 | 全队 |
| 高 | Zhu & Singh. *Surveying students' understanding of quantum mechanics in one spatial dimension*. 2016，arXiv:1602.05440。 | 直接给出可测概念簇 | 诊断题设计 | 原始研究 | 物理教育/教学设计 |
| 高 | Marshman & Singh. *Validation and Administration of a Conceptual Survey on the Formalism and Postulates of Quantum Mechanics*. 2020，arXiv:2006.04030。 | 上层量子 formalism 测评工具 | 评测仪器 | 原始研究 | 物理教育/评测 |
| 高 | Sayer, Maries, Singh. *Quantum interactive learning tutorial on the double-slit experiment*. 2020，arXiv:2006.16070。 | QuILT 的可迁移脚本样式 | 预测–仿真–解释设计 | 原始研究 | 教学设计 |
| 高 | Johansson, Nation, Nori. *QuTiP: An open-source Python framework for the dynamics of open quantum systems*. 2011，arXiv:1110.0573。 | 量子模拟技术底座 | 数值层选择 | 工程/科研 | 工程/物理 |
| 高 | Jupyter 官方主页与文档，最后核验：2026-07-11。 | notebook 作为教学媒介 | 计算实验平台 | 官方文档 | 工程/教学设计 |
| 高 | Dange et al. *aiPlato*. 2026，arXiv:2601.09965。 | 最接近“物理作业逐步反馈”的现代案例 | 物理作业交互 | E2 | 教学设计 |
| 高 | OpenAI. *Introducing ChatGPT agent*. 2025，官方公告。 | 行动型 agent 的风险与能力边界 | 为什么学生默认不能用行动型 agent | 官方文档 | 全队 |
| 高 | Anthropic. *Claude Code Overview*. 2025–2026，官方文档。 | 代码 agent 的良好交互与权限模式 | 项目辅导路线 | 官方文档 | 工程负责人 |
| 高 | GitHub. *About Copilot coding agent / agent mode*. 2025–2026，官方文档。 | 受控代码环境如何设计 | 代码沙箱与 PR 型流程 | 官方文档 | 工程负责人 |
| 高 | VanLehn. *The Relative Effectiveness of Human Tutoring, Intelligent Tutoring Systems, and Other Tutoring Systems*. 2011，Educational Psychologist。 | ITS 历史基准线 | 何谓“像 tutor” | 综述核心文献 | 教学研究全队 |
| 高 | Kulik & Fletcher. *Effectiveness of Intelligent Tutoring Systems: A Meta-Analytic Review*. 2016，Review of Educational Research。 | ITS 效果总览 | 教育主张边界 | 元分析 | 全队 |
| 中高 | Corbett & Anderson. *Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge*. 1995。 | student model 的经典原点 | student-model-lite | 奠基文献 | 教学研究 |
| 中高 | ASSISTments 平台与 in vivo experiments 相关论文。 | 把系统做成实验平台的范式 | 评测平台设计 | 平台研究 | 评测/教学研究 |
| 中高 | Motion Picture Engineering AI-TA. 2026，arXiv:2604.04670。 | 真实课程使用 + 开卷考试观察 | assessment design | E2 | 教学研究 |
| 中高 | AI Meets the Classroom. 2024，arXiv:2409.09047。 | LLM 使用方式与学习风险 | help policy | E3 | 全队 |
| 中高 | PydanticAI Overview. 2026，官方文档。 | typed outputs、tool validation、approval | 节点实现 | 官方文档 | 工程 |
| 中高 | LangGraph / AgentWorkflow 相关官方文档。最后核验：2026-07-11。 | 长时状态、HITL、恢复 | 中后期 runtime | 官方文档 | 工程 |
| 中高 | Shiksha Copilot. 2025，arXiv:2507.00456。 | 教师协同产品的真实价值 | teacher authoring | E2 | 产品/教学设计 |
| 中高 | TriQuest. 2025，arXiv:2510.03369。 | AI 课程共创与知识图谱工具 | 课程 authoring | E2 | 教学设计 |
| 中高 | LAUSD Ed 独立报道与后续调查新闻。2024–2026。 | 教育 AI 治理失败的反面教材 | 部署边界 | 新闻/案例 | 产品/治理 |
| 中高 | 中国生成式 AI 措施与教育 AI 政策材料。2023–2026。 | 决定部署边界与数据治理 | 校内合规 | 政策/报道 | 产品/治理 |

#### 按主题分组的扩展清单

**生产级 agent 工程**

- OpenAI. *New tools for building agents*. 2025。官方文档。最后核验：2026-07-11。  
- OpenAI. *Agents SDK Guide*. 2025–2026。官方文档。最后核验：2026-07-11。  
- OpenAI. *Introducing deep research*. 2025。官方公告。  
- OpenAI. *Introducing ChatGPT agent: bridging research and action*. 2025。官方公告。  
- Anthropic. *Building Effective AI Agents*. 2024。官方工程指南。  
- Anthropic. *Claude Code Overview*. 2025–2026。官方文档。  
- GitHub Docs. *About Copilot coding agent*. 2025–2026。官方文档。  
- GitHub Docs. *About Copilot agent mode*. 2025–2026。官方文档。  
- Google ADK. *ADK 2.0: Build production agents, not prototypes*. 2026。官方文档。  
- LangGraph / LangChain. 2025–2026 官方文档与平台说明。  
- Pydantic. *PydanticAI Overview*. 2026。官方文档。  
- Microsoft Research / AutoGen 团队. *AutoGen* 相关论文与文档，2024–2025。  
- CrewAI. *CrewAI Documentation*. 2026。官方文档。  
- LlamaIndex. *Introducing AgentWorkflow*. 2025。官方文档/博客。  
- OpenHands 文档与代码库，2025–2026。  

**agent 评测与安全**

- Google ADK. *Why evaluate agents*. 2026。官方文档。  
- OpenAI. tracing/evals 相关官方文档，2025–2026。  
- OpenAI. ChatGPT agent 安全附录，2025。  
- Anthropic. context windows / effective context engineering 相关文档，2025–2026。  
- Prompt injection 相关安全综述与行业报告，2024–2025。  
- LAUSD Ed 失败后续报道，2024–2026。  

**经典 ITS**

- VanLehn, K. 2011. *The Relative Effectiveness of Human Tutoring, Intelligent Tutoring Systems, and Other Tutoring Systems*. *Educational Psychologist*.  
- Kulik, J.A., Fletcher, J.D. 2016. *Effectiveness of Intelligent Tutoring Systems: A Meta-Analytic Review*. *Review of Educational Research*.  
- Corbett, A.T., Anderson, J.R. 1995. *Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge*. *User Modeling and User-Adapted Interaction*.  
- Koedinger, Anderson, et al. Cognitive Tutor / model-tracing 系列代表文献。  
- Graesser et al. AutoTutor 系列代表文献。  
- ALEKS 知识空间与掌握学习代表文献。  
- Heffernan & Heffernan. ASSISTments 平台代表文献。  
- VanLehn et al. Andes Physics Tutor 代表文献。  

**现代 LLM tutor**

- Wang et al. 2024. *Tutor CoPilot*. arXiv:2410.03017.  
- Kazemitabaar et al. 2024. *CodeAid*. arXiv:2401.11314.  
- Chen et al. 2025. *Generative AI alone may not be enough*. arXiv:2509.16778.  
- Patel et al. 2025. *LeanTutor*. arXiv:2506.08321.  
- Dange et al. 2026. *aiPlato*. arXiv:2601.09965.  
- Weijers et al. 2025. *AI Peer*. arXiv:2504.00408.  
- Hicke et al. 2023. *AI-TA*. arXiv:2311.02775.  
- O’Regan & Kokaram. 2026. *An AI Teaching Assistant for Motion Picture Engineering*. arXiv:2604.04670.  
- Ting & O’Briain. 2025. *Teaching Astronomy with Large Language Models*. arXiv:2506.06921.  
- Jiang & Jiang. 2024. *Beyond Answers: LLM-Powered Tutoring in Physics Education*. arXiv:2406.10934.  

**teacher copilot**

- Tutor CoPilot，2024。  
- Shiksha Copilot，2025。  
- TriQuest，2025。  
- Khanmigo for Teachers / 官方产品页，2024–2026。  

**student modeling 与 knowledge tracing**

- Corbett & Anderson, 1995。  
- BKT 后续综述与 deep knowledge tracing 代表文献。  
- ASSISTments 上的 in vivo experiment 方法。  
- Future-Proofing Programmers / CoTutor，2025 预印本。  

**physics 教育**

- AutoTutor/Andes 物理 tutor 代表文献。  
- Physics misconceptions 与 concept inventories 综述。  
- aiPlato，2026。  
- AI Peer，2025。  
- Physics-STAR，2024。  

**quantum mechanics 教育**

- Singh & Marshman, 2015。  
- Zhu & Singh, 2016。  
- McKagan, Perkins, Wieman, 2010. *QMCS*.  
- Marshman & Singh, 2020. *QMFPS*.  
- Sayer, Maries, Singh, 2020. QuILT 双缝。  
- 其他 QuILT / MZI / spin / QKD 系列。  

**simulation 与 computational learning**

- Jupyter 官方文档。  
- Johansson, Nation, Nori, 2011. *QuTiP*.  
- IBM Quantum Composer / OpenQASM 相关官方材料。  
- PhET 量子模拟与相关教育研究。  

**部署与治理**

- 中国生成式 AI 管理措施与备案制度材料，2023–2026。  
- 中国教育 AI 政策与高校课程改革报道，2025–2026。  
- LAUSD Ed 调查与后续报道，2024–2026。  
- 高校 AI-TA 部署案例（MPE、AstroTutor、Greek RAG chatbot 等）。  

### 六个可单独抽取的简版工件

#### 校正后的战略结论

Quantum Agent 不应被定义为通用大模型外壳上的“量子聊天框”，而应被定义为 **课程内、教师控制、工作流优先、验证增强、可审计、可扩展的量子课程助教系统**。首年目标不是最大化自治，而是最大化可信、最小帮助、可恢复和可评测。最优先价值来自：课程 grounding、误区诊断、推导步骤反馈、代码/模拟调试、教师/TA 分析与接管。最应避免的方向是：默认多代理、自动评分、学生端网页行动代理、把 RAG 当作正确性担保、把满意度当学习证据。fileciteturn0file0 citeturn49view1turn42academia2turn43academia0turn44academia0turn23academia2

#### 推荐的生产架构

前端分为学生入口、TA 队列、教师面板。中间层采用自定义确定性状态机，明确定义四条 workflow。LLM 只做分类、解释和摘要。工具层包括课程检索器、误区分类器、规则/符号 verifier、代码沙箱、QuTiP/Jupyter worker、日志与评测服务。治理层包括 hint gating、teacher override、权限控制、升级机制和审计日志。后续若长时跨会话项目增多，再迁移到 LangGraph 式 runtime。citeturn35view2turn25view1turn24academia3turn34view1

#### 学生与教师产品蓝图

学生端只保留四个模式：概念问答、步骤求助、代码调试、项目脚手架。教师端要有知识维护、班级误区热图、低置信度会话、TA 分诊、一键接管和策略配置。TA 端要像 Tutor CoPilot：会话摘要、困难会话优先级、参考回复草案和回放，而不是被系统从流程中移除。citeturn42academia2turn41view2turn43academia0

#### 框架决策简版

首年：**自定义状态机 > LangGraph > PydanticAI ≈ ADK > OpenAI Agents SDK > LlamaIndex > CrewAI > AutoGen**。  
推荐：总编排自己写；typed wrapper 用 PydanticAI；长时恢复需求高后再上 LangGraph；平台化需求高后再参考 ADK。原因：Quantum Agent 的难点是教学边界而不是 agent 炫技。citeturn35view2turn34view1turn51view2turn51view3

#### 顶级实现检查清单

1. 所有学生帮助都有 hint level。  
2. 默认禁止完整答案释放。  
3. 所有课程回答都附出处。  
4. 检索失败时显式说不确定。  
5. verifier 与 LLM 分离。  
6. 代码执行必须在容器沙箱。  
7. 资源限制、时间限制、文件限制齐全。  
8. 所有高风险会话可教师接管。  
9. 误区 taxonomy 先于 student model。  
10. 先做 single-course pilot。  
11. 先测 leakage，再谈 gains。  
12. 加入 AI 移除后的独立测验。  
13. 记录提示依赖率。  
14. 记录低置信度会话。  
15. 追踪每个工具调用。  
16. 保存教师修正以迭代策略。  
17. 项目式帮助分 milestone。  
18. notebook 模板由教师预写。  
19. 任何自动生成题先教师审。  
20. 禁止学生默认使用浏览器行动代理。  
21. 不把满意度写成学习效果。  
22. 不把产品页写成因果证据。  
23. 不把 pilot 写成成熟部署。  
24. 先支持 2–3 个高频章节。  
25. 加入 prompt injection 测试。  
26. 加入 citation fabrication 测试。  
27. 做教师与 TA 双方 usability。  
28. 做会话聚类和周报。  
29. 内容版本全可回滚。  
30. 知识与策略分层维护。  
31. 统计学生跳过思考直接索要答案的行为。  
32. 允许教师设置“只引导不直讲”模式。  
33. 允许教师标记“本章禁止自动解释”。  
34. 量子模拟要有 sanity checks。  
35. 对图表也要生成文字解释。  
36. 先支持中文，保留英文资料能力。  
37. 不做默认多代理。  
38. 不做自动评分首发。  
39. 不做全校 LMS 深耦合首发。  
40. 每学期结束做知识与误区资产沉淀。  

#### 验证过的优先阅读单

最值得先读的十项是：Anthropic *Building Effective AI Agents*；OpenAI *New tools for building agents*；OpenAI *Agents SDK Guide*；Google ADK *Why evaluate agents*；Tutor CoPilot；CodeAid；LLM-Tutor；量子困难综述；Zhu & Singh 的 QM 理解测评；QuTiP 文档/论文。它们分别对应：首年架构、工具层、审批与恢复、评测体系、TA Copilot、答案控制、推导帮助、量子误区 taxonomy、诊断仪器和数值层底座。citeturn49view1turn48view3turn48view5turn51view3turn42academia2turn43academia0turn44academia0turn23academia2turn23academia0turn24academia3