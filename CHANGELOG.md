# 更新日志（Changelog）

本项目的所有重要变更都记录在这里。格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)；
版本遵循 SemVer，`./VERSION` 是产品 release 版本的唯一源头（ADR-0018）。

## [0.2.0] - 未发布（Unreleased）

### 新增（Added）

- 产品 SIP runtime：`AS_SIP_BIND_ADDRESS` / `AS_SIP_ADVERTISED_ADDRESS` 与 `AS_TLS_*` / `AS_PEER_*` 环境变量接缝（`transport_env.py`）。
- `platform/tests/native_extensions.py`：`AS_REQUIRE_NATIVE_EXTENSIONS=1` 时无 native 扩展则契约测 fail（**GitHub Actions workflow 未更新** — 需 `workflow` scope PAT 方可 push `.github/workflows/ci.yml`）。
- Demo：故事 C M5 对账话术、故事 B 增加 S4/487 步骤、`run-all-automated` PASS/SKIP/FAIL 汇总。

### 变更（Changed）

- REQ-F-10：下游 408/480/486/503/504 透传至上游（`CallController` + native runtime）。
- FORWARD 双腿建立后 native 回传真实 UAC checkpoint 字段；恢复 BYE 使用 checkpoint Contact/route_set。
- `as_load` 支持 `--min-success-rate` / `--max-unresolved` 退出码策略。

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
- M1 行为基线：`testbed/contracts/sip-baseline/` 下 S1 基本呼叫（14 条）、S2 无匹配 404（4 条）、S3 策略拒绝 603（4 条）、S4 主叫放弃 CANCEL（12 条）四条消息样例；S5-S8 裁决为派生基线、S10/S11 转 M2 probe，见 `docs/plan.md` §4.1。
- SIP 栈选型验证：reSIProcate E1 probe 与构建脚本（ADR-0019）。
- requirement → ADR 双向引用：各 ADR 头部加"回应 REQ"字段。
- 需求标准 `docs/requirements/prd.md` v0.2：新增 REQ-S-* 安全需求类、REQ-F-12（规则 CRUD）、REQ-F-14（审批流程），并订正 RFC 3261 章节号。
- M1 验收报告 `docs/acceptance/report.md` 与退出评审记录 `docs/reviews/m1-exit-review.md`。
- M2a 内核（`platform/`）：`decide()` 判决纯函数与规则匹配（最长前缀、block 优先）、`StateStore` seam 及 `InMemoryStateStore` / `RedisStateStore` 双实现、feature 门控 seam（分层、默认关、fail-closed）、有界队列遥测（导出不阻塞呼叫路径）、进程壳与 draining、内部 API 契约模型。
- 依赖：运行时状态存储接入 `redis>=5.0`（ADR-0002 / ADR-0007）。
- 设计与评审：`docs/architecture/hld.md`、`lld.md`；`docs/reviews/m2-design-review.md`、`m2a-kernel-review.md`。
- M2b 边界 seam（`platform/src/as_platform/sip/`）：对端白名单与 TLS 配置热轮换（不可变重载、不重启不丢呼叫）、SIP 适配 seam（仅 Protocol，不含栈实现）、判决到 SIP 状态码映射（603 / 404）。
- M3 决策模块：`apps/translation`（号码翻译，含基线事实 `+8613800138000` → `013800138000` 的断言）与 `apps/anti-fraud`（速率窗口超限判定，`RATE_LIMIT`），均建立在内核 `decide()` 之上，纯函数、TDD。
- M3 契约用例集：`testbed/contracts/decision/`（14 例声明式用例），由 `apps/translation` 与 `apps/anti-fraud` 各自重放（marker `contract`）。
- 首个 `integration` 层用例：`platform/tests/test_telemetry_export_integration.py`（真 socket 验证遥测导出不阻塞呼叫路径）；CI 层② 同步改为阻塞。
- M4 配置治理内核（`services/config-service`）：变更单状态机（审批留痕、非法跳转拒绝）、不可变配置版本库、分批灰度分发与自动回滚。
- 开关走变更流水线：`ConfigBundle` 新增 `ToggleDTO`（含强制的移除条件），与规则同属一个配置版本；开 / 关两态均有测试覆盖。
- M4 控制台鉴权与审计（`services/console`）：角色 / 权限矩阵、提交者不得审批自己的变更、允许与拒绝均留痕、审计记录不可变。
- M4b 控制面工程切片（2026-10-02/03）：持久化鉴权 / 审计集成、控制台实时读取 / 会话、复用 ChangeOrder 提交 / 批准 / 拒绝工作流、同源 ASGI 静态资源 / runtime factory / CLI，以及可选 Helm config-service 接线；仅为工程切片，不代表 REQ/M4b 验收。真实部署 HTTPS / ingress / proxy、无损规则编译、实时 trace、集群通知 / 健康、Helm 渲染与镜像构建仍未验证或待办。
- 新增 owner-only PostgreSQL 设置命令 `as-config-migrate`：通过 store schema API 初始化专用 `as_config` 与 audit schema，仅向预配置 runtime role 授予所需的 config 表/列权限。数据库角色由 DBA 预先创建；owner DSN 仅供手动操作，绝不进入 web Pod。Runtime startup 仍无 DDL。Fake connection focused tests 通过；不声明 Helm render/deployment 或 M4b/M4/REQ acceptance。
- 未决项 D7 裁决（ADR-0021）：运行态覆盖粒度为号段 + 稳定哈希百分比，判定幂等；`gating/overrides.py` 与其测试。
- M5 部署产物：Helm 模板（每用例一 Deployment / Service、ConfigMap / Secret、HPA、PDB、SA、NOTES）与告警规则集（`deploy/alerts/`，8 条，只含比例 / 相对量 / 状态量阈值）。
- 容量数字纪律：HPA 阈值与副本上下限留空并由 `required` 守卫，`deploy/` 全目录不含 CPS 或并发绝对值（O1 待 M6 实测）。
- PostgreSQL 版 `VersionStore`（`services/config-service`）：不可变追加（无 UPDATE / DELETE）、表名白名单、`psycopg` 惰性 import；真实 PostgreSQL 16 容器 integration 用例 9 条（`pytest -m integration` 共 12 passed）。
- 内核指标 seam（`platform/src/as_platform/telemetry/metrics.py`）：`MetricsRegistry` / `CallMetrics`，每实例 `as_active_calls` 及 `as_sip_responses_total` / `as_rule_hits_total` / `as_telemetry_dropped_total`，与 `deploy/alerts/` 的指标契约同名；不含任何阈值或默认值。
- M5 容器镜像：`deploy/docker/Dockerfile`（多阶段 uv 构建，非 root，`python -m as_platform` 入口）与进程入口点 `platform/src/as_platform/__main__.py`；镜像内 SIGTERM 排空实测退出码 0。
- `testbed/probe/`：SIP 栈选型探针（E1 基线对拍、E4 TLS 热轮换）与序列比对器；绑定缺失时以退出码 2 响亮失败。

### 说明（Notes）

- 还没有产品代码：骨架刻意不含业务逻辑，以便在代码迁入前先评审结构。
- CI ② ③ ④ 三层在首个引入该类测试的里程碑之前不阻塞。见 `docs/plan.md` §2.4。
- M1 为文档与基线里程碑，**无产品代码交付**，故 `VERSION` 维持 `0.1.0`，未 bump（ADR-0018）。
- M2a 有产品代码交付，但产品尚未发布，故 `VERSION` 维持 `0.1.0`，全部增量归入未发布段；首次发布时再按 ADR-0018 定版本号。
