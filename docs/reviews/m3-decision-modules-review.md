# M3 决策模块评审记录（translation / anti-fraud）

> 评审对象：`apps/translation/src/as_translation/decision.py` 与其测试；`apps/anti-fraud/src/as_anti_fraud/decision.py` 与其测试
> 评审日期：2026-09-28
> 评审人：AI agent（实跑门禁 + 对照 AGENT.md §4/§5、ADR-0002/0016、基线事实）
> 评审结论：**通过** —— 两模块均建立于内核之上；1 项结构偏差已确认可接受

## 门禁证据

| 项 | 结果 |
|---|---|
| `uv run ruff format --check .` | 111 files already formatted |
| `uv run ruff check .` | All checks passed! |
| `uv run mypy` | Success: no issues found in 25 source files |
| `uv run pytest -m "unit or contract" -q` | 169 passed, 2 skipped |
| TDD | 两模块均先红（`ModuleNotFoundError`）后绿 |

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| M1 | 两模块的判决都以内核 `decide()` 为唯一入口，只在内核判决之上叠加用例语义 | 接受：M2 门禁"能在其上构建用例而不碰 sippy"得到实证，且未重复实现匹配/优先级 |
| M2 | translation 的 `+8613800138000 → 013800138000` 断言来自已抓取基线 S1 与规则 R-MOB-CM-40，不是臆造 | 接受：把派生基线的事实固化成用例层断言 |
| M3 | anti-fraud 用独立 `RATE_LIMIT` reason，与内核 `MATCH_BLOCK` 区分；且明确不改写号码（翻译属 translation 用例） | 接受：用例职责不互相侵入 |
| M4 | 速率窗口的计数由调用方注入（`Mapping[str, int]`），模块内不读时钟、不开 socket | 接受：保持决策模块纯函数（AGENT.md §5）；窗口语义由 StateStore 承担（ADR-0002） |
| M5 | 超限判定用 `>=` 而非 `>`，并在 docstring 解释 | 接受：边界语义正确（用 `>` 会多放行一次） |
| M6 | anti-fraud 在 `FORWARD` / `TRANSLATE` 之后才做速率筛查 | 接受：先被内核拒的呼叫不应消耗窗口，否则可被利用来耗尽窗口 |
| M7 | 两个成员下同名 `test_decision.py` 导致 pytest 收集冲突，解决方式是给 `apps/anti-fraud/tests/` 加 `__init__.py` | 接受：不改根 `pyproject.toml` 的导入模式、不动其他成员的前提下代价最小；**遗留**：建议后续统一为 `importmode = "importlib"` 或在成员内改用不同测试文件名 |
| M8 | 均未跨 app 导入（无 `as_translation` ↔ `as_anti_fraud`），无 `# type: ignore` / `# noqa` | 接受（AGENT.md §4） |

## 缺口（不阻塞）

| # | 缺口 | 去向 |
|---|---|---|
| M9 | 计数器如何写入/读取 StateStore（窗口滑动、TTL、脑裂幂等）尚未接线 | M3 后续（接线层），依赖未决 D3 |
| M10 | 两用例尚无 `contract` 层重放（契约用例集对两者重放是 M3 门禁） | M3 收尾 |
| M11 | 无 `integration` / `e2e` 层用例 | 首个该层用例的里程碑，并把 CI 层②③ 改阻塞 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过 |
| 门禁 | 全绿（169 passed / 2 skipped） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
