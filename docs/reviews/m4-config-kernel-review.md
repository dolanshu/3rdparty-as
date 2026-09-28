# M4 配置治理内核评审记录

> 评审对象：`services/config-service/src/as_config_service/`（`change_order.py`、`version_store.py`、`distributor.py`）、`platform/src/as_platform/api/contract.py` 的开关契约扩展，及其测试
> 评审日期：2026-09-28
> 评审人：AI agent（实跑门禁 + 对照 ADR-0006、ADR-0020、AGENT.md §3.4/§5）
> 评审结论：**通过（阶段性）** —— 治理逻辑闭环达成；PostgreSQL 接线与控制台未开始，不判 M4 完成

## 门禁证据

| 项 | 结果 |
|---|---|
| `uv run ruff format --check .` | 127 files already formatted |
| `uv run ruff check .` | All checks passed! |
| `uv run mypy` | Success: no issues found in 28 source files |
| `uv run pytest -m "unit or contract" -q` | 254 passed, 2 skipped |
| `uv run pytest -m integration -q` | 3 passed |
| TDD | 三个模块均先红（`ModuleNotFoundError` / `ImportError`）后绿 |

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| N1 | 变更单状态机为纯函数，非法跳转抛 `IllegalTransitionError`（含 `DRAFT → APPLIED`），审批必留审批人与时间 | 接受：REQ-F-14 与 ADR-0006 的状态机语义落地 |
| N2 | 版本库为不可变追加，历史版本只读；PG 实现留 seam 未实现 | 接受：ADR-0006 / ADR-0007 要求不可变版本行；PG 接线列为 M4 剩余项 |
| N3 | 分发在"任一实例不健康"时立即回滚并停止推进后续批次 | 接受：爆炸半径锁在当前批次，正是灰度的意义 |
| N4 | `rollback_target` 为 `version - 1`，首个版本无可回滚目标返回 `None` | 接受：边界明确，有测试 |
| N5 | 开关进入 `ConfigBundle`，与规则同属一个版本、走同一条流水线；`ToggleDTO.removal_condition` **不给默认值** | 接受：防开关债务（ADR-0020 / AGENT.md §3.4）；不给默认值是对的 |
| N6 | `toggle_deployment` 保留 `False`，不过滤"关" | 接受：过滤会让"关"被误读为"未配置"，也会在回滚时残留旧值 |
| N7 | 开关两态均有测试（内核契约 7 条 + 流水线 7 条） | 接受：AGENT.md §6 要求两态都覆盖 |
| N8 | `ConfigBundle.toggles` 带默认值，既有构造方式与 config-service 既有测试均未受影响（254 = 240 + 14，2 skipped 未变） | 接受：向后兼容已由门禁验证 |
| N9 | 两处实现偏差：`InMemoryVersionStore.append` 的 `now` 放宽为可选；`Distribution` 多两个默认字段 | 接受：否则注入的 clock 与 reason/now 无处安放；均为默认参数，不破坏调用方 |

## 剩余（M4 未完）

| # | 剩余 | 说明 |
|---|---|---|
| N10 | PostgreSQL 版 `VersionStore` 实现 | 需真实 PG；建议随 integration 层用例一起引入（该层已改为阻塞） |
| N11 | `services/console`（读写、鉴权、审计，REQ-S-4） | M4 另一半，尚未开始 |
| N12 | `ConfigVersion.change_id` 当前允许 `None` | 生产写入路径需强制非空，由 PG 实现或上层服务承担，待裁决 |
| N13 | ADR-0020 仍为 draft | 开关流水线的依据，须在 M4 完成前评审转正 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过（阶段性）；M4 不判完成 |
| 门禁 | 全绿（254 passed / 2 skipped；integration 3 passed） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
