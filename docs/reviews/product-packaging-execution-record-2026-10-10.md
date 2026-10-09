# 产品化包装执行记录（2026-10-10）

> **本文件是「执行记录」（execution record），不是维护者签字的评审记录。**
>
> | 项 | 内容 |
> |---|---|
> | 记录类型 | **执行记录** —— 记录 AI agent 本次实际落盘了什么、验证了什么、没做什么 |
> | 评审对象 | `docs/product-packaging-plan.md` §3.2 的 **A 类交付物**，以及第一 / 二 / 三批的文档与脚本 |
> | 执行日期 | 2026-10-10 |
> | 执行方式 | 主 agent 派发 writing subagent 落盘 + 主 agent 逐项核对（`git status` / `git diff` / 链接校验 / 脚本语法检查 / YAML 解析 / JSON 解析） |
> | 执行者 | AI agent（writing subagent `pkg-record` 等） |
> | **维护者评审人** | **待指定** |
> | **签字状态** | **待维护者评审（pending）** —— 本文件任何内容都不构成验收结论 |
>
> **纪律声明（与 `docs/reviews/product-packaging-plan-review-2026-10-09.md` 一致）**：
> - 本记录**不新增**任何需求 / ADR / REQ，也**不推翻**任何既有裁决。
> - 本记录**不含**任何容量 / 性能数字，**不引用** M6 dev-host 测量；**不给**保留天数或恢复时长（O1 / O4 / D5 未裁决，`AGENT.md` §2）。
> - 「已落盘」≠「已验收」。M8 退出签字仍搁置；E1 / E4 / E5 未验收；e2e marker = 0。
> - 产品名 **In-house IMS Application Server** 是**文档暂用名**（`docs/plan.md` §0 产品决策记录，2026-10-09 讨论确认）；「v1」「v1.1」**不是发行版本**（`docs/plan.md` §0）。
> - 本次**未提交任何 commit**，未 `git add`、未改分支、未改 remote、未打 tag。

---

## 1. 评审对象

### 1.1 第一批：评审入场券

| 编号 | 交付物 | 落盘文件 | 状态 | 行数 / 规模 |
|---|---|---|---|---|
| 1.1 | 产品一页纸 + 命名（文档暂用名） | `docs/product/one-pager.md` | 已落盘 | 214 行 |
| 1.2 | 3GPP 规范符合性矩阵 | `docs/product/compliance-matrix.md` | 已落盘 | 319 行 |
| 1.3 | 网元档案（NE Datasheet） | `docs/product/ne-datasheet.md` | 已落盘，**§3 容量章节受 O1 阻塞**（只写模型结构与测量方法学，未填任何数值） | 376 行 |
| 1.4 | 故障定界手册 | `docs/operations/fault-demarcation.md` | 已落盘 | 299 行 |
| 1.5 | README 重写为产品入口 | 根 `README.md`（重写）+ `docs/README.md`（导航更新） | 已落盘 | `README.md` 226 行；`docs/README.md` 72 行 |

### 1.2 第二批：可运维性

| 编号 | 交付物 | 落盘文件 | 状态 | 行数 / 规模 |
|---|---|---|---|---|
| 2.1 | Grafana 看板模板 | `docs/operations/grafana-dashboards/overview.json`、`sip-signaling.json`、`README.md` | 已落盘；**不含 Sh 面板、不含时延面板、不含容量数字**；抓取接线缺口已显式标注 | JSON 733 / 410 行；README 140 行 |
| 2.2 | 告警规则补强 + 告警-动作对照表 | `docs/operations/alert-response-matrix.md` + `deploy/alerts/as-alerts.yaml` + `deploy/alerts/README.md` | 已落盘；**新增 `as.runtime` / `as.platform` 两个规则组共 5 条规则，`as.call-path` 原 5 条未改** | 对照表 208 行；规则文件共 3 组 10 条规则 |
| 2.3 | L1 / L2 Runbook 分册 | `docs/operations/runbook-l1.md`、`runbook-l2.md`、`README.md` | 已落盘；`docs/acceptance/` 原件**保留不动**，只做索引与归集 | 252 / 239 / 86 行 |
| 2.4 | 摘流 / 回退 + iFC 配合 | `docs/operations/rollback-playbook.md` | 已落盘（方案与边界）；**真实集群演练未做**，依赖 S-CSCF / HSS 侧配合与 M8 7.2d 解锁 | 161 行 |
| 2.5 | 备份恢复方案 + 演练记录 | `docs/operations/backup-restore.md` | 已落盘（方案 + 演练记录**模板**）；**真实演练记录为空**，依赖真实集群 | 162 行 |

### 1.3 第三批：交付形态与合规

| 编号 | 交付物 | 落盘文件 | 状态 | 行数 / 规模 |
|---|---|---|---|---|
| 3.1 | Preflight 环境校验脚本 | `docs/delivery/preflight.sh` | 已落盘，可执行；`--dry-run` 路径已验证 | 663 行 |
| 3.2 | 离线安装包（air-gapped） | `docs/delivery/airgap-package.md` + `docs/delivery/scripts/bundle-images.sh`、`load-images.sh`、`images.txt` | 已落盘；范围限定 image save/load + 清单 + 校验和 + `helm package`，**不产生第二套安装形态**（ADR-0013） | 195 + 382 + 324 + 70 行 |
| 3.3 | 责任边界矩阵（RACI） | `docs/product/responsibility-matrix.md` | 已落盘 | 211 行 |
| 3.4 | 安全合规说明（PDPO） | `docs/product/security-privacy.md` | 已落盘；**保留期限未写天数**（O4 / D5 未裁决，只写留存范围、删除机制、数据留港原则） | 279 行 |
| 3.5 | 版本生命周期与 EOL 策略 | `docs/product/version-lifecycle.md` | 已落盘；§3 逐条**转述** ADR-0027 已接受的决定，不新增承诺；§7 API 兼容策略（交付物 **4.3**）标为**待决策、无 ADR** | 260 行 |

### 1.4 第四批：本次未做

| 编号 | 交付物 | 本次状态 | 原因 |
|---|---|---|---|
| 4.1 | 性能基准报告 | **只交付方法学章节**（`docs/product/ne-datasheet.md` §3，含 §3.1 为何不填数值、§3.2 模型结构、§3.4 测量方法学、§3.5 裁决前禁止事项、§3.6 何时可填） | O1 未裁决；`AGENT.md` §2 禁止在 M6 真实 socket 实测前发布任何容量数字 |
| 4.2 | 7×24 长稳测试报告 | **未做** | 计划已定为 v1.1 / 按需，不纳入当前里程碑（避免扩项） |
| 4.3 | API 版本兼容策略 | **未落为独立交付物**；在 `docs/product/version-lifecycle.md` §7 以「候选、未决策」形式列出待决点与出口条件 | 与 3.5 同源，需维护者决策 + 新 ADR + review record |
| 4.4 | 产品白皮书 / 架构白皮书 | **未做** | 第四批锦上添花，不纳入当前里程碑 |
| 4.5 | 多业务平台能力开放机制文档 | **未做** | 计划已定为 v1.1 / 按需，不纳入当前里程碑 |

---

## 2. 评审日期与执行者

| 项 | 内容 |
|---|---|
| 执行日期 | **2026-10-10** |
| 执行者 | **AI agent**（主 agent 派发 writing subagent 落盘，主 agent 核对） |
| 执行范围 | `docs/product/`（6 份）、`docs/operations/`（8 份 + 2 份看板 JSON）、`docs/delivery/`（3 份 + 3 个脚本/清单）、根 `README.md`、`docs/README.md`、`deploy/alerts/`（2 个文件） |
| 代码侧改动 | **仅 `deploy/alerts/as-alerts.yaml` 与 `deploy/alerts/README.md`**，且只新增规则组与说明；**未改任何产品代码**（`platform/`、`apps/`、`services/`、`testbed/`、`deploy/helm/` 均未动） |
| **维护者评审人** | **待指定** |
| 维护者评审日期 | **待填** |
| 评审结论 | **待维护者给出**（通过 / 有条件通过 / 不通过） |

---

## 3. 结论

结论分两类，如实给出，不合并表述。

### 3.1 A 类交付物：已落盘，**待维护者评审**

- 第一 / 二 / 三批的 **A 类交付物已全部落盘**（见 §1.1–§1.3），文件存在、行数与内容已由执行者逐项核对。
- 每份文档的状态块都写明了证据口径：**E1 / E4 / E5 未验收、e2e marker = 0、M8 RC 就绪 ≠ 关门、testbed 非 v1 交付物、零容量数字**。
- 这批文件的性质是「**已交付的工程产出**」，**不是「已验收的结论」**。按 `AGENT.md` §3.2「所有文档必须有 review」，它们进入下一阶段（内部上线评审）前**必须**经过维护者评审并留下 review record。
- **本次执行本身不构成评审**。本文件是执行记录。

### 3.2 B 类中受 O1 / O4 / D5 阻塞的部分：**已标注阻塞源，未填数值**

| 受阻内容 | 阻塞源 | 文档中的实际写法 |
|---|---|---|
| NE Datasheet 容量模型取值（CPS / BHCA / 并发 / 时延门限） | **O1** 未裁决 | `ne-datasheet.md` §3 只给变量与关系、瓶颈点成因与观测手段、测量方法学、禁止事项清单；**无任何数值** |
| 容量类告警（`as.capacity` 组） | **O1** 未裁决 | `deploy/alerts/README.md` §Deferred 明列候选与退出条件；`as.capacity` 组**刻意不存在** |
| PDPO 保留期限、轨迹保留天数 | **O4** 未裁决 | `security-privacy.md` 只写留存范围（MSISDN / IMPU / 呼叫轨迹）、删除机制、数据留港原则；**不写天数** |
| 轨迹存储方案（存储选型 / 跨境） | **D5** 未裁决 | 同上，存储方案标为待裁决 |
| 备份恢复 RPO / RTO、恢复时长 | 真实集群未就绪 + 客户侧 HA 未决（O5 / D3） | `backup-restore.md` 只给方法与记录模板；**不给天数与时长** |
| 性能基准报告（4.1 正式版） | **O1** 未裁决 | 本次只交付方法学章节（见 §1.4） |

**这些章节没有「先填个估计值再标 TODO」** —— 填数字本身违反 `AGENT.md` §2。

---

## 4. 问题清单与对应修改

| # | 发现的问题 | 处理方式 | 证据 / 位置 |
|---|---|---|---|
| 1 | **告警面存在抓取接线缺口**：AS Pod 模板无 `prometheus.io/scrape` 注解，chart 内无 ServiceMonitor / PodMonitor。`/metrics` 端点存在且渲染出 `health-http` 端口，但没有任何采集器被 chart 接线到它 → 标准部署下 Prometheus 收不到 `as_*` 序列 | **如实写进文档，未假装已生效**：`deploy/alerts/README.md` §Scrape wiring status 明确「这是已知未闭合缺口，上面的规则不是 live」；看板 README 状态块同样前置标注；`runbook-l2.md` §8 第 5 项列为「已知会误导排障的坑」。**本次不修 chart**（超出改动面） | `deploy/helm/templates/deployment.yaml`（唯一注解是 `checksum/config`）；`deploy/helm/templates/` 全目录 grep 无命中；`deploy/alerts/README.md` §Scrape wiring status |
| 2 | **新增 5 条告警中多数缺生产数据生产者**：3 条读 kube-state-metrics（集群侧提供），`ASDownscaleBlocked` 读 `as_*`（每 15s 无条件写入但**受抓取缺口影响**） | 在 `deploy/alerts/README.md` §New rules 表格增设 **「Currently triggerable?」** 列，逐条标注当前可触发性，不笼统写「已覆盖」 | `deploy/alerts/README.md` §New rules（2026-10-10, delivery 2.2） |
| 3 | **ISC 超时 / 会话泄漏 / TLS 证书到期无指标**：`MetricKind` 只有 `COUNTER` 与 `GAUGE`，仓库**无 histogram / summary**，无超时计数器、无会话开闭对、无证书到期 gauge | **列入 deferred，不写假规则**。`deploy/alerts/README.md` §Deferred 逐项写「为何现在不能加」+「退出条件」；看板 README §4 明确「时延面板建了就是假面板，比没有更糟」 | `platform/src/as_platform/telemetry/metrics.py`；`deploy/alerts/README.md` §Deferred alerts；看板 README §4 |
| 4 | **chart 无 `kubeVersion` 声明**（`deploy/helm/Chart.yaml` 只有 `apiVersion: v2`），预检无法直接读出集群版本下限 | `preflight.sh` **按模板实际使用的 K8s API 推导下限**，并在输出中注明「chart 无 kubeVersion 声明，此下限按模板实际使用的 API 推导」，同时提供环境变量可覆盖 | `docs/delivery/preflight.sh`（脚本头注释与「K8s 版本下限」检查项输出） |
| 5 | **`Chart.yaml` 的 `version` / `appVersion` 与根 `VERSION` 不同步**：`VERSION` = `0.2.0`，chart 为 `version: 0.0.0-skeleton` / `appVersion: "0.0.0"` | **记为缺口，只给建议不改代码**（改 chart 超出本次改动面）。`docs/product/version-lifecycle.md` §2.4 专节如实记录 | 根 `VERSION`；`deploy/helm/Chart.yaml`；`docs/product/version-lifecycle.md` §2.4 |
| 6 | **`608` 与 `603` 口径差**：`608 Rejected (RFC 8688)` 仍出现在 `apps/README.md`、`apps/anti-fraud/README.md`、`apps/anti-fraud/pyproject.toml` 与 `docs/architecture/新系统整体架构.md` 的 POC 现状描述中，产品路径实际只发 `603 Decline` | **符合性矩阵以代码为准并记录口径差**：标为 `open（未实现）`，写明是否新增 608 需**新 ADR + 契约变更**；`runbook-l2.md` §8 第 7 项把「把 608 当产品拒绝码」列为已知坑 | `docs/product/compliance-matrix.md` §3.8（`decision.py:22-25` 注释把 608 归为适配层关注点）；`runbook-l2.md` §8 #7 |
| 7 | **3.5 的上游决策已落地**（上一轮 G-P1-9 已新增 REQ-NF-16 与 ADR-0027 并注册） | `version-lifecycle.md` **只逐条转述** ADR-0027 已接受的决定，**不新增承诺**；4.3 API 兼容标「待决策、无 ADR」并给出口条件 | `docs/requirements/prd.md` REQ-NF-16；`docs/architecture/adr/0027-version-lifecycle-and-eol.md`；`version-lifecycle.md` §3 / §7 |
| 8 | **`docs/acceptance/` 已有 runbook 会被重复建设** | **原件保留不动**（不删除、不移动、不改写），`runbook-l1.md` / `runbook-l2.md` 只做**归集 + 索引 + 来源映射表**（命令原文照抄，冲突处显式标注） | `runbook-l2.md` 状态块「原件保留」+ §10 来源映射表 |
| 9 | **本次代码侧改动面可能被误解为「改了产品」** | **只改 `deploy/alerts/` 两个文件**（`as-alerts.yaml` 新增 `as.runtime` / `as.platform` 两组共 5 条规则，`as.call-path` 原 5 条**逐字未改**；`README.md` 同步新增规则、指标契约、抓取接线现状、deferred 清单）。**未改任何产品代码** | `deploy/alerts/as-alerts.yaml`（3 组 10 条规则）；`deploy/alerts/README.md` |
| 10 | **两处相对链接层级错误**（跨目录相对路径少算一级） | 已修：`grafana-dashboards/README.md` 的 `../../deploy/alerts/README.md` → `../../../deploy/alerts/README.md`；`runbook-l2.md` 的 `../../architecture/adr/0021-runtime-override-granularity.md` → `../architecture/adr/0021-runtime-override-granularity.md` | 见 §5 链接校验 |
| 11 | **D5 / O4 未决时 PDPO 文档容易被写成「已合规」** | `security-privacy.md` 只描述留存范围、删除机制与数据留港原则，保留期限与存储选型显式标注为待裁决；**依赖漏洞扫描与渗透测试只写计划，不伪造结果** | `docs/product/security-privacy.md` |

---

## 5. 已执行的验证

| 验证项 | 方法 | 结果 |
|---|---|---|
| 相对链接全量校验 | 对 `README.md`、`docs/README.md`、`docs/product/*.md`、`docs/operations/**/*.md`、`docs/delivery/*.md` 提取 Markdown 相对链接并逐个检查目标存在 | **19 个文件 / 494 条相对链接 / 缺失 0** |
| Shell 脚本语法 | `bash -n` | `preflight.sh` 通过；`bundle-images.sh` 通过；`load-images.sh` 通过（3/3） |
| `preflight.sh --dry-run` 行为与退出码 | `bash docs/delivery/preflight.sh --dry-run` | 正常输出分节报告：`PASS=0 FAIL=3 WARN=0 SKIP=10`，`FAIL` 三项为「未找到 kubectl / helm / 无法渲染 chart」（本机无这两个工具），**退出码 = 1**（有 FAIL 时拒绝继续安装，行为符合设计） |
| 告警规则 YAML 结构 | `yaml.safe_load` 解析 `deploy/alerts/as-alerts.yaml` | 解析成功；**3 个规则组**（`as.call-path` / `as.runtime` / `as.platform`）、**共 10 条规则**；原 5 条 + 新增 5 条；`as.capacity` 组**不存在**（符合 O1 纪律） |
| Grafana JSON 可解析 | `json.load` 两份看板 | 均解析成功；`overview.json` 15 面板 / `sip-signaling.json` 7 面板；`templating` 均含 `datasource` 与 `AS_NAMESPACE` |
| 看板指标白名单核对 | 提取 `targets[].expr` 中全部 `as_*` 指标名，与 README §5 的 6 个白名单求差 | **零违规**（两份看板使用的 `as_*` 全在白名单内）；**无** `histogram_quantile` |
| 交付物存在性与规模 | `wc -l` 逐个打开确认 | 见 §1 各表；全部存在，行数与记录一致 |

### 未执行的验证（如实标注为待办）

| 验证项 | 状态 | 原因 |
|---|---|---|
| `promtool check rules deploy/alerts/as-alerts.yaml` | **未执行** | 本机 `promtool` **不可用**（`command -v promtool` 无命中）。规则文件**未经 promtool 校验**，这是遗留待办 |
| `helm lint` / `helm template` / chart 部署验证 | **未执行** | 本机 `helm` **不可用** |
| `make gate` | **未运行** | 本次**不改产品代码**，无代码改动需要门禁；且不把「未跑」说成「已过」 |
| 真实集群演练（2.4 摘流 / 2.5 备份恢复） | **未执行** | 依赖真实集群与 S-CSCF / HSS 侧配合；M8 7.2d 仍 blocked |

---

## 6. 未做的事（清单 + 原因）

| # | 未做的事 | 原因 |
|---|---|---|
| 1 | 交付物 **4.2**（7×24 长稳测试报告） | 计划已定为 v1.1 / 按需，不纳入当前里程碑 |
| 2 | 交付物 **4.4**（产品白皮书 / 架构白皮书） | 第四批锦上添花，不纳入当前里程碑 |
| 3 | 交付物 **4.5**（能力开放机制文档） | 计划已定为 v1.1 / 按需，不纳入当前里程碑 |
| 4 | 交付物 **4.1** 的正式性能基准报告 | O1 未裁决；本次只交付方法学章节 |
| 5 | **O1 / O4 / D5 相关的一切数值**（容量、保留天数、恢复时长） | 未裁决项不得由 agent 自行取值 |
| 6 | 真实集群演练（摘流 / 回退、备份恢复） | M8 7.2d 仍 blocked；2.4 另需 S-CSCF / HSS 侧配合 |
| 7 | 维护者评审与签字 | 本文件是执行记录；评审人待指定 |
| 8 | `promtool check rules` | 本机工具不可用 |
| 9 | `helm lint` / 部署验证 / `make gate` | 本机工具不可用；本次不改产品代码 |
| 10 | 抓取接线修复（chart 加注解或 PodMonitor） | 属 chart 工作，超出本次改动面；已作为缺口记录 |
| 11 | `Chart.yaml` 的 `version` / `appVersion` 与 `VERSION` 同步 | 只记缺口给建议，不改代码 |
| 12 | 新增 608 支持、Record-Route 等口径修正 | 需新 ADR + 契约变更 + 评审，超出本次改动面 |
| 13 | **任何 git 操作** | **本次明确未提交任何 commit**：未 `git commit`、未 `git add`、未改分支、未改 remote、未打 tag |

---

## 7. 遗留风险与建议

| # | 项 | 风险 | 建议动作 | 责任方 |
|---|---|---|---|---|
| R1 | **告警抓取接线未闭合** | 标准部署下 Prometheus 收不到 `as_*` 序列，所有 `as_*` 规则与面板「无数据」。若在客户材料中把它们描述为「已在生产生效」，属**不实陈述** | 单独一次 chart 改动：Pod 模板加 `prometheus.io/scrape` + `prometheus.io/port`（端口名 `health-http`），或加 `PodMonitor` / `ServiceMonitor`；随后跑 `promtool check rules` 并在真实集群验证 | 维护者批准后由开发执行 |
| R2 | **`promtool check rules` 从未运行过** | 10 条规则的 PromQL 语法 / 表达式正确性未经工具校验，只有 YAML 层面解析通过 | 在有 `promtool` 的环境跑一次 `promtool check rules`，结果回写本文件 §5 | 开发 / CI |
| R3 | **`Chart.yaml` 版本与 `VERSION` 不同步** | `VERSION` = `0.2.0`，chart 仍是 `0.0.0-skeleton`。交付给运营商时 chart 版本不代表产品版本 | 维护者裁决：交付时是否要求二者同步；若要求，需一次显式改动并说明与 ADR-0018「一个数字一个家」的关系 | 维护者 |
| R4 | **chart 无 `kubeVersion` 声明** | 集群过旧时可能在渲染后才失败，失败点晚、难定位。当前由 `preflight.sh` 按模板实际使用的 API 推导下限作为补偿 | 补 `kubeVersion` 声明（需确认模板实际使用的最低 API 版本），或维持脚本推导并写明依据 | 维护者 + 开发 |
| R5 | **608 / 603 口径差仍在代码库其它位置** | `apps/README.md`、`apps/anti-fraud/README.md`、`apps/anti-fraud/pyproject.toml`、架构文档 POC 现状描述仍写 608，产品路径只发 603。文档链不一致 | 维护者裁决是否实现 608；无论裁决如何，先把这几处描述与代码对齐（属 docs 改动，需单独一次改动） | 维护者裁决 → 开发 / 文档 |
| R6 | **O1 / O4 / D5 未决持续阻塞** | Datasheet 容量章节、PDPO 保留期限、容量类告警、性能报告全部停在「只给方法，不给数值」 | 推进维护者裁决；裁决后按各文档 §「何时可填 / 出口条件」回填 | 维护者 |
| R7 | **真实集群证据缺位** | 2.4 / 2.5 只有方案没有演练记录；M8 退出签字仍搁置；E1 / E4 / E5 未验收 | 在 M8 7.2d 解锁后安排真实集群演练并回填记录模板 | 维护者 + 客户环境 |
| R8 | **A 类交付物尚无维护者评审** | 按 `AGENT.md` §3.2「所有文档必须有 review」，未评审的文档不能进入下一阶段 | 指定评审人，对本批交付物出 review record；评审意见回写各文档 | 维护者 |
| R9 | **`docs/operations/README.md` 与 `docs/acceptance/` 的索引可能随原件变动而失效** | 原件保留不动是正确纪律，但索引会腐化 | 后续每次改 `docs/acceptance/*-runbook.md` 时同步核对 `runbook-l1/l2.md` 的来源映射表 | 文档维护者 |

---

## 8. 签字栏

> 本次**执行**已完成并由主 agent 核对；**评审与签字尚未发生**。以下全部留空，由维护者填写。

| 角色 | 姓名 | 结论 | 日期 | 签字 |
|---|---|---|---|---|
| 执行者（AI agent） | — | 已落盘并自检（见 §5） | 2026-10-10 | — |
| 主 agent 核对 | — | 改动面与自述一致（见 §5 验证） | 2026-10-10 | — |
| 维护者评审人 | **待指定** | ☐ 通过　☐ 有条件通过　☐ 不通过 | | |
| 维护者（架构） | | ☐ 通过　☐ 有条件通过　☐ 不通过 | | |
| 维护者（运维 / NOC） | | ☐ 通过　☐ 有条件通过　☐ 不通过 | | |
| 维护者（网络部对接） | | ☐ 通过　☐ 有条件通过　☐ 不通过 | | |

**在上述签字完成前，本批交付物的状态一律为「已落盘，待维护者评审」，不得在任何对外材料中表述为「已验收」。**

---

## 9. 追溯

| 本记录章节 | 依据 / 来源 |
|---|---|
| §1 交付物清单 | `docs/product-packaging-plan.md` §1（四批交付物）、§2（目录结构）、§3.2（A / B 分类） |
| §2 执行方式 | `AGENT.md` §10.1（subagent 派发）、§10.2（状态落盘去向） |
| §3 结论分类 | `AGENT.md` §2（容量数字禁令）、§15（未决项）；`docs/product-packaging-plan.md` §3.2 |
| §4 问题清单 | `deploy/alerts/README.md`、`deploy/alerts/as-alerts.yaml`、`platform/src/as_platform/telemetry/metrics.py`、`deploy/helm/Chart.yaml`、根 `VERSION`、`docs/product/compliance-matrix.md` §3.8、`docs/product/version-lifecycle.md` §2.4/§3/§7 |
| §5 验证方法 | `docs/operations/grafana-dashboards/README.md` §6（建议的最小自检）、`deploy/alerts/README.md` §Loading |
| 格式与纪律 | `AGENT.md` §3.3（Review Record 五要素）；`docs/reviews/product-packaging-plan-review-2026-10-09.md` |
| 阻塞源 | `docs/plan.md` §5.1（O1 / O4 / O5）、§5.2（D5）、§5.4（M8 7.2d） |
| 暂用名与决策状态 | `docs/plan.md` §0 产品决策记录（2026-10-09） |
