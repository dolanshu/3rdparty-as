# L1 运维手册（NOC 日常与告警处置）— In-house IMS Application Server（文档暂用名）

> **读者**：L1 / NOC 值班。**不含**深度信令分析（见 [`runbook-l2.md`](runbook-l2.md)）。
>
> **证据口径（必读）**：本页**所有结论基于工程切片证据**。
> - **M5 工程关门 ≠ REQ 验收**；**M8 RC 就绪 ≠ 关门**（[`../acceptance/report.md`](../acceptance/report.md) §0）。
> - **e2e marker = 0**：完整呼叫 + 控制台端到端路径未落地；performance 仅 accept-all harness，**非业务判决路径**（G-P1-2）。
> - **模拟 `active_calls` 的证据边界**：缩容 / draining / 滚动升级的不掉呼叫证据来自 kind 上 `AS_M5_SIMULATED_ACTIVE_CALLS` 模拟，**真实 SIP 负载下不掉呼叫待 M7 / M8 验收**（G-P1-1）。
> - **零容量数字**：本页无 CPS / CAPS / BHCA / 并发 / 吞吐 / 时延 / 百分比容量（O1 未裁决）。表中出现的百分比与固定窗口计数是**既有告警阈值**，不是容量指标。
> - **原件保留**：本页是 [`../acceptance/`](../acceptance/) 下既有 runbook 的**归集与重组**，原文件**不删除、不移动、不改写**。每节末尾给出来源链接，证据原件在那边。

---

## 1. 每日巡检清单

前置：kubeconfig 已指向目标集群；命名空间按现场（本页示例用 chart 默认 `as-prod`，实际以 `helm get values` / 安装参数为准）。

| # | 检查项 | 命令 / 方法 | 期望结果 | 异常时跳转 | 依据 |
|---|---|---|---|---|---|
| 1 | Pod 状态与 ready | `kubectl -n as-prod get pods -l app.kubernetes.io/part-of=3rdparty-as` | 每个用例 Pod `Running` 且 READY 全为真；无 CrashLoop / 无 Pending | READY 不为真 → §4；重启 → §2 `ASRestartLoop` | 标签定义 `deploy/helm/templates/_helpers.tpl:55,71` |
| 2 | 健康端点 | 容器内探针已配置；人工核对用 `kubectl -n as-prod port-forward deploy/<release>-<use-case> 8080:8080` 后访问 `/health/live`、`/health/ready` | `/health/live` 200；`/health/ready` 200 | `/health/ready` **503** = 正在 draining（正常摘流中），见 §3.1；持续 503 → §4 | 端口来自 Helm `health.port`（`deploy/helm/values.yaml:281-282`）→ ConfigMap `AS_HEALTH_PORT`（`templates/configmap.yaml:58`）；路径来自 `values.yaml:286-303` |
| 3 | 配置版本一致性 | `kubectl -n as-prod exec deploy/<release>-<use-case> -- printenv CONFIG_VERSION` | 各副本 `CONFIG_VERSION` 相同且等于控制台当前生效版本 | 不一致 → §3.3；空值 = 实例尚未上报 → §4 | 命令原文见 `deploy/helm/templates/NOTES.txt:47-51`（由 config-service 灰度分发注入，ADR-0006） |
| 4 | 指标可用性 | `kubectl -n as-prod exec deploy/<release>-<use-case> -- curl -s :8080/metrics \| grep '^as_'`（端口来自 `health.port`；镜像内无 `curl` 时改用 `kubectl -n as-prod port-forward deploy/<release>-<use-case> 8080:8080` 后本地 `curl -s localhost:8080/metrics \| grep '^as_'`） | 能列出会话 / 判决相关 `as_*` 序列 | 列不出 → §4。**注意：chart 未接线抓取**（无 scrape 注解、无 ServiceMonitor），所以「Prometheus 里没有」不等于「进程没产出」 | 端点实现 `platform/src/as_platform/runtime/health.py`；⚠️ 缺口见 L2 §8 |
| 5 | ingress HTTPS 重定向 | `curl -I -H 'Host: <ingress-host>' http://ingress-nginx-controller.ingress-nginx.svc/` | **301 / 308**（经 ingress 的 HTTP 被重定向或拒绝） | 非 301/308 → §4；**empty reply（curl 52）视为未过关**，需修环境或换采证路径 | [`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md) 检查项 4；**port-forward HTTP 200 不能顶替此项** |
| 6 | Redis 可用性 | 指标 `as_state_store_available{use_case}`（方法同 #4） | `1` | `0` → §2 `ASCallStateStoreUnavailable` + §4；**序列不存在 ≠ 0**（未配 `REDIS_URL` 时不产出） | `deploy/alerts/README.md` §Metric contract |
| 7 | PostgreSQL 可用性 | 由平台侧在治理库主机执行 `pg_isready`（owner / 运维账号，非应用角色） | 接受连接 | 失败 → §4 | 角色与 DSN 口径见 §3.5 与 L2 §6 |
| 8 | 控制台可登录 | 浏览器访问控制台 HTTPS 入口，operator 登录 | 登录成功并可看到审批队列 | 失败 → §4；**不保存凭据**，不把会话 cookie 截图入档 | [`runbook-l2.md`](runbook-l2.md) §4.6 |

> ⚠️ **当前限制（如实标注）**：以上检查项在**真实生产集群上的执行记录当前 blocked** —— M4b-7.2d / M8 7.2d 仍为 **blocked**（`docs/product-packaging-plan.md` §0.3 第 1、3 条）。本页给的是**可执行动作**，**不得**据此在任何材料中写"已在生产验证"。同类地，L1 的证据底座是 kind / compose，**不是现网**。

---

## 2. 告警处置（L1 视角）

规则唯一权威：[`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml)（REQ-NF-14）；加载与校验见 [`../../deploy/alerts/README.md`](../../deploy/alerts/README.md)。**下表逐条覆盖该文件的全部 10 条规则、3 个组**（`as.call-path` 5 条 + `as.runtime` 3 条 + `as.platform` 2 条）。本表只做 L1 首响应，**升级路径**与定界见 [`alert-response-matrix.md`](alert-response-matrix.md)（已落盘；与本表逐条一致）。

| 告警 | 级别 / component | 一句话含义 | L1 动作 | 何时升级 L2 | 当前可触发性（自核实） |
|---|---|---|---|---|---|
| `ASHighErrorRatio` | `warning` / `signalling` | 5xx 与非 487 的 4xx 占全部 SIP 响应之比 > **1%**，持续 `10m`（**既有告警阈值，非容量指标**） | 记下时间窗；确认 `as_sip_responses_total` 是否真有样本；不要在无数据时判定为「故障」 | 有真实样本且比率持续升高 → L2（L2 §4.3 / §4.4） | **不可触发**：依赖 `as_sip_responses_total`，生产路径无数据生产者（唯一写入点是启动时一次性探针 `AS_M5_PROBE_SIP_STATUS`，生产 on-prem 不设） |
| `ASTelemetryDropped` | `warning` / `observability` | `as_telemetry_dropped_total` 在 `15m` 窗口内增量 ≥ **50**，持续 `15m`（**窗口内事件计数，非容量指标**） | 确认是否配置了 `telemetry.otlpEndpoint`；未配置则该序列本就不产生 | 已配置后端却持续丢弃 → L2 | **不可触发**：仅在配置了 OTLP 端点时才启用有界队列（chart 默认 `null`），且 exporter 当前为 `NoOpExporter` |
| `ASRestartLoop` | `critical` / `runtime` | 单 Pod 容器重启 **> 3 次 / 1 分钟**（**固定窗口存活信号，非容量指标**） | `kubectl -n as-prod describe pod <pod>` + 取上一个容器日志；核对最近一次配置版本 | 反复重启 / 涉及多个 Pod → L2 | **可触发（当前唯一无前置条件的一条）**：数据源是外部 **kube-state-metrics** 的 `kube_pod_container_status_restarts_total`，只要求集群装了 kube-state-metrics |
| `ASCallStateStoreUnavailable` | `critical` / `state` | `min by (use_case) (as_state_store_available) == 0`，持续 `2m`（**可达性状态条件，非容量指标**） | 立即升级 L2；AS 侧会话 / dialog / 反诈速率窗口状态都在 Redis | **立即**（critical，且在途呼叫无法维持） | **可触发（前提：`REDIS_URL` 已配置）**：此时真实 `PING` Redis 并写序列。`REDIS_URL` 为空时**序列不存在（不是 0）**，规则永不触发 |
| `ASActiveCallsSurge` | `warning` / `signalling` | 每用例当前 `as_active_calls` > 其自身 `30m` 滑动平均的 **1.3 倍**，持续 `10m`（**相对变化，构造上不含绝对呼叫数，不是容量指标**） | 判定为「流量形态变了」，先看是否有变更 / 摘流 / 上游动作；**不得**据此推断容量上限 | 伴随错误率上升或状态存储告警 → L2 | **序列总是产出**，但取值依赖 SIP 运行时的 dialog 事件；未启用该运行时或计数恒为 0 时不触发。另见 §1 #4 的抓取接线缺口 |
| `ASPodNotReady`（`as.runtime`） | `critical` / `runtime` | 该 Pod 的 `Ready` 条件为 **0**，持续 `5m`；就绪 = 进程在**拒新工作**（**就绪状态条件，非容量指标**） | 先分「正常摘流」与「卡住」：`/health/ready` **503 = 正在 draining（正常摘流中）**，持续 503 才是异常；再看 `describe pod` 的 Events（探针 / 挂载 / 镜像） | draining 不收敛 / 反复 not-ready → L2（L2 §4.7）；与 `ASRestartLoop` 同时出现 → 按 CrashLoop 处理 | **可触发（前提：集群装了 kube-state-metrics）**：只看 AS namespace 内的 Pod，**不区分组件**（AS 引擎 / `state-redis` / `state-postgres` / `config-service`），用 `pod` 名区分 |
| `ASDeploymentReplicasUnavailable`（`as.runtime`） | `warning` / `runtime` | 同一 Deployment 的可用副本数 < 期望副本数，持续 `10m`（**副本可用性状态条件，非容量指标**） | 先看告警里的 `deployment` 标签 —— 可能是用例 Deployment、`state-redis` 或 `config-service`；再 `get deploy` + `describe`；与 `ASPodNotReady` 合并判断（通常是同一事件的两个视角） | 用例副本不足影响业务 → L2；`state-redis` 不可用 → 与 `ASCallStateStoreUnavailable` 同路径立即升级 | **可触发（前提：KSM）**：选择器**按 namespace 限定**，故也覆盖内建 `state-redis` 与 `config-service` 两个 Deployment |
| `ASDownscaleBlocked`（`as.runtime`） | `warning` / `runtime` | 同一 `pod` / `use_case` 上 `as_downscale_removable == 0` **且** `as_active_calls == 0`，持续 `30m`。ADR-0010 的 guard 只有两个拦截理由（有在途呼叫 / 已在 draining），两者都排除后只剩「**draining 卡住**」（**guard 状态条件，非容量指标**） | 确认两个序列都产生（方法同 §1 #4）；看该 Pod `/health/ready` 是否长期 **503**；与 `ASPodNotReady` 合并：同一 Pod 上大概率同时 not-ready | 持续不收敛 → L2（L2 §4.7）；涉及多 Pod 或影响发布窗口 → 立即升级。**不得**直接删 Pod 或 SIGKILL —— 先走完 draining（ADR-0009 / ADR-0010） | **序列总是产出**（metrics 循环无条件写，不依赖 OTLP），但取值依赖真实 SIP dialog 活动 —— 无流量时不触发。另见 §1 #4 的抓取接线缺口 |
| `ASStatefulSetUnavailable`（`as.platform`） | `critical` / `state` | 某 StatefulSet 的 ready 副本数 < 期望副本数，持续 `5m`；chart 内即**治理库 PostgreSQL**（ADR-0008）（**副本就绪状态条件，非容量指标**） | 确认告警里的 `statefulset` 名（预期是 `<release>-postgres`）；`get sts` + `describe`；查最近的 migrate Job；治理库主机 `pg_isready` | **立即** L2 → 维护者。治理 PG 持有配置版本、变更单与 append-only 审计链 → **配置无法审批与分发**；先暂停变更单审批 | **可触发（前提：KSM）**：内建 PG 是**单副本、非 HA**（HA 由客户拥有；Redis HA 仍是 **O5 / D3**）—— 单副本是设计事实，**不是**容量结论 |
| `ASServiceEndpointsAbsent`（`as.platform`） | `warning` / `state` | 某 Service 的可用 endpoint 地址数为 **0**，持续 `5m` → selector 匹配不到任何 Ready Pod，客户端无法路由（**路由状态条件，非容量指标**） | 确认告警里的 `service` 名；`get endpoints <service> -o yaml`（ENDPOINTS 为空即证实）；对齐对应 Pod | 影响 `state-redis` → 与 `ASCallStateStoreUnavailable` 同路径立即升级；影响 `config-service` → 控制台不可用，转 L2（L2 §4.6）。回到 Pod 侧恢复，**不要**改 Service selector | **可触发（前提：KSM）**：与 `ASCallStateStoreUnavailable` 是**不同**失效模式 —— 本条是「Service 根本没有后端」，那条是「AS 连不上 Redis」 |

> **容量类告警：defer。** `as-alerts.yaml` **当前没有任何 CPS 上限或并发上限告警**，这是刻意设计。容量类告警在 **O1 裁决后**新建独立组，从实测取值。在此之前，异常负载用 `ASActiveCallsSurge` 与内部测量排查，**不得**用一个提前编造的数（`AGENT.md` §2 / §6）。
>
> **本页不含任何 Sh 相关告警**：不做 Diameter Sh 是已决策的非目标（`AGENT.md` §2）。控制面类告警（配置回滚 / 漂移 / 证书到期）在 `deploy/alerts/README.md` 中**明确 defer** 到相应指标导出为止 —— `as-alerts.yaml` 里**没有**它们。

---

## 3. 常见运维操作

每节结构：前置 → 命令原文 → 期望输出 → 失败处置 → 来源。

### 3.1 手工缩容与摘流

来源：[`../acceptance/m5-downscale-runbook.md`](../acceptance/m5-downscale-runbook.md)（判据实现 `platform/src/as_platform/ops/downscale_guard.py`，ADR-0010；ISSU = draining，ADR-0009）。

**前置**：每 Pod 可查询 **`as_active_calls`**（`GET :8080/metrics` 或遥测导出）；`AS_DOWNSCALE_GUARD_ENABLED` / `AS_DOWNSCALE_GUARD_PROTECT_ABOVE` 由 Helm ConfigMap 注入（默认 enable + 阈值 0）；HPA **可不启用**（O1 / M6 前无阈值），缩容可为手工或集群 autoscaler 提议副本数。

**判据（`plan_scale_down` 输入与调用）**

```python
from as_platform.ops.downscale_guard import InstanceLoad, plan_scale_down

plan = plan_scale_down(
    (
        InstanceLoad("as-translation-abc", active_calls=0, draining=False),
        InstanceLoad("as-translation-def", active_calls=3, draining=False),
    ),
    desired_replicas=1,
    protect_above=0,  # 与 AS_DOWNSCALE_GUARD_PROTECT_ABOVE 一致
)
```

**命令原文（推荐四步顺序）**

1. **计算** `plan_scale_down`（或运维脚本包装）。
2. 对 **removable** 中每个 Pod：`kubectl delete pod` 前确认 `active_calls==0`；Kubernetes 删除会触发 `preStop sleep` + SIGTERM。
3. 对 **仍承载呼叫** 的 Pod：不删除；等待自然结束，或业务层结束呼叫；readiness 在 `request_terminate` 后为 **503**，Endpoint 应摘流。
4. 若 `blocked`：仅缩减 `removable` 子集，或等待。

**期望输出**：`plan.allowed == True` 且 `plan.candidates` 列出可摘除实例；摘流期间 `/health/ready` 返回 **503**。

**失败处置**

- `plan.allowed` 为 `False`：无足够零呼叫实例可删 → **不要删 Pod**，或先对高负载实例发起 draining。
- **不得 SIGKILL**：`plan.candidates` 里的实例**仍须走 draining 流程**。
- readiness 不是 503、Endpoint 没摘流 → 升级 L2（L2 §4.7）。

> ⚠️ **证据边界**：`AS_M5_SIMULATED_ACTIVE_CALLS=N` 是**仅测试 / 证据用**的模拟在途呼叫（SIGTERM 后每秒减 1），用于 kind 证据脚本验证 draining 与判据。**它不是生产负载下的不掉呼叫证据** —— 真实 SIP 不掉呼叫待 M7 / M8 验收（G-P1-1）。

### 3.2 滚动升级

来源：[`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Upgrade discipline；[`../../deploy/helm/templates/NOTES.txt`](../../deploy/helm/templates/NOTES.txt) §3。

**前置**：确认本次变更窗口；确认 `helm history` 里的当前 revision；确认 state store 与用例副本可承接摘流（draining 语义 = ISSU，ADR-0009）。

**命令原文（只改这三组参数）**

| 变更范围 | 命令焦点 |
|---|---|
| 仅 AS 镜像 / SIP 旋钮 | `helm upgrade` with only `image.*`, `sip.*`, `useCases` |
| PG 镜像 / PVC | 维护窗口；follow Postgres upgrade runbook |
| Redis | 维护窗口；预期短暂运行态不可用 |

label 选择器：`app.kubernetes.io/component=state-postgres|state-redis` 用于状态存储，与用例 Deployment 区分。

**回退（镜像 / manifest 回退，与配置回退是两件事，不要混）** —— 以下三条逐字来自 `deploy/helm/templates/NOTES.txt` §3，仅把 Helm 模板占位符 `{{ include "as.namespace" . }}` / `{{ .Release.Name }}` 写成 `<ns>` / `<release>`：

```sh
helm -n <ns> history <release>
helm -n <ns> rollback <release> <revision>
kubectl -n <ns> rollout status deploy --selector app.kubernetes.io/part-of=3rdparty-as
```

**期望输出**：滚动期间 `/health/ready` 逐 Pod 转 **503** 后再重建；升级完成后 §1 #3 的 `CONFIG_VERSION` 在各副本一致。

**失败处置**：Pod 卡在非 ready → §4；需要业务摘流 / 回退的完整流程见 [`rollback-playbook.md`](rollback-playbook.md)（**已落盘**；但其 iFC / 摘流部分**依赖 S-CSCF / HSS 侧配合与真实集群演练**，当前仍 blocked，G-P1-10）。

> **ISSU 语义**：摘流（draining）是退出路径的既有语义，**不是**容量结论。

### 3.3 控制台日常操作（规则变更单）

来源：[`../acceptance/m4b-8-runbook.md`](../acceptance/m4b-8-runbook.md)（浏览器验收 5 步路径）；治理语义 ADR-0006；状态机实现 `services/config-service/src/as_config_service/change_order.py`。

**路径**：编辑草稿 → 提交 → 审批 → 灰度分发 → 回滚。配置**不走 GitOps**，也**不是**运维直接 UPDATE 数据库（`AGENT.md` §2）。

```
DRAFT --submit--> SUBMITTED
SUBMITTED --approve--> APPROVED
SUBMITTED --reject--> REJECTED
APPROVED --begin_distribution--> DISTRIBUTING
DISTRIBUTING --roll_back--> ROLLED_BACK
APPLIED --roll_back--> ROLLED_BACK
```

`REJECTED` / `APPLIED` / `ROLLED_BACK` 是终态。分发状态（`services/config-service/src/as_config_service/distributor.py`）：`pending` → `in_progress` → `completed`，异常时 `rolled_back`。

**范围（务必按此口径回答用户）**

- 当前 live 控制台仅暴露 **被叫 + 前缀** 规则。
- **主叫 / 正则规则为 v1.1，不是发行版本**（`docs/plan.md` §0：文档中的「v1」「v1.1」不能当作范围依据）。
- 运行态覆盖粒度 = **号段 + 稳定哈希百分比**（ADR-0021）；**AS 侧不主动摘在途呼叫**。

**BLOCKED 规则（不得写成通过）**

- Call-ID live trace（REQ-F-13 / M4b-7.4）：M4 关门裁决延期，**无 live trace source / API** → `BLOCKED: missing backend`；注入健康失败自动回滚 / 手动回滚的浏览器验收依赖完整 distribution 链路 → 仍 `BLOCKED`。

**期望输出**：变更单走完 `submitted → approved → distributing → applied`，各实例上报 `CONFIG_VERSION` 更新且一致；审计行产生（append-only）。

**失败处置**：配置改了但不生效 → L2 §5。控制台无法登录 / 越权 → L2 §4.6 与责任边界。

> 自动化替代：`cd deploy/compose && export M4B8_E2E_PASSWORD='<12+ chars, dev-only>' && ./scripts/m4b-8-browser-evidence.sh`。Ubuntu 20.04 若无法 `playwright install chromium`，脚本会回退到 `mcr.microsoft.com/playwright` 容器（`--network host`）。产物默认写入 `artifacts/m4b-8/<date>/`。**这是工程检查清单，不构成 M4b / M4 / REQ 验收通过**（维护者 2026-10-04 的签字只表示工程链跑通）。

### 3.4 证书轮换的配置热更新

来源：`AGENT.md` §13；`deploy/helm/templates/NOTES.txt` §1；ADR-0016；实现语义 `platform/src/as_platform/sip/tls_rotation.py`。

**前置**：客户 PKI Secret 已就绪（`tls.secretName` 指向 `tls.crt` / `tls.key` / `ca.crt`）—— 若 `tls.enabled=true` 而 `tls.secretName` 为空，chart **不挂载任何证书**、SIP TLS 路径指向不存在的文件，上线前必须补（NOTES.txt §1）；双证书重叠窗口策略已定（`retiring` + `overlap_deadline_monotonic`）。

**原则（不是命令，是硬约束）**：证书轮换是**配置热更新** —— **绝不重启进程，绝不丢掉在途呼叫**（`AGENT.md` §13）。轮换请求在重叠开始时向栈请求 `reloadCertificates`；已注册连接继续用 retiring 材料直到重叠截止，新连接用新材料。

**期望输出**：`RESIP_RUNTIME_RELOAD_CERTIFICATES`（`detail=invoked`）出现在运行时日志（见 L2 §2）。**失败处置** → L2。

> ⚠️ **E4 / REQ-S-2 / REQ-S-3 当前无实验室证据**：证书热轮换（E4）、运营商 PKI / 对端证书校验尚**未验收**。本节是操作纪律，**不是**已验证流程。

### 3.5 备份与恢复日常命令

来源：[`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Backup & restore（ADR-0008 最小集）。

**前置**：治理 PG 可达；使用具备备份权限的角色执行；`kubectl cp` 需要 Pod 内有 `pg_dump`（PostgreSQL 官方镜像有）。

**命令原文（PostgreSQL —— 治理态，必须保留审计链）**

```sh
kubectl -n <ns> exec as-3rdparty-as-postgres-0 -- \
  pg_dump -U postgres -d as_config -Fc -f /tmp/as_config.dump
kubectl -n <ns> cp as-3rdparty-as-postgres-0:/tmp/as_config.dump ./as_config.dump
```

**期望输出**：`./as_config.dump` 落盘且大小非零。

**失败处置**：`kubectl cp` 报 not found → 确认 Pod 名与 namespace；`pg_dump` 权限错误 → 换具备备份权限的角色；**不要**为了图省事把 owner DSN 写进 Deployment（见 L2 §6）。

**必须知道的三个限制**

- **Chart 不自带备份 Job。** 排期由客户备份工具承担（Velero、cron Job，或 HA 场景的集群外 WAL 归档）。
- **内建 Redis / PG 是单副本，不是 HA。** Redis HA 仍是未决项 **O5 / D3**（Sentinel）；生产 PG HA 由客户拥有（Patroni / 云 RDS，或改用外部 `postgres.host` 并设 `stateStores.enabled=false`）。客户须自行记录 **RPO / RTO**。
- Redis（运行态）丢失 ≈ 呼叫失败，备份可选（ADR-0007），但 RPO / RTO 仍须与客户共同记录。
- **Restore drill、备份验证脚本、定期演练记录**属交付物 2.5，见 [`backup-restore.md`](backup-restore.md)（**已落盘**；但**真实集群 restore drill 记录仍 blocked**，M8 真实集群证据当前搁置，G-P1-10）。

---

## 4. 升级与求助

**升级路径**：L1 → L2（[`runbook-l2.md`](runbook-l2.md)）→ 维护者。

**升级 L2 的触发条件**：§1 任一项无法判定归属；§2 表中标「升级 L2」；`/health/ready` 持续 503；Pod 反复重启；配置改了不生效。

**升级维护者的触发条件**：需要裁决产品口径、推翻既有裁决、或改动未决项（O1 / O4 / O5、D3 / D5）。L1 / L2 都**不得**自行把未决项当成已解决（`AGENT.md` §15）。

**求助时必须附的证据清单**

| 项 | 说明 |
|---|---|
| 告警名与完整表达式求值结果 | 例如 `ASCallStateStoreUnavailable` + `min by (use_case) (as_state_store_available)` 的时间序列 |
| 命名空间 / Pod 名 / use_case | `kubectl -n as-prod get pods -l app.kubernetes.io/part-of=3rdparty-as` 输出 |
| 时间窗（含时区） | 首次出现、持续、最近一次 |
| `/metrics` 片段 + 脱敏后的日志 | 只截取相关 `as_*` 序列；脱敏规则见 §5 |
| Call-ID | 若与具体呼叫相关；跨腿 B2BUA 的两腿 Call-ID **不同**，两个都带上 |
| 变更记录 + 已被排除的可能 | 最近一次 `helm upgrade` / 变更单的 revision 与时间；已做过什么、结果如何（避免把「没查」当成「已排除」） |

**AS 侧证据不足时的纪律**：无证据时**不得先行定界**。AS 侧只有自己的日志、指标与配置版本；对端链路（S-CSCF → S-SBC 触发段、S-SBC → AS trunk 段）的取证需对方配合（[`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3）。

---

## 5. 证据与脱敏规则

来源：`AGENT.md` §11 / §13；[`../acceptance/m4b-8-runbook.md`](../acceptance/m4b-8-runbook.md) §5/§8。

**禁止**（无一例外）

- **禁止保存**密码、token、cookie、session、私钥（`BEGIN PRIVATE KEY`）、任何 Secret 内容；**禁止**用真实地址、客户名称、真实号码作为示例。
- **禁止**把真实抓包（pcap）提交进仓库或证据目录。
- 载荷日志（SIP body / SDP）默认**关闭**（`AS_PAYLOAD_LOGS_ENABLED` / `telemetry.payloadLogsEnabled` 默认 `false`）；开启是显式、可审计的操作。

**截图 / 录屏前**：遮盖 cookie、session、CSRF、密码字段；确认地址栏是 **HTTPS**（不要通过 `http://` 访问登录页）；浏览器侧确认 API 为**同一 origin**（如 `https://<host>/internal/v1/...`），无 mixed-content。

**导出 / 查询审计记录时**：确认输出无 password / token；runtime 角色对 audit 表的 INSERT/UPDATE/DELETE/TRUNCATE 应被拒绝（append-only，fail-closed）。

**归档位置**（占位，按维护者指定目录）：`artifacts/<milestone>/<YYYY-MM-DD>/`。归档后在下册对应 `report.md` 小节填写路径、commit 与阻塞项摘要。

---

## 6. 来源映射

| 本页章节 | 原文件与位置 | 归集方式 |
|---|---|---|
| 状态块 | [`../acceptance/report.md`](../acceptance/report.md) §0.1/§0.4/§0.5；[`../plan.md`](../plan.md) §0 | 摘要 |
| §1 #1–#3 Pod / 健康端点 / 配置版本 | `deploy/helm/templates/_helpers.tpl:55,71`；`templates/NOTES.txt:37-51`；`deploy/helm/values.yaml:281-303`；`templates/configmap.yaml:58`；`platform/src/as_platform/runtime/health.py` | 索引链接（自核实） |
| §1 #4/#6 指标与 Redis 可用性 | `deploy/alerts/README.md` §Metric contract；抓取缺口自核实（`deploy/helm/templates/` 全目录无 `prometheus.io/scrape` / ServiceMonitor / PodMonitor） | 摘要 + 自核实 |
| §1 #5 ingress 301/308 | [`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md) 检查项 4、§「宿主机 80/443 与集群内 ingress curl」 | 摘要 |
| §1 #6 Redis 可用性 | `deploy/alerts/README.md` §Metric contract | 索引链接 |
| §1 #8 控制台 | [`../acceptance/m4b-8-runbook.md`](../acceptance/m4b-8-runbook.md) §8 | 索引链接 |
| §2 全表 | [`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml) **10 条规则 / 3 个组**；[`../../deploy/alerts/README.md`](../../deploy/alerts/README.md)；可触发性取自 [`alert-response-matrix.md`](alert-response-matrix.md) §2 与 [`../product/ne-datasheet.md`](../product/ne-datasheet.md) §6，并经 `platform/src/as_platform/__main__.py` 自核实 | 摘要（阈值以规则文件为唯一权威） |
| §3.1 缩容 | [`../acceptance/m5-downscale-runbook.md`](../acceptance/m5-downscale-runbook.md) §1–§5（**全文照抄命令与顺序**） | 重写操作正文 |
| §3.2 滚动升级 | [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Upgrade discipline；`templates/NOTES.txt` §3 | 重写操作正文 |
| §3.3 控制台 | [`../acceptance/m4b-8-runbook.md`](../acceptance/m4b-8-runbook.md) §1/§2/§4/§7；`services/config-service/src/as_config_service/change_order.py:17-23`；`distributor.py:49-55` | 摘要 + 索引链接 |
| §3.4 证书热更新 | `AGENT.md` §13；`templates/NOTES.txt` §1；`platform/src/as_platform/sip/tls_rotation.py:1-18` | 摘要 |
| §3.5 备份恢复 | [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Backup & restore、§PostgreSQL HA / PITR（**两条命令照抄**） | 重写操作正文 + 摘要 |
| §4 升级路径 | [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §4 | 摘要 |
| §5 脱敏 | `AGENT.md` §11 / §13；[`../acceptance/m4b-8-runbook.md`](../acceptance/m4b-8-runbook.md) §5/§8 | 摘要 |