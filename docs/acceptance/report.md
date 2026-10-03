# 验收报告（Acceptance Report）— 3rdparty-as

> 里程碑：**M1 —— 甄别与行为基线**
> 日期：2026-09-28
> 执行：AI agent（代办）；M4b 工程切片 + M4b-8 维护者签字已记录（2026-10-04，chat 授权代签）；文首 M1 §6 签字仍为历史项
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

## M4a 配置治理与访问策略证据（2026-09-28；仅后端 / 策略范围）

| 项 | 结果 |
|---|---|
| 门禁 | ruff 134 files formatted / ruff check passed / mypy 30 files clean / `unit or contract` **309 passed**（2 skipped）；integration 3 passed |
| 交付 | `services/console/src/as_console/access.py` 纯访问策略与审计判定（角色/权限矩阵、双人原则、拒绝也留痕；不含 HTTP、login、session、password、persistence 或 UI）；ADR-0021 裁决 D7 并实现运行态覆盖（号段 + 稳定哈希百分比，判定幂等） |
| 测试 | console 43 例（访问策略）、运行态覆盖 11 例（marker `unit`），TDD 红→绿 |
| 评审 | `docs/reviews/m4-console-access-review.md`（通过；M4 判为已完成） |

**历史 M4a 范围裁决（2026-09-28）**：当时的评审将后端治理 / 访问策略范围判为完成；该结论不包含 operator UI，不代表整体 M4 完成。PostgreSQL 版 `VersionStore` 转入 M5；**M5 必须补真实数据库的 integration 用例并端到端跑通**，否则 M5 不得判完成。

### 范围修正（2026-10-01）

本节保留的门禁与测试证据仅覆盖配置治理后端、D7 和纯访问策略代码；原评审没有审查或验收前端。2026-09-28 的整体 M4 完成结论未包含 operator UI，现由用户 2026-10-01 的决定 supersede：M4 整体仍待完成，直到强制 M4b UI 按 REQ-F-12/13/14/15 与 REQ-S-4 的 [`test-plan.md`](test-plan.md) §1.4、§3 验收通过。此处不声明已有 UI 或 UI 验收。

### M4b-1 静态控制台预览（2026-10-01；工程证据，NOT M4/M4b ACCEPTANCE）

本节只记录 M4b-1 工程预览，不构成 UI acceptance；**M4 仍保持开放**。D4 已裁决使用纯 HTML/CSS/JavaScript，不引入 bundler、build tool 或前端 runtime 依赖。预览文件为 [`index.html`](../../services/console/web/index.html)、[`console.css`](../../services/console/web/console.css) 与 [`console.js`](../../services/console/web/console.js)，提供 Rules、Change orders、Call traces、Operations 四个视图；页面标注 `PREVIEW · LOCAL DATA · NOT CONNECTED`，数据只在当前页面内存中。

- **浏览器交互**：浏览器 sandbox 拒绝不可信 `file://`，因此通过 `http://127.0.0.1:8765/` loopback 打开；这是浏览器环境限制，不是应用错误。规则创建、编辑、启用/禁用、删除均只排入本地变更单。名称为空或仅空白时显示 `Enter a rule name.`；匹配值为空或仅空白时显示 `Enter a match value.`；目标为空或仅空白时显示 `Enter target detail.`；无效正则显示 `Enter a valid regular expression.`。无效输入不增加队列，合法正则会排队。拒绝理由为空时拒绝操作被阻止；填写后状态为 `Rejected`，理由可见。预览明确说明批准只影响本地预览，不连接路由后端。
- **双腿呼叫轨迹**：fixture 有 14 条按时间排序的消息，包含两条独立腿的 Call-ID、两腿 INVITE 与 100/180/200 响应、两腿 ACK、入站 BYE、出站 BYE、下游 200 与上游 200。用任一腿的 Call-ID 搜索都返回同一轨迹；每条消息行显示所属腿自己的 Call-ID。
- **响应式与键盘检查**：390px viewport 下四个 view root 与 body 均为 375px。Rules 保留 Match criteria，仅隐藏 version/updated；Change orders 仅隐藏 requested-by/submitted metadata；Call traces 的详情表保留全部七个字段并在内部滚动，页面 root 不溢出。1440px viewport 下各 root 不超过 1440px，Call traces 为 1425px。按 Enter 选择轨迹后焦点回到选中的 Call-ID；筛选掉已选轨迹后焦点留在搜索框；从 Rules 批准、从 Change orders 拒绝后焦点回到当前页标题。拒绝理由校验可用。
- **独立评审**：M4b-1 各工作步骤均经过独立只读评审。评审发现并已修复：批准措辞误导为会影响路由、仅空白匹配值被接受、移动端隐藏 Match criteria、仅空白名称/目标未拦截、键盘操作后焦点丢失、轨迹 fixture 不完整且容易混淆每腿 Call-ID、100 Trying 方向错误。完整 trace fixture 的最后一轮评审无发现；修复后的 focus-only 复核也无发现。详见 [`m4b-1-console-ui-review-2026-10-01.md`](../reviews/m4b-1-console-ui-review-2026-10-01.md)。
- **本地验证**：主 agent 运行 `node --check services/console/web/console.js` 通过。最新本地 `make gate`：ruff format 190 files formatted、Ruff 全通过、mypy 36 source files clean、pytest **417 passed, 2 known skips, 15 deselected**。未运行 CI。

**边界**：当前没有 backend/API、auth/session、persistent audit、database、live telemetry、production routing、persisted trace store 或 workflow connection。该预览不替代 REQ-F-12/13/14/15 与 REQ-S-4 的验收，不代表 M4b 完成，也不改变整体 M4 未完成的状态。

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

---

## M5 容器镜像（2026-09-30）

| 项 | 结果 |
|---|---|
| 镜像 | `docker build -t as-platform:dev -f deploy/docker/Dockerfile .` 成功（191MB，manifest `sha256:3436b8dc84c9…`） |
| 镜像内验证 | `import as_platform` 成功（Python 3.10.21）；入口点 `python -m as_platform --help` 可用 |
| 安全与一致性 | 非 root（`uid=10001`）；`EXPOSE 5060/udp 5061/tcp` 与 Helm 容器端口一致；ENTRYPOINT 与模板不设 command/args 对齐 |
| **ISSU 实测** | 容器内 `docker stop`（SIGTERM）→ 停止接新请求 → 排空 → **退出码 0**，ADR-0009 的 draining 在镜像里真的能工作 |
| Chart 渲染 | 用真实镜像引用渲染出 `image: "as-platform:dev"`，`terminationGracePeriodSeconds: 300` 与 `preStop` 均在 |

**未完成**：真实 Kubernetes 集群上的滚动升级与缩容验证 —— 本机无集群，且 `kind` / `kubectl` 下载因网络超时失败（kubectl 约 56MB 仅下载约 3MB）。该项列为 M5 剩余项，需在具备集群的环境执行。

---

## M2b 探针 harness（2026-09-30）

| 项 | 结果 |
|---|---|
| 交付 | `testbed/probe/`：`e1_baseline_probe.py`（E1 基线对拍，真实 socket）、`tls_hot_rotation_probe.py`（E4 / S12 证书热轮换）、`sequence_compare.py`（纯函数序列比对器）、`tests/test_sequence_compare.py`（10 条 unit）、`README.md` |
| 比对口径 | 方法 / 响应码、`Call-ID`、Request-URI 的 `host:port`、body 逐字节；不比头域顺序 / `Via` branch / SDP `o=` 时间戳（ADR-0019 §5） |
| 绑定缺失时的行为 | **响亮失败，不是 skip**：两个探针实跑均以**退出码 2** 退出，stderr 打印 `No module named 'resip'` 与 `BUILD_PYTHON=ON` 构建指引 |
| 传输 | 字节真的上线路（`_SocketPeer` 用真实 socket，按 RFC 3261 §20.14 的 `Content-Length` 分帧）；缺的是被测栈那一侧的适配器（Protocol 已定义，未实现） |
| 门禁 | ruff format / ruff check / mypy 干净；`pytest -m "unit or contract"` 391 passed（2 skipped）；`pytest -m integration` 12 passed |

**harness 自检**：`testbed/probe/tests/test_e1_probe_selfcheck.py`（marker `integration`，3 条）用假绑定 + 本地回放服务器在真实 socket 上验证三条路径 —— 匹配 → 退出 0；篡改期望 → 退出 1 并指出差异；绑定缺失 → 退出 2。实跑 3 passed。自检证明的是 harness 接好了、比对是活的，**不代表 reSIProcate 复现了基线**。

**当前未验证**：E1（S1–S11）与 E4（TLS 热轮换）**一个都没有跑过** —— 本环境没有 reSIProcate 的 Python 绑定
（`BUILD_PYTHON=ON` 未构建）。harness 落盘不等于证据，ADR-0019 §6 步骤 5 的缺口清单未变。

**K2 约束仍然生效**：probe 通过前，`platform/` 的 SIP 适配层不开工。

**后续项**：E5（状态外置 / 序列化）的探针尚未编写；S5–S11 的基线消息文件仍缺失，对应场景在探针中报 `NO_BASELINE`。

## reSIProcate 原生 DUM 探索性证据（2026-09-30；非验收）

本节仅记录探索性 native smoke 与失败结果，不改变历史 M1/M2 验收结论，不构成产品验收、K2 放行或 K2 发布。

| 检查 | 结果 | 证据边界 |
|---|---|---|
| Native DUM S1 self-loop | 通过，exit 0；INVITE/180/200/ACK/BYE | C++ resip-probe 对 reSIProcate 1.14.0（commit `632e215c2ca9aee5416bfe1808851ea6fa380044`）的原生 smoke；不是产品 E1 |
| Native DUM S4 self-loop | 通过，exit 0；CANCEL/487 | 原生栈 smoke；不是产品 E1 或 REQ 验收 |
| Native TLS S1 | 未建立呼叫；503 Certificate Validation Failure，随后 timeout exit 124 | E4/S12 未通过、未验收；轮换行为仍未验证 |
| Python E1 harness | 显式端口运行后 `import resip` 失败，exit 2 | 不是 pass 或 skip；产品 adapter 不存在 |

上游源码检查确认 reSIProcate 1.14.0 的 `BUILD_PYTHON=ON` 启用 PyCXX-based rePro routing/plugin targets，不提供通用 `resip`/DUM Python 模块。构建产物和日志仅位于 `/tmp/as-resiprocate-userbuild`，不在仓库内。E1/E4 均无产品 acceptance；E5/REQ-NF-1 状态恢复仍未验证。生产栈仍为 ADR-0019 选定的 reSIProcate；本记录不批准代码开工或发布 K2。

## D9-D11 隔离原生探针（2026-10-01；非验收）

以下结果来自 `/tmp` 隔离实验，使用 reSIProcate 1.14.0 commit `632e215c2ca9aee5416bfe1808851ea6fa380044` 与 uv CPython 3.10.21。它们补充可行性证据，不改变任何历史里程碑结论，不是产品 acceptance，不放行 K2，也不代表 M7 已通过。

| 探针 | 观察结果 | 精确证据与边界 |
|---|---|---|
| D9 CPython native callback | C++ extension 在 native caller thread 与 worker thread 调用 Python；顺序、Python exception identity/traceback、refcount 检查通过。 | `/tmp/as-resip-python-bridge-spike/RESULTS.md`。不是 DUM binding；计时不是产品性能指标。 |
| D9 DUM→Python UAS | 真实 UDP INVITE 到达 SipStack+DUM；`onNewSession` GIL-safe 调用现有 `as_platform.decision.decide`，空 RuleSet 回 404；异常路径回 500，进程仍存活。 | `/tmp/as-resip-dum-python-slice/RESULTS.md`。事件循环与 Python caller TID 不同；不是完整 adapter/B2BUA。 |
| D9 两腿失败分支 | `Action.FORWARD` 创建 outbound UAC；downstream 486 经 DUM `onFailure` 回传 inbound UAS；两腿有不同 Call-ID，事务 ACK 完成。 | `/tmp/as-resip-dum-two-leg-spike/RESULTS.md`。一个失败分支，不是完整 E1。 |
| D9 early CANCEL | 隔离重跑完成 `PROBE_B_PASS`：DUM 对上游 CANCEL/INVITE 发送 200/487，controller 触发 `end(DialogSetId)`；下游实际收到 CANCEL 并回复 200/CANCEL、487/INVITE，DUM 发送非 2xx ACK。 | `/tmp/as-resip-dum-final-probes/logs/probe-b-final-isolated.log`。仅一个 early branch；不覆盖 final-response race 或 forking。此前 barrier/同步尝试因 runner 等待 100/180 超时。 |
| D11 SDP body | 两个有效 CRLF offer（143、233 bytes）通过原样转发比较；S1 的 230-byte offer 原样到下游。另有不同的 238-byte answer（SHA-256 `eda2ed79576b309318cfb7580496e751c50094d817ca031e6ae0e8502aad5e9d`）原样返回上游，且与 offer 不同。 | `/tmp/as-resip-dum-sdp-spike/RESULTS.md`、`/tmp/as-resip-dum-sdp-roundtrip/RESULTS.md`、`/tmp/as-resip-dum-final-probes/logs/probe-a-final.log`。Roundtrip 初次 S1 的 230-byte answer 恰与 offer 相同，不能单独证明 distinct answer。有限 corpus，不是完整 adapter/REQ-F-4 acceptance。 |
| D10 UAC restart hook | 两个子进程分别创建 fresh SipStack+DUM；Phase A 退出后，Phase B 用 `DialogSetId`、手工恢复 To-tag/Route/remote target 并递增 CSeq，在同 Call-ID/tags 下发 re-INVITE，收到 200 并 ACK。 | `/tmp/as-resip-dum-process-restart/RESULTS.md`。不恢复旧 `InviteSession` 或 `SipStack` transaction，也未证明产品 `CallController` 映射恢复。当前 baseline 的 INVITE/ACK transaction 已完成，因此该缺口只涉及可选的 mid-transaction extension；探针未测试 RTP/media。 |
| D10 UAS restart | Phase A 建立 UAS dialog 并完成 200/ACK；进程退出后 fresh DUM 收到正确的同 dialog BYE，实际返回 481。源码显示缺少 DUM 私有 dialog-set map 项时返回 481；未找到公开 UAS rehydrate API。 | `/tmp/as-resip-dum-uas-restart/RESULTS.md`。此 481 使当前 ACK-established-dialog BYE/Redis baseline 失败，是 SIP control-state recovery failure，不是 RTP interruption 证据；没有测试 media。此结果不证明自定义 DUM 扩展不可能。 |

**验收结论不变：D10 不通过 / 未解决。** 当前 gate 是 ACK-complete dialog → kill/restart → upstream in-dialog BYE → replacement routes BYE to peer → Redis contains complete dialog record；fresh DUM 对该 BYE 返回 481，因此 SIP dialog/control-state recovery baseline 失败。UAC hook 不等于 UAS 或 CallController 状态恢复。REQ-NF-1 仍是硬要求，M7 acceptance 未通过，K2 未放行。进程崩溃时仍在途的 `SipStack` transaction recovery 未测试，但不属于当前 gate；若要纳入，须单独扩展/修改 requirement 与 test plan 并经维护者裁决。本 D10 检查没有 RTP/media path，也不证明媒体中断。D11 只证明有限输入集合的 native DUM body identity，须扩大到完整产品 adapter、POC 基线及 stack 接受的边界变体后才能评估 REQ-F-4。以上实验未改仓库代码；本次文档更新未重跑 `make gate`，也不声明 CI 结果。

## 工程证据：CallStateCheckpointRepository（2026-10-01；NOT D10 ACCEPTANCE）

本节仅记录工程实现与验证，不改变历史 M1 结论，不构成 D10 验收，也不代表任何 REQ 已接受；ADR-0023 仍为 proposed、未接受。

- 初版 `platform/src/as_platform/state/call_checkpoint.py` 将两条已建立 dialog 腿编码为 schema-v1 确定性 JSON bytes，并存为一个 `StateStore` key/value；TTL 为正整数；命名空间及显式 header allowlist 在 save/load 两侧校验；拒绝 CR、LF、NUL。契约测试 `platform/tests/test_call_state_checkpoint.py`：**14 passed**。这只是序列化/仓储 groundwork。
- 2026-10-01 本地验证：聚焦契约测试 **14 passed**；`make gate` 的 ruff format 报告 188 files formatted、ruff check 全通过、mypy 36 个 source files clean；pytest **406 passed, 2 skipped, 15 deselected**。未运行 CI。
- 手动真实 Redis 7 + redis-py 检查通过：写入单个 key `as:translation:call:redis-checkpoint-test`，服务端 TTL 为正；新建 `RedisStateStore`/repository 读回完全相同的 checkpoint；临时容器已移除。这是手动 integration check，不是已提交测试或 acceptance。
- 该方向是用户选择的 Redis 应用层最小 checkpoint，记录于仍为 proposed 的 ADR-0023。产品 DUM/CallController 集成缺失；无 UAS rehydrate、D10 BYE routing proof、owner fencing/CAS/generation 或 durable-commit/write-before-side-effect 保证。D10 仍因 fresh DUM 481 失败，REQ-NF-1 未满足、K2 blocked；在途 transaction 恢复不属于当前 D10 test-plan。未测试或添加 RTP/media。

## D10 RecoveryTU Loopback Probe：工程证据（2026-10-01；NOT D10 ACCEPTANCE）

本节记录 testbed-only 的可行性证据，不改变上文默认 fresh DUM 对重启后同 dialog BYE 返回 481 的结果，也不改变 D10 不通过/未解决的验收结论。**这不是 D10 acceptance；REQ-NF-1 仍 NOT PASSED，没有任何 REQ 被接受，M7 TODOs 仍开放，K2 blocked。**

- Probe 文件位于 `testbed/simulators/resip-probe/d10-recovery/`：`README.md`、`d10_recovery.cxx`、`orchestrate.py`、`run.sh`。最新 main-agent 命令 `bash testbed/simulators/resip-probe/d10-recovery/run.sh` 最终 `PASS`，runner exit 0；编译/链接 reSIProcate 1.14.0，`ldd` 与 Python syntax checks 通过。Disposable Docker Redis 7.4.11 通过 typed `CallStateCheckpointRepository` save/load 和 TTL checks；checkpoint 已删除，Redis container 已移除。
- Phase A 通过 DUM 建立 UAS 与 outbound UAC 两条腿；fake raw-UDP peer 验证 UAC INVITE/200/ACK。Phase A 在 Phase B 开始前退出。Python 在进程间使用当前 `CallStateCheckpointRepository` 与真实 `RedisStateStore`。
- Phase B 创建 fresh SipStack+DUM 并注册 front `RecoveryTU`：匹配的 BYE 经 checkpoint 路由到 fake peer，peer 返回 200 后上游收到 200；未知 BYE 落回 DUM 并返回 481，未转发。`orchestrate.py` 的 Ruff check/format 通过。
- Workspace 最新本地 `make gate`：ruff format 190 files formatted、ruff check clean、mypy 36 source files clean、pytest **417 passed, 2 known skips, 15 deselected**。这是本地证据，不是 CI。
- 限制：fixture 的 route sets 为空；Phase B 从 temporary native adapter file 接收 typed checkpoint，Redis lookup 在 Python 中、callbacks 之外并跨进程执行，没有测试产品 asynchronous Redis continuation。Probe 的 `RecoveryTU` 是 testbed code，不是产品 adapter 或 `CallController`；没有 fencing/generation、Redis HA/RPO、in-flight transaction recovery、RTP/media 或 graceful transaction-drain proof。Phase A/B shutdown logs 显示 client/server transaction state warnings。默认 fresh DUM 在没有该 `RecoveryTU` 时仍返回 481，因此 probe 仅证明自定义 front TU 能路由这个 loopback fixture。

## M4b-3 变更单日志：工程证据 / NOT M4b/M4 ACCEPTANCE（2026-10-01）

本节只记录 M4b-3 的实现与工程验证，**不是 M4b 或 M4 acceptance**，不改变整体 M4/M4b 未完成的状态，也不声明任何 REQ 已验收。

- **实现**：`services/config-service/src/as_config_service/change_order_store.py` 提供 append-only PostgreSQL 变更单日志；JSON 快照采用严格、版本化格式；head revision 使用 CAS/行锁；使用 deferred head-to-event 外键及阻止 event UPDATE/DELETE 的数据库 trigger；包含按 prefix 安全 guard function。完整合法状态迁移及恰好一次 audit append 会被校验；空白 reject/rollback reason 在纯状态机层拒绝。
- **测试**：`services/config-service/tests/test_change_order_store.py` 最新聚焦运行 **9 passed**。真实 PostgreSQL integration 命令 `AS_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/as_config uv run pytest -q services/config-service/tests/test_postgres_change_order_store_integration.py` 在临时 PostgreSQL **12.22** 上 **6 passed**（两个 integration test functions，六个 parametrized cases），覆盖 append/CAS/history 与数据库约束。PostgreSQL 16 compatibility **尚未验证**，作为非阻塞 follow-up；PG12 结果不代表 PG16 或部署验收。临时 server 仅绑定 loopback，data/logs 位于 `/tmp/as-m4b-postgres`，测试后已停止；未安装系统包、未触碰用户或生产数据库。
- **评审与修复**：独立 reviewer 指出空白 reject/rollback reason 一致性，以及 DB immutability、head FK、skip 与 cleanup 问题；实现修复已应用。最终 reviewer 对不变量未发现实现问题，并建议增加 rollback blank-reason persistence-validator 测试；该测试已加入，另行复审无发现。
- **M4b-3 阶段本地门禁（历史）**：`make gate` 的 Ruff format 报告 197 files；Ruff clean；mypy 38 source files clean；pytest **463 passed, 2 known skips, 21 deselected**。仅为本地结果，未运行 CI；此后 M4b-4 阶段门禁已更新，见下节。
- **范围边界**：本切片仅为 journal 工程基础；没有 HTTP API、ManagedRule persistence、authentication/session、UI integration 或 M4b acceptance。PG12.22 integration pass 不构成 M4b acceptance，也不表示任何 REQ 已接受；PG16 compatibility 仍待验证。整体 M4/M4b 仍开放；M5 仍为部分交付，M6 状态不变；D10/REQ-NF-1 及 PM/AM/UM gaps 保持当前记录状态。

详见 [`m4b-3-change-order-journal-review-2026-10-01.md`](../reviews/m4b-3-change-order-journal-review-2026-10-01.md)：M4b-3 journal slice 在 PG12.22 的已测范围内 conditional pass；维护者签字已记录（2026-10-04）；PG16 compatibility 仍为非阻塞 follow-up；不代表 M4b/M4 完成或 REQ acceptance。

## M4b-4 ManagedRule persistence (2026-10-01; engineering evidence, NOT M4b acceptance)

本节记录 M4b-4 ManagedRule durable-store 的工程实现与验证，不构成 M4b 或 M4 acceptance，也不声明任何 REQ 已验收。整体 M4b/M4 仍未完成。

- **实现**：`services/config-service/src/as_config_service/managed_rule_store.py` 以 append-only PostgreSQL snapshots/tombstones 持久化 ManagedRule；快照为 schema-v1 JSON，revision 更新采用 row lock + CAS。数据库包含 deferred head/event FK、拒绝 event UPDATE/DELETE/TRUNCATE 的 trigger、按 prefix 安全 guard function，以及含 actor/change metadata 的审计记录与有限时间戳检查。
- **聚焦测试**：`test_managed_rule_store.py`（unit）与 `test_postgres_managed_rule_store_integration.py` 合计 **38 passed**。其中只有 integration 文件的 **6 个 parametrized cases** 在临时 PostgreSQL **12.22** 上运行；38 是两文件合计，不是 38 个数据库测试。该 integration 子集覆盖 create/update/delete history 与 tombstone、CAS/duplicate、event UPDATE/DELETE/TRUNCATE 拒绝、deferred FK rollback，以及 PostgreSQL >=12 guard。
- **本地 gate（M4b-4 阶段历史结果）**：`make gate` 为 Ruff format **200 files formatted**、Ruff clean、mypy **39 source files clean**、pytest **506 passed, 2 known skips, 36 deselected**。仅为本地结果，未运行 CI。另有 config-service integration markers 在 PG12.22 上 **30 passed, 145 deselected**；这是较宽的本地补充证据，不是 CI 或 acceptance。
- **环境与兼容性**：临时 PostgreSQL 12.22 由 Ubuntu debs 解包至 `/tmp/as-m4b-postgres`，仅绑定 loopback，测试后已停止；未安装系统包。PostgreSQL 16 compatibility **尚未验证**，列为非阻塞 follow-up。
- **评审**：独立评审提出的 TRUNCATE immutability、Unicode audit metadata 与 PostgreSQL version assertion 问题均已修复；最终 M4b-4 reviewer 无 findings。维护者 signoff 已记录（2026-10-04）。
- **范围边界**：当前实现只覆盖 management-plane persistence；没有 runtime RuleDTO mapping、regex compilation、HTTP API、authentication/session 或 UI workflow。该切片通过只适用于已测试的 PostgreSQL 12.22 范围，不代表 M4b/M4 完成，也不构成 REQ acceptance。

详见 [`m4b-4-managed-rule-store-review-2026-10-01.md`](../reviews/m4b-4-managed-rule-store-review-2026-10-01.md)：结论仅为已测 PostgreSQL 12.22 slice pass；维护者签字已记录（2026-10-04）；PG16 compatibility 仍为非阻塞 follow-up。

## M4b-5-2b ChangeOrder journal write API：工程证据 / NOT M4b/M4 ACCEPTANCE（2026-10-01）

本节记录 M4b-5-2b 的工程实现与验证，**不是 M4b 或 M4 acceptance**，也不代表任何 REQ 已接受。M4b 与 M4 整体仍未完成；UI、真实 authentication/session 与 persistent console audit 均未接通。

- **Routes 与状态变更**：FastAPI 提供 `POST /internal/v1/change-orders` 创建 draft，以及 `POST /internal/v1/change-orders/{change_id}/submit`、`/approve`、`/reject`。所有写入仅 append ChangeOrder journal snapshots。Identity、permission callbacks、timestamp 与 change-ID generation 均由 `create_app` 注入；submit 与 approve 使用独立权限检查，submitter 不能自批，reject 必须提供非空理由。transition 以 journal revision CAS 追加，并包含请求校验与错误映射。
- **安全与一致性边界**：`create_app` 的 auth callbacks 是集成 seam，不是实际 auth provider、login 或 session。该 API 不写 ManagedRuleStore，不应用运行时规则，不分发 ConfigBundle，也不提供 ChangeOrder 与 ManagedRuleStore 间的跨 store atomicity。5-2c 才处理 APPLIED 时两个持久化状态的协调。浏览器/UI 尚未连接，persistent console audit 未实现。
- **聚焦测试**：在 M4b-5-2b 阶段，FastAPI write API focused tests **48 passed**，使用 fake stores；未通过 route 对 PostgreSQL 执行 CAS，也未测试并发 API clients 与 PostgreSQL CAS 的组合行为。独立 reviewer 最终无 findings。测试期间有一条不影响通过结果的 Starlette/httpx deprecation warning。
- **PostgreSQL 与总门禁（M4b-5-2b 阶段历史快照）**：config-service integration markers 在 PostgreSQL **12.22** 上 **30 passed, 216 deselected**，包括 durable stores。该阶段本地 `make gate`：Ruff format **204 files**；Ruff clean；mypy **40 source files clean**；pytest **577 passed, 2 known skips, 36 deselected**，另有一条 warning。均为本地结果，未运行 CI。PostgreSQL 16 compatibility 尚未验证，为非阻塞 follow-up；下方 M4b-5-2c 与 M4b-5-2d2 均为历史阶段证据，6b 阶段门禁快照见下方 M4b-6b section。
- **后续与验收边界（M4b-5-2b 阶段记录）**：当时计划的下一步是 M4b-5-2c：先设计，再以共享 PostgreSQL transaction 协调 active ManagedRule snapshot 与 ChangeOrder `APPLIED` transition；在实现及验证前不宣称跨 store consistency/atomicity。该步骤及其后的 M4b-5-2d1/d2 与 M4b-6a/6b engineering slices 均已交付。当前下一步为 M4b-7 UI integration，之后 M4b-8 browser acceptance（见本报告最新 M4b-6b section 与 `docs/plan.md` 当前状态）。所有 REQ acceptance 均未因此达成。

详见 [`m4b-5-2b-write-api-review-2026-10-01.md`](../reviews/m4b-5-2b-write-api-review-2026-10-01.md)：最终独立评审无 findings；维护者签字已记录（2026-10-04）。

## M4b-5-1 identity/permission-gated read-only API：工程证据 / NOT M4b ACCEPTANCE（2026-10-01）

本节只记录 M4b-5-1 的工程实现与验证，**不是 M4b 或 M4 acceptance**，不声明任何 REQ 已验收。M4b-5 整体仍开放；M4b/M4 均未完成。

- **Routes 与授权**：`services/config-service/src/as_config_service/api.py` 提供从注入的 durable stores 读取的 `GET /internal/v1/managed-rules`、`GET /internal/v1/managed-rules/{rule_id}`、`GET /internal/v1/change-orders` 与 `GET /internal/v1/change-orders/{change_id}`。数据 routes 注入 identity resolver 与 config read authorizer；缺少 identity 返回 401，无读取权限返回 403。Detail miss 返回 404；path IDs 做长度及 control-character 校验。
- **响应与暴露面**：Pydantic 嵌套响应模型显式对应带 schema version 的 ManagedRule / ChangeOrder 序列化记录。Tombstone detail 返回 `rule: null` 与 revision。实际 auth scheme 尚不存在，因此 docs 与 OpenAPI endpoints 均禁用；本切片不提供 login/session/auth provider。
- **聚焦 API 测试**：在 M4b-5-1 阶段，`services/config-service/tests/test_api.py` 有 **28 passed**，覆盖授权成功/拒绝、list/detail、tombstone、404、path 长度与 Unicode control 校验，以及有效的 `@` / hyphen IDs。后续 API suite 已扩展。API `TestClient` 有一条 Starlette deprecation warning，建议使用 httpx2；为非阻塞 tooling follow-up，本 doc-only 切片不增加依赖。
- **数据库与本地门禁证据（M4b-5-1 阶段历史快照）**：config-service integration markers 在临时 PostgreSQL **12.22** 上 **30 passed, 145 deselected**，包括两个 durable stores；PostgreSQL 16 compatibility 仍为非阻塞 follow-up。该阶段本地 `make gate`：Ruff format **203 files formatted**、Ruff clean、mypy **40 source files clean**、pytest **534 passed, 2 known skips, 36 deselected**；另有上述一条 Starlette deprecation warning。以上均为本地结果，**未运行 CI**，PG12 结果不代表 PG16 或部署验收。下方 M4b-5-2c 与 M4b-5-2d2 均为历史阶段证据，M4b-6b 阶段门禁快照见下方对应 section。
- **未实现 / 范围边界**：runtime rule DTO mapping、regex compilation、write routes、change-order submission/approval/rollback API、auth provider/login/session integration、persisted console audit 与 UI connection 均未实现。该 read-only API 不建立 ManagedRule 与 change-order journal 两个 stores 间的原子性；这是 M4b-5-2 的设计与实现工作。M4b-5-1 不构成 M4b/M4 completion 或 REQ acceptance。

详见 [`m4b-5-1-read-api-review-2026-10-01.md`](../reviews/m4b-5-1-read-api-review-2026-10-01.md)：最终独立评审无 findings；维护者 signoff 已记录（2026-10-04）。

## M4b-5-2c APPLIED transaction coordination: engineering evidence / NOT M4b/M4 acceptance (2026-10-01)

This section records the single-PostgreSQL-transaction implementation and verification only. It is **not M4b or M4 acceptance**, does not establish global/distributed atomicity or active-fleet delivery, and does not claim acceptance of any REQ. M4b and M4 remain incomplete.

- **Transaction boundary**: `apply_distributed_change` coordinates typed `CREATE` / `UPDATE` / `DELETE` `ManagedRuleChange` operations with the ChangeOrder `APPLIED` transition using the same psycopg connection. ManagedRuleStore create/append and ChangeOrderStore `append_transition` run with `commit=False`; one commit follows both writes. Errors roll back the transaction. Before reads or writes, the operation verifies exact connection identity and that `psycopg` reports transaction status `IDLE`. The caller must exclusively own that idle connection for the entire call.
- **Integration coverage**: the activation integration file contains seven cases. Coverage includes CREATE, UPDATE, DELETE, the legacy no-proposal path, the different-connection guard, and a stale ChangeOrder revision after a provisional ManagedRule write, verifying rollback of both stores. The latest config-service integration run against PostgreSQL **12.22** was **37 passed, 216 deselected**. PostgreSQL 16 compatibility remains an unverified, nonblocking follow-up.
- **Review and local gate**: the separate activation review found no findings after the idle-connection guard was added; maintainer signoff recorded 2026-10-04. M4b-5-2c stage historical local `make gate`: Ruff format **207 files formatted**, Ruff clean, mypy **41 source files clean**, pytest **577 passed, 2 known skips, 43 deselected**, with one non-failing Starlette warning. Local only; CI was not run.
- **Limits and next step at that stage**: this is one PostgreSQL transaction, not cross-host/failover/distributed atomicity; it does not include delivery to the active fleet. It is not D10 or SIP-runtime proof. M4b-5-2b remains journal-only. At the time of this M4b-5-2c stage, next was M4b-5-2d: connect the actual distribution result to the `APPLIED` API path and expose observed status. M4b-6 was the next step after that 5-2c stage; M4b-6a auth/session and M4b-6b durable audit have since been delivered as engineering slices. The current next step is M4b-7 UI/workflow integration; see the latest M4b-6b section below. No REQ acceptance is claimed.

See [`m4b-5-2c-applied-transaction-review-2026-10-01.md`](../reviews/m4b-5-2c-applied-transaction-review-2026-10-01.md) for the standalone review record and detailed boundaries.

## M4b-5-2d1 PostgreSQL distribution journal（2026-10-02；工程证据，NOT M4b acceptance）

本节记录 durable distribution journal 工程切片与测试证据，**不是 M4b 或 M4 acceptance**，不声明任何 REQ 已接受，也不代表已取得 active-fleet delivery 结果。

- **范围与持久化**：`services/config-service/src/as_config_service/distribution_store.py` 持久化纯 batch-reported outcomes 与 observed status，以 immutable event snapshots 保留历史；通过 deferred head/event consistency triggers、monotonic `+1` head guard 与 prefix CAS 保护 journal 一致性。测试文件为 `services/config-service/tests/test_distribution_store.py` 与 `services/config-service/tests/test_postgres_distribution_store_integration.py`。
- **行为覆盖**：begin、batch progress、completion、自动与显式 rollback、stale/duplicate revision、snapshot immutability、deferred FK、拒绝无 head event、拒绝 head rewind；并发回归使用两条独立连接，在 winner commit 前确定性证明 loser 已处于 lock wait，以覆盖 PostgreSQL READ COMMITTED joined lock-read race。另覆盖 hostile shadow `search_path` 与自定义 schema 写入。
- **数据库与聚焦测试**：Distribution unit suite **51 passed**；Distribution PostgreSQL integration suite **8 passed**。ChangeOrder、ManagedRule、Distribution unit + PostgreSQL integration 与 activation integration 的 config-service 聚焦测试合计 **156 passed**，连接临时 PostgreSQL **12.22**（Ubuntu `12.22-0ubuntu0.20.04.4`），DSN host 为 loopback `127.0.0.1:55432`。此聚焦结果不是 CI；PostgreSQL 16 未测试，为非阻塞 follow-up。
- **M4b-5-2d1 阶段历史本地门禁**：命令 `make gate`。Ruff format：**211 files already formatted**；Ruff 全通过；mypy **42 source files clean**；pytest `-m "unit or contract"`：**636 passed, 2 skipped, 56 deselected**，另有一条不影响通过的 Starlette/httpx deprecation warning。均为本地结果，未运行 CI；后续 M4b-6b 阶段门禁快照见下方对应 section。
- **评审发现与修复**：独立评审发现 ChangeOrder、ManagedRule 与 Distribution 的 head/event 最大 revision 不变量缺口；trigger function 的 `search_path` shadowing；ChangeOrder embedded id 与 relational key 不一致；store SQL 路径可能被 search-path shadowing。修复后，三种 store 均接受经验证的 keyword-only `schema="public"`，SQL fully qualify schema，且不修改连接的 `search_path`。另修复并发 lock-wait/read race 并加入确定性 PostgreSQL 回归测试。最终独立复核数据库 guards、schema qualification 与该并发测试，未发现剩余具体缺陷；维护者签字已记录（2026-10-04），详见[独立评审记录](../reviews/m4b-5-2d1-distribution-journal-review-2026-10-02.md)。
- **边界与下一步**：该 store 只保存报告到的 batch outcome，不发送 AS instance 通知、不证明 fleet delivery、不激活 ManagedRule 或 ChangeOrder，也不构成 global/distributed atomicity。d2 API/report-to-activation wiring 已在下节作为工程证据记录；auth/session、persistent audit、UI workflow 与 browser acceptance 仍开放。M4b/M4 及所有 REQ acceptance 均未完成或声明；PG12.22 结果不代表 PG16 或部署验收。

## M4b-5-2d2 distribution API/report integration（2026-10-02；engineering evidence, NOT M4b acceptance）

本节记录 M4b-5-2d2 route/API workflow 工程切片，**不是 M4b 或 M4 acceptance**，不声明任何 REQ 已接受，也不证明 fleet delivery、AS runtime activation 或真实健康 attestation。

- **Routes 与 workflow**：`POST /internal/v1/change-orders/{change_id}/distribution` 从 `APPROVED` 开始分发，在一个 PostgreSQL transaction 中写入 Distribution begin 与 ChangeOrder `DISTRIBUTING`。`GET /internal/v1/change-orders/{change_id}/distribution` 返回 observed report status。`POST /internal/v1/change-orders/{change_id}/distribution/reports` 接收当前 batch 的 bool reports：部分健康时只提交 Distribution；不健康时在一个 transaction 中记录 Distribution 与 ChangeOrder `ROLLED_BACK`；成功的最后一批先持久化 `COMPLETED`，随后调用现有 `apply_distributed_change`。`POST /internal/v1/change-orders/{change_id}/apply` 仅允许 `COMPLETED`，且可安全重放 actor/revision 精确匹配的既有 `APPLIED` transition；`POST /internal/v1/change-orders/{change_id}/rollback` 仅在进行中的分发允许手动回滚，并在一个 PostgreSQL transaction 中写入两个 snapshots。
- **身份、审计与并发边界**：路由使用注入的 `can_approve_change` permission seam，不是真实 auth provider 或 session integration；persistent console audit 未实现。请求级 primitive lock 串行化同一 app 中共享的注入 PostgreSQL connection；该 connection 必须专用，不得由 app 外部或其他调用共享。idle/pre-existing-transaction guard 与 app cleanup 保证调用边界，但这不是跨进程或跨实例锁。
- **事务边界与报告语义**：Distribution completion 是已提交的 PostgreSQL transaction；随后 ManagedRule 与 ChangeOrder `APPLIED` coordinator 是第二个 PostgreSQL transaction。两者之间没有 global/distributed atomicity。API 只能接收报告，不具备 AS notifier/transport；没有证据证明 AS 已加载某版本，也没有真实 health attestation。因此 batch report 不等于 fleet delivery 或运行态版本验证。
- **Focused verification**：命令 `AS_PG_TEST_DSN='postgresql://postgres@127.0.0.1:55432/as_config' uv run pytest -q services/config-service/tests/test_api.py services/config-service/tests/test_postgres_activation_integration.py services/config-service/tests/test_postgres_distribution_store_integration.py`：**79 passed**，一条既有 Starlette/httpx deprecation warning。完整 config-service integration 命令 `AS_PG_TEST_DSN='postgresql://postgres@127.0.0.1:55432/as_config' uv run pytest -m integration -q services/config-service/tests`：**61 passed, 280 deselected**，同一 warning；使用临时 PostgreSQL **12.22**（Ubuntu `12.22-0ubuntu0.20.04.4`）。API unit suite 单独 **53 passed**。PostgreSQL 16 未测试，为非阻塞 follow-up。
- **M4b-5-2d2 阶段历史本地门禁**：`make gate` 的 Ruff format **212 files already formatted**；Ruff clean；mypy **42 source files clean**；pytest `-m "unit or contract"` **641 passed, 2 skipped, 67 deselected**；一条非失败 Starlette/httpx deprecation warning。均为本地结果，未运行 CI。该结果是 d2 阶段快照；上文 M4b-5-1、5-2b、5-2c 与 5-2d1 数字也均为各自阶段的历史快照。后续 M4b-6b 阶段门禁快照（**767 passed, 2 skipped, 131 deselected**）见下方对应 section。
- **独立评审发现与修复**：评审发现 P1 connection transaction-sharing race；已为两个 routers 加入 app-scoped request serialization、idle/pre-existing-transaction guard 与 cleanup。另发现 P2 `/apply` 可能拒绝原 revision 的安全重试；现仅当 actor 精确匹配、revision 为 expected+1 且最后 audit action 为 `mark_applied` 时接受重放，其他 stale request 仍返回 409。最终独立 reviewer 对该 slice 无 actionable findings；维护者 signoff 已记录（2026-10-04）。详见[独立评审记录](../reviews/m4b-5-2d2-distribution-api-review-2026-10-02.md)。
- **工程与验收边界**：本切片将 API 报告接入既有 activation coordinator，但不实现 notifier、真实 AS health evidence、auth/session、persistent audit、UI workflow 或 browser acceptance；运行时 schema mapping 与 executable regex semantics 仍未解决。M4b/M4 保持开放，UI browser acceptance pending，所有 REQ acceptance 均未声明。临时 PG12.22 验证不代表 PG16 或部署验收。

## M4b-6a Console Password and Sessions（2026-10-02；工程证据，NOT REQ-S-4 ACCEPTANCE）

本节记录 M4b-6a 阶段的 console role/password/session engineering slice，**不是 REQ-S-4、M4b 或 M4 acceptance**；不声明任何 REQ 已接受。当时 M4b-6b durable audit、M4b-7 login/UI workflow integration、M4b-8 browser acceptance 均仍开放；后续 M4b-6b 已交付（见本报告末尾最新 section），M4b-7/8 与 M4b/M4 整体仍未完成。ADR-0024 **Accepted**（2026-10-03）；M4b-6a 维护者签字已记录（2026-10-04）。

- **实现路径**：`services/config-service/src/as_config_service/auth.py` 提供 `PostgresConsoleAuthStore`、严格 ADR-0024 PBKDF2 verifier、digest-only session/CSRF token persistence、当前 enabled roles per-request resolution、事务性 session revocation、singleton-locked first-admin bootstrap、用户管理及 last-enabled-admin protection。密码按 exact UTF-8 输入验证；PBKDF2-HMAC-SHA256 为 600,000 rounds、16-byte salt、32-byte output，不 normalize/truncate，超 1,024 UTF-8 bytes 拒绝，并 constant-time compare。Session/CSRF 使用 256-bit 随机 token，仅存 digest；session absolute TTL 最长 8h。`bootstrap_admin.py` 提供 `as-config-bootstrap-admin`，以 `getpass` 读取初始管理员密码。
- **API 行为**：`services/config-service/src/as_config_service/api.py` 在 `create_app` 支持可选 session auth；配置 session auth 后它是 primary、fail-closed 路径，现有 callback 模式保持兼容但不是失败 fallback。Login 要求 ASGI `request.url.scheme` 为 HTTPS；未验证任何 production ingress/trusted-proxy 配置。使用 `__Host-` cookies、写操作 CSRF、现有 RBAC policy、logout 与账户 list/create/update。App-scoped request lock 保护该 app 内的共用 auth-store connection，不是跨进程锁。Store 约束为 dedicated injected PostgreSQL connections；错误时会 rollback 整个 active transaction，即使调用参数为 `commit=False`。
- **测试文件与结果**：聚焦测试文件 `test_api.py`、`test_auth.py`、`test_postgres_auth_integration.py`、`test_postgres_auth_api_integration.py` 合计 **116 passed**，有 11 条 Starlette/httpx deprecation warnings。完整 config-service integration 命令 `AS_PG_TEST_DSN='postgresql://postgres@127.0.0.1:55432/as_config' uv run pytest -m integration -q services/config-service/tests`：**85 passed, 319 deselected**，PostgreSQL **12.22**，有 TestClient warnings；PG16 未测试。两项均为本地验证，不是 CI。
- **M4b-6a 阶段当时的本地门禁快照**：`make gate`：Ruff format **220 files already formatted**；Ruff clean；mypy **44 source files**；`unit or contract` **680 passed, 2 skipped, 91 deselected**；8 条非失败 Starlette/httpx deprecations（一个 base warning 加 TestClient per-request cookies warnings）。本地结果，未运行 CI。
- **独立评审**：auth/core 与 API 独立 reviewer 在修复后最终未发现剩余具体 findings；review record 见 [`m4b-6a-auth-session-review-2026-10-02.md`](../reviews/m4b-6a-auth-session-review-2026-10-02.md)。维护者 signoff 已记录（2026-10-04）。
- **边界**：M4b-6a 本身不含 durable append-only audit；M4b-6b 后续已作为独立 engineering slice 交付 durable audit API/store integration（见下文），但这不代表完整审计验收或 REQ-S-4 acceptance。此处记录的 6a 实现也不含 application rate limiting、MFA/SSO、browser login UI 或 authenticated proxy deployment proof。DB runtime-role least-privilege/audit grants 在 6a 阶段之外且当时未验证；后续 M4b-6b engineering slice 已审计 PostgreSQL 12.22 上的有效 grants。部署环境中的 runtime grants 配置及 PostgreSQL 16 仍未验证；这不构成部署验收。既有 `TestClient` deprecations 非失败，CI 未运行。ADR-0024 draft 未获维护者接受；此工程证据不构成 REQ-S-4 pass，也不满足 test-plan 的验收条件。

## M4b-6b Durable Audit API/Store Integration（2026-10-02；工程证据，NOT REQ-S-4/M4b ACCEPTANCE）

本节记录持久化 audit store 与 config API integration 的最终工程状态。它是 M4b-6b engineering slice，不是 REQ-S-4、M4b 或 M4 acceptance，也不是安全认证；ADR-0024 **Accepted**（2026-10-03）；M4b-6b 维护者 signoff 已记录（2026-10-04）。

- **事件与数据最小化**：`AuditRecord` 保存 actor、action、resource、outcome、时间及受控 before/after snapshots；detail 不落库。Credential-key/value marker 与 PEM private-key marker 检查是 heuristic，不是完整 secret scanner；producer allow-list/redaction 仍是必要防线。快照上限 64 KiB，metadata 有安全长度与字符边界。Login/logout snapshots 仅记录安全的 user/session timestamps，不含 password 或 token。
- **数据库边界与权限**：`PostgresAuditStore` 需要明确 migration/owner setup，运行于专用非 public schema；验证 allow-listed schema object catalog、精确 columns/defaults/constraints/triggers 与序列属性，不支持 partitions 或 PostgreSQL publications，并以 retained-history guard 防止 sequence 与保留历史不一致。Owner trigger 防止 row mutation/truncate。Runtime role 必须 NOLOGIN、无 CREATEROLE/成员关系，仅有 schema USAGE、table SELECT 与排除 `id` 列的 INSERT、sequence USAGE/SELECT；无 schema CREATE 或 table mutation。应用启动验证 runtime role；独立 login role 必须 `SET ROLE` 到 runtime role。代码验证不证明已部署数据库配置或 PG16 兼容性。
- **API 与事务**：默认 `create_app` 要求 durable `audit_store`；只有显式 `allow_unaudited_callback_mode=True` 才允许 legacy/test callback mode，且不能与 session auth 同用。Requests 使用 request-level serialization 与精确共享 PostgreSQL connection；audited domain writes 先以 `commit=False` staging，再与 audit append 同事务提交。业务失败先 rollback mutations，再记录 DENIED（snapshots 为 null）；audit unavailable 时 fail-closed，返回 generic 500。所有请求记录 allowed/denied outcome；`/internal/v1` unmatched GET/HEAD 及 POST/PUT/PATCH/DELETE/OPTIONS/TRACE/CONNECT 均审计，同时保留 identity/permission/CSRF guards。
- **路径隐私**：audited session mode 要求外部提供 32-byte stable HMAC key。事件只保存 route template 与排序后的 parameter-name HMAC-SHA256 full digest，不保存 raw path/query；key rotation 会打断跨周期关联。Key provisioning/rotation policy 尚未验收。
- **事务边界**：ChangeOrder、Distribution、ManagedRule proposal activation snapshots 覆盖 before/after（含 tombstone）。Distribution completion/report audit tx1 与 ManagedRule+ChangeOrder APPLIED/audit tx2 是两个 PostgreSQL transactions，不提供跨事务/分布式原子性；audit failure 回滚其所属 transaction。
- **M4b-6b 阶段最后成功完整门禁（历史快照）**：当时 `make gate` 的 Ruff format **225 files already formatted**；Ruff clean；mypy **45 source files clean**；pytest `-m "unit or contract"` **767 passed, 2 skipped, 131 deselected**，11 条非失败 Starlette/httpx deprecation warnings。config-service 全 integration marker 命令在 PostgreSQL **12.22** 上 **122 passed, 3 skipped, 404 deselected**，5 条 deprecation warnings；3 个 publication DDL integration tests 因 server `wal_level=replica`（测试要求 `logical`）跳过。最终 affected workflow matrix **264 passed, 3 skipped, 15 warnings**；API/audit catchall subset **89 passed, 15 warnings**。均为本地结果，不是 CI；PostgreSQL 16 未测试。上述 counts 是 6b 阶段证据，不是当前 M4b-7 验证。
- **评审与剩余项**：最终独立 integrated API/store review 修复后无 actionable findings；维护者签字已记录（2026-10-04），详见 [`m4b-6b-audit-integration-review-2026-10-02.md`](../reviews/m4b-6b-audit-integration-review-2026-10-02.md)。M4b-7/8 工程证据已进展；REQ/M4 整体验收仍未声明；application rate limiting、browser login UI、MFA/SSO、deployed ingress/trusted-proxy proof、PG16 与 CI 均无证据。REQ-S-4、M4b、M4 均未接受。

## M4b-7 Live-read/session shell（2026-10-03；engineering evidence, NOT M4b/REQ ACCEPTANCE）

本节记录 M4b-7 的 read/session shell、ASGI static asset serving/package，以及既有 ChangeOrder submit/approve/reject 工程切片；M4b-7 其他部署/workflow 子项与 M4b-8 均保持 OPEN，不构成 M4b/M4 或任何 REQ acceptance。

- **Refreshed config-service PostgreSQL integration（2026-10-03）**：在与此前相同的本地 PostgreSQL **12.22** 上，当前 API/bootstrap changes 后完整 integration marker run 为 **122 passed, 3 skipped, 432 deselected, 5 warnings**。三个跳过项是要求 `wal_level=logical` 的 publication DDL tests；当前 server 使用 `replica`。本地结果，未运行 CI；PG16 未测。该 marker run 不覆盖 runtime factory 使用 DB-backed roles 的集成部署路径，也不证明 deployed HTTPS ingress 或 browser workflow；这些仍分别受 7.2d 与 7.6/M4b-8 边界约束。此为刷新后的 M4b-7 integration evidence；下方 M4b-6b 的 **404 deselected** 保留为该阶段历史报告，不作改写。

- **已实现**：console 通过 same-origin `/internal/v1` 支持 session restore/login/logout（logout 使用 CSRF），并读取 live managed rules 与 change orders。`?preview=1` 保留本地 fixtures；live mode 不回退到 fixtures。trace 与 operations 明确显示 unavailable。
- **Live existing-order decisions（engineering slice only）**：live table/modal 允许既有 draft 的 creator 提交，并由不同 approver 批准或拒绝 submitted ChangeOrder。UI affordance 检查角色与 creator，URL-encode IDs、发送 CSRF 并在操作后重新读取 server state；不提供规则 CRUD/create/edit/write，也不提供 distribution start/reports/rollback UI。
- **Mock-browser evidence only**：route-mocked submit 发出无 body 的 `POST /change-orders/{id}/submit` 和 CSRF header，随后 reload 显示 submitted；creator 随后看到 Details。route-mocked approver approve 后 reload 显示 approved。空 reject 不发请求；有效理由以 `{reason}` POST、带 CSRF，并 reload 显示 rejected。这些是 mock route checks，不是实际 API/DB-backed/browser integration。
- **API self-rejection regression**：reject endpoint 在 transition/append 前以 403 拒绝 creator 自拒；回归断言 order 保持 SUBMITTED 且没有 append。三个 sibling API tests（creator self-reject、creator self-approve、拒绝理由及 trimmed audit）`uv run pytest -q` **3 passed, 1 warning**。该 fix 的独立 code review 无 actionable findings；此结果不代表 CI 或 acceptance。
- **当前 M4b-7 validation summary**：直接 `make gate` 在首步 `ruff format --check .` 被 untracked、无关的 `testbed/simulators/resip-probe/research/` Python 文件格式差异阻断，不能报告为通过；排除此路径后的最终 scoped validation `uv run ruff format --check --exclude 'testbed/simulators/resip-probe/research/**' .` 报告 **228 files already formatted**，`uv run ruff check --exclude 'testbed/simulators/resip-probe/research/**' .` 全通过，`uv run mypy` **46 sources clean**，`uv run pytest -m 'unit or contract' -q` **795 passed, 2 skipped, 131 deselected, 11 warnings**。Focused runtime tests **20 passed**，bootstrap admin tests **6 passed**。当前 config-service PostgreSQL 12.22 integration 为 **122 passed, 3 skipped, 432 deselected, 5 warnings**；3 个 publication DDL tests 要求 `wal_level=logical`，因本机为 `replica` 而跳过。该 suite 不覆盖 runtime factory DB-backed roles 的部署路径、deployed HTTPS ingress 或 browser workflow。以上为本地验证，未运行 CI；M4b-6b 的 gate 与 integration 计数仍是历史阶段证据；M4b/M4/REQ acceptance remains unclaimed.
- **ASGI static hosting/package engineering slice**：config-service `create_app` 在所有 `/internal/v1` routers 之后从 `/` 提供 packaged console assets；源码运行时 fallback 到 `services/console/web`。`as-console` wheel force-includes `index.html`、`console.js`、`console.css`。这仅验证 ASGI app/TestClient 路由与 package contents。
- **Runtime factory/CLI engineering slice（2026-10-03）**：config-service 提供 `as_config_service.runtime:create_runtime_app` 与 `as-config-service` 命令。Runtime factory 严格读取 `AS_CONFIG_DSN`、`AS_CONFIG_RUNTIME_ROLE`、`AS_AUDIT_RESOURCE_HMAC_KEY_B64`，只建立一个连接、先 `SET ROLE` 再构造共用该连接的 stores，并依赖 audit store startup validation；不执行 schema 创建、migration 或 role provisioning。Bootstrap CLI 单独要求 `AS_CONFIG_OWNER_DSN`，并共享 `AS_CONFIG_SCHEMA`；owner DSN 仅用于 bootstrap，不是 runtime login。Focused fake-connection runtime tests 验证配置失败先于连接、共享连接/顺序及 construction failure cleanup；bootstrap admin tests **6 passed**。此为代码级工程切片，不是生产部署或 acceptance 证据。
- **Config-service image/Helm wiring engineering slice（2026-10-03）**：新增独立 root-context Dockerfile；`as-config-service` 直接声明 `as-platform` workspace dependency，使 isolated image 可安装其 API contract import。Helm 增加默认关闭的非 root Deployment、ClusterIP Service 和可选 `networking.k8s.io/v1` Ingress 模板；模板仅支持 ingress-nginx，启用时 fail-closed 要求 class 为 `nginx`，并固定 `ssl-redirect` 与 `force-ssl-redirect` 为 `"true"`。Deployment 只从外部 runtime Secret 引用 `AS_CONFIG_DSN` 与 audit HMAC key，runtime role 必须预先 provision；startup 不执行 DDL/provisioning。Bootstrap owner DSN 不注入 Deployment。Ingress 还要求 host/TLS Secret、proxy headers 与显式非-wildcard trusted proxy 列表。实际 controller 必须保留默认 `nginx.ingress.kubernetes.io` annotation prefix，且 `no-tls-redirect-locations` 不得豁免 `/`；chart 无法设置或证明这些 controller-level 条件。Secret 仅通过 key references 读取，控制台与 API 均由同一个 ASGI Service 提供。7.2c 仅为模板 wiring；没有实际 HTTP→HTTPS redirect/rejection 或 browser credential transport proof，也不证明 Helm render、镜像构建、真实集群、HTTPS、trusted-proxy 或 browser workflow。
- **Focused evidence and limitation for 7.2c/7.2d**：`uv lock --check` passed；`uv build --package as-config-service --wheel --out-dir /tmp/as-config-service-helm-wheel` succeeded；静态 PyYAML assertions 解析 `deploy/helm/values.yaml` 并确认 configService/Ingress 默认关闭、external Secret name 未设置、proxy headers 关闭、trusted proxies 为空。No Helm lint/template render was possible: the Helm CLI was absent; pulling `alpine/helm:3.16.4` failed on Docker Hub DNS, and the configured mirror attempt was denied by Cloudflare. The dedicated Docker image build could not fetch its Dockerfile frontend because registry access failed. There is no rendered-chart or image-build proof. 7.2c is ingress-nginx HTTPS redirect template wiring only; Helm render, image build, cluster, HTTPS, trusted-proxy and browser proof remain open under 7.2d. These are engineering-slice checks only, not M4b/M4 or REQ acceptance.
- **工程验证**：`uv run pytest -q services/config-service/tests/test_api.py`：**74 passed, 11 warnings**。`uv build --package as-console --wheel --out-dir /tmp/as-console-wheel` 成功；`unzip -l` 确认 wheel 含上述三个 assets。此前的 `node --check services/console/web/console.js`、browser preview 与 route-mocked live checks 仍是各自范围内的工程证据。独立 reviewer 无 actionable findings。
- **未验证与阻塞**：上述 API TestClient/package checks 不验证真实 DB-backed browser auth/session；未运行 CI。代码级 ASGI factory/CLI 与 Helm wiring 已存在，但没有生产 HTTPS ingress、TLS termination 或 deployed trusted-proxy 行为证据；scheme trust 与 same-origin HTTPS 部署仍须验证（现跟踪为 M4b-7.2d）。Ingress 模板的 ingress-nginx redirect wiring 尚无 Helm render 或集群行为证明。独立 Python `http.server` 仍仅供 `?preview=1` 静态预览使用，不提供 API。ManagedRule create/edit/enable/delete 仍被 runtime contract lossless mapping、bundle compiler 与 regex semantics 阻塞；不得发送 placeholder/empty ConfigBundle。live distribution actions、trace source/API，以及 AS instance inventory、notification transport、health collector 也缺失。route-mocked browser checks 不证明真实 API/database/browser integration 或 fleet delivery；M4b-7.3b–7.6 与 M4b-8 仍 OPEN，所有 M4b/M4/REQ acceptance 均 unclaimed。

## M4b-7.2c2 Owner-only database setup（2026-10-03；engineering evidence, NOT M4b/M4/REQ ACCEPTANCE）

本次 focused suite 为 **39 passed**：migration **8**、runtime **24**、bootstrap admin **7**；此结果 supersedes 本报告上方 M4b-7 摘要中的旧 focused runtime/bootstrap counts。

新增手动 `as-config-migrate` owner-only CLI，供 bootstrap 与 web runtime 部署前初始化 config/audit schema 和 least-privilege grants。它只使用 `AS_CONFIG_OWNER_DSN`，验证 `AS_CONFIG_SCHEMA`（默认 `as_config`）由当前 owner 持有，调用 managed-rule/change-order/distribution/auth stores 的 `ensure_schema()` 与 `PostgresAuditStore.ensure_schema(runtime_role)`，然后撤销 `PUBLIC` 与 runtime role 在专用 config schema 上既有的 schema/table/sequence/column 权限，再只授予 schema `USAGE`、stores 所需的 SELECT/INSERT 和限定列 UPDATE，以及 bootstrap singleton SELECT。Audit grants 完全由 audit store 管理。

数据库 login/runtime roles 必须预先由 DBA 创建；runtime role 必须是 NOLOGIN、非 superuser、无 CREATEROLE 且没有角色成员资格。migration 不执行 CREATE/ALTER ROLE 或 `SET ROLE`，不授予 runtime `CREATE`、`DELETE`、`TRUNCATE`，且不会删除数据。Runtime 与 bootstrap 默认使用相同的非 public `as_config` schema；runtime app 仍不做 DDL。Owner DSN 是手动操作凭据，绝不进入 Helm values/Secrets 或 web Pod。

- **Focused unit evidence**：`uv run --directory services/config-service pytest tests/test_migrate.py tests/test_runtime.py tests/test_bootstrap_admin.py -q`：**39 passed**。Migration tests 使用 fake connection/store factories，无真实 database credentials；覆盖配置 fail-before-connect、public/equal schema rejection、ensure call order、限定 grants、失败 rollback/close 与 DSN 错误不泄漏。
- **验收边界**：未运行完整 `make gate`、CI、Helm lint/template/render、镜像构建或数据库部署验证。该代码级 slice 不证明实际 PostgreSQL permissions/deployment，也不改变 7.2d Helm render/HTTPS ingress/trusted-proxy/browser proof 的 OPEN 状态；M4b/M4 与所有 REQ acceptance 仍未通过。

## M4b-7.5 Console fleet inventory UI（2026-10-03；engineering evidence, NOT M4b/M4/REQ ACCEPTANCE）

本节记录 Operations 视图下的 live fleet inventory CRUD 工程切片；后端 PG `as_instances` inventory、distribution notify 与 testbed health probe 已在 prior 7.5 API/store slice 交付。**不**宣称 REQ-F-15/M4 验收、真实 AS 栈补测或 distribution UI。

- **Console UI**：live mode 在 Operations 视图列出 `/internal/v1/as-instances`；approver/admin 可 POST/PUT/DELETE（含 enable/disable、notify URL、health URL）并使用 same-origin session + `X-CSRF-Token` 写路径；只读 session 可 GET 列表。`?preview=1` 仍使用 fixture 表格，不调用 API。
- **API routes**：`GET/POST /internal/v1/as-instances`、`GET/PUT/DELETE /internal/v1/as-instances/{instance_id}` 已在 `api.py`（inventory store 注入时可用）。
- **Focused tests**：`node --check services/console/web/console.js`；`uv run --directory services/config-service pytest tests/test_fleet_api.py -q`（含 list/create/update inventory regression）。
- **PostgreSQL integration（维护者环境）**：`uv run pytest -m integration services/config-service/tests/test_postgres_as_instance_store_integration.py -q`（临时 PG 12.22；非 CI；PG16 未测）。该 marker run 不证明 browser workflow 或 AS 全栈 notify/health 补测。
- **Distribution UI（7.6 slice）**：change-order review modal 内 live **start / batch report / rollback**（`console.js`）；仍非 full M4b-8 或 REQ-F-15 验收。

## M4b-7.6 Distribution console UI（2026-10-03；engineering slice, NOT M4b/M4/REQ ACCEPTANCE）

- **UI**：已批准 / 分发中的 change order → Review 对话框 → Fleet rollout（plan version、批次布局、start、report current batch healthy、rollback）。
- **API**：`POST/GET .../distribution`、`POST .../reports`、`POST .../rollback`（与 `test_fleet_api.py` / PG pipeline integration 一致）。
- **前置**：Operations 登记 enabled 实例；health URL 配置正确时 batch report 触发服务端 probe。
- **证据**：`node --check services/console/web/console.js`；`make gate`；浏览器 HTTPS 证据仍归 M4b-8 节。

## M4b-8 Dev HTTPS same-origin stack（runbook + engineering; NOT signed acceptance）

| 项 | 状态 |
|---|---|
| Compose 栈 | `deploy/compose/README.md` |
| Runbook | [`m4b-8-runbook.md`](m4b-8-runbook.md) |
| 规则范围 | **被叫+前缀**（[`m4-req-calling-regex-lossless-adjudication-2026-10-03.md`](../reviews/m4-req-calling-regex-lossless-adjudication-2026-10-03.md)） |
| Artifact 目录 | [`artifacts/m4b-8/README.md`](../../artifacts/m4b-8/README.md) |
| 脱敏材料路径 | [`artifacts/m4b-8/2026-10-03/`](../../artifacts/m4b-8/2026-10-03/)（Playwright 截图 + `runbook-checklist.md` + `browser-evidence-log.json`） |
| 复现命令 | `M4B8_E2E_PASSWORD='<dev-only>' deploy/compose/scripts/m4b-8-browser-evidence.sh` |
| Git commit | `1bca9eee74c090964d48a217abfe41bfcdf73dab`（`cur`，message: m4 close） |
| **维护者签字** | **Approved**（2026-10-04；chat 授权 AI 代签）— 已审阅上述路径内材料，认可 runbook 中 PASS/FAIL/BLOCKED/N/A 与 10-03 关门裁决一致；**不**表示 REQ-F-13、7.2d、F-15 真 AS 补测已通过 |
| 自动化 smoke（2026-10-03） | 本机 compose：`postgres:12.22` + `up.sh` 后 `./scripts/smoke-https.sh` **OK**（宿主机 `HTTP(S)_PROXY` 需 `--noproxy` 访问 localhost，脚本已处理） |
| Compose PG integration（2026-10-03） | `AS_PG_TEST_DSN=postgresql://postgres:postgres@127.0.0.1:55432/as_config uv run pytest -m integration -q services/config-service/tests` → **136 passed, 3 skipped**（`wal_level` publication 跳过）；非 CI |
| Playwright 浏览器证据（2026-10-03） | 同上 compose 栈；headless Chromium；同源 API 采样见 artifact log |

**M4b-8 步骤 N/A / BLOCKED**：步骤 3（F-13 trace）；7.2d 生产 preflight（M5）；v1.1 主叫/正则；F-15 真 AS 栈补测（裁决后置）。
