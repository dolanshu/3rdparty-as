# M2a 内核代码评审记录

> 评审对象：`platform/src/as_platform/`（decision / state / gating / telemetry / shell / api）与 `platform/tests/` 六个新增测试文件
> 评审日期：2026-09-28
> 评审人：AI agent（实跑门禁 + 结构守卫 + 反向依赖检查）
> 评审结论：**通过** —— 门禁全绿；6 项实现决策已确认，4 项缺口列入后续

## 门禁证据（2026-09-28 本机实跑，非 CI）

| 项 | 结果 |
|---|---|
| `uv run ruff format --check .` | 95 files already formatted |
| `uv run ruff check .` | All checks passed! |
| `uv run mypy` | Success: no issues found in 19 source files |
| `uv run pytest -m "unit or contract" -q` | **114 passed**，0 skipped |
| 结构守卫（`platform/tests/test_library_independence.py` + `tests/`） | 56 passed |
| 内核反向依赖（grep `as_platform` → apps/services/testbed） | 无 |

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| C1 | TDD 顺序真实执行：先落六个测试文件并跑出红（collection error：模块不存在），再实现至绿 | 接受（AGENT.md §6 决策层强制 TDD） |
| C2 | `decide()` 纯度：`received_at` 由调用方注入，模块内无 socket / 时钟 / 全局状态 | 接受（AGENT.md §5） |
| C3 | 冲突裁决用排序键 `(action_rank, len(prefix))` 降序（BLOCK=2 > TRANSLATE=1 > FORWARD=0） | 接受：与 test-plan §5.1 用例 7 一致；副作用"更短的 block 压过更长的 translate"已写专门测试 |
| C4 | `RedisStateStore.get()` 用 `isinstance` 收窄 `bytes \| str \| None` → `bytes \| None`，未用 `# type: ignore` | 接受：真实类型收窄，符合 mypy strict |
| C5 | redis 依赖 `redis>=5.0`（锁 8.1.0）后，9 条 Redis 契约用例由 skip 变为**真正执行**（105+9 → 114 passed） | 接受：契约对两个实现都重放，符合 test-plan §5.2 |
| C6 | 命名空间默认取 `as`（而非 LLD 草案的 `as:default`），产出键 `as:{case}:{kind}:{id}` | 接受：以可验收的键格式为准（ADR-0007、test-plan §5.2 用例 6） |
| C7 | 规则层 `Action`（forward/translate/block）与判决层 `DecisionAction`（含 decline/not_found）分成两个枚举 | 接受：规则表达"配置意图"，判决表达"协议结果"，由 `decide()` 翻译 |
| C8 | `FORWARD` 的 target 在规则未指定时回落到归一化后的被叫号码 | 接受：对齐 LLD §3 |
| C9 | `ShellConfig` 增加 `poll_interval_seconds`（仅加法），draining 用注入时钟推进 | 接受：使 draining 可确定性测试 |
| C10 | `platform/src/as_platform/` 内未见 `util` / `helper` / `misc` / `common` / `tools` 一类模块名 | 接受（AGENT.md §5） |

## 缺口（不阻塞 M2a）

| # | 缺口 | 去向 |
|---|---|---|
| C11 | TLS transport 与 SIP adapter 未实现（绑定 reSIProcate） | M2b |
| C12 | `CallState` 未落（StateStore 只提供通用原语） | M3 |
| C13 | 无 `integration` / `e2e` 层用例；这两层 CI 仍带 `continue-on-error` | M2b / M3 引入时改为阻塞 |
| C14 | ADR-0020（门控）仍为 draft，门控 seam 以其为依据 | M4 控制面前完成评审 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过 |
| 门禁 | 全绿（114 passed / 0 skipped） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
