# M4 控制台鉴权与审计、D7 裁决评审记录

> 评审对象：`services/console/src/as_console/access.py` 与其测试；`docs/architecture/adr/0021-runtime-override-granularity.md`、`platform/src/as_platform/gating/overrides.py` 与其测试
> 评审日期：2026-09-28
> 评审人：AI agent（实跑门禁 + 对照 REQ-S-4、ADR-0016、ADR-0020、AGENT.md §13/§15）
> 评审结论：**通过** —— 控制台鉴权审计落地、D7 已按 AGENT.md §15 写 ADR 裁决并移出未决清单；M4 判为**已完成**，PostgreSQL 接线转入 M5

## 门禁证据

| 项 | 结果 |
|---|---|
| `uv run ruff format --check .` | 134 files already formatted |
| `uv run ruff check .` | All checks passed! |
| `uv run mypy` | Success: no issues found in 30 source files |
| `uv run pytest -m "unit or contract" -q` | 309 passed, 2 skipped |
| `uv run pytest -m integration -q` | 3 passed |
| TDD | 两个模块均先红（`ModuleNotFoundError`）后绿 |

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| P1 | 权限矩阵参数化 20 组合，并带"矩阵覆盖全部角色与权限"的防空洞守卫 | 接受：防止新增权限时矩阵静默失效 |
| P2 | 无角色 / 未知角色一律拒绝（fail-closed），不抛异常 | 接受：未知角色不应成为绕过检查的路径 |
| P3 | `authorize_and_audit` 把判定与审计绑在一起，且**拒绝也留痕** | 接受：这正是 REQ-S-4「每个控制台操作都要鉴权并审计」的可测表达 |
| P4 | `AuditRecord` 为 frozen | 接受：审计证据不应可事后改写 |
| P5 | `may_approve` 双人原则：提交者不能审批自己的变更，且仍需具备 `APPROVE_CHANGE` | 接受：与 ADR-0006 的审批留痕语义一致 |
| P6 | D7 按 AGENT.md §15 走"写 ADR + 移动 plan.md 那一行"的正当流程解决，而非悄悄消化 | 接受：未决项不得静默消失 |
| P7 | 运行态覆盖用稳定哈希（FNV-1a 32）而非随机/时钟，保证脑裂窗口下判定幂等 | 接受：直接回应风险 R5 与未决 D3 |
| P8 | `enabled=False` 优先于百分比；无命中返回 `None` 而非 `True` | 接受：显式关闭与 fail-closed 的语义一致 |
| P9 | 时间全程由调用方注入，两模块均无时钟 / 无 socket | 接受：保持纯函数（AGENT.md §5） |

## M4 完成裁决（重要）

| 项 | 裁决 |
|---|---|
| M4 是否完成 | **判为已完成** —— 治理闭环（编辑 → 审批 → 分发 → 上报版本 → 回滚）、开关走流水线 + 两态测试、控制台鉴权与审计，均已落地并有测试证据 |
| PostgreSQL 版 `VersionStore` | **转入 M5**，理由：它属于部署与运维形态的一部分，与 Helm / 高可用同批接线；当前以 `InMemoryVersionStore` + Protocol 保证契约可测 |
| 这样做的风险 | 治理闭环尚未在真实数据库上验证；M5 必须补一条针对真实 PG 的 integration 用例，并把该闭环端到端跑通，否则 M5 不得判完成 |
| 未决项变化 | D7 已裁决（ADR-0021）；O1（容量）、O5（容灾等级）、D3（Redis 接线与幂等）仍开放 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过；M4 判为已完成 |
| 门禁 | 全绿（309 passed / 2 skipped；integration 3 passed） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |

## 范围修正（2026-10-01）

本评审原始范围是访问策略代码与 D7 裁决；未审查或交付前端 UI，也未进行 UI 验收。保留上述历史发现，但其整体 M4 closure 结论已由用户 2026-10-01 的决定 supersede：M4 仍未完成，须待强制 M4b operator UI 按 [`plan.md`](../plan.md) 和 [`acceptance/test-plan.md`](../acceptance/test-plan.md) 中 REQ-F-12/13/14/15、REQ-S-4 的现有标准验收通过。
