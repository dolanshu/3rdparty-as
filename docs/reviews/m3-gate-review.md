# M3 门禁评审记录

> 评审对象：M3 —— 应用（决策模块与契约重放）。范围含 `apps/translation`、`apps/anti-fraud` 的决策模块与测试、`testbed/contracts/decision/` 契约用例集
> 评审日期：2026-09-28
> 评审人：AI agent（实跑门禁 + 对照 plan.md §4 M3 门禁、AGENT.md §4/§5/§6）
> 评审结论：**通过** —— M3 门禁达成，M3 判为已完成

## 门禁核对

| 门禁项 | 状态 | 证据 |
|---|---|---|
| `apps/translation` 与 `apps/anti-fraud` 的决策模块 | 达成 | `as_translation/decision.py`（132 行）、`as_anti_fraud/decision.py`（158 行），均建立在内核 `decide()` 之上 |
| 决策模块先做 TDD | 达成 | 两模块均先红（`ModuleNotFoundError`）后绿；translation 10 例、anti-fraud 14 例（marker `unit`） |
| 契约用例集对两者都重放绿 | 达成 | `testbed/contracts/decision/cases.json` 14 例；`apps/translation/tests/test_contract_replay.py` 与 `apps/anti-fraud/tests/test_contract_replay.py` 各自重放，marker `contract`，共 21 个用例通过（19 个参数化重放 + 2 条防假绿守卫） |

## 门禁证据

| 项 | 结果 |
|---|---|
| `uv run ruff format --check .` | 116 files already formatted |
| `uv run ruff check .` | All checks passed! |
| `uv run mypy` | Success: no issues found in 25 source files |
| `uv run pytest -m "unit or contract" -q` | 190 passed, 2 skipped |
| `uv run pytest -m contract -q` | 49 passed, 2 skipped |
| `uv run pytest -m integration -q` | 3 passed |

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| G1 | 契约用例集为声明式 JSON + README，与实现语言无关；用例带 `applies_to` 区分 two apps | 接受：符合 AGENT.md §6「契约 = 声明式用例，对每一个实现重放」 |
| G2 | 基线翻译事实（`+8613800138000` → `013800138000`）只标 `translation`，不标 `both` | 接受：同一输入下 translation 改写 target、anti-fraud 明确不改写（target 为 null），语义本就互斥；共享语义已用 `both` 表达（block 优先、无匹配、最长前缀、分隔符无语义） |
| G3 | 两个重放测试各带"本用例至少命中若干契约例"的守卫，防止筛选器失配导致空绿 | 接受：防的是静默假绿 |
| G4 | 契约期望值由内核取胜规则 `(action_rank, prefix_length)` 手算后再由重放验证，未为通过而改数据 | 接受 |
| G5 | 期间同时引入了首个 `integration` 层用例（遥测导出真 socket），并把 CI 层②改为阻塞 | 接受：AGENT.md §9 要求首个引入该层的里程碑同步改阻塞；层③ e2e 与层④ performance 仍无用例，保持原状 |

## 遗留（不阻塞 M3）

| # | 遗留 | 去向 |
|---|---|---|
| G6 | 速率窗口的计数仍未与 StateStore 接线（滑动窗口、TTL、脑裂幂等） | M3 后续 / 依赖未决 D3 |
| G7 | `e2e` 层仍零用例 | 首个 e2e 用例的里程碑，并把 CI 层③改阻塞 |
| G8 | 两个成员下的测试目录结构不对称（`apps/anti-fraud/tests/` 有 `__init__.py`，translation 没有），源于同名 `test_decision.py` 的收集冲突 | 建议后续统一：根 pyproject 设 `importmode = "importlib"`，或成员内改用不重名文件名 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过，M3 判为已完成 |
| 门禁 | 达成（190 passed / 2 skipped；contract 49 passed；integration 3 passed） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
