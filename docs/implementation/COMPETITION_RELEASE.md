# 竞赛原型结项与发布准备

整理日期：2026-09-21。本次只新增根目录 README 与本文档，保留既有代码和历史证据；这是竞赛原型留档，不是生产稳定版。作者随后授权将文档合入 `main`，并仅清理本地可再生成的缓存；源码、文档与演示材料保留。

## 版本对应关系

| 对象 | 本次核实结果 |
| --- | --- |
| 检查时分支 | `fix/flash-only-live-validation` |
| 检查时完整 HEAD | `fc7f2b0690232ea602e21dcd11ed5a57838b8fbc` |
| 最新适用的历史验收 | [2026-09-18 Flash 验收](VIDEO_PARITY_ACCEPTANCE.md)；对应修复及公开证据收录于上述 HEAD。 |
| 更早的验收材料提交 | 首轮主线：`1daca8ae3ad84ff4fdb0201baa75a726d2cf5df7`；后续失败复核：`3ef5ef916b512a7e11e3b678f5da17324d331862`。仅说明材料收录关系。 |
| 历史运行时的精确源码 / 镜像提交 | **未核实**。已查看的运行 JSON 没有记录 Git SHA；材料与修复一起提交，不能单凭此证明当时运行镜像逐字对应提交。 |
| 检查时远程默认分支 | `main`，HEAD 为 `f3a22ef76e0ac9ace0d9fe2d4693ec8e922c3f75`，为 PR #10 合并提交，父提交之一是上述本地 HEAD；合并提交与本地 HEAD 不能混用版本标识。 |
| 已有标签与 Release | 本地及远程均未见 `competition-final-2026`；已有标签 `pre-competition-ui-flow-hardening-20260830` 解引用至 `ddf2cafe51a973035f66a6ffed5863f6747eb609`。GitHub Release API 返回空列表。 |
| 建议标签 / 最终发布提交 | 建议 `competition-final-2026`；文档合入 `main` 后，以包含本文的实际提交作为候选，最终标签指向仍待人工确定。本文不表示已有 Release。 |

“历史已验收代码”在此指历史报告描述的实现及随修复收录的证据；本次没有重新运行它。工作区原有未跟踪文件保留，未纳入本次交付。没有将旧 CI 结果归给当前工作区或未来发布提交。

## 可用于 GitHub Release 的中文说明

以下正文使用固定材料提交链接，可直接复制；版本字段应在确定发布提交后由 GitHub 标签关联。

---

QuantumAgent 是面向量子物理教学的工作流驱动智能体，结合课程证据、科学工具、代码生成与执行、结果核验和学习记录恢复。由谢翔宇独立开发、单人参赛，作品 **QuantumAgent——面向《量子物理》课程的Learning-Native多智能体教学系统** 获得中国科学技术大学“一〇七杯”算力与智能体开发大赛智能体赛道研究生组二等奖：[官方公示](https://www.teach.ustc.edu.cn/notice/notice-info/20582.html)。

本次留档整理首页与发布说明，保留已有实现及证据。历史真实模型验收主要覆盖自编有限矩形势垒教学主线：生成、执行、独立数值核验、回讲、迁移、Solo 和恢复；不表示本次重新运行测试。参见 [2026-09-18 验收报告](https://github.com/techandscixie2005/Quantum-Agent/blob/fc7f2b0690232ea602e21dcd11ed5a57838b8fbc/docs/implementation/VIDEO_PARITY_ACCEPTANCE.md)、[公开证据目录（含录屏、截图及 JSON）](https://github.com/techandscixie2005/Quantum-Agent/tree/fc7f2b0690232ea602e21dcd11ed5a57838b8fbc/docs/implementation/evidence/video-parity-flash-20260918)。成功与失败记录均保留。

复现请按 [本地环境手册](https://github.com/techandscixie2005/Quantum-Agent/blob/fc7f2b0690232ea602e21dcd11ed5a57838b8fbc/docs/implementation/LOCAL_STACK.md)和 [演示运行手册](https://github.com/techandscixie2005/Quantum-Agent/blob/fc7f2b0690232ea602e21dcd11ed5a57838b8fbc/docs/implementation/DEFENSE_RUNBOOK.md)配置有效模型凭据、基础设施、课程导入 / 发布 / 授权及对应模型配置。

这是竞赛原型留档，不是生产稳定版。阶段开发已完成，暂不扩展功能，不承诺长期在线服务；正式演示前需检查环境与模型服务。现有结果不覆盖整门课程或任意量子问题，不证明生产级多用户能力或长期教学效果；外部服务变化可能影响复现。

---

## 首次文档整理的实际检查

- 阅读适用 AGENTS.md，核对分支、完整 HEAD、工作区、标签和远程 Release 信息；只读查看关键实现、运行手册、配置示例、锁文件及 CI 定义。
- 官方公示可访问，奖项、作品名称和获奖队员一致；独立开发信息由作者提供。
- README 直接引用的 WebM、截图及 JSON 均已跟踪，并通过匿名下载核对与本地文件一致。录屏为 14,645,627 字节，SHA-256 与 `recording.json` 一致；截图已查看。未重新录制或上传本地私有材料。
- 历史数字核对自 [validation.json](evidence/video-parity-flash-20260918/validation.json)：Python 468 passed、2 skipped，两次新主线；不是本次测试结果。
- 文档相对路径存在性、公开材料链接、空白格式、敏感信息与两文件改动范围作静态检查。未读取真实环境文件、认证会话或真实学生数据。
- 未启动服务、调用模型、安装依赖、构建或运行单元 / 全量 / E2E 测试，也未核验当前提交的 CI 结果。`npm run check:secrets` 扫描客户端构建产物，本次不构建、不将旧产物的扫描结果作为新文档验证；仅检查新增文档的敏感内容。

## 合入与后续人工发布

1. 文档合入使用基于远程 `main` 的独立工作区，仅提交 README 与本文档，不覆盖其他工作区。以 Git 提交记录确认合入结果；上表保留首次检查时的 SHA，不充当文档提交 SHA。
2. 在包含文档的 `main` 上选择已审阅的发布提交，记录 `git rev-parse HEAD` 的完整 SHA，确认它包含相应代码、证据和文档。再次用 `git tag --list competition-final-2026` 和 `git ls-remote --tags origin 'refs/tags/competition-final-2026*'` 检查标签；如已存在，核对指向，**不覆盖、不移动**。
3. 仅在标签不存在且最终提交已确定后，人工创建标签：`git tag -a competition-final-2026 <最终完整SHA> -m "QuantumAgent 竞赛原型留档"`。人工按既有流程推送选定分支及该标签，再在 GitHub 基于该标签创建 Release，复制上方正文；不附带私有录制或认证文件。

首次整理只准备本地文件；后续授权包含文档提交与合入 `main`，不包含标签创建、远程 Release 创建或仓库归档。公开展示所需的报告、录屏、截图与 JSON 已有入口；历史运行的精确源码 / 镜像 SHA 对应关系未核实，最终发布提交仍待人工确定。
