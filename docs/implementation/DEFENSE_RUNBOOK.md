# 答辩运行手册

使用真实 `/agent` 工作台。视频参考 `defense/full-demo` 只读，不是产品入口。当前验收服务为 `http://127.0.0.1:14384/agent`，Python API 在 18000；原有 3000/8000 服务和数据卷未覆盖。最终结果见 [验收报告](VIDEO_PARITY_ACCEPTANCE.md)。

最新两次全新主线使用 `deepseek-v4-flash` 显式非思考模式通过。配置见 [Flash 测试配置](../../content/barrier_demo/compose.flash-test.yaml)：将它追加到当前 Compose 文件列表，保留原端口、数据卷和私有环境。正常验收服务已保留该模型配置。代码修复和回讲评价也有对应修复，不能只改模型名称而使用旧业务代码。

所有文本主备路由与登录探测使用同一模型；非文本协议不冒充聊天接口。本案例没有调用远程图像、嵌入或 OCR 模型。模型服务仍可能超时或输出错误，此时保留 FAIL/INCONCLUSIVE，不自动换成演示答案；正式展示前运行健康检查与 live 主线。录屏必须标注为录屏。

## 从干净仓库启动

按 [LOCAL_STACK.md](LOCAL_STACK.md) 配置私有环境；不把密钥写入 Git、浏览器存储或测试产物。

```bash
make doctor
make up
```

默认入口为 3000/8000。单独开发前端可使用：

```bash
npm ci
npm run build
QUANTUM_API_BASE_URL=http://127.0.0.1:18000 npx vinext start --port 14384
BASE_URL=http://127.0.0.1:14384 QUANTUM_API_BASE_URL=http://127.0.0.1:18000 \
  node scripts/video-parity/health.mjs
```

先结束构建再启动。不要在正在服务的 dist 上并行构建。本轮测试的前端从干净源码副本构建，未包含本地未跟踪的旧静态 `/demo` 或离线资源。

## 课程准备

生产课程沿用现有审核发布与授权。自编验收课程见 [材料说明](../../content/barrier_demo/README.md)，使用真实 PDF、版本、哈希和限定的审核范围，明确标注为自编讲义，不代表教师批准正式教材。

新部署可以在根 compose 后附加 `content/barrier_demo/compose.example.yaml`。按说明显式执行 `prepare-demo.sh ingest`，核对文件及审核范围后再执行 `publish-self-authored` 与 `authorize-demo-student`。已准备的课程不要重复初始化；这些命令不创建学生回答或成功证据。

正常登录后选择“量子隧穿工作台 · 自编演示课程 / 有限矩形势垒 · 自编演示讲义 v1”。

## 一次完整操作

1. 新建学习记录，加载课程任务。入口只加载问题和 E=5 eV、V0=10 eV、a=0.10 nm。
2. 发送问题，提交自己的判断、理由或明确“不知道”。空白不算尝试。
3. 打开证据面板和引用，核对原文、文件版本、页码并打开原件。提交自己的修正。
4. 在推导模式填写原式与目标式，请求当前允许的补桥。内容是有来源的模型推断，未自动成为教师结论或科学证明。
5. 进入实验模式提交计算任务。查看本次代码生成、独立 Sandbox 执行与 Verifier；失败不能当作 PASS。
6. 改动参数使旧图、代码和核验失效。使用“确定性参考重算”快速计算；这复用固定求解器，不宣称重新调用 Coding Agent。图表、表格与 T/R 使用同一结果版本。
7. 进入重构卡，写出自己的解释，再完成 Teach-Back 和针对性追问。点击进入或提交非空内容不等于通过。
8. 完成有支架 Transfer 后开始新的 Solo 参数任务。提示、来源和解答入口受后端锁限制；不能通过重放旧请求取得答案。可以显式退出求助，但本次不计无提示完成。
9. Solo 趋势题只要求方向和依据，不暗中要求精确数值。错误或无法评价时仍待完成；提交后才返回允许的评价与参考计算。
10. 完成后查看本 episode 的学习事件、原始作答、诊断、帮助、计算与来源。回看已完成阶段；刷新或重新登录后恢复同一记录。

可以通过旧浏览器标签/外部资料记住已经看过的知识；系统只约束本产品的入口，不声称控制浏览器外行为。

## 验证与恢复

```bash
npm test
npx tsc --noEmit
npm run lint
npm run check:secrets
# services/api 下
uv run pytest -q
uv run ruff check quantum_agent tests alembic
uv run mypy quantum_agent tests
```

live 检查使用正常登录产生的私有 storageState（仓库外、0600），不要录制登录凭据。模型测试使用现有 `RecordingBudget.provision`，每次显式独立账本，上限 41 请求、600 秒、输出 2048 token；不修改旧账本、不自动补额。预算用尽或服务失败就是失败，不能切换演示答案。预算是验收限制，不应遗留在长期正常服务配置中。

```bash
BASE_URL=http://127.0.0.1:14384 QA_VIDEO_SESSION_FILE=/private/session.json \
  npx playwright test --config playwright.live.config.ts video-parity-full.spec.ts
# 不拦截第一方 API。全新过程必须逐项通过，不能以 resume 替代。
```

改参、语义变体、双尺寸回看分别使用 `parameters.mjs`、`diagnostic-inputs.mjs`、`review.mjs`。指定 `QA_VIDEO_RESUME=<episode>` 的恢复检查：

```bash
BASE_URL=http://127.0.0.1:14384 QA_VIDEO_SESSION_FILE=/private/session.json \
  QA_VIDEO_RESUME=<episode> QA_VIDEO_RECOVERY_SNAPSHOT=/private/recovery.json \
  node scripts/video-parity/recovery.mjs
```

可以附加 `QA_VIDEO_REPLAY_REQUEST=<本次最后请求JSON>`，检查两次并发重发。后端重启并 ready 后追加 `QA_VIDEO_COMPARE=1`，比较阶段、事件集合与产物完整快照。不要在模型执行中重启。SSE 已发 HTTP 头后，失败以 `workflow.failed` 表示，HTTP 200 本身不代表成功。

## 回退与能力边界

本轮无数据库迁移。出现回归时使用修复前的代码/镜像重启对应服务，保留持久卷；不要 reset/clean、清空数据库、覆盖私有配置或恢复静态演示答案。新失败的请求保留失败状态，不能修库填成完成。

当前科学范围是同质量、无吸收、两侧零势能的电子有限矩形势垒。独立边界匹配检查生成代码，`R=1−T` 不作为独立正确性证据。参数超出可靠范围时明确拒绝或无法判定。数值 PASS 不认证整段解释；语义评价是有依据的模型判断，可能失败或不确定。一次任务完成不是长期掌握证明。

答辩只使用验收报告明确列出的真实结果；原始录制与失败尝试分开。短视频可以剪辑展示，但不能把录屏包装为正在实时运行。
