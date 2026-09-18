# 视频主线实施审计

本地产品：`/home/xiangyu_xie/QuantumAgent-final-case`。起点 `cc332f4`，保留本地未推送修改；公开 main 仅作比较。参考目录实际为 `defense/full-demo`，下划线属于用户名，不是 `/home/xiangyu/_xie`。参考目录、原视频和 PPT 未修改。

已读取参考 README、storyboard、UI/录制源码和关键帧。原片约 195.7 秒，因此按实际场景抽取并查看 0、10、20、33、41、53、69、75、87、98、110、119、130、147、160、179、191 秒。未找到用户指定名称的 PPT。参考包含硬编码回答与计算展示，不能作为真实运行证据。

请求链保持为 `/agent` → React/TypeScript BFF `/api/teaching` → Python FastAPI → TutorGraph / policy / published retrieval / science / isolated runner → PostgreSQL → SSE / 恢复接口 → 同一工作台。未迁移框架、认证或单轮 TutorGraph；旧 TypeScript 后端不作为本次业务权威。

|参考操作/秒|现有 UI 与数据来源|审计发现及实际修改|验证入口|
|---|---|---|---|
|0–20 材料与判断|AgentExperience / Commitment Gate / 学生原文|原有真实任务入口保留，不预填过程；降级时明确显示模型帮助未就绪并保留输入|全新 live 第一轮；承诺/未知输入测试|
|20–33 课程依据|SourcePreview / published EvidencePacket / source_files|复用真实弹窗与授权原件；单独准备有文件、哈希、版本、审核范围的“自编演示讲义”，不冒充正式教材|原件 HTTP、字节数、来源截图；权限/发布回归|
|33–53 首错与最小帮助|DiagnosisAgent / ReleasePolicy / HITL|修复参考求解 PASS 被误当“学生解释正确”的冲突；分开模型提议和后端来源标签，仍严格校验最终诊断|specialist_agents、hitl_verification_scope；真实不同输入|
|53–69 推导补桥|DerivationBridgePanel / 当前检索与模型输出|模型只选择本轮来源索引，后端装配原文；非法索引拒绝，帮助级别限制保留。补桥原文折叠，下一步在卡内显示|derivation_bridge；真实起止式请求、截图|
|69–98 代码、核验、曲线|CodingArtifactPanel / CodingAgent → AST → runner → oracle|保留生成/运行/独立核验分工；执行状态依据实际运行和核验，不伪造逐个完成。参数变动使旧结果失效|sandbox/science 回归；三组非预设 live 重算|
|110–130 重建与回讲|LearningNativeSurface / durable phase / 模型关系评价|将先前已保存的完整重构加入后续评价上下文，避免要求重复已经说明的关系；保留追问与失败|golden_loop_phase_sequence；真实回讲与追问|
|147–160 Transfer / Solo|真实指派记录 / backend Solo lock|开始 Solo 即阻断辅助生成；SSE、恢复及幂等重放统一隐藏课程答案、旧诊断/镜像/桥/代码；提交前不返回参考计算。旧答案重放被拒绝|错误/正确作答；直接帮助、求解、重放、来源、状态接口检查|
|179–191 学习证据|EpisodeEvidence / PostgreSQL 本 episode 的事件与产物|复用本次事件，不用掌握率；并发重复请求与进程重启恢复检查同一事件集合|live 完成证据；recovery.mjs|

额外修复：格式错误不再把可用模型线路全局冷却；上游网络故障仍按原规则冷却。日志只新增校验错误类型，不记录回答、提示词或凭据。Solo 语义评价明确其六字段结构，失败仍不产生通过证据。

实施顺序为基线 → 纵向 live 暴露问题 → 小步修复与回归 → 再跑 live → 双尺寸视觉/恢复/质量门 → 交付。没有删除断言、放宽科学判定或把 mock 通过当成真实验收。具体执行结果及剩余边界以 [VIDEO_PARITY_ACCEPTANCE.md](VIDEO_PARITY_ACCEPTANCE.md) 为准。
