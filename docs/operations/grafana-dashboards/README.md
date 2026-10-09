# Grafana 看板模板 — In-house IMS Application Server（文档暂用名）

> **状态**：交付物 **2.1 Grafana 看板模板**（[`docs/product-packaging-plan.md`](../../product-packaging-plan.md) §1 第二批 #2.1；评审意见 **G-P0-4** 已落实：不含 Diameter Sh 面板，且**未创建** `sh-interface.json`（**G-P2-3**）。本目录含 `overview.json` 与 `sip-signaling.json` 两份看板。
>
> **⚠️ 可用性前置条件（必须先读）**：AS Pod 模板**没有** `prometheus.io/scrape` 注解，chart 内**没有** ServiceMonitor / PodMonitor（`deploy/helm/templates/` 全目录 grep 无命中，2026-10-10 自核实）。`/metrics` 端点存在且渲染出容器端口 `health-http`（`platform/src/as_platform/runtime/health.py`，`health.port` 默认 8080），但**没有任何采集器被 chart 接线到它**。**在补齐抓取接线前，所有依赖 `as_*` 的面板不会有数据**；不依赖它的面板（kube-state-metrics / cAdvisor 系列）只取决于集群是否装了对应组件。「Prometheus 里没有」≠「进程没产出」—— 人工验证方法见 [`../runbook-l1.md`](../runbook-l1.md) §1 检查 4。
>
> **零容量数字 / 不含时延面板**：本目录**不含任何容量数字**（无 CPS / CAPS / BHCA / 并发 / 吞吐 / 时延 / 资源配额）；O1 容量目标**未裁决**，`AGENT.md` §2 禁止在 M6 真实 socket 实测前发布任何此类数字，本目录**不引用** M6 dev-host 测量。**时延面板同样不存在**：本仓库没有 histogram / summary —— `MetricKind` 只有 `COUNTER` 与 `GAUGE`（`platform/src/as_platform/telemetry/metrics.py`），注册表里没有任何时延或吞吐序列；计划文档 2.1 原文的「时延 P50/P95/P99」因此**无法交付**，建了就是假面板（§4）。
>
> **不含 Sh 面板 / 术语纪律**：`AGENT.md` §2 明确**不做 Diameter Sh**，属范围外的非目标（N/A，非 defer），连占位面板都不建。「v1」「v1.1」**不是发行版本**；本目录任何内容**不构成验收结论** —— M5 工程关门 ≠ REQ 验收，**M8 RC 就绪 ≠ 关门**，E1/E4/E5 仍未验收，e2e = 0（performance 仅 accept-all harness，非业务判决路径）。

---

## 1. 两份看板的定位与面板清单

`overview.json`（`uid: as-overview`，15 个面板）—— 整体健康 / 会话数 / 吞吐观测 / 状态存储 / 运行时。
`sip-signaling.json`（`uid: as-sip-signaling`，7 个面板）—— SIP 信令明细与判决。

### 1.1 `overview.json`

| # | 面板 | 指标 / 表达式要点 | 数据来源 | 前置条件 | 口径提醒 |
|---|---|---|---|---|---|
| 1 | 状态存储可达性（当前值） | `min by (use_case) (as_state_store_available)` | AS `/metrics` | 抓取接线 + `REDIS_URL` 非空 | 序列**不存在 ≠ 0**；可达性状态，非容量 |
| 2 | Pod Ready 状态（当前值） | `max by (pod) (kube_pod_status_ready{namespace=~"$AS_NAMESPACE", condition="true"})` | kube-state-metrics | 集群装了 kube-state-metrics | draining 时 `/health/ready` 返回 503（ADR-0009） |
| 3 | Deployment 副本：期望 / 可用 | `kube_deployment_spec_replicas` / `..._status_replicas_available` | kube-state-metrics | 同上 | 只反映已公布的整数，**不说系统该有几个副本**（O1） |
| 4 | 各用例在途呼叫数 | `sum by (use_case) (as_active_calls)` | AS `/metrics` | 抓取接线 | 每 15s 无条件写入；数量观测，无上限阈值 |
| 5 | 每 Pod 在途呼叫数 | `as_active_calls`（保留 `pod`+`use_case`） | AS `/metrics` | 抓取接线 | 缩容守卫需要**每实例**值（ADR-0010），聚合均值会掩盖单点 |
| 6 | 缩容守卫状态 | `max by (pod, use_case) (as_downscale_removable)` | AS `/metrics` | 抓取接线 | 1 = 可摘除，0 = 承载呼叫**或** draining；无阈值（「大于 0 即保护」是实现口径，不是容量结论） |
| 7 | SIP 响应速率 | `sum by (use_case, status_class) (rate(as_sip_responses_total[5m]))` | AS `/metrics` | 抓取接线 + **生产无生产者** | 速率观测，非吞吐能力 |
| 8 | 失败响应占比 | 与 `ASHighErrorRatio` 同口径的比率表达式 | AS `/metrics` | 同上 | **比率不是容量指标**；面板不画阈值线，阈值唯一维护点在 `as-alerts.yaml` |
| 9 | 规则命中速率 | `sum by (rule) (rate(as_rule_hits_total[5m]))` | AS `/metrics` | **无任何调用方 → 预期无数据** | 保留面板只为让缺口可查；异常口径只能是相对基线 |
| 10 | 状态存储可达性历史 | `min by (use_case) (as_state_store_available)` | AS `/metrics` | 同面板 1 | 面板 1 的历史视角 |
| 11 | 遥测丢弃速率 | `sum by (use_case) (rate(as_telemetry_dropped_total[5m]))` | AS `/metrics` | 抓取接线 + `OTEL_EXPORTER_OTLP_ENDPOINT` 非空 | chart 默认 `telemetry.otlpEndpoint: null` → 无数据 |
| 12 | CPU 使用（每 Pod） | `sum by (pod) (rate(container_cpu_usage_seconds_total{namespace=~"$AS_NAMESPACE", container!="POD"}[5m]))` | kubelet / cAdvisor | 集群提供 kubelet 指标 | 资源观察；不含 requests/limits 承诺 |
| 13 | 内存工作集（每 Pod） | `sum by (pod) (container_memory_working_set_bytes{...})` | kubelet / cAdvisor | 同上 | **不可用作会话泄漏基线**（会反推出容量数字） |
| 14 | Pod 容器重启增量 | `sum by (pod) (increase(kube_pod_container_status_restarts_total{namespace=~"$AS_NAMESPACE"}[1m]))` | kube-state-metrics | 集群装了 kube-state-metrics | 唯一不依赖 AS 抓取接线的 `as_*` 无关面板；崩溃循环 ≠ 过载 |
| 15 | Service 可用端点数 | `sum by (service) (kube_endpoint_address_available{namespace=~"$AS_NAMESPACE"})` | kube-state-metrics | 同上 | 路由状态，非连接池、非容量 |

### 1.2 `sip-signaling.json`

| # | 面板 | 指标 / 表达式要点 | 数据来源 | 前置条件 | 口径提醒 |
|---|---|---|---|---|---|
| 1 | SIP 响应速率（按 use_case + status_class） | `sum by (use_case, status_class) (rate(as_sip_responses_total[5m]))` | AS `/metrics` | 抓取接线 + 生产无生产者 | **没有入腿/出腿维度**：仓库无 `direction` label，不拆不编造 |
| 2 | 响应状态类分布 | `sum by (status_class) (rate(as_sip_responses_total[5m]))` | AS `/metrics` | 同上 | 487 属正常取消；404/603 是判决结果 |
| 3 | 关注响应码计数 403 / 404 / 603 / 502 | 4 个查询按 `status_code` 精确过滤 + `increase(...[5m])` | AS `/metrics` | 同上 | **403** 入腿未授权；**404 / 603 是判决结果、属预期行为**；**502** 是下游非 2xx 的统一映射（透传集合 {408,480,486,503,504} 之外）—— 口径证据见 [`../../product/compliance-matrix.md`](../../product/compliance-matrix.md) §3 |
| 4 | 按规则的判决命中速率 | `sum by (rule) (rate(as_rule_hits_total[5m]))` | AS `/metrics` | **无生产者 → 预期无数据** | 绝对阈值即伪装的容量数字，禁止 |
| 5 | 告警状态（firing / pending） | `count by (alertname, severity) (ALERTS{alertstate="firing"\|"pending"})`，`instant: true` | Prometheus 计算序列 | **需 Alertmanager + 已加载 `as-alerts.yaml`** | 有数据 ≠ 规则可触发（见 `deploy/alerts/README.md` §Metric contract）；处置见 [`../alert-response-matrix.md`](../alert-response-matrix.md) |
| 6 | 会话与 draining 联动 | `as_active_calls`（左轴）+ `as_downscale_removable`（右轴，右轴 override `max: 1`） | AS `/metrics` | 抓取接线 | 「都为 0 却持续不下」= draining 未收敛（`ASDownscaleBlocked`） |
| 7 | 各用例失败响应占比 | 按 `use_case` 拆分的 `ASHighErrorRatio` 同口径比率 | AS `/metrics` | 抓取接线 + 生产无生产者 | 比率，非容量；不画阈值线 |

> **为什么没有「入腿 / 出腿」面板**：交付要求提到入腿/出腿响应速率，但 `as_sip_responses_total` 的 label 只有 `use_case` / `status_class` / `status_code`（`metrics.py` 的 `_LABEL_*` 常量），**不存在** `direction` 之类的标签；双腿 B2BUA 的两腿区分是产品内部结构（两腿独立 Call-ID），当前没有对应指标 label。因此**不建面板、也不编造 label**，补齐路径见 §4。

---

## 2. 前置条件与接线现状

| 需要什么 | 当前状态 | 证据 | 补齐方式建议（只写建议，本交付不改 chart） |
|---|---|---|---|
| AS `/metrics` 抓取 | ❌ **未接线**。Pod 模板无 `prometheus.io/scrape` 注解（唯一注解是 `checksum/config`）；chart 内无 ServiceMonitor、无 PodMonitor | `deploy/helm/templates/deployment.yaml`；`deploy/helm/templates/` 全目录 grep `prometheus.io/scrape` / `ServiceMonitor` / `PodMonitor` 无命中；`deploy/alerts/README.md` §Scrape wiring status | 二选一：① Pod 模板加 `prometheus.io/scrape` + `prometheus.io/port`（端口名 `health-http`，`health.port` 默认 8080）注解；② 加一个 `PodMonitor`/`ServiceMonitor` 指向 `health-http`。属 chart 工作，需另一次改动 |
| OTLP 导出后端 | ❌ 未配置。`telemetry.otlpEndpoint` 默认 `null`，此时 sink 为 `NoOp`；即使配上 endpoint，exporter 默认仍是 `NoOpExporter` | `deploy/helm/values.yaml`（telemetry 段）；`deploy/alerts/README.md` §Metric contract | 部署侧指向真实 OTLP collector。**注意：这只影响 `as_telemetry_dropped_total` 是否有数据，不影响 `/metrics` 文本导出** |
| `$AS_NAMESPACE` 替换 | ⚠️ 看板用 Grafana 模板变量 `AS_NAMESPACE`（`type: custom`，默认值 `as-prod`）；告警规则文件里是字面占位符 `$AS_NAMESPACE` | `deploy/alerts/as-alerts.yaml` 文件头；本目录两份 JSON 的 `templating.list` | 导入后在看板变量里改成客户命名空间；告警侧用 `envsubst` 或 `PrometheusRule` 模板在加载时替换。**一个命名空间 = 一套完整系统**（REQ-NF-9），这也是所有 kube-state-metrics 选择器的隔离边界 |
| kube-state-metrics | ⚠️ **集群侧提供，本仓库与 chart 都不安装**。未安装 → 面板 2 / 3 / 14 / 15 无数据 | `deploy/alerts/README.md` §Kubernetes standard series | 由运维方在集群安装；本看板不依赖 chart 变更 |
| cAdvisor / kubelet 指标 | ⚠️ 集群侧提供。面板 12 / 13 依赖 `container_cpu_usage_seconds_total` / `container_memory_working_set_bytes` 及 `namespace` / `pod` / `container` 标签 | 同上 | 若集群在 relabel 阶段丢弃了 `container` 标签，面板按 `pod` 聚合仍可用（看板不依赖 `container` 标签收窄） |
| Alertmanager | ⚠️ 集群侧提供。面板 5 依赖 `ALERTS` 序列，该序列由 Prometheus 依据已加载的规则计算 | `deploy/alerts/as-alerts.yaml`；`deploy/alerts/README.md` §Loading | 加载规则文件（`rule_files:` 或 `PrometheusRule`），并用 `promtool check rules` 校验 |

**看板自身不改变任何接线状态**：在 §2 第 1 行闭环之前，`overview.json` 面板 1、4–13 与 `sip-signaling.json` 面板 1–4、6、7 都**不会有数据**；本目录不把「未接线」描述成「已生效」。

---

## 3. 导入步骤

1. **Grafana UI 导入**：`Dashboards → New → Import → Upload JSON file`，分别上传 `overview.json` 与 `sip-signaling.json`。导入时 Grafana 会提示选择数据源，选 Prometheus 实例即可；`uid` 已固定（`as-overview` / `as-sip-signaling`），重复导入会覆盖同一份，避免产生重复副本。
2. **改命名空间变量**：导入后打开看板 → 右上角 Dashboard settings → Variables → `AS_NAMESPACE`，把默认值 `as-prod` 改成实际客户命名空间。也可在 URL 上用 `?var-AS_NAMESPACE=<ns>` 临时覆盖。两个 `as_*` 之外的（kube-state-metrics / cAdvisor）查询都走这个变量。
3. **数据源变量**：`templating` 里的 `datasource` 变量（`type: datasource`, `query: prometheus`）会自动列出实例；所有面板的 `datasource` 字段引用 `${datasource}`，因此多 Prometheus 实例场景下切换一次即可全局生效。
4. **provisioning 目录放置**（推荐用于交付环境，可版本化）：
   ```yaml
   # grafana/provisioning/dashboards/as.yaml（示例，本仓库不提供该文件）
   apiVersion: 1
   providers:
     - name: as
       orgId: 1
       folder: AS
       type: file
       disableDeletion: false
       updateIntervalSeconds: 60
       options:
         path: /etc/grafana/provisioning/dashboards/as
   ```
   把两份 JSON 放进 `path` 指向的目录，Grafana 会按 `uid` 幂等加载（`updateIntervalSeconds` 到期自动刷新）。**provisioning 只解决「看板存在」，不解决 §2 的抓取接线。**
5. **导入后自检**：面板 2 / 3 / 14 / 15 有没有数据 → 判断集群是否装了 kube-state-metrics；面板 1 / 4 有没有数据 → 判断抓取接线是否闭环；面板 9 / 3（SIP 侧）**无数据是预期结果**（无生产者），不是导入失败。

---

## 4. 刻意不做的面板及原因

| 不做什么 | 原因 | 何时可做 |
|---|---|---|
| **Diameter Sh 相关面板**（含占位面板） | **N/A，不是 defer。** `AGENT.md` §2 明确不做 Sh；评审 **G-P0-4** 要求移除 Sh 面板与告警，**G-P2-3** 要求删除 `sh-interface.json` 文件项 | **永不**（除非出现新需求 + 新 ADR）。若有人再要求加 Sh 面板，那是新需求，不是本看板的缺口 |
| **时延 P50 / P95 / P99、ISC 往返时延、SIP 处理耗时** | 仓库**没有** histogram / summary：`MetricKind` 只有 `COUNTER` / `GAUGE`，注册表里没有任何时延序列（`metrics.py`；`docs/product/ne-datasheet.md` §5 明确「当前没有任何时延类 KPI」）。`histogram_quantile` 会永远指向空序列 —— 建了就是**假面板**，比没有更糟 | 先在 `telemetry/metrics.py` 加时延仪器（histogram 或 summary）→ 真实 SIP 路径上有生产者 → 抓取接线闭环。**且**任何绝对时延门限仍受 O1 约束：相对回退可以说，「必须在 N ms 内应答」在 M6 实测前不能说 |
| **容量面板**（CPS / 并发会话 / 每 Pod 负载上限 / HPA 目标） | **O1 未裁决**，M6 实测前禁止发布任何容量数字（`AGENT.md` §2；`deploy/helm/values.yaml` autoscaling 段全部留空并注明「填入值必须来自 M6 实测」）。`as.capacity` 组刻意不存在 | O1 由维护者基于 M6 真实 socket 实测裁决后，按实测值新建，**不得凭直觉写** |
| **入腿 / 出腿响应速率**（按 direction 拆分） | `as_sip_responses_total` 只有 `use_case` / `status_class` / `status_code` 三个 label，**不存在** `direction`。编一个 label 就是让看板永远无数据 | SIP 适配层在真实响应路径上写入时新增 `direction`（或等价）label，且同步更新 `metrics.py` 契约表与 `deploy/alerts/README.md` |
| **规则命中异常面板**（阈值线 / 绝对上限） | `as_rule_hits_total` **无任何调用方**，序列从不被写入；且绝对阈值就是伪装的容量数字 | ① 决策路径接上真实生产者；② 异常口径改为相对自身滚动基线的**相对**变化。两个条件都满足才可加 |
| **会话泄漏面板**（用 as_active_calls 当基线） | 没有「合法在途呼叫数」这个数 —— 那正是 O1。把它当基线就是发明容量数字 | O1 裁决给出合法在途量，或导出「会话开启 / 关闭」成对计数使泄漏成为**比率** |
| **连接池 / 连接数面板** | 计划文档 2.1 原文提到「连接池」，但仓库**没有导出任何连接池或连接数指标**，Redis / PostgreSQL 客户端连接数无 series。面板 15（Service 可用端点数）是集群侧最接近的替代物，只说明路由状态 | 状态存储客户端导出连接相关 gauge，且与 `deploy/alerts/README.md` 契约表同步 |
| **TLS 证书到期面板** | 该指标不存在（`as_tls_certificate_expiry_seconds` 只是命名约定表里的示意名，代码里没有这个常量，也没有生产者） | SIP 传输层按 `tls.secretName` 导出到期 gauge，走 ADR-0016 热轮换路径刷新，且抓取接线闭环 |
| **配置漂移 / 回滚面板** | config-service 未导出相关 series。`ASConfigDrift` / `ASConfigRollbackTriggered` 只出现在 `deploy/helm/templates/NOTES.txt` —— **NOTES.txt 里出现名字不等于有指标**（`../runbook-l2.md` §8 第 6 项） | config-service 把漂移 / 回滚事件 series 接入同一抓取通路 |
| **CDR / 计费 / 媒体（RTP / 转码）面板** | **N/A，不是 defer。** ADR-0017 不做 CDR / 计费，ADR-0004 无媒体面 —— 没有可观测的对象 | **永不**（新需求 + 新 ADR 另算） |

---

## 5. 指标契约与变更纪律

- **唯一权威**：`platform/src/as_platform/telemetry/metrics.py`。本看板只使用其中定义的 **6 个** `as_*` 指标：`as_active_calls{use_case,pod}`、`as_downscale_removable{use_case,pod}`、`as_state_store_available{use_case}`、`as_sip_responses_total{use_case,status_class,status_code}`、`as_rule_hits_total{rule}`、`as_telemetry_dropped_total{use_case}`。权威说明与逐项生产者核对见 [`../../../deploy/alerts/README.md`](../../../deploy/alerts/README.md) §Metric contract。
- **非 `as_*` 指标**（kube-state-metrics / cAdvisor / `ALERTS`）由**集群或 Prometheus** 提供，不由本仓库产生；选择器纪律与 `as-alerts.yaml` 一致：只用 `namespace=~"$AS_NAMESPACE"`，**不按 `label_*` 收窄** —— kube-state-metrics 只有配置了标签白名单才会暴露 `label_*` 系列，那是集群侧设置，chart 不能假设。
- **`$AS_NAMESPACE` 只出现在 kube-state-metrics / cAdvisor 选择器里**。`as_*` 序列自身的 label 只有上表那些（**没有 `namespace`**），给它加命名空间匹配器会在抓取配置未注入该 label 时让查询恒为空。`as_*` 的实例归属由 `pod` label 识别。
- **改名必须同一次改动同步**：规则与看板都依赖指标名。改名若不同步，规则会**静默停止匹配** —— 那比没有规则更糟。因此任何指标改名必须在**同一次提交**里更新：`metrics.py` → `deploy/alerts/README.md` 契约表 → `as-alerts.yaml` → **本目录两份 JSON** → `docs/product/ne-datasheet.md` §5 → `docs/operations/alert-response-matrix.md`。
- **新增指标必须先有生产者**：写面板前先 grep 指标名并读写入点。只有启动探针、测试 harness 或完全没有调用方的指标，面板只能是「预期无数据」（面板 9 / SIP 面板 4 即属此类），且必须在 `description` 里写明原因。
- **阈值只在一处维护**：面板**刻意不画**告警阈值线。所有门限写在 `deploy/alerts/as-alerts.yaml`，其 `description` 已注明「不是容量指标」。看板与规则两处各画一次就会漂移。
- **不承诺未生效的东西**：抓取接线未闭环（§2 第 1 行）这一事实，必须与看板一起交付，不得在客户材料中把 `as_*` 规则或面板描述为「已在生产生效」。

---

## 6. 维护与校验

**JSON 结构校验**（两份文件都必须通过）：

```sh
python3 -c "import json; [json.load(open(f)) for f in ['docs/operations/grafana-dashboards/overview.json','docs/operations/grafana-dashboards/sip-signaling.json']]"
```

**导入前建议的最小自检**（不依赖 Grafana 实例）：

1. 上面的 JSON 解析通过（语法层面）；
2. 每个 panel 都有 `id` / `type` / `title` / `gridPos` / `datasource` / `targets` / `fieldConfig` / `options`；
3. `targets[].expr` 里出现的 `as_*` 指标名 ⊆ §5 的 6 个白名单，且对 `as_*` 只使用 `use_case` / `pod` / `status_class` / `status_code` / `rule` 这些真实存在的 label；
4. 全文不含 `histogram_quantile`、不含 Sh 相关面板标题、不含任何容量数字或门限线；
5. `templating.list` 里 `datasource` 与 `AS_NAMESPACE` 两个变量存在，且所有 PromQL 用变量而非硬编码命名空间。

**建议纳入 CI**：把第1 步的 `python3 -c` 作为最小门槛（与 `promtool check rules` 同级）；第 3、4 步的语义检查目前靠人工 review，若后续需要自动化可加一个只读校验脚本 —— 但**本交付不新增脚本文件**，以免与「只创建 3 个文件」的范围约束冲突。

**面板 review 纪律**：改面板前先问「这个指标有生产者吗」，答案是「没有」就不建面板（要建就必须写明「预期无数据」及原因）；任何新增面板都要在 `description` 里写清口径、**不是容量指标**的提醒（含量 / 比率的面板）与前置条件（JSON 无注释，说明只能写进 `description` 或本 README）。
面板口径与 `docs/product/ne-datasheet.md` §5/§6、`docs/product/compliance-matrix.md` §3、`deploy/alerts/README.md` 保持一致；不一致时以代码与上述权威文件为准，看板随之修正。术语纪律：产品名统一 **In-house IMS Application Server（文档暂用名）**；chart / 镜像 / OTel 服务名保持 `3rdparty-as`；`state-*` 指 bundled Redis / PostgreSQL（ADR-0026 Option E），HA 属客户侧（O5 / D3 未决）。