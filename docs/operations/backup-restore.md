# 备份恢复方案（Backup & Restore）— In-house IMS Application Server（文档暂用名）

> **交付物归属**：[`../product-packaging-plan.md`](../product-packaging-plan.md) §1 第二批 **2.5 备份恢复方案 + 演练记录**。按该计划 §3.2，本交付物属 **B 类**：**依赖真实集群环境，M8 真实集群证据当前搁置（7.2d 仍 blocked）**，**M8 退出签字仍搁置**（评审 **G-P1-10**）。本文给出**方案与记录模板**，**不是**已演练的结论。
>
> **⚠️ Chart 不自带备份 Job。** chart 只提供**一次性 schema 迁移 Job**（`stateStores.migrateJob`），**那不是备份**。备份排期由**客户的备份工具**承担（Velero、cron Job，或 HA 场景下的集群外 WAL 归档）。
>
> **⚠️ 内建 Redis / PostgreSQL 是单副本，不是 HA。** Redis HA 仍是未决项 **O5 / D3**（Sentinel）；生产 PG HA 由**客户拥有**（Patroni、云 RDS，或改用外部 `postgres.host` 并设 `stateStores.enabled=false`）。ADR-0008 定的是**冗余口径**（站点内 N+1零单点、跨站点 1+1 温备非双活），**HA 拓扑由客户与 ADR-0008 共同决定**。
>
> **⚠️ 本文不含任何容量数字**：无 CPS / CAPS / BHCA / 并发 / 吞吐 / 时延 / 百分比容量，也不引用 M6 dev-host 数字（O1 未裁决，`AGENT.md` §2）。本文亦不含备份窗口的时长承诺。
>
> **⚠️ RPO / RTO 需与客户共同记录，本文不单方面给数值。** 呼叫轨迹的**保留期**与**存储选型**为未决项 **O4 / D5**，**本文不写任何保留天数**。
>
> **互链**：[`runbook-l1.md`](runbook-l1.md) §3.5（备份与恢复日常命令）、[`runbook-l2.md`](runbook-l2.md) §6（数据库与迁移排障）、[`rollback-playbook.md`](rollback-playbook.md) §4（有状态组件维护窗口）、[`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §2行 ⑪ / §5.1（备份与恢复 RACI、窗口协作）、[`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md)（原件，**不删除、不移动、不改写**）。
>
> **状态说明**：上游文档中的过期「未创建」标注已于 2026-10-10 统一清理；本文件所述的 blocked 状态（**真实集群环境 / 演练记录**）**仍然成立**。

---

## 1. 数据分类与备份对象

| 数据 | 存储 | 丢失后果 | 备份必要性 | 现状 |
|---|---|---|---|---|
| **治理态**：规则版本、变更单、审批记录、审计（schema `as_config` / `console_audit`，表 `console_audit`）、控制台用户 | **PostgreSQL**（chart 内建单副本 StatefulSet，或客户外部 PG） | **审计链断裂**：变更单与审批人不可追溯，规则版本历史丢失，审计表 append-only 语义被破坏 —— 这类事件须**同时通知 OP-SEC** | **必须备份** | 命令见 §2；**排期由客户备份工具承担**；PG HA 拓扑由客户 + ADR-0008 决定 |
| **运行态**：会话 / dialog 状态、反诈速率窗口 | **Redis**（chart 内建单副本） | **在途呼叫失败与计数丢失** —— 丢失 ≈ 呼叫失败（ADR-0007）；AS 侧**不能主动摘在途呼叫**，所以恢复路径尤其依赖对方不摘 | 备份策略**由客户与维护者共同决定**（ADR-0007 把Redis 定位为可备份项，但**不强制**） | chart 单 Redis **不是 HA**；Sentinel 拓扑未决 **O5 / D3**；可用性探针仅在 `REDIS_URL` 非空时才产出 `as_state_store_available` |
| **呼叫轨迹**（按 Call-ID 的投诉追溯与反诈举证） | **选型未决** | 待裁决 | **待裁决** | **保留期 O4 未决**、**存储选型 D5 未决**（PostgreSQL 还是独立的短保留存储）。本文**只写「待裁决」，不写保留天数、不写存储方案** |
| **证书与凭据** | 客户 PKI / k8s Secret | 密文不丢失即无影响 | **不入备份脚本** | `tls.secretName` 指向客户 Secret（`tls.crt` / `tls.key` / `ca.crt`）；`AS_CONFIG_DSN`、审计 HMAC key 走 Secret。**备份脚本不得导出 Secret 内容**；恢复时由客户按其 PKI 流程重新下发 |

> **恢复顺序的硬约束**：治理态（PG）与运行态（Redis）**不是同构的**。Redis 丢失 ≈ 在途呼叫失败；PostgreSQL 丢失 ≈ 审计链断裂。**先恢复 PG、再恢复 Redis、最后复核控制台**（§4）。

---

## 2. 备份策略

### 2.1 PostgreSQL（治理态 —— 必须保留审计链）

**命令原文（照抄 [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Backup & restore）**

```sh
kubectl -n <ns> exec as-3rdparty-as-postgres-0 -- \
  pg_dump -U postgres -d as_config -Fc -f /tmp/as_config.dump
kubectl -n <ns> cp as-3rdparty-as-postgres-0:/tmp/as_config.dump ./as_config.dump
```

**前置与期望**：治理PG 可达；使用具备备份权限的角色；`kubectl cp` 需要 Pod 内有 `pg_dump`（PostgreSQL 官方镜像有）。期望 `./as_config.dump` 落盘且**大小非零**。

**调度**：**chart 不自带备份 Job**。排期由**客户备份工具**承担 —— Velero、cron Job，或 HA 场景下的**集群外 WAL 归档**。**RPO / RTO 与客户共同记录**；本文不代填数值（`AGENT.md` §2 与本文状态块）。

**HA 场景的替代路径**：外部 `postgres.host` + `stateStores.enabled=false`（客户自管 PG），或客户侧 Patroni / 云 RDS。

### 2.2 Redis（运行态 —— 策略由客户共同决定）

- ADR-0007 把 Redis 定位为运行态存储：**丢失 ≈ 呼叫失败**，因此备份为**可选项**而非强制项；但**RPO / RTO 仍须与客户共同记录**。
- 客户若选择备份：按其 Redis 持久化策略（RDB / AOF）与客户备份工具执行；**本文不代客户裁决**。
- ⚠️ **Redis 维护窗口内预期出现短暂运行态不可用** —— 在途呼叫状态全在 Redis。这是**已知窗口行为**，不是缺陷；处置见 [`rollback-playbook.md`](rollback-playbook.md) §4。

### 2.3 不进入备份范围的东西

| 不备份 | 理由 |
|---|---|
| **CDR / 话单** | 不采集、不投递、不归档（ADR-0017）。呼叫轨迹**不是**话单 |
| **媒体 / RTP** | 不做媒体（ADR-0004）：没有 RTP、没有转码、没有 DTMF、没有 MRF |
| **Secret 内容**（私钥、`AS_CONFIG_DSN`、审计 HMAC key） | 由客户 PKI / Secret 管理流程重新下发；`AGENT.md` §11/ §13禁止提交密钥 |
| **Diameter Sh 侧数据** | 不做 Sh（`AGENT.md` §2）；无此类数据 |
| **LI / IRI 材料** | 不做 LI（ADR-0016），**不为其预留任何采集点** |

---

## 3. PostgreSQL HA / PITR 三档

> 原文照抄 [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §PostgreSQL HA / PITR。chart 发的是**单副本** StatefulSet；**生产 HA 由客户拥有**。下表是**工程建议**，**不是**对客户 topologies 的裁决。

| 档 | 最低期望 |
|---|---|
| **Lab / kind** | emptyDir 或单 PVC；**备份可选** |
| **On-prem prod** | 记录 **RPO/RTO**（**与客户共同记录**）；用 `pg_dump -Fc`（见 §2.1）或 WAL 归档到**集群外**存储；故障切换由客户的 Postgres HA（Patroni、云 RDS 等）承担，**或**改用外部 `postgres.host` 并设 `stateStores.enabled=false` |
| **Restore drill** | 把 dump 恢复到一个**新实例**；若 schema 版本变了，**重跑 `as-config-migrate`**；把 runtime Secret 指向新主机（步骤见 §4） |

**Redis HA 仍是 O5 / D3（Sentinel）；chart 单 Redis 不是 HA。**

---

## 4. 恢复步骤（Restore drill）

**前置**：§2.1 已拿到可用 dump；治理库可达；**owner DSN 只在可信主机或一次性 Job 中使用，绝不进 runtime Pod / Deployment**（ADR-0006；L2 §6）。

| 步 | 动作 | 验证方法 |
|---|---|---|
| **1. 恢复 dump 到新实例** | 在**新**实例上恢复（不覆盖原实例，原实例保留作回退参照）；DSN host 用**新主机名** | dump 恢复无错误；新实例上 `as_config` 与 `console_audit` 两个 schema 均存在 |
| **2. 核对角色** | 三角色：`as_config_owner`（owner）/ `as_config_web`（runtime Pod 用，**非owner**）/ `as_config_runtime`（`NOLOGIN` 最小权限，审计 append-only 相关） | runtime Secret里的 `AS_CONFIG_DSN` 用的是 **`as_config_web`**，**不是** owner；`AS_AUDIT_RESOURCE_HMAC_KEY_B64` 存在 |
| **3. schema 版本变化时重跑迁移** | 每个 schema 版本跑一次（命令原文见下）；**库为空时必须先跑** | `as-config-migrate` 成功返回；重复执行幂等 |
| **4. 把 runtime Secret 指向新 host** | 更新 Secret 指向新实例（Secret 内容**不由本文提供**，走客户 Secret 管理流程） | 各实例重启/热加载后 `printenv CONFIG_VERSION` 有值且**各副本一致** |
| **5. 复核控制台登录** | 浏览器经**HTTPS**（同源）登录控制台 | 登录成功、可看到审批队列；⚠️ **不保存凭据**，不把会话 cookie 截图入档 |
| **6. 复核审计可查** | 导出审计记录 | 输出无 password / token；runtime 角色对 audit 表的 INSERT/UPDATE/DELETE/TRUNCATE **被拒绝**（append-only，fail-closed） |
| **7. 复核 Redis 侧** | 按§1 的恢复顺序，Redis 在 PG 之后 | `as_state_store_available{use_case}` 回到 `1`；⚠️ 未配置 `REDIS_URL` 时**该序列不存在（不是 0）** |

**迁移命令原文（每个 schema 版本跑一次；照抄原件）**

```sh
kubectl -n <ns> port-forward pod/as-3rdparty-as-postgres-0 15432:5432
export AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:<password>@127.0.0.1:15432/as_config"
export AS_CONFIG_RUNTIME_ROLE=as_config_runtime
export AS_AUDIT_SCHEMA=console_audit
export AS_CONFIG_SCHEMA=as_config
uv run as-config-migrate
```

**Helm migrate Job（生产 / 可重复）** —— Secret `as-config-migrate-owner` 的键 `AS_CONFIG_OWNER_DSN`（仅 owner 登录）：

```sh
helm upgrade --install as deploy/helm -f deploy/helm/values-onprem.example.yaml ...
kubectl -n <ns> delete job/as-3rdparty-as-config-migrate --ignore-not-found
kubectl -n <ns> wait --for=condition=complete job/as-3rdparty-as-config-migrate --timeout=300s
```

⚠️ **Job 复用坑**：同名 Job 不重建 → **必须先 `delete job ... --ignore-not-found` 再 `wait`**，否则会**等到一个已完成的旧 Job 而误判成功**。

---

## 5. 恢复演练记录模板

**当前状态：⚠️ 无真实集群演练记录。** 下表为模板，**当前没有任何一行已填数据**。M8 **7.2d blocked**、退出签字搁置（G-P1-10）。⚠️ **耗时一栏由演练方填写，本文不预设任何数值**（也不给时长承诺）。

| 字段 | 填写要求 |
|---|---|
| **日期** | 演练实际执行日期（含时区） |
| **范围** | 治理态 / 运行态 / 两者；是否含控制台复核 |
| **备份来源** | dump 文件标识 / WAL 归档批次 / 备份工具与调度（**不含任何凭据**） |
| **恢复目标** | 新实例的主机标识；**不覆盖原实例** |
| **耗时** | **由演练方填写**；本文不预设、不承诺 |
| **校验项** | §4 的 7 步逐条勾选（含 `CONFIG_VERSION` 一致性、控制台 HTTPS 登录、审计 append-only 拒绝验证） |
| **结果** | 通过 / 有条件通过 / 不通过；证据路径（`artifacts/<milestone>/<YYYY-MM-DD>/`，脱敏后） |
| **遗留问题** | 未闭合项、责任方、需要谁裁决 |

> **记录纪律**：演练记录属证据，按 `AGENT.md` §3.2 / §3.3 需配套独立 review record 才算走完文档链；记录**不构成验收结论**。kind / compose / `testbed/` 的仿真结果**不得**充当演练记录（ADR-0014：testbed 非 v1 交付物）。

---

## 6. 边界与不做的事

| 不做 | 理由 |
|---|---|
| **CDR 归档 / 计费备份** | 不做 CDR：不采集、不投递、不归档、不批价（ADR-0017）。呼叫轨迹**不是**话单 |
| **媒体备份** | 不做媒体：无 RTP、无转码、无 DTMF、没有 MRF、没有媒体锚定（ADR-0004） |
| **Diameter Sh 侧数据备份** | 不做 Sh —— 数据来自我们自己的数据面（`AGENT.md` §2） |
| **LI / IRI 留存** | 不做 LI：IRI 属网内网元职能，ADR-0016 **不为其预留任何采集点** |
| **在本文写保留天数** | 呼叫轨迹保留期 **O4 未决**、存储选型 **D5 未决**；**保留期限由客户（OP-SEC）与维护者共同裁决后填入**，本文不硬编码 |
| **在本文写 RPO / RTO 数值** | **由客户与维护者共同记录**；本文不单方面给数值 |
| **在本文写恢复时长承诺** | 本文只给**步骤与验证方法**；实际耗时由演练方填入 §5 |
| **自带备份 Job / 第二套安装形态** | chart 不自带备份 Job；生产形态只有 Helm（ADR-0013） |

---

## 7. 未决与阻塞

| 项 | 阻塞源 | 对本文的影响 | 责任方 |
|---|---|---|---|
| **真实集群恢复演练** | M8 **7.2d blocked**、退出签字搁置（G-P1-10） | §4 只有**步骤与验证方法**，**无一次已执行的演练**；§5 **无任何已填记录** | 维护者 + OP-NOC |
| **PG HA 拓扑** | 由客户拥有（ADR-0008 / ADR-0026）；容灾等级 **O5** 未决 | §3 的「On-prem prod」档是**工程建议**，不是对客户拓扑的裁决 | OP-NET（客户 SLA）+ 维护者 |
| **Redis HA（Sentinel）** | **O5 / D3** 未决 | §1 运行态的丢失影响可判定，但**恢复路径**取决于客户最终选定的拓扑 | OP-NET + 维护者 |
| **呼叫轨迹保留期（O4）与存储选型（D5）** | 客户合规要求 | §1 的轨迹行**只能写「待裁决」**；**本文不得出现保留天数** | **OP-SEC**（A/R）+ AS-Vendor |
| **ADR-0008 冗余演练** | 矩阵中 **blocked** | 跨站点 **1+1 温备（非双活）** 的切换与恢复剧本**未编写**；备站无在途呼叫 | OP-NOC + OP-NET |
| **E5 / REQ-NF-1（状态外置与恢复）** | REQ-NF-1 签收归 M8（D-2 defer） | 呼叫级 checkpoint 恢复路径只有**工程切片证据**，本文只覆盖 **PG / Redis 两个存储**的恢复 | AS-Vendor |
| **M5D 10 项 defer** | M5 REQ 级不通过构成项 | 部分控制面能力仍defer，影响恢复后的复核完整性 | 维护者 |
| **RPO / RTO 记录** | 需与客户共同记录 | §2.1 / §2.2 的数值栏**由客户与维护者填入**，本文留空 | AS-Vendor + OP-NOC |
| **本文评审状态** | `AGENT.md` §3.3 需独立 review record | **本文尚无 review record**，待维护者评审 | 维护者 |