# M8 test-plan 签收矩阵（Phase C）

> **来源**：`docs/acceptance/test-plan.md` §1–§5（v1 范围）。
> **回溯说明**：本矩阵映射到 M8 任务草稿附录各节（该文件为 REQ 检查表附录，本次不修改该文件；
> 注：本仓库内未见 `M8任务草稿.md` 文件，回溯以 test-plan 章节号 `§1.1–§5` 为准）。
> **不宣称全绿**：本矩阵不是「全 REQ 绿」声明；所有行 `signed_by` 均为 `维护者待签`，
> 仅当矩阵中无未解释的 v1 `open` 项且维护者在 M8 退出评审（`docs/reviews/m8-exit-review-*.md`）中确认后，
> 方可宣称 M8 全绿。`blocked` 须指向 `docs/plan.md` §5（O/D 编号）或 v1.1；`n-a` 须附理由，永不记为 pass。
> 维护者缺席期间本矩阵仅记录可验证证据与自决策状态，不替代维护者签字。

依据计划：`docs/handoff/2026-10-06-m8-release-candidate-plan.md` §4 Phase C + §3.1 范围。

## 证据基线（2026-10-06 本地实测，非编造）

- `make gate` → **978 passed, 2 skipped**（exit 0）。2 个 skip 均为
  `test_derived_baseline.py`：S1 基线无 Route 头 / 无 Record-Route，需 M2 probe 补采。
- `uv run pytest platform/tests/test_resip_runtime_log_contract.py -q` → **13 passed**。
- `uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q` → **4 passed**。
- `uv run pytest platform/tests/test_m7_forward_two_leg_integration.py platform/tests/test_req_f4_sdp_identity_integration.py -m integration -q` → **4 passed**。
- `uv run pytest platform/tests/test_d10_product_recovery_integration.py -q` → **1 passed**。
- `uv run pytest testbed/simulators/tests/test_derived_baseline.py -m contract -q` → **10 passed, 2 skipped**（同上）。
- `uv run pytest tests/test_version_consistency.py -q` → **9 passed**；`tests/test_workspace_layout.py` → **32 passed**。
- `python3 scripts/ci/check_adr_annotations.py` → **checked 69 files, clean**。
- `make chart-check` → **chart-check: OK**（工程形状证据，不作为 REQ pass 依据）。
- NF-6 grep：`rg -il 'rtp|G.711|G.729|dtmf|transcod' apps/ platform/src/ services/` 唯一命中
  `services/console/web/console.js`，经查为 DOM id `distributionStartPanel` 中 `rtp` 子串误命中（Start**P**anel），
  无真实 RTP/媒体实现；`platform/src` 内 `media/seam` 仅为注释措辞（call_checkpoint 不存媒体、ingress 换 seam 注释）。
- NF-7 grep：`rg -il 'cdr|批价|计费|billing' apps/ platform/src/ services/` → **无命中**。
- NF-8 grep：`rg -il 'lawful_intercept|\bIRI\b|intercept' apps/ platform/src/ services/` → **无命中**；
  范围排除另见 `docs/architecture/hld.md`（单租户 on-prem 边界：排除媒体/CDR/LI/Diameter Sh）。
- NF-5 grep：`rg -n 'is_intranet|is_extranet|network_mode' apps/` → **无命中（exit 1）**。
- NF-10 grep：无 `import git / from git / github.com / gitlab / git clone-pull` 类配置加载逻辑；
  唯一含 `git` 字样的是 `services/config-service/src/as_config_service/change_order.py:4` 注释行
  （"instead of GitOps" 说明性文字，非代码逻辑）。
- NF-11 grep：`rg -n 'VERSION=' platform/ apps/ services/` → **无命中**（各组件不拥有 VERSION）。
- NF-14：`deploy/alerts/as-alerts.yaml` 存在（含 5xx>1%、active_calls 突增、证书 30 天到期等规则，`make chart-check` 覆盖模板形状）。
- NF-15：`docs/requirements/req-nf-15-testbed-performance.md` 存在；ADR-0014 `回应 REQ` 指向 REQ-NF-15；
  dev-host 实测见 `docs/acceptance/m6-o1-measurement-report-2026-10-05.md`（非 SLA）。

## §1 功能签收（REQ-F-*）

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| REQ-F-1 | §1.1 基本呼叫 14 条消息 | M7 | C | `test_e1_contract_resip_runtime_full.py -m contract` 4 passed；`test_m7_forward_two_leg_integration.py`（integration 4 passed 之一）；`test_derived_baseline.py -m contract` 10 passed。工程切片通过，REQ 正式签收待维护者 M8 退出评审 | open | 维护者待签 |
| REQ-F-2 | §1.1 两腿 Call-ID 独立 | M7 | C | E1 contract 套件在 `make gate`（978 passed）内通过；C_in≠C_out / 腿内一致断言的 REQ 级签收待 M8 评审 | open | 维护者待签 |
| REQ-F-3 | §1.1 Request-URI 翻译 | M7 | C | `test_derived_baseline.py` S1 翻译场景（+8613800138000→013800138000）在 10 passed 内；REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-F-4 | §1.1 SDP 透传字节一致 | M7 | C | `test_req_f4_sdp_identity_integration.py`（integration 4 passed 之一）+ D11 fixtures；`plan.md` §5.2 D11 明确"REQ-F-4 正式通过仍须 M8 review + 更广 corpus，不得单独宣称 REQ 绿" | open | 维护者待签 |
| REQ-F-5 | §1.1 Route/Record-Route | M7 | C | `test_derived_baseline.py` 2 skipped：S1 基线无 Route 头、无 Record-Route，"需 M2 probe 补采"。产品真实路径行为验收另指 O3；补采前不签 pass | open | 维护者待签 |
| REQ-F-6 | §1.2 无匹配 404 | M7 | C | 内核 5.1 decide 矩阵（用例 5 NO_MATCH→404）在 `make gate` 978 passed 内；REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-F-7 | §1.2 阻止 603 + 优先级 | M7 | C | 内核 5.1 decide 矩阵（用例 3/7 block 优先）在 `make gate` 978 passed 内；REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-F-8 | §1.3 CANCEL 三分支 | M7 | C | `test_call_controller.py` 等 M7 呼叫控制用例在 `make gate` 978 passed 内；三分支 REQ 级签收待 M8 评审（分支覆盖结论以评审为准，不在此自称分支全绿） | open | 维护者待签 |
| REQ-F-9 | §1.3 in-dialog 路由 | M7 | C | M7.3 context restoration 工程切片（`restore_from_checkpoint` / `route_in_dialog_bye`，见 plan §5.2 D10 TODO）；re-INVITE/UPDATE/BYE 对拍场景 REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-F-10 | §1.3 486/480/408 透传 | M7 | C | D9 产品 adapter 486 映射工程已解决（plan §5.2 D9）；透传非改码 + 非 2xx 清理的 REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-F-11 | §1.3 最终响应竞态两分支 | M7 | C | D9 forking/final-response race 覆盖归属 M8 验收（plan §5.2 D9）；REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-F-12 | §1.4 控制台规则 CRUD（M4：被叫+前缀） | M4/M4b | C | M4 工程关门；dev HTTPS 采证见 `docs/acceptance/m4b-8-runbook.md`；plan §5.4 明确 §1.4 正式全绿归 M8 或维护者单独签收 | open | 维护者待签 |
| REQ-F-13 | §1.4 Call-ID 轨迹查询 | M4/M4b | C | M4b-7.4：无 trace store/API，M4b-8 标 BLOCKED（test-plan 头注 + `m4b-8-runbook.md`）。指到 plan §5.4；live 环境证据归 Phase D | blocked | 维护者待签 |
| REQ-F-14 | §1.4 审批流 | M4/M4b | C | M4 工程关门（创建→待审批→批准/拒绝+理由，self-approve 禁止）；正式全绿归 M8（plan §5.4 §1.4 行），待维护者签收 | open | 维护者待签 |
| REQ-F-15 | §1.4 灰度分发/回滚（控制面） | M4/M4b | C | M4 已交付 inventory + notify + testbed probe + 浏览器 distribution start；**完整 AS 栈补测**后置（plan §5.4），见下方 5.4-F-15 行。整体不签 pass | blocked | 维护者待签 |
| REQ-F-16 | §1.5 翻译决策链 | M7 | C | decide 翻译用例在 gate 内通过；轨迹联动（翻译前后号码/规则 ID/版本）依赖 F-13 trace，REQ 签收待 M8 评审 | open | 维护者待签 |

## §2 非功能签收（REQ-NF-*）

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| REQ-NF-1 | §2 kill 重启状态不丢 | M7 | C/D | 工程 harness 见 `test_d10_product_recovery_integration.py`（1 passed）等。客户 K8s live 为 **restriction**（2026-10-07，Close 前不测客户集群）：[`m8-environment-evidence.md`](m8-environment-evidence.md) D-2。不能签 pass | blocked | 维护者待签 |
| REQ-NF-2 | §2 双 Deployment 隔离 | 横切 | C | 架构 ADR-0002（每用例独立进程/Deployment）；`make chart-check` OK（模板形状）。live kill translation 不影响 anti-fraud 验证待 K8s 环境（Phase D），不签 pass | open | 维护者待签 |
| REQ-NF-3 | §2 HPA 扩缩 + 容量数字 | M5 | B/C | **Blocked**：test-plan 带固定容量数字（500 active_calls 阈值、1000 并发、3→≥5 副本）与 AGENT §2"M6 前不发布容量数字"冲突。指到 plan §5.1 **O1**：维护者目标裁决仍 open，M6 O1 报告为非 SLA 实测。待维护者改写验收口径或标 N/A | blocked | 维护者待签 |
| REQ-NF-4 | §2 滚动升级零丢失 | M5 | C/D | 内核 5.5 draining 单测在 gate 978 passed 内；M7 进程壳 harness 为工程切片。**带真实 SIP 话务**的滚动验证需 live 环境，归 Phase D（待填）；未验证前不签 pass | blocked | 维护者待签 |
| REQ-NF-5 | §2 仿真器中立 | 横切 | C | `rg 'is_intranet\|is_extranet\|network_mode' apps/` 无命中（代码无内外网分支）；换仿真器（Kamailio）行为一致验证待 sim 环境，REQ 签收待 M8 评审 | open | 维护者待签 |
| REQ-NF-6 | §2 无媒体面实现 | 横切 | C | 生产代码 grep 见头注：无 RTP/G.711/G.729/DTMF/转码实现（唯一命中为 console.js DOM id 子串误报）；seam 仅注释。非目标项以"缺席"为通过依据 | pass | 维护者待签 |
| REQ-NF-7 | §2 轨迹保留 + 无计费 | 横切 | C | 无 CDR/批价/计费实现（grep 无命中）一半成立；但轨迹查询依赖 F-13（plan §5.4 BLOCKED），保留期天数待 O4 冻结、清理任务验证待定。指到 plan §5.4 + §5.1 **O4**，归 Phase C（口径）/D（live） | blocked | 维护者待签 |
| REQ-NF-8 | §2 无 LI 实现 | 横切 | C | 生产代码 grep 无 `lawful_intercept/IRI/intercept` 命中；hld 明确 LI 由网内出、不在我方交付边界。非目标项以"缺席"为通过依据 | pass | 维护者待签 |
| REQ-NF-9 | §2 命名空间隔离 | M5 | B/C | `make chart-check` OK（独立 namespace 模板形状，工程切片，非 REQ pass）；live 故障隔离（Redis 挂/AS 崩不影响另一 namespace）待集群环境。D12/O5 条件见下方专项行 | open | 维护者待签 |
| REQ-NF-10 | §2 控制面：草稿→审批→分发→回滚→审计 | M4/M4b | C | config-service 套件（change_order/distributor/audit store）在 `make gate` 978 passed 内；代码无 git/github/gitlab 配置加载逻辑（见头注）；`make chart-check` 覆盖模板形状。live 灰度分发/回滚随 F-15 真 AS（Phase D），不签 pass | open | 维护者待签 |
| REQ-NF-11 | §2 VERSION 唯一 | 横切 | C | `tests/test_version_consistency.py` 9 passed；`rg 'VERSION=' platform/ apps/ services/` 无命中。机制成立；发布一致性终签随 Phase E（VERSION/CHANGELOG） | pass | 维护者待签 |
| REQ-NF-12 | §2 uv workspace | 横切 | C | `tests/test_workspace_layout.py` 32 passed；`pyproject.toml` `[tool.uv.workspace]` 存在。机制成立 | pass | 维护者待签 |
| REQ-NF-13 | §2 可观测：指标/追踪/JSON 日志 | M5 | B/C | `test_resip_runtime_log_contract.py` 13 passed（timestamp/level/trace_id/call_id/direction/method 字段契约切片）；decide/遥测内核（5.4）在 gate 内。Prometheus/Grafana live 采集与 span 链验证待环境（Phase D），不签 pass | open | 维护者待签 |
| REQ-NF-14 | §2 告警规则 | M5 | B/C | `deploy/alerts/as-alerts.yaml` 存在（5xx>1%、active_calls 突增、证书 30 天等）；`make chart-check` OK 为形状证据。Alertmanager 真实触发验证待环境（通知通道 M2 冻结事项延续），不签 pass | open | 维护者待签 |
| REQ-NF-15 | §2 testbed 性能 harness | M6 | C | PRD + `docs/requirements/req-nf-15-testbed-performance.md` 存在，ADR-0014 回应 REQ 指向 REQ-NF-15（D8 已关闭）；dev-host 批次见 m6-o1 报告（非 SLA）。生产多副本饱和点/HPA 阈值/`performance` 阻塞 CI 在 M8 前保持 open；M6 O1 维护者目标裁决仍 open（plan §5.1 O1） | open | 维护者待签 |

## §3 安全签收（REQ-S-*）

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| REQ-S-1 | §3 白名单 | 横切 | C | 白名单逻辑存在（`platform/src/as_platform/sip/ingress.py` 等含 allowlist/peer 引用的文件，gate 978 passed 覆盖）；白名单变更走审批（F-14 联动）。REQ 签收待 M8 评审（M2 REQ-S-* 工程覆盖 + 维护者 M2 退出） | open | 维护者待签 |
| REQ-S-2 | §3 AS↔S-SBC TLS + 运营商 PKI | M2 | C/D | 本地 TLS 工程测试在 gate 内。运营商 PKI + 外网 S-SBC 为 **restriction**（2026-10-07，Close 前不联调）：[`m8-environment-evidence.md`](m8-environment-evidence.md) D-1。不能签 pass | blocked | 维护者待签 |
| REQ-S-3 | §3 证书轮换无损 | M2 | C/D | 真实对端上的运营商证书轮换窗口为 **restriction**（2026-10-07，同 D-1）。测试证书上的轮换不代替本条。不能签 pass | blocked | 维护者待签 |
| REQ-S-4 | §3 RBAC + 审计不可篡改 | M4/M4b | C | config-service 审计/鉴权套件（`test_audit_store.py`、`test_auth.py` 等）在 `make gate` 978 passed 内；M4b-6b 为工程切片。plan §5.4 明确 REQ-S-4 正式全绿归 M8 或维护者单独签收，待签 | open | 维护者待签 |

## §4 治理签收（REQ-G-*）

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| REQ-G-1 | §4 feature 门控两态 | 横切 | C | 内核 5.3 两态单测在 gate 内；`check_adr_annotations.py` 69 files clean（无未标注架构性代码）。记 pass-机制：逐变更的移除条件审查仍需维护者按 PR 执行 | pass | 维护者待签 |
| REQ-G-2 | §4 PR checklist + REQ 追溯 | 横切 | C | review-record 惯例存在（`docs/reviews/` 内各记录均挂 REQ/ADR 编号，如 d8/m5 系列）；机制成立。逐变更追溯仍需维护者在每次评审中确认，记 pass-机制 | pass | 维护者待签 |
| REQ-G-3 | §4 ADR 标注扫描阻断 | 横切 | A/C | `check_adr_annotations.py` clean（69 files）；`make gate` 四步不含 AST 扫描符合 test-plan 口径（扫描属 gate-strict/CI 前置）。CI fail-blocking 语义终态归 Phase A（A-5/A-6），机制当前成立记 pass-机制 | pass | 维护者待签 |
| REQ-G-4 | §4 gate 绿 + CI 阻断 + pre-commit | 横切 | C | `make gate` exit 0（978 passed, 2 skipped，见头注）。CI 失败阻断后续步骤与 pre-commit 语义终态归 Phase A（A-4/A-6）确认；本地门禁本身绿，记 pass（CI 侧待 A 闭合） | pass | 维护者待签 |

## §5 内核行（test-plan §5，引用 gate，不重证）

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| KERNEL-§5 | §5.1 decide 矩阵 / §5.2 StateStore 契约 / §5.3 门控两态 / §5.4 遥测不阻塞 / §5.5 draining（unit/contract 层） | M2/M3 | C | `make gate` 978 passed, 2 skipped（2026-10-06）。M3 契约重放已在 gate；2 skipped 为 Route/Record-Route probe 缺口（见 F-5），不掩盖 | pass | 维护者待签 |

## §5.4 补测行（plan §5.4，不阻塞 M4 关门，阻塞 REQ 全绿宣称）

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| 5.4-F-13 | §1.4 REQ-F-13 live trace（M4b-7.4） | M4/M4b→集成栈 | C/D | 与 REQ-F-13 同源：无 trace store/API（test-plan 头注 BLOCKED）。live 轨迹查询证据归 Phase D（环境+已知 Call-ID，待填）；此前不得记通过 | blocked | 维护者待签 |
| 5.4-F-15真AS | §1.4 REQ-F-15 完整 AS 栈（非 testbed notify/health） | M7 集成后 | C/D | M4 仅交付 inventory + notify + testbed probe + 浏览器 distribution start；真 AS 全栈分批分发/健康/自动+手动回滚待集成后补测（Phase D 环境，待填）。指到 plan §5.4 | blocked | 维护者待签 |

## 条件 / 环境 / 明确排除行

| req_id | test_plan_ref | milestone | phase | evidence | status | signed_by |
|---|---|---|---|---|---|---|
| D12/O5-HA | §2 NF-1/NF-9/NF-10（生产 Redis/PG HA） | M5 | B/C | ADR-0026 accepted；Helm `stateStores` 骨架已落库。**生产** Redis/PG HA 为 **restriction**（2026-10-07）：Close 前无客户生产拓扑。kind bundled state 不是本条。不能签 pass | open | 维护者待签 |
| ADR-0008-演练 | 架构 ADR-0008 跨站点 | — | C/D/E | 跨站点切换演练为 **restriction**（2026-10-07）：Close 前无客户/生产双站点。不能签 pass。见 [`m8-environment-evidence.md`](m8-environment-evidence.md) | blocked | 维护者待签 |
| D6-testbed验收 | test-plan 外（D6） | — | D | plan §5.2 D6：testbed 是否须 v1 支持客户验收，架构推迟到 v1.1，待维护者拍板（v1 vs v1.1）。归 Phase D（D-3） | blocked | 维护者待签 |
| NA-主叫/正则 | §1.4 F-12 四维 UI（主叫/正则） | — | — | plan §5.4：属 **v1.1**，M4 live 仅被叫+前缀。M8 不验收，永不记 pass | n-a | 维护者待签 |
| NA-PM/AM/UM | §2 NF-13/NF-14 外 | — | — | plan §5.3：完整产品需求未补齐，M8 仅含 REQ-NF-13/14 工程切片。M8 不验收 | n-a | 维护者待签 |
| NA-D1 | 全局（Python 3.10 EOL） | — | — | plan §5.2 D1：风险登记，不默认阻断 RC。M8 矩阵不验收运行时版本迁移 | n-a | 维护者待签 |
| NA-D10ext | §2 NF-1 外（mid-transaction 崩溃/owner-CAS 极端） | — | — | plan §5.2 D10："不把 D10 扩展到崩溃时的 mid-transaction recovery；Redis 故障转移极端场景不扩展"。M8 不验收 | n-a | 维护者待签 |

## 状态统计

- pass：9（NF-6、NF-8、NF-11、NF-12、G-1、G-2、G-3、G-4、KERNEL-§5；其中 G-1/G-2/G-3 为 pass-机制，逐变更评审仍需维护者）
- fail：0
- blocked：12（F-13、5.4-F-13、F-15、5.4-F-15真AS、NF-1、NF-3、NF-4、NF-7、S-2、S-3、ADR-0008-演练、D6-testbed验收）。其中 NF-1、S-2、S-3、ADR-0008-演练于 2026-10-07 标为 Close 前 **restriction**（真实客户网络不做），状态词仍是 blocked，不能签 pass。D12/O5-HA 仍计在 open，同样是 restriction。
- n-a：4（主叫/正则 v1.1、PM/AM/UM、D1、D10 极端扩展；均附理由，永不记 pass）
- open：24（F-1/2/3/4/5/6/7/8/9/10/11/12/14/16、NF-2/5/9/10/13/14/15、S-1/S-4、D12/O5-HA；每项均有工程证据 + 待维护者 M8 退出评审签收的明确理由，无未解释 open）

**未宣称绿的项**：全部 24 个 open 与 12 个 blocked（含所有 live 环境尾项 S-2/S-3、NF-1 live、F-13 live、F-15 真 AS、NF-3 容量口径、NF-4 真实话务滚动、NF-7 轨迹/O4、ADR-0008 演练、D6）均未宣称为绿；
4 个 n-a 明确排除。`不宣称全绿`，待维护者 M8 退出评审确认。
