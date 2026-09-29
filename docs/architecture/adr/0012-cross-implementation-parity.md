# ADR-0012：语言无关契约 + 跨实现对拍作为转正门槛

- **Status**: accepted
- **Date**: 2026-09-30
- **Decides**: §0 账本条目 9 —— 跨实现边界：语言无关契约 + 跨实现对拍通过才允许该实现转正
- **回应 REQ**: REQ-G-2

---

## Context（背景）

本项目有一条明确的同构翻译路线：把某个用例镜像移植到 Go（`docs/plan.md` M7），`AGENT.md` §10 明确指出「Go 镜像移植是本项目收益最高的 AI 任务 —— 同构翻译 + 对拍 harness」。移植的风险不在于写不出来，而在于**写出来但不等价**：一个能跑、能过自己那套测试、却在号段匹配优先级或速率窗口边界上与原实现分岔的实现，是比"没移植"更糟的结果 —— 它把差异藏进了生产。

因此"等价"不能是口头声明，也**不能是实现内部的自证**。它只可能由一份**独立于任何实现语言**的判据来裁定。如果契约写在 Python 里（例如写成 pytest fixture），那么 Go 实现永远是在追 Python，而不是在追需求；一旦 Python 侧自己错了，两套实现会一起错，并且互相证明对方正确。

这个判断在栈选型之后变得更强，而不是更弱。[ADR-0019](0019-sip-stack-selection.md) 的 K7 记下：生产栈选定 reSIProcate 之后，若最终栈为 Go/C/C++，`platform/` 的 Python 内核退化为 seam 定义与测试 harness，**ADR-0012 的"跨实现对拍"语义从"Python vs Go 同用例"变为"新栈实现 vs `testbed/` 基线"**。也就是说，基线（而不是某一个语言的当前实现）才是锚点。

判决语义之所以能被完整地声明为数据，是因为它本来就是纯函数：`AGENT.md` §5 规定「决策模块是纯函数。产出判决的模块里不能有 socket、不能有时钟、不能有全局状态」。没有时钟意味着 `received_at` 可以作为数据传入；没有全局状态意味着速率窗口的计数器可以由调用方注入；没有 socket 意味着判决与协议无关。这三条合起来，使"给定这个号码与这份配置，判决是什么"可以被写成一份与语言无关的用例集。

## Decision（决策）

- **契约以声明式、语言无关的形式存在，落在 `testbed/contracts/`；它是数据，不是某一种语言的 fixture。** 契约回答的是需求问题，不是"Python 现在怎么做的"。
- **任何实现都必须对它重放，逐例、逐字段。** 判决契约集 `testbed/contracts/decision/cases.json` 由每个用例各自重放：`apps/translation` 取 `applies_to` 含 `translation` 或 `both` 的用例，`apps/anti-fraud` 取 `anti-fraud` 或 `both`；`both` 是共享内核语义，任何实现都必须逐字段一致。
- **契约缺失或为空必须响亮失败，不是静默跳过。** 没有被重放的契约等于没有被执行的契约。
- **跨实现对拍通过，才允许该实现转正。** M7 的 Go 镜像受 M6 把关：仅当与 Python 实现输出对输出一致时才转正（`docs/plan.md` §4 M7 行）。
- **对拍语义按 ADR-0019 的 K7：新栈实现 vs `testbed/` 基线，而不是"Python vs Go 同用例"。** 基线是锚点，某个语言的当前实现不是。
- **契约变更等于需求变更。** 新增或修改一个契约用例是接口变更：需要 ADR，且每个实现的门禁都要重跑（REQ-G-2 的文档链）。**实现无法表达某个用例，是发现了实现之间的真实差异，不是弱化该用例的理由。**
- **判决契约与 SIP 基线分工明确、互不替代**：`testbed/contracts/sip-baseline/` 抓的是**线路字节**（约束 SIP 适配层），`decision/cases.json` 写的是**期望判决**（约束判决，与协议无关）。换了 SIP 栈的实现仍需逐条回答后者。

## Consequences（后果）

### Positive（正面）

- **契约是"等价"的唯一判据。** 它不依赖审查者的记忆，也不依赖"上次移植时看过一遍"。等价性从一句声明变成一个可重复的断言。
- **转正门槛可执行、可自动化。** 新增实现不需要讨论"要不要对拍"，只需跑同一份契约；门槛在 CI 的 `contract` 层，而不是在评审会上。
- **契约让"判决书"与"协议"解耦。** 换栈（`ADR-0019`）不会波及判决语义的判定，因为判决契约里没有任何 SIP 语法。
- **契约强制实现把不确定性外置。** 时钟与计数器必须由调用方注入，这使判决在任何语言里都可确定性重放 —— 副作用是判决逻辑天然可测。

### Negative / accepted（负面 / 已接受）

- **契约的维护成本是三处同步。** 加一条判决事实要同时动契约、每个实现的重放、以及需求条目；漏一处就会出现"契约通过了但需求没跟上"或反之。接受：这三处同步正是 REQ-G-2 文档链要求的东西，不是额外负担。
- **契约变更走需求流程，比改代码慢。** 这是刻意的：契约是接口，接口变更本就该慢。
- **跨实现对拍目前只在判决层产生了证据。** SIP 侧的 E1 对拍探针 `testbed/probe/e1_baseline_probe.py` **尚未执行** —— 本环境没有 reSIProcate 的 Python 绑定，探针以**退出码 2 响亮失败并打印构建指引，不会静默 skip**。因此"跨实现对拍通过才转正"这条门槛，今天只在判决契约层可判定，在协议层仍是开放的缺口（ADR-0019 的 E1 / E4 / E5）。
- **当前只有 Python 一侧在重放。** `apps/translation` 与 `apps/anti-fraud` 的重放证明的是"两个用例对同一份契约一致"，不是"两种语言对同一份契约一致"。第一次真正的跨实现对拍要等 M7。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 契约写成 Python 测试（pytest fixture） | 契约与实现语言绑定；Go 侧必须重写一套断言，"等价"失去共同锚点。Python 侧自身出错时，两套实现会一起错并互相证明对方正确 |
| 以人工比对抓包作为等价判据 | 不可复现、不可自动化，且是一次性的：下一次移植要重做一遍，结论还因人而异 |
| 按需求文档逐条人工 review 判定等价 | 文档不是可执行的判据；"看起来一致"无法区分号段优先级这类边界行为 |
| 各实现各写各的测试，只要都绿就算等价 | 测试各自针对自己的实现写，绿只证明自洽，不证明与他实现一致 |
| 声明式语言无关契约 + 每个实现重放（本决策） | 采纳。契约是数据，锚定需求而非某个语言；对拍是转正的硬门槛 |

## Evidence（证据）

- **判决契约集已落地**：`testbed/contracts/decision/cases.json` 为 14 例 JSON 数组，每例含 `case_id` / `description` / `applies_to` / `call_id` / `calling_number` / `called_number` / `received_at` / `rules` / `translations`（translation 专用）/ `limits` 与 `counters`（anti-fraud 专用）/ `expected`。按 `applies_to` 分布：`both` 5 例（`blocked-range-is-declined`、`no-rule-matches-is-not-found`、`longest-prefix-wins`、`block-outranks-translate`、`separators-carry-no-routing-meaning`）、`translation` 3 例（`translate-baseline-number`、`translate-without-a-translation-rule-falls-back`、`translation-prefers-the-longest-prefix`）、`anti-fraud` 6 例（`forward-under-the-limit-passes-through`、`forward-over-the-limit-is-declined`、`translate-under-the-limit-is-not-rewritten`、`blocked-range-outranks-the-rate-screen`、`rate-window-prefers-the-longest-prefix`、`an-ungoverned-number-is-not-screened`）。
- **两个用例各自重放**：`apps/translation/tests/test_contract_replay.py` 与 `apps/anti-fraud/tests/test_contract_replay.py`，marker `contract`；`test_contract_case` 对 `action` / `target` / `reason_code` / `matched_rule_id` 四个字段逐字段比对，`test_the_contract_set_carries_cases_for_this_use_case` 防止过滤器匹配为空导致的空过。文件缺失或为空时 `pytest.fail` 响亮失败。
- `testbed/contracts/decision/README.md` 原文：「This directory holds the **decision contract case set**: data, not code… without reference to Python, Go or any other host language. Every implementation has to reproduce the whole set, case for case (ADR-0012).」同文件：「A Go implementation that keeps its own SIP stack still has to answer every case here identically, and that is the entry ticket for the migration.」另：「A missing `cases.json` fails the replay loudly — a contract that is not replayed is not enforced.」以及契约变更口径：「adding or changing a contract case is an interface change. It needs an ADR, and every implementation's gate has to be re-run. An implementation that cannot express a case has found a real difference between the stacks; it is not a reason to weaken the case.」
- **SIP 消息基线已落地**：`testbed/contracts/sip-baseline/` 下 `S1-basic-call`（14 条消息）、`S2-no-match-404`、`S3-policy-reject-603`、`S4-caller-cancel`（12 条）有消息文件；`S5-b2bua-two-legs`、`S6-request-uri-rewrite`、`S7a-sdp-pass-through`、`S8-route-record-route`、`S10-non-2xx-branch`、`S11-cancel-race` 仅 README（M1 裁决：S5/S6/S7a/S8 作派生基线从 S1 派生断言，S10/S11 留待 M2 probe 补，见 `docs/plan.md` §3 M1 裁决表）。
- **探针提供 E1 对拍但当前未执行**：`testbed/probe/README.md` 原文「**当前状态：两个探针都未执行。** 本环境没有 reSIProcate 的 Python 绑定（构建选项 `BUILD_PYTHON=ON` 未构建）……两个探针在绑定缺失时**以退出码 2 响亮失败并打印构建指引，不会静默 skip**。因此 E1 与 E4 在 ADR-0019 中**仍是开放的接受缺口**」。退出码表记 `2` = 「被测栈的 Python 绑定缺失（或没有可用的栈句柄工厂）—— 探针没有运行，不是通过」。
- [ADR-0019](0019-sip-stack-selection.md) §7.1 K7 原文：「**换栈后 Python 运行时角色需重新定位** …… 若最终栈为 Go/C/C++，`platform/` 的 Python 内核退化为 seam 定义与测试 harness，ADR-0012 的"跨实现对拍"语义从"Python vs Go 同用例"变为"新栈实现 vs `testbed/` 基线"」。
- `docs/plan.md` §4 里程碑 M7 原文：「Go 迁移 | 一个用例的 `go-b2bua` 镜像，commit 固定并 vendoring；跨实现对拍 | 未开始 | **受 M6 把关。** 仅当与 Python 实现输出对输出一致时才转正（ADR-0012）」。
- `AGENT.md` §6 测试策略表：「契约 | `contract` | 声明式用例，放在 `testbed/contracts/`，对**每一个**实现重放」。
- PRD REQ-G-2（改动必须贯通文档链）原文：「任何行为改动——无论大小——都必须贯通整条文档链：requirement → ADR → 设计 → 契约 → 代码 → 验收。只改代码不改上游文档是未完成。」
- 架构文档 §0 决策账本条目 9 原文：「Go 侧边界 | 镜像移植 + 语言无关契约 + 跨实现契约测试对拍」。

## Related（相关）

- [ADR-0014](0014-three-layer-testbed.md) 三层 testbed —— 契约层是本 ADR 的载体
- [ADR-0019](0019-sip-stack-selection.md) 生产 SIP 栈选型 —— K7 重定义了"对拍"的比对对象
- [ADR-0002](0002-per-usecase-process-state-redis.md) 每用例一进程 —— 决定了重放按用例切分
- [ADR-0015](0015-engineering-discipline.md) 研发模式 —— `contract` marker 与四层门禁
- [`../新系统整体架构.md`](../新系统整体架构.md) §11.4 测试平台、§10.3 镜像移植 + 对拍
- PRD REQ-G-2（改动必须贯通文档链）
- 里程碑 M7（Go 镜像 + 跨实现对拍）**未开始**，受 M6 容量研究把关
