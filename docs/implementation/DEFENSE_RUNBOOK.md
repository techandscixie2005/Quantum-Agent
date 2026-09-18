# 当前入口与操作补充 — 2026-09-18

当前增量代码的生产构建入口为 **http://127.0.0.1:14380/agent**，连接真实隔离 API 18000。原 3000/8000 服务保留。完整新主线尚未通过；当前原因是模型引用合同触发教师复核，而不是自编课程来源缺失。下面旧章节为历史记录，当前结论以 [VIDEO_PARITY_ACCEPTANCE.md](VIDEO_PARITY_ACCEPTANCE.md) 顶部为准。

```bash
make doctor
# 常规配置齐全时：make up
# 已有隔离后端的本次前端入口：
npm run build
QUANTUM_API_BASE_URL=http://127.0.0.1:18000 npx vinext start --port 14380
QUANTUM_API_BASE_URL=http://127.0.0.1:18000 BASE_URL=http://127.0.0.1:14380 node scripts/video-parity/health.mjs
```

必须等 build 完成后再启动服务器；不要在验收过程中重建正在使用的 dist。make doctor 只检查命令存在；health.mjs 才检查 Docker daemon、真实 API 和网页，且最多等待 8 秒/项。

正常登录后选择“量子隧穿工作台 · 自编演示课程 / 有限矩形势垒 · 自编演示讲义 v1”，新建学习记录 → 加载课程任务 → 发送 → 提交自己的判断 → 依据实际反馈修正 → 按允许操作补桥/计算 → 重构与回讲 → Transfer → Solo → 学习证据。空白不能通过。出现“等待复核”时保持暂停；不要用旧完成记录替代当前任务。

演示课程已存在时不重复初始化。需要准备独立部署时，确保 lecture PDF/content 只读挂载，按 `scripts/video-parity/prepare-demo.sh` 的 ingest / publish-self-authored / authorize-demo-student 三个限定入口操作，仅涉及固定自编课程。范围固定的审核依据位于 content/barrier_demo/reviews.json，部署需配置该文件路径及真实 SHA256。不得用这份自编材料审核为正式教材背书，不写学生成功记录。

真实验收需要仓库外授权 storageState 和明确的后端调用预算（不把密钥写入命令或日志）：

```bash
BASE_URL=http://127.0.0.1:14380 QA_VIDEO_SESSION_FILE=/private/session.json \
  npx playwright test --config playwright.live.config.ts video-parity-full.spec.ts
# 仅历史视觉回看，绝不声称新全链通过：
BASE_URL=http://127.0.0.1:14380 QA_VIDEO_SESSION_FILE=/private/session.json \
  QA_VIDEO_RESUME=<已有完成episode> node scripts/video-parity/review.mjs
```

完整测试最多 900 秒、无自动重试；模型仍服从后端更短的预算。恢复模式和跳过错误 Solo 的开关不能用于完整验收。本轮预算现已到期（已用 4/30 请求），不自动补额；当前入口仍可恢复历史与运行允许的确定性重算，新的模型任务会明确报额度未就绪。下一次模型验收须由运行者明确配置新的有界预算。证据目录中的 compose.budget.json 是一次性预算引用，不能直接拿来当长期服务配置。

当前真实阻塞 episode：`e20cc92f-3521-46ea-a81f-863c91f7906d`；教师需核对 `85fef6b8-daab-57ba-8474-b6ba0c5d2ae7` 复核记录中的引用问题，使用既有 staff 入口。没有为学生提升权限或自动通过复核。

回退只停止本轮额外前端，或恢复隔离 API 的既有 Compose 配置；不删除卷，不重置仓库，不覆盖私有环境文件。当前新增字段无表迁移。先前完成 episode 的恢复只是历史回看；本轮失败录屏须标注“未完成，等待复核”。

---

以下保留先前 runbook 供历史部署核对。

# Quantum Agent 答辩操作与恢复

当前交付是实际仓库的增量修改。**真实全流程尚被课程来源审核阻断，不能讲成已经全程通过。** 状态和测试见 [VIDEO_PARITY_ACCEPTANCE.md](VIDEO_PARITY_ACCEPTANCE.md)。`defense/full-demo` 是只读的旧静态录屏参考，不是运行入口。

## 常规启动

沿用 [LOCAL_STACK.md](LOCAL_STACK.md) 的安全配置：数据库密码、会话保险库、模型与独立 embedding 配置保存在既有私有环境中，不写入前端或提交到 Git。

```bash
make doctor
make up
# http://127.0.0.1:3000/agent
curl --fail http://127.0.0.1:8000/health/ready
```

`make up` 构建当前 Python/React，并执行现有迁移；本轮没有新迁移。保留数据库卷，不运行 `down -v`。课程准备只建立课程、题目、材料和授权；不能写入已通过的学生学习证据。

如只验证新前端，对已经运行的隔离 Python 服务：

```bash
npm run build
QUANTUM_API_BASE_URL=http://127.0.0.1:18000 npx vinext start --port 14375
# http://127.0.0.1:14375/agent
```

本轮实际使用 `quantum-agent-final-demo` 的 18000 API，与原 8000 API/3000 web 分离。隔离 API 通过只读挂载加载当前 `services/api/quantum_agent`。使用过的无密钥 Compose 覆盖保存在验收 artifacts 的 compose.current.json；原环境文件位于仓库外。该覆盖含本次一次性录制预算，不适合作为长期正式服务配置。

## 前置检查

1. `/agent` 经现有 API Key 登录入口建立会话；不要公开发送密钥，不要将会话文件放进仓库。已有 session 失效时用正常登录，不修改认证数据库绕过。
2. 选择真实已授权课程版本。当前实测版本对有限矩形势垒返回 `barrier_applicability_review_missing`：需要教师核对适用文档版本、原件哈希、边界条件和任务覆盖，按现有审核流程处理。不要为了演示批准整批资料。
3. 课程引用必须确实已发布，原件存在且当前学生可访问。只有来源通过后才复验后半程。
4. 检查独立 sandbox-runner 的健康、隔离与资源限制；不可用时 Coding 路径必须失败/INCONCLUSIVE，不改成 API 主进程 exec。
5. 有界真实模型测试使用现有 RecordingBudget，明确一次测试预算、超时和账本。本轮 20 请求/600 秒已经使用，重启不续期、不自动换 ID 补额。

## 操作路线

1. 打开 `/agent`。点击“新建学习记录”创建新的过程入口，保留旧历史。
2. 点击“加载课程任务”：仅加载电子 E=5 eV、V₀=10 eV、完整宽度 a=.10 nm 及问题。点击“发送 / 运行”，等待真实承诺门。
3. 在“认知承诺文本”输入自己的预测、理由或明确“不知道”，提交。不要点击录屏/离线填样例入口。
4. 当前实测会停在“课程依据不足 · 等待教师复核”。此时正常行为是保持暂停，不能自行点完成。教师补齐审核前，不继续声称下面各步已验证。
5. 来源可用后，打开“证据”中的真实引用，核对片段、版本/定位并打开原件；根据诊断补上自己的下一步。
6. 科学计算页设置 E/V₀/a，提交合法任务。Code 与 Sandbox 摘要来自返回产物；核验状态由后端决定。改参会立即撤下旧图/数值/PASS，再提交计算。E≈V₀ 不支持，极厚范围可能返回 INCONCLUSIVE。
7. 完成自己的修订、重建、Teach-Back 与追问；以后端允许动作进入 Transfer、Solo。
8. Solo 活动时不能通过切换模式绕过后端锁；明确退出请求帮助会留下辅助事实。现有题目要求数值时才提交数值；新建的势垒 Solo 采用定性趋势合同，不要求精确数值；模型解释评价与参考计算分别记录，评价不可用时保持锁定。
9. 点击“学习证据”可查看本次已有记录；未完成时明确显示待完成，Solo 期间关闭回看。后端完成后才显示完成状态。刷新恢复同一 episode，不填示例总结。

## 检查与测试

```bash
npm run test:unit
npx tsc --noEmit
npm run lint
npm run build
npm run check:secrets
cd services/api
.venv/bin/python -m pytest -q
.venv/bin/ruff check quantum_agent tests alembic
```

浏览器 mock 合同测试与真实测试分开运行：

```bash
BASE_URL=http://127.0.0.1:14375 npx playwright test \
  tests/e2e/golden-loop.spec.ts tests/e2e/learning-native.spec.ts --workers=1 --reporter=list

# 明确会调用真实服务；先准备授权会话、来源、一次性模型预算。
QA_VIDEO_SESSION_FILE=/private/path/session.json BASE_URL=http://127.0.0.1:14375 \
  npx playwright test --config playwright.live.config.ts video-parity-smoke.spec.ts
```

新增 live smoke 是前缀验收，硬断言真实来源出现；不能把它当完整闭环。完整既有测试仍是 `tests/e2e/live/golden-loop-live.spec.ts` 等，须按该测试现有安全认证与预算要求执行。本轮未跑通其后半程。

## 恢复与回退

- 浏览器只保存会话/课程标识，学习过程在 PostgreSQL；刷新失败显示重试，不冒充新成功记录。
- 本轮验证了 episode `7f2d6709-c340-4c38-969a-d0c200c67737` 的承诺门与人工暂停恢复，包括 API 重启。不是已完成全部学习产物的重启验收。
- 不重置/删除学习数据库。复开演示用新 episode。
- 若只回退本轮隔离服务的源码挂载：以原 `compose.yaml`、`defense/final-case/deployment-20260915/compose.demo.json`、`defense/live-demo-20260915-231336/scripts/compose.patch.json` 及原私有 env 文件，省略 compose.current.json，`up -d --no-build --no-deps api`。这恢复原隔离镜像，数据卷保持。
- 原 3000/8000 服务未被本轮替换；不要 `git reset --hard` 或清理用户未提交修改。

当前诚实可讲：真实授权入口、真实模型承诺门、来源不足时不释放答案、持久化暂停恢复、独立边界匹配的确定性数值与变异拒绝。不可讲：本次已完成真实全链路、已验证真实来源弹窗、已录成完整产品原片、一次成功证明长期掌握。旧 MP4 只能标记为录屏参考。


## 本次续轮操作补充

最新本地前端入口为 `http://127.0.0.1:14376/agent`，后端仍为隔离 18000；启动命令是 `QUANTUM_API_BASE_URL=http://127.0.0.1:18000 npx vinext start --port 14376`（先 `npm run build`）。原 3000/8000 未替换。正常登录后加载课程任务；不得用旧静态视频站替代此入口。

已完成阶段的进度按钮可打开只读回看，用“返回当前任务”继续。回看只请求 state API，不发教学轮次。Solo 时按钮锁住且直接 API 请求返回 423。最新趋势题默认电子 E=4/V0=12、完整宽度 .12→.18 nm；若前题已使用同能量/高度，则改用 E=3/V0=11。回答趋势及因果依据即可，不必填参考数值；评价未通过或不可用不算独立完成。

新的字段在现有 learning_phase_json / evidence_json 中，旧数值任务保留默认 numeric 合同，无表迁移。回退应按本次具体文件补丁进行，不清空数据库、不删除本轮之前的未提交修改。关闭额外前端进程即可回到已有入口；不要复用失效账本继续录制。

实测能力与局限以 VIDEO_PARITY_ACCEPTANCE.md 的“续轮”节为准：新模型语义评价尚无真实调用验收，真实来源门仍阻断全链，不能对外讲成已完成全流程。
