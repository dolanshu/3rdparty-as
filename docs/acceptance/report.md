# 验收报告（Acceptance Report）— 3rdparty-as

> 里程碑：**M1 —— 甄别与行为基线**
> 日期：2026-09-28
> 执行：AI agent（代办）；维护者签字待补
> 门禁依据：`docs/plan.md` §4.1；DoD 依据：`AGENT.md` §14

## 1. 结论

**M1 门禁达成**。M1 的产出是文档与行为基线，**无产品代码**，故 DoD 中与代码相关的条目按 N/A 标注并说明理由。

## 2. M1 门禁核对

| 门禁项 | 状态 | 证据 |
|---|---|---|
| 每个文件都有一个带证据的裁决 | 达成 | `docs/migration/triage.md` 检索无"未决 / 待裁决 / TBD / pending"残留；`b27bb3d` |
| 冻结 POC commit；抓取消息样例与 trace | 达成（部分） | `testbed/contracts/sip-baseline/` 各场景 README 记录抓取脚本与日期；`92c244c` |
| 基线已抓取且可复现 | 达成（带裁决） | S1 / S2 / S3 / S4 有消息文件（14 / 4 / 4 / 12 条）；S5-S8 裁决为派生基线、S10 / S11 裁决为 M2 probe 补，详见 `plan.md` §4.1 |

> 计数校正：S4-caller-cancel 实际有 **12** 条消息文件（`01-in-invite-trunk.txt` … `12-out-ack-core.txt`，其 README 亦写"消息序列（12 条）"），非 9 条。本报告以仓库实际内容为准。

## 3. DoD 逐项取证（AGENT.md §14）

| # | DoD 条目 | 状态 | 证据 / N/A 理由 |
|---|---|---|---|
| 1 | 对着仿真对等端端到端跑通 | N/A | M1 无产品代码；端到端是 M2/M3 的验收项。M1 只在 POC 侧抓行为基线（S1-S4） |
| 2 | 在改动所属的层补了测试；`make gate` 绿 | 达成 | 本机实跑 `make gate`（2026-09-28）：ruff format `70 files already formatted`；ruff check `All checks passed!`；mypy `Success: no issues found in 7 source files`；pytest `-m "unit or contract"` `44 passed`。现有 44 个测试为 M0 结构守卫与库独立性守卫；M1 未新增产品代码，故无新增测试 |
| 3 | `ruff format`、`ruff check`、`mypy` 干净 | 达成 | 同上（同一轮实跑结果） |
| 4 | 改动带了 ADR；决策有移动时架构文档已更新 | 达成 | ADR-0019（SIP 栈选型）Accepted，其 E1 probe 验证由 `e30c426` 落在 M1；`2341166` 完成 requirement→ADR 双向引用；`b13567a` 将 ADR-0001/0002/0003/0018 标为 accepted |
| 5 | README 与受影响文档已更新 | 达成 | `docs/plan.md` 本次同步更新（M1 完成、当前步骤 M2、新增 §4.1 门禁裁决）；`docs/requirements/README.md` 索引指向 PRD 与 acceptance；PRD 已到 v0.2 |
| 6 | 有 CHANGELOG 条目；若交付内容变化则产品版本号已 bump | 条目待补 / 版本维持 | CHANGELOG 条目由本次同步补写；`VERSION` 维持 `0.1.0` —— M1 无产品代码交付，交付内容未变，按 ADR-0018 不 bump |
| 7 | 若采纳了 POC 代码：已引用对应的 triage 行 | N/A | M1 未采纳任何 POC 代码；POC 行为仅作为基线（`testbed/contracts/`），不进入产品依赖（AGENT.md §12） |
| 8 | 没有提交任何密钥 | 达成 | 本里程碑无凭据、证书或真实抓包入库 |
| 9 | 文档链完整：requirement → ADR → HLD/LLD → 契约/消息样例 → 验收项 → review record | 部分（HLD/LLD 缺） | requirement（PRD v0.2）→ ADR-0019 → 契约/消息样例（S1-S4）→ 验收项（test-plan）→ review record（`prd-v0.1-review.md`）已贯通；**HLD/LLD 尚未创建**，为 M2 的前置项 |
| 10 | 若引入 feature 开关：两态测试与验收证据、移除条件 | N/A | M1 未引入 feature 开关（ADR-0020 机制待 M2 内核落地） |

## 4. 证据清单

| 产物 | 位置 / 提交 |
|---|---|
| POC 文件裁决 | `docs/migration/triage.md`（`b27bb3d`） |
| 行为基线 | `testbed/contracts/sip-baseline/`（`92c244c`） |
| SIP 栈选型 probe | reSIProcate E1 probe（`e30c426`），对应 ADR-0019 |
| requirement→ADR 双向引用 | 各 ADR 头部"回应 REQ"字段（`2341166`） |
| 需求标准 | `docs/requirements/prd.md` v0.2（`c9d4899`） |
| 验收项 | `docs/acceptance/test-plan.md`（`1cb387c` 迁入 acceptance） |
| 评审记录 | `docs/reviews/prd-v0.1-review.md`、`docs/reviews/adr-0019-review.md`、`docs/reviews/adr-m1-draft-review.md` |

## 5. 移交 M2 的事项

| # | 事项 | 去向 |
|---|---|---|
| 1 | 创建 HLD / LLD（`docs/architecture/hld.md`、`lld.md`），含 feature enablement 设计 | M2 首个动作（AGENT.md §3.1 要求 HLD/LLD 是进入 Code 的前置） |
| 2 | S10 / S11 对拍场景补齐（REQ-F-10 非 2xx 分支、REQ-F-11 CANCEL 竞态） | M2 probe 阶段，在 `testbed/` 补 |
| 3 | S5 / S6 / S7a / S8 若后续改为实抓，需在 `plan.md` §4.1 追加推翻记录 | 不得静默替换 |
| 4 | OTel 三信号、数据面拆分（ADR-0005 / 0007）仍为 skeleton，未落地 | M2 内核需要，须先写 ADR |
| 5 | 本报告的维护者签字 | 待补 |

## 6. 签字

| 项 | 值 |
|---|---|
| 里程碑结论 | M1 门禁达成 |
| 未达成项 | 见 §3 第 9 项（HLD/LLD 缺失），已作为 M2 前置列入 §5 |
| 执行人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |

---

## M2a 验收（2026-09-28）

| 项 | 结果 | 证据 |
|---|---|---|
| `make gate` | 全绿 | ruff format 95 files / ruff check passed / mypy 19 files clean / pytest **114 passed**（0 skipped） |
| 结构守卫 | 通过 | 56 passed；内核无反向 import |
| unit 层 | 通过 | `decide()` 判决矩阵 7 例、规则匹配、门控两态、遥测不阻塞、进程壳 draining |
| contract 层 | 通过 | StateStore 契约对 `InMemoryStateStore` 与 `RedisStateStore` 双实现重放（各 9 例） |
| 依赖 | 已接 | `redis>=5.0`（锁 8.1.0）写入 `platform/pyproject.toml` 与 `uv.lock` |
| 文档链 | 贯通 | REQ-F/NF/S → ADR-0005/0007/0016（accepted）→ HLD/LLD（reviewed）→ 契约（test-plan §5）→ 代码 → 评审记录（`m2-design-review.md`、`m2a-kernel-review.md`） |

**未覆盖**：TLS transport / SIP adapter（M2b）、`CallState`（M3）、integration / e2e 层用例（M2b / M3）。

---

## M2b 边界 seam（2026-09-28）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 105 files formatted / ruff check passed / mypy 23 files clean / pytest **145 passed**（2 skipped） |
| 交付 | `platform/src/as_platform/sip/`：对端白名单（fail-closed）、TLS 配置热轮换（不可变重载）、SIP adapter Protocol、判决→状态码映射 |
| 测试 | `test_transport_seam.py` 9 例、`test_sip_adapter_seam.py` 9 例（marker `unit`） |
| 评审 | `docs/reviews/m2b-seam-review.md`（通过） |

**未覆盖**：SIP adapter 的栈绑定实现、证书真实加载与握手、integration / e2e 层用例（均列 M2b 后半）。

---

## M3 决策模块（2026-09-28）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 111 files formatted / ruff check passed / mypy 25 files clean / pytest **169 passed**（2 skipped） |
| 交付 | `apps/translation` 与 `apps/anti-fraud` 的决策模块，均建立在内核 `decide()` 之上 |
| 测试 | translation 10 例、anti-fraud 14 例（marker `unit`），TDD 红→绿 |
| 评审 | `docs/reviews/m3-decision-modules-review.md`（通过） |

**未覆盖**：计数器与 StateStore 的接线（依赖未决 D3）、契约用例集对两用例的重放、`integration` / `e2e` 层。

---

## M3 契约重放与门禁（2026-09-28）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 116 files formatted / ruff check passed / mypy 25 files clean / `unit or contract` **190 passed**（2 skipped） |
| contract 层 | 49 passed（其中 21 个为本次新增的契约重放） |
| integration 层 | 3 passed（首个 integration 用例，真 socket 验证遥测导出不阻塞呼叫路径） |
| 契约用例集 | `testbed/contracts/decision/cases.json` 14 例，对 `apps/translation` 与 `apps/anti-fraud` 各自重放 |
| 评审 | `docs/reviews/m3-gate-review.md`（通过，M3 判为已完成） |

**CI**：层② integration 已改为阻塞（AGENT.md §9）；层③ e2e 与层④ performance 仍无用例，保持 `continue-on-error`。

---

## M4 配置治理内核（2026-09-28）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 127 files formatted / ruff check passed / mypy 28 files clean / `unit or contract` **254 passed**（2 skipped）；integration 3 passed |
| 交付 | 变更单状态机（7 态、审批留痕）、不可变版本库、分批灰度与自动回滚、开关进入 `ConfigBundle` 走同一流水线 |
| 测试 | 状态机 8 条、版本库 6 条、分发 10 条、开关契约 7 条、开关流水线 7 条（marker `unit`），TDD 红→绿 |
| 评审 | `docs/reviews/m4-config-kernel-review.md`（通过，阶段性） |

**未覆盖**：PostgreSQL 版 `VersionStore`、`services/console`（REQ-S-4）、真实数据库端到端闭环。

---

## M4 控制台鉴权与 D7 裁决（2026-09-28）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 134 files formatted / ruff check passed / mypy 30 files clean / `unit or contract` **309 passed**（2 skipped）；integration 3 passed |
| 交付 | `services/console` 鉴权与审计（角色/权限矩阵、双人原则、拒绝也留痕）；ADR-0021 裁决 D7 并实现运行态覆盖（号段 + 稳定哈希百分比，判定幂等） |
| 测试 | console 43 例、运行态覆盖 11 例（marker `unit`），TDD 红→绿 |
| 评审 | `docs/reviews/m4-console-access-review.md`（通过；M4 判为已完成） |

**M4 完成裁决**：治理闭环与开关两态均已落地；PostgreSQL 版 `VersionStore` 转入 M5，**M5 必须补真实数据库的 integration 用例并端到端跑通**，否则 M5 不得判完成。

---

## M5 Helm 与告警（2026-09-28）

| 项 | 结果 |
|---|---|
| 交付 | `deploy/helm/templates/` 9 个模板（按用例遍历 Deployment/Service、ConfigMap/Secret、HPA、PDB、SA、NOTES）；`values.yaml` 扩展；`deploy/alerts/as-alerts.yaml` 8 条规则（两组） |
| 容量约束 | 全仓库无 CPS / 并发绝对值；HPA 阈值与副本上下限为 `null` + `required` 守卫（未填则安装失败）；PDB 无容量默认值；告警只用比例 / 相对量 / 状态量 |
| 安全与连续性 | 凭据占位 + 替换提示；TLS 走客户 PKI Secret 挂载（轮换不重启）；`preStop` draining + 延长终止宽限期；关闭 SA token 自动挂载 |
| 校验 | 纯 YAML 全部 `yaml.safe_load` 通过；模板做了静态配平自查（修掉 2 处：缺 `}}`、range 内 `.Values` 应为 `$`） |
| **已校验** | helm v3.16.2：`helm lint deploy/helm` 0 failed、`helm template as deploy/helm` exit 0；首次渲染暴露并修掉 `_helpers.tpl` 两处左裁剪导致的标签拼接；`--set autoscaling.enabled=true`（HPA 阈值未填）路径按预期失败 |

**M5 未完成的项**：缩容保护的运维接线（每实例 `active_calls` 指标）、PostgreSQL 版 `VersionStore` 接线及其真实数据库 integration 用例（M4 转入）、容量类告警（受 M6 / O1 阻塞）。

---

## M5 PostgreSQL 闭环与指标（2026-09-28）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 146 files formatted / ruff check passed / mypy 34 source files clean / `unit or contract` **331 passed**（2 skipped）；integration **12 passed** |
| PG 实现 | `services/config-service/src/as_config_service/postgres_store.py`：版本**不可变追加**（无 UPDATE / DELETE，回滚靠写回上一版本内容）、**表名白名单**（标识符不经拼接进 SQL）、`psycopg` **惰性 import**（未装驱动也能导入与跑单测） |
| 真实库实跑 | `services/config-service/tests/test_postgres_store_integration.py` 9 条，真连 `127.0.0.1:55432` 的 PostgreSQL 16 容器；跑通治理闭环：审批 → 落库 → 分发 → 自动回滚 → 取回上一版本；`pytest -m integration` 全仓 **12 passed**（9 条 PG + 3 条遥测导出） |
| 指标 seam | `platform/src/as_platform/telemetry/metrics.py`：`MetricsRegistry`（线程安全、不读时钟、不做 IO、快照确定性排序）与 `CallMetrics`（每实例 `as_active_calls`，`as_sip_responses_total` / `as_rule_hits_total` / `as_telemetry_dropped_total`），与 `deploy/alerts/README.md` 指标契约同名；导出走 `BoundedQueueSink`，满则丢弃、不阻塞呼叫路径（ADR-0005） |
| 测试 | `platform/tests/test_metrics.py` 9 条（marker `unit`），TDD 红→绿；含并发累加不丢更新、按实例取回、状态码分类、`capacity=1` sink 不抛不阻塞且 `dropped_count > 0`、纯度（无时钟 / 无 socket） |
| 评审 | `docs/reviews/m5-helm-alerts-review.md`：H11 判为已完成，签字条件改为"真实环境的滚动升级与缩容验证" |

**未完成的项**：真实环境的滚动升级与缩容验证（每实例 `active_calls` 指标已可查询，但尚未在真实集群上验证滚动升级与缩容不掉呼叫）；容量类告警与 HPA 阈值仍受 O1 / M6 阻塞。本模块只定义指标名与语义，**不含任何阈值、目标值或默认值**。
