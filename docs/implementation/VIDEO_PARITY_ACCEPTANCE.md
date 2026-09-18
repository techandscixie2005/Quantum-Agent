# 视频主线验收 · 2026-09-18

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
