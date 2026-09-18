# Video parity audit — 2026-09-17

基线：本地分支 `defense/final-case-20260915`，HEAD `1f195cf4`，已有未提交修改全部保留。实际产品为仓库根目录；`defense/full-demo` 只读参考，195.733 秒成片，含预设对话、静态计算和浏览器本地记录，不是产品运行证据。

请求链：`/agent` → AgentExperience → `/api/teaching` BFF → FastAPI teaching → TutorGraph / learning_native / repository → PostgreSQL。科学计算由 science/toolbox 和 coding/agent、独立 sandbox 提供。原始资料经过 knowledge 发布和 source_files 权限校验。禁止接到 offline adapter。

|参考秒/操作|当前 UI / 状态来源|初审差距（源码存在≠验证）|修改/验收位置|
|---|---|---|---|
|0–10 材料/判断|AgentExperience、CommitmentCard / backend gate|缺明确有限势垒任务入口；不应注入学生回答|课程入口；新过程检查|
|20 来源|Radix SourcePreview / evidence_packet、source_files|已有真实来源弹窗；待验证发布/授权/原文件|source tests、live source|
|33 诊断|diagnosis / TutorGraph diagnose|模型诊断已有；输入多样性待实测|teaching tests / live|
|41–53 提示/补桥|policy、derivation_bridge|已有；不能由导航推进后端状态|learning_native tests|
|69–98 代码/验证/曲线|CodingArtifactPanel、AgentPlot / science+coded artifact|确定性工具以构造守恒判 PASS，异常曲线填零；改参可能展示旧图|toolbox、独立边界匹配、回归测试、失效展示|
|110–130 重建/Teach-Back|LearningNativeSurface / durable phase|已有评价和持久化；完整输入覆盖待验证|golden loop|
|147–160 Transfer/Solo|solo + oracle / backend lock|已有锁、退出、评价；趋势题与数值题区分待验证|learning_native、API tests|
|179–191 学习证据/恢复|EpisodeEvidence / PostgreSQL|已有本次事件展示；刷新/重启完整产物待实测|live evidence / restore|

实施顺序：先科学独立核验和异常处理；再课程入口、导航及参数失效；运行现有与新增质量门；通过当前安全入口尝试真实链路，记录阻塞与逐场景证据。前端配色沿用参考暖白/深绿，现有 KaTeX/Plotly/Monaco 和 Radix 弹窗复用，不复制字幕/鼠标/自动作答。

## 本轮实际结果

- 全片按实际分镜抽取 0、10、20、33、41、53、69、75、87、98、110、119、130、147、160、179、191 秒并查看拼图；98 秒单帧核对曲线布局。参考目录未修改。
- 已修改：有限势垒题目入口（仅载题）、九项展示导航、工作区宽度、来源片段、代码/执行输出、改参失效、恢复错误提示、独立边界匹配、明确不知道的承诺处理。
- 当前真实调用抵达 commitment_required；提交承诺后持久化暂停于 `pre_release_review`。原因是 `insufficient_coverage`，检索警告为 `source_insufficient:barrier_applicability_review_missing`，另有 local_hashing 降级提示。
- 没有自动审核/发布课程资料，没有将静态演示讲义作为检索结果，没有把暂停计为已完成。
- 实验/回讲/Solo 后半程只具有现有实现与契约回归证据，本次未完成真实全链路。具体证据和剩余功能差距见 VIDEO_PARITY_ACCEPTANCE.md。

## 续轮审计（2026-09-17）

已重新核对本地路径、Git 状态、参考拼图与教学/科学请求链；沿用当前未提交实现。基线 learning_native + video_barrier_reference：64 passed。优先修复 Solo 任意数字匹配、未关联 PASS 的验收漏洞；补齐趋势合同与独立评价记录，再处理可回看的单 Stage。既有验收结果仅属上一轮，本轮结果另记。

### 续轮修改与边界

|场景|新增实现|验收依据|仍需真实验收|
|---|---|---|---|
|回看已完成阶段|LearningJourney → StageReview → 现有 state API 的 review_stage；按用户/课程/episode 检查，读取最多最近 100 个已完成轮次，不修改阶段|API 回归包含 423 Solo 锁、409 未完成、404 跨课程；浏览器 mock 检查单 Stage 回看及返回|有审核来源的完整历史阶段|
|Solo 趋势|新矩形势垒 Solo 默认 E=4/V0=12、a=.12→.18 nm；已练过同 E/V0 时换 E=3/V0=11；无精确数值要求|真实策略/数据库/数值 + 显式语义 mock 测试|真实模型的正确/错误/部分/未知/同义输入评价|
|Solo 判定|数值合同只接受明确 T 或纯数字，关联当前任务 hash/kind/PASS，拒绝不相关参数数字和冲突数值；趋势评价用学生原文引用，单独记录解释判断和两端参考计算|test_barrier_trend、golden loop phase tests|本次 episode 的真实完整 Solo|
|中途证据|未完成过程可查看已有原始记录；Solo 锁下不返回；不显示虚构的完成总结|原 API 权限与 Solo 回归|完整过程恢复与逐条关联视觉检查|
|独立执行|部署 runner 经 Unix socket 实际运行复用测试代码，三组参数与独立边界匹配相符|real-sandbox.json|Coding Agent 本次真实生成记录|

新增 review 和 trend 均扩展当前合同；没有新状态机、认证或数据库表。新字段为持久 JSON 的兼容默认字段，不需要迁移。原来仅两个宽度的课程适用性审核合同没有放宽，正式资料没有自动批准。当前真实完整主线仍被来源审核阻断。

最终状态：59 项聚焦后端测试、8 项浏览器 mock 合同测试及静态检查通过；真实独立 runner 三组数值通过，真实旧 episode 重启后恢复通过。全量 pytest 的两项执行超时及其 55 项独立复跑均保留在验收记录。课程来源与新的真实模型全链验收仍是未通过项。

## 当前续验（2026-09-18，独立于此前日志）

已确认当前仓库/分支与上述基线一致，参考目录只读；读取 README、分镜、源码并查看长片关键帧拼图。发现 9 月 18 日代码与 artifacts 已超出文档：自编演示课程有独立文件和发布记录，存在完成 episode 和改参记录；最近新流程仍在计算时收到 INVALID_UPSTREAM_CONTRACT。因此旧的“正式课程审核阻塞”不能代表自编课程当前情况，旧完成记录也不能代表最新代码全链通过。

|场景|当前发现|本轮修改/验收|
|---|---|---|
|SSE 失败/恢复|BFF 未接受 Python 的两个附件失败代码；带注释的混合块可能绕过终态校验|补齐有限白名单，终态校验失败即关闭，保留输入并显示具体问题；Node 回归|
|全主线验收|现有 live 驱动可从任意阶段恢复，complete=true 不代表这次覆盖所有场景|新增严格全流程检查入口，恢复与全流程分开报告；绑定 episode 和持久证据|
|当前环境|Docker activating、docker ps 超时；18000 连接拒绝|有界健康检查留证；不重置数据库/账本，不把旧截图算本轮实跑|

实施顺序：修复 SSE 失败合同 → 强化全链验收 → 执行质量门/界面截图 → 更新当前可执行 runbook 与明确未验收项。

### 本轮收尾（当前事实）

- Docker 自启动完成后已恢复真实链路，不再记为阻塞。当前工作台 `14380/agent` → BFF → `18000` Python → PostgreSQL；正常私有凭据登录，无 mock 回退。
- 新主线 episode `e20cc92f-3521-46ea-a81f-863c91f7906d` 真实进入 commitment_required，再因模型引用合同警告进入 `pre_release_review / verifier_model_disagreement`。真实来源与独立计算成功；没有批准暂停或记成主线完成。
- 修复完成页被旧实验面板挤出首屏、非实验模式丢失正文；计算回看改双栏；学习证据增加中文事件标签和 ID/轮次定位。
- 真实三组非预设改参、来源原件 200、两档历史阶段截图、完成请求并发幂等重发、隔离 API 重启恢复均执行。真实新回讲/Solo/成功录像尚未完成。
- 隔离 API 重启到 ready 13988 ms；完成记录恢复 915 ms，当前暂停记录恢复 879 ms。不是完整冷启动测量。
- 79 Node 单测、9 浏览器 mock 用例、65 聚焦后端、Ruff/相关 mypy/TS/lint/build/secret 检查通过。全量 pytest 439 passed/2 skipped/1 symbolic timeout；原限制相关组复跑 41 passed。保留首次失败。
- 本轮模型预算消耗 4/30 个请求，时间已到期，未补额。当前剩余外部条件：课程 staff 处理真实引用复核；下一次完整模型验收须显式配置新有界预算。
