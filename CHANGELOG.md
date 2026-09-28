# 更新日志（Changelog）

本项目的所有重要变更都记录在这里。格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)；
版本遵循 SemVer，`./VERSION` 是产品 release 版本的唯一源头（ADR-0018）。

## [0.1.0] - 未发布（Unreleased）

### 新增（Added）

- 仓库骨架：uv workspace，七个成员，分别位于 `platform/`、`apps/`、`services/`、`testbed/`。
- 结构守卫：依赖方向（`platform/tests/`）、workspace 布局、版本一致性（`tests/`）。
- 四层 CI 门禁：fast → integration → e2e → performance。
- `AGENT.md` —— 产品的协作守则（rules of engagement）。
- ADR 注册表：把 19 项已确认决策映射到 ADR 编号，外加 ADR 模板。
- `docs/plan.md` —— 里程碑计划与未决项注册表。
- `docs/migration/triage.md` —— POC 与库代码的清点、初步分类，以及把关采纳的甄别规则。
- `docs/architecture/新系统整体架构.md` —— 已确认的设计基线。
- feature 能力门控决策：分层开关（部署级总开关 + 运行态细粒度覆盖，ADR-0020），并定义新 feature 的实现流程（`AGENT.md` §3.4）。

### 说明（Notes）

- 还没有产品代码：骨架刻意不含业务逻辑，以便在代码迁入前先评审结构。
- CI ② ③ ④ 三层在首个引入该类测试的里程碑之前不阻塞。见 `docs/plan.md` §2.4。
