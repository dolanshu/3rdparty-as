# 项目硬规则（自动注入，始终生效）

本文件只是索引和红线摘要。完整协作守则的**唯一权威**是仓库根目录的 `AGENT.md`。

## 开场仪式（任何任务动手前必须执行，见 AGENT.md §10.4）
1. 完整读 `AGENT.md`
2. 读 `docs/README.md`
3. 读 `docs/plan.md` 当前里程碑章节
4. 读 `docs/acceptance/criteria.md` 对应验收项
5. 确认当前分支（由维护者命名或批准）

## Subagent 协作（AGENT.md §10.1，无例外）
- **任何文件改动（新建、编辑、删除）必须通过 `Agent` 工具派发 writing subagent（`subagent_type = general-purpose`）执行。主 agent 绝不直接写文件。**
- 探索、调研、代码搜索使用只读 Explore subagent（`subagent_type = Explore`）。
- 一个工作树同时只允许一个 writing subagent。
- writing subagent 完成后，主 agent 必须用 `git status` / `git diff` 核对实际改动，与其自述报告比对（trust but verify）。
- spawn prompt 必须自包含，把所有硬约束写进去（如"不许运行 git commit"），不依赖后续消息（AGENT.md §10.3）。

## Git 红线（AGENT.md §11）
- 绝不 `git push` / force-push、绝不 `git tag`、agent 不创建分支。
- commit 的切分与执行由维护者决定；未经逐次显式批准不得 commit，任何东西不得进 `main` / `master`。
- 不跳过 hook（`--no-verify` 禁止）；绝不提交密钥、证书或真实抓包。

## 门禁（AGENT.md §9）
- 改动完成必须跑 `make gate` 并全绿（M0 阶段只跑 unit/contract 层）。
- 本地门禁不绿，什么都不能提交；绝不要把本地重跑冒充成 CI 结果。
