# ADR-0013：Helm 是唯一生产形态

- **Status**: accepted
- **Date**: 2026-09-30
- **Decides**: §0 账本条目 6 —— 部署形态：Kubernetes + Helm（compose 仅作 dev 环境）
- **回应 REQ**: REQ-NF-9

---

## Context（背景）

我们交付的是**单租户 on-premises**（REQ-NF-9）：每客户一个独立实例，部署在客户（运营商）自己的机房里，一个命名空间承载一整套系统 —— 它自己的 Redis、PostgreSQL 与 AS Pod 组。交付面对的人是客户的运维，他们不会读我们的源码，只会照着一份安装说明执行命令。

在这种交付形态下，**交付形态本身的数量是一个需要被管理的变量**。如果 `docker compose` 也能上生产，那么"这个客户的生产上跑的到底是哪一套"就变成每次排障都要先确认的问题；更糟的是，draining、会话亲和、Secret 挂载、探针、证书热轮换这些语义会在两套形态里各自演化，最终谁都不完整，而事故只会发生在语义缺失的那半边。

`AGENT.md` §2 的非目标已经把另一条路封死：**「不写 Operator（CRD）。用 Helm + 标准 Deployment / ConfigMap / Secret（ADR-0013）。」** 理由是收益不匹配：Operator 的自动化能力（自定义资源、自动调谐、复杂升级编排）在"单租户 on-prem、变更频率按客户协商窗口走"的场景里，换来的收益不足以抵消它自身的学习、构建与维护成本。

还有一个必须由交付形态承担的特殊约束：**在未决项 O1 被 M6 实测回答之前，本仓库不得发布任何容量数字**（`AGENT.md` §2）。这意味着交付形态里不能出现任何"看起来权威"的容量默认值 —— 一个被猜出来的 HPA 阈值比没有 HPA 更危险，因为它会静默地限流或过度扩容。这条约束要求 chart 具备**拒绝渲染**的能力，而不只是"留空"。

## Decision（决策）

- **生产交付只有 Helm chart（`deploy/helm/`）。** 一套形态，别无分店。
- **`deploy/compose/` 仅作本地开发环境，不得用于生产。** 它不是"轻量版生产"，是开发用的启动器。
- **不写 Operator / CRD。** 用 Helm + 标准 Deployment / ConfigMap / Secret（`AGENT.md` §2 非目标）。
- **容器镜像由 `deploy/docker/Dockerfile` 构建；镜像是 chart 的输入，不是第二套交付形态。** 镜像的 tag 通过 chart 的 `image.repository` / `image.tag` 注入，发布到客户内部 registry 后由 Helm 消费。
- **容量类 key 一律留空（null），且模板拒绝渲染而不是回退到猜测值。** 未填即安装失败（`required` 守卫 + `fail`），而不是用一个默认值假装它存在。
- **客户专属的密钥、地址、拓扑一律不在仓库内落值**：凭据占位（空串）、TLS 走客户 PKI 的 Secret 引用、Redis / PostgreSQL 为外部依赖（chart 不部署它们）。

## Consequences（后果）

### Positive（正面）

- **一套形态，运维只需学 Helm。** 安装、升级、回滚、参数化都只有一处语义；排障时不需要先回答"这是哪一套"。
- **连续性语义只有一处实现。** `preStop` draining 与延长的终止宽限期（[ADR-0009](0009-issu-draining.md)）、`sessionAffinity: ClientIP`（[ADR-0002](0002-per-usecase-process-state-redis.md) 的双保险之一）、TLS 证书挂载与热轮换（[ADR-0016](0016-in-boundary-security.md)）、审计与凭据替换，全部只在 chart 里定义一次。
- **容量数字不会从 chart 里漏出去。** `autoscaling` 的阈值与副本上下限为 `null`，`hpa.yaml` 在阈值缺失时**不渲染该资源**；开启 `autoscaling.enabled` 而阈值未填时 `minReplicas` / `maxReplicas` 走 `required` 守卫，安装**失败**并给出明确信息。PDB 的 `minAvailable` 为 `null` 时同样不渲染 —— 一个凭空发明的可用性下限，是一个没人做过的决定。
- **每用例一 Deployment 与 ADR-0002 同构。** `useCases` 是被遍历的列表，`enabled: false` 的用例不渲染任何对象，扩用例不需要改模板结构。

### Negative / accepted（负面 / 已接受）

- **放弃了 Operator 的自动化能力。** 没有自定义资源、没有自动调谐、没有复杂的升级编排。接受：单租户 on-prem，变更频率低，Operator 的成本高于收益；且这一条是 `AGENT.md` §2 的非目标，不是本 ADR 的取舍。
- **客户环境必须有 Kubernetes。** 没有 K8s 的环境无法交付；当前不接受裸机部署或"容器直跑"形态。若将来出现这类客户，需要新写 ADR 推翻本决策，而不是在交付时临时凑一套。
- **`helm` 二进制是安装前置，本仓库不交付 helm 本身。** 离线交付场景需自行带上；这属于实施手册的内容。
- **若干 values 必须在安装时由客户或实施方填写，空值语义需被正确理解**：`redis.sentinel.masters` / `.addresses`（依赖未决的 O5 与 D3）、`postgres.host` / `.database`（客户专属外部存储，[ADR-0007](0007-data-plane-split.md)）、`tls.secretName`（客户 PKI）、`telemetry.otlpEndpoint`（空 = NoOp 导出，对呼叫路径安全，[ADR-0005](0005-observability-otel.md)）、`sip.peerAllowlist`（**空必须按 fail-closed 处理**，[ADR-0016](0016-in-boundary-security.md)）。空的 `peerAllowlist` 不是一个"以后再配"的便利，它是一个安全控制的开启状态。
- **chart 不部署 Redis 与 PostgreSQL。** 它们是外部依赖，其高可用与备份由客户或实施方承担（[ADR-0008](0008-redundancy.md) 要求有状态组件纳入冗余与备份清单，但不在本 chart 的范围内）。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| compose 也可上生产（双形态） | 语义在两套形态里漂移：compose 无 HPA、无 PDB、无 Secret 治理、无 draining 的 terminationGracePeriod 语义；且"生产跑的是哪一套"每次都要重新确认 |
| Helm + Operator（CRD） | 收益不匹配：单租户 on-prem、变更频率低，Operator 的学习与维护成本高于其自动化收益；`AGENT.md` §2 已列为非目标 |
| Kustomize | 无打包与 release 版本管理；同一套运营商级旋钮无法以 values 的形式集中显式化，也无法做安装期的参数校验 |
| 裸机 / systemd 部署 | 与 [ADR-0010](0010-autoscaling-hpa-downscale-guard.md) 的 HPA、[ADR-0008](0008-redundancy.md) 的多副本零单点直接冲突；每用例一进程的扩缩与 draining 都需要编排层 |
| 纯 Helm + 标准对象（本决策） | 采纳。一套形态、一处语义、阈值缺失即拒绝渲染 |

## Evidence（证据）

- `AGENT.md` §2 非目标原文：「**不写 Operator（CRD）。** 用 Helm + 标准 Deployment / ConfigMap / Secret（ADR-0013）。」
- `deploy/helm/values.yaml` 原文（M5 values contract 注释块）：「Single-tenant, on-prem: one namespace holds one complete system (its own Redis / PostgreSQL / AS Pod group). See REQ-NF-9. **Helm is the only production form; `deploy/compose/` is dev-only. See ADR-0013.**」同文件容量规则注释：「no CPS or concurrency figure is published before M6 measures it. Every key below that would encode a capacity assumption is left null, and the template that consumes it does not render the resource at all rather than fall back to a guessed number.」
- `deploy/helm/README.md`「Render guards」原文：`hpa.yaml` 仅在 `autoscaling.enabled` **且**至少一个目标阈值非 null 时渲染，`minReplicas` / `maxReplicas` 随后为 `required`；`pdb.yaml` 仅在 `podDisruptionBudget.minAvailable` 非 null 时渲染；`secret.yaml` 仅在 `postgres.secretName` 为空时渲染。同表：「`autoscaling.minReplicas` / `.maxReplicas` | `required` — install **fails** with an explicit message when autoscaling is enabled. There is no default, because a default would be a guessed capacity number」。
- `deploy/helm/templates/hpa.yaml` 的守卫代码：`{{- $minReplicas := required "autoscaling.minReplicas is required when autoscaling.enabled=true. It is a capacity figure: measure it in M6 (O1), do not guess." $a.minReplicas }}`（`maxReplicas` 同），以及阈值全空时的 `{{- fail ... }}`。文件头注释写明：进入该文件而容量数字为 null 是**硬错误，不是静默跳过**，因为"因阈值留空而被静默省略的 HPA，看起来和本来就没打算要的 HPA 一样"。
- **渲染已校验（M5）**：`docs/acceptance/report.md` M5 段原文 ——「helm v3.16.2：`helm lint deploy/helm` 0 failed、`helm template as deploy/helm` exit 0；首次渲染暴露并修掉 `_helpers.tpl` 两处左裁剪导致的标签拼接；`--set autoscaling.enabled=true`（HPA 阈值未填）路径按预期失败」。按当前默认 values（`useCases` 为 `translation` 与 `anti-fraud` 两项且均 `enabled: true`，HPA 阈值与 `podDisruptionBudget.minAvailable` 为 null、故 `hpa.yaml` 与 `pdb.yaml` 不渲染），`serviceaccount.yaml` / `secret.yaml` / `configmap.yaml` 各渲染 1 个，加每用例一组 Deployment + Service 共 4 个，合计 **7 个对象**。
- **镜像是 chart 的输入而非第二形态**：`deploy/docker/README.md` 原文「The image is an input to the Helm chart; it is not a second production deployment form. Helm remains the only production deployment form under ADR-0013. The files under `deploy/compose/` are for local development only.」构建命令为 `docker build -t as-platform:dev -f deploy/docker/Dockerfile .`（构建上下文为仓库根）。
- `docs/plan.md` §2.1 目录结构原文：「`deploy/` helm/（生产）· compose/（仅 dev）」；§4 里程碑 M5 交付项含 Helm chart。
- 架构文档 §0 决策账本条目 6 原文：「部署形态 | Kubernetes + Helm（compose 仅作 dev 环境）」。
- PRD REQ-NF-9（单租户 on-premises 部署）原文：「每客户独立实例，on-premises 交付（运营商机房内部署）。不做多租户……运营商的交付形态本身就是一客户一系统，多租户在此场景无收益，反而增加跨租户数据泄露风险。」
- `deploy/helm/README.md`「Keys left empty on purpose」表中对 O5 / D3 的关联原文：「`redis.sentinel.masters` / `.addresses` | topology depends on unresolved O5 (N+1 vs N+M) and D3 (Sentinel wiring, split-brain window)」。

## Related（相关）

- [ADR-0002](0002-per-usecase-process-state-redis.md) 每用例一进程 —— `useCases` 遍历与会话亲和双保险
- [ADR-0009](0009-issu-draining.md) ISSU 是 draining —— `preStop` + 延长 terminationGracePeriodSeconds
- [ADR-0010](0010-autoscaling-hpa-downscale-guard.md) 扩缩容 HPA —— 阈值缺失即拒绝渲染的守卫归它消费
- [ADR-0016](0016-in-boundary-security.md) 边界内安全 —— TLS Secret 挂载热轮换、`peerAllowlist` 空即 fail-closed
- [ADR-0005](0005-observability-otel.md) OTel 三信号 —— `otlpEndpoint` 空即 NoOp 导出
- [ADR-0007](0007-data-plane-split.md) 数据面拆分 —— 治理 PG / 运行 Redis 逻辑不变
- [ADR-0008](0008-redundancy.md) 冗余 —— HA/备份责任见 [ADR-0026](0026-in-cluster-state-stores-proposal.md) runbook
- [ADR-0026](0026-in-cluster-state-stores-proposal.md)（2026-10-04）—— 修订下文「chart 不部署 PG/Redis」：可选 `stateStores.enabled` 同 chart 渲染；禁止 IMS PG
- [`../新系统整体架构.md`](../新系统整体架构.md) §0 条目 6
- 未决项 O1（容量目标 / M6）与 O5 / D3（Redis 拓扑与接线）—— 均**未裁决**，chart 对应 key 保持为空

## Amendment（[ADR-0026](0026-in-cluster-state-stores-proposal.md)，2026-10-04）

**部分修订**本 ADR Decision 最后一条与 Consequences 中「chart 不部署 Redis 与 PostgreSQL」：

- **仍成立**：唯一生产形态是 `deploy/helm/`；不写 Operator；compose 仅 dev；容量 key 拒绝猜测渲染。
- **修订**：标准 on-prem 可通过 **`stateStores.enabled=true`**（见 `values-onprem.example.yaml`）在**同一 release、同一 namespace** 渲染专用 PostgreSQL 与 Redis；`bootstrapDevCredentials` 仅 kind/dev。
- **仍成立**：运营商 **IMS 核心库**不得作为 AS 治理 DSN；客户自带托管 PG/Redis 时设 `stateStores.enabled=false` 并填 `postgres.host` / `redis.url`。
- **备份 / HA**：chart 不替代 ADR-0008 清单；见 `docs/acceptance/m5-state-stores-runbook.md`。
