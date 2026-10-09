# 业务摘流 / 回退手册（Rollback Playbook）— In-house IMS Application Server（文档暂用名）

> **交付物归属**：[`../product-packaging-plan.md`](../product-packaging-plan.md) §1 第二批 **2.4 ISC 触发后业务灰度 / 摘流方案 + 与 S-CSCF 侧 iFC 灰度的配合**。按该计划 §3.2，本交付物的**文档部分**属 A 类；**真实集群演练部分为 B 类**，被M8 真实集群环境（**7.2d仍 blocked**）与 S-CSCF / HSS 侧配合阻塞（评审 **G-P1-10**）。**M8 退出签字仍搁置**。
>
> **⚠️ iFC 触发逻辑属 S-CSCF / HSS，不在 AS 侧（评审 G-P0-5已裁决）**。本产品**只实现 ISC 触发后的业务判决与摘流 / 回退**，**不实现 iFC**。按号段 / 百分比的 **iFC 触发**必须在 OP-NET / OP-HSS 侧配置，AS 侧无从代劳。本文**只定义 AS 侧的配合接口与流程**，不把 iFC 写成 AS 侧交付物。
>
> **AS 侧不主动摘在途呼叫。** 我方能保证的是「**不主动摘在途呼叫**」；**呼叫是否进入本 AS 由 S-SBC / S-CSCF 侧的 iFC 配置与摘流动作决定**（G-P0-5 / G-P1-10）。
>
> **draining 证据边界**：现有 draining / 缩容 / 滚动升级的不掉呼叫证据来自 kind 上 `AS_M5_SIMULATED_ACTIVE_CALLS` **模拟**在途呼叫（**G-P1-1**）。**真实 SIP 负载下的不掉呼叫待 M7 / M8 验收**。
>
> **零容量数字**：本文无 CPS / CAPS / BHCA / 并发 / 吞吐 / 时延 / 百分比容量，也不引用 M6 dev-host 数字（O1 未裁决，`AGENT.md` §2）。**本文不含任何恢复时长承诺**；表中「恢复时间量级」一列只写**相对表述**。
>
> **互链**：[`runbook-l1.md`](runbook-l1.md)（日常操作）、[`runbook-l2.md`](runbook-l2.md)（深度排障）、[`fault-demarcation.md`](fault-demarcation.md)（定界）、[`backup-restore.md`](backup-restore.md)（有状态组件维护窗口）、[`../product/responsibility-matrix.md`](../product/responsibility-matrix.md)（RACI）。
>
> **状态说明**：上游文档中的过期「未创建」标注已于 2026-10-10 统一清理；本文件所述的 blocked 状态（**M8 真实集群环境 / 演练**）**仍然成立**。

---

## 1. 边界声明（三段式）

| 段 | 内容 |
|---|---|
| **我方负责** | ① ISC 触发后的**业务判决**（`decide()` 纯函数，可重放）；② **业务规则灰度**：运行态覆盖的判定粒度固定为**号段 + 稳定哈希百分比**（ADR-0021，`in_bucket` 用 `fnv1a32(call_id) % 100`，**按 Call-ID 判定、幂等**）；③ **摘流 / 回退的执行**（draining、Pod 级摘除、镜像回退）；④ **配置版本回滚**（变更单状态机，ADR-0006）；⑤ 提供给对方对齐的**字段契约与日志检索键** |
| **对方负责** | ① **iFC 签约与触发配置**（按号段 / 百分比触发 ISC）—— OP-NET **A/R**、OP-HSS R；② trunk 建立、拓扑与优先级、摘流动作 —— OP-SBC；③ 呼叫是否进入本 AS 的决定权；④ 变更窗口批准（网络侧窗口 A 角是 OP-NET） |
| **联合动作** | ① iFC 触发比例与 AS 侧 override 比例的**联合标定**；② 灰度期行为分布的联合观测；③ 摘流与放行的联合验证；④ 回退演练与证据互认（§5） |

**一句话**：AS 侧只拥有「ISC 触发之后的判决、摘流与回退」；触发之前的接入决策（iFC 签约、触发、灰度）全部在OP-NET / OP-HSS / OP-SBC 侧。

---

## 2. 回退层次

**层次由轻到重**。选择原则：**先用影响面最小、最不需要对方配合的一层**；只有当上一层无法达成目标时才下沉一层。**下沉不等于升级**—— L4 摘流仍可由 AS-Vendor决策 + OP-NOC 执行。

| 层次 | 触发条件 | 动作 | 影响面 | 恢复时间量级（**相对表述，不含时长承诺**） | 依赖 |
|---|---|---|---|---|---|
| **L0** 业务规则灰度收窄 | 新判决逻辑在灰度池内行为不符预期，但仅限部分号段 | 通过 **runtime override** 收窄：按**号段**置`enabled=false`，或把稳定哈希**百分比**调到更小 | 只影响override 覆盖的号段 / 比例；**热判定、不重启** | 最短（热判定，下一次判决即生效，无需重启、无需对方动作） | override 的**当前实现状态见下方注记** |
| **L1** 变更单回滚 | 配置版本 vN 生效后行为异常 | 控制台 / config-service 发起 `roll_back` → 变更单进入 `ROLLED_BACK`（终态），生效标记回退一个不可变版本行（vN-1）；灰度分发随之回退 | 全部实例的该配置版本；**审计链完整保留** | 短（走既有分发链路 + 健康检查）；**健康检查失败会自动回滚**（见 §2.1） | 不需要对方配合 |
| **L2** AS 业务逻辑整体关闭 / 摘流 | AS 业务逻辑本身判错，影响面覆盖全部号段 | 用**部署级总开关**关闭 AS 业务逻辑，呼叫**放行到下一环节**（即 AS 侧不再改写 / 不再拒绝） | 全部用例、全部号段 | 比 L1 重（仍走变更流水线，**不是**独立通道）；**不得**用 L0 覆盖全部号段来代替总开关 | 部署级总开关走 ADR-0006 变更流水线（ADR-0020）；**实现现状见 §2.2** |
| **L3** 镜像版本回退 | 新镜像引入缺陷、或与规则 schema 不兼容 | `helm history` → `helm rollback <revision>` → `kubectl rollout status`（原文见 §2.3） | 全部 Pod 的镜像 / manifest；**draining 在退出路径上生效**（ADR-0009） | 最重（要走完整的 Pod 替换周期，且存量呼叫须自然跑完） | 需要维护窗口 |
| **L4** 摘流（Pod 级 draining） | 缩容 / 升级 / 实例异常，需要把实例移出轮转 | readiness 转 `503` → Endpoint 摘流 → 等 `as_active_calls` 归零 → 删除 Pod（**不得 SIGKILL**） | 单个 Pod / 单个用例 | 与存量呼叫时长相关，**不可压缩**（ISSU = draining，ADR-0009） | 不需要对方配合；**不需要在途状态迁移** |

### 2.1 L1 的自动回滚语义（照抄实现）

灰度分发过程中**任一批次健康检查不通过即自动回滚**：

- 分发状态机：`pending` → `in_progress` → `completed`；异常时 `rolled_back`（`services/config-service/src/as_config_service/distributor.py`）。
- 自动回滚原因常量：`_AUTOMATIC_ROLLBACK_REASON = "health check failed"`（`distributor.py`）。
- 回滚目标：`rolled_back_to` 必须**紧邻计划版本的前一个版本**（`distribution_store.py` 校验）。
- 变更单侧：`APPLIED | DISTRIBUTING --roll_back--> ROLLED_BACK`（`change_order.py`）；`REJECTED` / `APPLIED` / `ROLLED_BACK` 是**终态**。
- **自动回滚仍需人工确认**：NOTES.txt §3a 明确「always needs a human to confirm afterwards」。

### 2.2 L2 的实现现状（如实说明，不夸大）

- **部署级总开关（layer ①）**：ADR-0020 定义为「部署级总开关 + 运行态细粒度覆盖」两层。实现上，开关以 `ToggleDTO` 形式**搭配置变更单的同一趟车**（`ConfigBundle.toggles` → `toggle_deployment()` → `gating.is_enabled`），**不新开通道**；`is_enabled` **fail-closed**（未注册的开关名求值为 `False`）。其「开 / 关两态」由变更单流水线端到端测试覆盖。
- **运行态细粒度覆盖（layer ②）**：判定函数 `match_override`（`platform/src/as_platform/gating/overrides.py`）已实现为**纯函数**，粒度为号段 + 稳定哈希百分比、最长前缀优先、显式 `enabled=false` 高于百分比、未覆盖返回 `None`（fail-closed）。⚠️ **当前生产路径尚无该模块的调用方**（仅单测覆盖），控制台 live 范围也只有**被叫 + 前缀规则**。
- **因此**：L0 与 L2 的**机制与判定语义成立、治理通道成立**，但**「一键秒级关闭 AS 业务逻辑、放行到下一环节」是产品包装计划里的措辞，不是已交付、已验收的运维动作**。落地前需先补：控制台 / API 上的开关与override 管理入口、生产路径接线、以及开 / 关两态的验收证据。**不得**在本文把它写成可当场执行的按钮。
- **L2 的边界**：关闭 AS 业务逻辑只改变 **AS 侧行为**；**把呼叫从本 AS 引走仍需 S-SBC / S-CSCF 侧配合**（G-P1-10）。

### 2.3 L3 的回退命令（原文照抄 `deploy/helm/templates/NOTES.txt` §3）

NOTES.txt §3 明确「两种东西都叫 rollback，不要混淆」：**(a) 配置回滚**走变更单（= L1）；**(b) 镜像 / manifest 回滚** revert Helm release 让 Deployment 滚回，**draining 在退出路径上生效**（ADR-0009）：

```sh
helm -n <ns> history <release>
helm -n <ns> rollback <release> <revision>
kubectl -n <ns> rollout status deploy --selector app.kubernetes.io/part-of=3rdparty-as
```

> 原文的 Helm 模板占位符 `{{ include "as.namespace" . }}` / `{{ .Release.Name }}` 在此写成 `<ns>` / `<release>`。⚠️ NOTES.txt §3b 提到 `ASConfigRollbackTriggered` 会告警，但 `deploy/alerts/as-alerts.yaml` **里没有这条规则**（`deploy/alerts/README.md` 明确列为 deferred）—— 按名去查告警系统会一无所获。

### 2.4 L4 的摘流四步

命令原文见 [`runbook-l1.md`](runbook-l1.md) §3.1 与 [`../acceptance/m5-downscale-runbook.md`](../acceptance/m5-downscale-runbook.md)：① 计算 `plan_scale_down`；② 对 removable 中每个 Pod，`kubectl delete pod` 前确认 `active_calls==0`；③ 对仍承载呼叫的 Pod **不删除**，等待自然结束，readiness 在 `request_terminate` 后为 `503`，Endpoint 应摘流；④ 若 `blocked`，仅缩减 removable 子集或等待。**不得 SIGKILL。**

---

## 3. 与 S-CSCF / HSS 侧 iFC 灰度的配合

> **本章是本手册的核心边界。** 按号段 / 百分比的 **iFC 触发**在 S-CSCF / HSS 侧配置，**我方不实现 iFC**；本章定义的是**配合接口、联合验证点与失败回退**。

### 3.1 配合接口

| 接口项 | 我方提供 | 对方提供 |
|---|---|---|
| **关联键** | 入腿 `inbound_call_id` ↔ 出腿 `outgoing_call_id`（B2BUA 两腿 Call-ID 不同，REQ-F-2） | 触发侧的呼叫标识（Call-ID 或等价） |
| **判定粒度** | AS 侧 override：**号段前缀 + 稳定哈希百分比**（ADR-0021） | iFC 侧触发粒度：**号段 / 百分比**（G-P0-5） |
| **生效观测** | `as_active_calls`、判决结果分布（404/ 603 占比）、`CONFIG_VERSION` | 触发量观测、触发成功率 |
| **摘流信号** | draining 期间 readiness `503` + Endpoint 摘除（AS 侧只对自己摘） | 对端停止向本 AS 引发的动作 |
| **对齐方式** | 双方**各自抓本侧**；TLS 解密各方自理，**密钥不跨方共享** | 同左 |

### 3.2 联合阶段表

| 阶段 | 对方动作（S-CSCF / HSS / S-SBC） | 我方动作（AS-Vendor） | 联合验证点 | 失败时的回退 |
|---|---|---|---|---|
| **0. 前置对齐** | 提供 iFC 侧当前触发粒度与生效范围 | 提供 AS 侧 override 粒度与当前生效配置版本 | 双方对「哪些号段处于灰度中」的理解一致 | 不一致 → **停止变更**；先对齐口径，不动任何一侧 |
| **1. 灰度比例调整** | 调整 iFC 触发比例 / 号段 | 观察 `as_active_calls` 与判决结果分布的变化 | AS 侧入腿呼叫量与对方触发量**方向一致、量级相当**（**相对比较，不预设绝对数字**） | 方向不一致 → 先查关联键对齐，不调AS 侧 override |
| **2. AS 侧业务灰度** | 无（AS 侧 override 由我方自管） | 按号段 / 百分比设置或收窄 override | 同一号段内不同 `call_id` 落不同桶 —— **这是设计预期**（`FNV-1a 32-bit(call_id)`）；先看 `call_id` 落在哪个桶 | 命中判断不了 → 用 `call_id` + 生效规则版本 + 判决路径判定；**不用 `as_rule_hits_total`**（无生产调用方） |
| **3. 摘流** | 停止向本 AS 引入新呼叫（iFC / trunk 侧动作） | Pod 级 draining：readiness `503` → Endpoint 摘除 → 等 `active_calls` 归零 | `as_downscale_removable` 与 `as_active_calls` 的收敛过程；存量呼叫自然结束 | 不收敛 → 不删 Pod，转 L2 / L3（§2） |
| **4. 呼叫放行** | 呼叫按原路径继续 | AS 侧业务逻辑关闭时**不改写、不拒绝**（L2 的语义） | 呼叫在 AS 侧**未被拒绝**、未被改写 | AS 侧仍改写 → override / 总开关未生效，回 §2.2 与变更流水线 |
| **5. 收尾** | 确认 iFC 侧配置稳定 | 确认 `CONFIG_VERSION` 各副本一致、审计行已产生 | 双方各留一份变更记录 | — |

### 3.3 联合验证清单（可勾选）

- [ ] 对方已确认 iFC 侧当前生效的触发号段 / 比例，并提供书面记录。
- [ ] 我方已确认 AS 侧 override 当前生效的号段 / 比例，`CONFIG_VERSION` 各副本**一致**。
- [ ] 双方时间基准已对齐（不是「看起来同时」）。
- [ ] 灰度比例调整后，AS 侧入腿呼叫量与对方触发量方向一致（**相对表述，不预设绝对数值**）。
- [ ] 判决结果分布（404 / 603 占比）变化可解释，且404 / 603 被当作**业务判决**而非故障处理。
- [ ] 摘流期间 AS 侧 readiness 为 `503`、Endpoint 已摘除，`as_active_calls` 呈收敛趋势。
- [ ] 呼叫放行验证通过：AS 侧不再改写、不再拒绝。
- [ ] 双方各留一份变更记录与时间线，入档路径 `artifacts/<milestone>/<YYYY-MM-DD>/`（按维护者指定目录）。
- [ ] 脱敏检查：无密码 / token / cookie / 私钥，无真实抓包（`AGENT.md` §11 / §13）。

> ⚠️ **风险注记（G-P1-10）**：以上清单**依赖 S-CSCF 侧配合窗口与真实集群演练**。当前 **7.2d仍 blocked**、**无真实集群演练记录**、**M8 退出签字搁置**。本文给出的是**可执行的流程与验证点**，**不是**已演练通过的结论。

---

## 4. 变更窗口与决策人

| 项 | 内容 |
|---|---|
| **谁决策回退** | **AS 侧决策 + OP-NOC 执行 + OP-NET 配合**（RACI §5.2）。AS-Vendor 对 L0–L4 的选择负责；**呼叫是否进入本 AS** 不在我方决策范围 |
| **网络侧窗口** | iFC 签约 / 触发灰度、trunk 优先级、摘流的提单与审批在**OP-NET**，**AS 侧不代提、不代批** |
| **有状态组件窗口的特殊性** | PostgreSQL / Redis 维护需 OP-NOC 批准窗口。⚠️ **Redis 维护窗口内预期出现短暂运行态不可用** —— 在途呼叫状态（会话 / dialog / 反诈速率窗口）都在 Redis，Redis 不可用即在途呼叫无法维持。**这不是缺陷，是已知窗口行为**；处置与恢复见 [`backup-restore.md`](backup-restore.md) |
| **PG / Redis 拓扑提醒** | chart 内建的是**单副本**，**不是 HA**；Redis HA 仍是未决项 **O5 / D3**（Sentinel）；生产 PG HA 由客户拥有（ADR-0008 / ADR-0026） |
| **回退后复核项** | ① 生效配置版本回退到位（`CONFIG_VERSION` 各副本一致）；② 判决结果分布回到预期；③ `as_active_calls` 与 draining 状态收敛；④ **审计行已产生**（append-only，回退本身也留痕）；⑤ 变更单进入终态且**不可再动**；⑥ 双方时间线归档 |
| **回退不是「一键零影响」** | L0 / L2 只改变 AS 侧行为；**把呼叫从本 AS 引走仍需 S-SBC / S-CSCF 侧配合** |

---

## 5. 回退演练记录模板

**当前状态：⚠️ 无真实集群演练记录。** 下表为模板，**当前没有任何一行已填数据**。M8 **7.2d blocked**、M8 退出签字搁置；iFC 侧配合窗口未安排（G-P1-10）。**不得**用 kind / compose / `testbed/` 的仿真结果充当演练记录（ADR-0014：testbed 非 v1 交付物）。

| 字段 | 填写要求 |
|---|---|
| **日期** | 演练实际执行日期（含时区） |
| **环境** | 集群标识 / 命名空间 / chart release；⚠️ **当前无真实集群** |
| **版本 from → to** | 回退前的版本 → 回退后的版本（配置版本填 `CONFIG_VERSION` / 变更单号；镜像版本填 `helm history` 的 revision） |
| **触发原因** | 现象 + 判定依据；写明是哪个剧本（§2 的 L0–L4 哪一层） |
| **层次** | L0 / L1 / L2 / L3 / L4 |
| **双方参与人** | AS-Vendor（决策人 / 执行人）、OP-NOC（执行）、OP-NET / OP-SBC（配合）；**姓名与角色由各方自行记录**，本模板不代填 |
| **观察项** | 逐条勾选 §3.3 联合验证清单 + §4 回退后复核项 |
| **结果** | 通过 / 有条件通过 / 不通过；**证据路径**（`artifacts/...`，脱敏后） |
| **遗留问题** | 未闭合项、责任方、需要谁裁决 |

> 记录纪律：按 `AGENT.md` §3.2/ §3.3，演练记录属证据，**必须有对应 review record** 才算走完文档链；记录本身**不构成验收结论**。

---

## 6. 未决与阻塞

| 项 | 阻塞源 | 对本文的影响 | 责任方 |
|---|---|---|---|
| **iFC 侧灰度联调** | OP-NET / OP-HSS 配置（G-P0-5 / G-P1-10） | §3 全章**无法端到端闭环**；AS 侧只能自证 override 生效 | OP-NET / OP-HSS |
| **真实集群演练** | M8 **7.2d blocked**、退出签字搁置 | §5 **无任何已填记录**；§2 各层的时序均为**未演练**表述 | 维护者 + OP-NOC |
| **L2 部署级总开关的运维入口** | 控制台 live 范围只有被叫 + 前缀规则；override 生产路径无调用方 | §2.2：「一键关闭」目前是**机制成立、入口未交付** | AS-Vendor（M4b / M8） |
| **L0 runtime override 生产接线** | `match_override` 仅单测覆盖 | §2 的 L0 行**当前不可当场执行** | AS-Vendor |
| **真实 SIP 不掉呼叫** | G-P1-1；draining 证据为**模拟** `active_calls` | §2.4 与 §3.2 阶段 3 的收敛性**未验收** | AS-Vendor（M7 / M8） |
| **E1 / E4 / E5** | M8 验收（O2 / O3） | L3 回退后的行为判定缺生产证据 | AS-Vendor |
| **O5 / D3（容灾 / Redis Sentinel）** | 客户 SLA | §4 的 PG / Redis 窗口分级无法定稿 | OP-NET + 维护者 |
| **告警侧确认** | `ASConfigRollbackTriggered` / `ASConfigDrift` 在 `as-alerts.yaml` 中**不存在** | 回退后**没有告警证据**可自动留痕，只能人工记录 | AS-Vendor（M6 后 / O1 裁决后另定） |
| **本文评审状态** | `AGENT.md` §3.3 需独立 review record | **本文尚无 review record**，待维护者评审 | 维护者 |