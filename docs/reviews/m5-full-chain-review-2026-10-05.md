# M5 全链评审记录 — Requirement / ADR / Design / Code / Testing

- **评审对象**：M5 里程碑（运维）全链交付 —— Helm chart、自定义指标 HPA、缩容保护控制器、draining / ISSU、告警规则集、控制面集群部署证明（含 M4b-7.2d ingress/trusted-proxy）、D12 集群内 PostgreSQL/Redis（ADR-0026）。
  - 计划与关门记录：`docs/plan.md` §4.4 / §4.5 / §4.6
  - 代码范围：`deploy/helm/**`、`deploy/alerts/**`、`deploy/kind/**`、`platform/src/as_platform/{runtime,ops,telemetry}/`、`platform/src/as_platform/__main__.py`、`services/config-service/src/as_config_service/runtime.py`
  - 门禁范围：`Makefile`、`.github/workflows/ci.yml`、`pyproject.toml` pytest 配置
- **评审日期**：2026-10-05
- **评审人**：AI agent（维护者指派全链 review；维护者判定 `docs/reviews/` 下既有 M5 评审记录不可信）
- **评审方法**：只读核查。按 AGENT.md §3 的文档链逐环节核对（需求 → ADR → HLD/LLD → 契约 → 代码 + 测试 → 验收）。
- **证据排除声明**：本次评审**未采信** `docs/reviews/` 下任何 M5 评审记录（`m5-*` 系列）作为证据来源。全部结论来自 `docs/plan.md`、ADR、HLD/LLD、代码、Makefile、CI 配置的原文。

---

## 1. 评审结论

**结论：不通过（Not approved）。建议撤销 / 降级 2026-10-04 的 M5 工程关门签字。**

不是"文档没写全"的问题，而是三类硬伤：

1. **核心交付物是死的** —— 8 条告警中 6 条永不触发；缩容保护配置读了不参与判定；生产 profile 渲染即不可启动。
2. **证据是伪的** —— 5 处"看起来通过但不可能失败"的检查；唯一能变红的那项检查（`make chart-check`）不在任何门禁里；集群日志证据位于被 gitignore 的 `artifacts/`。
3. **设计文档停在 M5 之前** —— HLD/LLD 仍写"PG/Redis 在 chart 外""真实集群滚动升级与缩容未跑"，与 ADR-0026 / §4.6 的实际交付直接矛盾。

### 1.1 正面确认（应当保留，不是本次否定的对象）

- **纯逻辑内核真实且测试质量高**：`plan_scale_down` 是纯函数并有 socket/时钟/随机数探针测试（`platform/tests/test_downscale_guard.py:138-163`）；`ProcessShell` draining 状态机（`test_shell.py`）、`MetricsRegistry`（`test_metrics.py`）、有界队列与后台导出线程（`test_telemetry.py`、`test_telemetry_export_integration.py`，真 UDP socket）、health HTTP server（真 socket）均为真实现。
- **`make gate` 四步真的会红**：`ruff format --check` → `ruff check` → `mypy` → `pytest -m "unit or contract"`（`Makefile:21,22,25,33`），无 `|| true`、无 `-` 前缀、无结尾 `exit 0`。
- **三个结构守卫有效且会红**：`tests/test_workspace_layout.py`、`tests/test_version_consistency.py`、`platform/tests/test_library_independence.py`，且均带防空转断言。
- **ADR-0026 不是纸面 ADR**：`values.stateStores` + `state-{postgres,redis,networkpolicy,config-runtime-secret,migrate-job}.yaml` + `chart-check` bundled 矩阵 + kind `M5_BUNDLED_STATE=1` + `values-onprem.example.yaml` + runbook 全部落地。
- **部分 kind 证据是真断言**：`m5-issu-scale-evidence.sh`（drain 期间必须观测到 503）、`m5-plan-scale-down-from-metrics.sh`（调用真实 `plan_scale_down`，拒绝路径 `SystemExit(1)`）、7.2d 浏览器脚本（登录成功与"无明文 HTTP POST"会抛错）。

---

## 2. Requirement 链

M5 的 7 类交付物中 5 类可追溯到 `REQ-NF-3 / REQ-NF-4 / REQ-NF-9 / REQ-NF-13 / REQ-NF-14`，源头存在。链在两处断开：**验收文档层**与**运维代码层**。

| # | 现象 | 证据 | 影响 | 严重度 |
|---|---|---|---|---|
| R-1 | **7.2d（ingress/trusted-proxy）是 M5 三大关门条件之一，但 PRD 中无任何对应需求**。`REQ-S-2` 是与 S-SBC 的 SIP 信令 TLS，`REQ-S-4` 只讲鉴权与审计，都不覆盖控制台 HTTPS 重定向 / `X-Forwarded-Proto` 信任 / ingress proxy CIDR 白名单 | `docs/plan.md:217,392` vs `docs/requirements/prd.md` 全文 | 关门条件无需求出处，也就没有可判定的验收项；`test-plan.md:183-191` 中它只是 §1.4 的 BLOCKED 前置条件 | **Blocker** |
| R-2 | 5 份 M5 验收 / runbook 文档与 `report.md` 全文 **REQ-\* 引用数为 0** | `docs/acceptance/m5-*.md`；`report.md:167-227` | 违反 REQ-G-2 的验收项（`test-plan.md:339-342` 要求 review record 可追溯到至少一个 REQ 编号）；M5 证据无法与 REQ-NF-3/4/13/14 对齐 | Major |
| R-3 | REQ-NF-3 验收口径含容量数字（阈值 500、1000 并发、3→≥5 副本），与项目硬规则互斥 | `test-plan.md:231-233` vs `plan.md:249,403` | 按验收项填就违反"M6 前不发布容量数字"，遵守禁令就永远无法通过；需求 / 验收 / 工程规则三方互斥 | Major |
| R-4 | REQ-NF-14 验收写成"手动触发**任一**条件" + "通知通道待定（M2 冻结）" | `test-plan.md:295-301` | 4 条要求只需 1 条触发即可勾选，且通道未定则"正确发出告警"无从断言 | Major |
| R-5 | 缩容保护判据（ADR-0010 的核心决策）在 `test-plan` 中**零验收断言** | `test-plan.md:230-235` vs `ADR-0010:6` | M5 声称"缩容保护已交付"，验收侧无从判定 | Major |
| R-6 | M5 全部集群运行时证据位于被 gitignore 的 `artifacts/m5/<date>/`，仓库内不可复核 | `m5-evidence-summary.md:3,22-29`；`.gitignore:25` | 除维护者本机外无人可复核；`report.md` / closure 中的 "PASS" 全是对不存在文件的转述 | Major |
| R-7 | ISSU / 缩容的"不掉呼叫"证据全部来自注入计数器 `AS_M5_SIMULATED_ACTIVE_CALLS` | `m5-downscale-runbook.md:48-56`；`deploy/kind/m5-issu-scale-evidence.sh:27-28,97` | 只能证明判据接线，证明不了"存量呼叫完成 / 无呼叫丢失"（那是 REQ-NF-1/3/4 的断言，属 M7） | Major |
| R-8 | 无源交付项（有实现、无 REQ 出处）：PDB 模板、NetworkPolicy、`simulatedActiveCalls` chart 字段、D12 的 HA / PITR / RPO-RTO / restore drill 承诺 | `pdb.yaml:4`；`state-networkpolicy.yaml`；`deployment.yaml:99-102`；`m5-state-stores-runbook.md:70-105` | 无法判定做没做、做到什么程度；与 `plan.md:369-379` 自认的 PM/AM/UM"需求待补"同源 | Minor |
| R-9 | 代码侧 REQ 追溯缺失：`downscale_guard.py` / `downscale_config.py` 只标 ADR-0010/0009，无 REQ 编号 | `platform/src/as_platform/ops/downscale_guard.py:9,22,46,86,88,118` | REQ-G-2 只能经 ADR 间接追溯，链长一跳 | Minor |

**M5 证据等级判定**：kind 真实集群证据覆盖部署形态与模板渲染；模拟注入证据覆盖"机制接线"；工程切片（`make gate` / integration）覆盖 REQ-G-4。**没有任何一项达到 REQ 级验收**。M5 文档自己也声明"Not claimed | REQ / test-plan acceptance"（`m5-engineering-closure-2026-10-04.md:76`），因此问题定性为"以工程切片 + 模拟注入证据充当里程碑关门"，而非虚假验收。

---

## 3. ADR

7 个 M5 相关 ADR（0005 / 0008 / 0009 / 0010 / 0013 / 0014 / 0026）状态均为 accepted，consequences 均非空，无"proposed 被当作 accepted 使用"。冲突集中在：

| # | 冲突 / 缺口 | 证据 | 严重度 |
|---|---|---|---|
| A-1 | **ADR-0008「站点内零单点」与 ADR-0026 内建单副本 PG/Redis 直接冲突**。0008 要求 Redis Sentinel（1 主 2 从 3 哨兵）+ PG 流复制 + 备份 + PITR；0026 标准路径渲染出 `replicas: 1` StatefulSet 与 `replicas: 1` Redis Deployment，runbook 自认 "Production HA is customer-owned"。0008 无 Amendment 登记此缺口 | `0008:27-29` vs `state-postgres.yaml:35`、`state-redis.yaml:12`、`m5-state-stores-runbook.md:72,80` | **Blocker** |
| A-2 | ADR-0008 把跨站点切换演练**明确指派给 M5**，M5 关门清单无此项，也未登记延期 | `0008:49,76`；`plan.md:236-241,314-325`（全文无"温备/切换/演练/RTO/RPO"） | Major |
| A-3 | ADR-0005 三信号只落地 1/3：全仓无 `opentelemetry` 依赖、无 OTLP exporter 实现、无 `trace_id`/`span_id`、无结构化 JSON 日志、`cps` 指标不存在 | `telemetry/__init__.py:77-86,129`；`__main__.py:147-150`；`metrics.py:34-37` | Major |
| A-4 | ADR-0019 推翻 SIP 栈后未同步架构文档：`新系统整体架构.md:348` 仍以 `sippy==2.4.2` 作为 ADR-0009 的"前提事实"，而 ADR-0009 的复核条款正是建立在该前提上 | `新系统整体架构.md:348,225,391,442` vs `0009:22,30`；AGENT.md §7 | Major |
| A-5 | ADR-0013 正文 Decision / Consequences 仍写"chart 不部署 PG/Redis"，修订只在末尾 Amendment 段 | `0013:27,44` vs `0013:82-89` | Minor |
| A-6 | 架构 §6.3 图写"缩容保护挑 active_calls **最少**的 Pod"，与 ADR-0010 / 实现 / values 的"≤ 阈值（默认 0）"矛盾 —— 按图实现会掉呼叫 | `新系统整体架构.md:377` vs `0010:25`、`downscale_guard.py:85-88`、`values.yaml:254` | Minor（实现正确，图错误） |
| A-7 | 告警规则集（REQ-NF-14）无独立 ADR；`as_` 前缀命名契约从未被 ADR 裁决 | `deploy/alerts/README.md:38-60` | Minor |
| A-8 | ADR-0014 的 REQ 追溯编号错误（自称 REQ-NF-13，实为 OTel 三信号），已自注并登记 D8，未裁决 | `0014:6,72`；`plan.md:352` | Minor |
| A-9 | ADR-0009 / 0010 的 M5 实证基于模拟计数，ADR-0010 的 Evidence 节未披露 | `0010:57-62` vs `plan.md:226-228`（计划层已披露） | Minor |

**纸面 ADR**（写了、代码/工件不体现）：ADR-0005 的 traces / logs / 呼叫轨迹通道 / `cps`；ADR-0008 的跨站点温备、Sentinel、PG 流复制；ADR-0020 的 feature 门控整体（0020:59 自认"暂无实现证据"）；ADR-0010 的 in-cluster actuator（ADR 允许运维脚本，但至今无工件）。

---

## 4. Design（HLD / LLD）

**文档链断得最彻底的一环。** HLD / LLD 标注 `As of: 2026-10-02`，M5 工作发生在 2026-10-04，两份文档**从未为 M5 更新**。

| # | 现象 | 证据 | 严重度 |
|---|---|---|---|
| D-1 | HLD §7 仍写 "**Redis and PostgreSQL are external to the chart**"，与 ADR-0026 / §4.6 已交付的 `stateStores` 直接矛盾 | `hld.md:135` | **Blocker（文档链）** |
| D-2 | HLD §7 仍写 "**A real Kubernetes rolling upgrade and scale-down have not been run**"，而 §4.5 已声称 kind 上跑通并签字 | `hld.md:139` vs `plan.md:284-293` | **Blocker（文档链）** |
| D-3 | LLD §1 对 `deploy/helm` 仍写 "no Helm lint/template/render proof…real cluster rollout/scale-down and alert firing also remain unverified"；LLD §7 同样写 "Live Kubernetes rolling-upgrade/scale-down … unverified" | `lld.md:34,124` | **Blocker（文档链）** |
| D-4 | `stateStores` 在 HLD / LLD 中**零出现**（全 docs 检索仅命中 plan、ADR README、0013、0026、架构文档、reviews、acceptance runbook） | grep `stateStores` | Major |
| D-5 | M5 新增的 `downscale_config.py`、`ActiveCallSource` 模拟计数 seam、health/metrics 端点、ingress 模板，HLD / LLD 均未记载；LLD 仍写"executable injects `active_calls=lambda: 0`" | `lld.md:23` | Major |
| D-6 | HLD §6 / LLD §6 已诚实写明"alert rules are configuration artifacts, not evidence of an alert backend firing"，但该结论未传导到 M5 关门判定 | `lld.md:114`、`hld.md:113` | Minor（信息） |

按 AGENT.md §3.1，HLD/LLD 是编码前的必经产物；M5 的部署形态发生了**架构级变化**（chart 内建状态存储），却没有任何 HLD/LLD 落点。

---

## 5. Code

### 5.1 告警：8 条规则中 6 条是死规则

| 规则 | 引用指标 | 事实 |
|---|---|---|
| `ASCallStateStoreUnavailable`（critical） | `as_state_store_available` | **代码中不存在** |
| `ASConfigRollbackTriggered`（critical） | `as_config_rollbacks_total` | **代码中不存在** |
| `ASTlsCertificateExpiring` | `as_tls_certificate_expiry_seconds` | **代码中不存在**（REQ-NF-14 明确要求"证书 30 天内到期"，实际不可达） |
| `ASConfigDrift` | `as_config_version_in_sync` | **代码中不存在** |
| `ASHighErrorRatio` | `as_sip_responses_total` | 名字存在，但 `record_response()` 在生产代码中**零调用点** |
| `ASTelemetryDropped` | `as_telemetry_dropped_total` | 名字存在，但 `record_telemetry_dropped()` **零调用点** |

证据：`platform/src/as_platform/telemetry/metrics.py:34-37` 只定义 4 个指标；四个不存在的指标名全仓仅命中 `deploy/alerts/` 自身；`record_response` / `record_rule_hit` / `record_telemetry_dropped` 的调用点只出现在 `platform/tests/test_metrics.py`；`__main__.py:94` 只调用 `set_active_calls`。

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| C-1 | 上述 6 条规则永不 firing，且 `promtool check rules` 不会报错（PromQL 允许引用不存在的指标）；全仓无任何 `promtool` 执行点 | `as-alerts.yaml:86,123,140,157,23-31,49`；Makefile / CI / 测试均无 promtool | **Blocker** |
| C-2 | `ASHighErrorRatio` 分母 `clamp_min(sum(rate(...)), 1)` 数学错误：`rate()` 单位是"每秒"，低话务全量故障时 ratio 被压到 0.01，恰好不触发 | `as-alerts.yaml:30` | Major |
| C-3 | `ASTelemetryDropped` 阈值 `> 0` 等价于"发生一次即告警"（配合 `for: 15m`），与 description 的"持续上升"语义不符 | `as-alerts.yaml:49` | Major |
| C-4 | `ASActiveCallsSurge` 在零基线时任意非零即触发；`sum()` 抹掉 `use_case` 维度 | `as-alerts.yaml:104` | Minor |
| C-5 | 8 条规则均无 `runbook` / `runbook_url`；无 `absent()` 类规则，指标从未出现不会告警 | `as-alerts.yaml` 全文 | Minor |

### 5.2 平台代码：模拟 seam 进入生产路径

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| C-6 | **缩容保护是"死配置"**：`load_downscale_guard_config()` 读进来只 `logging.info`；`guard.enabled` / `protect_when_active_calls_above` 全仓无消费点；`plan_scale_down` 除测试外只在 kind 脚本中被手工调用。Helm 确实下发了 `AS_DOWNSCALE_GUARD_*`（`configmap.yaml:69-70`），形成"配了但不生效"的假象 | `__main__.py:119-124`；`downscale_config.py:40,46`；`plan.md:227`（只证明了"读取"，不证明"生效"） | **Blocker** |
| C-7 | **OTLP 导出是空壳**：配了 `OTEL_EXPORTER_OTLP_ENDPOINT` 也只创建 `BoundedQueueSink(capacity=256)` 而不传 exporter → `NoOpExporter`，数据入队即丢弃；`export_failure_count` 永远为 0，运维无从发现 | `__main__.py:147-150,169`；`telemetry/__init__.py:77-86,129` | Major |
| C-8 | **模拟计数 seam 进入生产类**：`ActiveCallSource.__init__` 无条件读 `AS_M5_SIMULATED_ACTIVE_CALLS`，`count()` 把假计数并入真实返回值；该 env 被 Helm 渲染为正式字段（`simulatedActiveCalls`） | `runtime/active_calls.py:22-29,49,68-76`；`deploy/helm/templates/deployment.yaml:99-102` | Major |
| C-9 | `record_response` / `record_rule_hit` / `record_telemetry_dropped` 零生产调用点，指标永不递增 | grep 全仓 `*.py` | Major |
| C-10 | `AS_DOWNSCALE_GUARD_*` 解析失败抛 `ValueError`，但加载点在 `try` 块**之外**（`try` 自 `:179` 开始）→ 配置错误直接崩进程而非返回 exit code 2；且失败路径无测试 | `downscale_config.py:31,45`；`__main__.py:119` vs `:187-189` | Major |
| C-11 | `PostgresVersionStore` 运行时接线**零测试**：`test_runtime.py` 全文无 `version_store` / `PostgresVersionStore`；表名推导 `f"{config_schema}_config_versions"` 无任何断言固定 | `services/config-service/src/as_config_service/runtime.py:278-280`；`services/config-service/tests/test_runtime.py` | Major |
| C-12 | 4 个 M5 新文件无 `# See ADR-00NN`（AGENT.md §5 硬性要求 / REQ-G-3） | `runtime/active_calls.py`、`runtime/health.py`、`ops/downscale_config.py`、`__main__.py` | Minor |

### 5.3 Helm：生产 profile 开箱即坏

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| H-1 | **`stateStores.enabled=true` + `bootstrapDevCredentials=false` → Postgres 起不来**。`secret.yaml` 的 else 分支不写 `POSTGRES_SUPERUSER_PASSWORD` / `CONFIG_DB_OWNER_PASSWORD`，而 `state-postgres.yaml` 用非 optional 的 `secretKeyRef` 引用它们 → `CreateContainerConfigError`。**这正是 `values-onprem.example.yaml` 的组合** | `secret.yaml:30-40` vs `state-postgres.yaml:58-72` vs `values-onprem.example.yaml:8-12` | **Blocker** |
| H-2 | **`values-onprem.example.yaml` 原样无法通过 `helm template`**：`configService.enabled=true` 而 `secretName: ""` → 模板直接 `fail`；README 第 2-3 行的安装命令必然失败，而 `chart-check` 从不以该 profile 渲染 | `values-onprem.example.yaml:31-35`；`config-service-deployment.yaml:4-6`；`chart-check.sh` 只用 `--set` | **Blocker** |
| H-3 | `tls.enabled=true` + `secretName=""`（**默认值**）→ 卷挂载被跳过，但 ConfigMap 无条件输出 `SIP_TLS_ENABLED: "true"`，fail-open | `deployment.yaml:138` vs `configmap.yaml:33-39`；`values.yaml:211-217` | Major |
| H-4 | `sip.peerAllowlist` 默认空串，chart 侧不 fail-closed（ADR-0016 的核心控制退化为"靠进程自觉"） | `values.yaml:148`；`NOTES.txt:27-30` | Major |
| H-5 | 明文口令进入 values；`state-migrate-job.yaml` 把 owner 口令作为**明文 env value**，`kubectl get job -o yaml` 即可读 | `values.yaml:160-165`；`state-migrate-job.yaml:16,67-68` | Major |
| H-6 | `secretKeyRef: optional: true` + 空 `postgres.host` / `database` → 渲染出 `postgresql://:@:5432/`，Pod 正常起、运行时才失败；DSN 未做 URL 编码 | `deployment.yaml:69-89`；`secret.yaml:16-40`；`values.yaml:200-207` | Major |
| H-7 | 含 `@` 的 `REDIS_URL` 被**静默丢弃**，无任何提示 | `configmap.yaml:43` | Major |
| H-8 | NetworkPolicy 只有 `policyTypes: [Ingress]`（无 Egress），且源为任意带 `app.kubernetes.io/part-of: 3rdparty-as` 标签的 Pod → 同标签任意 Pod 可直连 5432/6379 | `state-networkpolicy.yaml:18-24` | Major |
| H-9 | `postgres.port` 可配置，但 config-service Secret / migrate Job / NetworkPolicy 三处硬编码 `5432` | `values.yaml:202` vs 三处 | Major |
| H-10 | `minAvailable: 0` 因 falsy 判定静默不渲染；`minAvailable >= replicas` 无校验会致节点 drain 死锁 | `pdb.yaml:11`；`deployment.yaml:29` | Minor |
| H-11 | 无 `resources` → BestEffort QoS；AS 无 startupProbe；config-service 用 `tcpSocket` 探针且无 preStop / PDB | `values.yaml:103,107,128`；`config-service-deployment.yaml:78-91` | Minor |

### 5.4 kind 证据脚本：5 处伪验证

| # | 伪验证 | 证据 |
|---|---|---|
| K-1 | `m5-ingress-evidence.sh` 三个状态码**只 echo**：HTTP 非 3xx 仅 `WARN` 不退出，HTTPS / port-forward 码从不断言，结尾 `echo "recorded"` → 三个码全是 000 也 exit 0 | `:104-127` |
| K-2 | `chart-check.sh` 的 HPA 守卫只 grep `minReplicas` 字符串、**不校验 helm 退出码**；而 `hpa.yaml:43` 正常渲染的 stdout 天然含 `minReplicas` → 把守卫删掉测试照样 PASS | `:50-57` vs `hpa.yaml:21-22,43` |
| K-3 | `m5-7.2d-evidence.sh` item-2 无条件 PASS（else 分支直接打印 PASS）；item-3 空 secret 也打印 PASS | `:55-69` |
| K-4 | bootstrap-admin 任何失败（口令错 / DSN 不通 / 命令不存在）都被吞成 "already complete or skipped" | `:37-42` |
| K-5 | `m5-verify.sh` 无 kind 集群 → `exit 0`；无 config-service Pod → WARN 跳过断言，仍打印 `m5-verify: OK` | `:16-19,29-45` |
| K-6 | `m5-ingress-evidence.sh:30` 从 GitHub `main` 拉取未 pin、无校验和的 ingress-nginx 清单 → 证据不可复现 + 供应链风险 | `:30` |

**关键定性**：所有 ISSU / 缩容证据的输入是注入的 `AS_M5_SIMULATED_ACTIVE_CALLS=3`。真实 SIP 呼叫从未驱动过 `as_active_calls`（`increment` / `decrement` 全仓无生产调用点）。这是"假造计数 → 观察假计数下降 → 断言通过"的自证式取证。

---

## 6. Testing 与门禁

### 6.1 核心问题：门禁不会因为 M5 的问题而变红

| 事实 | 证据 |
|---|---|
| `make gate` = `lint type test-unit`，**不含 chart-check** | `Makefile:62` |
| CI 只有 `.github/workflows/ci.yml`，四个 job **无一执行 helm / chart-check**；而 `plan.md:260` 白纸黑字写 "M5-0c chart-check…CI ① fast 已纳入"（与事实不符） | `.github/workflows/ci.yml:37-57` vs `plan.md:260` |
| CI ③ e2e / ④ performance **0 条测试 → pytest 退出码 5（NO_TESTS_COLLECTED）**，被 `continue-on-error: true` 永久涂绿；注释仍写 "Remove in M3"，已过期两个里程碑 | `ci.yml:92,116,91` |
| CI ② integration 无 PG service、无 `AS_PG_TEST_DSN` → 13 个文件中 11 个 `pytest.skip`，实际只跑 1-2 个；"142 passed" 是本地 compose PG 的数字，CI 里产不出来 | `ci.yml:79-80`；AGENT.md §9「本地门禁不是 CI」 |
| `make gate-strict` / AST 扫描**完全不存在**，但 AGENT.md:176、ADR-0015、prd.md:507 都写成既有能力 → REQ-G-3 无处执行 | Makefile 无此目标；全仓无 AST 扫描脚本 |
| `.PHONY` 漏 4 个 m5 目标 | `Makefile:6` |

**结论**：M5 关门证据的三项（`make gate` / `chart-check` / `test-integration-compose`）每一项单独看都真实可失败，但**合起来不等于"M5 通过了门禁"** —— M5 的交付物没有任何一层自动化门禁覆盖。`make gate` 的绿与 M5 是否完成**在技术上无关**。

### 6.2 测试层实况

| 层 | marker | 文件数 | 状态 |
|---|---|---|---|
| ① unit | `unit` | 42 | 真跑、真红（含 3 个守卫） |
| ① contract | `contract` | 5 | 真跑 |
| ② integration | `integration` | 13 | CI 中 11 个 skip；本地需 compose PG |
| ③ e2e | `e2e` | **0** | 至今没有任何测试 |
| ④ performance | `performance` | **0** | `testbed/load/` 下 0 个测试文件 |

pytest 配置健康：无 `conftest.py`、无 `deselect`、无 `xfail`、无 `-k` / `-m not` 过滤；报告中的 "deselected" 是 `-m "unit or contract"` 的自然反选。

### 6.3 测试质量

正面：未发现 `assert True`、未发现"只调用不断言"、未发现 mock 掉被测逻辑；`test_downscale_guard.py:138-163` 的纯度探针、`test_telemetry_export_integration.py` 的真 socket + 条件变量，质量高。

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| T-1 | **feature 开关只有解析层测试，无开 / 关两态的行为测试**。`AS_DOWNSCALE_GUARD_ENABLED` 已引入，但没有任何测试证明"关闭时行为不同"（事实上确实没不同，见 C-6）；ADR-0020 要求的默认态 / 灰度策略 / 移除条件在代码与注释中均未见 | `test_downscale_config.py:12-25`（全文件仅 4 条断言）；AGENT.md:109,151,287 | **Blocker** |
| T-2 | `test_downscale_config.py` 无任何非法输入失败路径（`_parse_bool` 的 `ValueError`、非整数阈值的 `ValueError`） | `downscale_config.py:31,45` | Major |
| T-3 | `test_health_server.py` 仅 `assert "as_active_calls" in body`，不校验 TYPE / 标签 / 数值；404 分支未测；4 类断言挤在单一 test 内，前一条失败即掩盖后续 | `:42-52` | Minor |
| T-4 | `test_active_calls_source.py:22-35` 整体是在给生产模拟 seam 写合法性背书 | `:22-35` | Minor |
| T-5 | 测试注释普遍只引 ADR / test-plan，不引 REQ 编号（对比 `version_store.py:40` 有 `REQ-NF-10`） | `test_downscale_guard.py`、`test_metrics.py`、`test_shell.py` | Minor |

---

## 7. 建议的最小修复集（按性价比排序）

1. **告警**：删掉或实现 4 个不存在指标对应的规则；给 `record_response` / `record_rule_hit` 接真实调用点；修 `clamp_min` 数学错误与 `> 0` 阈值；把 `promtool check rules` 加入 CI。
2. **缩容保护**：让 `guard.enabled` / `protect_when_active_calls_above` 真正参与判定（或删除配置项并同步改文档），补开 / 关两态行为测试与非法输入测试。
3. **Helm**：修 `secret.yaml` else 分支缺 key（H-1）；让 `values-onprem.example.yaml` 可渲染并将其纳入 chart-check 矩阵（H-2）；`tls.secretName` 为空时 `fail`（H-3）；`peerAllowlist` 为空时 `fail`（H-4）。
4. **伪验证**：修 K-1 ~ K-5 五处（核心是"断言必须能失败"+"校验退出码"），pin 住 ingress-nginx 清单（K-6）。
5. **门禁**：`chart-check` 进 CI ①（兑现 `plan.md:260` 已声称的行为）；CI ② 起 compose PG 并设 `AS_PG_TEST_DSN`；给 e2e / performance 加"该层有用例时必须阻塞"的守卫；补 `gate-strict` + AST 扫描，或把 AGENT.md / ADR-0015 / PRD 中的措辞改为"尚未实现"。
6. **文档链**：HLD / LLD 补 M5 章节（`stateStores`、downscale 配置、模拟 seam、health/metrics、ingress），并改掉"PG/Redis 在 chart 外""真实集群未跑"等陈旧表述；ADR-0008 加 Amendment 处理与 ADR-0026 的 SPoF 冲突；`新系统整体架构.md` §6.2/§6.3/§8 的 sippy 前提事实按 ADR-0019 更新；补 7.2d 的 REQ 出处或显式登记为无源关门条件。
7. **证据可复核**：把 `artifacts/m5/` 从 `.gitignore` 放开或改存至仓库内 `docs/acceptance/artifacts/`，否则所有 "PASS" 都是对不存在文件的转述。

---

## 8. 签字

| 项 | 记录 |
|---|---|
| 评审结论 | **不通过（Not approved）** |
| 建议处置 | 撤销 / 降级 2026-10-04 M5 工程关门签字；按 §7 修复后重新评审 |
| 评审人 | AI agent（维护者指派），2026-10-05 |
| 维护者确认 | **待签字**（本栏须由维护者填写；本记录不构成 REQ 级验收，也不替代 M5 关门裁决） |
| 未采信证据 | `docs/reviews/` 下所有 `m5-*` 评审记录（维护者判定不可信） |
