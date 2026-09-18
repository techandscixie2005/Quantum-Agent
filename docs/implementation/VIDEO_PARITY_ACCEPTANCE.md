# 视频主线验收 · 2026-09-18

## 最新验收：统一 Flash 后两条全新主线通过

在 `deepseek-v4-flash`、显式非思考模式、结构化生成 temperature=0 的服务端配置下，两次独立的新学习记录均通过严格 live Golden Loop，未拦截第一方 API、未预填产品作答、未恢复旧成功记录代替重跑：

- [第一次主线](evidence/video-parity-flash-20260918/main-run.json)：episode `966ef7e3-71ba-4b72-8c48-ad7a918d137a`，约 2.3 分钟，36/41 个模型请求。
- [第二次独立主线](evidence/video-parity-flash-20260918/repeat-run.json)：episode `f96687cd-ae82-43f9-98c1-4fc5c89c5932`，约 2.2 分钟。
- 两次都验证本轮来源、实际生成代码、隔离执行、独立领域参考、重建/回讲、迁移、新 Solo 的直接 API/SSE/历史重放锁、错误 Solo 不完成、正确 Solo 才完成，以及同一 episode 的持久化证据。
- [真实错误→修正回讲](evidence/video-parity-flash-20260918/teachback-corrections.json)验证历史错误不会永久阻塞已经明确修正的解释，错误本身仍被拒绝。
- [五种真实诊断输入](evidence/video-parity-flash-20260918/diagnostic-inputs.json)覆盖正确、错误、同义改写、部分正确和不知道；不知道返回 insufficient_evidence，未冒充掌握。
- [本轮学习事件](evidence/video-parity-flash-20260918/episode-evidence.json)、[Solo 锁证据](evidence/video-parity-flash-20260918/solo-lock.json)、[恢复记录](evidence/video-parity-flash-20260918/recovery.json)、[双尺寸检查](evidence/video-parity-flash-20260918/visual-review.json)、[未经剪辑录制](evidence/video-parity-flash-20260918/main-raw.webm)及[录制哈希](evidence/video-parity-flash-20260918/recording.json)。时长为固定学生测试输入驱动的操作过程，不是真实学生学习效率承诺。

最终本地 Python 全量 **468 passed、2 skipped**（352.28 秒），Ruff、mypy（142 文件）通过；两项 skip 是既有 opt-in 入口，本轮真实主线另行运行，远程多模态不在本次 P0 范围。历史上下文集成测试保留原断言，并新增当前回答独立评价、有效部分回答再带历史的两段检查。没有删除失败用例或放宽阶段规则。[质量记录](evidence/video-parity-flash-20260918/validation.json)。

[当前模型配置](evidence/video-parity-flash-20260918/model-config.json)与[预算记录](evidence/video-parity-flash-20260918/budgets.json)：第二次使用 35/41 请求；包含失败与语义变体在内本轮合计 142 次，不自动补额。已移除正常服务中的测试预算，保留 Flash 配置。[保留卷的全服务停启](evidence/video-parity-flash-20260918/cold-start.json)约 49.58 秒；完成记录在全服务重启后恢复约 2.46 秒，17 条事件及完整快照不变，两个并发重放不重复写入。不是空机器下载安装耗时。

本轮实际修复：文本模型覆盖包括主备候选与登录探测；请求体显式携带非思考开关；代码修复收到上一版程序及完整安全约束；回讲先评当前观点，仅在当前回答有效但不完整时结合历史再评价。没有改动数值容差、Solo 锁或阶段完成条件，也没有用关键词直接判定理解。

[前置失败记录](evidence/video-parity-flash-20260918/preceding-failures.json)保留切换过程中的诊断超时、错误代码和回讲误判。仅替换模型名称不足以解决全部问题。以下旧复核记录是这些修复之前的历史结果，不能视为当前验收状态。


> **后续复核（同日 20:28 起）：不能把先前成功等同于当前稳定全程可用。** 新 episode `63618708-d5aa-47c5-8a13-cd1bff92d758` 的全新真实重跑在代码生成处失败：上游 timeout，Coding Agent 返回 `INCONCLUSIVE`，没有程序、没有 PASS，也没有进入完成阶段。模型服务恢复后仍需重新执行全新 live 主线。见 [失败记录](evidence/video-parity-recheck-20260918/fresh-run-failed.json) 和 [复核结果](evidence/video-parity-recheck-20260918/recheck.json)。

本次还发现并修复了首屏空计算区把发送按钮挤出视口的问题：有限势垒新任务在收到真实轮次结果前不显示空计算区。两种尺寸的新任务检查均通过（[1366](evidence/video-parity-recheck-20260918/1366-new-task.png)、[1920](evidence/video-parity-recheck-20260918/1920-new-task.png)），未调用模型、未拦截 API。新页面回看原完成 episode 的六个历史阶段、真实 PDF 与两种尺寸检查通过，这是恢复验收，不能当作新的全程验收。

科学/学习状态专项 73 项、Node 82 项、类型检查、lint、生产构建与客户端密钥扫描重新通过。失败 episode 在 API 重启前后均为 awaiting_revision、5 条事件，前后各两次并发重放不重复写入；完整状态一致。一次探测早于 API ready 而失败，ready 后才重做恢复并通过。此次模型预算仅使用 14/41 请求，未用尽预算，也未补额；已移除临时预算，正常服务保留真实失败状态。

下文记录的是此前成功验收的事实与边界。


**有限矩形势垒的全新真实主线已通过。** 本次 episode：`5f7dad0c-29a8-4647-9db7-5082054f6acb`。不是恢复旧成功记录，不拦截第一方 API，不向产品注入自动作答。测试驱动通过真实 UI 提交明确的测试学生输入。

证据：[全程事件与耗时](evidence/video-parity-20260918/main-run.json)、[数据库学习事件](evidence/video-parity-20260918/episode-evidence.json)、[未经剪辑的实际操作视频](evidence/video-parity-20260918/main-raw.webm)、[录制哈希](evidence/video-parity-20260918/recording.json)。视频约 3.1 分钟；不是原有演示 MP4，也不是 60 秒学习效率承诺。

## 逐场景

|场景|实现位置|本次真实验证|
|---|---|---|
|材料与判断|AgentExperience / learning_native / repository|新记录只加载题目与参数；提交预测后进入 attempt_received，未直接完成|
|课程依据|SourcePreview / published retrieval / source_files|本轮真实检索原文与 PDF，文件 411629 字节、版本 1、页码可定位；来源明确为自编演示讲义|
|首错与提示|DiagnosisAgent / policy / hitl|本轮错误对应 physical_interpretation_error；修正单独提交；科学参考 PASS 不再错误否定学生诊断|
|推导补桥|derivation.py / DerivationBridgePanel|真实模型提出当前一步，后端从本轮检索装配原文与来源；标记未获科学验证；按 Assistance Ladder 限制|
|代码与科学计算|coding / sandbox_runner / science|本次生成记录、隔离执行输出、独立领域参考核验；不是计时器点亮状态，也不是旧脚本伪装生成|
|改参|AgentExperience / ScientificToolbox|三组非默认参数均重新计算，旧 PASS 与代码立即失效，Plot/Data/数值和版本一致|
|重建与 Teach-Back|tutor/nodes / learning_native|保存重构、回讲和追问回答，评价使用实际历史上下文；非空提交不直接通过|
|Transfer / Solo|durable phase / solo_visibility / replay gate|先完成有支架迁移，再指派新 E/V/a；提交前 API、SSE、恢复不含答案片段、旧诊断、镜像、代码或参考数值|
|Solo 作答|barrier_trend / independent oracle|错误回答保持 solo_active 且不产生成功事件；正确定性说明后才 complete，解释评价与参考数值分开|
|学习证据与恢复|repository / EpisodeEvidence|15 条本 episode 的真实学习事件；刷新、关闭重开、服务停启恢复逐字段一致；两次并发重放无重复证据|

[来源记录](evidence/video-parity-20260918/source.json)关联 `d90091e5-bdbb-54a1-a94a-83dc26a35a20`，PDF SHA256 为 `530ab542811eb36095fa32121dbaeb0ffadde7c9c3bb785c63a469936fdc125c`。只发布了指定自编材料；未批量审批正式课程。

[Solo 接口记录](evidence/video-parity-20260918/solo-lock.json)：历史回看 423、来源 409；直接帮助与求解请求保持锁态且无答案；旧请求重放以 SSE `workflow.failed / CONVERSATION_CONFLICT` 结束。流已发送 HTTP 头时状态仍为 200，因此检查的是终态和内容，而不是只看 HTTP 状态。

[五种真实输入](evidence/video-parity-20260918/diagnostic-inputs.json)：正确、典型错误、同义改写、部分正确、明确不知道均有不同诊断记录。错误及同义改写定位物理解释错误；其余没有被套用这条错误。此检查携带明确的课程计算合同。另两次未携带合同的尝试被自编材料的适用范围门拦截，未绕过审核释放答案。

[非默认参数结果](evidence/video-parity-20260918/parameters.json)：

|E / V0（eV）|a（nm）|T|独立边界参考 T|
|---|---|---|---|
|3.7 / 9.2|0.137|0.13365196103825366|0.1336519610382537|
|6.1 / 11.3|0.213|0.02704002195970811|0.027040021959708088|
|4.8 / 13.7|0.287|0.0005638426062132884|0.0005638426062132886|

这些是另一个真实计算 episode 的验收，未篡改完整主线的学习证据。确定性重算明确标识固定求解器，不冒充再次生成代码。

## 质量门与异常

本地执行命令：

```bash
npm test
npx tsc --noEmit
npm run lint
npm run check:secrets
BASE_URL=http://127.0.0.1:14384 npx playwright test \
  tests/e2e/golden-loop.spec.ts tests/e2e/learning-native.spec.ts --workers=1 --reporter=list
BASE_URL=http://127.0.0.1:14384 QA_VIDEO_SESSION_FILE=/private/session.json \
  npx playwright test --config playwright.live.config.ts video-parity-full.spec.ts --reporter=list
# services/api 下
.venv/bin/pytest -q
.venv/bin/ruff check quantum_agent tests alembic
.venv/bin/mypy quantum_agent tests
```

- 干净交付源码的 Node 82 项、生产 build、产物/渲染 HTML 检查通过。
- TypeScript、lint、客户端敏感信息扫描通过。干净源码 lint 0 error、5 条既有 warning。
- 浏览器合同测试 10 项通过：这些使用明确 mock，不计作真实服务验收。
- 全新 live Golden Loop 1 项通过：真实模型、PostgreSQL、已发布自编材料、独立 Sandbox 和 Verifier；无第一方 API 返回值 mock。
- Python 最终低负载全量 **455 passed、2 skipped**（4 分 23 秒）；两项跳过为原有 opt-in live 入口，另行执行的真实主线已列出。此前并行负载下有一次符号工具超时，随后专项 29 项和本次全量通过。没有改超时、删除断言或把 INCONCLUSIVE 改为 PASS。Ruff 与 mypy（140 文件）通过。
- 来源权限/未发布/版本冲突、科学五个回归点、守恒但错误的变异代码、非法/退化/极厚势垒、Sandbox 拒绝/超时、错误/不确定 Solo、退出辅助、并发与跨用户边界由后端回归覆盖；这些故障注入是测试，不宣称每项都对远程模型人为制造过。

修复期间真实出现过模型结构失败、引用合同降级、补桥失败与前端合同拒绝；失败记录没有算完成。最终主线不再出现这些阻断。模型超时、限流和预算耗尽仍可能发生，界面会显示失败/降级。SSE 终态、错误、心跳及断流由已有合同测试覆盖；本轮未专门拔断物理网络。

## 视觉与性能

已查看参考抽帧，并复查 1920×1080、1366×768 的实际工作台。暖白/深绿、窄导航、课程标题、横向学习导航、单 Stage、来源弹窗、代码与曲线工作区保留；补桥减少重复标题和长原文占位。未把剪辑字幕或鼠标效果固化到产品。

[并排对照](evidence/video-parity-20260918/comparison.png) · [双尺寸检查记录](evidence/video-parity-20260918/visual-review.json) · [1366 来源弹窗](evidence/video-parity-20260918/1366-source-modal.png) · [1366 计算区](evidence/video-parity-20260918/1366-verify.png) · [Solo 锁态](evidence/video-parity-20260918/main-10-solo.png)。没有横向溢出，回看返回按钮在视口内，弹窗可用 Escape 关闭。原始 PDF 已实际获取；headless 截图不作为内嵌 PDF 阅读器渲染可靠性的证明。

[实测耗时](evidence/video-parity-20260918/timings.json)：

|操作|本次观测|
|---|---|
|已构建镜像、保留数据卷的全服务进程冷启动|42.44 秒；不是空机器下载安装|
|干净生产前端进程启动|1.16 秒|
|打开来源并获取 PDF|72 / 78 毫秒（两尺寸）|
|普通诊断 / 学生修正轮次|14.24 / 46.29 秒，包含模型等待|
|补桥轮次|7.68 秒|
|代码生成模型 / Sandbox|10.83 / 0.252 秒|
|完整计算轮次|12.50 秒，含独立核验；Verifier 未单独埋点，未伪造单项耗时|
|三组确定性参数重算|0.35 / 0.35 / 1.40 秒|
|停启服务后恢复完成记录|2.35 秒，逐字段比较通过|

[停启记录](evidence/video-parity-20260918/cold-start.json)、[恢复前](evidence/video-parity-20260918/completed-recovery-before.json)、[恢复后](evidence/video-parity-20260918/completed-recovery-after.json)。数字是实际单次观测，不是 p95 或测试超时配置。

[预算记录](evidence/video-parity-20260918/budget-summary.json)：每次显式独立账本，不修改或补充旧账本。最终完整主线使用 35/41 个 provider 请求；本次续轮所有修复、失败尝试和变体检查合计 241 次请求。正常服务已移除临时录制预算，不会因验收账本到期永久降级。

## 能力边界

P0 有限电子矩形势垒主线已具备本机真实运行证据；不扩大为任意量子问题或全课程知识图谱。自编讲义有明确适用范围；本机检索包含标识清楚的 lexical/local-hashing 降级，不冒充已验证的远程语义检索质量。语义评价保留模型推断属性，数值 PASS 只覆盖科学合同，一次完成不代表长期掌握。凭据、认证 storageState、完整原始运行目录及旧答辩材料未纳入公开交付。
