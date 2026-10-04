# ADR-0026（提案）：集群内治理态 PostgreSQL 与运行态 Redis —— 澄清「外部」语义与部署边界

- **Status**: accepted
- **Date**: 2026-10-04
- **Maintainer sign-off**: 2026-10-04 —— 交付形态选 **单 chart 完全合并**（见下文 Option **E**）；**不**采用双 release（原 Option A）
- **Decides**: §0 / D12 —— 标准 on-prem 在**同一 namespace** 内部署 AS 工作负载 + 专用 PostgreSQL + Redis；**禁止**运营商 IMS PG；**不**改变 ADR-0007 逻辑拆分；**部分修订** ADR-0013「chart 不部署 PG/Redis」为「默认由同一 chart **可选渲染**集群内 state（`stateStores.enabled`）」
- **回应 REQ**: REQ-NF-1, REQ-NF-2, REQ-NF-9, REQ-NF-10；与 REQ-S-4 控制面数据落库相关

---

## Context（背景）

维护者对既有 ADR 中「PostgreSQL / Redis 为外部依赖」的表述提出质疑，动机是**安全与可交付性**，而不是否定 ADR-0007 的数据面拆分本身。

**AS 治理态 PostgreSQL 不是运营商 IMS 核心网 PostgreSQL。** IMS 侧（S-CSCF、HSS、UDR 等）自有配置与订阅数据存储；第三方 AS 的治理态是**本产品实例专属**的规则版本库、变更单、审批与审计（ADR-0006）。二者在信任域、变更路径、备份与合规归属上都不相同。把 AS 配置治理库「挂到」运营商 IMS 运维已管的同一套 PG 上，通常意味着跨团队权限、跨网段访问与事故域耦合 —— 在网外部署前提下既难证明边界，也与单租户「一客户一完整系统」的交付叙事冲突。

**运营商约束（维护者输入）**：目标部署环境中，**运营商 IMS 的 PostgreSQL 不向 AS 开放**（无 DSN、无网络路径、无共用实例）。因此「让客户填一个现成 PG 地址」若被理解为「复用 IMS PG」，在该类客户上**不可行**；AS 仍需**独立**的治理库，只是物理上可以由客户基础设施团队提供，也可以与 AS 工作负载落在**同一 Kubernetes 集群、同一命名空间**内。

**「外部」在 ADR-0013 中的实际含义**是交付工件边界，不是「必须在 K8s 集群外」：

- Helm chart **不渲染、不生命周期管理** PostgreSQL 与 Redis 的 StatefulSet / Operator / 备份 Job；
- 连接信息通过 `values.yaml` 中的 `postgres.*`、`redis.*`（或 Sentinel 地址）注入 AS、`config-service` 等 Pod；
- M5 工程证据使用 **compose 起的 PG**（`deploy/kind/m5-lib.sh`）满足 kind 验收，同样说明「库角色」与「chart 是否打包数据库」是两件事。

当前 chart 与文档把「客户或实施方填写 `postgres.host` / Redis 拓扑」与「chart 不部署有状态组件」绑在一起表述，容易被读成「生产 PG/Redis 必须在集群外」。维护者希望：**在集群内、仍在 AS 信任边界内**部署专用 PG + Redis，并用 NetworkPolicy 收紧东西向访问，而不是把状态存储暴露在集群外或依赖 IMS 核心库。

**Redis 仍在 Pod 外、进程外**（ADR-0002）：无论 Redis 跑在集群内 Service 后面还是集群外 VIP，AS 进程都不内嵌会话状态；本提案只讨论 Redis **网络落点与交付责任**，不推翻 `StateStore` / Sentinel（O5、D3）方向。

未决项 **O5**（容灾等级）、**D3**（Sentinel 接线与脑裂幂等）仍约束 Redis 拓扑；本提案不替它们裁决，但要求任何「集群内 Redis」方案必须能接上 O5/D3 的后续结论。

## Decision（决策）

### 已采纳（逻辑与边界）

1. **ADR-0007 不变**：治理态 → PostgreSQL，运行态 → Redis。
2. **AS 治理库与 IMS 核心库必须分离**；运营商 IMS PG **不得**作为 AS DSN。
3. **标准交付**：PG + Redis 与 translation / anti-fraud / config-service **同一 Kubernetes namespace**（单租户「一套系统」）。
4. **Helm 交付形态（维护者裁决）**：**Option E —— 单 chart、单 release、完全合并**（`deploy/helm/` 一处渲染应用与可选集群内 state）。**拒绝 Option A（双 chart / 双 release）**：维护者认为 ISSU 隔离收益不足以抵消双 release 运维与版本矩阵复杂度。

### 部署选项（历史比较；**E 为唯一标准路径**）

| Option | 概要 | 裁决 |
|---|---|---|
| **A. 伴随 release `as-state`** | 第二 chart + 第二 release | **不采用** |
| **B. 可选 subchart** | 同一 release，`dependencies` 拉上游 chart | **不单独采用**；E 实现时若复用上游 chart，可作为 E 的**实现手段**（仍一个 release） |
| **C. 客户平台能力** | `stateStores.enabled=false`，只填外部 endpoint | **保留**（已有托管 PG/Redis 的客户） |
| **D. 裸 StatefulSet 示例** | 非正式交付 | **仅 lab/kind 辅助**，非生产唯一故事 |
| **E. 单 chart 完全合并（accepted）** | 一个 `helm upgrade` 安装 namespace 内应用 +（默认开启时）PG + Redis；Service DNS / Secret 由 chart 内 `fullname` 贯通；`stateStores.enabled=false` 时行为等同 C | **标准 on-prem** |

### Option E —— 实现约束（与 ISSU / 扩容 / 话务）

**运行时与 chart 个数无关**（见维护者评审）：HPA / draining / `as_active_calls` 只作用于 AS Deployment；话务不驱动 PG 水平扩容；Redis 拓扑仍服从 **O5 / D3**。

**合并 chart 的 ISSU 纪律**（弥补放弃双 release 后的边界）：

| 纪律 | 要求 |
|---|---|
| **资源标签** | state 与 app 使用不同 `app.kubernetes.io/component`（如 `state-postgres`、`state-redis`、`as-*`），便于 `kubectl` / policy 筛选 |
| **升级默认值** | 应用 ISSU：`helm upgrade` 仅改 `image.*` / AS values 时，**不得**触发 PG/Redis StatefulSet 非必要变更（模板用稳定 name、PVC retention 文档化） |
| **Runbook 分章** | 同一 chart 内仍分 **「应用滚动 / ISSU」** 与 **「state 维护窗口（PG 补丁、Redis Sentinel）」** 两章，避免一次 upgrade 无审改变库 |
| **客户外置库** | `stateStores.enabled=false` + `postgres.host` / `redis.*` 指向客户 Service（Option C），不渲染 in-cluster state |

### 安全：NetworkPolicy（Option E / C 集群内端点）

在采用集群内 PG/Redis 时，提案要求至少：

- **入站**：仅允许来自 AS 用例 Deployment、`config-service`、`console`（及经批准的 migration Job）到 PG（5432）与 Redis（6379 / Sentinel 端口）的流量；默认拒绝同一 namespace 内其他 Pod 与跨 namespace 访问。
- **出站**：状态存储 Pod **不需要**访问 SIP 网段或公网；AS 应用 Pod 的出站仍由 ADR-0016（S-SBC 方向）约束，与 PG/Redis 策略分离。
- **凭据**：继续 `postgres.secretName` / Redis auth Secret 由客户或实施方注入；禁止把真实 DSN 写入 Git（ADR-0013 既有约束）。

集群内落点的主要安全收益是：**状态端口不对集群外暴露**，且与 IMS 核心数据面在实例与 NetworkPolicy 上隔离 —— 这比「依赖集群外未知拓扑的 PG」更容易在交付评审中证明。

### 实施顺序（accepted 后工程）

1. [x] **values 契约**：`stateStores.*`（默认 `enabled: false` 保 AS-only CI；kind `M5_BUNDLED_STATE=1`）。
2. [x] **模板**：`state-postgres.yaml`、`state-redis.yaml`、`state-networkpolicy.yaml`、`state-config-runtime-secret.yaml`；`chart-check` bundled 矩阵。
3. [x] **kind（M5 §4.6 / D12，非 M2）**：`m5-helm-install.sh` / `m5-ingress-evidence.sh` bundled profile。
4. [x] **生产（工程工件）**：`values-onprem.example.yaml`、`state-migrate-job.yaml`、[`m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) HA/PITR + migrate Job；客户 HA 运维与 D3 Sentinel 替换单实例 Redis 仍 **O5/D3**。
5. [x] **文档**：`新系统整体架构.md`、ADR-0013 Amendment（§4.6）。

### 对 ADR-0013 的修订（accepted 后果）

- **仍成立**：唯一生产形态是 Helm；不写 AS 专用 Operator（CRD）；compose 仅 dev。
- **修订**：「chart 不部署 Redis / PostgreSQL」改为 —— **默认 on-prem 由同一 chart 在 `stateStores.enabled=true` 时渲染**；客户外置库时 `enabled=false`，chart 只消费 endpoint。

## Consequences（后果）

### Positive（正面）

- **消除 IMS PG 误读**，避免不可交付的「填一个运营商核心库地址」假设。
- **安全叙事可画边界图**：SIP 入口（ADR-0016）与状态平面（PG/Redis）均在客户命名空间内，NetworkPolicy 可审计。
- **保留 ADR-0007 / 0002 逻辑模型**；仅移动状态存储的网络与运维归属，不引入跨存储事务。

### Negative / accepted（负面 / 已接受）

- **运维面扩大**：集群内 PG/Redis 的备份、升级、容量与 HA 必须有明确责任人；ADR-0013 当前把这部分明确推到「客户或实施方」，伴随 release 后产品侧需配套 runbook，否则只是把问题从「集群外」挪到「集群内」。
- **合并 chart 的 ISSU 纪律成本**：须靠标签、runbook 与模板稳定性避免「升应用顺带升库」；维护者接受，以换取单 release 简单性。
- **O5 / D3 未决**：集群内 Redis 不自动解决 Sentinel 与脑裂；D3 仍是硬项。
- **与部分 M5 文档字面「外部 PostgreSQL」并存**：需用本 ADR 澄清「外部 = chart 不部署」，避免证据链被误读为否决集群内 PG。

## Alternatives considered（考虑过的备选）

| Option | Why not（作为唯一路径时） |
|---|---|
| 复用运营商 IMS PostgreSQL | 维护者约束下不可用；信任域与 ADR-0006 治理归属冲突 |
| 坚持「必须在 K8s 集群外」的 PG/Redis | 无法满足「状态端口仅集群内可达」的安全目标；与单 namespace 完整系统叙事不一致 |
| 为 AS 编写专用 CRD Operator 管理 PG/Redis | `AGENT.md` §2 非目标：不写 Operator；与 ADR-0013 一致拒绝 |
| 把会话状态收回进程内 / 改 PostgreSQL 运行态 | ADR-0002 / 0007 已否决；本提案不涉及 |
| Option A 双 release | 维护者 2026-10-04 否决：复杂度高于收益 |
| Option E 单 chart 合并 + NetworkPolicy | **accepted** |

## Evidence（证据）

- [ADR-0013](0013-helm-only-production.md) 决策原文：「Redis / PostgreSQL 为外部依赖（**chart 不部署它们**）」；`deploy/helm/README.md` 表项 `postgres.host` —— "customer-specific, **external store** (ADR-0007)" —— 与 chart 不渲染数据库对象一致，但未定义「external = 集群外」。
- [ADR-0007](0007-data-plane-split.md) 治理态 / 运行态拆分；与部署拓扑无关。
- [ADR-0006](0006-config-governance.md) 治理态形态：PostgreSQL 版本库 + 变更单；实例归属 AS 产品。
- `docs/plan.md` §4.4.4 **M5-1d**：kind 使用 compose PostgreSQL，**非** Chart 内建库。
- `deploy/helm/values.yaml` 注释块：单租户 on-prem「one namespace holds one complete system (its own Redis / PostgreSQL / AS Pod group)」—— 与「集群内自有 PG/Redis」一致，与「IMS 共用 PG」不一致。
- 维护者输入（2026-10-04）：运营商 IMS PG 不对 AS 开放；要求 PG/Redis 在 K8s 内以满足安全边界。

## Related（相关）

- [ADR-0013](0013-helm-only-production.md) Helm 唯一生产形态 —— 「外部」语义澄清的主要对象
- [ADR-0007](0007-data-plane-split.md) 数据面拆分 —— **逻辑**不变
- [ADR-0002](0002-per-usecase-process-state-redis.md) 状态外置 Redis —— 进程外、可在集群内
- [ADR-0006](0006-config-governance.md) AS 治理态 PostgreSQL
- [ADR-0008](0008-redundancy.md) 有状态组件冗余与备份清单
- [ADR-0016](0016-in-boundary-security.md) SIP 入口安全 —— 与状态平面 NetworkPolicy 互补
- [ADR-0023](0023-redis-call-state-checkpoint.md) Redis checkpoint 方向 —— 不依赖 PG 落点
- `docs/plan.md` §5.2 **D12** —— 跟踪本提案
- 未决项 O5、D3
