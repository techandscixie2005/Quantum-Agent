# 自编有限矩形势垒课程

这是真实 PDF 与摄取清单，供开发验收使用，不是正式教材，也不代表任课教师审核。
`lecture.html` 是 PDF 的可读原稿；`manifest.toml` 固定 PDF SHA256。
`reviews.json` 仅约束这份自编材料和有限电子矩形势垒合同，不批准其他课程。

从仓库根目录使用现有私有配置启动：

```bash
docker compose -f compose.yaml -f content/barrier_demo/compose.example.yaml up -d --build
# 将容器名设为本部署的 API 容器；默认示例值来自隔离验收环境。
QA_DEMO_API_CONTAINER=<api-container> bash scripts/video-parity/prepare-demo.sh ingest
```

核对 PDF、哈希、适用范围和开发审核说明后，分别执行同一脚本的
`publish-self-authored`、`authorize-demo-student`。这些命令仅摄取/发布指定文件并准备课程授权，
不写入学生作答、学习阶段或成功证据。正式课程仍须走其原有审核发布流程。

发布后正常登录，选择该课程/版本，在 `/agent` 新建记录并加载任务。
不要将测试驱动中的学生输入植入产品。运行与验收说明见
[DEFENSE_RUNBOOK](../../docs/implementation/DEFENSE_RUNBOOK.md)。
