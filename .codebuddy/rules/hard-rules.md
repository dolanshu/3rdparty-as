# 项目硬规则（自动注入，始终生效）

本文件只是索引和红线摘要。完整协作守则的**唯一权威**是仓库根目录的 `AGENT.md`。

> 本文件仅供 CodeBuddy 读取，与 `.trae/rules/hard-rules.md`（Trae 读取）**刻意不要求内容一致** —— 两个 IDE 的派发机制不同，规则按 IDE 分化。共享的、IDE 中立的规则以 `AGENT.md` 为准。

## 开场仪式（任何任务动手前必须执行，见 AGENT.md §10.4）
1. 完整读 `AGENT.md`
2. 读 `docs/README.md`
3. 读 `docs/plan.md` 当前里程碑章节
4. 读 `docs/acceptance/criteria.md` 对应验收项
5. 确认当前分支（由维护者命名或批准）

## Subagent 协作（AGENT.md §10.1，无例外）
- **接任务时判定**：本次任务会产生文件改动 → 在动手之前先派 writing member。主 agent 绝不直接写文件。
- **派 writable member = `Task` 工具传 `name` + `mode = "acceptEdits"`（team mode）。** 不传 `name` 的同步 subagent 是只读的，永远不能用来做文件改动。
- **CodeBuddy 里不存在 `general-purpose` / `Explore` subagent**（那是 Trae 的 `Agent` 工具用的词汇），按名字调用会报 not found；此时改用 team mode，**不要**退回主 agent 自己写。
- team mode 也不可用时 → **停下来报告维护者**，等待显式批准；禁止自行直接写。
- 探索、调研、代码搜索用同步只读 subagent（`code-explorer`）。
- 一个工作树同时只允许一个 writing member；上一个关闭后再开下一个。
- writing member 完成后，主 agent 必须用 `git status` / `git diff` 核对实际改动，与其自述报告比对（trust but verify）。
- spawn prompt 必须自包含，把所有硬约束写进去（如"不许运行 git commit"），不依赖后续消息（AGENT.md §10.3）。
- 每个 turn 结束前自检："我这一 turn 有没有直接写过文件？" 有 → 立即停止并报告维护者。

## Git 红线（AGENT.md §11）
- 绝不 `git push` / force-push、绝不 `git tag`、agent 不创建分支。
- commit 的切分与执行由维护者决定；未经逐次显式批准不得 commit，任何东西不得进 `main` / `master`。
- 不跳过 hook（`--no-verify` 禁止）；绝不提交密钥、证书或真实抓包。

## 门禁（AGENT.md §9）
- 改动完成必须跑 `make gate` 并全绿（M0 阶段只跑 unit/contract 层）。
- 本地门禁不绿，什么都不能提交；绝不要把本地重跑冒充成 CI 结果。
