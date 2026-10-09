# `docs/product-packaging-plan.md` 评审记录

> 评审对象：`/home/shudong/project/3rdparty-as/docs/product-packaging-plan.md`
> 评审日期：2026-10-09
> 评审人：AI agent（主 agent 派发 Explore subagent 完成文档审阅，本 writing subagent 落盘）
> 评审范围：产品包装计划全文（§0 现状盘点、§1 四批交付物、§2 文档结构、§3 执行顺序、§4 已确认决策）
> 评审结论：该计划需大幅修订后才能作为内部上线评审基线

## 当前状态（Current Status）

- **维护者已于 2026-10-09 对全部 24 项 gap（8 P0 / 10 P1 / 6 P2）完成裁决；`docs/product-packaging-plan.md` 已按裁决完成修订（2026-10-09）。**
- 裁决结果：**22 项"接受"，2 项"部分接受"**（G-P0-6、G-P2-6）。
- **独立复核已完成**：独立复核 agent 已对照 `docs/product-packaging-plan.md` 修订版全文逐项验证，24 项 gap 的修改方案均已正确落地，Adjudication 表回写与裁决一致。
- **24 项 gap 已全部验证关闭（8 P0 + 10 P1 + 6 P2），P0 全部关闭**，该计划可作为内部上线评审基线。
- 当前里程碑：M7.1 工程已关门（2026-10-07），M8 发布候选产物就绪但退出签字仍搁置（`docs/plan.md` §0）。
- 遗留动作已全部关闭（2026-10-09）：
  - **G-P0-6 目标场景、G-P2-6 产品命名**：已在 `docs/plan.md` §0 新增"产品决策记录"小节，包含 2 条决策行（目标场景、产品文档暂用名），来源为 discussion.md 讨论 + 维护者 2026-10-09 确认。
  - **G-P1-9（§3.5 版本生命周期 / EOL）**：已新增 REQ-NF-16（`docs/requirements/prd.md` L459-470）与 ADR-0027（`docs/architecture/adr/0027-version-lifecycle-and-eol.md`），并在 ADR 注册表注册。
  - **B 类交付物**（NE Datasheet 容量数值、PDPO 保留期限、性能基准报告、真实集群演练）仍被 M8 退出签字搁置与 O1/O4/D5 未决阻塞。

---

## 评审对象与范围

| 项 | 内容 |
|---|---|
| 对象文件 | `docs/product-packaging-plan.md` |
| 基线文档 | `AGENT.md`、`docs/plan.md`、`docs/discussion.md`、`docs/acceptance/test-plan.md`、`docs/acceptance/report.md`、ADR 注册表及 ADR-0013/0014/0017/0018/0019 等 |
| 评审范围 | 全文 §0–§4，重点核对与当前里程碑、未决项、非目标及 ADR 的一致性 |

---

## Executive summary

`docs/product-packaging-plan.md` 试图把工程里程碑的已有产出和缺口整理成面向内部上线评审的产品化包装路线图，但当前版本与项目实际状态存在多处重大偏差：

1. **过度宣称已完成项**：Console、容量 harness、分层测试体系、Health/Draining 等被标为"已有"，但对应的 REQ 验收、真实集群验证或 e2e 覆盖尚未通过。
2. **违反硬规则**：在 §0.1 #9、§1.3、§1.4 #4.1 等处把 dev-host harness 或未决 O1 写成可对外发布的容量/性能数字，违反 `AGENT.md` §2「M6 实测之前不发布任何容量数字」。
3. **超出项目范围**：§2.1/§2.2 出现 Diameter Sh 接口面板与告警，与 `AGENT.md` §2「不做 Diameter Sh」及 ADR-0017 冲突。
4. **技术事实错误**：§2.4「iFC 灰度 + 一键回退」把 iFC 触发责任错误地放到 AS 侧；iFC 实际在 S-CSCF/HSS，AS 只实现 ISC 触发后的业务逻辑。
5. **决策依据不足**：§4 中多项"已确认决策"仅能在 `docs/discussion.md` 中找到讨论记录，未在 `docs/plan.md`、ADR 或 review record 中形成正式决策落点。
6. **排期不现实**：§3 给出 3–4 周总排期，未考虑 M8 签字搁置、O1/O4/D5 等未决项及 12 项 blocked / 24 项 open 的验收矩阵。

综上，本计划需重大修订后方可作为内部上线评审基线。

---

## 1. §0.1 已有资产逐项评估

| # | 资产 | 计划声称 | 准确性 | 证据与说明 |
|---|---|---|---|---|
| 1 | 产品版本号 | ✅ 已有 | 准确 | `VERSION` 文件 + `tests/test_version_consistency.py` 守卫；ADR-0018 accepted。 |
| 2 | Helm Chart | ✅ 已有 | 基本准确 | `deploy/helm/` 存在，`make chart-check` 通过；但 config-service 7.2d、真实集群 HTTPS 仍未验收（`docs/plan.md` §5.4）。 |
| 3 | Prometheus 指标 + 告警骨架 | ✅ 已有 | 基本准确 | `deploy/alerts/as-alerts.yaml` 存在；但告警-动作对照表、OTLP exporter 接线、容量类告警仍 defer（`report.md` §0.4）。 |
| 4 | Health / Readiness / Draining | ✅ 已有 | 部分准确 | 机制与单测已交付（`platform/tests/test_health_server.py`、ADR-0009）；但真实集群 ISSU/缩容不掉呼叫尚未完整验收，M5 工程关门≠REQ 验收。 |
| 5 | 分层测试体系 | ✅ 已有 | 不准确 | `e2e` marker 为 0（`test-plan.md` L19）；performance 层仅 accept-all harness，非业务判决路径。 |
| 6 | 架构文档 + ADR 体系 | ✅ 已有 | 准确 | `docs/architecture/adr/README.md` 注册 26 篇 ADR；部分仍为 draft（ADR-0023/0025）。 |
| 7 | 控制台（Console） | ✅ 已有 | 不准确 | M4b 仅完成工程切片（被叫+前缀、审批流、fleet distribution start）；REQ-S-4、F-13、F-15 真 AS、7.2d ingress 等仍 open（`plan.md` §4.3、§5.4）。 |
| 8 | 部分 Runbook | ✅ 已有（分散） | 部分准确 | Runbook 实际集中在 `docs/acceptance/`（`m5-downscale-runbook.md`、`m5-state-stores-runbook.md`、`m4b-8-runbook.md` 等），并非"散落在各里程碑交付物中"那般零散。 |
| 9 | 容量实测 harness | ✅ 已有 | 不准确 | M6 仅完成 dev-host O1 正式批次（`m6-o1-measurement-report-2026-10-05.md`），明确标注"非对外 O1/SLA"；`AGENT.md` §2 禁止在 M6 实测前发布容量数字。 |
| 10 | 可插拔业务引擎架构 | ✅ 已有 | 准确 | `apps/translation/` 与 `apps/anti-fraud/` 独立进程，符合 ADR-0002。 |

---

## 2. §0.2 主要缺口逐项评估

| # | 缺口项 | 计划状态 | 评估 | 关键问题 |
|---|---|---|---|---|
| 1 | 3GPP 规范符合性矩阵 | ❌ 缺失 | 合理 | 无争议，但需标注 Sh/CDR 为 N/A（范围外）。 |
| 2 | 网元档案（NE Datasheet） | ❌ 缺失 | 需修订 | 未注明容量数字受 O1 阻塞；在 O1 裁决前不能写 CAPS/BHCA/并发数值。 |
| 3 | 故障定界手册 | ❌ 缺失 | 合理 | 无争议。 |
| 4 | 一页纸产品定位 + 架构大图 | ❌ 缺失 | 合理 | 无争议。 |
| 5 | Grafana 看板模板 | ❌ 缺失 | 基本合理 | 但看板内容不得包含 Diameter Sh 面板。 |
| 6 | Preflight 环境校验脚本 | ❌ 缺失 | 合理 | 无争议。 |
| 7 | 离线安装包 | ❌ 缺失 | 需修订 | 范围应限定为 image sync + helm package 脚本，而非通用 offline installer；ADR-0013 明确 Helm 是唯一生产形态。 |
| 8 | 责任边界矩阵（RACI） | ❌ 缺失 | 合理 | 无争议。 |
| 9 | SLA / 版本生命周期 / EOL 策略 | ❌ 缺失 | 需修订 | ADR-0018 仅覆盖 release/组件版本号语义，生命周期/EOL 是新的决策，需新增 requirement + ADR。 |
| 10 | 安全合规证据（PDPO 等） | ❌ 缺失 | 需修订 | 未提及 O4（呼叫轨迹保留期）和 D5（轨迹存储选型）仍未决，不能硬编保留天数。 |
| 11 | 多业务承载平台能力开放 / 插件化机制文档 | ❌ 缺失 | 合理 | 建议标记为 v1.1 或按需，避免当前里程碑扩项。 |

---

## 3. 批次评审（§1）

### 第一批：评审入场券

- **1.1 产品一页纸 + 命名**：目标场景"内部上线评审"仅见于 `docs/discussion.md` 讨论，未在 `docs/plan.md` 或 ADR 中落点为正式决策（见 G-P0-6）。
- **1.2 3GPP 规范符合性矩阵**：标注 Sh/CDR 为 N/A 正确，但需同时明确 E1/E4/E5 仍未验收（`plan.md` §5.1 O2/O3）。
- **1.3 网元档案（NE Datasheet）**：撰写容量模型前必须等待 O1 裁决；当前写 CAPS/BHCA/并发会话违反 `AGENT.md` §2（见 G-P0-3）。
- **1.4 故障定界手册**：合理，但需与 RACI、抓包责任方、S-CSCF/HSS 侧日志对齐。
- **1.5 README 重写**：合理，但需先明确产品名与目标场景决策。

### 第二批：可运维性

- **2.1 Grafana 看板模板**：包含 "Diameter Sh 接口" 面板超出范围（见 G-P0-4）。
- **2.2 告警规则补强**："Sh 超时"告警同样超出范围；需移除或改为明确 N/A。
- **2.3 L1/L2 Runbook**：合理；但应归集现有 `docs/acceptance/*-runbook.md` 而非从零新建。
- **2.4 iFC 灰度 + 一键回退**：iFC 触发属于 S-CSCF/HSS，AS 仅实现 ISC 业务逻辑；此项描述误导（见 G-P0-5、G-P1-10）。
- **2.5 备份恢复方案**：合理；但依赖真实集群演练，当前 M8 7.2d 仍 blocked。

### 第三批：交付形态与合规

- **3.1 Preflight 脚本**：合理。
- **3.2 离线安装包**：范围应收窄为 image sync + helm package 脚本，符合 ADR-0013 单形态约束（见 G-P1-7）。
- **3.3 RACI**：合理。
- **3.4 PDPO 合规**：不能硬编码保留天数；必须声明 O4 未决、D5 未决（见 G-P1-8）。
- **3.5 版本生命周期/EOL**：ADR-0018 只解决版本号，EOL/支持周期需新增 ADR/requirement（见 G-P1-9）。

### 第四批：锦上添花

- **4.1 性能基准报告（正式版）**：在 O1 未裁决前安排正式性能报告违反 `AGENT.md` §2（见 G-P0-8）。
- **4.2 7×24 长稳测试报告**：建议按需/v1.1，当前里程碑不宜默认纳入。
- **4.3 API 版本兼容策略**：可并入版本生命周期文档，但需明确其依赖 ADR-0018 之上新决策。
- **4.4 白皮书**：合理，优先级最低。
- **4.5 能力开放机制文档**：合理，建议 v1.1 或按需。

---

## 4. 文档结构评审（§2）

| 建议目录 | 评估 | 说明 |
|---|---|---|
| `docs/product/` | 接受 | 与 `docs/README.md` L26 的 `operations/` 规划不冲突；新增目录合理。 |
| `docs/operations/` | 接受 | `docs/README.md` L26 已规划；但目前目录不存在（G-P2-1）。 |
| `docs/delivery/` | 基本接受 | 与 `deploy/helm/README.md` 边界需明确（G-P2-4）。 |
| `operations/grafana-dashboards/sh-interface.json` | 需修改 | 文件名与"不做 Sh"范围冲突（G-P2-3）。 |
| `delivery/install-guide.md` | 需修改 | 与 `deploy/helm/README.md` 内容重叠，应明确前者面向交付清单、后者面向 Helm 参数（G-P2-4）。 |

---

## 5. 执行顺序与排期评审（§3）

- 总排期 **3–4 周** 不现实：M8 签字仍搁置（`plan.md` §0），O1/O4/D5 等未决项未裁决，12 项 blocked / 24 项 open 的验收矩阵未收敛（`report.md` §0.5）。
- 第 4 步"运维能力补全"中的 iFC 灰度/回退依赖 S-CSCF 侧配置与真实集群演练，不能按固定天数完成（见 G-P1-10）。
- 第 7 步"安全合规"需 O4/D5 先裁决，否则无法写出可落地的 PDPO 说明（见 G-P1-8）。

建议：先关闭 M8 退出签字与 O1/O4/D5 裁决，再制定可落地的包装排期。

---

## 6. 已确认决策一致性评审（§4）

| 决策 | 计划声称 | 实际状态 | 评估 |
|---|---|---|---|
| 4.1 目标场景：内部上线评审 | 已确认 | 仅 `docs/discussion.md` L100、L168 有讨论；`docs/plan.md` 无对应决策行，无 ADR，无 review record。 | 待裁决（G-P0-6） |
| 4.2 业务定位：多业务承载平台 | 已确认 | `apps/` 架构支持；讨论中反复提及。 | 可接受，但建议补一条 ADR/计划决策行。 |
| 4.3 命名：In-house IMS Application Server | 已确认 | 仅 `docs/discussion.md` L203-253 有命名讨论；`docs/plan.md`、ADR 无正式落点。 | 待裁决（G-P2-6） |
| 4.4 推进节奏：顺序全量推进 | 已确认 | M8 仍搁置，无上游授权推进包装里程碑；O1/O4/D5 未决。 | 需修改（G-P0-7） |

---

## 7. 遗漏关键项

本计划未充分反映下列对内部上线评审至关重要的项目：

1. **M8 状态**：RC 产物就绪但退出签字搁置（`plan.md` §0、`report.md` §0）。
2. **E1/E4/E5 未验收**：reSIProcate 生产路径行为、TLS 热轮换、状态外置仍为 open（`plan.md` §5.1 O2/O3、ADR-0019 §7/§10）。
3. **TLS/REQ-S-2/S-3 未验收**：运营商 PKI、证书轮换无 lab 证据（`report.md` §0.6 D-1）。
4. **e2e=0**：`test-plan.md` L19 明确 e2e 标记数为 0，完整呼叫 + 控制台未落地。
5. **O1 容量目标未裁决**：`AGENT.md` §2 与 `plan.md` §5.1 O1 均禁止发布容量数字。
6. **O4 呼叫轨迹保留期 / D5 存储选型未决**：影响 PDPO、安全合规、备份恢复方案。
7. **REQ-S-4 / M4b 整体验收未通过**：控制台安全审计仍为工程切片，非 REQ 验收（`plan.md` §4.3、§5.4）。
8. **testbed 不作 v1 交付物**：ADR-0014 明确 v1 不把 testbed 当交付物；包装计划应避免把仿真器 IOT 报告当作产品证据。

---

## Gap Register

### P0 gaps

#### G-P0-1 — Console 被过度宣称

- **位置**：`docs/product-packaging-plan.md` §0.1 #7
- **问题**：Console 被标为"已有"，但 M4b 仅为工程切片；REQ-S-4、M4b-8、F-13、F-15 真 AS、主叫/正则 v1.1、7.2d ingress 均未通过验收。
- **证据**：`docs/plan.md` §4.3 明确 M4 工程关门不含 `test-plan` 全 REQ 绿、F-13、F-15 真 AS、主叫/正则 v1.1、7.2d ingress；§5.4 补测清单仍 open。
- **建议**：将 #7 改为"部分已有（工程切片）"，并在说明中列出尚未验收的子项。

#### G-P0-2 — 容量 harness 被误述为"容量实测"

- **位置**：`docs/product-packaging-plan.md` §0.1 #9
- **问题**：把 M6 dev-host harness 报告称为"容量实测"，违反 `AGENT.md` §2「M6 实测之前不发布任何容量数字」。
- **证据**：`AGENT.md` §2；`docs/plan.md` §5.1 O1 仍 open；`m6-o1-measurement-report-2026-10-05.md` 明确标注"非对外 O1/SLA"。
- **建议**：改为"M6 容量 harness（dev-host 内部测量，非对外发布）"。

#### G-P0-3 — NE Datasheet 计划提前写容量数字

- **位置**：`docs/product-packaging-plan.md` §1.3
- **问题**：NE Datasheet 准备写入 CAPS/BHCA/并发会话等数字，但 O1 仍未裁决。
- **证据**：`AGENT.md` §2；`docs/plan.md` §5.1 O1（容量目标：CPS、并发会话、建立时延预算，维护者目标裁决仍 open）。
- **建议**：Datasheet 中容量章节写为"受 O1 阻塞，待 M6 实测与维护者裁决后填入"，不得出现具体数字。

#### G-P0-4 — Grafana 面板含 Diameter Sh 接口

- **位置**：`docs/product-packaging-plan.md` §2.1 / §2.2
- **问题**：Grafana 看板与告警规则包含 "Diameter Sh interface / Sh timeout"，超出项目范围。
- **证据**：`AGENT.md` §2 明确"不做 Diameter Sh"；`ADR-0017` 明确不做 CDR/billing。
- **建议**：移除 Sh 面板与告警；合规矩阵中 Sh 标 N/A。

#### G-P0-5 — "iFC 灰度 + 一键回退"范围错误

- **位置**：`docs/product-packaging-plan.md` §2.4
- **问题**：iFC 触发逻辑属于 S-CSCF/HSS，AS 只实现 ISC 触发后的业务逻辑；计划把 iFC 灰度/回退写成 AS 侧交付物，误导评审。
- **证据**：`docs/discussion.md` L126（"iFC 支持按用户群/号段/百分比灰度触发"在 S-CSCF 侧）；架构文档 §1.1 单一 ISC 语义。
- **建议**：改为"ISC 触发后的业务灰度/摘流方案 + 与 S-CSCF 侧 iFC 灰度的配合接口"，明确 AS 侧边界。

#### G-P0-6 — "目标场景：内部上线评审"决策依据不足

- **位置**：`docs/product-packaging-plan.md` §4.1
- **问题**：该决策被标为"已确认"，但在 `docs/plan.md` 中无对应决策行，无 ADR，无 review record。
- **证据**：`docs/discussion.md` L100、L168 有讨论；`docs/plan.md` 无此决策落点。
- **建议**：维护者裁决：要么在 `docs/plan.md` §1/§4 补正式决策行 + review record，要么本项标为讨论意见而非已确认决策。

#### G-P0-7 — "顺序全量推进"与 M8 搁置冲突

- **位置**：`docs/product-packaging-plan.md` §4.4
- **问题**：声称推进节奏"已确认"，但 M8 退出签字仍搁置，且 O1/O4/D5 未决，缺乏上游授权。
- **证据**：`docs/plan.md` §0 "M8 仍搁置"；§5 O1/O4/D5 均为 open。
- **建议**：改为"待 M8 签字与 O1/O4/D5 裁决后重新确认推进节奏"，或拆分为"第一批优先、其余按需"。

#### G-P0-8 — 第四批性能基准报告仍违反容量数字禁令

- **位置**：`docs/product-packaging-plan.md` §1.4 #4.1
- **问题**：第四批仍计划"基于 D10 / M6 容量 harness 整理正式报告"，在 O1 未裁决前发布性能基准报告违反硬规则。
- **证据**：`AGENT.md` §2；`docs/plan.md` §5.1 O1；`ADR-0014` 明确 M6 前不发布容量数字。
- **建议**：改为"O1 裁决后，基于 M6 实测整理内部评审版性能报告"；当前阶段仅保留测试方法学说明，不出现吞吐/并发/时延数值。

### P1 gaps

#### G-P1-1 — Health/Draining 仅机制验证，缺真实集群证据

- **位置**：`docs/product-packaging-plan.md` §0.1 #4
- **问题**：ISSU/Draining 仅在 kind 上用模拟 `active_calls` 验证机制；真实集群滚动升级/缩容不掉呼叫未完整验收。
- **证据**：`docs/acceptance/report.md` M5 容器镜像段；`m5-downscale-runbook.md` §4 明确使用 `AS_M5_SIMULATED_ACTIVE_CALLS`；M5 工程关门≠REQ 验收。
- **建议**：说明中增加"机制已交付，真实 SIP 负载下的不掉呼叫待 M7/M8 验收"。

#### G-P1-2 — 分层测试体系被过度宣称

- **位置**：`docs/product-packaging-plan.md` §0.1 #5
- **问题**：e2e=0，performance 仅 accept-all harness，不是完整分层测试体系。
- **证据**：`docs/acceptance/test-plan.md` L19-20；`test-plan.md` 自动化分层表。
- **建议**：改为"三层 testbed 骨架已建立；e2e 尚未落地，performance 仅 accept-all harness（非业务路径）"。

#### G-P1-3 — NE Datasheet 缺口未注 O1 阻塞

- **位置**：`docs/product-packaging-plan.md` §0.2 #2
- **问题**：缺口表未说明容量数字因 O1 未决而暂时无法撰写。
- **证据**：`docs/plan.md` §5.1 O1；`AGENT.md` §2。
- **建议**：在 #2 影响范围中增加"容量章节受 O1 阻塞"。

#### G-P1-4 — SLA/EOL 缺口未区分 ADR-0018 范围

- **位置**：`docs/product-packaging-plan.md` §0.2 #9
- **问题**：缺口表未说明 ADR-0018 只覆盖版本号语义，生命周期/EOL 是新的决策。
- **证据**：`ADR-0018` Decision/Consequences 明确只解决 release/组件版本号，未涉及支持周期/EOL。
- **建议**：#9 说明中增加"需新增 requirement + ADR，超出 ADR-0018 范围"。

#### G-P1-5 — 安全/隐私缺口遗漏 O4/D5

- **位置**：`docs/product-packaging-plan.md` §0.2 #10
- **问题**：未提及呼叫轨迹保留期 O4 和存储选型 D5 仍未决，无法落地 PDPO 说明。
- **证据**：`docs/plan.md` §5.1 O4、§5.2 D5；`ADR-0017` Decision ④。
- **建议**：#10 状态改为"受 O4/D5 阻塞"，并列为与 PDPO 同等关键的前置项。

#### G-P1-6 — 3GPP 矩阵未注 E1/E4/E5 与 sippy 参考

- **位置**：`docs/product-packaging-plan.md` §1.2
- **问题**：规范矩阵未说明生产栈 E1/E4/E5 仍 open，且 sippy 仅 testbed 基线参考。
- **证据**：`ADR-0019` §7/§10；`docs/plan.md` §5.1 O2/O3。
- **建议**：矩阵中增加"E1/E4/E5 待 M8 验收"备注，并在范围说明中明确 sippy 仅 testbed 基线。

#### G-P1-7 — Air-gapped 包范围过宽

- **位置**：`docs/product-packaging-plan.md` §3.2
- **问题**："离线安装包"描述偏向通用 offline installer，可能偏离 Helm-only 生产形态。
- **证据**：`ADR-0013`；`AGENT.md` §2 单租户 on-prem。
- **建议**：明确为"镜像同步脚本 + `helm package` + 依赖镜像清单 + 离线加载脚本"，不产生第二套安装形态。

#### G-P1-8 — PDPO 未声明 O4 未决

- **位置**：`docs/product-packaging-plan.md` §3.4
- **问题**：PDPO 合规准备写入"保留期限"，但 O4 未裁决，不能硬编码天数。
- **证据**：`docs/plan.md` §5.1 O4；`ADR-0017` Decision ④。
- **建议**：改为"保留期限由 O4 裁决后填入；当前仅描述留存范围、删除机制、数据留港原则"。

#### G-P1-9 — 版本生命周期/EOL 未说明需新 ADR

- **位置**：`docs/product-packaging-plan.md` §3.5
- **问题**：未说明该交付物需新增 requirement + ADR，依赖文档链不完整。
- **证据**：`AGENT.md` §3.1 文档链要求。
- **建议**：增加"需先补 REQ-NF-XX 与 ADR，再走 HLD/LLD/验收"的说明。

#### G-P1-10 — iFC 灰度/备份恢复未 acknowledge S-CSCF 依赖

- **位置**：`docs/product-packaging-plan.md` §2.4 / §2.5
- **问题**：iFC 灰度与备份恢复演练依赖 S-CSCF 侧配置和真实集群环境，计划未充分说明。
- **证据**：`docs/discussion.md` L126；M8 7.2d BLOCKED（`plan.md` §5.4）。
- **建议**：在相关交付物中增加"依赖 S-CSCF 侧配合与 M8 真实集群环境"的风险说明。

### P2 gaps

#### G-P2-1 — `docs/operations/` 尚未创建

- **位置**：`docs/product-packaging-plan.md` §2
- **问题**：计划新增 `docs/operations/`，但该目录目前不存在。
- **证据**：`docs/README.md` L26 已规划 `operations/`，但实际目录未创建。
- **建议**：接受为已知缺口；创建目录时把现有 runbook 迁/链接进去。

#### G-P2-2 — Runbook 实际位置描述不准

- **位置**：`docs/product-packaging-plan.md` §0.1 #8
- **问题**："部分 Runbook 散落在各里程碑交付物中"与事实不符；runbook 已集中在 `docs/acceptance/`。
- **证据**：`docs/acceptance/m5-downscale-runbook.md`、`m5-state-stores-runbook.md`、`m4b-8-runbook.md`、`m8-native-consistency-runbook.md` 等。
- **建议**：改为"Runbook 已集中在 `docs/acceptance/`，计划迁/链接到 `docs/operations/`"。

#### G-P2-3 — `sh-interface.json` 文件名冲突

- **位置**：`docs/product-packaging-plan.md` §2
- **问题**：`operations/grafana-dashboards/sh-interface.json` 与"不做 Diameter Sh"范围冲突。
- **证据**：`AGENT.md` §2。
- **建议**：删除该文件项或改为明确标注 N/A 的占位说明。

#### G-P2-4 — `delivery/install-guide.md` 与 Helm README 边界不清

- **位置**：`docs/product-packaging-plan.md` §2
- **问题**：`delivery/install-guide.md` 与现有 `deploy/helm/README.md` 内容重叠，职责边界未说明。
- **证据**：`deploy/helm/README.md` 已含详细安装、values 说明、渲染守卫。
- **建议**：`delivery/install-guide.md` 聚焦"交付清单 + 镜像同步 + helm install 命令清单"，`deploy/helm/README.md` 聚焦 Helm chart 参数与行为；两文档互相链接，避免重复。

#### G-P2-5 — 3–4 周排期忽略 M8 搁置与未决项

- **位置**：`docs/product-packaging-plan.md` §3
- **问题**：排期未考虑 M8 签字搁置、O1/O4/D5 未决、12 blocked / 24 open 验收项。
- **证据**：`docs/plan.md` §0、§5；`report.md` §0.5、§0.8。
- **建议**：改为"先关闭 M8 与 O1/O4/D5，再制定可执行排期"，或给出带阻塞条件的多情景估算。

#### G-P2-6 — 产品名"已确认"依据不足

- **位置**：`docs/product-packaging-plan.md` §4.3
- **问题**：产品名被标为"已确认"，但仅见于 `docs/discussion.md` L203-253 讨论，无 ADR/plan 决策行。
- **证据**：`docs/discussion.md` L203-253；`docs/plan.md` 无该决策行。
- **建议**：维护者裁决：要么补正式决策落点，要么标为"建议名称"而非已确认。

---

## Adjudication

| ID | 来源 | 问题摘要 | 裁决 | 修改方案 | 状态 | 验证方式 | 备注 |
|---|---|---|---|---|---|---|---|
| G-P0-1 | §0.1 #7 | Console 被标为"已有"，但 M4b 仅为工程切片，REQ-S-4/M4b/REQ 多项未验收 | 接受 | 将 #7 改为"部分已有（工程切片）"，列出未验收子项 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L21） | |
| G-P0-2 | §0.1 #9 | M6 dev-host harness 被描述为"容量实测"，违反 M6 前不发布容量数字规则 | 接受 | 改为"M6 容量 harness（dev-host 内部测量，非对外发布）" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L23） | |
| G-P0-3 | §1.3 | NE Datasheet 计划写入 CAPS/BHCA/并发数字，但 O1 未裁决 | 接受 | 容量章节写为"受 O1 阻塞，待实测后填入" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L69） | 容量数值待 O1 裁决（B 类交付物） |
| G-P0-4 | §2.1/§2.2 | Grafana/告警含 Diameter Sh 面板与 Sh 超时告警，超出范围 | 接受 | 移除 Sh 面板与告警；合规矩阵 Sh 标 N/A | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L79-L80） | |
| G-P0-5 | §2.4 | "iFC 灰度 + 一键回退"误把 S-CSCF/HSS 侧 iFC 责任放到 AS | 接受 | 改为"ISC 触发后业务灰度/摘流 + 与 S-CSCF 侧配合" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L82） | |
| G-P0-6 | §4.1 | "目标场景：内部上线评审"标为已确认，但无 plan/ADR/review record 落点 | **部分接受** | 维护者 2026-10-09 确认方向 A（内部上线评审），但该方向目前仅来自 discussion.md；计划文档 §4.1 已降格表述为"当前默认方向（讨论确认，待补 plan/ADR 正式决策落点）"，不再写成已确认决策 | 已关闭 | 文档更新 + plan 决策行（docs/plan.md L21-28） | 正式决策落点已补：docs/plan.md §0 "产品决策记录"小节 |
| G-P0-7 | §4.4 | "顺序全量推进"标为已确认，但 M8 签字搁置、O1/O4/D5 未决 | 接受 | 改为"待 M8 签字与 O1/O4/D5 裁决后确认推进节奏" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L220-L223） | 推进节奏已改为 A/B 两类，B 类待前置项闭合 |
| G-P0-8 | §1.4 #4.1 | 第四批正式性能基准报告仍违反容量数字禁令 | 接受 | 改为"O1 裁决后整理内部评审版报告"；当前不写数值 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L103） | 性能报告待 O1 裁决（B 类交付物） |
| G-P1-1 | §0.1 #4 | Health/Draining 仅机制+模拟验证，缺真实集群 ISSU/缩容证据 | 接受 | 增加"真实 SIP 负载下不掉呼叫待 M7/M8 验收"说明 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L18） | |
| G-P1-2 | §0.1 #5 | 分层测试体系过度宣称：e2e=0、performance 仅 accept-all harness | 接受 | 改为"骨架已建立；e2e 未落地，performance 非业务路径" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L19） | |
| G-P1-3 | §0.2 #2 | NE Datasheet 缺口未注 O1 阻塞 | 接受 | #2 影响范围增加"容量章节受 O1 阻塞" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L31） | 容量数值待 O1 裁决 |
| G-P1-4 | §0.2 #9 | SLA/EOL 缺口未区分 ADR-0018 只覆盖版本号 | 接受 | #9 说明增加"需新增 requirement + ADR" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L38） | 与 G-P1-9 同源，需新增 requirement + ADR |
| G-P1-5 | §0.2 #10 | 安全/隐私缺口遗漏 O4/D5 | 接受 | #10 状态改为"受 O4/D5 阻塞" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L39） | 待 O4/D5 裁决 |
| G-P1-6 | §1.2 | 3GPP 矩阵未注 E1/E4/E5 仍 open、sippy 仅 testbed 基线 | 接受 | 矩阵增加 E1/E4/E5 待验收备注，并说明 sippy 参考地位 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L68） | |
| G-P1-7 | §3.2 | Air-gapped 包范围过宽，可能偏离 Helm-only | 接受 | 明确为"镜像同步 + helm package + 离线加载脚本" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L92） | |
| G-P1-8 | §3.4 | PDPO 合规未声明 O4 未决、不能硬编码保留天数 | 接受 | 保留期限写为"由 O4 裁决后填入" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L94） | 待 O4/D5 裁决 |
| G-P1-9 | §3.5 | 版本生命周期/EOL 未说明需新 ADR/requirement | 接受 | 增加"需先补 REQ + ADR"说明 | 已关闭 | 文档更新 + REQ-NF-16（prd.md L459-470）+ ADR-0027 | 已新增 REQ-NF-16 与 ADR-0027，ADR 注册表已更新 |
| G-P1-10 | §2.4/§2.5 | iFC 灰度/备份恢复未 acknowledge S-CSCF 与真实集群依赖 | 接受 | 增加依赖与风险说明 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L82-L83） | 真实集群演练待 M8 7.2d 解锁，2.4 另需 S-CSCF/HSS 侧配合 |
| G-P2-1 | §2 | `docs/operations/` 尚未创建 | 接受 | 创建目录并迁移/链接现有 runbook | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L124） | §2 已注明目录尚未创建，随创建时迁移/链接现有 runbook |
| G-P2-2 | §0.1 #8 | Runbook 实际集中在 `docs/acceptance/`，描述不准 | 接受 | 改为"Runbook 已集中，计划迁到 operations/" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L22） | |
| G-P2-3 | §2 | `sh-interface.json` 文件名与不做 Sh 范围冲突 | 接受 | 删除或改为 N/A 占位说明 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L125-L127） | 目录树已删除该文件项，仅保留 overview/sip-signaling 看板 |
| G-P2-4 | §2 | `delivery/install-guide.md` 与 `deploy/helm/README.md` 边界不清 | 接受 | 明确两文档职责并互相链接 | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L136-L143） | |
| G-P2-5 | §3 | 3–4 周排期忽略 M8 搁置与 O1/O4/D5 | 接受 | 改为"先关闭 M8 与 O1/O4/D5，再定排期" | 已验证 | 文档更新 + 维护者验证（product-packaging-plan.md 2026-10-09 修订版 L148-L189） | 已改为带阻塞条件的 A/B 两类与多情景排期，不预设总工期 |
| G-P2-6 | §4.3 | 产品名"已确认"仅 discussion 证据 | **部分接受** | 维护者 2026-10-09 确认文档采用暂用名 In-house IMS Application Server、repo 名 3rdparty-as 不改动；计划文档 §4.3 已改为"文档暂用名 / 建议名称（待补正式决策落点）"，不再表述为已正式批准产品名 | 已关闭 | 文档更新 + plan 决策行（docs/plan.md L21-28） | 正式命名决策落点已补：docs/plan.md §0 "产品决策记录"小节 |

---

## AI 复核结论（Verification）

- 本 review record 已对照 `docs/product-packaging-plan.md` 全文、`AGENT.md`、`docs/plan.md`、`docs/discussion.md`、`docs/acceptance/test-plan.md`、`docs/acceptance/report.md` 及 ADR-0013/0014/0017/0018/0019 进行复核。
- 所有 P0/P1/P2 gap 均已给出证据来源、修改方案与 adjudication 表初始状态。
- 维护者已于 2026-10-09 完成全部 24 项裁决（22 项接受、G-P0-6 与 G-P2-6 部分接受），`docs/product-packaging-plan.md` 已按裁决修订。
- **独立复核 agent 已对照 `docs/product-packaging-plan.md` 修订版全文逐项验证，24 项 gap 的修改方案均已正确落地。**
- **§0.3 前置依赖完整覆盖 review record §7 全部遗漏关键项。**
- **Adjudication 表回写与裁决一致。**
- **24 项 gap 已全部关闭（8 P0 + 10 P1 + 6 P2），P0 全部关闭，该计划可作为内部上线评审基线。**
- **遗留动作已全部关闭**：G-P0-6/G-P2-6 已在 docs/plan.md 补正式决策行；G-P1-9 已新增 REQ-NF-16 + ADR-0027。

---

## 签字

- **评审人**：AI agent（Explore + writing subagent）
- **评审日期**：2026-10-09
- **维护者裁决日期**：2026-10-09
- **独立复核日期**：2026-10-09
- **复核结论**：24 项 gap 全部关闭（8 P0 + 10 P1 + 6 P2），P0 全部关闭，计划可作为内部上线评审基线。遗留动作已全部关闭（2026-10-09）。
