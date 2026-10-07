# M8 发布候选退出评审记录（2026-10-06）

- **评审对象（object）**：M8 发布候选（RC）退出，范围 = RC 计划 §3 退出条件 1–5（阶段 A–B 闭合、阶段 C v1 签收矩阵、阶段 D 环境 true blocker 结论、阶段 E 报告/版本/签字、本总审 + 里程碑签字表）。
- **评审日期（date）**：2026-10-06
- **评审人（reviewer）**：AI agent（维护者缺席期间用户指令 self-decision；**维护者会签 PENDING**，本记录不替代维护者签字，不构成关门结论）。
- **评审结论（conclusion）**：**RC就绪，defer项未清，不宣称全绿；维护者签字后方可关门**（不是"通过"）。

依据：[`2026-10-06-m8-release-candidate-plan.md`](../handoff/2026-10-06-m8-release-candidate-plan.md) §3 / §3.1 / §5、[`plan.md`](../plan.md) §4（M8 定义）/ §5（O/D 未决项）、AGENT.md §3.3（review record 格式）/ §10.4（tag 仅维护者）。

---

## 1. 退出条件逐项核对（RC 计划 §3 条件 1–5）

| # | 退出条件 | 本 RC 状态 | 结论 |
|---|---|---|---|
| 1 | 阶段 A–B 闭合：P1 尾项 + M5.1 / 全链复评达到维护者认可的 REQ 证据门槛 | A：F9 workflow-ready-locally（push 待 PAT）、F8 契约落地、F6 documented limitation、gate-strict + performance 阻塞 + runbook；B：MINIMAL M5.1、B-2 降级、B-3 L1，复评 REQ 级不通过 + 10 defer。**维护者认可待补** | 未闭合（待维护者） |
| 2 | 阶段 C：test-plan v1 范围内验收项有可追溯证据 | 矩阵 [`m8-test-plan-matrix.md`](../acceptance/m8-test-plan-matrix.md)：pass 9 / fail 0 / blocked 12 / n-a 4 / open 24；全部 `signed_by` 为维护者待签 | 未闭合（待签收） |
| 3 | 阶段 D：环境类 true blocker 有记录结论 | D-1/D-2 明确 defer，D-3 裁决 pending（建议 v1.1）；记录见 [`m8-environment-evidence.md`](../acceptance/m8-environment-evidence.md) | 记录齐备，终态待维护者 |
| 4 | 阶段 E：`report.md` 升级为 M8 发布候选报告；VERSION + CHANGELOG 与交付一致；`plan.md` §0 / §4 M8 行标记 | report.md §0 已升级（历史保史为附录）；VERSION 维持 `0.2.0`（未 bump，CHANGELOG 首标题一致）；plan.md §0 / §4 M8 行标 **RC就绪、待维护者退出签字**（未标已完成） | 产物就绪，签字待补 |
| 5 | Review records：M8 总审 + 各里程碑退出签字表 | 本文件即 M8 总审；签字表见 §4（M1/M2/M6/M7/M8，全为维护者待签） | 记录已建，签字待补 |

**总评**：5 项中无一项达到"维护者已确认"；RC 产物齐备可供评审，但**不得宣称为全绿或已关门**。

---

## 2. Issues 列表（签字前须逐项终态）

| # | Issue | 现状 | 终态要求 |
|---|---|---|---|
| 1 | **F9 push pending** | `.github/workflows/ci.yml` 本地就绪（blocking native jobs + chart-check + gate-strict），origin 未推送 | 维护者以 `workflow` scope PAT 推送并确认 origin CI 绿 |
| 2 | **矩阵 24 open** | F-1/2/3/4/5/6/7/8/9/10/11/12/14/16、NF-2/5/9/10/13/14/15、S-1/S-4、D12/O5-HA；均有工程证据，待 M8 退出评审签收 | 维护者逐项签收或书面接受 |
| 3 | **矩阵 12 blocked** | F-13、5.4-F-13、F-15、5.4-F-15真AS、NF-1、NF-3、NF-4、NF-7、S-2、S-3、ADR-0008演练、D6；每项已指到 plan §5 / O1 / v1.1 / Phase D | 转终态（证据 / 有条件通过 / defer 授权） |
| 4 | **D-1 运营商 PKI / 外网 S-SBC** | 明确 defer（本环境无 lab 与对端） | 维护者排期采证或书面接受风险 |
| 5 | **D-2 客户 K8s NF-1 live** | 明确 defer（本环境无客户集群） | 同上 |
| 6 | **D-3（D6 testbed v1 验收）** | 维护者裁决 pending；本 RC 建议 v1.1 | 维护者书面裁决 v1 / v1.1 |
| 7 | **M5D 10 项 defer** | C-1、C-2、C-3、C-6、C-7、C-9、H-8、H-11、A-2、T-1（复评 §6；拟新增 M5D-1…M5D-6 由维护者落定） | 关闭或移出 v1（维护者书面） |
| 8 | **O1 容量目标裁决** | dev-host 实测为非 SLA；维护者目标裁决仍 open（plan §5.1 O1） | 维护者目标裁决 |
| 9 | **NF-3 验收口径** | test-plan 固定容量数字与 AGENT §2 冲突 | 维护者裁决改写口径或标 N/A |
| 10 | **D1 风险** | Python 3.10 EOL（2026-10），风险登记，不默认阻断 RC | 维护者确认接受为风险（或立项迁移） |

v1 明确排除重申（不计入全绿）：主叫/正则（v1.1）、PM/AM/UM 完整产品、D1、D10 极端扩展（mid-transaction / owner-CAS 极端）。

---

## 3. 里程碑签字表（E-5）

列定义：对象 / 结论 / 签字 / 日期 / 备注。**以下签字栏全部为维护者待签**；历史引用仅说明既有记录，不构成签字。

| 对象 | 结论 | 签字 | 日期 | 备注 |
|---|---|---|---|---|
| M1 甄别与行为基线 | 门禁达成（历史结论） | 维护者待签 | — | 历史记录 [`m1-exit-review.md`](m1-exit-review.md) 存在；文首 M1 §6 签字仍为历史项 |
| M2 内核 / transport-runtime | 工程完成（2026-10-05），REQ-S-* 验收未签 | 维护者待签 | — | 工程裁决见 `m2-engineering-closure-adjudication-2026-10-05.md`；REQ-S-2/S-3 尾项 D-1 defer |
| M6 容量研究 | 工程完成（2026-10-05），O1 目标未发布 | 维护者待签 | — | 工程裁决见 `m6-engineering-complete-adjudication-2026-10-05.md`；O1 裁决 open |
| M7 生产 SIP 集成 | 工程完成（2026-10-05），REQ-NF-1/E1 全量未签收 | 维护者待签 | — | 工程裁决见 `m7-final-engineering-adjudication-2026-10-05.md`；D10/REQ-NF-1 待 D-2 |
| M8 发布候选 | RC就绪，defer项未清，不宣称全绿（本记录结论） | 维护者待签 | — | 维护者签字 + tag 后方可关门（AGENT §10.4，仅维护者） |

另：M5 为**工程关门（2026-10-04，维护者 chat 授权代签；含义已降级为非 REQ 验收）**，REQ 级不通过（见 [`m5-req-acceptance-review-2026-10-06.md`](m5-req-acceptance-review-2026-10-06.md)）；M3/M4 工程结论见 report 附录历史，REQ 全绿归 M8 或维护者单独签收（plan §5.4）。

---

## 4. E-6 打包校验记录（本总审执行，2026-10-06）

| 检查 | 结果 |
|---|---|
| `uv run pytest tests/test_version_consistency.py -q` | **9 passed**；VERSION `0.2.0`，CHANGELOG 首标题 `== 0.2.0`，未新增版本节 |
| 密钥复检（新 M8 文档） | `BEGIN PRIVATE KEY` 零命中；`--password` / `passwd` 零命中 |
| `helm template` | 已覆盖，引用 `chart-check: OK`（形状证据，不重跑重型构建） |
| README/runbook vs `AS_SIP_*`/`AS_TLS_*` | 实现：`platform/src/as_platform/runtime/transport_env.py`；README 无 env 名（无错名）；runbook `AS_REQUIRE_NATIVE_EXTENSIONS=1` 与实现一致；记文档缺口（非阻塞），无 typo 可改 |
| 镜像 push/tag | 明确留给维护者（AGENT §10.4），未执行 |

---

## 确认（confirmation）

| 项 | 记录 |
|---|---|
| 评审结论 | RC就绪，defer项未清，不宣称全绿；维护者签字后方可关门（不是"通过"） |
| 自决策 | M8 Phase E 由 AI agent 在维护者缺席期间按 RC 计划 §4 Phase E（E-1…E-6）执行；用户指令 self-decision；所有签字均为维护者待签 |
| 维护者确认 | **待签字**（本栏须由维护者填写；本记录不构成关门结论） |
| 所需维护者动作 | (1) 以 `workflow` scope PAT 推送 CI workflow 并确认 origin 绿；(2) 排期 D-1/D-2 环境采证或书面接受风险；(3) 裁决 D-3（D6）、O1 目标、NF-3 口径、M5D-1…M5D-6 行落定；(4) 完成 M1/M2/M6/M7/M8 退出签字；(5) 仅由维护者执行 tag（AGENT §10.4） |
| 输入评审 | [`2026-10-06-m8-release-candidate-plan.md`](../handoff/2026-10-06-m8-release-candidate-plan.md)、[`m8-test-plan-matrix.md`](../acceptance/m8-test-plan-matrix.md)、[`m8-environment-evidence.md`](../acceptance/m8-environment-evidence.md)、[`m5-req-acceptance-review-2026-10-06.md`](m5-req-acceptance-review-2026-10-06.md)、[`m8-phase-a-f6-f8-note-2026-10-06.md`](m8-phase-a-f6-f8-note-2026-10-06.md) |
| 未采信证据 | `artifacts/m8/` 占位目录（待采证，无证据效力）；`make gate` 本地绿仅为工程门禁，不替代 REQ 签收 |
