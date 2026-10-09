# 告警-动作对照表（Alert / Action Matrix）— In-house IMS Application Server（文档暂用名）

> **交付物**：**2.2 告警规则补强 + 告警-动作对照表**（[`../product-packaging-plan.md`](../product-packaging-plan.md) §1 第二批 2.2）。
> **规则唯一权威**：[`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml)（REQ-NF-14）。**阈值以规则文件为准**；本页只回答"看到这个告警，第一步做什么、什么时候叫人、要留什么证据"。
> **加载与校验**：[`../../deploy/alerts/README.md`](../../deploy/alerts/README.md)（`promtool check rules` / `make alert-check`）。
> **本册位置**：[`README.md`](README.md) §1 分层中的 L1 / L2 之上层 —— L1 给首响应，L2 给定界与取证，本页给**级别、动作、升级路径**。
>
> **状态：草稿，未验收。** 本页是**工程切片证据**，不构成验收结论：
> - **M5 工程关门 ≠ REQ 验收**；**M8 RC 就绪 ≠ 关门**（[`../acceptance/report.md`](../acceptance/report.md) §0）。
> - **e2e marker = 0**：完整呼叫 + 控制台端到端路径未落地；performance 仅 accept-all harness，**非业务判决路径**（G-P1-2）。
> - **E1 / E4 / E5 未验收**（生产栈 reSIProcate 行为、TLS 热轮换、状态外置），见 [`../product/ne-datasheet.md`](../product/ne-datasheet.md)。
> - **7.2d / M8 真实集群证据仍 blocked**（G-P1-10）：本页的每个命令都是**可执行动作**，**没有任何一条**在生产集群上跑过并留档。
>
> **⚠️ 当前告警面存在已知盲区**（详见 §3）：抓取接线缺口、e2e=0、M8 退出签字搁置、7.2d blocked。
> **零容量数字**：本页无 CPS / CAPS / BHCA / 并发上限 / 时延阈值 / 吞吐数字。O1 未裁决（[`../../AGENT.md`](../../AGENT.md) §2 / §6），容量类告警 defer 到 O1 裁决后新建 `as.capacity` 组。
> **范围之外**：不做 Diameter Sh / 不做 CDR 与计费 / 不做媒体（[`../../AGENT.md`](../../AGENT.md) §2）。本页无任何 Sh 相关告警。

---

## 1. 告警级别定义与升级路径

### 1.1 级别映射

Prometheus 的 `severity` 标签是规则里的**唯一级别来源**。P 级是值班视角的分级，两者按下表硬映射，不允许出现"同一条规则在两处写法不同"。

| Prometheus `severity` | 本文档级别 | 含义 | 首响应要求（流程要求，非时长承诺） |
|---|---|---|---|
| `critical` | **P1** | 业务不可用或在途呼叫无法维持 | **立即介入**，不排班等待；并行通知二线（L2）；一边处置一边取证，不要先查清再动手 |
| `warning` | **P2** | 状态偏离但业务尚未中断，或可自愈 | 当班处置；先按对照表走首查动作，命中"升级路径"任一条件即转 P1 处理 |
| `info` / 未定级 | **P3** | 记录与趋势观察 | 记录到值班日志，不需要立即动作；若持续或反复出现则按 P2 处理 |

> **本页不写分钟数。** 响应时限是现场 SLA 与客户约定的事，本仓库不承诺任何具体分钟数；上表只写流程纪律（`docs/product-packaging-plan.md` §0.2 缺口 9：SLA / EOL 策略尚未立项）。

### 1.2 升级路径

```text
值班 NOC（L1）
   │  命中对照表"升级路径"列的任一条件
   ▼
二线工程（L2）—— 定界、取证、必要时改配置
   │  需要裁决产品口径 / 动未决项（O1、O4、O5、D3、D5）/ 推翻既有裁决
   ▼
维护者 / 架构
   │
   ▼
客户侧对接人（仅当归属落在对端：S-CSCF / HSS / S-SBC / 客户 PKI / 客户网络）
```

- **L1 → L2**：见 §2 每行的"升级路径"列；[`runbook-l1.md`](runbook-l1.md) §4 给了完整求助证据清单。
- **L2 → 维护者**：需要裁决口径或改未决项时。L2 **不得**自行把未决项当成已解决（[`../../AGENT.md`](../../AGENT.md) §15）。
- **→ 客户侧对接人**：定界结论落在对端时。AS 侧**只有**自己的日志、指标与配置版本；对端链路（S-CSCF → S-SBC 触发段、S-SBC → AS trunk 段）的取证**必须**对方配合（[`runbook-l2.md`](runbook-l2.md) §3、[`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3/§4）。
- **AS 侧证据不足时的纪律**：无证据**不得先行定界**。缺证据就把缺口写进求助单，不要用推测结论替代。

---

## 2. 告警-动作对照表（主表）

逐条覆盖 `as-alerts.yaml` **全部 10 条规则**：`as.call-path` 原有 5 条 + 2026-10-10 新增 5 条（`as.runtime` 3 条、`as.platform` 2 条）。
所有阈值均为**既有告警阈值或状态条件**，**不是容量指标**。

### 2.1 `as.call-path` — 原有 5 条（本次未改动）

| # | 告警 | 级别 | 触发条件（表达式语义） | 首查动作 | 处置动作 | 升级路径 | 回退 / 止损 | 需留证据 | 当前可触发性 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **`ASHighErrorRatio`** | P2 `warning`<br/>`signalling` | 5xx 与**非 487 的** 4xx 之和 ÷ 全部 SIP 响应 > **1%**，持续 **10m**。分母 `clamp_min(..., 1)` 避免零样本除零；**487（主叫取消）被显式排除**，属正常行为 | 1) 确认 `as_sip_responses_total` **是否真有样本**（`kubectl -n <ns> port-forward deploy/<release>-<use-case> 8080:8080` 后 `curl -s localhost:8080/metrics \| grep '^as_sip_responses_total'`）<br/>2) 无样本 → **不要**判定为故障，先看抓取接线<br/>3) 有样本 → 按 `status_class` / `status_code` 拆开看是哪一类 | 先分清判决类与故障类：404 = 无匹配规则、603 = 策略拒绝，**都是预期判决**（[L2 §4.3](runbook-l2.md)）。确有 5xx 再查 Redis 可达性、S-SBC 侧拒绝原因、决策模块异常 | 有真实样本且比率持续升高 → L2（[L2 §4.3](runbook-l2.md) / [L2 §4.4](runbook-l2.md)）；落点在 S-SBC → 客户侧对接人 | 业务侧止损：按号段 / 百分比切 runtime override 放行下一环节（ADR-0021）；AS 侧**不主动摘在途呼叫**（摘流是对方动作） | 表达式求值时间序列 + `status_code` 分布 + Call-ID（跨腿两腿 Call-ID **不同**，两个都留）+ 同期 `helm history` / 变更单 revision | **不可触发。** 唯一写入点是启动时一次性探针 `AS_M5_PROBE_SIP_STATUS`（`__main__.py:_apply_m5_metrics_probes`），生产 on-prem 不设；产品 SIP adapter 每次响应都调用的路径待 M7 |
| 2 | **`ASTelemetryDropped`** | P2 `warning`<br/>`observability` | `as_telemetry_dropped_total` 在 **15m** 窗口内 `increase` ≥ **50**，持续 **15m** | 1) 确认是否配置了 OTLP 端点（chart `telemetry.otlpEndpoint`，默认 `null`）<br/>2) 未配置 → 该序列**本就不产生**，不是故障<br/>3) 已配置 → 看后端可达性与队列日志 | 丢遥测**设计上可接受**，对呼叫路径施加背压**不可接受**；持续丢弃通常意味着后端不可达或过慢。先确认呼叫路径是否受影响，再修导出链路 | 已配置后端却持续丢弃 → L2；影响面扩到呼叫路径 → 按 P1 处理 | 无需业务止损；必要时**静默**关闭导出（不阻塞呼叫路径，ADR-0005） | `/metrics` 片段 + 后端可达性证据 + 丢弃量与窗口 | **不可触发（默认配置下）。** 仅当 `OTEL_EXPORTER_OTLP_ENDPOINT` 非空才创建 `BoundedQueueSink`；且 exporter 默认 `NoOpExporter`，队列难以填满 |
| 3 | **`ASRestartLoop`** | P1 `critical`<br/>`runtime` | 单 Pod 容器重启次数 `increase(...[1m])` > **3**，`for: 0m` | 1) `kubectl -n <ns> describe pod <pod>`<br/>2) 取上一个容器日志：`kubectl -n <ns> logs <pod> --previous`<br/>3) 核对最近一次配置版本（`printenv CONFIG_VERSION`） | CrashLoop。先分清**反复重启**与**单次滚动**；反复重启按 P1 走，不等业务反馈 | 反复重启 / 涉及多个 Pod → L2（[L2 §4.6](runbook-l2.md) 的 config-service 段、§4.7 缩容段） | `kubectl -n <ns> rollout undo deploy/<release>-<use-case>`；镜像 / manifest 回退用 [`rollback-playbook.md`](rollback-playbook.md)（**已落盘**；但依赖对端配合，真实集群演练仍 blocked，G-P1-10） | `describe` 输出 + `--previous` 日志 + `CONFIG_VERSION` + 变更单 revision（避免把"没查"当成"已排除"） | **可触发（唯一无配置前置条件的一类）。** 数据源是集群提供的 kube-state-metrics；只需集群装了 KSM |
| 4 | **`ASCallStateStoreUnavailable`** | P1 `critical`<br/>`state` | `min by (use_case) (as_state_store_available) == 0`，持续 **2m**。二进制可达性状态 | 1) 读 `/metrics` 确认序列**存在且为 0**（序列不存在 ≠ 0，见下）<br/>2) 查 Redis Pod：`kubectl -n <ns> get pods -l app.kubernetes.io/component=state-redis`<br/>3) 查 Sentinel / failover 状态 | 会话、dialog、反诈速率窗口状态全在 Redis（ADR-0002 / ADR-0007）→ 在途呼叫无法维持、新判决失去计数器。按 P1 立即处置 | **立即** L2。不等 | 恢复前**不要**让 AS 继续承接新呼叫；config-service 侧暂停变更单审批（治理动作，不动数据面） | `/metrics` 片段（证明是 0 不是 absent）+ Redis Pod 状态 + failover 窗口（未决 O5 / D3）+ 受影响 use_case 列表 | **可触发，前提 `REDIS_URL` 已配置**：此时 metrics 循环真实 `PING` Redis 并写序列。`REDIS_URL` 为空时**序列不存在（不是 0）**，规则永不触发 |
| 5 | **`ASActiveCallsSurge`** | P2 `warning`<br/>`signalling` | 每 `use_case` 当前 `as_active_calls` > 其自身 **30m 滑动平均的 1.3 倍**，持续 **10m**。**相对变化**，构造上不含绝对呼叫数 | 1) 先看**是否有变更 / 摘流 / 上游动作**（最常见原因）<br/>2) 对比同期 `ASHighErrorRatio` 是否同时上升<br/>3) 检查 `AS_M5_SIMULATED_ACTIVE_CALLS` 是否被误设 | 判定为「**流量形态变了**」，不是故障本身。确认是业务变更引起就记录并观察；无对应变更再深入 | 伴随错误率上升或状态存储告警 → L2（转 P1 处理）；有对应变更 → **不升级**，记录即可 | **不得**据此推断容量上限或临时封顶。真实负载异常用 M6 harness 与内部测量排查 | 两个时间窗的 `as_active_calls` 曲线 + 同期变更记录 + 是否有模拟值介入 | **序列总是产出**（`__main__.py` metrics 循环无条件写），但取值依赖 SIP 运行时的 dialog 事件；无流量或计数恒 0 时不触发。**另见 §3 抓取接线缺口** |

### 2.2 `as.runtime` — 2026-10-10 新增 3 条

| # | 告警 | 级别 | 触发条件（表达式语义） | 首查动作 | 处置动作 | 升级路径 | 回退 / 止损 | 需留证据 | 当前可触发性 |
|---|---|---|---|---|---|---|---|---|---|
| 6 | **`ASPodNotReady`** | P1 `critical`<br/>`runtime` | 该 Pod 的 `Ready` 条件（`condition="true"`）为 0，持续 **5m**。就绪 = 进程在**拒新工作** | 1) `kubectl -n <ns> get pod <pod> -o wide` 看 `READY`<br/>2) 访问 `/health/ready`：**503 = 正在 draining（正常摘流中）**，持续 503 才是异常<br/>3) `describe pod` 看 Events（探针失败 / 挂载 / 镜像） | 先区分**正常 draining** 与**卡住**：503 + 即将重建 = 正常滚动；503 长时间不变 = draining 不收敛，转 [L2 §4.7](runbook-l2.md) | draining 不收敛 / 反复 not-ready → L2；与 #3 同时出现 → 按 CrashLoop 处理 | `kubectl -n <ns> rollout undo deploy/<release>-<use-case>`；**不得**直接 SIGKILL 在途呼叫（先走 draining，ADR-0009） | `get pod -o wide` + `describe` Events + `/health/ready` 响应码与时间 + `CONFIG_VERSION` | **可触发（前提：集群装了 kube-state-metrics）。** 注意它**不区分组件**：AS 引擎 Pod、`state-redis`、`state-postgres`、`config-service` 都在同一 namespace，用 `pod` 名区分 |
| 7 | **`ASDeploymentReplicasUnavailable`** | P2 `warning`<br/>`runtime` | 同一 Deployment 的 `kube_deployment_status_replicas_available` < `kube_deployment_spec_replicas`，持续 **10m** | 1) 看告警里的 `deployment` 标签 —— 它可能指**用例 Deployment**、`state-redis` 或 `config-service`<br/>2) `kubectl -n <ns> get deploy <deployment>` + `describe`<br/>3) 与 #6 合并判断（通常是同一事件的两个视角） | 按上一步的组件分流：用例 Deployment → 查滚动 / 探针；`state-redis` → 查 Redis（与 #4 合并）；`config-service` → 查控制台链路 | 用例副本不足影响业务 → P1 转 L2；`state-redis` 不可用 → 与 #4 同路径立即升级 | 镜像 / manifest 回退：`helm -n <ns> rollback <release> <revision>`（回退路径与**配置回退是两件事**，不要混，[`runbook-l1.md`](runbook-l1.md) §3.2） | `deployment` 名 + `get deploy` 的 `READY/AVAILABLE` + ReplicaSet 事件 + `helm history` 当前 revision | **可触发（前提：KSM）。** 选择器**按 namespace 限定**，故也覆盖 `state-redis` 与 `config-service` 两个 Deployment |
| 8 | **`ASDownscaleBlocked`** | P2 `warning`<br/>`runtime` | 同一 `pod`/`use_case` 上 `as_downscale_removable == 0` **且** `as_active_calls == 0`，持续 **30m**。ADR-0010 的 guard 只有两个拦截理由：**有在途呼叫**、**已在 draining** → 两者都排除后只剩「**draining 卡住**」 | 1) `curl -s localhost:8080/metrics \| grep -E '^as_(downscale_removable\|active_calls)'` 确认两个序列<br/>2) 看该 Pod `/health/ready` 是否长期 503<br/>3) 与 #6 合并：同一 Pod 上大概率同时出现 not-ready | 确认 draining 未收敛：在途呼叫归不了零，或 `preStop` / SIGTERM 后进程未退出。按 [L2 §4.7](runbook-l2.md) 处置 | 持续 30m 以上不收敛 → L2；涉及多 Pod 或影响发布窗口 → 立即升级 | **不得**直接删 Pod 或 SIGKILL——先走完 draining；确认呼叫归零后 `kubectl -n <ns> delete pod <pod>`（会触发 `preStop sleep` + SIGTERM） | 两个序列的时间序列（证明是同一 `pod`/`use_case`）+ Pod 事件 + 是否处于变更窗口（`helm history` / 变更单） | **序列总是产出**（metrics 循环无条件写，不依赖 OTLP），但**取值依赖真实 SIP dialog 活动** —— 无流量时不触发。**另见 §3 抓取接线缺口** |

### 2.3 `as.platform` — 2026-10-10 新增 2 条

| # | 告警 | 级别 | 触发条件（表达式语义） | 首查动作 | 处置动作 | 升级路径 | 回退 / 止损 | 需留证据 | 当前可触发性 |
|---|---|---|---|---|---|---|---|---|---|
| 9 | **`ASStatefulSetUnavailable`** | P1 `critical`<br/>`state` | 某 StatefulSet 的 `kube_statefulset_status_replicas_ready` < `kube_statefulset_replicas`，持续 **5m**。chart 内即**治理库 PostgreSQL**（ADR-0008） | 1) 确认告警里的 `statefulset` 名（预期是 `<release>-postgres`）<br/>2) `kubectl -n <ns> get sts <name>` + `describe`<br/>3) 查最近的 migrate Job：`kubectl -n <ns> get jobs \| grep config-migrate`<br/>4) 在治理库主机 `pg_isready` | 治理 PG 持有配置版本、变更单与 append-only 审计链 → **配置无法审批与分发**，控制台变更单流程停摆。按 P1 处置 | **立即** L2 → 维护者（涉及数据面恢复） | 配置面止损：暂停变更单审批；**不要**在库上直接 UPDATE 配置表（配置不走 GitOps，也不允许运维直接改库，`AGENT.md` §2 / ADR-0006）。恢复手段见 [`backup-restore.md`](backup-restore.md)（**已落盘**；但真实集群 restore drill 记录仍 blocked，G-P1-10） | `statefulset` 名 + `describe` Events + migrate Job 状态 + `pg_isready` 输出 + 最近一次备份时间（若声称可恢复，必须有备份记录） | **可触发（前提：KSM）。** 内建 PG 是**单副本、非 HA**；HA 由客户拥有（Patroni / 云 RDS，或改用外部 `postgres.host` + `stateStores.enabled=false`）。单副本是设计事实，**不是**容量结论 |
| 10 | **`ASServiceEndpointsAbsent`** | P2 `warning`<br/>`state` | 某 Service 的 `kube_endpoint_address_available` 之和为 **0**，持续 **5m** → selector 匹配不到任何 Ready Pod，客户端无法路由。chart 内覆盖 `state-redis` 与 `config-service` 两个 Service | 1) 确认告警里的 `service` 名<br/>2) `kubectl -n <ns> get endpoints <service> -o yaml`（ENDPOINTS 为空即证实）<br/>3) `get pods -l app.kubernetes.io/component=<component>` 对齐 Deployment 与 Pod | 与 #4 区分：#4 是「AS 连不上 Redis」，本条是「**Service 根本没有后端**」（Pod 不存在 / 不 Ready / 正在滚动）。先看 Pod，再看 Service 选区是否匹配 | 影响 `state-redis` → 与 #4 同路径立即升级；影响 `config-service` → 控制台不可用，转 L2（[L2 §4.6](runbook-l2.md)） | 回到 Pod 侧恢复：先修 Pod / 探针 / 滚动，不要直接改 Service selector（selector 是 Deployment 契约，改了会静默失配） | `service` 名 + `get endpoints` 输出 + 对应 Pod 的 `get pods` / `describe` + 是否处于滚动窗口 | **可触发（前提：KSM）。** 是与 #4 **不同**的失效模式：配置正确但 Service 无后端 |

### 2.4 使用本页的三条纪律

1. **无数据 ≠ 健康，也 ≠ 故障。** §3 的盲区表说明大多数情况下你拿到的是 `no data`。**先判断"有没有数据"，再判断"数据说什么"**。
2. **不把比例型阈值当容量。** `1%`、`1.3 倍`、`3 次/分钟`、`50 事件/15m` 都是**既有告警阈值**，用来在**没有容量基线**时先发现问题；**没有一条是 O1 的答案**。
3. **定界要留证据。** 缺证据就把缺口写进求助单，不要用推测结论替代（[`runbook-l1.md`](runbook-l1.md) §4 的求助证据清单）。

---

## 3. 无告警覆盖的盲区

这张表比主表更重要：**它说明"现在还没有覆盖什么、为什么没覆盖、拿什么顶、什么条件能补上"**。运维交接时必须一起交接。

| 盲区 | 原因 | 当前替代手段 | 补齐出口条件 |
|---|---|---|---|
| **时延 / 处理时长无告警** | 仓库**没有任何 histogram 或 summary** —— `MetricKind` 只有 `COUNTER` / `GAUGE`（[`metrics.py`](../../platform/src/as_platform/telemetry/metrics.py)）。没有分布就没有分位数，`histogram_quantile` 永远取不到样本 | 人工比对 SIP 报文时间戳（L2 抓包对齐，[`runbook-l2.md`](runbook-l2.md) §3） | ① 在 `telemetry/metrics.py` 加时延仪器；② 真实 SIP 路径（M7，非启动探针）有生产者；③ 抓取接线补齐。**注意**：即使用量延比例或相对回归阈值可以，但**绝对时延门限**同样受 O1 纪律约束（O1 未裁决，AGENT.md §2） |
| **ISC 超时无告警** | 同上：**没有超时计数器，也没有时延**被导出。且 ISC 触发的所有权在 S-CSCF 侧 | 双方报文对齐取证（L2）；联调期人工核对 | ① SIP adapter 导出 ISC 超时计数（带真实生产者）；② 与运营商 S-CSCF 侧**协商清楚"超时由谁判定"**（归属问题，先解决再写规则） |
| **会话泄漏无告警** | 没有"应有的在途呼叫数"可作泄漏基线。`as_active_calls` 是绝对量纲的 gauge，拿它当泄漏阈值就是**提前发明的容量数字**（AGENT.md §2 禁止） | `ASDownscaleBlocked`（#8）覆盖**相邻**失效模式：draining 卡住。真正的"呼叫只开不关"目前只能靠投诉 / Call-ID 轨迹（ADR-0017）反查 | 二者之一：① O1 从 M6 实测裁决出合法在途呼叫数；② 导出「会话开启 / 会话关闭」成对计数，使泄漏成为**比率**而非阈值 |
| **TLS 证书到期无告警** | **指标不存在。** `as_tls_certificate_expiry_seconds` 只作为命名示例出现在 `deploy/alerts/README.md` 的命名约定表，代码里**没有**这个常量，也没有生产者（该示例已在本轮同步中改为真实指标名） | 客户 PKI 日历 + 客户侧到期跟踪；轮换本身走配置热更新（ADR-0016，[`runbook-l1.md`](runbook-l1.md) §3.4） | SIP transport 按 `tls.secretName` 导出到期 gauge、在热轮换路径上刷新，且抓取接线补齐。**告警对象是客户 PKI 日历，不是重启触发器** —— 轮换绝不重启进程、绝不丢在途呼叫（AGENT.md §13）。**E4 / REQ-S-2 / REQ-S-3 当前无实验室证据** |
| **配置漂移 / 回滚无告警** | config-service 未导出漂移与回滚事件序列。`ASConfigDrift` / `ASConfigRollbackTriggered` 两个名字**只出现在 `templates/NOTES.txt`**，规则文件里没有 —— 按名去告警系统查会一无所获（[`runbook-l2.md`](runbook-l2.md) §8 第 6 项） | 直接查变更单状态机（[`runbook-l1.md`](runbook-l1.md) §3.3）+ 各副本 `CONFIG_VERSION` 一致性 | config-service 导出漂移 / 回滚序列到同一抓取路径 |
| **规则命中异常无告警** | `as_rule_hits_total` **无任何调用方**：`record_rule_hit` 定义了但 `src/` 里无人调用，序列永不写 | 无 | ① 决策路径接上生产者；② 异常阈值定义为**相对自身滚动基线**，而不是"命中数不得超过 N"（后者是伪装的容量数字） |
| **`as_*` 指标在标准部署下采不到** | ⚠️ **最大盲区。** Pod 模板**无** `prometheus.io/scrape` 注解，chart 内**无** ServiceMonitor / PodMonitor（`deploy/helm/templates/` 全目录无命中）。`/metrics` 端点工作正常，但**没有任何采集器被接线到它** | 人工拉取：L1 §1 检查 4 的 `kubectl port-forward` + `curl` | chart 增加 Pod 注解或 `PodMonitor` / `ServiceMonitor`（属 chart 工作，**不在本交付物的改动范围内**）。**补齐前不得对外称 `as_*` 规则"已生效"** |
| **遥测丢弃告警在默认配置下不触发** | `OTEL_EXPORTER_OTLP_ENDPOINT` 默认 `null` → 不创建 `BoundedQueueSink` → 序列不写；即便配置了，exporter 默认 `NoOpExporter`，队列难以填满 | 呼叫路径不受影响即无需处置（丢遥测设计上可接受，ADR-0005） | 配置真实 OTLP 后端并接入 collector。**这是配置问题，不是规则问题** —— 规则本身正确 |
| **SIP 失败率在默认部署下无样本** | `as_sip_responses_total` 的唯一写入点是**启动时一次性探针** `AS_M5_PROBE_SIP_STATUS`，生产 on-prem 不设；产品 SIP adapter 每次响应都调用的路径待 M7 | 抓包对齐（L2 §3） | M7 接线完成 + 抓取接线补齐 |
| **没有测试兜底** | **e2e marker = 0**：完整呼叫 + 控制台端到端路径未落地；performance 仅 accept-all harness，**非业务判决路径**（G-P1-2） | kind 上的工程证据脚本（M5 / ISSU 缩容证据）——**是工程证据，不是现网证据** | M7 / M8 落地 e2e 层并把该层改为阻塞（AGENT.md §9） |
| **容量类告警（`as.capacity`）不存在** | **O1 未裁决。** M6 真实 socket 实测未完成，AGENT.md §2 / §6 禁止在实测前发布任何容量数字 | 异常负载用 `ASActiveCallsSurge`（#5）+ M6 harness 排查，**不得**用提前编造的数 | O1 由维护者基于 M6 实测结果裁决后，**新建** `as.capacity` 组，阈值取自实测 |
| **Diameter Sh / CDR / 计费 / 媒体告警** | **N/A，不是盲区。** 均为已决策的非目标（[`../../AGENT.md`](../../AGENT.md) §2；评审 G-P0-4 已移除 Sh 告警） | 不适用 | 无。若出现新需求，属新的 requirement + 新的 ADR，不是新告警 |

---

## 4. 阈值纪律

### 4.1 本页与 `as-alerts.yaml` 中每条阈值的分类

规则文件里**只允许**出现三类阈值，每条规则的 `annotations.description` 都要自证属于哪一类：

| 类别 | 含义 | 本页实例 |
|---|---|---|
| **比率（ratio）** | 分子分母同量纲，与系统规模无关 | `ASHighErrorRatio` 的 1%（分母做了 `clamp_min(..., 1)`） |
| **相对变化（relative change）** | 与该序列**自身**的历史基线比较，不含绝对目标 | `ASActiveCallsSurge` 的 1.3 倍（30m 滑动平均） |
| **状态条件 / 固定窗口计数（state / fixed-window count）** | 布尔可达性、可观测性，或固定窗口内的事件计数 | `ASCallStateStoreUnavailable`（== 0）、`ASRestartLoop`（> 3 次/1m）、`ASTelemetryDropped`（≥ 50 / 15m）、以及本次新增的 5 条全部（`Ready` 为 0、副本数比较、guard 状态、StatefulSet ready 副本、Endpoint 地址为 0） |

### 4.2 为什么绝对容量阈值被禁止

- **AGENT.md §2**：**M6 实测之前不发布任何容量数字**（CPS、并发）。
- **AGENT.md §6 / §15**：性能测试**只能用真实 socket**，绝不能靠驱动回调测；而 O1 未裁决前不能假设任何容量数字。
- **`docs/plan.md` §5.1**：O1 是最大的未决项，有独立的 M6 研究里程碑。
- **评审纪律**：G-P0-3 / G-P0-8 明确禁止容量类告警与容量承诺数字；G-P1-2 要求 e2e 覆盖。
- **规则文件与本页是同一纪律的两个载体**：[`deploy/alerts/README.md`](../../deploy/alerts/README.md) §"Why there is no capacity alert" 与本页 §4.1 必须一致。

### 4.3 加阈值前的三个问题

1. 这个数是**比率 / 相对变化 / 状态**吗？不是 → 停下来走 O1 + M6。
2. 它会随系统规模变化吗？会 → 它是绝对数 → 不合格。
3. 有人会在一年后把它当成"系统容量"引用吗？如果规则描述没写明"这不是容量指标" → 描述不合格，退回重写（这是新增规则的验收条件之一）。

---

## 5. 与其它文档的一致性检查清单

以下为自查清单。**勾选代表本次改动已逐条核对**，不代表任何一项已在生产验证。

**与 `runbook-l1.md` 的一致性**

- [x] **全部 10 条告警（3 个组：`as.call-path` 5 + `as.runtime` 3 + `as.platform` 2）**的级别、触发条件、L1 动作与 [`runbook-l1.md`](runbook-l1.md) §2 表**逐条一致**
- [x] `runbook-l1.md` §2 关于 **`REDIS_URL` 为空时序列不存在（不是 0）** 的纪律，本页 #4 采纳
- [x] `runbook-l1.md` §2 关于 **`AS_M5_PROBE_SIP_STATUS` 是启动时一次性探针** 的坑，本页 §3 与 #1 采纳
- [x] `runbook-l1.md` §2 关于 **`AS_M5_SIMULATED_ACTIVE_CALLS` 是证据用模拟值** 的边界，本页 #8 采纳
- [x] 巡检第 4 项「**Prometheus 里没有 ≠ 进程没产出**」的告警，本页 §3 盲区表展开为独立行
- [x] 抓取缺口与 [`runbook-l2.md`](runbook-l2.md) §8 第 5 项**同一口径**（Pod 无 scrape 注解、chart 无 ServiceMonitor/PodMonitor）
- [x] `NOTES.txt` 里的 `ASConfigDrift` / `ASConfigRollbackTriggered` **不存在于规则文件**——与 [`runbook-l2.md`](runbook-l2.md) §8 第 6 项一致
- [x] 新增 5 条告警已在 [`runbook-l1.md`](runbook-l1.md) §2 **补齐对应行**（含组标注 `as.runtime` / `as.platform`），逐条一致

**与产品文档的一致性**

- [x] 告警清单与 [`../product/ne-datasheet.md`](../product/ne-datasheet.md) §6 的**全部 10 条**逐条一致（触发条件摘要、severity/component、可触发性口径）
- [x] 判决口径与 [`../product/compliance-matrix.md`](../product/compliance-matrix.md) 一致：**404** = 无匹配规则、**603** = 策略拒绝，均为**预期判决**；透传集合 {408, 480, 486, 503, 504} 不因本告警改变
- [x] **487 被排除**于失败率之外（主叫取消属正常行为），与规则表达式一致
- [x] 归属判定口径与 [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3 / §4 一致；AS 侧只有自有日志 / 指标 / 配置版本
- [x] **零容量数字**：本页无 CPS / CAPS / BHCA / 并发上限 / 时延阈值 / 吞吐数字（§4 分类可自证）
- [x] **不含 Diameter Sh 告警**（G-P0-4 已移除；非目标，`AGENT.md` §2）
- [x] **不含 CDR / 计费 / 媒体告警**（非目标；出现即 N/A + 理由）
- [x] 命名纪律：产品名用「In-house IMS Application Server（文档暂用名）」；chart / 镜像 / OTel 服务名 `3rdparty-as` 不变

**规则文件自身的一致性**

- [x] `as-alerts.yaml` 原有 5 条规则的表达式 / 标签 / 注解**未被修改**（已用脚本对比 `HEAD` 版本逐字段校验通过）
- [x] 新增规则全部带 `severity` + `component` 标签、一行 `summary`、含"不是容量指标"自证的 `description`
- [x] kube-state-metrics 选择器一律使用 `$AS_NAMESPACE` 占位，无硬编码 namespace
- [x] 新增规则的指标**均已核实生产者**：`as_downscale_removable` / `as_active_calls`（metrics 循环无条件写）+ kube-state-metrics（集群提供，`ASRestartLoop` 已在用）
- [x] 未为**未导出**指标写任何规则（README 明文规则："Do not add PromQL rules for metrics that are not emitted"）
- [x] 文件头 SCOPE 注释已更新：说明新增了哪两组、为什么新增、为何仍无容量类告警，并声明**不是验收记录**

---

## 6. 未决与阻塞

| # | 项 | 类型 | 影响 | 归属 / 出口条件 |
|---|---|---|---|---|
| 1 | **抓取接线缺口**：Pod 无 `prometheus.io/scrape` 注解、chart 无 ServiceMonitor / PodMonitor | 阻塞 | 所有 `as_*` 规则（#1–#5、#8）在标准部署下**无数据**，看板同样不可用 | 需改 chart（Pod 注解或 `PodMonitor`）。**不在本次改动范围**；看板与抓取接线同属待办批次 |
| 2 | **O1 容量目标未裁决** | 阻塞 | `as.capacity` 组无法建立；一切绝对阈值被禁止 | 维护者基于 **M6 真实 socket 实测**裁决（[`../../AGENT.md`](../../AGENT.md) §2 / §15） |
| 3 | **时延 / ISC 超时类指标不存在**（无 histogram / summary） | 阻塞 | 交付物 2.2 中"ISC 超时"一项**无法以告警形式交付** | 需先加仪器 + 真实生产者 + M7 接线；ISC 超时还需与运营商 S-CSCF 侧协商超时判定归属 |
| 4 | **会话泄漏无判定指标** | 阻塞 | 交付物 2.2 中"会话泄漏"一项**无法以告警形式交付** | 需 O1 裁决合法在途呼叫数，或导出"开启 / 关闭"成对计数使其成为比率 |
| 5 | **证书到期无指标** | 阻塞 | 证书到期提醒只能靠客户 PKI 日历 | 需从 SIP transport 导出到期 gauge；且 **E4 / REQ-S-2 / REQ-S-3 当前无实验室证据** |
| 6 | **e2e = 0**（G-P1-2） | 阻塞 | 告警逻辑**没有端到端测试兜底**，只能靠静态评审 + kind 工程证据 | M7 / M8 落地 e2e 层并改为阻塞门禁 |
| 7 | **M8 退出签字搁置**（[`../plan.md`](../plan.md) §0） | 阻塞 | 本页所有动作**未在生产集群执行记录** | 维护者签字 |
| 8 | **7.2d / 真实集群证据 blocked**（G-P1-10） | 阻塞 | `rollback-playbook.md`、`backup-restore.md` **已落盘**，但其**真实集群演练 / restore drill 记录仍 blocked**，本页引用处已就地标注；本页的处置动作**未经真实集群演练** | 需要真实集群环境 + 对端（S-CSCF / HSS）配合 |
| 9 | **O5 / D3（Redis HA 未决）** | 阻塞 | `ASCallStateStoreUnavailable` 的 failover 窗口无定论 | 维护者裁决 Sentinel / HA 方案 |
| 10 | **`runbook-l1.md` §2 与 `ne-datasheet.md` §6 的告警清单同步** | **已解决** | 新增 5 条（`as.runtime` 3 + `as.platform` 2）已补入两处清单，三份文档的告警条目集合现与 `as-alerts.yaml` 一致（10 条 / 3 组） | 已闭合；后续新增规则仍须按 `deploy/alerts/README.md` §Adding a rule 第 8 条同步这两处 |
| 11 | **`ASRestartLoop` 选择器按 namespace 而非按 Pod 收敛**（既有规则，本次**未改**，仅报告） | 观察项 | 该规则会匹配命名空间内**任何** Pod 的重启（包括非 AS 工作负载）。与 REQ-NF-9「一个命名空间一套完整系统」在当前 chart 下等价，但若客户在同一命名空间部署了旁路工作负载，误报面会变大 | 需与维护者裁决：是否收窄为 `app.kubernetes.io/part-of=3rdparty-as`（依赖 KSM 的 label allowlist，集群侧设置）。**本次按纪律只在报告中提出，不擅自修改既有规则** |

---

## 7. 来源映射

| 本页章节 | 来源 |
|---|---|
| 状态块与免责 | [`../../AGENT.md`](../../AGENT.md) §2 / §6 / §9 / §15；[`../product-packaging-plan.md`](../product-packaging-plan.md) §0.3 与 §1 交付物 2.2；[`../reviews/product-packaging-plan-review-2026-10-09.md`](../reviews/product-packaging-plan-review-2026-10-09.md)（G-P0-3 / G-P0-4 / G-P0-8 / G-P1-2 / G-P1-10）；[`../acceptance/report.md`](../acceptance/report.md) §0 |
| §2 原有 5 条 | [`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml) `as.call-path`（表达式原文，**本次未改动**）；L1 动作取自 [`runbook-l1.md`](runbook-l1.md) §2，可触发性核实自 `platform/src/as_platform/__main__.py` 与 [`ne-datasheet.md`](../product/ne-datasheet.md) §6 |
| §2 新增 5 条 | 同文件 `as.runtime` / `as.platform`（2026-10-10 新增）；生产者核实：`platform/src/as_platform/telemetry/metrics.py`、`platform/src/as_platform/__main__.py:_start_metrics_loop`、`platform/src/as_platform/ops/downscale_guard.py`、`deploy/helm/templates/_helpers.tpl`、`deploy/helm/templates/state-{postgres,redis}.yaml`、`deploy/helm/templates/config-service-deployment.yaml` |
| §3 盲区 | [`runbook-l2.md`](runbook-l2.md) §8 坑位清单（第 4/5/6/9/10 项）；抓取缺口自核实：`deploy/helm/templates/` 全目录无 `prometheus.io/scrape` / ServiceMonitor / PodMonitor；[`../../deploy/alerts/README.md`](../../deploy/alerts/README.md) §Deferred alerts |
| §4 阈值纪律 | [`../../deploy/alerts/README.md`](../../deploy/alerts/README.md) §"Why there is no capacity alert"；[`../../AGENT.md`](../../AGENT.md) §2 / §6；`as-alerts.yaml` 文件头 SCOPE 注释 |
| §5 一致性核对 | [`runbook-l1.md`](runbook-l1.md) §1 / §2；[`runbook-l2.md`](runbook-l2.md) §4.3 / §4.4 / §4.6 / §4.7 / §8；[`../product/ne-datasheet.md`](../product/ne-datasheet.md) §6；[`../product/compliance-matrix.md`](../product/compliance-matrix.md)；[`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3 / §4；[`rollback-playbook.md`](rollback-playbook.md)、[`backup-restore.md`](backup-restore.md)、[`fault-demarcation.md`](fault-demarcation.md) |
| 验证口径 | `promtool check rules` / `make alert-check`（[`../../deploy/alerts/README.md`](../../deploy/alerts/README.md) §Loading、§Adding a rule；[`../../Makefile`](../../Makefile) `alert-check`） |
