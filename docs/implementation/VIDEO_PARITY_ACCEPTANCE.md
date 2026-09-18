# 视频主线验收 — 当前续验 2026-09-18

**当前结论：增量实现、真实改参和历史恢复通过；全新真实主线未通过，暂停于教师复核。** 以下本节优先于后面的历史记录。没有提交或推送；原参考目录、视频、PPT及用户未提交工作保留。

## 本轮实际修改

- `AgentExperience.tsx`：完成后聚焦学习证据，隐藏旧参数/空图/旧回复/输入区；非实验模式继续显示必要的教学解释。未提交承诺时不显示实验面板。失败说明区分附件不可用、检索失败、预算到期及执行失败，保留输入。
- `StageReview.tsx`、`agent.module.css`：持久计算回看采用代码/核验与图表双栏；1366×768 可同时看到主要曲线、T/R 和返回入口。没有改后端阶段。
- `EpisodeEvidence.tsx`：行动记录使用中文标签，明确区分学生原话、模型评价、确定性计算；每项展示实际事件 ID、轮次 ID、时间与 payload，空记录不补示例。
- Python teaching SSE 与 BFF：异常明确发出安全失败终态；不转发异常文本。补齐附件失败代码；带注释的块不能绕过终态校验，失败立即结束。未放宽来源/科学验证规则。
- `video-parity-full.spec.ts` 与 `acceptance.mjs`：独立完整主线入口；必须是全新 episode，按序覆盖承诺、诊断、修正、补桥、计算、重构、Transfer、Solo 错答和正答，并逐项关联同 episode 的持久证据。恢复、课程累计数或单个 PASS 不能算全程通过。
- `health.mjs` / `review.mjs`：有界健康检查及真实持久阶段的两档视觉检查。恢复脚本支持 BASE_URL。没有新增迁移或认证机制。

## 当前运行证据

本次日志：[video-parity-current](artifacts/video-parity-current/README.md)。本次真实主线：[run-1789693390865](artifacts/video-parity-live-20260918/run-1789693390865/outcome.json)。更早的 9 月 18 日 run 目录为既有记录，不视作本次新执行。

|场景|本次真实证据|判断|
|---|---|---|
|新任务/判断|新 episode `e20cc92f-3521-46ea-a81f-863c91f7906d`，首轮 `c46dbbad-e160-45f6-83ca-d24313dfa14d`|没有预填成功过程；commitment_required，约 140.621 s，含 interpret 上游约 120 s 超时与明确降级|
|来源/诊断|第二轮 `224f6cbb-3db4-43d5-afe8-2bc925f50e49` 的真实 SSE|检索自编讲义成功、模型针对 E<V0→ψ=0 的输入诊断约 8.13 s；教学输出 citation_contract 警告触发复核，不能说诊断后主线已释放|
|生成/计算|同轮 capability events 记录 generate_coding_artifact 约 7.40 s；独立工具 T=.3336822872167467，参考 T=.3336822872167468|确实调用模型及计算；暂停响应没有释放代码产物，不能当本轮 Code 工作区验收成功|
|真实来源弹窗|旧已完成 episode 的当前授权回看，PDF 200、411629 bytes，两档截图|真实已发布的“自编演示讲义”，明确不是正式教材；Escape 关闭、原件可获取；无正式课程自动批准|
|真实改参|episode `e44d4db1-fa07-4ed1-91b7-f2c7d5bf8392` 的本次新增三个 turn；[参数结果](artifacts/video-parity-live-20260918/run-1789693722326/outcome.json)|3.7/9.2/.137、6.1/11.3/.213、4.8/13.7/.287 均 PASS；任务 hash 不同，图/Data/数值同步，独立参考匹配，code_artifact=null；固定求解器，不调用 Coding Agent|
|历史工作台|[两档逐阶段截图与计时](artifacts/video-parity-current/review-1789693721136/result.json)|当前构建从真实 DB 回看来源、桥、计算、Teach-Back、Transfer、Solo、学习证据；均无横向溢出，返回按钮在屏内；这是历史记录回看，不是本次重新完成这些任务|
|重复提交|[并发重发恢复](artifacts/video-parity-live-20260918/recovery-1789693778823/result.json)|旧完成 episode 原请求同时重发两次，同一 turn，29 条证据 ID 不变，刷新恢复约 892 ms；没有新增模型调用|
|新完整主线|`live-full.log` 真实 Playwright 失败|`pre_release_review / verifier_model_disagreement`，interrupt `85fef6b8-daab-57ba-8474-b6ba0c5d2ae7`；没有跳过阶段或批准输出|

正常私有配置经 `/api/auth/login` 登录 200，2305 ms；凭据在仓库外 0600 session 文件。当前独立预算 30 请求、600 秒、2048 输出 tokens，旧账本未覆盖，本次不补额。当前真实重算约 959/3519/10055 ms，包含系统负载；不是模型耗时。完整冷启动、本次成功打开 Code 产物及全链恢复耗时未测成，不用配置超时冒充性能。

## 质量门

|命令|本次结果|
|---|---|
|聚焦 pytest：teaching_api、golden_loop_phase_sequence、video_barrier_reference、barrier_trend|65 passed；语义模型为明确 mock，科学算法实际运行|
|全量 `pytest -q`|439 passed、2 skipped、1 failed / 548.78 s；失败为既有符号计算 SYMBOLIC_TIMEOUT|
|原限制复跑 tutor_graph + scientific_tools|41 passed / 39.61 s；未删断言/延长业务超时，首次全量失败保留|
|`npm test`|Node 单测、构建和 rendered HTML 通过，见 npm-test-latest.log；末次视觉调整另 build-delivery.log + rendered-delivery.log|
|`npx tsc --noEmit` / Ruff / 相关 Python mypy|通过；mypy 覆盖 teaching API 及其测试，不声称全仓 mypy|
|`npm run lint`|0 errors、11 warnings|
|Golden Loop + Learning Native Playwright|最终 9 passed / 22.7 s，第一方 API 为 mock；包含两档完成提示在屏内|
|`npm run check:secrets`|通过，最终构建检查见 secrets-delivery.log|
|真实 `video-parity-full.spec.ts`|失败，如上；测试绝不把历史恢复当新全程通过|

## 重启与最终复核

隔离 API 重启到 ready **13988 ms**（restart.json，非完整冷启动）；旧完成过程恢复 **915 ms**，仍为原 turn 和 29 条证据（recovery-1789693955292）；本次新暂停恢复 **879 ms**，仍是 attempt_received + 等待复核，不出现完成标记（paused-after-restart.json/png）。最终 Node **79 passed**，新增失败终态测试 **3 passed**；TS、Ruff、相关 mypy、最终构建/HTML/secret 检查通过。diff --check 无问题。

本轮账本实际使用 **4/30 请求**，时间已到期；剩余 26 次不能越过期限使用，没有补额。正式课程没有发布/批准变动。

## 当前阻塞与边界

1. 新 episode 的引用合同失败触发既有教师复核；只有课程 staff 能处理，学生不能自批。暂停前已检索到自编讲义，**不是**上一轮的“缺少来源审核”。需教师核对本轮引用/解释后，通过现有复核入口处理；再次完整验收仍应从新 episode 开始并明确调用预算。
2. 本次没有新的完整 Teach-Back/Transfer/Solo 真实评价、多种语义输入的真实模型验收或全程原始成功录像。脚本保留了真实失败片段 webm，不能包装为成功演示。
3. 独立 Sandbox 的既有历史产物本次能够恢复显示；新生成调用虽有事件，但由于教学复核暂停，未完成新产物可见验收。新 Solo 提交前的 UI/API 锁本次依靠后端和浏览器合同回归，不能替代新全链真实验收。
4. 已有正式课程审核要求保持原样；当前可演示课程是明确标识的自编演示讲义。一次任务评价不代表长期掌握。

---

以下为保留的历史验收记录，结果和端口按其日期理解。

# 视频主线验收记录 — 2026-09-17

**结论：增量实现与回归通过；真实全链路未通过。** 真实流程到达课程依据不足的持久化复核暂停，没有生成成功收尾或录像。不能把下列 mock 回归当作真实模型闭环。

## 本轮修改

- `AgentExperience.tsx`：真实 `/agent` 加载有限矩形势垒题目与初始参数，不提交学生答案；保留已有认证与 BFF。参数改变/请求运行时隐藏过期图、代码核验和科学结果，宽度步长 0.001 nm。恢复计算参数；恢复失败可见并可重试。来源弹窗增加真实检索片段，保留版本、定位、原件授权入口。
- `LearningJourney.tsx`：九项教学展示语义；完成信息取后端状态及实际来源/推导桥，不修改 TutorGraph。
- `CodingArtifactPanel.tsx`、`AgentCodeEditor.tsx`：后端执行产物的只读代码、可选 Monaco、耗时、退出码、截断标识、标准输出/错误；明确代码注释与解释不在数值认证范围内。
- `agent.module.css`：工作区从 880 扩至 1440 px 上限，暖白/绿色课程卡与来源片段；小屏进度条压缩间距。
- `science/barrier_reference.py`、`science/toolbox.py`：四个独立边界连续方程解反射/透射振幅，与解析 T 交叉核验；R 不再用 1−T 作为独立守恒证据。极厚势垒/扫描数值异常返回 INCONCLUSIVE，不伪造曲线零点。
- `teaching/learning_native.py`：明确“不知道/不会/不确定”可进入承诺后的基础支架，记录 explicit unknown，空白仍不接受。
- 新增科学测试、课程入口/改参失效浏览器回归、无第一方 API mock 的可复用 live 前缀 smoke。

本轮没有数据库迁移；保留所有原有未提交改动，未提交、推送或发布。

## 测试记录

证据目录：[`artifacts/video-parity-20260917`](artifacts/video-parity-20260917)。Python 使用现有 `.venv/bin/python`，未重装依赖。

|执行命令|结果|证据与边界|
|---|---|---|
|`cd services/api && .venv/bin/python -m pytest -q tests/test_learning_native.py tests/test_golden_loop_phase_sequence.py`|基线 74 passed|修改前基线；模型/仓储测试替身|
|`.venv/bin/python -m pytest -q`|417 passed, 2 skipped，629.60 s|pytest-full.log；既有 live infra/model 默认不启用。全量运行后补充的 5 个科学用例另跑通过|
|`.venv/bin/python -m pytest -q tests/test_scientific_tools.py tests/test_coding_agent.py tests/test_coding_sandbox.py tests/test_barrier_patch.py tests/test_teaching_api.py`|81 passed|backend-focused.log；沙箱单测不是部署沙箱实跑|
|`.venv/bin/python -m pytest -q tests/test_video_barrier_reference.py`|15 passed|physics-final.log；真实本地确定性计算，无模型|
|`.venv/bin/ruff check quantum_agent tests alembic`|通过|ruff.log|
|`.venv/bin/mypy quantum_agent/science/barrier_reference.py quantum_agent/science/toolbox.py quantum_agent/teaching/learning_native.py tests/test_video_barrier_reference.py`|通过|mypy-final.log；非全仓 mypy|
|`npm run test:unit`|72 passed|node.log|
|`node --test tests/rendered-html.test.mjs`|1 passed|rendered-html.log|
|`pytest -q tests/test_learning_native.py -k explicit_unknown`|4 passed|unknown-final.log；验证承诺接纳与未知事实记录，不产生掌握证据|
|`npx tsc --noEmit`|通过|tsc-final.log|
|`npm run lint`|0 errors，12 warnings|lint-final.log；已有参考目录/脚本等警告未删除|
|`npm run build`|通过|build-final.log，现有 Vinext 构建|
|`BASE_URL=http://127.0.0.1:14375 npx playwright test tests/e2e/golden-loop.spec.ts tests/e2e/learning-native.spec.ts --workers=1 --reporter=list`|8 passed|playwright-final.log；明确 mock 第一方 API，只证明 UI 合同|
|`npm run check:secrets`|通过|secrets-final.log|

初次浏览器回归暴露代码内容缺失，补齐展示后通过。一次开发服务器 HMR 发生模块加载异常，改用完整构建的生产服务器重新运行通过。没有删除断言或跳过失败阶段。

## 真正执行的链路

- 当前本地构建 → 14375 前端 → 18000 隔离 FastAPI → 真实会话/模型路由 → PostgreSQL。没有第一方 API 拦截，没有 offline 回退。
- 原私有会话已失效；使用既有私有 runtime 凭据经正常 `/api/auth/login` 登录，约 1.784 s。凭据未进入仓库/截图/日志。
- 本次预算另建持久账本：20 请求、600 s、2048 输出 token、65536 请求字节。没有重置旧账本，也没有因失败补额。余额见 budget-final.log：剩余 14 次，时间已到期；没有补额。真实能力事件见 capability-events.json。
- 新 episode：`7f2d6709-c340-4c38-969a-d0c200c67737`。第一轮 `450fa475-fd4b-4cf7-8990-74a69ef86e15` 已完成，后端阶段为 commitment_required。interpret 模型调用 66.98 s，承诺提案 1.27 s；未提前进行检索、科学求解或下发答案。
- 学生手动式测试驱动提交“E<V0，因此波函数处处为零……”后，第二轮 `efa01dcc-6f1e-4209-9fdb-835d7f636362` 暂停，interrupt `029c2d8b-4c12-50b8-a93c-f4a77dc2fd41`，`pre_release_review / insufficient_coverage`。只有 staff 可处理。见 live-interrupt.json。
- 真实检索 `coverage=not_found`，警告 `source_insufficient:barrier_applicability_review_missing`；另有 `local_hashing_is_lexical`。未将静态讲义冒充真实来源，未审核正式材料。
- 刷新恢复暂停成功，约 2.45 s；隔离 API 重启后再次恢复同一 episode/interrupt，见 recovery-after-restart.json。这是暂停与已完成首轮的恢复，不是后半程产物恢复证明。
- 当前容器直接调用新边界匹配模块得到 T=0.3336822872167468、R=0.6663177127832535。宿主确定性工具扫描 .100/.137/.173/.213/.250 nm 均 PASS，约 1009/253/187/264/249 ms（含当前机器负载与首次导入）；见 calculation-timings.json。

第一次抓 SSE 使用 Playwright `response.text()` 遇到 Network.getResponseBody 错误；后来以真实 UI、授权 state/interrupt API、数据库 turn 行核对。抓流脚本失败不被记为业务失败或业务成功。

## 逐场景验收与剩余项

|场景|本次证据|结论|
|---|---|---|
|材料/判断|live-task、live-commitment；真实新 episode|入口与真实门控通过，未预填学生过程|
|课程依据|live-interrupt.json；not_found|**外部阻塞**：当前课程缺少适用性审核；真实弹窗成功路径未验收|
|诊断/最小帮助/补桥|现有后端与 mock 浏览器回归|本次真实流程被来源门阻断，不能宣称通过|
|代码/独立 Sandbox/Verifier|既有相关单测 + 新独立科学路径|未完成本次真实 Coding Agent + 部署 Sandbox 联跑|
|改参|15 项科学测试 + 三组浏览器失效检查|确定性计算与 UI 失效通过；真实 episode 多次改参产物关联未验收|
|重建/Teach-Back|现有阶段测试通过|真实语义评价多样性未验收|
|Transfer/Solo|既有锁、错误作答、答案脱敏测试通过|本次真实 API 绕过检查及完整 Solo 未执行|
|学习证据|同 episode 的已完成 turn 与待复核 turn；持久暂停恢复|未到完成页，未伪造完整学习证据|
|视觉|1920/1366 真实入口、承诺、暂停截图；无横向溢出|不是逐关键阶段全部验收；来源/代码/曲线/Solo 真实截图尚缺|

**尚未完成的产品要求**：九项目前是进度展示，尚未形成逐历史阶段回看的单 Stage 导航；Solo 仍使用现有明确要求数值的迁移合同，没有实现题目所述独立定性趋势合同；尚无本轮真实来源、后半程模型/计算产物、完整学习证据与原始全程录像。以上不归因于测试通过，也不包装为已经实现。

环境更新曾遇到 Docker 容器 Dead/Created 停滞，最终恢复；原 3000/8000 服务、数据库卷、原片/PPT均保留。当前隔离测试服务的录制预算会到期，禁止以换 run ID 自动绕过限额。完整复验须先补齐真实课程审核来源，再明确启动下一次有界测试。

## 续轮实施与复验（本节优先于上文的剩余项）

证据目录：[`artifacts/video-parity-followup-20260917`](artifacts/video-parity-followup-20260917)。保留上轮日志，不把它们当成本轮执行。参考目录保持只读；本轮重新用 ffmpeg 抽取实际长片关键帧，补看约 26 秒来源及 168/174 秒 Solo，输出 `reference-frames.jpg` 与 `reference-source-solo.jpg`。

新增代码：

- `StageReview.tsx`、`LearningJourney.tsx` 与 state BFF/FastAPI：可点击回看持久化的已完成阶段；返回当前任务不会提交作答。只读取本课程、本学生、本 episode 最近 100 个已完成轮次。非法阶段 400、未完成 409、没有快照 404、Solo 活跃 423。Solo 正在启动但尚无完成快照时，不恢复上一轮已解答快照。
- `teaching/barrier_trend.py`、`tutor/nodes.py`、模型路由：新的 Solo 是定性题；解释分类、原文引用和理由是模型判断，数值参考另行保存。模型失败/超时、部分解释、矛盾、引用不存在、参考不通过均不完成；保留 45 秒评价期限。未扩大数值验证为整段解释的科学证明。旧数值合同仍兼容，改为匹配本题 hash/kind 的 PASS，拒绝把其他参数数字当答案。
- 进行中的过程也可回看已保存学习证据，明确显示尚未完成；Solo 不返回这些记录。
- 按截图修正回看标题、T/R 摘要、折叠技术记录；使用现有代码/图表/推导桥组件。没有另建演示站。

本轮已执行：

|检查|结果与边界|
|---|---|
|基线 learning_native + video_barrier_reference|64 passed|
|最终聚焦回归（趋势、完整阶段、教学 API、物理检查点）|59 passed；数据库、策略与计算真实，语义模型为显式 mock；backend-final.log|
|全量 pytest|**430 passed、2 skipped、2 failed**；失败是 matplotlib sandbox 与 symbolic equivalence 执行超时，原日志 pytest-full.log 保留|
|失败相关组复跑|55 passed / 25.37 s，见 science-sandbox-recheck.log；未放宽期限、删断言或跳过测试。不能把复跑表述成全量首次全绿|
|TypeScript / Ruff / 本次 Python mypy|通过，见对应 final.log|
|npm test|通过：72 Node 单测、构建、1 HTML 检查|
|lint|0 errors、11 warnings；lint-final.log|
|Playwright Golden Loop + Learning Native|8 passed；含新增历史回看、返回任务与 Solo 禁止回看；第一方 API 使用 mock，非真实全链|
|check:secrets|通过|

本轮真实环境证据：

- `make doctor` 的 Docker/uv/node/npm 均可用；18000 API readiness 200（约 0.020 s，重启后约 0.010 s）。这是健康请求时间，不是冷启动时间。
- 过期会话返回 401；通过既有私有配置、正常登录获得授权，1383 ms；未输出密钥、修改认证数据或将会话提交到仓库。
- 真实 `/agent` 入口已截 1920/1366 两档；1366 无横向溢出。`live-workspace-*.png` 是真实授权页面；`mock-review.png` 是明确的 UI 合同截图。
- 隔离 API 重启后，恢复原 episode `7f2d6709-c340-4c38-969a-d0c200c67737`，durable phase=`attempt_received`，仍有真实复核暂停；见 `live-restored-blocker.json/png`。恢复脚本最初用 APIRequestContext 未带上浏览器 secure-cookie 行为，之后使用正常浏览器 fetch 验证成功。该记录的 3054 ms 包含 3 秒截图稳定等待，**不作为真实恢复延迟指标**。
- 实际独立 runner 三组参数 (E,V0,a[nm])=(3.7,9.2,.137)、(6.1,11.3,.213)、(5,10,.25) 均执行成功，与边界匹配参考相符；runner 执行 0.642/0.324/0.257 s，总计时 6.849/0.499/0.383 s（首组含参考冷加载）。`real-sandbox.json` 明确是**复用参数化测试代码**，没有模型生成，也不是学生 episode 的证据。
- 当前既有录制账本返回 `recording deadline or identity rejected`。本轮没有重置或替换它来增加调用；没有声称新趋势评价已实测真实模型。

当前阻塞与未验收：正式课程仍缺少势垒适用性审核，现有审核合同还只覆盖 E=5/V0=10、a=.10/.15 nm，不能替非预设参数自动背书；需要教师按真实文档/版本/原件/适用范围补齐审核，并配置一次明确的新有界模型验收。来源弹窗成功路径、完整真实 Coding Agent/Teach-Back/Solo、新 episode 全链恢复、各阶段真实视觉验收和未剪辑原片仍未通过。完整当前任务区域的逐阶段聚焦布局也还需在有真实来源的后半程中验证，现阶段只验证了历史回看单 Stage。没有将这些缺项写成完成。

最终复验：最新构建下 8 项浏览器合同测试再次通过（9.1 s），包含中途证据不标记成功。隔离 API 重启至 readiness 实测 6250 ms（非完整冷启动）；刷新到真实复核暂停标题可见实测 1756 ms，无人为稳定等待，见 api-restart.json / recovery-timing.json。仍恢复同一旧 episode；没有把这次恢复当作新完整学习闭环。
