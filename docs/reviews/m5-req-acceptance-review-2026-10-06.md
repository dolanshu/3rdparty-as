# M5 REQ 级验收评审记录（M8 发布候选，Phase B 最小集）

- **评审对象（object）**：M5 里程碑 **REQ 级**验收（为 M8 test-plan 勾选提供口径），范围 = REQ-NF-3 / REQ-NF-4 / REQ-NF-9 / REQ-NF-13 / REQ-NF-14 + 7.2d ingress/trusted-proxy 关门条件。输入：[`m5-full-chain-review-2026-10-05.md`](m5-full-chain-review-2026-10-05.md)（结论：不通过）、[`2026-10-06-m8-release-candidate-plan.md`](../handoff/2026-10-06-m8-release-candidate-plan.md) §4 Phase B。
- **评审日期（date）**：2026-10-06
- **评审人（reviewer）**：AI agent（维护者缺席期间用户指令 self-decision；**维护者会签待补**，本记录不替代维护者签字）。
- **评审结论（conclusion）**：**有条件通过（工程切片）/ REQ 级不通过，10 项 defer**。M5 工程切片（chart 部署形态、draining/缩容机制接线、kind 部署证据）可进入 M8 引用；M5 **REQ 级不通过**，不得宣称为 REQ 全绿；下表 10 项明确 defer，其余全链 Major/Minor 仍按全链评审 §7 跟踪（见 §5）。

---

## 1. Phase B 自决策记录（B-1 / B-2 / B-3，会签待补）

| ID | 自决策 | 理由 |
|----|--------|------|
| **B-1** | 只执行 **MINIMAL M5.1**：Helm fail-open 修补（H-1…H-4）+ chart-check onprem 矩阵 + K-1/K-2 fail-closed 加固 + HLD/LLD M5 delta + ADR-0008 amendment + REQ 链注记。全量告警/指标接线（C-1…C-5）、OTLP exporter（C-7）、缩容守卫参控（C-6）、NetworkPolicy egress、resources/probes 全部 **DEFER 到 RC 后** | RC 不得宣称 M5 REQ 绿；工程切片证据足以支撑部署形态举证，全链修复超出 RC 窗口 |
| **B-2** | **维持** 2026-10-04 M5 工程关门签字（不撤销、不改写历史），但将其含义明确**降级**为`工程关门（非REQ验收）` | 避免重写历史；工程关门与 REQ 验收是两回事，本记录首次把这句话写进评审结论 |
| **B-3** | 故事 C 保持 **L1（F10）**：只展示 chart/alerts **形态** + kind 摘要，不得表述为"M5 全链已验收"或"生产告警/缩容已闭环" | 依据 [`pre-m8-demo-review-plan.md`](../handoff/pre-m8-demo-review-plan.md) F10 对账段；在全链结论翻转前口径不变 |

## 2. B-4 — 7.2d 需求链缺口登记

- 7.2d（ingress/trusted-proxy）是 M5 三大关门条件之一，但在 PRD 中**无对应 REQ 来源**（全链 R-1：REQ-S-2 是 SIP 信令 TLS，REQ-S-4 只讲鉴权与审计，均不覆盖控制台 HTTPS 重定向 / `X-Forwarded-Proto` 信任 / ingress proxy CIDR 白名单）。
- 本记录将其登记为**无源关门条件（sourceless gate condition）**：`test-plan.md` §1.4（M4b-7.2d preflight）只作为部署前检查执行，**不产生 REQ 通过项**；补 REQ 或 ADR 修正由维护者在 M8 阶段 C 前裁决。

## 3. B-5 — 范围说明

- `chart-check` 进 CI（阻塞式 ① fast job）已在 **Phase A** 完成（`.github/workflows/ci.yml`），本任务不再动 CI。
- 本任务的 B-5 落点是 **onprem values 可渲染**：`values-onprem.example.yaml` 置非空占位 secretName + `config-service-deployment.yaml` fail 信息指向示例文件 + chart-check 新增 onprem 矩阵（H-2 验证）。

## 4. B-6 — REQ 追溯注记

- 全链 R-2：5 份 M5 验收/runbook 文档与 `report.md` M5 段 **REQ-\* 引用数为 0**。本记录恢复该链接，M5 工程切片追溯到：**REQ-NF-3**（水平扩展/draining/缩容机制）、**REQ-NF-4**（ISSU draining 语义）、**REQ-NF-9**（单租户 on-prem Helm 交付）、**REQ-NF-13**（指标/health 端点形态）、**REQ-NF-14**（告警规则集形态，仅形态）、**7.2d**（无源关门条件，见 B-4）。
- 追溯止于"工程切片"等级，不构成上述 REQ 的通过判定。

## 5. 本次最小集做了什么 / 明确没做什么

已做（本任务 diff）：H-1（`secret.yaml` else 分支补全 key + stateStores 生产组合 `fail`）、H-2（onprem 示例占位 + chart-check onprem 矩阵）、H-3（`tls.secretName` 为空 `fail`）、H-4（`peerAllowlist` 为空 `fail` + `sip.allowEmptyAllowlistForTest` 测试逃生）、K-1（ingress/verify 脚本 WARN→FAIL）、K-2（HPA 守卫校验 helm exit code + onprem 渲染断言 exit code）、HLD/LLD `Amendment 2026-10-06`、ADR-0008 SPoF 缺口 amendment、ADR-0013 amendment 注记。

明确没做（仍 open，全链 §7 原文为准）：告警 C-4/C-5 minor、模拟 seam C-8、配置崩溃路径 C-10、版本 store 零测试 C-11、H-5/H-6/H-7/H-9/H-10、K-3…K-6、R-1…R-9（含 R-3 容量口径互斥、R-6 证据 gitignore），以及下表 10 项正式 defer。

## 6. Defer 清单（10 项；REQ 级不通过的构成项）

| # | 全链 ID | 内容 | plan §5 对应 / 拟新增行 |
|---|---------|------|--------------------------|
| 1 | C-1 | 告警 6 条死规则（4 指标不存在 + 2 零调用点） | §5.3 PM/AM（告警生命周期需求待补）＋ §4.4.3（容量类告警 M6 后）；拟新增 `M5D-1` |
| 2 | C-2 | `clamp_min` 数学错误（低话务全量故障不触发） | §5.1 O1（阈值须 M6 实测）；拟新增 `M5D-1` |
| 3 | C-3 | telemetry 阈值 `> 0` 语义不符 | §5.1 O1；拟新增 `M5D-1` |
| 4 | C-6 | 缩容守卫死配置（读入只 log，不参与判定） | ADR-0020/M7 actuation 未决；拟新增 `M5D-2`（守卫参控 + 开/关两态行为测试） |
| 5 | C-7 | OTLP 导出空壳（NoOp sink，入队即丢） | §5.3 PM（OTel traces/logs 未落地）；拟新增 `M5D-3` |
| 6 | C-9 | 指标零生产调用点（response/rule_hit/telemetry_dropped 永不递增） | M7 E1（真呼叫计数走信令路径）；拟新增 `M5D-1` |
| 7 | H-8 | NetworkPolicy 无 Egress、源标签过宽 | §5.1 D12/O5（HA/拓扑客户 SLA）；拟新增 `M5D-4` |
| 8 | H-11 | 无 resources（BestEffort）、AS 无 startupProbe、config-service tcpSocket 探针 | §5.1 O1/M6（sizing 下游于实测）；拟新增 `M5D-5` |
| 9 | A-2 | 跨站点切换演练未做（ADR-0008 指派给 M5） | §5.1 O5（容灾等级客户 SLA）；拟新增 `M5D-6` |
| 10 | T-1 | feature 开关无开/关两态行为测试 | ADR-0020 默认态/灰度策略未决；拟新增 `M5D-2` |

拟新增 plan §5 行（`M5D-1`…`M5D-6`）的落定由维护者执行——本任务不改 `plan.md`（维护者拥有计划编辑权），上表即提议的行内容。

## 7. B-7 — 复评声明

- 本记录为 M5 的 **REQ 级复评**（相对全链"不通过"与 2026-10-04"工程关门"）：结论是有条件通过（工程切片）/ REQ 级不通过。
- M5 REQ 级要翻转为通过，须关闭上表 10 项（或维护者书面接受为风险/移出 v1），并由维护者在本记录会签栏签字；签字前任何"全 REQ 绿"表述均属违规。

---

## 确认（confirmation）

| 项 | 记录 |
|---|------|
| 评审结论 | 有条件通过（工程切片）/ REQ 级不通过，10 项 defer（§6） |
| 自决策 | B-1（最小 M5.1）/ B-2（维持工程关门并降级含义）/ B-3（故事 C 保持 L1）——维护者会签待补 |
| 维护者确认 | **待签字**（本栏须由维护者填写；本记录不构成 REQ 级通过，也不撤销既有关门记录） |
| 输入评审 | [`m5-full-chain-review-2026-10-05.md`](m5-full-chain-review-2026-10-05.md)（不通过，维持有效；本记录是其 Phase B 复评，不是推翻） |
| 未采信证据 | `docs/reviews/` 下所有 `m5-*` 工程关门评审记录（沿用全链证据排除声明） |
