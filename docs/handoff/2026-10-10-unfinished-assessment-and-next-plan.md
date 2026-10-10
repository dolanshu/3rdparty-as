# 未完成项评估与下一步计划（2026-10-10）

## 0-A. 动工前的裁决门禁（阻断清单）—— 下一 session 开场必读

> **编号说明（请先读）**：本块为**新增前置节**，插在既有 §0（维护者裁决，含 §0.1 / §0.2）**之前**，故采用 `0-A` 编号，以避免与既有 `§0.1` / `§0.2` 重号。既有全部小节编号（§0 / §1 … §10）**一个都没改**。
>
> 本 session 只做评估、计划与落盘，**不动工**。下一 session 若在本 handoff 上开工，必须**先**处理 §0-A.2 的裁决门禁：未裁决项不得默认执行，也不得以「先做着」的方式绕过 —— `AGENT.md` §15（不要悄悄解决一个未决项）与 §10.4（开场仪式）要求如此。裁决前，`AGENT.md` §2 的容量纪律（M6 实测之前不发布任何容量数字）、§15 的未决项规则（O1 未裁决前不假设任何容量数字，且不得悄悄解决未决项），以及 `plan.md` §5 的未决项登记，继续有效。

### 0-A.1 已授权、可立即执行的三项（但仍需维护者每次显式批准）

1. **`promtool` 容器化语法校验** —— 本机有 `docker`、无 `promtool`：以容器等价命令执行 `promtool check rules`。
2. **W0-A2 真栈构建常态化** —— `make m2-platform-resip-build` → `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate`（等价 `make gate-native`）。
3. **W0-A3 Phase A 三个 pytest 复验** —— 须在 A2 之后执行；其中第三个目标 `platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200` 是 `integration` 标记，**不在** `make gate` 默认收集范围内，**须显式指定**才能跑到。

命令原文见 §5（另见 §10.3 的启动项清单）。这三项**不依赖**任何未决裁决，但执行前**仍需维护者一句话批准**：**评审通过不等于执行授权**（与 §0.2 的「开工状态」、§10.3 一致）。

### 0-A.2 阻断型裁决清单（不裁决就无法动）

| 编号 | 要裁决什么 | 不裁决会怎样（冻结哪项工作） | 选项与推荐所在处 |
|---|---|---|---|
| **G1** | **B4 Python 3.10 EOL**：走选项①（3.12 验证 spike）还是选项②（登记 accepted risk） | 决定 W0-A2 那一次 native 构建是否顺带做迁移验证；也是 on-prem 基础镜像合规问题 | §9（尤其 §9.4 两个选项） |
| **G2** | **A4 e2e 四项裁决**（改 marker 还是新建文件 / 缺 native 时 fail 还是 skip / Wave 2 本迭代必做还是单开 issue / kind e2e 是否进 PR required） | e2e Wave 1 不能落地；CI 侧是否转阻塞无从讨论 | §8.1 |
| **G3** | **A5 告警抓取接线选型**（A `prometheus.io/scrape` 注解默认 vs B `ServiceMonitor` / `PodMonitor` 优先） | chart 抓取接线不能落地。注意：**`promtool` 只是语法校验，不等于抓取接线已闭合** | §8.2 |
| **G4** | **A6 版本口径**（A / B / C 三方案选哪个；`kubeVersion` 是否声明） | Chart 版本与交付包一致性不能动 | §8.3 |
| **G5** | **B1 O1 分级裁决**（三级是否照此执行、是否启用「内部目标值 / 对外承诺值」区分）+ **NF-3 是否改 n-a** | HPA 阈值、容量类告警、`ne-datasheet.md` 的容量取值、4.1 性能基准报告全部冻结 | §8.4 |
| **G6** | **B2 O4 呼叫轨迹保留期取值** + **D5 轨迹存储选型** | `security-privacy.md` 的 PDPO 保留期限与存储方案冻结 | §8.5 |
| **G7** | **B3 O5 容灾等级** + **D3 Redis HA 拓扑**（N+1 + Sentinel vs N+M） | `backup-restore.md` 的 RPO / RTO 与 HA 章节冻结 | §8.6 |
| **G8** | **产品正式命名 / 目标场景的决策落点**（目标场景方向 A、暂用名 In-house IMS Application Server 是否补 plan / ADR 正式决策行；git repo 改名 `inhouse-ims-as` 是否执行 —— **属远端操作**） | 仓库名与对外材料口径不一致；改名涉及目录名与 remote URL | `docs/product-packaging-plan.md` §4.1 / §4.3 |

**G1 是唯一会「搭 W0 顺风车」的裁决**：若选①，可与 A2 那一次 native 构建合并执行；错过这次就要多一轮构建。

### 0-A.3 已后置（不阻断本机 W0，但重启需另外的授权或资源）

- **CI 整体工作**：A1（CI workflow 重写与推送）、N1（`workflow` scope PAT 授权）、§3 里「重写 workflow」这一纠正路径（本文记为 **§3-a**）。
- **外部 IOT 与真实环境采证**：D-1（运营商 PKI + 外网 S-SBC）、D-2（客户 K8s REQ-NF-1 live）、2.4 摘流 / iFC 配合与 2.5 备份恢复的真实集群演练。
- **M8 退出签字**：排队在上述两项之后。

**重启条件**：**维护者另行裁决 + 外部资源到位**。后置 ≠ 取消，但**不得因本机工作顺带推进**（依据 §0 第 1–3 项裁决及其口径说明）。

### 0-A.4 本 session 收尾状态

- 本 session **不动工**：未执行任何构建 / 测试 / 容器 / CI 动作。
- **评审链已闭环并代签**：结论「有条件通过（accepted as a planning baseline）」，签字栏由维护者 2026-10-10 授权的 AI agent 代签 —— 见本块之后的文首状态块与 §10。
- 所有产出留在工作树，**由维护者本人 commit / push**。

### 0-A.5 这块怎么维护

开场若发现 G1–G8 任一项已被裁决，须在本块**追加**一行写明裁决结果与日期，并同步到 `plan.md` §0 决策记录；**不得静默删除本块**。

### 0-A.6 裁决记录（2026-10-10）

| 门禁 | 裁决结果 | 边界与保留事项 |
|---|---|---|
| **G1 / B4** | 选项①：做 Python 3.12 验证 spike | 仅完成处置选择；本次**未授权/未执行**该 spike。是否与 W0 的 native build 绑定执行**未裁决**。本次不改 pin、不改 lockfile、不运行任何相关动作。 |
| **G2 / A4-1** | e2e 采用**单独文件**：`testbed/e2e/test_sip_first_edition.py` | 保留现有 integration tests，不做替换。 |
| **G2 / A4-2** | 缺少必需 native extension 时，e2e **fail** | 不使用 skip 作为缺失原生扩展时的通过替代。 |
| **G2 / A4-3** | Wave 2 的 14 条回放用例后置到独立 issue | 本迭代仅登记为 gap；本任务**不创建 issue**。 |
| **G2 / A4-4** | kind e2e 的方向是纳入 PR required 的 E2E policy | 该方向**不构成** CI workflow 变更授权；CI 仍处于 hold，本任务不改任何 CI 文件。 |
| **G3 / A5** | 维持待决：annotation vs ServiceMonitor/PodMonitor **暂不选边** | 等待运营商 monitoring-integration 标准输入；当前不改 chart。FM 指 Fault Management，按新 feature 流程管理，实施时补 demo/功能文档；本次不发明需求、不实现。 |
| **G4 / A6** | 根 `VERSION` 为唯一源；release 时同步 Chart `version` / `appVersion` | `kubeVersion` 需要声明；其最小值由所用 API 反推，本次不作数值裁决。当前不修改 `VERSION` 与 `Chart.yaml`。 |
| **G5 / B1 + NF-3** | 采纳 O1 三级决策流程，并区分内部目标与外部承诺 | 在 M6 证据与维护者决策前，不落容量取值、不落 HPA 阈值、不落容量类告警。REQ-NF-3 继续适用且 blocked；其固定数值型验收断言需另行修订/后置处理，不能把整条 requirement 标记 N/A。 |
| **G6 / B2 + D5** | O4 默认呼叫轨迹保留期为 10 天（部署可配）；D5 选 in-cluster PostgreSQL；Redis 保持 runtime checkpoint 存储 | 本次不实现轨迹存储/查询/删除能力。清理触发点与时间起算口径归入实现细节待定义，不作为保留期未决项。 |
| **G7 / B3 + D3** | O5 基线为站点内 N+1、跨站 1+1 warm standby；D3 选 Redis primary/replica + Sentinel（沿用 ADR-0008 拓扑），不选 Redis Cluster | 当前不承诺机架/AZ 级容错，不裁决 RTO/RPO 数值；本次不授权实现或上线验收。 |
| **G8-1** | 目标场景正式口径：3HK 内部生产就绪/发版评审 | 同步记录到 `docs/plan.md`；除非架构边界变化，不新增 ADR。 |
| **G8-2** | 正式采用 `In-house IMS Application Server` 作为产品/文档描述名 | 描述名属性，不作为商标/品牌宣称。 |
| **G8-3** | GitHub repo 重命名 `inhouse-ims-as` 记为维护者报告已完成 | 本仓库内不执行 remote 或本地路径改动。 |

> 以上均为**裁决落盘记录**，不是执行授权；所有执行动作仍需维护者逐次明确批准。

> **口径优先级追加说明（2026-10-10）**：对 G1–G8 中已在 §0-A.6 记载的事项，**以本节同日裁决记录为准**；§0-A.2 的阻断清单与 §0.2 中「A4/A5/A6/B1/B2/B3 全待裁决」等较早表述保留为历史审计链，不作删改。**G3（A5 监控接线）仍待运营商 monitoring-integration 标准输入，当前不改 chart。**本节及相关裁决记录仅用于状态落盘，**不构成执行授权、外部验收通过或 REQ/里程碑签收**。
> 对已在本节落盘为 resolved 的事项，文首状态块末行「所有取值仍待维护者裁决」及同类全量待决表述按历史语境保留，但以 §0-A.6 记录为控制口径；CI hold、外部 IOT/真实环境采证 hold 与执行授权冻结口径维持不变。

---

> **本文状态：已落盘，待维护者评审。**
>
> - 本文是**盘点与排期**，不是验收记录：**不签收任何 REQ，不签收任何里程碑，不新增任何决策**。
> - 凡需要拍板的一律写成「**待维护者裁决**」，本文不给方案、不选边。
> - 事实基线：`master @ 86cceca`（message `package phase 1 done`），工作树干净；`make gate` 本次本地实测 **1002 passed / 10 skipped / 206 deselected / 11 warnings**（exit 0）。
> - 本文**不含任何容量或性能数字**；出现的数字只有测试计数、文件/条目计数与版本号。
> - 本文若被推翻或修正，须**追加行**说明，不得静默替换（见 §7）。
> - （2026-10-10 追加）本文已通过评审：`docs/reviews/unfinished-assessment-2026-10-10-review.md` 结论为**有条件通过（accepted as a planning baseline）**，签字栏已由维护者 2026-10-10 授权的 AI agent 代签。**本文仍不签收任何 REQ / 里程碑，所有取值仍待维护者裁决，所有执行项（含 W0）仍须维护者另行批准后方可启动。**

---

## 1. 方法与非承诺

### 1.1 证据来源

| 来源 | 覆盖内容 |
|---|---|
| 仓库文件（`docs/plan.md`、`docs/acceptance/report.md`、`.github/workflows/ci.yml`、`Makefile`、`VERSION`、`deploy/helm/Chart.yaml` 等） | 文档状态、门禁定义、版本口径 |
| git 历史（`git log`、`git log --all -S`、`git stash list`、分支与 remote-tracking 引用） | 某段内容是否真的存在于仓库/历史/分支/stash |
| 本次本地实测（`make gate`、marker 收集、`.so` 查找、工具探测） | 门禁计数、skip 构成、真栈是否可跑、本机缺哪些工具 |

### 1.2 本次**没能跑**的部分（不得当作绿的）

| 未能执行 | 原因 | 影响 |
|---|---|---|
| 真栈（reSIProcate）相关用例 | 本机无 `_resip_runtime` / `_resip_recovery` 的 `.so`（`find` 无命中） | 相关用例是 **skip，不是通过**；不得作为真栈行为证据 |
| `make chart-check` | 本机无 `helm` | chart 形状门禁未在本机复验 |
| `make alert-check`（`promtool check rules`） | 本机无 `promtool` | 告警规则语法未校验 |
| kind 集群证据（`deploy/kind/m5-*.sh`） | 本机无 `kind` / `kubectl` | 任何集群级证据不在本次范围内 |
| CI | 本机不运行 GitHub Actions；且当前仓库 `ci.yml` 为旧版（见 §3） | 本地门禁绿 **不等于** CI 通过 |

本机可用工具：`uv` 有、`docker` 有；`helm` / `kubectl` / `kind` / `promtool` **均无**。

### 1.3 非承诺

- 本文不解除任何未决项（O1/O2/O3/O4/O5、D1/D3/D5/D6/D11/D12 等）。
- 本文不修改既有的 milestone 状态、签收矩阵状态或决策行。
- 本文不执行任何 git 写操作（`git add` / `git commit` / `git tag` / `git push` / 建分支 / 改 remote 一律不做）。

---

## 0. 维护者裁决（2026-10-10）

> **本节为追加**：按 §7.3 的保史原则，本节不改动、不删除既有任何文字。下文 §2 及其后各节若出现与本节不一致的旧表述，**一律以本节为准**；旧表述保留不动，以维持审计链完整。

维护者于 **2026-10-10** 作出三条裁决（**照录，未改写措辞**）：

| # | 裁决项 | 覆盖范围 | 影响（哪些条目因此从当前工作中移出） |
|---|---|---|---|
| 1 | **CI 整体工作 hold，后置** | A1（CI workflow 重写与推送）、N1（`workflow` scope PAT 授权），以及 §3 里「重写 workflow」这一纠正路径 | A1 整体移出当前工作；§3 中与流水线绑定的纠正路径（本文记为 **§3-a**）随 A1 后置；W0 中的「A1 草案」与「提请授权」两步移出；B5 / N1 的 push 环节移出 |
| 2 | **所有外部 IOT / 真实环境采证 hold，后置** | D-1（运营商 PKI + 外网 S-SBC）、D-2（客户 K8s REQ-NF-1 live）、2.4 摘流 / iFC 配合与 2.5 备份恢复的真实集群演练 | Lane C 中依赖外部环境的部分整体移出（**C2、C3、C4 全部**；**C1 与 C5 只有需要运营商 PKI 或客户 K8s 的部分**）；W0 / W3 中的外部采证步骤移出 |
| 3 | **M8 退出签字后置** | M8 退出签字动作本身 | 签字排队在第 1、2 项完成之后再处理；B5 的 N1 → N2 → N3 → N4 序列中，签字类动作排在 CI 与外部采证之后 |

口径说明（避免误读）：

- **后置 ≠ 取消。** 目标是保留的：CI 增强仍然是想要的能力，外部 IOT 采证仍然是要做的证据，M8 退出签字仍然要签。**改变的只是它们不在当前工作范围内。**
- 因此本文不再把 CI 称作「当前工作」，但也不把 A1 / C 栏写成「已废弃」或「已完成」。它们的准确状态是：**已被维护者 decision 后置**。
- 第 1 项带来的边界，请用这一句话理解：**CI 不再是「当前工作」，但目标还在。** 在 CI 工作重启之前，任何依赖 CI 运行结果的出口判据都不得被宣称为已达成。

### 0.1 本节与下文的关系（读法）

- 下文 §4 Lane A 的 **A1**、**Lane C 各条目**、§5 的分波表格都保留了本次裁决前的原文；每处已**追加**一行状态标记 `**状态：后置（维护者 2026-10-10 裁决）**`，并链回本节。
- **例外，且务必看清**：E1 / E4 / E5 的**本地真栈部分**（S1–S4 harness、自签证书的 TLS 热轮换 smoke）**不属于外部 IOT**，不因第 2 项裁决后置，仍随 A2 / A3 在 W0 推进。细节见 §5 的「W0 范围调整」追加段。

### 0.2 维护者认可项（2026-10-10）

> **本节为追加**（2026-10-10）。维护者已对下列四点表示**全部同意**，但要求**先落盘、不要开工，待其 review**。措辞照录语义，未代为改写。

| # | 认可项 | 内容（一句） | 影响（解锁什么、仍未裁决什么） |
|---|---|---|---|
| 1 | **E1 / E4 / E5 边界** | **本地真栈部分**（S1–S4 harness、自签证书的 TLS 热轮换 smoke、checkpoint / 恢复的工程 harness）继续推进；**仅**需要运营商 PKI 或客户 K8s 的**外部部分**后置 | **解锁**：A2 / A3 的推进范围得以收窄并确定（与 §0.1 的例外段、§5 的「W0 范围调整」一致）。**仍未裁决**：本地真栈各条的出口判据与排期属执行面，待维护者批准启动后再落地；外部部分（D-1 / D-2、真实集群演练）的重启时点仍随 §0 第 2 项后置 |
| 2 | **`promtool` 用本机 docker 跑** | 授权执行 `docker run --rm -v $PWD/deploy/alerts:/a prom/prometheus promtool check rules /a/as-alerts.yaml`（本机有 `docker`、无 `promtool`）；**但本次不开工**，待 review 后再由维护者批准后执行 | **解锁**：§1.2 表格里「`make alert-check` 未运行」一条具备关闭路径（结果须**追加**记录，不得改写原行）。**仍未裁决**：A5 抓取接线的 A / B 选型（§8.2）本身仍未裁决；`promtool` 只校验告警规则语法，**不等于**抓取接线已闭合 |
| 3 | **A6 解释（版本口径）** | `Chart.yaml` 的 `version` / `appVersion` 字段**不受** `AGENT.md` §8「任何成员不得拥有 `VERSION` 文件」约束，因此「release 流程从根 `VERSION` 同步到 chart」这一路径**不违反**该条 | **解锁**：§8.3 方案 A 的合规前提在**解释层面**成立，不再因 §8 的约束而被排除。**仍未裁决**：A / B / C 三方案**究竟选哪个**、`kubeVersion` 是否声明及其取值，均仍待裁决 |
| 4 | **B3 定位（D3 Redis）** | D3 的 Redis **客户端接线已于 2026-10-05 resolved**；当前未决的**只剩 HA 拓扑**（N+1 vs N+M、Sentinel vs Cluster 等） | **解锁**：§8.6 的讨论范围收窄到 HA 拓扑一项，历史表述里「D3 未决」的连带理解相应收窄。**仍未裁决**：究竟选 N+1 + Sentinel 还是 N+M（或 Redis Cluster 等），以及 O5 容灾等级取值本身 |

**口径边界（非常重要，请勿误读）**：上列四条是**边界、口径、定位、许可**层面的认可，**不等于** §8 中 A4 / A5 / A6 / B1 / B2 / B3 六项建议的**取值**已被裁决。六项的取值**仍全部待维护者裁决**：

| 项 | 取值待裁决的内容 |
|---|---|
| **A4**（e2e 四项） | ① 改 marker 还是新建文件；② 缺 native 时 fail 还是 skip；③ Wave 2 的 14 条本迭代必做还是单开 issue；④ kind e2e 是否进 PR required |
| **A5**（抓取接线） | A（`prometheus.io/scrape` 注解）与 B（`ServiceMonitor` / `PodMonitor` 模板）的选型与叠加顺序 |
| **A6**（版本口径） | 三方案 **A / B / C 选哪个**；`kubeVersion` 是否声明及取值 |
| **B1**（O1 分级裁决） | 三级阶段的划分是否照此执行；阶段 2 是否启用「内部目标值 / 对外承诺值」的区分 |
| **B2**（O4 / D5） | O4 保留期的具体取值（即使是「默认值 + 部署期可配」的默认值）、D5 存储选型 A / B / C 选哪个 |
| **B3**（O5 / D3 HA 拓扑） | 究竟 N+1 + Sentinel，还是 N+M；是否启用 Redis Cluster 作为客户驱动的升级项 |

**开工状态**：**本次只落盘，未开工。** `promtool` 已获授权但**待 review 后再执行**；W0（A2 真栈构建常态化、A3 Phase A 复验）**等待维护者明确批准后启动**。本次未执行任何构建、测试、容器或 CI 动作 —— 明细见 §10。

---

## 2. 当前基线快照（实测）

### 2.1 git 与工作树

| 项 | 实测结果 |
|---|---|
| 分支 / HEAD | `master`，HEAD `86cceca`，message `package phase 1 done` |
| `origin/master` | 同为 `86cceca`（**同步，无领先/落后**） |
| 工作树 | **干净**，无未提交改动 |
| 分支列表 | 只有 `master`（历史分支已清理） |
| `git stash list` | **空** |
| 陈旧引用 | 本地残留 `origin/callload`、`origin/cur`（远端已删）；可 `git fetch --prune` 清理 —— **属维护者操作，本文不执行** |

### 2.2 本地门禁（`make gate`，本次运行，exit 0）

| 项 | 实测结果 |
|---|---|
| 组成 | `ruff format --check` → `ruff check` → `mypy` → `pytest -m "unit or contract"` |
| 计数 | **1002 passed / 10 skipped / 206 deselected / 11 warnings** |

10 个 skip 的构成：

| 数量 | 位置 | 原因 |
|---|---|---|
| 7 | `platform/tests/native_extensions.py:24` | `_resip_runtime` 未构建 |
| 1 | `platform/tests/test_sip_recovery.py:69` | `_resip_recovery` 未构建 |
| 2 | `testbed/simulators/tests/test_derived_baseline.py` | S1 基线无 Route / 无 Record-Route，需 M2 probe 补 |

### 2.3 测试标记分布（本次实测）

| marker | 命中文件数 | 备注 |
|---|---|---|
| `pytest.mark.integration` | **35 个文件** | — |
| `pytest.mark.e2e` | **0 个文件** | 全仓库 `pytest -m e2e` 收集 **0 条** |
| `performance` | 仅 testbed harness 类 | 非产品路径 |

### 2.4 版本事实

| 文件 | 值 |
|---|---|
| 根 `VERSION` | `0.2.0` |
| `deploy/helm/Chart.yaml` | `version: 0.0.0-skeleton`、`appVersion: "0.0.0"` |

两者**不同步**。受 `AGENT.md` §8 约束（任何成员不得拥有 `VERSION` 文件），**同步口径属待维护者裁决**，本文不提方案。

### 2.5 既有文档状态（作为输入，不改写）

| 文档 | 状态 |
|---|---|
| `docs/plan.md` §0 / §2 / §4 / §5 | M8 = **RC 产物就绪、退出签字搁置**；M2/M4/M5/M6/M7/M7.1 为**工程关门/工程完成**，**不等于 REQ 级验收**；未决项 O1–O5、D1/D5/D11/D12 |
| `docs/acceptance/report.md` §0.5 签收矩阵（2026-10-06） | pass 9 / fail 0 / blocked 12 / n-a 4 / **open 24** |
| `docs/handoff/2026-10-07-m8-next-step-plan.md` | N1（workflow push，需 `workflow` scope PAT）→ N2（9 项书面裁决）→ N3（open 里可签的行）→ N4（停止线） |
| `docs/handoff/2026-10-09-sip-native-testing-plan.md` | Phase A 已改动、B 有命令，**C、D 未完成**；文末 Sign-off 三个 checkbox 全未勾 |
| `docs/acceptance/2026-10-09-e2e-test-plan.md` | **草案、未实现**；§6 有 4 项待维护者裁决 |
| `docs/product-packaging-plan.md` §5 与 `docs/reviews/product-packaging-execution-record-2026-10-10.md` | **16 份包装文档已落盘，0 份已评审**；遗留 4 项（抓取接线未闭合、`promtool` 未跑、版本不同步、无 `kubeVersion`）；批次 4.1–4.5 未做 |

---

## 3. 需要纠正的一条文档事实（重要）

### 3.1 偏差

`docs/acceptance/report.md` §0.3（F9 / A-1）称：

> 「origin blocking native CI 为 **workflow-ready-locally** —— `.github/workflows/ci.yml` 已含 `m2-platform-resip` / `chart-check` / `m2-native-smoke` / `m7-*` 阻塞式 jobs …… 但 **push 待维护者 PAT（`workflow` scope）**，见 merge handoff §6；RC 内未推送。」

但仓库当前实际的 `.github/workflows/ci.yml`：

| 项 | 实际内容 |
|---|---|
| job 列表 | 只有 `fast`（①）/ `integration`（②）/ `e2e`（③）/ `performance`（④） |
| `m2-platform-resip` | **无** |
| `chart-check` | **无** |
| `m7-*`（recovery / two-leg） | **无** |
| `gate-strict` | **无** |
| `e2e` / `performance` | 仍为 `continue-on-error: true`（文件第 92、116 行） |
| 最后一次改动该文件的 commit | `73c9321`（内容仍为 2026-09-29 的旧版形态） |

### 3.2 核实过程与证据命令

| 步骤 | 命令 / 路径 | 结果 |
|---|---|---|
| 读当前文件 | `.github/workflows/ci.yml` | 4 个 job，无 native / chart-check / gate-strict |
| 查该文件的最后改动 | `git log --oneline -- .github/workflows/ci.yml` | 末次 `73c9321` |
| 全历史 + 全分支搜字符串 | `git log --all -S "m2-platform-resip" -- .github/workflows/ci.yml` | **零命中** |
| 查 stash | `git stash list` | **空** |
| 查分支 | `git branch -a` | 只有 `master` |
| 查 commit 是否触碰该文件 | `git show --stat 18f2bb7` | commit `18f2bb7`（2026-10-09，`Fix S1 harness SDP on the real stack and document e2e gaps.`）的 message 声称新增 native-contract CI job，但**未触碰** `.github/workflows/ci.yml` |

> 补充：`docs/acceptance/report.md` 第 33 行还称 `gate-strict`「进 CI ① 且阻塞」，同样与实际文件不符；该行也依赖同一份不存在的 workflow。

### 3.3 结论与影响

**结论：该版 workflow 增强内容当前不存在于仓库任何位置 —— 不在工作树、不在 git 历史、不在任何分支、不在任何 stash。它不是「等待 PAT push」，而是「尚未写入，需要重写」。**

影响：

1. **origin CI 并不阻塞真栈行为**：没有 native job，缺 `_resip_runtime` 时 CI 不会 fail（本地是 skip）。
2. **merge 门禁未验 UDP/TLS 产品栈**：`report.md` §0.3 F9 所声称的「阻塞式 native 门禁」在当前 origin 上**并未生效**，基于该声称的任何「门禁已具备」的推论都不成立。
3. **`report.md` §0.3 的 A-4 行（gate-strict 阻塞）同样不成立**，需一并纠正。
4. **纠正方式待维护者裁决**：是改写 `report.md` §0.3 的措辞、还是先重写 workflow 再保留原文，本文不代为决定。

### 3.4 纠正路径拆分（2026-10-10 追加）

> 本节回应 §0 第 1 项裁决。§3.3 第 4 点的原文保留不动；本节在其后**追加**，把原来看成一件事的「纠正」拆成两条独立路径 —— 它们不是同一件事，不得混为一谈。

| 路径 | 内容 | 归属 | 当前状态 |
|---|---|---|---|
| **§3-a** | 重写 CI workflow，使其具备上述能力：native-contract 阻塞 job、`chart-check` job、`gate-strict` job，以及 `e2e` / `performance` 的 `continue-on-error` 处置 | **CI 工作** | **随 A1 后置**（§0 第 1 项）。**已被 decision 后置，不是取消**；CI 工作重启之前不做 |
| **§3-b** | 纠正 `docs/acceptance/report.md` §0.3（第 30 行 F9、第 33 行 A-4）与现实不符的措辞 | **纯文档** | **与流水线无关，不由 A1 阻塞，可立即执行**。已在 `docs/acceptance/report.md` §0.3 以「追加更正（2026-10-10）」段落落地（只追加，不改写第 30、33 行原文一个字） |

**为什么建议 §3-b 先做（建议，维护者未裁决）**：真正的风险不在仓库里少了一段 workflow —— 少一段只是能力缺口，是已知的、写在这里的。**风险在于对外备忘录与验收报告继续声称一项当前并不存在的能力**（「origin blocking native CI」、「`gate-strict` 进 CI ① 且阻塞」），而这个声称会被下游读者当作既成事实，进而推导出「门禁已具备」的结论。因此建议把 §3-b 排在 §3-a 之前：它不需要任何 pipeline 改动、不需要 `workflow` scope PAT、不触碰 `.github/workflows/ci.yml`，也不受 CI 后置这一裁决影响。

**§3-a 的保留条件**：CI 工作重启时，此处由被指派者连同 A1 一并处理。在此之前，`.github/workflows/ci.yml` 与 `docs/acceptance/report.md` §0.3 的原文保持不动，仅以追加段落/追加小节标注，**不得静默替换**。

---

## 4. 未完成项清单

分四条泳道。**每条的「出口判据」都是可勾选、可验证的**；「谁做」列标为 维护者 / agent / 需外部环境。

### Lane A · 门禁与证据自动化（agent 可做，优先）

#### A1 · CI workflow 重写并推送

- **状态：后置（维护者 2026-10-10 裁决）** —— 依据见 §0 第 1 项。**目标保留，当前不做**；下文其余各行（现状 / 范围 / 出口判据 / 依赖）原样保留，作为 CI 工作重启时的输入。

- **现状与证据**：仓库 `.github/workflows/ci.yml` 仍为旧版（§3）；`report.md` §0.3 的描述不成立。
- **为什么未完成**：该 workflow 内容从未写入仓库，需从零重写，不是 push 授权问题。
- **需要的 job（范围，非定稿）**：
  - native-contract 阻塞 job（缺 `_resip_runtime` 即 fail，非 skip）；
  - `chart-check` job；
  - `gate-strict` job（REQ-G-3 ADR 标注扫描）；
  - `e2e` 与 `performance` 的 `continue-on-error` 处置 —— **必须与 A4 的 Wave 1 决定绑定**（见 A4），不得私自改阻塞。
- **出口判据**：
  - [ ] `.github/workflows/ci.yml` 中可 `grep` 到 native-contract / `chart-check` / `gate-strict` 三个 job 名；
  - [ ] 该文件被提交的 commit 出现在 `git log -- .github/workflows/ci.yml`；
  - [ ] `git log --all -S "m2-platform-resip" -- .github/workflows/ci.yml` 有命中；
  - [ ] CI 上该 workflow 至少一次真实运行结果已留档（**本机不可执行**，需 CI）；
  - [ ] `report.md` §0.3 F9 / A-4 的措辞纠正方式已由维护者裁决并执行。
- **依赖**：①「`workflow` scope PAT 授权」（维护者）；②「由谁重写」的授权（维护者）；③ A4 的 Wave 1 决定。
- **谁做**：**agent（需维护者先授权 PAT 与重写范围）**。

#### A2 · 真栈构建常态化

- **现状与证据**：Makefile 已有 `gate-native`（第 133–134 行）= `m2-platform-resip-build` + `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate`；本机无 `.so`，7+1 条真栈用例为 skip。
- **为什么未完成**：从未在本机跑过一次带真栈的门禁，skip 无法充当证据。
- **出口判据**：
  - [ ] `make m2-platform-resip-build` 成功；
  - [ ] `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate`（或直接 `make gate-native`）跑通；
  - [ ] 原 7 条 `native_extensions.py` skip **消失**（真实执行）；
  - [ ] 一次完整 run 结果（计数与 exit code）已记录到 handoff 或 review record。
- **依赖**：无（不依赖任何裁决）。
- **谁做**：**agent**。

#### A3 · SIP native plan 收尾（`docs/handoff/2026-10-09-sip-native-testing-plan.md`）

- **现状与证据**：
  - Phase A：已在 commit `18f2bb7` 改动 `runtime_module.cxx` 与两个 E1 契约测试（`platform/tests/test_e1_contract_resip_runtime.py`、`platform/tests/test_e1_contract_resip_runtime_full.py`）；但**未见真栈复验记录**；
  - Phase B：命令已具备（`make gate-native`）；
  - Phase C：**未完成** → 并入 A1；
  - Phase D：**未完成**（S1 的 14 条回放、S5–S11 真栈用例）→ 待排期；
  - Phase E：M2 smoke，与 A2 同源；
  - 该 plan 文末 Sign-off 三个 checkbox **全未勾**。
- **为什么未完成**：Phase A 的改动未经真栈复验；C/D 无产物。
- **出口判据**：
  - [ ] A2 完成后，Phase A 的三个复验目标**每一条**都有真实执行结果并留档 —— ① `uv run pytest platform/tests/test_e1_contract_resip_runtime.py platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q`（含 `test_e1_s1_accept_all_harness_returns_200` 与 `test_e1_s1_accept_all_from_contract_invite` 两条）；② `uv run pytest platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200 -q`（`integration` 标记，**不在** `-m "unit or contract"` 收集范围内，须显式指定）；
  - [ ] Phase C 由 A1 承接并落地；
  - [ ] Phase D 的范围与批次已排期（写入本文或新 plan，需维护者确认优先级）；
  - [ ] 该 plan 文末 Sign-off 三框的处置（勾选或标注未完成）已明确。
- **依赖**：A2（先有真栈）、A1（Phase C）。
- **谁做**：**agent**（Phase D 排期需维护者确认优先级）。

#### A4 · e2e 落地

- **现状与证据**：`pytest -m e2e` 收集 **0 条**；`pytest.mark.e2e` 命中 **0 个文件**；`docs/acceptance/2026-10-09-e2e-test-plan.md` 为草案（Wave 0–4 设计），§6 有 **4 项待维护者裁决**：
  1. Wave 1 是改 `test_product_path` 的 marker，还是新建文件；
  2. 缺 native 扩展时 e2e 应 **fail** 还是 **skip**；
  3. Wave 2 的 14 条对拍，本迭代必做还是单开 issue；
  4. kind e2e 是否**永不**进 PR required。
- **为什么未完成**：裁决未答，且首条用例未落；CI ③ 的 `continue-on-error` 因此不能自行改。
- **出口判据**：
  - [ ] 上述 4 项裁决有维护者书面答复（落 `plan.md` §5 或该 plan 文档）；
  - [ ] Wave 1 落地，`pytest -m e2e` 收集 **≥ 1 条**且稳定通过；
  - [ ] 首条用例稳定后，按 `AGENT.md` §9 将 CI ③ 改为阻塞的处置已执行（与裁决 2 / 4 一致）；
  - [ ] e2e 计划文档状态由「草案」更新。
- **依赖**：维护者 4 项裁决；A1（CI ③ 处置）。
- **谁做**：**agent（先请裁决）**。

#### A5 · 可观测性接线闭环

- **现状与证据**（来自 `docs/reviews/product-packaging-execution-record-2026-10-10.md`）：
  1. 告警抓取接线**未闭合**：chart 无 `prometheus.io/scrape` 注解、无 `ServiceMonitor` / `PodMonitor`；
  2. `promtool check rules` **未运行**（本机无 `promtool`）；
  3. `Chart.yaml` version/appVersion 与根 `VERSION` **不同步**；
  4. chart 无 `kubeVersion` 声明。
- **为什么未完成**：无抓取接线 → Grafana 看板与 metrics 序列在标准部署中**收不到数据**；告警规则语法未校验。
- **出口判据**：
  - [ ] chart 侧抓取接线（annotations 或 ServiceMonitor/PodMonitor）已实现 —— **具体选型待维护者裁决**；
  - [ ] `promtool check rules deploy/alerts/as-alerts.yaml` 在有 `promtool` 的环境跑过并留档（**本机不可执行**；等价容器命令亦需维护者确认允许）；
  - [ ] 版本口径按 A6 裁决执行；
  - [ ] `kubeVersion` 是否声明按 A6 裁决执行；
  - [ ] 上述每项留 review record（`AGENT.md` §3）。
- **依赖**：A6 裁决（其中两项）、有 `promtool` 的环境、helm（chart 验证）。
- **谁做**：**agent + 需外部环境（`promtool` / helm / 集群）**。

#### A6 · 版本口径裁决（先裁决，再动）

- **现状与证据**：根 `VERSION` = `0.2.0`；`deploy/helm/Chart.yaml` = `0.0.0-skeleton` / `appVersion: "0.0.0"`；chart 无 `kubeVersion`。
- **为什么未完成**：`AGENT.md` §8 规定任何成员不得拥有 `VERSION` 文件 → 同步动作的权限归属未定。
- **出口判据**：
  - [ ] 维护者书面裁决：`Chart.yaml` 的 `version` / `appVersion` 是否同步到根 `VERSION`、由谁改；
  - [ ] 维护者书面裁决：chart 是否声明 `kubeVersion`，若是则取值；
  - [ ] 裁决结果落 `plan.md` §5（或 ADR），再执行改动。
- **依赖**：维护者裁决。
- **谁做**：**维护者（裁决）→ agent（执行）**。

### Lane B · 维护者裁决（阻塞验收与多个交付物）

#### B1 · O1 容量目标

- **现状与证据**：`docs/plan.md` §5.1 中 O1 仍 open（「维护者目标裁决仍 open」）。
- **阻塞**：HPA 阈值（M5）、容量类告警、`docs/product/ne-datasheet.md` 的容量取值、包装批次 **4.1 性能基准报告**。
- **出口判据**：- [ ] 维护者给出目标值并落 `plan.md` §5.1；- [ ] 上述 4 项下游随之更新并留 review record。
- **谁做**：**维护者**。

#### B2 · O4 呼叫轨迹保留期 + D5 轨迹存储选型

- **现状与证据**：`docs/plan.md` §5.1 O4（阻塞 M4）、§5.2 D5（阻塞 M4，与 O4 相关）均 open。
- **阻塞**：`docs/product/security-privacy.md` 的 PDPO 保留期限与存储方案。
- **出口判据**：- [ ] O4 保留期已裁决；- [ ] D5 存储选型已裁决；- [ ] `security-privacy.md` 相应章节按裁决更新。
- **谁做**：**维护者**。

#### B3 · O5 容灾等级 + D3 Redis HA 拓扑

- **现状与证据**：`docs/plan.md` §5.1 O5（N+1 节点 vs N+M 机架/AZ）open；§5.2 D3 的客户端接线已 resolved，**HA 拓扑仍挂在 O5**。
- **阻塞**：`docs/operations/backup-restore.md` 的 RPO/RTO 与 HA 章节。
- **出口判据**：- [ ] O5 等级已裁决；- [ ] D3 HA 拓扑随之确定；- [ ] `backup-restore.md` 相应章节按裁决更新。
- **谁做**：**维护者**。

#### B4 · D1 Python 3.10 EOL

- **现状与证据**：`docs/plan.md` §5.2 D1 —— Python 3.10 在 2026 年 10 月到达 EOL；产品锁 3.10 因 sippy 验证过该版本。
- **为什么未完成**：二选一未定 —— 迁移，或在 ADR 里登记为**已接受 risk**。
- **出口判据**：- [ ] 维护者选定路径；- [ ] 若选 risk 接受，须有对应 ADR 记录（`AGENT.md` §15）。
- **谁做**：**维护者**。

#### B5 · M8 的 N2 九项书面裁决 → N3 → N4

- **现状与证据**：`docs/handoff/2026-10-07-m8-next-step-plan.md`：N1（workflow push，需 `workflow` scope PAT）→ N2（9 项书面裁决，含 M5D-1…M5D-6 落 `plan.md` §5、NF-3 改 n-a、D6 放 v1.1）→ N3（open 里可签的行）→ N4（停止线）。
- **为什么未完成**：N1 未落地（且按 §3，N1 的前提 —— workflow 内容 —— 尚不存在）；N2 未裁决；N3 未执行。
- **出口判据**：
  - [ ] N1：workflow 内容重写（A1）+ PAT 授权 + push（**需维护者授权**）；
  - [ ] N2：9 项裁决有书面记录并落 `plan.md` §5；
  - [ ] N3：open 中确定可签的行按流程签收；
  - [ ] N4：停止线全程未被越过。
- **依赖**：A1、PAT 授权。
- **谁做**：**维护者（裁决与授权）+ agent（执行）**。

#### B6 · 产品化包装 16 份文档的评审

- **现状与证据**：`docs/product/`（6 份）、`docs/operations/`（8 份文档 + 2 份看板 JSON + README）、`docs/delivery/`（3 份文档 + 脚本）共 **16 份已落盘**，`docs/reviews/product-packaging-execution-record-2026-10-10.md` 记录为 **0 份已评审**。
- **为什么未完成（且重要）**：这批文档 materially 影响「Phase 1 能否当作工程完成」——未经评审的包装文档不得作为对外交付或验收依据。
- **出口判据**：
  - [ ] 16 份文档逐份评审，结论（accept / 需修改 / 驳回）留 review record；
  - [ ] 需修改项闭环后复评；
  - [ ] `docs/product-packaging-plan.md` §5 的批次状态按评审结果更新。
- **谁做**：**维护者**。

### Lane C · 需外部环境的验收（本机 / 本仓库无法自证）

> 共同出口判据：**在拿到环境之前不得宣称绿**；每项须有留档证据 + review record。

| 编号 | 内容 | 所需环境 | 谁做 |
|---|---|---|---|
| **C1** | E1 / E4 / E5：reSIProcate 生产路径行为、TLS 证书热轮换、状态外置与恢复<br>**状态：部分后置（维护者 2026-10-10 裁决，见 §0）** —— 只有需要运营商 PKI 或客户 K8s 的部分后置；**本地真栈部分（S1–S4 harness、自签证书的 TLS 热轮换 smoke）不在后置范围**，仍随 A2 / A3 推进 | 真栈 + 产品部署环境 | **需外部环境**（执行可 agent，环境由维护者提供） |
| **C2** | D-1：运营商 PKI + 外网 S-SBC（REQ-S-2 / REQ-S-3）<br>**状态：后置（维护者 2026-10-10 裁决，见 §0）** | 运营商侧配合窗口 | **需外部环境** |
| **C3** | D-2：客户 K8s REQ-NF-1 live（kill / restart / BYE）<br>**状态：后置（维护者 2026-10-10 裁决，见 §0）** | 客户 K8s 集群 | **需外部环境** |
| **C4** | 包装 2.4 摘流 / iFC 配合演练、2.5 备份恢复演练记录<br>**状态：后置（维护者 2026-10-10 裁决，见 §0）** | 真实集群 + S-CSCF/HSS 侧配合窗口 | **需外部环境** |
| **C5** | `docs/plan.md` §5.4 的 REQ 补测：REQ-F-13 live Call-ID trace、REQ-F-15 完整 AS 栈、REQ-S-4 正式全绿、PostgreSQL 16 follow-up<br>**状态：后置（维护者 2026-10-10 裁决，见 §0）** | 信令/集成栈 + 目标环境 | **需外部环境** |

- **依赖**：B2（C1 的恢复路径与 B3 的 HA 拓扑相关）、B5（M8 重开前提）。
- **排期**：由维护者排；本文不假定时间。
- **追加说明（2026-10-10）**：上表每行已就地追加状态标记（原文未改）。按 §0 第 2 项裁决，**C2 / C3 / C4 整体后置**；**C1 与 C5 仅其中需要运营商 PKI 或客户 K8s 的部分后置**。其中 **C1 的本地真栈部分不属于外部 IOT**，仍随 A2 / A3 在 W0 推进，边界见 §5 的「W0 范围调整」追加段。本 lane 其余约定不变：**在拿到环境之前不得宣称绿**。

### Lane D · 延后 / 候选（不纳入当前里程碑）

| 编号 | 内容 | 归属 | 备注 |
|---|---|---|---|
| **4.2** | 7×24 长稳报告 | **v1.1 / 按需** | 不纳入当前里程碑 |
| **4.3** | API 版本兼容策略 | 需 requirement + ADR + review record | 属新增决策，不在本文范围内提出 |
| **4.4** | 白皮书 | 按需 | 未做 |
| **4.5** | 多业务能力开放机制 | **v1.1** | 未做 |

- **出口判据**：- [ ] 维护者确认归属（v1.1 / 按需 / 取消）；- [ ] 若启动，须走 requirement → ADR → HLD/LLD → 契约 → 代码+测试 → 验收项 + review record（`AGENT.md` §3）。
- **谁做**：**维护者（决定是否启动）**。

---

## 5. 建议执行顺序（分波）

> **命令说明**：凡标注「**本机不可执行**」的，均因本机缺 `helm` / `kubectl` / `kind` / `promtool`，需在具备工具的环境运行。

### W0 · 不依赖任何裁决，可立刻做

**状态：等待开工批准（2026-10-10 认可边界，但未授权启动）** —— 依据见 §0.2（第 1 项认可的是 E1 / E4 / E5 的**边界划分**，不是开工许可）。W0 的 A2 / A3 步骤在维护者明确批准启动前**一律不执行**。

**目标**：把「skip 当证据」这一最大缺口补上；同时把 PAT 授权问题提给维护者。

| 步骤 | 命令 | 备注 |
|---|---|---|
| A2 真栈构建 | `make m2-platform-resip-build` | 本机可执行 |
| A2 真栈门禁 | `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate`（等价：`make gate-native`） | 本机可执行 |
| A3 Phase A 复验 | `uv run pytest platform/tests/test_e1_contract_resip_runtime.py platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q`，加上 `uv run pytest platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200 -q`（`integration` 标记，不在默认 gate 收集内，须显式指定） | 本机可执行（须在 A2 之后） |
| A5 告警规则校验 | `promtool check rules deploy/alerts/as-alerts.yaml` | **本机不可执行**（无 `promtool`）；需有该工具的环境或容器 |
| M7 扩展（如需） | `make m7-platform-recovery-build`、`make m7-platform-two-leg-build` | 本机可执行；用途按 A2/A3 结果决定 |
| A1 草案 | 起草 `.github/workflows/ci.yml` 增强版（native-contract / `chart-check` / `gate-strict`） | **先不动文件**，等维护者授权与 PAT |
| 提请授权 | 向维护者提出：① `workflow` scope PAT；② 由谁重写 workflow；③ 是否授权 push | 属 B5/N1 |

**出口判据**：`make gate-native` 跑通且原 7+1 条 skip 变为真实执行；一次 run 结果已留档；A3 复验有结果留档。

**明确不动**：不改 `VERSION`、不改 `Chart.yaml`、不改 `docs/plan.md` 既有文字、不改 `report.md`、不打 tag、不 push、不新开分支。

**2026-10-10 追加：W0 的范围调整（按 §0 第 1、2 项裁决）**

> 上面的 W0 表格原文保留不动；本节在其后**追加**范围口径。凡本节与上表冲突处，以本节为准。

**W0 保留且仍是当前工作的步骤**：

| 保留步骤 | 命令 / 动作 | 为什么不受裁决影响 |
|---|---|---|
| A2 真栈构建 | `make m2-platform-resip-build` | 本机可执行；不依赖 CI，不依赖任何外部环境 |
| A2 真栈门禁 | `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate`（等价 `make gate-native`） | 同上；这是「skip 当证据」这一最大缺口的唯一收口手段 |
| A3 Phase A 复验 | `uv run pytest platform/tests/test_e1_contract_resip_runtime.py platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q`，加上 `uv run pytest platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200 -q`（`integration` 标记，不在默认 gate 收集内，须显式指定） | 本机可执行，须在 A2 之后 |
| A5 中的 `promtool` 容器化执行 | 本机无 `promtool` 但有 `docker`，建议用容器等价命令立即执行 —— 见 §8 第 2 项的推荐 | 不依赖集群、不依赖 CI；属本机可完成的工作 |

**`promtool` 容器命令的状态（2026-10-10 追加）**：上表末行的等价命令 `docker run --rm -v $PWD/deploy/alerts:/a prom/prometheus promtool check rules /a/as-alerts.yaml` —— **已获授权，未执行**。维护者已授权用本机 docker 跑该命令，但本次**不开工**，须待其 review 后再行批准执行。依据见 §0.2 第 2 项，命令与风险见 §8.2。

**从 W0 移出的步骤（后置，不取消）**：

| 移出项 | 依据 |
|---|---|
| A1 草案（起草 `.github/workflows/ci.yml` 增强版） | §0 第 1 项：CI 整体工作 hold、后置 |
| 提请授权（`workflow` scope PAT / 由谁重写 / 是否授权 push） | §0 第 1 项：N1 一并后置 |
| 所有 C 栏外部采证（D-1、D-2，以及 2.4 / 2.5 的真实集群演练） | §0 第 2 项：外部 IOT 与真实环境采证整体后置 |

**关于 E1 / E4 / E5 的边界（这条最容易搞错，请照此执行）**：这一组里，**本地真栈部分 —— S1–S4 harness 的执行，以及自签证书的 TLS 热轮换 smoke（二者都只依赖本机 + 已构建好的 native 扩展）—— 不属于外部 IOT**，因此**不因 §0 第 2 项裁决而后置**，仍作为 A2 / A3 的下游在 W0 推进。**只有**需要运营商 PKI（真实证书链、外网 S-SBC）或客户 K8s 集群（live 的 kill / restart / BYE、真实集群上的摘流 iFC 配合与备份恢复演练）的部分才后置。

**W0 出口判据的调整（追加）**：原出口判据中依赖 CI 运行结果或外部环境的部分，在 CI / 外部采证重启之前**暂不适用**；W0 当前只看三件事 —— ① `make gate-native` 跑通且原 native skip 变为真实执行；② 一次完整 run 的结果已留档；③ A3 Phase A 复验有结果留档。

### W1 · e2e 与版本口径（先请裁决）

**目标**：拿到 A4 的 4 项裁决与 A6 的版本口径裁决。

| 步骤 | 动作 |
|---|---|
| A4 | 请维护者答复 `docs/acceptance/2026-10-09-e2e-test-plan.md` §6 的 4 项裁决；裁决落地后再动 Wave 1 |
| A4 | Wave 1 落地后：`uv run pytest -m e2e -q` 应收集到至少 1 条 |
| A4 | 首条用例稳定后，按 `AGENT.md` §9 处置 CI ③（与裁决 2 / 4 一致） |
| A6 | 请维护者裁决 `Chart.yaml` version/appVersion 与根 `VERSION` 的同步口径、`kubeVersion` 是否声明 |

**出口判据**：4 项裁决 + A6 裁决均有书面记录（落 `plan.md` §5 或 ADR）；`pytest -m e2e` 收集 ≥ 1 条。

**明确不动**：裁决未到前不改任何 marker、不改 CI 的 `continue-on-error`、不动 `VERSION` / `Chart.yaml`。

### W2 · 维护者集中裁决（B 栏）

**目标**：一次性请维护者裁决 B1–B6。

| 编号 | 请求内容 |
|---|---|
| B1 | O1 容量目标值（阻塞 HPA 阈值、容量告警、Datasheet、4.1） |
| B2 | O4 保留期 + D5 轨迹存储选型 |
| B3 | O5 容灾等级（并连带确定 D3 Redis HA 拓扑） |
| B4 | D1 Python 3.10 EOL：迁移还是 ADR 登记为已接受 risk |
| B5 | M8 N2 九项裁决（M5D-1…M5D-6 落 `plan.md` §5、NF-3 改 n-a、D6 放 v1.1）→ N3 → N4 |
| B6 | 16 份包装文档的评审 |

**出口判据**：每项裁决落 `plan.md` §5 或 ADR；下游文档与代码随裁决更新并留 review record。

**明确不动**：裁决未落前不改 `report.md` / 签收矩阵状态（open 24 / blocked 12 不得改 pass）。

### W3 · 外部环境的验收（C 栏）

**目标**：排期 C1–C5，并在拿到环境后逐项留证。

| 编号 | 环境依赖 |
|---|---|
| C1 | 真栈 + 产品部署环境；可先 `make m7-platform-recovery-build` / `make m7-platform-two-leg-build` 准备本机侧 |
| C2 | 运营商 PKI + 外网 S-SBC 窗口 |
| C3 | 客户 K8s 集群 |
| C4 | 真实集群 + S-CSCF/HSS 侧配合窗口 |
| C5 | 信令/集成栈；REQ-F-13 / REQ-F-15 / REQ-S-4 / PostgreSQL 16 |

**出口判据**：每项有留档证据 + review record；**在拿到环境之前不得宣称绿**。

**明确不动**：不以本机 skip / 本地门禁绿充抵 C 栏任何一项。

### 附：本机可复制命令一览

```bash
# W0（本机可执行）
make m2-platform-resip-build
AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate     # 等价：make gate-native
uv run pytest platform/tests/test_e1_contract_resip_runtime.py platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q
uv run pytest platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200 -q   # integration 标记，不在 -m "unit or contract" 收集内，须显式指定
make m7-platform-recovery-build
make m7-platform-two-leg-build

# 本机不可执行（缺工具/环境）
promtool check rules deploy/alerts/as-alerts.yaml   # 缺 promtool
deploy/helm/scripts/chart-check.sh                  # 缺 helm（等价 make chart-check）
# kind 集群证据脚本 deploy/kind/m5-*.sh             # 缺 kind / kubectl

# W1
uv run pytest -m e2e -q
```

---

## 6. 停止线（本文及后续工作都不越过）

1. **不谎称全绿**：`report.md` §0.5 的 open 24 / blocked 12，未经 `docs/handoff/2026-10-07-m8-next-step-plan.md` 的 N2 / N3 流程不得改为 pass。
2. **不自行解决未决项**：O1 / O4 / O5 / O2 / O3、D1 / D3 / D5 / D6 / D11 / D12 等必须先落 `docs/plan.md` §5 或 ADR（`AGENT.md` §15）；本文只登记，不裁决。
3. **本地门禁绿 ≠ CI 通过**；**本机无真栈时的 skip 不是证据**。
4. **不打 tag、不 push**（除维护者明确授权的 workflow 提交）、**不 bump `VERSION`**、不建分支、不改 remote。
5. **任何改动仍须贯通**：requirement → ADR → HLD/LLD → 契约 → 代码 + 测试 → 验收项 + review record（`AGENT.md` §3）。
6. **e2e 首条用例落地前，CI ③（`e2e` job）的处置只能按 A4 的 wave-decision 二选一**，不得私自改阻塞。
7. **不把未跑的当绿的**：`chart-check` / `alert-check` / kind 证据 / CI 运行在本机均无结果，一律标注为未执行。
8. **不签收**：本文不签收任何 REQ、不签收任何里程碑、不新增任何决策。

---

## 7. 状态口径与后续回写

### 7.1 本文状态

**已落盘，待维护者评审。** 本文是盘点与排期，未经验收，不构成任何 REQ 或里程碑的签收。

### 7.2 何时应回写

| 触发 | 回写位置 |
|---|---|
| 维护者评审本文通过（或给出修改意见） | `docs/plan.md` §0 的入口小节补一句状态；必要时在本文追加评审结论行 |
| A1 / A2 / A3 / A4 / A5 / A6 任一落地 | `docs/plan.md` §0（状态）与本文对应条目（勾选出口判据） |
| B6 的 16 份包装文档评审有结论 | `docs/product-packaging-plan.md` §5 与 `docs/reviews/product-packaging-execution-record-2026-10-10.md` |
| §3 的文档事实纠正被执行 | `docs/acceptance/report.md` §0.3（F9 / A-4 行）—— 纠正方式待维护者裁决 |
| 产生了对外可见的变更 | `CHANGELOG.md`（按既有格式，不 bump 版本） |

### 7.3 被推翻时的处理

本文的任何结论若被后续证据或维护者裁决推翻，**须在本文末尾追加一行说明**（日期 + 被推翻的条目 + 依据），**不得静默替换或删除原文**，以保持审计链完整。

---

## 8. 待维护者裁决：建议与选项（2026-10-10，均为建议，未裁决）

> **本章全部内容都是建议（维护者未裁决）。** 本章不新增任何决策、不选边到执行、不解除任何未决项。
> 每项的结构统一为：**现状 → 选项（含优缺点 / 成本 / 风险）→ 主 agent 推荐项 → 解锁 / 阻塞**。
> 本章**不含任何容量或性能数字**；出现的数字只有条目计数、用例计数、文件 / 行号与版本号。

### 8.1 A4 e2e 四项裁决（`docs/acceptance/2026-10-09-e2e-test-plan.md` §6）

**现状（一句）**：e2e 目前是一份草案，`pytest -m e2e` 收集到 0 条、`pytest.mark.e2e` 命中 0 个文件，而草案 §6 的 4 项裁决未答，导致首条用例无法落地、CI ③ 的处置也不能自行决定。

**① 改 `test_product_path` 的 marker，还是新建文件**

| 选项 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A | 改现有 `test_product_path` 的 marker，把它标成 e2e | 零新文件，立刻可被 `-m e2e` 收集 | 该文件原本承担 integration 语义；改 marker 后**开发者本机快跑的一条路径消失**，且 e2e 与 integration 的边界被抹平，后续难以再区分「本机可跑」与「需完整栈」 |
| B | 新建 `testbed/e2e/test_sip_first_edition.py` | **保留 integration 供开发者本机快跑**；e2e 语义独立、收集路径清晰 | 需新增文件与 `testbed` 下的归属判断（纯文件新增，属可立即执行的工作量） |

**推荐：B（新建 `testbed/e2e/test_sip_first_edition.py`）**。
**解锁**：e2e 首条用例的落地位置确定，④ 的阻塞性讨论才有对象。**阻塞**：无 —— 不依赖 CI、不依赖外部环境的驳回 Blocker。

**② 缺 native 扩展时，e2e 是 fail 还是 skip**

| 选项 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A | skip | CI / 本机都不会因环境缺 native 而变红 | **skip 容易被读成绿**；与 native-contract 已有的收紧方向相反；会把 A2 正在修补的「skip 当证据」缺口重新打开一个口子 |
| B | fail | 与 native-contract 的口径一致（缺扩展即 fail），**防止 skip 冒充绿** | 环境不具备时会红；需要先把 native 构建跑起来 —— 这正好是 A2 已经在做的事，成本被摊薄 |

**推荐：B（fail）**，并建议与 A2 的真栈构建常态化同时出场，避免长期红。
**解锁**：②④ 的判定口径收敛。**阻塞**：若长期不跑 A2，e2e 会持续红 —— 属执行风险，不是技术风险。

**③ Wave 2 的 14 条对拍：本迭代必做，还是单开 issue**

| 选项 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A | 本迭代必做 | 一次性把覆盖率补齐 | 在「还没有第一条稳定 e2e」的前提下铺开 14 条，骨架与判定口径都未站稳；返工面大 |
| B | 单开 issue，本迭代只做 Wave 1（T1 / T4 / F2 结果码 + BYE 不挂死 + TCP / TLS 各一条） | 先把 **e2e 从 0 变成非零**；骨架、命名、判定与留档方式先固化 | 覆盖率不带回本迭代，需在 issue 里登记范围 |

**推荐：B（单开 issue，本迭代只做 Wave 1）**。**理由**：现在 `-m e2e` 是 0 条，CI ③ 怎么设阻塞都没有意义 —— **e2e 必须先从 0 变成非零，CI ③ 才有讨论阻塞的资格**。
**解锁**：Wave 1 可交付并留档。**阻塞**：Wave 2 的 14 条推迟到该 issue，不影响本迭代任何出口判据。

**④ kind e2e 是否永不进 PR required**

| 选项 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A | 进 PR required | 门禁最严 | 本机与 CI runner 都**没有 kind**，PR 会被永久卡红；且 CI 工作已按 §0 第 1 项后置，短期内无法调整该文件 |
| B | 不进 PR required，仅 nightly / `workflow_dispatch` | 不在 PR 关键路径上制造永久红灯；有 kind 的环境里仍可随时手动触发 | 需要有人在具备条件的环境里保留一条手动运行约定 |

**推荐：B（不进 PR required，仅 nightly / `workflow_dispatch`）**。
**解锁**：④ 有答案后，将来 CI 重启时 ③ job 的处置方式可一次性写清。**阻塞**：当前不阻塞任何动作（CI 工作已后置本就不可改）。

### 8.2 A5 告警抓取接线选型

**现状（一句）**：chart 侧既无 `prometheus.io/scrape` 注解，也无 `ServiceMonitor` / `PodMonitor` 模板，因此标准部署下 Grafana 看板与 metrics 序列收不到数据；`promtool check rules` 也因本机无该工具而未跑（§1.2 已登记为「未执行」）。

| 方案 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A | chart 在 metrics 开关下输出 `prometheus.io/scrape` 注解，**默认关闭** | **不需要任何 CRD**；符合 ADR-0013「Helm-only、无 operator 依赖」的精神；客户集群不装 Prometheus Operator 也能工作 | 只能接最基础的一路抓取；多 job / 高级 relabel 场景表达力弱 |
| B | 提供可选的 `ServiceMonitor` / `PodMonitor` 模板 | 表达力强，契合已装 Prometheus Operator 的客户 | 依赖客户集群已装 CRD；**必须做 fail-closed 处理**，否则客户没装 CRD 时 `helm install` 直接失败 |

**推荐：A 为默认路径；B 作为后续可选模板叠加（二者不是互斥，是先后）**。
**另有一条可立即执行的建议（维护者未裁决）**：`promtool check rules` 不必等有该工具的环境 —— 本机无 `promtool` 但有 `docker`，可在**本机 docker** 上直接执行等价命令：

```bash
docker run --rm -v $PWD/deploy/alerts:/a prom/prometheus promtool check rules /a/as-alerts.yaml
```

绿则可以把 §1.2 表格里「`make alert-check` 未运行」这一条划掉（**须以追加方式记录结果，不得改写原行**）。**风险**：需要拉取 `prom/prometheus` 镜像，属本机网络操作；若本机环境不允许拉取镜像，该条维持「未执行」状态，不得默认其为绿。

**维护者 2026-10-10 认可该项的解释/定位（取值仍待裁决）** —— 认可的是「授权用本机 docker 跑 `promtool`」这一**许可**；**已获授权，未执行**，待 review 后再批准执行。A5 的 A / B 抓取接线**选型取值仍待裁决**。见 §0.2 第 2 项。

**解锁**：抓取选型定后，A5 的前两项出口判据可以开始落地；`promtool` 一条可以先关闭。**阻塞**：版本口径（§8.3）未裁决前，A5 的「版本口径」「`kubeVersion`」两项仍悬着。

### 8.3 A6 版本口径（`Chart.yaml` version / appVersion vs 根 `VERSION`）

**现状（一句）**：根 `VERSION` 是 `0.2.0`，而 `deploy/helm/Chart.yaml` 是 `version: 0.0.0-skeleton` / `appVersion: "0.0.0"`，两者不同步；且 chart 没有 `kubeVersion` 声明。

| 方案 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A | release 流程从根 `VERSION` **同步**到 chart（`VERSION` 是唯一源头，ADR-0018 精神） | 「一个数字一个家」；产品版本与交付物版本不会漂移 | 需要一个明确的 release 步骤（谁在什么时候同步），并扩展 `tests/test_version_consistency.py` 的守卫断言 |
| B | chart 版本与产品版本**语义解耦**，chart 自带独立版本号，并在 `deploy/helm/README.md` 写清 | chart 迭代节奏可以独立于产品 | 需 ADR 裁决这算不算「一个数字两个家」；解释成本落在交付文档与 release 流程上 |
| C | 维持现状，仅在交付文档注明「chart version 与产品 `VERSION` 无关」 | 零改动 | 现状里这个注明**目前还没写**；口径仍是隐性的，每次对外回答都要临时解释 |

**推荐：A**。并请维护者确认一处解释：**chart 的 `version` 字段不是 `AGENT.md` §8 所禁止的「成员拥有 `VERSION` 文件」**（那条约束针对的是工作区成员自带版本源），因此 A **不违反** `AGENT.md` §8 —— 这一解释须由维护者确认后再执行。
**`kubeVersion`**：建议声明，取值可由 chart 实际用到的 API 推导（`docs/delivery/preflight.sh` 中已有同类推导逻辑可复用，不必从零写）。

**维护者 2026-10-10 认可该项的解释/定位（取值仍待裁决）** —— 认可的是「`Chart.yaml` 的 `version` / `appVersion` 不受 `AGENT.md` §8 约束、方案 A 不违反该条」这一**解释**；A / B / C **三方案选哪个、`kubeVersion` 是否声明及取值仍待裁决**。见 §0.2 第 3 项。

**解锁**：`VERSION` / chart 口径统一后，`tests/test_version_consistency.py` 的扩展守卫与交付文档的版本说明可以落定。**阻塞**：A5 的「版本口径」「`kubeVersion`」两项出口判据直接挂在这里。

### 8.4 B1 O1 容量目标（受 `AGENT.md` §2 约束）

**现状（一句）**：O1 在 `docs/plan.md` §5.1 仍 open，「维护者目标裁决仍 open」，而 HPA 阈值、容量类告警、`docs/product/ne-datasheet.md` 的容量取值与包装批次 4.1 都在等它；`AGENT.md` §2 规定裁决前不得发布任何容量数字（**本章因此不给值、也不给单位**）。

**建议不要一次性裁决整套，而是分三级**（均为建议，维护者未裁决）：

| 阶段 | 裁决内容 | 是否需要新的测量 |
|---|---|---|
| 阶段 1 | **口径**：要不要发布、以 SLO 还是绝对值表述、用什么单位 | **不需要** —— 纯口径问题，可以立刻裁决 |
| 阶段 2 | **内部目标值** 与 **对外承诺值** 区分：前者可立刻驱动 HPA 阈值与容量类告警，后者才进 `ne-datasheet.md` 与评审材料 | 不需要新的测量，但需要决定哪些数字属于哪一类 |
| 阶段 3 | 基于已完成的 dev-host 正式批次与后续更高保真批次**填值** | 需要（依赖已有测量批次与后续批次） |

**这样做的好处**：阶段 1 与阶段 2 今天就能裁掉，不必等测量；只有阶段 3 依赖测量批次。把「口径」和「取值」拆开，可以避免口径没定就先讨论具体值的空转。

**顺带提请一并裁决**：NF-3 改 n-a 已是 `docs/handoff/2026-10-07-m8-next-step-plan.md` **N2 第 6 项**的既有建议，与 O1 同源、同属裁决类，**建议与 O1 一次裁决**，不要分两次打扰。

**解锁**：阶段 1/2 裁决后，HPA 阈值与容量类告警可以先动起来，Datasheet 的写法也可以定下来。**阻塞**：阶段 3 之前，`ne-datasheet.md` 的容量取值仍需留空或标注待裁决。

### 8.5 B2 O4 呼叫轨迹保留期 + D5 轨迹存储选型

**现状（一句）**：O4（保留期）与 D5（存储选型）双 open，共同阻塞 `docs/product/security-privacy.md` 的 PDPO 保留期限与存储方案；两者又都在等「客户合规输入」，形成互相等待。

**建议拆开裁决**（推荐了两个维度分别给推荐值）：

**D5 轨迹存储选型**

| 选项 | 做法 | 优点 | 缺点 / 成本 / 风险 |
|---|---|---|---|
| A（推荐） | **复用集群内 PostgreSQL**（ADR-0026 已有先例，运维面最小；Redis 侧仍保留为运行态 checkpoint） | 不引入新的组件；备份、权限、审计都落在既有的集群内 PG 运维面上 | PG 侧需要保留策略与对应的清理作业；写入路径的形态须另行确认（属 §8.5 之外的独立问题，本章不代为裁决） |
| B（次选） | Redis 短保留 + PG 归档 | 查询近期轨迹快；归档成本低 | 两份存储的生命周期要分别证明，PDPO 文档要写两条删除路径 |
| C（次次选） | 独立短保留存储 | 与其它数据完全隔离 | 新增组件与新的运维面；对单租户 on-prem 交付来说成本最高 |

**O4 呼叫轨迹保留期**

**推荐：先给默认值 + 部署期可配**（Helm values 暴露，交付时由客户按自身合规确认后覆盖）。这样把「客户合规输入」从**阻塞项**变成**部署参数**。

**这样做直接带来什么**：`docs/product/security-privacy.md` 可以立刻落地「**留存范围 + 删除机制 + 数据留港原则 + 默认可配**」四件事，而不必等客户给出确定性答复；客户的答复随后只调整参数取值，不再阻塞文档成型。

**解锁**：PDPO 章节可写。**阻塞**：默认值本身仍需维护者裁决（此建议未代其值）。

### 8.6 B3 O5 容灾等级 + D3 Redis HA 拓扑

**现状（一句）**：O5（N+1 节点 vs N+M 机架 / AZ）open，D3 的**客户端接线已于 2026-10-05 resolved**（见 `docs/plan.md` §5.2 D3 行与 `docs/reviews/m2-d3-sentinel-adjudication-2026-10-05.md`），**当前未决的只剩 HA 拓扑**；二者共同阻塞 `docs/operations/backup-restore.md` 的 RPO / RTO 与 HA 章节。

**请维护者先确认这一定位**：D3 的「未决」不等于「客户端没接好」—— 接线已 resolved，剩下的只有 HA 拓扑，且 HA 拓扑挂在 O5 之下。若这一定位被确认，很多历史表述里「D3 未决」的连带理解需要相应收窄。

**维护者 2026-10-10 认可该项的解释/定位（取值仍待裁决）** —— 认可的是「D3 客户端接线已于 2026-10-05 resolved、未决的只剩 HA 拓扑」这一**定位**；究竟 **N+1 + Sentinel 还是 N+M（含是否启用 Redis Cluster）仍待裁决**。见 §0.2 第 4 项。

**选项**

| 项 | 选项 | 评价 |
|---|---|---|
| O5 容灾等级 | N+1（节点） | 单方可控；不依赖客户集群的具体拓扑 |
| O5 容灾等级 | N+M（机架 / AZ） | 更严，但**机架 / AZ 拓扑取决于客户集群形态，不是单方能决定的** |
| D3 HA 拓扑 | Sentinel | 与已 resolved 的客户端接线同源，改动面最小 |
| D3 HA 拓扑 | Redis Cluster | 表达力更强，但需要产品侧重新处理拓扑与故障语义 |
| D3 HA 拓扑 | 主从 + Sentinel（等价于默认项） | 同上，作为默认项的表述方式 |

**推荐：默认 N+1 + Redis Sentinel**；把 N+M 与 Redis Cluster 作为**由客户明确要求驱动的升级项**。理由：机架 / AZ 拓扑取决于客户集群形态，把它定为默认值等于承诺一件交付方无法单方兑现的事。

**解锁**：`backup-restore.md` 的 RPO / RTO 与 HA 章节可以基于「N+1 + Sentinel」写默认值，并在部署文档中写明升级条件。**阻塞**：在此之前这两节只能留分支说明。

---

## 9. B4（Python 3.10 EOL）重新定位：技术事实与可选处置（2026-10-10 追加）

> 本节全部技术事实已在**本仓库内核实**（文件 + 行号可查）。本节不新增决策，只把 `docs/plan.md` §5.2 D1 的**理由**与**残余问题**分开：前者已失效，后者是真的。

### 9.1 事实一：没有代码强制 3.10，是显式 pin

3.10 不是被任何库或 API 逼出来的，而是仓库里**显式写死**的。共 6 处：

| # | 位置 | 内容 | 备注 |
|---|---|---|---|
| ① | 7 个成员的 `pyproject.toml`（`platform` / `apps/translation` / `apps/anti-fraud` / `services/config-service` / `services/console` / `testbed/simulators` / `testbed/load`） | `requires-python = ">=3.10,<3.11"` | **真正的锁是上界 `<3.11`**，不是下界 |
| ② | 根 `.python-version` | `3.10` | 本机工具链选择 |
| ③ | `uv.lock` 首部（第 3 行） | `requires-python = "==3.10.*"` | 重锁时会随之变化 |
| ④ | 根 `pyproject.toml`（第 116 行） | mypy `python_version = "3.10"` | 类型检查目标版本 |
| ⑤ | `deploy/docker/Dockerfile` | 第 3 行 builder `uv:python3.10-bookworm-slim`；第 23 行 runtime `python:3.10-slim` | 交付镜像的基础版本 |
| ⑥ | `.github/workflows/ci.yml`（第 30 行） | `PYTHON_VERSION: "3.10"` | CI 工作已按 §0 第 1 项后置，**当下不冲突** |

另有一条条件依赖：根 `pyproject.toml` 第 36 行 `tomli>=2.0; python_version < '3.11'` —— 升到 3.11+ 后它会因内置 `tomllib` **自动消失**，不是迁移障碍。

### 9.2 事实二：`plan.md` §5.2 D1 的理由已失效

D1 那一行写的是：**「产品锁 3.10 是因为那是 sippy 验证过的版本。」**

但全仓库 grep `sippy` 只命中**三条**，且全是注释：

- 根 `pyproject.toml` 第 139、141 行：`sippy ships without type information` 的 mypy ignore 配置注释与 `module = ["sippy.*"]`；
- `platform/pyproject.toml` 第 22 行：`The POC behaviour baseline, which currently runs on sippy` 的注释。

**没有任何 `pyproject.toml` 依赖 sippy，`uv.lock` 里也没有。** 生产栈是 C++ reSIProcate 扩展（`platform/native/resip_*`），与 sippy 无关。

**因此 D1 的性质变了**：它不再是「有一个叫 sippy 的依赖拖住了升级」这种技术理由，而是 「**历史遗留 + on-prem 交付的基础镜像合规问题**」—— 3.10 已到 EOL，**不再有上游安全更新**，客户安全评审会问这一条。这是**汇报/合规**问题，不是技术障碍。

### 9.3 事实三：真正需要重新验证的耦合

| 耦合点 | 是否版本无关 | 换 minor 后必须做什么 |
|---|---|---|
| native 扩展（三个 CMakeLists 均为 `find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)`：`platform/native/resip_runtime/CMakeLists.txt:33`、`platform/native/resip_two_leg/CMakeLists.txt:32`、`platform/native/resip_recovery/CMakeLists.txt:32`） | 本身**版本无关**（只要求有 Interpreter + `Development.Module`） | **换 minor 必须重编并复验 E1 / TLS smokes** —— 正好与 W0 的 A2 / A3 共用一次构建，成本可被摊薄 |
| mypy strict 的类型推断 | 否 | 跨版本推断结果可能不同，**需重跑 `make type`** |

### 9.4 两个处置选项（建议，维护者未裁决）

**选项①（推荐）：低成本验证 spike** —— 把 §9.1 的 6 处 pin 改到 3.12 → `uv sync` 重锁 → `make gate` → `make m2-platform-resip-build` + E1 / TLS smokes 复验 → 镜像构建。

- **绿**：新增 ADR **supersede** D1 的理由，并按 `AGENT.md` §15 把 `docs/plan.md` §5.2 的 D1 行移动到已解决一侧；
- **红**：回滚 pin，在 ADR 里登记为 **accepted risk**，并写明红在哪一处。
- **成本为什么能被摊薄**：① CI 已后置，改 CI 那一行当下不冲突；② native 扩展反正要随 A2 重编，可共用一次构建。

**选项②：不迁移** —— 现在就在 ADR 登记 accepted risk，并在 `docs/product/ne-datasheet.md` 与交付材料里接受「EOL 运行时」在客户评审中被质疑。

### 9.5 一条不可越过的约束

**无论如何都不能悄悄换版本。** `AGENT.md` §15 规定未决项必须走 ADR，并同步移动 `docs/plan.md` 里的那一行。任何人在没有 ADR 的情况下改 pin、改重锁或改基础镜像，都会让版本口径失去追溯；这条对着两个选项同时成立。

---

## 10. 当前开工状态（2026-10-10）

> 本节为**追加**（2026-10-10），只记录本次回写的状态与待批准的启动项，不新增任何决策、不签收任何 REQ / 里程碑。

### 10.1 本次改动只有文档回写，未执行任何实质性工作

本次**只做文档回写**。以下动作**一个都没有执行**：

| 未执行的动作 | 说明 |
|---|---|
| 任何 `make` target | 未跑 `make gate` / `make m2-platform-resip-build` / `make gate-native` / `make chart-check` / `make alert-check` / `make type` 等 |
| 任何 pytest | 未跑 `pytest`（含 A3 Phase A 的两条契约测试复验） |
| 任何 `docker` 命令 | 未执行 `promtool` 的容器化校验（**已获授权，未执行**） |
| `uv sync` / 重锁 | 未执行，未改任何 pin |
| CI / git 写操作 | 未运行 GitHub Actions；无 `git add` / `git commit` / `git tag` / `git push` / 建分支 / 改 remote |

因此本文的状态结论与 §2 的基线快照**未因本次回写而变化**：真栈仍是 skip、告警规则语法仍未校验、chart 形状门禁仍未在本机复验 —— 三项均**不得**读作绿。

### 10.2 工作树当前改动面（三个文件的角色说明）

| 文件 | 角色 | 说明 |
|---|---|---|
| `docs/handoff/2026-10-10-unfinished-assessment-and-next-plan.md`（本文） | **新增文档**（未跟踪） | 未完成项盘点 + 分波计划 + §8 建议与选项 + §9 B4 重新定位；本次回写新增 §0.2、§5 W0 状态行、`promtool` 授权标注、§8.2 / §8.3 / §8.6 的认可行与本节 |
| `docs/acceptance/report.md` | **已修改** | 仅 §3-b 的「追加更正（2026-10-10）」段落 —— 纠正 §0.3（F9 / A-4）与现实不符的措辞；只追加，未改写第 30 / 33 行原文 |
| `docs/plan.md` | **已修改** | §0 状态入口、§0 产品决策记录表（本次追加 §0.2 对应的四行认可 + 表格外一行注记）、产品化包装交付状态小节 |

三个文件的共同性质：**全部是文档**。本次未改任何产品代码、未改 `VERSION` / `Chart.yaml` / `.github/workflows/ci.yml`。

### 10.3 下一步需维护者批准的启动项清单

以下三项**均需维护者明确批准后才启动**；在批准前一律不执行（与 §0.2 的「开工状态」和 §5 W0 的「等待开工批准」一致）：

1. **`promtool` 容器化校验** —— 已获授权、未执行：`docker run --rm -v $PWD/deploy/alerts:/a prom/prometheus promtool check rules /a/as-alerts.yaml`。批准后执行，结果以**追加**方式记录到 §1.2 对应行（不得改写原行）。
2. **W0 的两项**（A2 与 A3）：
   - **A2 真栈构建常态化**：`make m2-platform-resip-build` → `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate`（等价 `make gate-native`）；
   - **A3 Phase A 复验**：`uv run pytest platform/tests/test_e1_contract_resip_runtime.py platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q`，加上 `uv run pytest platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200 -q`（须在 A2 之后；该第三个目标是 `integration` 标记，**不在** `make gate` 的 `-m "unit or contract"` 收集范围内，须显式指定才能跑）。
3. **是否把 B4 的 Python 3.12 spike 并入同一次 native 构建** —— 即 §9.4 选项①（改 6 处 pin 到 3.12 → `uv sync` 重锁 → `make gate` → `make m2-platform-resip-build` + E1 / TLS smokes 复验）是否搭 W0 的 A2 那一次构建的车。**B4 本身未被裁决，当前仍是建议**；此处只请求「是否并入同一次构建」这一执行面的批准，不代表 B4 已被裁决。

批准之外的六项取值（A4 / A5 / A6 / B1 / B2 / B3）仍按 §0.2 的「口径边界」处理：**全部待维护者裁决**。

上述三项截至 2026-10-10 仍未获批启动；评审通过不等于执行授权。
