# ADR-0015：研发模式 —— 分层 TDD、ADR 制度化、四层 CI 门禁

- **Status**: accepted
- **Date**: 2026-09-30
- **Decides**: §0 账本条目 17 —— 研发模式：分层 TDD + ADR 制度化 + 四层 CI 门禁
- **回应 REQ**: REQ-G-3, REQ-G-4

---

## Context（背景）

本项目的代码有两类，它们的测试成本结构完全不同。**判决逻辑是纯函数**：`AGENT.md` §5 规定「产出判决的模块里不能有 socket、不能有时钟、不能有全局状态」—— 输入确定、无 IO、无时间依赖，TDD 在这里最便宜也最有效。而**协议 / 接入层**依赖真实 socket、真实栈行为与时序，为它写严格的红-绿-重构循环成本高、回报低：架构文档 §11.3 对此的结论是「契约测试 + 仿真集成测试为主，不做严格 TDD」。用一个统一的测试策略覆盖这两类代码，必然是其中一类被过度要求、另一类被放任。

第二个事实决定了纪律必须以机器而非自觉来落地：**本项目的代码大部分由 AI agent 产出**（`AGENT.md` §10）。`AGENT.md` §10 的第一条硬规则是「AI 生成的代码过**完全相同**的门禁。不会因为是生成的就降低标准」。人的注意力是稀缺资源，它应当集中在"这个决策对不对"，而不是"这段格式对不对"；格式、类型、分层这些必须交给门禁。

第三个事实是决策本身的半衰期。ADR 注册表开篇就写着：**「没有 ADR 的决策，是要被重新争论的决策。」** 一个没有被记录的架构决策，不会消失，只会在下一次有人碰到它时被重新讨论一遍 —— 通常是在没有原始约束信息的情况下。因此"ADR 制度化"不是文档工作，它是把决策成本一次性付清。

`AGENT.md` §6 已经给出了分层与 marker 的骨架，`AGENT.md` §9 给出了门禁的定义，`docs/plan.md` §2.4 给出了四层 CI 的表，架构文档 §11.2 / §11.3 给出了分层图与开发模式表。本 ADR 把这几处已经分散生效的纪律收成一条有后果的决策，并明确它们的边界（尤其是"哪些不在门禁内"）。

## Decision（决策）

- **① 分层测试与 marker：`unit` / `contract` / `integration` / `e2e` / `performance`。决策逻辑层强制 TDD（红 - 绿 - 重构）；协议 / 接入层以契约测试 + 仿真集成为主，不做严格 TDD。** 分层不是优先级，是不同的证据类型：单元证明判决对，契约证明各实现一致，集成证明能对仿真对等端工作，e2e 证明完整流程含错误分支，性能证明容量边界。
- **② 每个架构决策必须在 ADR 中有记录；没有 ADR 的决策等于没有发生过。** ADR 与它所授权的改动**一起**写，不事后补、不批量补；ADR 必须写明它接受的缺口（空的 consequences 节等于没分析完）；推翻一个决策意味着写一个新的 ADR，并在同一次改动里更新架构文档。
- **③ 四层 CI 门禁：① fast → ② integration → ③ e2e → ④ performance。** 本地 `make gate` 必须全绿才能提交；`--no-verify` 及其等价物禁止（`AGENT.md` §11）。本地门禁不是 CI —— 绝不要把本地重跑冒充成 CI 结果。
- **④ 不显而易见的代码必须标注 ADR**：`# See ADR-00NN`，让审稿人能从代码一步走到理由（REQ-G-3）。AST 扫描（检查这条标注）属于 CI 流水线的**额外步骤**，不在 `make gate` 四步之内，可用 `make gate-strict` 触发。
- **引入某一层首个用例的里程碑，必须同步把该层从 `continue-on-error` 改为阻塞。** 否则该层形同虚设。

## Consequences（后果）

### Positive（正面）

- **质量门禁统一。** 本地 `make gate` 与 CI 层① 跑同一组检查、同一顺序（`ruff format --check` → `ruff check` → `mypy` → pytest unit+contract），不存在"本地绿、CI 红"的第二套标准。
- **TDD 的投入落在回报最高的地方。** 判决逻辑强制 TDD；协议层不被强推，省下的成本投向契约与仿真 —— 后者才是协议层真正的风险所在。
- **决策可追溯，代码可追因。** ADR 让"为什么是这样"有据可查；`# See ADR-00NN` 让审稿人从一行不直观的代码一步走到那条 ADR，而不是自己猜。
- **AI 产出的代码与人工代码同标准。** 门禁对来源不敏感，只检查产物 —— 这正是 AI 辅助能在本项目被大规模使用的前提。
- **分层让慢测试不阻塞快反馈。** 容量层只跑 nightly / tag / 手动，不进提交门禁。

### Negative / accepted（负面 / 已接受）

- **四层门禁只有在每层真正阻塞时才有意义。** 引入某层首个用例的里程碑必须同步改为阻塞，否则该层只是装饰。当前层③ e2e 与层④ performance 仍无用例，保持 `continue-on-error`；层② integration 已随首个用例（`platform/tests/test_telemetry_export_integration.py`）改为阻塞。**这是一条需要持续执行的纪律，不是一次性动作。**
- **`make gate` 四步不含 AST 扫描。** 因此"ADR 标注"这一条在本地快速门禁里不被强制，只在 CI 额外步骤或 `make gate-strict` 中检查（REQ-G-3 明确这一归属）。接受：换本地快速反馈；代价是标错漏标在本地不会被拦。
- **分层 marker 依赖人工正确打标。** 打错层的测试会跑到错误的门禁层（例如把慢的集成测试打成 `unit`），既拖慢快层、又让集成层空过。marker 本身没有自动校验。
- **ADR 制度化的成本是实打实的。** 每个决策都要写一份带 consequences 的文档；为了赶进度而跳过它，正是"决策被重新争论"的来源。本批 ADR（0008 / 0012 / 0013 / 0014 / 0015）本身就是这条纪律的滞后产物 —— 它们在架构文档 §0 账本里早已存在，但 ADR 缺位，属于 `AGENT.md` §7「不事后补，也不批量补」的反例，记录在案。
- **`--no-verify` 被禁止意味着门禁挡住时必须修原因，而不是绕过。** 在紧急修复场景下这会增加时间成本。接受：被绕过的门禁等于没有门禁。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 所有层强制 TDD | 协议 / 接入层 TDD 成本高、回报低（架构文档 §11.3）；它会把成本从真正的高风险处（契约与仿真）挤走 |
| 所有层都不强制 TDD（测试跟着实现补） | 判决逻辑是纯函数，TDD 在那儿最便宜；放弃它等于在最便宜的地方放弃质量 |
| 只做一层 CI（全量跑一次） | 慢测试阻塞快反馈；容量跑每次提交会拖死合并，且容量结论本就不是提交门禁该管的事 |
| 只有 CI、不要本地门禁 | 反馈周期从分钟级拉到"push 之后"；且本地不绿就提交会把 CI 当成调试器 |
| 决策靠口头 / PR 描述，不强制 ADR | 没有 ADR 的决策会被重新争论（ADR 注册表开篇）；推翻一个决策时无处追责、无处对比 |
| 分层 TDD + ADR 制度化 + 四层 CI 门禁（本决策） | 采纳 |

## Evidence（证据）

- `AGENT.md` §6 测试策略表原文（逐行）：「决策逻辑 | `unit` | **强制 TDD**，红 - 绿 - 重构。TDD 的回报就在这里。」「契约 | `contract` | 声明式用例，放在 `testbed/contracts/`，对**每一个**实现重放」「协议 / 接入 | `integration` | 契约测试 + 仿真对等端；不做严格 TDD —— 成本高、回报低」「完整流程 | `e2e` | 完整呼叫 + 错误分支，含控制台」「容量 | `performance` | 只用真实 socket。绝不要靠驱动回调来测 —— 那测的是业务逻辑，不是系统（ADR-0014）」。
- `AGENT.md` §9 门禁原文：「`make gate` = `ruff format --check` → `ruff check` → `mypy` → pytest（unit/contract 层）。四步固定，AST 扫描**不在 gate 内**。」「AST 扫描（检查不显而易见的代码是否标注 ADR，对应 REQ-G-3）属于 CI 流水线**额外步骤**——在 `make gate` 之外。可用 `make gate-strict` 目标触发」「本地门禁不绿，什么都不能提交。**本地门禁不是 CI**：绝不要把本地重跑冒充成 CI 结果。」「**首个引入某层测试的里程碑必须同步把该层改为阻塞。**」
- `Makefile` 定义：`gate: lint type test-unit`，其中 `lint` = `ruff format --check .` + `ruff check .`，`type` = `uv run mypy`，`test-unit` = `uv run pytest -m "unit or contract" -q`。文件头注释：「`make gate` is the same set of checks CI layer ① runs, in the same order. Nothing is committed unless it is green here first (AGENT.md §Git rules).」
- `.github/workflows/ci.yml`：四层 job ① fast → ② integration → ③ e2e → ④ performance，文件头注释「Four-layer gate, ADR-0015: ① fast -> ② integration -> ③ e2e -> ④ performance.」层② 注释原文：「Blocking since the milestone that added the first integration case (`platform/tests/test_telemetry_export_integration.py`): a failure here is a real regression, not an empty collection. See AGENT.md §9.」层③ 与层④ 仍带 `continue-on-error: true`（层③ 注释「SKELETON EXCEPTION …… Remove in M3.」，层④ 注释「SKELETON EXCEPTION: no real-socket harness exists yet (M6).」）。
- `docs/plan.md` §2.4「四层 CI 门禁（ADR-0015）」表：① fast `unit or contract`（每次 push 和 PR）、② integration（在 ① 之后）、③ e2e（在 ② 之后）、④ performance（nightly、tag、手动）。同节进展原文：「`integration` 层首个用例已引入（`platform/tests/test_telemetry_export_integration.py`，真 socket 验证遥测导出不阻塞），CI 层② 已同步改为阻塞；层③ e2e 与层④ performance 仍无用例，保持 `continue-on-error`。」
- 架构文档 §11.3「开发模式（Q16 = A）」表原文：「**业务决策层**（`routing/engine`、`screening`）| **强制 TDD**，Red-Green-Refactor | 纯函数，TDD 收益最高、成本最低」「**协议/接入层** | 契约测试 + 仿真集成测试为主 | 不做严格 TDD，成本高收益低」「**设计决策** | **ADR 制度化** | 本次每一项决策都落 ADR」。§11.2 四层门禁图标注 ①「分钟级 · 必过」。
- 架构文档 §0 决策账本条目 17 原文：「研发模式 | 分层 TDD + ADR 制度化 + 四层 CI 门禁」。
- PRD REQ-G-3（不显而易见的代码必须标注对应 ADR）原文：「不显而易见的代码（不读上下文看不懂为什么这么写的）必须有注释指向对应的架构决策……必须在代码行末标注 `# See ADR-00NN`。审稿人从代码一步走到理由，不是自己猜。AST 扫描属于 CI 流水线额外步骤（在 `make gate` 之外）……」
- PRD REQ-G-4（`make gate` 必须全绿才能提交）原文：「`make gate` = `ruff format --check` → `ruff check` → `mypy` → pytest（unit/contract 层）。本地门禁不绿，什么都不能提交。`--no-verify` 及其等价物禁止。」
- `AGENT.md` §11 Git 规则原文：「**不跳过 hook。** `--no-verify` 及其等价物禁止。如果 hook 挡住了 commit，去修原因。」§10 第 1 条：「AI 生成的代码过**完全相同**的门禁。不会因为是生成的就降低标准。」
- `docs/architecture/adr/README.md` 规则原文：「ADR 与它所授权的改动**一起**写，不事后、不最后批量补。没有 ADR 的决策，是要被重新争论的决策。」「**ADR 必须写明它接受了什么。** …… 没有 consequences 节的 ADR 是宣传。」「**代码指向它的 ADR。** 一行不显而易见的代码带 `# See ADR-00NN`」。

## Related（相关）

- [ADR-0012](0012-cross-implementation-parity.md) 语言无关契约 —— `contract` 层的判据来源
- [ADR-0014](0014-three-layer-testbed.md) 三层 testbed —— `integration` 与 `performance` 层的载体
- [`../新系统整体架构.md`](../新系统整体架构.md) §11.2 四层 CI 门禁、§11.3 开发模式
- `AGENT.md` §6 测试策略、§9 门禁、§10 AI 辅助、§11 Git 规则（**仓库红线，本 ADR 是对它们的归档，不是替代**）
- PRD REQ-G-3（ADR 标注）、REQ-G-4（`make gate` 门禁）
- 层③ e2e 与层④ performance **仍无用例**，保持 `continue-on-error`；改阻塞的时点分别为 M3 与 M6
