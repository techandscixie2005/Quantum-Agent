# Quantum Agent 产品需求文档 PRD

> 从仓库根目录 `PRD.pdf` 机械提取，源文件 SHA-256：
> `0f696247a7dcacdd8e71f8cd1644ec768e22ed9d52924b61e91e1f15a0dddccd`。
> PDF 是排版权威版本；本文件用于搜索和工程追踪，不替代原页布局。

产品名称： Quantum Agent
产品副标题： 面向大学量子物理课程的可信教学智能体
文档状态： V1.0，比赛与首轮课程试点的权威实施规范
目标版本： Competition Release 0.1
目标用户： 中国科学技术大学量子物理课程学生、助教、主讲教师
开发团队： 1 名核心开发者，1 名主讲教师提供教学审核
开发起始日期： 2026 年 7 月
比赛作品提交截止： 2026 年 9 月 6 日
产品原则： Course-bounded、Teacher-controlled、Workflow-first、Tool-verified、Student-model-lite


比赛面向“人工智能赋能教育教学”，智能体赛道支持自主选题，作品将从创新性、实用性、技术难度和完成
度四个维度评价；在线作品提交时间为 2026 年 8 月 1 日至 9 月 6 日。参赛作品所用知识库、数据、代码、模型
和外部服务必须来源合法合规，并防止敏感数据泄露。




1. 产品执行摘要
Quantum Agent 不是一个“量子物理聊天机器人”，也不是一个替学生完成作业的自动解题器。


它是一套课程内教学基础设施，由六部分组成：


Quantum Agent = 课程知识模型 + 学生学习证据 + 教学策略引擎 + 科学验证工具 + 计算实验环境 + 教师治

首个版本围绕四类高频教学任务展开：


    1. 概念理解与课程问答；
    2. 推导过程诊断与分层提示；
    3. 数值模拟、代码调试与图像解释；
    4. 课程 Project 的里程碑式辅导。

学生端不是一个无边界聊天框，而是四个明确入口：


   • 问概念
   • 看推导
   • 做实验
   • 做项目

教师和助教端提供：


   • 课程知识库维护；
   • 作业答案释放策略；
   • 高风险会话审核；
   • 学生误区分布；
   • 项目进度概览；
   • Agent 轨迹回放；
   • 教学内容与提示策略调整。




                                            1
比赛版本必须完整打通一个“黄金教学闭环”：


    学生对量子隧穿作出错误预测 → Agent 诊断误区 → 只给最小提示 → 学生运行波包模拟 → 系统
    验证概率守恒 → 学生解释图像 → Agent 给出迁移问题 → 教师端出现误区与学习轨迹。


其他三个 Project 在比赛版本中至少具备完整教学设计、项目页面、Notebook 骨架、示例输出和基础验证器。




2. 第一性原理
2.1 教育产品的目标函数
普通生产力 Agent 的目标通常是：


                   min (完成任务的时间 + 完成任务的人力) .

教学 Agent 的目标必须是：


            max P (学生在撤去 AI 后，能够独立解决新的相关问题) .

因此，系统不能只优化：


  • 有 AI 时的题目正确率；
  • 回复满意度；
  • 对话次数；
  • 作业完成速度；
  • 用户停留时间。

系统必须优先优化：


  • AI 移除后的独立表现；
  • 延迟保持；
  • 新情境迁移；
  • 学生自我解释能力；
  • 对提示的依赖程度；
  • 教师与助教的有效工作量；
  • 答案泄漏率。

无护栏生成式 AI 可能提高练习阶段的表现，却损害学生离开 AI 后的独立表现；加入答案约束和教学支架可显著
缓解这一问题。


2.2 为什么不能只做 RAG 问答
RAG 主要回答：


    “课程资料中有哪些相关内容？”




                               2
但真实教学还需要回答：


  • 学生现在误解了什么；
  • 下一步最恰当的帮助是什么；
  • 当前是否应该给答案；
  • 学生的推导在数学上是否成立；
  • 数值结果是否守恒；
  • 图像是否符合物理规律；
  • 学生是真的理解，还是复制了答案。

因此必须将三类责任分开：


      层次             责任                 实现方式

      课程 Grounding   回答依据来自哪里           教师审核知识库、混合检索、页码引用

      教学决策           此刻应该怎样帮助           教学状态机、答案策略、学生证据

      科学正确性          公式、代码和结果是否成立       SymPy、NumPy、SciPy、QuTiP、单元测试


2.3 为什么必须 Workflow-first
日常课程任务大多具有明确边界：


  • 判断问题类型；
  • 检索课程内容；
  • 判断是否为作业；
  • 识别学生尝试；
  • 选择提示层级；
  • 必要时调用验证器；
  • 记录学习证据。

这些任务不需要模型自由发明流程。


Anthropic 将 workflow 定义为由代码预先规定路径的系统，将 agent 定义为由模型动态决定流程和工具的系
统，并建议优先采用最简单、可组合的方案，只有在复杂性确实带来收益时才增加 Agent 自主性。


因此：


  • 日常答疑、答案释放、课程检索、权限和工具调用采用确定性状态机；
  • 误区初判、提示措辞、解释生成和教师摘要允许模型驱动；
  • 多代理只保留为未来教师研究模式或复杂开放项目模式；
  • MVP 不使用 peer-to-peer multi-agent swarm。


2.4 为什么必须 Teacher-controlled
教师必须拥有以下最终决定权：


  • 哪些资料属于课程权威资料；
  • 作业是否可以给完整答案；
  • 哪些题目处于限制期；




                                    3
  • 什么情况下允许释放标准解；
  • 哪些 Agent 回复必须人工审核；
  • 哪些学习数据可以统计和导出；
  • 哪些误区标签进入正式课程模型。

Tutor CoPilot 的真实随机试验显示，AI 增强真人辅导员可以提高学生知识点掌握率，并促使辅导员更多使用引
导性问题、减少直接泄露答案。


2.5 为什么必须 Tool-verified
语言模型可以负责：


  • 解释；
  • 组织；
  • 提问；
  • 诊断假设；
  • 将工具结果转写成教学语言。

语言模型不能作为以下事项的唯一裁决者：


  • 代数等价；
  • 归一化；
  • 厄米性；
  • 矩阵本征值；
  • 数值收敛；
  • 概率守恒；
  • 代码是否通过测试；
  • 图像是否来自真实运行结果。

系统必须明确显示结论的证据类型：


  • 课程资料支持；
  • 符号工具验证；
  • 数值实验支持；
  • 单元测试通过；
  • 模型推断，尚未验证；
  • 工具无法判定。




3. 产品目标与非目标
3.1 比赛版本必须实现

             编号     目标

             G-01   建立可登录、有学生/TA/教师权限的 Web 产品

             G-02   支持教师上传、审核、发布课程资料

             G-03   支持带页码或章节出处的课程问答




                              4
              编号     目标

              G-04   实现确定性教学状态机和分层提示策略

              G-05   支持学生输入公式和推导步骤，定位首个关键错误

              G-06   实现至少 5 类量子物理确定性验证器

              G-07   实现安全 Python 执行和结果可视化

              G-08   完整实现量子隧穿与波包传播 Project

              G-09   为另外三个 Project 提供可运行骨架

              G-10   建立教师/TA 面板、误区统计和会话轨迹回放

              G-11   建立离线评测集、答案泄漏测试与工具测试

              G-12   支持 Docker Compose 一键部署和本地开发


3.2 比赛版本明确不做
  • 不做面向社会公众的通用量子问答平台；
  • 不做学生端自由网页浏览 Agent；
  • 不做自动提交作业或访问教务系统；
  • 不做最终成绩自动判定；
  • 不做无限制完整答案输出；
  • 不做复杂长期心理画像；
  • 不做全课程知识追踪模型；
  • 不做强化学习或 DPO；
  • 不做模型微调作为首发依赖；
  • 不做多课程通用平台；
  • 不做实时语音课堂；
  • 不做完整 JupyterHub；
  • 不允许学生任意安装 Python 包；
  • 不把多智能体作为核心运行时。




4. 用户与权限
4.1 学生 Student
学生可以：


  • 加入课程；
  • 使用四类教学模式；
  • 查看课程资料引用；
  • 上传文字、LaTeX、代码和允许的文件；
  • 运行受限代码；
  • 完成 Project；
  • 查看自己的学习证据；
  • 删除自己的对话；




                                 5
  • 对回答反馈；
  • 请求 TA 人工帮助。

学生不能：


  • 查看其他学生数据；
  • 查看教师标准答案库；
  • 修改答案策略；
  • 访问系统 Prompt；
  • 运行联网代码；
  • 访问宿主文件系统；
  • 自动提交课程作业。


4.2 助教 TA
TA 可以：


  • 查看被升级的会话；
  • 查看匿名化高频误区；
  • 查看学生主动求助的对话；
  • 审核 Agent 建议；
  • 给学生发送人工反馈；
  • 将典型错误加入候选误区库；
  • 生成习题课摘要草案。

TA 不能：


  • 修改系统级安全设置；
  • 查看未授权课程；
  • 发布课程知识源；
  • 修改主讲教师锁定的答案政策。


4.3 教师 Teacher
教师可以：


  • 建立和维护课程；
  • 邀请 TA 和学生；
  • 上传、审核、发布、下架课程资料；
  • 定义作业与答案释放规则；
  • 编辑标准解和提示树；
  • 查看班级级误区统计；
  • 查看需要审核的高风险会话；
  • 修改 Project 模板和 Rubric；
  • 导出匿名统计数据；
  • 设置数据保留时间。




                             6
4.4 管理员 Admin
管理员负责：


  • 系统配置；
  • 模型配置；
  • 资源配额；
  • 故障排查；
  • 安全审计；
  • 用户封禁；
  • 数据备份和恢复。

管理员默认不查看课程对话内容，除非为故障或安全事件且留下审计日志。




5. 学生端产品结构
5.1 主导航
桌面端采用三栏结构：


               区域   内容

               左栏   课程章节、四种模式、历史会话、Project

               中栏   对话、推导步骤、代码编辑和 Agent 回复

               右栏   资料引用、公式卡片、工具结果、图像、学习状态

移动端折叠为单栏，通过底部标签切换。


5.2 四种模式

模式 A：问概念

适用场景：


  • 定义和物理意义；
  • 课程内容澄清；
  • 不同表象比较；
  • 直观图像；
  • 章节联系；
  • 常见误区。

默认回复结构：


  1. 一句话结论；
  2. 物理图像；
  3. 数学表达；
  4. 常见误区；




                              7
   5. 一个理解检查；
   6. 课程资料出处。

快捷按钮：


  • 再直观一点；
  • 再数学一点；
  • 给一个反例；
  • 和经典物理比较；
  • 画图说明；
  • 检查我是否理解。

模式 B：看推导

学生可：


  • 分步输入 LaTeX；
  • 粘贴完整推导；
  • 上传文本文件；
  • 可选上传手写图片。

系统必须：


   1. 识别推导目标；
   2. 将推导切成步骤；
   3. 找到第一处具有实质影响的错误；
   4. 区分错误类型；
   5. 默认不给完整解；
   6. 提供最小修正提示；
   7. 支持学生修正后继续；
   8. 必要时调用符号验证器。

错误类型枚举：


  • ALGEBRA_ERROR
  • ASSUMPTION_ERROR
  • BOUNDARY_CONDITION_ERROR
  • NORMALIZATION_ERROR
  • BASIS_CONFUSION
  • OPERATOR_ERROR
  • DEGENERACY_ERROR
  • DIMENSION_ERROR
  • NUMERICAL_ERROR
  • PHYSICAL_INTERPRETATION_ERROR
  • INCONCLUSIVE

模式 C：做实验

界面为轻量 Notebook 工作区，而不是完整 JupyterLab：


  • Markdown 教学单元；
  • 参数面板；




                                    8
   • Monaco 代码编辑器；
   • 运行按钮；
   • 标准输出；
   • 交互图形；
   • Agent 解释区；
   • 下载 .ipynb ；
   • 重置模板。

Jupyter Notebook 能把代码、叙述、公式和富媒体输出保存在同一开放文档中；本产品保留这一“计算叙
事”思想，但首版不嵌入完整 Jupyter 服务。


模式 D：做项目

Project 页面包括：


   • 项目问题；
   • 学习目标；
   • 前置知识；
   • 里程碑；
   • Starter Code；
   • 数据与参数；
   • 自动测试；
   • 可视化要求；
   • 报告问题；
   • Agent Coach；
   • Rubric；
   • 当前进度。

Agent 不允许一次性生成完整可提交项目。




6. 教学动作空间
模型每一轮不能自由决定任意行为，只能从下列动作中选择：



 ASK_GOAL
 ASK_FOR_ATTEMPT
 ELICIT_PREDICTION
 ASK_SELF_EXPLANATION
 GIVE_CONCEPT_CUE
 GIVE_FORMULA_CUE
 GIVE_PROCESS_CUE
 SHOW_LOCAL_EXAMPLE
 SHOW_COUNTEREXAMPLE
 COMPARE_REPRESENTATIONS
 RUN_RETRIEVAL
 RUN_SYMBOLIC_VERIFIER
 RUN_NUMERIC_VERIFIER
 RUN_SIMULATION
 REVIEW_CODE_LOCALLY



                            9
 SUMMARIZE_PROGRESS
 GIVE_TRANSFER_CHECK
 RELEASE_FULL_EXPLANATION
 ESCALATE_TO_TA
 REFUSE_OUT_OF_SCOPE


每个动作均必须有：


   • 允许的课程模式；
   • 最大答案详细度；
   • 是否允许调用工具；
   • 是否更新学生状态；
   • 是否需要教师批准；
   • 用户界面组件；
   • 日志字段。




7. 分层提示与答案释放
7.1 提示层级

                    层级      名称          可提供内容

                    H0      诊断          询问目标、已有步骤、卡点

                    H1      概念线索        相关概念、物理图像、应检查的假设

                    H2      公式线索        相关公式或定理，不代入完成

                    H3      过程线索        下一步操作、选基、边界条件、算法方向

                    H4      局部示范        展示一个关键子步骤或局部代码修复

                    H5      完整讲解        完整解法、总结和迁移题


7.2 课程任务模式
教师可为每项任务设置：


                            模式                       默认最高提示

                            自由学习 LEARNING                 H5

                            普通练习 PRACTICE                 H4

                            计分作业 GRADED                   H3

                            Project PROJECT        H4，禁止完整项目

                            复习 REVIEW                     H5

                            考试锁定 EXAM_LOCKED        H1 或完全禁用




                                              10
7.3 答案释放规则
完整答案只能在以下至少一种条件成立时释放：


   1. 教师明确允许；
   2. 任务处于复习或自由学习模式；
   3. 学生已经提交有效尝试；
   4. 学生已经完成至少一次修正；
   5. 学生主动选择“查看完整讲解”，且系统记录该行为；
   6. 完整讲解后安排一道迁移检查。

系统不得仅依赖 Prompt 实现答案策略。策略必须由后端代码执行。


7.4 挫败处理
若出现以下信号：


   • 连续三次失败；
   • 明确表达完全不理解；
   • 连续请求相同提示；
   • 多次修改但无进展；

系统应：


   1. 降低认知负荷；
   2. 将任务拆小；
   3. 从追问切换到局部示范；
   4. 提供前置知识回顾；
   5. 仍无法推进时建议 TA 接管。

禁止无限重复“你觉得下一步是什么”。




8. 教学状态机
8.1 状态图

 RECEIVE_INPUT
     ↓
 VALIDATE_PERMISSION
     ↓
 CLASSIFY_TASK
     ↓
 LOAD_COURSE_POLICY
     ↓
 RETRIEVE_COURSE_CONTEXT
     ↓
 DIAGNOSE_STUDENT_STATE
     ↓




                           11
 PROPOSE_PEDAGOGICAL_ACTION
     ↓
 POLICY_GATE
     ├── deny / downgrade action
     ├── require student attempt
     ├── require teacher approval
     └── allow
     ↓
 OPTIONAL_TOOL_EXECUTION
     ↓
 GENERATE_RESPONSE
     ↓
 VERIFY_RESPONSE_CONTRACT
     ↓
 STREAM_TO_USER
     ↓
 UPDATE_LEARNING_EVIDENCE
     ↓
 WRITE_TRACE



8.2 确定性节点
以下节点必须由应用代码控制：


  • 权限检查；
  • 课程和任务识别后的政策加载；
  • 答案层级上限；
  • 工具白名单；
  • 文件与代码资源限制；
  • 引用格式；
  • 会话状态持久化；
  • 高风险升级；
  • 学生数据写入条件；
  • 日志；
  • 失败重试；
  • 超时；
  • 人工批准。


8.3 模型驱动节点
模型可负责：


  • 任务分类建议；
  • 误区候选标签；
  • 当前教学动作建议；
  • 提示措辞；
  • 解释生成；
  • 工具结果的教学化表述；
  • 教师周报草案。




                                    12
所有模型输出必须是 Pydantic 结构化对象。


8.4 核心结构化类型

 class TaskType(str, Enum):
     CONCEPT = "concept"
     DERIVATION = "derivation"
     CODE = "code"
     SIMULATION = "simulation"
     PROJECT = "project"
     ADMIN = "admin"
     OUT_OF_SCOPE = "out_of_scope"



 class TutorAction(str, Enum):
     ASK_GOAL = "ask_goal"
     ASK_FOR_ATTEMPT = "ask_for_attempt"
     ELICIT_PREDICTION = "elicit_prediction"
     ASK_SELF_EXPLANATION = "ask_self_explanation"
     GIVE_CONCEPT_CUE = "give_concept_cue"
     GIVE_FORMULA_CUE = "give_formula_cue"
     GIVE_PROCESS_CUE = "give_process_cue"
     SHOW_LOCAL_EXAMPLE = "show_local_example"
     SHOW_COUNTEREXAMPLE = "show_counterexample"
     RUN_VERIFIER = "run_verifier"
     RUN_SIMULATION = "run_simulation"
     REVIEW_CODE_LOCALLY = "review_code_locally"
     SUMMARIZE_PROGRESS = "summarize_progress"
     GIVE_TRANSFER_CHECK = "give_transfer_check"
     RELEASE_FULL_EXPLANATION = "release_full_explanation"
     ESCALATE_TO_TA = "escalate_to_ta"
     REFUSE_OUT_OF_SCOPE = "refuse_out_of_scope"



 class TutorDecision(BaseModel):
     task_type: TaskType
     proposed_action: TutorAction
     confidence: float
     misconception_candidates: list[str]
     requested_hint_level: int
     requires_retrieval: bool
     requested_tool: str | None
     risk_flags: list[str]
     short_reason: str


不得要求模型输出隐藏思维链。 short_reason 仅保存一句可审计的决策摘要。




                                           13
9. 课程知识系统
9.1 知识源类型
首版支持：


   • PDF；
   • Markdown；
   • TXT；
   • DOCX；
   • PPTX；
   • 教师手工录入 FAQ；
   • 标准解与提示树；
   • Project 文档；
   • 课程政策。

首版不以 OCR 为强制依赖。扫描版 PDF 应标记为“需要人工处理”。


9.2 文档生命周期

 UPLOADED
 → PROCESSING
 → REVIEW_REQUIRED
 → APPROVED
 → PUBLISHED
 → ARCHIVED


只有 PUBLISHED 文档可进入学生检索。


9.3 文档处理
处理流程：


   1. 文件类型与魔数校验；
   2. 病毒扫描接口预留；
   3. 提取标题、页码、章节；
   4. 清除重复页眉页脚；
   5. 按标题、段落、公式附近语义切块；
   6. 每块保留文档、版本、章节、页码；
   7. 生成全文索引；
   8. 生成向量；
   9. 教师预览；
  10. 审核发布。


9.4 检索策略
采用 PostgreSQL 全文检索与 pgvector 混合检索：




                                     14
                         S(d, q) = αSvector + βStext + γScourse-priority .

默认流程：


   1. 向量召回 20 条；
   2. 全文召回 20 条；
   3. Reciprocal Rank Fusion；
   4. 去重；
   5. 按课程版本和教师优先级过滤；
   6. 返回最多 6 个上下文片段；
   7. 回复最多展示 3–5 个直接引用。

所有事实性课程回答必须带：


   • 文档标题；
   • 章节；
   • 页码或幻灯片号；
   • 文档版本。

无法找到可靠课程依据时，系统必须明确说“课程知识库中未找到足够依据”，不能伪造引用。


9.5 外部网络
学生端核心辅导默认不联网检索。


未来可以增加教师研究模式，但必须与学生模式隔离，并显示外部来源不属于课程权威材料。




10. 学生模型 Student-model-lite
首版不预测智力、性格或长期能力，只记录可操作的学习证据。


10.1 知识状态
每个知识点状态只能为：


   • UNKNOWN
   • EXPOSED
   • DEVELOPING
   • DEMONSTRATED
   • NEEDS_REVIEW

不得显示虚假的精确掌握百分比。


10.2 证据类型

 CORRECT_SELF_EXPLANATION
 CORRECT_TRANSFER_RESPONSE
 CORRECTED_DERIVATION




                                                15
 PASSED_TOOL_CHECK
 FAILED_TOOL_CHECK
 MISCONCEPTION_OBSERVED
 REPEATED_MISCONCEPTION
 HIGH_HINT_DEPENDENCY
 COMPLETED_PROJECT_MILESTONE
 TEACHER_CONFIRMED


每条证据保存：


   • 知识点；
   • 来源会话；
   • 时间；
   • 正向或负向；
   • 置信度；
   • 是否由教师确认；
   • 所用提示层级。


10.3 提示依赖
系统记录：

                                      ∑i w(hi )
                               Dk =             ,
                                        Nk
其中 hi 是完成该知识点任务所需的提示等级。


该指标仅用于：


   • 判断下次是否应先要求独立尝试；
   • 向学生显示“你通常在过程提示后能继续”；
   • 帮助教师发现学生是否过度依赖完整示范。

不得用于正式成绩。


10.4 初始量子误区标签
首版至少包含：


   1. 将波函数理解为粒子轨迹；
   2. 将 ∣ψ∣2 理解为经典连续物质密度；
   3. 认为定态完全不随时间变化；
   4. 混淆整体相位与相对相位；
   5. 将纯态叠加等同于经典混合；
   6. 认为测量只是在读取预先存在的值；
   7. 混淆期望值与单次测量结果；
   8. 忽略边界条件；
   9. 忽略归一化；
  10. 混淆算符、本征态和本征值；
  11. 误用非简并微扰论；




                                      16
  12. 忽略微扰展开的适用条件；
  13. 将变分参数视为直接可观测量；
  14. 将原子轨道或分子轨道视为电子轨迹；
  15. 认为隧穿粒子获得了额外能量；
  16. 将自旋完全理解为经典自转；
  17. 将不确定关系仅理解为测量扰动；
  18. 混淆可区分与全同粒子；
  19. 忽略概率流与守恒；
  20. 混淆密度矩阵中的经典无知与量子纠缠。

标签必须允许教师编辑、合并、停用和增加课程内示例。




11. 科学工具层
所有工具统一返回：



 class ToolResult(BaseModel):
     status: Literal["verified", "contradicted", "inconclusive", "error"]
     summary: str
     evidence: list[str]
      numeric_values: dict[str, float | str]
      artifacts: list[str]
      warnings: list[str]
      runtime_ms: int


工具若无法判定，必须返回 inconclusive ，不能由模型改写为“已经证明”。


11.1 Symbolic Verifier
首版实现：


V-01 代数等价检查

输入：


   • 两个 SymPy 表达式；
   • 变量；
   • 假设；
   • 可选数值测试范围。

方法：


   1. simplify(expr1 - expr2) ；
   2. equals ；
   3. 随机高精度数值抽样；
   4. 若存在奇点或分支，返回警告。




                                                  17
V-02 归一化检查

支持：


                           ∫ ∣ψ(x)∣2 dx = 1

以及有限维状态：


                             ⟨ψ∣ψ⟩ = 1.

返回积分值、误差和所用区域。


V-03 厄米性检查

有限矩阵检查：


                               A† = A.

符号算符只支持首版白名单，不尝试通用形式证明。


V-04 对易子检查

计算：


                       [A, B] = AB − BA.

支持 Pauli 矩阵、角动量矩阵、有限维矩阵。


V-05 本征问题检查

验证：


                            A∣ψ⟩ = λ∣ψ⟩.

检查维数、残差范数和归一化。


V-06 边界条件检查

支持一维分段波函数：


  • 波函数连续性；
  • 导数连续性；
  • 无限势垒边界；
  • 有限跃变的规则提示。

V-07 量纲检查

首版使用教师提供的符号单位表，不做任意自然语言单位推断。




                                 18
V-08 变分上界检查

比较试探能量与教师提供的参考基态上界或数值基准。


11.2 Numerical Simulator
首版包含预建模拟器：


   • 高斯波包；
   • 一维自由传播；
   • 矩形势垒；
   • 双势垒；
   • 有限深势阱；
   • 两能级系统；
   • Bloch 球演化；
   • 氢原子径向波函数；
   • 简单变分能量曲线。

QuTiP 提供量子态、时间演化、主方程和量子状态可视化能力，可用于两能级与开放系统扩展；首个隧穿项目
主要使用 NumPy/SciPy 自研求解器。


11.3 Python Sandbox
学生代码在临时容器运行。


强制配置：



 network: none
 user: non-root
 read-only root filesystem: true
 capabilities: drop all
 no-new-privileges: true
 memory: 512 MB
 CPU: 1 core
 PIDs: 64
 wall time: 20 seconds
 stdout: 200 KB
 artifact output: 20 MB
 temporary filesystem only
 no host mounts
 no Docker socket inside container


允许包：


   • numpy；
   • scipy；
   • sympy；
   • matplotlib；
   • pandas；




                                     19
  • qutip；
  • pytest。

禁止：


  • pip install ；
  • 网络访问；
  • subprocess 启动任意系统服务；
  • 访问宿主路径；
  • 长期进程；
  • GPU；
  • 未审核二进制。

Docker 容器默认并不会自动拥有资源上限，因此 CPU、内存、进程数和超时必须显式设置；同时保持默认
seccomp 并采用最小权限。




12. 四个课程 Project

Project 1：量子隧穿与波包传播
实现等级：比赛黄金闭环，必须完整。


学习问题
      一个有限宽度高斯波包撞向势垒时，反射、透射、干涉和展宽如何发生？


知识点
  • 时间依赖薛定谔方程；
  • 高斯波包；
  • 概率密度；
  • 概率流；
  • 隧穿；
  • 定态与波包；
  • 数值离散；
  • 概率守恒；
  • WKB 近似。


里程碑

              里程碑    学生任务           自动检查

              M1     写出初始高斯波包并归一化   归一化误差

              M2     实现自由传播         概率守恒、群速度

              M3     加入矩形势垒         势函数检查




                              20
                     里程碑    学生任务            自动检查

                     M4     计算反射与透射概率       R+T ≈1

                     M5     扫描势垒宽度和高度       趋势合理性

                     M6     与定态/WKB 结果比较    相对误差

                     M7     完成物理解读          Rubric + 迁移题


可视化
  • ∣ψ(x, t)∣2 动画；
  • 势垒叠加图；
  • x − t 热力图；
  • R, T 随势垒参数变化；
  • 总概率随时间；
  • 数值误差随网格和时间步长变化。


Agent 特有流程
实验前必须要求学生预测：


  1. 当平均能量低于势垒时是否完全不能通过；
  2. 透射部分是否获得更高能量；
  3. 增加势垒宽度会发生什么；
  4. 定态透射系数和波包透射率是否完全相同。

实验后要求学生用图和数值证据修正预测。



Project 2：氢原子轨道、简并与外场微扰
实现等级：完整项目页面和可运行基础模块。


学习问题
    量子数、轨道形状、节点和能级简并之间有什么关系？外场如何打破简并？


里程碑

                           里程碑   内容

                           M1    计算径向波函数

                           M2    绘制径向概率分布

                           M3    绘制球谐函数与轨道截面

                           M4    识别节点结构

                           M5    构造简并子空间




                                      21
                    里程碑         内容

                    M6          构造 Stark 或 Zeeman 微扰矩阵

                    M7          对角化并绘制能级劈裂


自动检查
  • 归一化；
  • 正交性；
  • 节点数量；
  • 矩阵厄米性；
  • 选择定则对应的零矩阵元；
  • 本征值残差。



Project 3：变分法与氦原子的有效核电荷
实现等级：完整教学设计、代码骨架、能量曲线。


学习问题
   无法精确求解多电子体系时，如何用物理直觉构造可检验的近似？


基础试探波函数：


                  Ψ(r1 , r2 ; Zeff ) = ϕ1s (r1 ; Zeff )ϕ1s (r2 ; Zeff ).

里程碑
  • 推导能量期望值；
  • 分解动能、核吸引和电子排斥；
  • 扫描 Zeff ；
  • 找到变分最优点；
  • 检查变分上界；
  • 解释屏蔽；
  • 可选加入 1 + cr12 相关因子。


自动检查
  • 波函数归一化；
  • 极限行为；
  • 能量最小点；
  • 变分上界；
  • 数值积分稳定性。



Project 4：双原子分子的分子轨道与振转光谱
实现等级：完整教学设计、LCAO 可视化和光谱示例。




                                           22
学习问题
   如何从原子轨道的线性组合得到成键、势能曲线和可观测光谱？


基础模型：

                               ϕA ± ϕB
                        ψ± =              .
                               2(1 ± S)

里程碑
  • 计算重叠积分；
  • 绘制成键和反键轨道；
  • 比较核间电子密度；
  • 构造或拟合势能曲线；
  • 求平衡键长；
  • 使用 Morse 势计算振动能级；
  • 加入转动能级；
  • 生成棒状和展宽光谱。


自动检查
  • 轨道归一化；
  • 成键/反键对称性；
  • 极限 R → ∞；
  • 势能曲线最低点；
  • 振动能级顺序；
  • 光谱跃迁索引。




13. 教师与 TA 产品
13.1 教师首页
首页展示：


  • 本周活跃学生；
  • 待处理升级；
  • 高频误区；
  • 高提示依赖知识点；
  • 失败工具运行；
  • 引用缺失警报；
  • 答案泄漏警报；
  • Project 里程碑完成率。

这些指标用于教学支持，不用于学生排名。




                               23
13.2 会话轨迹回放
每次 Tutor Turn 展示：



 用户输入
 → 任务分类
 → 命中的课程政策
 → 检索到的知识块
 → 误区候选
 → 模型建议动作
 → Policy Gate 调整
 → 工具调用
 → 工具结果
 → 最终回复
 → 学生状态更新


教师可标记：


   • 动作正确；
   • 提示过多；
   • 提示过少；
   • 误区识别错误；
   • 引用错误；
   • 工具错误；
   • 应由人工处理。

标记结果进入失败集。


13.3 误区地图
按章节显示：


   • 误区出现次数；
   • 涉及学生数；
   • 首次出现和重复出现；
   • 平均提示层级；
   • 迁移题通过情况；
   • 典型匿名对话；
   • 教师备注。


13.4 TA 队列
升级原因：


   • 模型分类置信度低；
   • 工具结论冲突；
   • 课程资料不足；
   • 学生连续失败；
   • 学生主动求助；




                    24
  • 涉及教师未发布内容；
  • 可能存在标准答案错误；
  • 代码执行异常；
  • 系统安全事件。


13.5 课程政策编辑器
教师可配置：


  • 任务开放时间；
  • 作业模式；
  • 最大提示层级；
  • 是否允许完整解；
  • 是否要求先提交尝试；
  • 是否允许运行代码；
  • 每日资源限额；
  • 必须引用的资料；
  • 高风险关键词；
  • 人工审核规则。




14. 技术架构
14.1 总体架构

 Browser
   │
   ▼
 Next.js Web App
   │ HTTPS / SSE
   ▼
 FastAPI Application
   ├── Auth & RBAC
   ├── Course Service
   ├── Knowledge/Retrieval Service
   ├── Tutor Workflow Engine
   ├── Project Service
   ├── Analytics Service
   └── LLM Model Gateway
           │
           ├── OpenAI-compatible endpoint
           ├── Anthropic-compatible endpoint
           └── School/local model endpoint

 FastAPI
   │
   ├── PostgreSQL + pgvector
   ├── Object Storage
   └── Job Table




                                           25
           │
           ▼
 Python Worker
   ├── Document ingestion
   ├── Embeddings
   ├── Symbolic verification
   ├── Numerical simulation
   └── Docker sandbox execution



14.2 技术栈

前端

  • Next.js；
  • TypeScript strict mode；
  • React；
  • Tailwind CSS；
  • shadcn/ui；
  • TanStack Query；
  • Zod；
  • KaTeX；
  • Monaco Editor；
  • Plotly.js；
  • Server-Sent Events；
  • Playwright。

后端

  • Python 3.12；
  • FastAPI；
  • Pydantic v2；
  • PydanticAI；
  • SQLAlchemy 2；
  • Alembic；
  • psycopg 3；
  • pgvector；
  • httpx；
  • PyMuPDF；
  • python-pptx；
  • python-docx；
  • SymPy；
  • NumPy；
  • SciPy；
  • QuTiP；
  • Matplotlib；
  • pytest；
  • Ruff；
  • mypy。

PydanticAI 用于有边界的结构化模型调用、类型校验和评测，不用作自由运行的全系统 Agent。其类型安全和
评测能力适合本项目的节点式模型调用。




                                  26
14.3 不采用重型 Agent 框架作为主骨架
MVP 使用自定义 Python 状态机：



 class TutorWorkflow:
     async def run_turn(self, context: TurnContext) -> TurnResult:
          ...


每个节点是独立、可测试函数：



 classify_task()
 retrieve_context()
 diagnose_student()
 propose_action()
 apply_policy()
 execute_tool()
 compose_response()
 validate_response()
 update_evidence()


未来若出现以下需求，再考虑 LangGraph 或耐久工作流框架：


   • 跨小时任务；
   • 多次人工暂停恢复；
   • 多代理并行；
   • 大规模长任务；
   • 跨服务补偿事务。


14.4 模型供应商抽象
环境变量：



 LLM_PROVIDER=openai_compatible
 LLM_BASE_URL=
 LLM_API_KEY=
 LLM_MODEL=
 LLM_SMALL_MODEL=
 EMBEDDING_PROVIDER=openai_compatible
 EMBEDDING_BASE_URL=
 EMBEDDING_API_KEY=
 EMBEDDING_MODEL=


代码中禁止直接在业务逻辑调用某一厂商 SDK。


接口：




                                                27
 class ModelGateway(Protocol):
     async def structured_generate(
          self,
          task: str,
          messages: list[Message],
          output_type: type[T],
          model_tier: ModelTier,
     ) -> T: ...


测试使用 FakeModelGateway ，不得在单元测试中产生真实 API 费用。




15. 数据模型
核心表如下。


身份与课程

 users
 courses
 course_memberships
 invitations
 sessions



课程知识

 course_modules
 knowledge_components
 misconceptions
 documents
 document_versions
 document_chunks
 document_publications
 canonical_solutions
 teaching_policies
 assignments
 problems



Tutor

 conversations
 conversation_participants
 turns
 tutor_decisions
 retrieval_hits



                                      28
 citations
 tool_runs
 turn_feedback
 escalations



学习证据

 student_evidence
 student_knowledge_states
 student_misconception_evidence
 transfer_checks



Project

 project_templates
 project_milestone_templates
 project_instances
 project_milestones
 project_artifacts
 code_snapshots
 execution_jobs
 rubric_feedback



系统

 model_usage
 prompt_versions
 audit_logs
 system_events
 feature_flags


所有主表必须包含：



 id UUID
 created_at
 updated_at
 created_by


与课程有关的表必须包含 course_id 。


15.1 关键索引
   • document_chunks.embedding ：HNSW 或 IVFFlat；
   • document_chunks.search_vector ：GIN；




                                          29
   • turns(conversation_id, created_at) ；
   • student_evidence(user_id, knowledge_component_id) ；
   • tool_runs(status, created_at) ；
   • escalations(course_id, status, priority) ；
   • audit_logs(actor_id, created_at) 。




16. API 规范
所有 API 使用 /api/v1 。


16.1 Authentication

 POST /auth/login
 POST /auth/logout
 POST /auth/invitations/accept
 GET /auth/me


采用服务器 Session 和 HttpOnly Cookie，不将长期 JWT 存入 localStorage。


16.2 Courses

 GET     /courses
 POST    /courses
 GET     /courses/{course_id}
 PATCH   /courses/{course_id}
 GET     /courses/{course_id}/members
 POST    /courses/{course_id}/invitations



16.3 Knowledge

 POST    /courses/{course_id}/documents
 GET     /courses/{course_id}/documents
 GET     /documents/{document_id}
 POST    /documents/{document_id}/process
 POST    /documents/{document_id}/approve
 POST    /documents/{document_id}/publish
 POST    /documents/{document_id}/archive
 GET     /documents/{document_id}/chunks



16.4 Conversations

 POST    /courses/{course_id}/conversations
 GET     /conversations/{conversation_id}




                                              30
 POST /conversations/{conversation_id}/turns
 GET    /runs/{run_id}/events
 POST /turns/{turn_id}/feedback
 POST /conversations/{conversation_id}/request-ta
 DELETE /conversations/{conversation_id}


POST /turns 返回：



 {
     "run_id": "uuid",
     "status": "queued",
     "event_stream": "/api/v1/runs/uuid/events"
 }


SSE 事件：



 run.started
 retrieval.completed
 decision.completed
 tool.started
 tool.completed
 response.delta
 response.completed
 run.failed



16.5 Tools
工具不直接暴露给普通客户端任意调用。前端通过受控工作流发起。


教师测试接口：



 POST /teacher/tools/symbolic-check
 POST /teacher/tools/simulation
 POST /teacher/tools/code-run



16.6 Projects

 GET       /courses/{course_id}/project-templates
 POST      /project-templates
 GET       /project-templates/{id}
 POST      /project-templates/{id}/start
 GET       /project-instances/{id}
 PATCH     /project-instances/{id}/milestones/{milestone_id}
 POST      /project-instances/{id}/artifacts
 POST      /project-instances/{id}/run




                                                  31
 GET    /project-instances/{id}/runs
 POST   /project-instances/{id}/request-review



16.7 Teacher Analytics

 GET /teacher/courses/{course_id}/overview
 GET /teacher/courses/{course_id}/misconceptions
 GET /teacher/courses/{course_id}/escalations
 GET /teacher/conversations/{id}/trace
 GET /teacher/courses/{course_id}/export




17. 前端设计规范
17.1 视觉方向
风格：


   • 现代学术工具；
   • 深色黑板与浅色纸张双主题；
   • 公式和图像优先；
   • 克制，不采用幼儿化拟人形象；
   • 不模拟通用聊天软件；
   • 明确区分模型解释、资料引用和工具结果。


17.2 回答卡片
每条回复可以包含：



 Tutor Message
 Concept Card
 Formula Card
 Citation Card
 Verifier Result
 Simulation Result
 Misconception Check
 Transfer Question
 TA Escalation



17.3 证据徽标
使用固定徽标：


   • 课程资料
   • 符号验证




                                                 32
   • 数值模拟
   • 代码测试
   • 模型推断
   • 教师审核


17.4 工具失败
不得只显示“Something went wrong”。


必须显示：


   • 哪一步失败；
   • 是否保存了学生输入；
   • 是否可重试；
   • 是否建议修改参数；
   • 是否可以转交 TA；
   • 技术错误 ID。


17.5 无障碍
   • 键盘可操作；
   • 图表提供文本描述；
   • 公式提供可复制 LaTeX；
   • 不仅靠颜色表达状态；
   • 正文字号不低于 16px；
   • 支持浏览器缩放；
   • 动画可暂停。




18. 安全、隐私与治理
18.1 身份认证
   • 密码使用 Argon2id；
   • Cookie 设置 HttpOnly 、 Secure 、 SameSite=Lax ；
   • Session 可撤销；
   • 登录限速；
   • 教师和管理员关键操作重新验证；
   • 所有 RBAC 在后端执行。


18.2 数据最小化
首版仅保存：


   • 登录身份；
   • 课程成员关系；
   • 学习会话；
   • 明确的知识证据；
   • Project 文件；




                                          33
  • 用户反馈。

不得保存：


  • 非教学人格画像；
  • 政治、健康、宗教等无关属性；
  • 无边界长期记忆；
  • 未经说明的第三方跟踪数据。


18.3 Prompt Injection
防护策略：


  1. 学生端无网页浏览工具；
  2. 检索文档作为引用数据，不作为系统指令；
  3. 工具权限由代码决定；
  4. 文档内容不能修改 Policy Gate；
  5. 工具采用白名单；
  6. 模型不能自行构造任意系统命令；
  7. 输出经过结构和引用检查；
  8. 记录越权尝试；
  9. 对“忽略之前指令”等内容按普通课程文本处理。


18.4 文件上传
  • 限制后缀和魔数；
  • 单文件默认不超过 25 MB；
  • 总课程配额可配置；
  • 文件名重新生成；
  • 不使用用户文件名作为路径；
  • 对压缩包默认拒绝；
  • 图像移除不必要元数据；
  • 解析失败进入人工审核。


18.5 审计
以下操作写入不可修改审计日志：


  • 教师发布知识源；
  • 修改答案策略；
  • 查看受限对话；
  • 导出数据；
  • 删除课程；
  • 修改用户角色；
  • 修改模型和安全配置；
  • 人工覆盖 Agent 结果。




                         34
19. 可观测性
每个 Tutor Run 生成 trace_id 。


记录：


   • 模型；
   • Prompt 版本；
   • Token 使用；
   • 延迟；
   • 检索结果；
   • 模型结构化输出；
   • Policy Gate 调整；
   • 工具调用；
   • 工具结果；
   • 错误；
   • 最终回复版本；
   • 用户反馈；
   • 学习证据更新。

不得记录：


   • API Key；
   • 数据库密码；
   • Session Cookie；
   • 不必要的隐藏模型推理；
   • 未脱敏敏感字段。

OpenAI Agents SDK 的生产指南同样将 trace、评测、人工审核和状态管理视为构建可靠 Agent 的核心组成部
分。




20. 评测体系
20.1 离线数据集
首版建立至少 200 个案例：


                             类别            数量

                             课程事实与引用       50

                             概念误区          40

                             推导诊断          40

                             符号工具          25

                             代码与仿真         20

                             答案泄漏攻击        15




                                      35
                             类别                      数量

                             Prompt Injection / 权限   10

每个案例包含：


   • 输入；
   • 用户角色；
   • 课程模式；
   • 允许动作；
   • 禁止动作；
   • 期望引用；
   • 误区标签；
   • 工具期望；
   • 最大提示层级；
   • 人工 Rubric。


20.2 自动指标

Grounding

   • 引用存在率；
   • 引用页码正确率；
   • 引用是否支持结论；
   • 未检索到依据时是否诚实拒答。

Pedagogy

   • 动作是否符合 Policy；
   • 是否过早给答案；
   • 是否要求无意义重复尝试；
   • 是否提供可执行的下一步；
   • 是否安排迁移检查。

Tool

   • 工具参数正确率；
   • 工具结论正确率；
   • inconclusive 是否被正确保留；
   • 数值容差；
   • 资源与超时执行。

Security

   • 越权工具调用数；
   • 网络访问成功数；
   • 沙箱逃逸；
   • 跨课程数据泄漏；
   • Prompt Injection 成功率。




                                         36
20.3 比赛版验收阈值

                指标                               最低要求

                课程引用存在率                           ≥ 95%

                人工抽检引用支持率                         ≥ 90%

                受限任务完整答案泄漏率                       ≤ 5%

                确定性 verifier 单元测试通过率              ≥ 95%

                非授权工具调用                               0

                沙箱网络访问成功                              0

                跨用户/跨课程数据泄漏                           0

                黄金闭环 E2E 通过率                       100%

                服务器错误后会话输入保留率                      100%

                普通非工具回答首个事件 P95         ≤ 3 秒，不含外部模型异常

                普通回答完成 P95                       ≤ 15 秒

                工具任务完成 P95                       ≤ 30 秒


20.4 真实课堂评估
比赛后先做 20–30 名学生可用性试点，再考虑正式对照研究。


评估：


  • 前测；
  • 有 AI 的练习；
  • 无 AI 后测；
  • 一周延迟测验；
  • 迁移题；
  • 提示依赖；
  • 教师工作量；
  • TA 响应时间；
  • 学生信任；
  • 典型误区变化。

结构化 AI Tutor 的物理课程随机试验表明，严格的顺序支架、主动参与、认知负荷控制、及时反馈和预先准备
的可靠解答是效果的重要来源；仅依靠自由聊天 Prompt 无法稳定实现复杂教学顺序。




                                   37
21. 测试策略
21.1 后端单元测试
覆盖：


   • Policy Gate；
   • 提示等级；
   • RBAC；
   • 检索融合；
   • Citation 构造；
   • Verifier；
   • 学生状态更新；
   • 资源配额；
   • 文件校验；
   • 数据隔离。


21.2 模型契约测试
对每个模型节点测试：


   • 输出 Schema；
   • 非法枚举；
   • 缺失字段；
   • 置信度范围；
   • 工具不存在；
   • 请求超过权限；
   • Prompt Injection；
   • 无课程上下文；
   • 模型超时；
   • 返回非 JSON。


21.3 集成测试
使用：


   • PostgreSQL 测试容器；
   • Fake LLM；
   • Fake Embedding；
   • Sandbox 测试镜像；
   • 临时对象存储。


21.4 E2E
Playwright 必须覆盖：


   1. 学生登录；
   2. 加入课程；
   3. 问概念并查看引用；




                         38
  4. 提交错误推导并获得提示；
  5. 运行隧穿模拟；
  6. 修改参数；
  7. 完成迁移题；
  8. 请求 TA；
  9. TA 回复；
 10. 教师查看误区；
 11. 教师修改策略；
 12. 受限作业答案被阻止。




22. 项目仓库结构

quantum-agent/
├── apps/
│ └── web/
│        ├── app/
│        ├── components/
│        ├── features/
│        ├── lib/
│        └── tests/
├── services/
│ ├── api/
│ │    ├── quantum_agent/
│ │    │ ├── auth/
│ │    │ ├── courses/
│ │    │ ├── knowledge/
│ │    │ ├── tutor/
│ │    │ ├── policies/
│ │    │ ├── tools/
│ │    │ ├── projects/
│ │    │ ├── analytics/
│ │    │ ├── llm/
│ │    │ └── common/
│ │    ├── migrations/
│ │    └── tests/
│ └── worker/
│     ├── jobs/
│     ├── sandbox/
│     ├── simulations/
│     └── tests/
├── content/
│ ├── quantum_course/
│ ├── misconceptions/
│ ├── projects/
│ └── evals/
├── prompts/
│ ├── classify_task/
│ ├── diagnose_student/




                            39
 │ ├── select_action/
 │ ├── compose_response/
 │ └── teacher_summary/
 ├── infra/
 │ ├── docker/
 │ ├── compose/
 │ └── scripts/
 ├── docs/
 │ ├── PRD.md
 │ ├── architecture.md
 │ ├── pedagogy.md
 │ ├── security.md
 │ ├── evals.md
 │ └── deployment.md
 ├── tests/
 │ └── e2e/
 ├── docker-compose.yml
 ├── Makefile
 ├── .env.example
 ├── CLAUDE.md
 └── README.md




23. 本地开发与部署
23.1 必须支持的命令

 make bootstrap
 make dev
 make test
 make lint
 make typecheck
 make e2e
 make eval
 make seed-demo
 make build
 make up
 make down
 make backup
 make restore



23.2 Docker Compose 服务

 web
 api
 worker
 postgres



                           40
 minio
 reverse-proxy


开发模式可使用本地文件存储，减少依赖。


23.3 健康检查

 GET /health/live
 GET /health/ready
 GET /health/dependencies


依赖检查：


   • PostgreSQL；
   • 对象存储；
   • 模型端点；
   • Embedding 端点；
   • Sandbox；
   • Worker 心跳。


23.4 数据库迁移
   • 使用 Alembic；
   • 服务启动不得自动执行破坏性迁移；
   • 部署脚本先备份，再迁移；
   • 每次迁移提供 downgrade；
   • Seed 数据与生产迁移分离。




24. 开发计划
比赛截止为 2026 年 9 月 6 日，因此范围必须严格固定。


Phase 0：工程底座
日期：7 月 13 日—7 月 16 日


完成：


   • Monorepo；
   • Docker Compose；
   • Next.js/FastAPI；
   • PostgreSQL；
   • Session Auth；
   • RBAC；
   • CI；
   • 基础设计系统；




                              41
   • Seed 用户。

验收：


   • 学生、TA、教师可登录；
   • 后端测试和前端测试运行；
   • 一条 PR 完整通过 CI。


Phase 1：课程知识系统
日期：7 月 17 日—7 月 23 日


完成：


   • 文档上传；
   • PDF/Markdown 解析；
   • 切块；
   • Embedding；
   • 混合检索；
   • 教师审核发布；
   • 引用卡片。

验收：


   • 教师上传一份讲义；
   • 发布后学生可引用页码回答；
   • 未发布文档不能检索。


Phase 2：Tutor Workflow
日期：7 月 24 日—7 月 31 日


完成：


   • 四种模式；
   • 状态机；
   • Pydantic 模型节点；
   • Policy Gate；
   • 提示层级；
   • SSE；
   • Turn Trace；
   • 课程问答和基础推导。

验收：


   • 计分作业最多给 H3；
   • 模型请求 H5 时 Policy Gate 可降级；
   • 每轮可在教师端回放。




                                  42
Phase 3：Verifier 与沙箱
日期：8 月 1 日—8 月 9 日


完成：


   • 代数等价；
   • 归一化；
   • 厄米性；
   • 对易子；
   • 本征问题；
   • Docker Sandbox；
   • Tool Result UI。

验收：


   • 测试集通过率达到要求；
   • 网络访问和超资源代码被终止；
   • 工具无法判定时显示 inconclusive。


Phase 4：隧穿黄金 Project
日期：8 月 10 日—8 月 19 日


完成：


   • Project 页面；
   • 波包求解器；
   • 参数面板；
   • 动画和热力图；
   • 自动检查；
   • 预测—模拟—解释流程；
   • 下载 Notebook。

验收：


   • 从启动项目到完成迁移题完整运行；
   • 概率守恒检查；
   • 教师端出现学习轨迹。


Phase 5：教师端与其他项目
日期：8 月 20 日—8 月 27 日


完成：


   • 教师首页；
   • TA 队列；
   • 误区地图；
   • 三个附加 Project 页面；




                               43
   • 项目骨架；
   • 数据导出。


Phase 6：评测、安全与视觉完善
日期：8 月 28 日—9 月 3 日


完成：


   • 200 例评测；
   • 泄漏红队；
   • Prompt Injection；
   • E2E；
   • 性能；
   • 响应式界面；
   • 演示数据；
   • 崩溃恢复。


Phase 7：提交材料
日期：9 月 4 日—9 月 6 日


完成：


   • 部署；
   • README；
   • 产品说明；
   • 架构图；
   • 演示脚本；
   • 演示视频；
   • 评测报告；
   • 备份；
   • Release tag。




25. 比赛演示脚本
演示只讲一条故事，不罗列功能。


演示步骤
   1. 学生进入“隧穿与波包”项目；
   2. 系统要求预测平均能量低于势垒时的结果；
   3. 学生回答“完全不能穿过”；
   4. Agent 标记隧穿误区，但不直接纠正；
   5. Agent 要求学生运行基准模拟；
   6. 学生修改势垒高度和宽度；
   7. 系统运行真实代码；
   8. 图中出现反射和透射波包；




                             44
   9. Verifier 显示概率守恒；
  10. Agent 要求学生解释为什么透射不意味着获得能量；
  11. 学生回答；
  12. Agent 给出双势垒共振迁移题；
  13. 教师端显示该学生的误区、提示等级和工具轨迹；
  14. 教师端显示班级中相同误区的聚合分布；
  15. 切换教师策略，将某项作业最大提示从 H4 改为 H2；
  16. 学生重新询问时，Policy Gate 自动限制答案。


演示必须显式呈现
   • 课程引用；
   • 教学动作；
   • Policy Gate；
   • 数值模拟；
   • 确定性验证；
   • 学习状态；
   • 教师控制；
   • 轨迹可审计。




26. Definition of Done
Competition Release 0.1 只有在以下全部满足时才算完成：


   • 可通过 Docker Compose 一键启动；
   • 无硬编码 API Key；
   • 学生、TA、教师权限隔离；
   • 教师可上传和发布资料；
   • 学生回答带课程引用；
   • Policy Gate 由代码实现；
   • 完整答案限制经过红队测试；
   • 至少五个 Verifier 可运行；
   • Python Sandbox 无网络且有限额；
   • 隧穿 Project 从头到尾可完成；
   • 另外三个 Project 可展示和启动；
   • 教师可查看误区和完整 Trace；
   • 关键流程有 E2E；
   • 所有数据库迁移可执行；
   • README 可让新机器部署；
   • 评测报告随 Release 保存；
   • 演示账号和演示数据可自动生成；
   • 所有已知严重安全问题关闭；
   • 无伪造引用；
   • 无把 inconclusive 描述为已验证；
   • 无自动替学生提交作业。




                                   45
27. 给编程助手的执行指令
本 PRD 是项目的权威产品规范。


编程助手必须遵循以下执行规则：


   1. 首先将本文件保存为 docs/PRD.md 。

   2. 根据本 PRD 创建：


   3. docs/architecture.md


   4. docs/pedagogy.md
   5. docs/security.md
   6. docs/evals.md
   7. docs/tasks.md

   8. docs/tasks.md 必须按 Phase 和可验证任务拆分，每项带：


   9. 依赖；


  10. 涉及文件；
  11. 测试；
  12. 验收标准；
  13. 完成状态。
  14. 先实现最小垂直闭环，不先搭建多代理系统。
  15. 所有 LLM 输出必须经过 Pydantic 校验。
  16. 所有教学政策必须由代码执行，不能只依赖 Prompt。

  17. 所有科学结论必须区分：


  18. 课程引用；


  19. 工具验证；
  20. 数值支持；
  21. 模型推断。
  22. 不得使用真实 API 作为单元测试依赖。

  23. 每完成一个 Phase：


  24. 运行 lint；


  25. 运行类型检查；
  26. 运行单元测试；
  27. 运行集成测试；
  28. 更新任务状态；
  29. 更新变更日志；
  30. 创建 Git commit。
  31. 不得擅自扩大 MVP 范围。
  32. 遇到不明确的非关键实现细节时，采用最简单、可测试、可替换的实现。
  33. 遇到安全、权限、答案泄漏或数据隔离问题时，安全优先于功能。



                                 46
 34. 不允许用 Mock 界面假装后端功能已经完成。
 35. 演示图表必须来自真实运行数据。

 36. 最终交付必须包含：


 37. 完整源码；


 38. Docker 部署；
 39. 数据库迁移；
 40. Seed 数据；
 41. 自动测试；
 42. 评测集；
 43. 演示脚本；
 44. 架构说明；
 45. 安全说明；
 46. 操作手册。

项目的核心验收问题不是：


      “它能回答多少量子物理问题？”


而是：


      “它能否在教师控制下，以可验证、可追踪、不过早泄漏答案的方式，帮助学生完成一次真实的
      概念—推导—模拟—解释学习闭环？”




                               47

