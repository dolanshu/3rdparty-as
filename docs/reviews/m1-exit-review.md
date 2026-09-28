# M1 退出评审记录（Milestone Exit Review）

> 评审对象：M1 —— 甄别与行为基线。范围含 `docs/plan.md` §4.1 门禁裁决、`docs/acceptance/report.md`、`docs/migration/triage.md`、`testbed/contracts/sip-baseline/`
> 评审日期：2026-09-28
> 评审人：AI agent（核对门禁与 DoD 取证）
> 评审结论：**有条件通过** —— 条件为 HLD/LLD 补建，已列入 M2 前置，不回退 M1 结论

## 评审方法

| 维度 | 方法 |
|---|---|
| 门禁达成 | 逐项核对 `plan.md` §4 M1 门禁原文，并回查仓库产物 |
| DoD 取证 | 按 `AGENT.md` §14 十条逐项取证，代码相关条目要求实跑证据 |
| 基线完整性 | 逐个统计 `testbed/contracts/sip-baseline/` 各目录下 `.txt` 消息文件数 |
| 文档链 | requirement → ADR → HLD/LLD → 契约 → 验收 → review record 六环是否贯通 |

## 发现与裁决

| # | 发现 | 证据 | 裁决 | 状态 |
|---|---|---|---|---|
| F1 | S5 / S6 / S7a / S8 基线目录只有 README，零消息文件 | 目录实测；对应 REQ-F-2 / F-3 / F-4 / F-5（P0） | 接受为**派生基线**：`test-plan.md` 中这四条验收本就写为"完成 REQ-F-1 的基本呼叫后提取 X"，可从 `S1-basic-call` 派生，重复抓取只增加维护面 | 已裁决（写入 `plan.md` §4.1） |
| F2 | S10 / S11 基线未抓 | 目录实测；POC ReturnUas 只回 200 OK，无 busy 分支与竞态构造 | 接受为 **M2 probe 补**，与 `prd.md` §2.4 已知缺口表一致 | 已裁决 |
| F3 | `plan.md` 状态滞后（§0 写 M1 进行中、§4 写 M1 未开始），但实际产出已入库 | 提交 `b27bb3d` / `92c244c` / `e30c426` / `2341166` / `c9d4899` | 接受：更新为 M1 已完成、当前步骤 M2，并新增 §4.1 记录门禁裁决 | 已修改 |
| F4 | 无 M1 验收报告 | `docs/acceptance/` 原只有 README 与 test-plan | 接受：新建 `docs/acceptance/report.md`，含实跑门禁证据与 DoD 逐项 | 已修改 |
| F5 | 无 M1 退出评审记录 | `docs/reviews/` 原有记录均针对 ADR 或 PRD | 接受：本文件 | 已修改 |
| F6 | CHANGELOG 无 M1 条目；`VERSION` 仍 0.1.0 | `CHANGELOG.md`、`VERSION` | 接受：CHANGELOG 补 M1 条目；`VERSION` **维持 0.1.0** —— M1 无产品代码交付，交付内容未变，按 ADR-0018 不 bump | 已修改 |
| F7 | HLD / LLD 尚未创建 | `docs/architecture/` 下无 `hld.md`、`lld.md` | 接受为**条件**：不回退 M1 结论，但列为 M2 首个动作（AGENT.md §3.1 要求 HLD/LLD 是进入 Code 的前置） | 待 M2 |
| F8 | 计数错误：S4 消息条数记为 9，实为 12 | `S4-caller-cancel/` 实测 12 个 txt，README 写"消息序列（12 条）" | 接受：已修正 `plan.md` §4.1 与 `report.md` | 已修改 |
| F9 | PRD 评审中 RFC 3261 依据一度仅到"目录确认"级别 | `docs/reviews/prd-v0.1-review.md` | 接受：已用 `curl` 抓全文切片补验，§9 / §9.1 / §9.2 / §15 / §15.1.2 / §16.4 全部升为 L1 逐字核对，遗留清零 | 已修改 |

## Adjudication 汇总

| 类别 | 条数 | 处置 |
|---|---|---|
| 已裁决并落地 | 8（F1-F6、F8、F9） | 修改已入 `plan.md` / `report.md` / `CHANGELOG.md` / `prd-v0.1-review.md` |
| 条件项（移交 M2） | 1（F7 HLD/LLD） | 列为 M2 首个动作，不阻塞 M1 结论 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 有条件通过（条件：M2 补建 HLD/LLD） |
| M1 门禁 | 达成 |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
