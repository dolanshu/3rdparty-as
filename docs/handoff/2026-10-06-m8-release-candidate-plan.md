# M8 发布候选 — 执行计划（2026-10-06）

> **状态**：**进行中**（维护者于 2026-10-06 授权进入 M8）  
> **依据**：[`plan.md`](../plan.md) §4（M8 定义）、[`2026-10-05-milestones-engineering-complete.md`](2026-10-05-milestones-engineering-complete.md)、[`2026-10-05-callload-review-response-plan.md`](2026-10-05-callload-review-response-plan.md)、[`test-plan.md`](../acceptance/test-plan.md)、AGENT.md §3.1 / §14  
> **单一 backlog（callload 评审尾项）**：[`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md) §4 跟踪表 —— 本计划 **不重复** 开第三条工程线。

---

## 1. M8 是什么 / 不是什么

| M8 **是** | M8 **不是** |
|-----------|-------------|
| 带证据的 **REQ / test-plan** 签收运行 | 新的功能里程碑（不默认扩 PRD 范围） |
| **维护者里程碑退出**（M1/M2/M6/M7）与 **M8 自身** 签收的收口阶段 | 重复做 M2–M7 **工程关门**（工程关门已完成，见 `plan.md` §4） |
| 刷新 **`docs/acceptance/report.md`**（M8 发布候选报告） | 对外 SLA / 商用 O1 数字发布（仍受 AGENT.md §2、plan §5.1 O1 约束） |
| **VERSION / CHANGELOG** 统一产品版本（F15） | Pre-M8 **全量**客户 Demo（故事 C 仍受 F10；见 [`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md)） |
| M5 **REQ 级**证据与全链Remediation（若维护者采纳全链评审） | 自动推翻 2026-10-04 M5 **工程关门**工件（除非维护者显式重开并留裁决记录） |

**完成定义（`plan.md` §4 表）**：逐条验收报告 + 文档链完整 + 统一产品版本。

---

## 2. 进入条件（已满足）

| 条件 | 证据 |
|------|------|
| M0–M5 工程关门；M2/M6/M7 工程完成 | `plan.md` §4 里程碑表 |
| 产品 native / M6 / M7 工程切片在 `master` | [`2026-10-06-callload-merge-to-master.md`](2026-10-06-callload-merge-to-master.md) |
| 本地默认门禁可绿 | `make gate`（基线：964 passed, 2 skipped，2026-10-06） |
| callload P0 + 大部分 P1 已闭合 | [`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md) |

---

## 3. 退出条件（M8 关门）

维护者 **一次性或分里程碑** 签字前，须全部满足：

1. **阶段 A–B 闭合**（§4）：P1 尾项 +（若适用）M5.1 / 全链复评达到维护者认可的 REQ 证据门槛。  
2. **阶段 C**：[`test-plan.md`](../acceptance/test-plan.md) 中 **v1 范围内** 验收项有可追溯证据（含 §5.4 补测；**不含** v1.1 主叫/正则，见 `plan.md` §5.4）。  
3. **阶段 D**：环境类 true blocker 有记录结论（通过 / 有条件通过 / 明确 defer 并写 ADR 或 plan §5 行）：运营商 PKI / 外网 S-SBC、客户 K8s **REQ-NF-1** live baseline。  
4. **阶段 E**：`docs/acceptance/report.md` 升级为 **M8 发布候选报告**；`VERSION` + `CHANGELOG` 与交付一致；`plan.md` §0 / §4 M8 行标 **已完成**。  
5. **Review records**：M8 总审（`docs/reviews/m8-exit-review-*.md`，文件名待创建）+ 各里程碑退出签字表（M1/M2/M6/M7）。

**不宣称「全 REQ 绿」** 除非 test-plan 矩阵中无 open 的 v1 项且维护者在 M8 总审中确认。

### 3.1 v1 验收范围与明确排除

**范围来源**：[`test-plan.md`](../acceptance/test-plan.md) §1–§4 全部 REQ-*；逐条勾选落在 §6 矩阵（[`M8任务草稿.md`](M8任务草稿.md) 为 **REQ 检查表附录**，不修改该文件，矩阵须能回溯到其中每一节）。

| 类别 | 纳入 M8 签收（v1） |
|------|-------------------|
| 功能 | REQ-F-1～F-11、F-16；F-12～F-15 / NF-10（控制面）；§5.4 补测 **F-15 真 AS** |
| 非功能 | REQ-NF-1～NF-15（含 NF-2 双 Deployment、NF-5 仿真器中立、NF-6～NF-8 非目标 grep、NF-11/12 版本与 workspace） |
| 安全 | REQ-S-1～S-4 |
| 治理 | REQ-G-1～G-4 |
| 内核 | test-plan §5（M2 contract/unit）— 已在 `make gate`，M8 报告 **引用** 即可 |

**不计入「M8 全绿」除非维护者扩大范围**（与 `plan.md` §5.3、§5.4 一致）：

- PM / AM / UM 完整产品（需求未补齐）
- REQ-F-13 **live** Call-ID 轨迹（M4b-7.4）；主叫 / 正则（**v1.1**）
- Python 3.10 EOL（**D1**）— 风险登记，不默认阻断 RC
- Redis 故障转移下 owner / CAS 极端场景；**mid-transaction** 崩溃恢复（D10 不扩展）
- test-plan **NF-3** 中带固定容量数字的条目 — 与 AGENT.md §2「M6 前不发布容量数字」冲突时，须 **维护者裁决** 改写验收口径或标 N/A（阶段 C）

**环境 / 架构尾项**：ADR-0008 跨站点切换 **演练**取证归入 M8 报告或维护者 defer；**D12 / O5** 生产 Redis/PG HA 按维护者划定范围 **有条件签收**（阶段 B/C）。

---

## 4. 阶段与顺序（严格顺序）

```text
A 门禁与证据基础设施（P1 尾）
   ↓
B M5 REQ 链 / 全链Remediation（维护者拍板范围）
   ↓
C test-plan 逐条签收（含 §5.4）
   ↓
D 现场 / 运营商环境证据（可与 C 部分并行，但 NF-1/PKI 不得晚于 M8 签字）
   ↓
E 报告、版本、里程碑签字、M8 退出
```

### 阶段 A — 门禁与证据基础设施（P1 尾）

**目标**：后续验收不会在「无 native CI / 无结构化日志」下产生不可复核结论。

| ID | 任务 | 交付物 | 验证 |
|----|------|--------|------|
| A-1 **F9** | origin **blocking** native CI | `.github/workflows/ci.yml`：`m2-platform-resip`（+ 维护者批准的 `chart-check` / `m2-native-smoke` / `m7-*` 子集） | PR 绿；无 `_resip_runtime` 时相关测 **fail**（`native_extensions.py`）；CONTRIBUTING / AGENT §9 写清 gate vs native |
| A-2 **F8** | 结构化 SIP 运行时日志 | C++→Python JSON 回调或字段契约 + 测 | REQ-NF-13 相关断言可挂证据 |
| A-3 **F6** | transport close 回调（尾项） | native 行为 + 测或 documented limitation + 裁决 | 更新 adjudication 表 |
| A-4 | `make gate` 与 CI 关系文档化 | `CONTRIBUTING.md` 或 acceptance 附录 | 维护者确认「合并门禁」清单 |
| A-5 **REQ-G-3 / G-4** | ADR 标注扫描与 CI 阻断语义 | 实现 `make gate-strict`（或 CI 前置 AST 步）**或** 维护者裁决同步改 PRD/ADR/AGENT 为「未实现」并在矩阵标 N/A | `fast` 失败时后续 job 不跑；对照 [`m5-full-chain-review-2026-10-05.md`](../reviews/m5-full-chain-review-2026-10-05.md) §7 |
| A-6 **CI ②③④** | e2e / `performance` 层 | 若该层已有用例则去掉 `continue-on-error`（ADR-0015）；**或** M8 总审书面接受风险 | 对照 `ci.yml` 与 `plan.md` §2.3 |
| A-7 | 验收前 native 一致性 | Runbook 一句：签收跑前 `make m2-platform-resip-build`（及 M7 recovery/two-leg 目标） | 与阶段 C 大跑绑定 |

**闭合标准**：adjudication 表 F9/F8 为「已修复」或 F6 为「已修复 / 已裁决接受风险」；A-5/A-6 有终态（实现或 defer 记录）；**方可大规模开阶段 C**。

**阻塞说明**：F9 上 origin 需维护者 PAT **`workflow` scope** 或等效授权推送 workflow（见 merge handoff §6）。

---

### 阶段 B — M5 REQ 链与全链Remediation

**目标**：M5 **REQ 级**验收与 Demo **故事 C** 口径可对齐，不冒充「工程关门 = REQ 通过」。

| 输入 | [`m5-full-chain-review-2026-10-05.md`](../reviews/m5-full-chain-review-2026-10-05.md)（结论：不通过） |
|------|--------------------------------------------------------------------------------------------------------|
| 维护者决策（阶段 B 开工前 **一次拍板**） | **B-1** 是否执行 M5.1 Remediation 清单；**B-2** 是否维持 2026-10-04 M5 工程关门签字；**B-3** 故事 C 是否仍 L1（F10） |

| 任务 | 说明 |
|------|------|
| B-4 需求链修补 | 7.2d ↔ PRD 缺口（全链 R-1）— 补 REQ 或 ADR 修正 + test-plan 条目 |
| B-5 告警 / 缩容 / onprem values | 对齐全链 Major 项；`chart-check` 进 CI |
| B-6 验收文档 REQ 追溯 | `m5-*.md`、`report.md` M8 章节挂 REQ-NF-* |
| B-7 复评 | 新 review record：`m5-req-acceptance-review-*.md` 或更新全链记录状态 |

**闭合标准**：维护者书面结论 —— M5 **REQ 级**可进入 test-plan 勾选，或明确 **N 项 defer** 写入 plan §5 + M8 总审。

---

### 阶段 C — test-plan 签收

**目标**：[`test-plan.md`](../acceptance/test-plan.md) v1 范围内逐项 **Pass / Fail / Blocked / N/A（含理由）**。

**工作方式**：

1. 自 `test-plan.md` 导出 **M8 矩阵**（见 §6 模板），列：REQ-ID、里程碑归属、证据类型、命令/路径、状态。  
2. 按族并行，但 **签字前** 须全矩阵无未解释的 open。  
3. 与里程碑签收的映射：

| 里程碑 | 主要在 M8 闭合的签收内容 |
|--------|--------------------------|
| **M1** | 维护者补签（[`m1-exit-review.md`](../reviews/m1-exit-review.md)）；无代码变更 |
| **M2** | REQ-S-* 工程已覆盖部分 + 运营商 PKI 尾项；维护者 M2 退出 |
| **M3** | 契约重放（已在 gate）；M8 报告引用即可 |
| **M4/M4b** | REQ-F-12/14、**REQ-NF-10**、REQ-S-4 §1.4；§5.4：**F-13**（BLOCKED→矩阵）、**F-15** 真 AS |
| **M5** | REQ-NF-3/4/9/13/14 + 7.2d；**D12/O5** HA 有条件范围；依赖阶段 B |
| **M6** | REQ-NF-15、O1 **维护者目标裁决**（非对外发布）；NF-15 末条 HPA/`performance` CI；M6 维护者退出 |
| **M7** | REQ-F-1～F-5 / F-6～F-11（含 CANCEL 分支、in-dialog、F-10 透传、竞态）、**REQ-F-16**；E1 S1–S11、D9 forking；D10/D11 **REQ 签收**；**REQ-NF-1** 工程 harness + 阶段 D live |
| **横切** | REQ-NF-2/5/6/7/8、REQ-NF-11/12、REQ-S-1、REQ-G-1/2、**O4** 轨迹保留期（与 NF-7 清理任务） |

**闭合标准**：矩阵中 v1 项均为终态；Blocked 须指到 plan §5 或 v1.1。

---

### 阶段 D — 环境证据（true blockers）

来自 [`2026-10-05-milestones-engineering-complete.md`](2026-10-05-milestones-engineering-complete.md) §True blockers：

| # | 项 | 证据落点 |
|---|-----|----------|
| D-1 | 运营商 PKI / 外网 S-SBC（REQ-S-2/3 尾） | `docs/acceptance/artifacts/m8/<date>/req-s-*/`（脱敏） |
| D-2 | 客户 K8s REQ-NF-1 live kill/restart/BYE | 同目录 + runbook 引用 |
| D-3 | **D6** testbed 是否 v1 客户验收 | 维护者裁决 → ADR 或 plan §5.2 行关闭 |

无法在 M8 窗口内完成的项：**不得** 宣称 M8 全绿；须在 M8 总审中 **有条件通过** 并列出 defer 清单（须维护者授权）。

---

### 阶段 E — 报告、版本、签字

| 任务 | 交付物 |
|------|--------|
| E-1 | `docs/acceptance/report.md` — M8 发布候选主报告（取代「仅 M1 叙事」的读者体验；历史 M1 节可保留为附录） |
| E-2 | **F15**：`VERSION`、`CHANGELOG.md` |
| E-3 | `plan.md` §0、§4 M8 行 → **已完成** |
| E-4 | `docs/reviews/m8-exit-review-YYYY-MM-DD.md` |
| E-5 | 里程碑签字表：M1、M2、M6、M7、M8（AGENT.md §3.3 格式） |
| E-6 | **发布候选打包**：`VERSION`/`CHANGELOG`/ `test_version_consistency`；镜像与 Helm **可重复构建**；复检无密钥/无真实抓包；README 与 runbook 与 `AS_SIP_*`/`AS_TLS_*` 等实现一致 | NF-9、NF-11；镜像 push/tag 仍仅维护者 |

**闭合标准**：维护者 M8 签字 + tag 由维护者执行（AGENT.md §10.4）。

**非工程任务**：callload **F11**（提交历史形态）— 维护者自行处理，不纳入 agent 队列（见 adjudication）。

---

## 5. 未决项在 M8 内的处置

| ID | 处置阶段 | 说明 |
|----|----------|------|
| **O1** 容量目标 | C + E | dev-host 报告已有；维护者 **目标裁决** + HPA 填值是否进入 v1 RC |
| **O3** E1 S5–S11 | C | M7 工程已覆盖部分；余项 test-plan |
| **D6** testbed 客户验收 | D（拍板） | v1 vs v1.1 |
| **D9** forking / race | C | M8 验收范围 |
| **D10/D11** REQ 签收 | C + D | 工程测试已有；NF-1 live 在 D |
| **§5.4** F-13、F-15、REQ-S-4 全绿 | C | 不阻塞工程关门，阻塞 REQ 全绿宣称 |
| **O4** 轨迹保留期 | C | 与 NF-7 清理；可冻结天数后签收 |
| **O5** / **D12** | B + C | 集群内 store HA/PITR；未覆盖写 defer |
| **ADR-0008** 切换演练 | C 或 defer | 跨站点演练证据或 M8 总审 defer |
| **REQ-G-3** | A | gate-strict 或文档/矩阵 N/A |
| **REQ-NF-3** 容量数字 | C + E | 与 O1、AGENT §2 三方对账 |

---

## 6. M8 test-plan 矩阵（执行时填写）

复制到 `docs/acceptance/m8-test-plan-matrix.md`（首任务可在阶段 C 开工时由 agent 生成），列定义：

| 列 | 含义 |
|----|------|
| `req_id` | REQ-F-* / REQ-NF-* / REQ-S-* / REQ-G-* |
| `test_plan_ref` | test-plan 章节 |
| `milestone` | M2…M7 归属 |
| `phase` | A/B/C/D |
| `evidence` | 命令、日志路径、review 链接 |
| `status` | open / pass / fail / blocked / n/a |
| `signed_by` | 维护者 + 日期 |

---

## 7. 验证命令（基线）

```bash
# 默认合并门禁
make gate

# Native / M7（阶段 A 后应在 CI 等价覆盖）
make m2-platform-resip-build
uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q
uv run pytest platform/tests/test_m7_forward_two_leg_integration.py \
  platform/tests/test_req_f4_sdp_identity_integration.py -m integration -q

# M5 chart（阶段 A/B）
make chart-check

# 维护者环境（阶段 C）
# PostgreSQL 12.22 integration：见 plan §0 PG 说明
uv run pytest -m integration -q

# Kind 证据（阶段 B/C，维护者机）
make m5-kind-verify   # 按需
```

---

## 8. 跟踪表（M8 级）

| 阶段 | 状态 | 目标日期 | 备注 |
|------|------|----------|------|
| A P1 尾 + CI 治理 | open | | F9/F8/F6；A-5～A-7 |
| B M5 REQ | open | | 待维护者 B-1…B-3 |
| C test-plan | open | | 矩阵待建 |
| D 环境 | open | | PKI / NF-1 |
| E 签字发布 | open | | report + VERSION |

---

## 9. 关联文档

| 文档 | 角色 |
|------|------|
| [`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md) | 客户 Demo 边界（F10） |
| [`m5-full-chain-review-2026-10-05.md`](../reviews/m5-full-chain-review-2026-10-05.md) | M5 REQ 风险清单 |
| [`cross-milestone-final-adjudication-2026-10-05.md`](../reviews/cross-milestone-final-adjudication-2026-10-05.md) | 工程基线裁决 |
| [`acceptance/report.md`](../acceptance/report.md) | M8 最终主报告载体 |
| [`M8任务草稿.md`](M8任务草稿.md) | REQ 域检查表（矩阵须全覆盖；流程以本文为准） |
| [`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md) | F1–F18 尾项（F9 非「仅消费」） |

---

## 10. 维护者开工确认（待填）

| 项 | 维护者 | 日期 | 备注 |
|----|--------|------|------|
| 批准进入 M8 | | | |
| 阶段 B 范围（M5.1 是否做） | | | |
| D-3 / D6 裁决 | | | |
| 阶段 A 完成 | | | |
| M8 退出签字 | | | |
