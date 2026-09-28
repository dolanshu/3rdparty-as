# ADR-0020 评审记录（Feature 能力门控与开关）

> 评审对象：`docs/architecture/adr/0020-feature-capability-gating.md`（Status: draft → 本次评审）
> 评审日期：2026-09-28
> 评审人：AI agent（对照 AGENT.md §3.4 / §6、ADR-0006、已落地的门控实现）
> 评审结论：**通过** —— 转 accepted；1 项未决（D7）列为已知缺口，不阻塞

## 评审方法

| 维度 | 方法 |
|---|---|
| 与红线一致性 | AGENT.md §3.4（每个 feature 必须裁决开关 / 默认态 / 灰度 / 移除条件）、§6（两态都要覆盖） |
| 与既有 ADR 一致性 | ADR-0006（开关复用配置治理流水线）、ADR-0007（运行态覆盖在 Redis） |
| 与实现一致性 | `platform/src/as_platform/gating/`（默认关、fail-closed、判定幂等）、`platform/src/as_platform/api/contract.py`（`ToggleDTO` 进 `ConfigBundle`） |
| 结构完整性 | 是否具备 Context / Decision / Consequences / Alternatives / Evidence / Related |

## 发现与裁决

| # | 发现 | 裁决 |
|---|---|---|
| T1 | 两层门控职责分明：① 部署级总开关（PG 版本库、热加载）② 运行态细粒度覆盖（Redis、判定幂等） | 接受：既有总闸可一键收敛，又有灰度粒度 |
| T2 | 明确"默认关"与"移除条件"（防开关债务），并要求每个 feature 在 ADR / HLD 显式裁决 | 接受：与 AGENT.md §3.4 一致；`ToggleDTO.removal_condition` 已实现为**必填**（不给默认值） |
| T3 | 开关只做能力启停、不改接口契约；关闭走既有默认路径 | 接受：避免出现"关闭态"的对外行为分支 |
| T4 | 运行态判定必须幂等以承受 Redis 脑裂窗口（风险 R5 / 未决 D3） | 接受：已由 `is_enabled` 的纯函数判定与两态测试覆盖 |
| T5 | 与 ADR-0006 一致：开关作为一类配置版本走同一条变更流水线，不另开通道 | 接受：已落地 —— `ConfigBundle.toggles` 与 `toggle_deployment()`，并有"开关随变更单走审批→分发→回滚"的测试 |
| T6 | 未决 D7（运行态覆盖的判定粒度与配置 schema：号段 / 呼叫 / 用户 / 百分比）仍未定 | 接受为**已知缺口**：M4 完成前需定，否则运行态覆盖无法配置化 |
| T7 | 运行态覆盖目前只有 seam（`StaticToggleSource`），Redis 侧实现未做 | 接受为**已知缺口**：与 ADR-0007 的运行态存储接线同步完成（M5 前后） |

## Adjudication 汇总

| 类别 | 条数 | 处置 |
|---|---|---|
| 接受且无需修改 | 5（T1-T5） | — |
| 接受为已知缺口 | 2（T6、T7） | D7 在 M4 完成前定；Redis 侧实现与 ADR-0007 接线同步 |
| 需要修改 | 0 | — |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过 |
| 状态流转 | `draft` → `accepted`；注册表同步 |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
