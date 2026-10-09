# 运维文档（Operations）— In-house IMS Application Server（文档暂用名）

> **状态**：本目录为**新增**运维文档目录（2026-10-09 创建，对应 `docs/product-packaging-plan.md` §2 与评审意见 **G-P2-1**）。目录内容是**归集与重组** —— 把原先散在 `docs/acceptance/` 的验收态 runbook 重新组织为面向值班的操作正文。
>
> **原件保留不动**：`docs/acceptance/*-runbook.md` **不删除、不移动、不改写**，仍是历史原件与审计追溯源。本目录只做「索引 + 链接 + 面向值班的操作正文」。
>
> **证据口径（重要）**：本目录内容属**工程切片证据**。**M5 工程关门 ≠ REQ 验收**（`docs/acceptance/report.md` §0.4 B-2）；**M8 RC 就绪 ≠ 关门**（`report.md` §0.1）。签收矩阵现状为 pass 9 / fail 0 / **blocked 12** / n-a 4 / **open 24**（`report.md` §0.5）—— 本目录任何一句话都不得读作"已验收"。
>
> **零容量数字**：本目录**不含任何容量数字**（无 CPS / CAPS / BHCA / 并发 / 吞吐 / 时延 / 百分比容量）。O1 容量目标**未裁决**，`AGENT.md` §2 禁止在 M6 真实 socket 实测前发布任何此类数字。M6 dev-host 测量是内部参考、非对外 O1/SLA，本目录**不引用**。
>
> **范围之外**：**不做 Diameter Sh**、**不做 CDR / 计费**、**不做媒体**（`AGENT.md` §2）。本目录因此**不含**任何 Sh 相关告警、面板或 CDR 话单相关内容。

---

## 1. 读者与分层

| 分册 | 读者 | 回答的问题 | 深度 |
|---|---|---|---|
| [`runbook-l1.md`](runbook-l1.md) | **L1 / NOC 值班** | 「现在该看什么、看到什么算异常、第一步做什么、什么时候叫人」 | 日常巡检 + 告警首响应 + 常见操作 |
| [`runbook-l2.md`](runbook-l2.md) | **L2 / 二线工程** | 「为什么是这个现象、AS 侧能不能自证、故障归属是哪一方、怎么取证」 | 深度排障 + 信令/日志取证 + 归属定界 |

**升级路径**：L1 → L2 → 维护者。

- **L1 → L2**：命中本册中标注「升级 L2」的任一条件；或 L1 的四步排查走完仍不能判定归属。
- **L2 → 维护者**：需要裁决产品口径或改动未决项（O1 / O4 / O5 / D3 / D5 等），或需要推翻既有裁决。L2 **不得**自行修改未决项（`AGENT.md` §15）。

---

## 2. 目录内容

| 文件 | 内容 | 读者 | 来源 runbook（原件保留） | 状态 |
|---|---|---|---|---|
| [`runbook-l1.md`](runbook-l1.md) | 每日巡检清单、10 条告警（3 个组）的 L1 处置、手工缩容 / 滚动升级 / 控制台操作 / 证书热更新 / 备份恢复日常命令、升级与求助、脱敏规则 | L1 / NOC | [`../acceptance/m5-downscale-runbook.md`](../acceptance/m5-downscale-runbook.md)、[`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md)、[`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md)、[`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml) | 已创建（本次交付） |
| [`runbook-l2.md`](runbook-l2.md) | 排障方法论、日志字段取证契约、信令抓包对齐、7 类分层故障树、变更与灰度排障、迁移排障、签收环境准备、误导性坑位清单 | L2 / 二线 | [`../acceptance/m8-resip-runtime-log-contract.md`](../acceptance/m8-resip-runtime-log-contract.md)、[`../acceptance/m8-native-consistency-runbook.md`](../acceptance/m8-native-consistency-runbook.md)、同 L1 来源 | 已创建（本次交付） |

除上表两册外，本目录的其余交付物（故障定界、回退、备份恢复、告警-动作对照表、Grafana 看板）**均已落盘**，与其内容状态见 §4。

---

## 3. 归集映射

「归集方式」三档：**重写操作正文** = 面向值班重写、命令原文照抄；**索引链接** = 只给指针与口径，不重写；**摘要** = 保留结论与状态，不搬过程。

| 现有验收文档 | 归入本目录的哪一节 | 归集方式 |
|---|---|---|
| [`../acceptance/m5-downscale-runbook.md`](../acceptance/m5-downscale-runbook.md) | L1 §3.1 手工缩容与摘流；L2 §4.7 缩容不掉话 / draining 不收敛 | 重写操作正文（`plan_scale_down` 判据、四步顺序、draining readiness 503 照抄） |
| [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) | L1 §3.2 滚动升级、§3.5 备份与恢复日常命令；L2 §6 数据库与迁移排障、§4.6 config-service CrashLoop | 重写操作正文（`helm upgrade` 参数面、`as-config-migrate` owner DSN、`pg_dump -Fc` 两句照抄）+ 摘要（PG HA/PITR 三档、Restore drill、升级纪律） |
| [`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md) | L1 §1 巡检第 5 项、§2 告警可触发性注记；L2 §4.6 Ingress 不 Ready、§8 坑位清单 | 索引链接（6 条关门检查项原文保留在被引文件）+ 摘要（301/308 期望、admission webhook WARN 口径、代理 403/000、empty reply curl 52 视为未过关） |
| [`../acceptance/m4b-8-runbook.md`](../acceptance/m4b-8-runbook.md) | L1 §3.3 控制台日常操作（规则变更单的浏览器路径与 BLOCKED 规则） | 摘要 + 索引链接（5 步操作路径、BLOCKED 规则、Playwright 容器回退、脱敏要求留在原件） |
| [`../acceptance/m8-native-consistency-runbook.md`](../acceptance/m8-native-consistency-runbook.md) | L2 §7 测试与签收环境准备 | 重写操作正文（`make` 目标与两条 `pytest` 命令照抄） |
| [`../acceptance/m8-resip-runtime-log-contract.md`](../acceptance/m8-resip-runtime-log-contract.md) | L2 §2 日志取证 | 索引链接 + 字段契约表与 7 行示例日志**原文照抄**（这是字段契约，不是 runbook） |
| [`../acceptance/report.md`](../acceptance/report.md) §0 与未闭合清单 | 两册状态块；L2 §8 坑位清单 | 摘要（术语纪律：RC 就绪 ≠ 通过） |
| [`../plan.md`](../plan.md) §0 / §5.1 | 两册状态块（v1/v1.1 不是发行版本、O1 未裁决）；L1 §3.3 标注 | 摘要 |
| [`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml) + [`README.md`](../../deploy/alerts/README.md) | L1 §2 告警处置 | 摘要（**10 条规则 / 3 个组**的表达式与级别）+ 索引链接（阈值以规则文件为唯一权威） |
| [`../product/ne-datasheet.md`](../product/ne-datasheet.md) §5/§6 | L1 §1 巡检、§2 告警可触发性 | 摘要（KPI 口径与告警清单单一来源，避免两处漂移） |
| [`../product/compliance-matrix.md`](../product/compliance-matrix.md) | L2 §4.3 / §4.4 判决与失败码 | 索引链接（404 / 603 / 403 / 透传集合 {408,480,486,503,504} 的 file:line 证据在矩阵中） |
| [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3/§4 | L2 §3 抓包责任、§4 故障树归属判定 | 索引链接 + 摘要（AS 侧能自证什么 / 不自证什么） |

---

## 4. 本目录其余交付物的当前状态

以下文件属于本计划的运维文档交付物，**均已落盘**（可直接打开阅读）。但**依赖真实集群 / 依赖对端配合的部分仍为 blocked**，两册中凡引用之处均已就地标注该阻塞 —— **受阻部分不构成已演练的可执行步骤**：

| 文件 | 归集自 / 依赖 | 落盘状态 | 仍然 blocked 的部分 |
|---|---|---|---|
| [`fault-demarcation.md`](fault-demarcation.md) — 故障定界手册 | [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3/§4 已在产品分册给出首轮归属 | **已落盘** | **完整剧本的真实集群证据仍缺**（M8 7.2d 仍 blocked） |
| [`backup-restore.md`](backup-restore.md) — 备份恢复方案 + 演练记录 | [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §PG HA/PITR + §Restore drill；[`../product-packaging-plan.md`](../product-packaging-plan.md) 交付物 2.5 | **已落盘** | **真实集群 restore drill 记录仍 blocked**（M8 真实集群证据当前搁置，G-P1-10） |
| [`rollback-playbook.md`](rollback-playbook.md) — 业务摘流 / 回退 + iFC 配合 | ADR-0006 配置回滚 + ADR-0021 runtime override 粒度；G-P1-10 | **已落盘** | **iFC / 摘流部分依赖 S-CSCF/HSS 侧配合配置，真实集群演练仍 blocked**（G-P1-10） |
| [`alert-response-matrix.md`](alert-response-matrix.md) — 告警-动作对照表 | [`../../deploy/alerts/as-alerts.yaml`](../../deploy/alerts/as-alerts.yaml) **10 条规则 / 3 个组**；产品分册 2.2 | **已落盘** | 无（容量类告警继续 defer 到 O1 裁决后） |
| [`grafana-dashboards/overview.json`](grafana-dashboards/overview.json)、[`grafana-dashboards/sip-signaling.json`](grafana-dashboards/sip-signaling.json) — Grafana 看板模板（说明见 [`grafana-dashboards/README.md`](grafana-dashboards/README.md)） | 产品分册 2.1 | **已落盘** | **可用性取决于 AS 指标抓取接线，当前未闭环**（无 scrape 注解、无 ServiceMonitor / PodMonitor）；**不含 Sh 看板**（Sh 不在范围内，G-P2-3 已删除 `sh-interface.json`） |

---

## 5. 全册统一免责

1. **本目录不是验收结论。** 所有内容基于工程切片证据；**M5 工程关门 ≠ REQ 验收**，**M8 RC 就绪 ≠ 关门**。
2. **零容量数字。** 无 CPS / CAPS / BHCA / 并发 / 吞吐 / 时延 / 百分比容量。O1 未裁决。比例型告警阈值（如 1%、30%）与固定窗口计数（如 3 次/分钟）是**既有告警阈值**，**不是**容量指标。
3. **不引用 M6 dev-host 数字。** M6 测量为内部参考、非对外 O1/SLA。
4. **e2e = 0。** `docs/acceptance/test-plan.md` 中 e2e marker 数量为 0，完整呼叫 + 控制台端到端路径未落地；performance 仅 accept-all harness，**非业务判决路径**。
5. **不做 Diameter Sh / 不做 CDR / 不做计费 / 不做媒体。** 出现即 N/A，理由见 `AGENT.md` §2 与 [`../product/compliance-matrix.md`](../product/compliance-matrix.md)。
6. **不主动抓在途呼叫。** AS 侧不摘在途呼叫；摘流是对方（OP-SBC / OP-NET）侧动作。
7. **TLS 下解密属各方责任，密钥不跨方共享。** 不为解密复制对端私钥。
8. **testbed / kind / compose 抓包不是现网证据。** ADR-0014 明确 v1 不把 testbed 作为交付物。
9. **术语纪律。** 「v1」「v1.1」**不是发行版本**（`docs/plan.md` §0，2026-10-07 维护者口径）；产品版本号只看根目录 `VERSION`。文档中的主叫 / 正则规则一律标 **v1.1（不是发行版本）**。
10. **命名纪律。** 产品名为 **In-house IMS Application Server（文档暂用名）**；chart name / 镜像名 / OTel 服务名保持 `3rdparty-as` 不变。
11. **密钥与抓包。** 禁止保存密码 / token / cookie / 私钥；**绝不提交真实抓包**（`AGENT.md` §11 / §13）。

---

> **评审入口**：本目录各分册的**执行记录**见 [`../reviews/product-packaging-execution-record-2026-10-10.md`](../reviews/product-packaging-execution-record-2026-10-10.md)。该文件是**包装交付的执行记录，不是维护者签字的 review record** —— `AGENT.md` §3.3 要求的独立 review record 仍待维护者评审。