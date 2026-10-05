# ADR-0014：三层 testbed；容量压测只用真实 socket；testbed 不是 v1 交付物

- **Status**: accepted
- **Date**: 2026-09-30
- **Decides**: §0 账本条目 16 —— 测试平台：testbed 三层；v1 不作交付物
- **回应 REQ**: [REQ-NF-15](../../requirements/req-nf-15-testbed-performance.md)（2026-10-05，关闭 D8；原 REQ-NF-13 误指向见 Evidence 历史备注）

---

## Context（背景）

交付环境里，S-CSCF、S-SBC 和 HSS 是**运营商的网元**，不属于我方交付物（`AGENT.md` §1）。本地没有它们，只能仿真。如果 iFC 触发链与 S-SBC 的透明桥接行为无法被仿真，那么集成测试无处可跑 —— 这一条不是"测试不够完善"，而是"没有被测对象"。

容量测量则有一个更具体的历史教训。POC 的 `CapacityDriver` **直接驱动回调**，绕过 socket 与事件循环：这样测出来的是业务逻辑的执行时间，不是系统容量。架构文档 §11.4 把它列为第一关键点：容量基线不可比，就无法判断"CPS 是否撞墙"，也就无法裁决是否需要更强的栈。换句话说，**测错对象的数字比没有数字更有害** —— 它会被当成依据来用。

`testbed/` 的定位同时由一条硬边界确定：`AGENT.md` §4 的分层图写的是 `testbed/ ──may use──▶ platform/ 研发资产，绝不做运行时依赖`，并且「内核绝不能 import 应用、服务或 testbed」，由 `platform/tests/test_library_independence.py` 强制。testbed 可以**用**内核，内核绝不能**依赖** testbed；方向是单向的。

最后一个约束来自交付范围：架构文档 §11.4 关键点 4 记「⏳ **v1 不把 testbed 当交付物**，只作研发资产；客户验收测试能力留 v1.1」。是否必须在 v1 支持客户验收测试，是**未决项 D6**（`docs/plan.md` §5.2，责任里程碑 M8），当前口径是推迟到 v1.1。

## Decision（决策）

- **`testbed/` 分三层，各层回答不同的问题：**
  - **contracts** —— 声明式契约与基线（判决用例集 `decision/cases.json`、SIP 消息基线 `sip-baseline/`）。回答"判决对不对，各实现是否一致"（[ADR-0012](0012-cross-implementation-parity.md)）。
  - **simulators** —— 仿真对等端与探针（仿真 S-SBC / IMS 网元、栈选型探针 `testbed/probe/`）。回答"AS 能不能对着一个行为像运营商对等端的东西工作"。
  - **load** —— 真实 socket 压测。回答"容量边界到底在哪"。
- **容量压测只用真实 socket。绝不用驱动回调来测** —— 驱动回调测的是业务逻辑，不是系统。字节必须真的上线，socket、事件循环、协议栈都必须在测量回路里。
- **testbed 是研发资产，绝不做运行时依赖。** 内核不 import testbed；生产镜像不带 testbed。
- **testbed 不是 v1 交付物。** 客户验收测试能力推迟到 v1.1（未决项 D6 的当前口径）。
- **压测工具可用 SIPp（GPL）**：仅内部测试使用，**绝不随产品分发**。

## Consequences（后果）

### Positive（正面）

- **契约与仿真让"等价"可断言。** 契约是数据、仿真是可执行对象，"等价"从一句判断变成一条可重复的断言（[ADR-0012](0012-cross-implementation-parity.md)）。
- **仿真网元是一等资产。** iFC 链与 S-SBC 透明桥接行为能被仿真，集成测试才有地方跑；否则 [ADR-0003](0003-s-sbc-transparent-bridge.md) 的单一 ISC 语义无法被验证，只能被相信。
- **真实 socket 压测才有容量意义。** 测量回路包含 socket 与事件循环，测出的数字才回答得了"CPS 撞墙了没有"，才能作为 O1 与栈选型的输入。
- **三层各司其职，层间不互相冒充。** 契约层不被用来冒充集成验证，压测层不被用来冒充功能正确 —— 前者会漏掉协议行为，后者会漏掉系统开销。
- **方向单一（testbed → platform）保证生产镜像干净。** 运行时不可能反向依赖研发资产。

### Negative / accepted（负面 / 已接受）

- **本 ADR 不给任何容量数字。** CPS、并发会话、建立时延全部要等 M6 与未决项 O1（`AGENT.md` §2：「M6 实测之前不发布任何容量数字」）。`testbed/load` 在本 ADR 接受时（2026-09-30）是 README 与包骨架状态；截至 2026-10-03，维护者已授权继续 M6 harness engineering，当前为 WIP，已有 loopback socket 测试与一次 user-local SIPp 3.6.0 UAS 互操作 smoke 证据，但仍无 reSIProcate/产品目标实测，也尚未开始真实目标栈容量测量。
- **testbed 自身有维护成本，且它的失效方式是静默的。** 仿真器必须跟着真实网元行为演进；一旦仿真与真实网元分岔，"仿真通过"就会变成假证据 —— 它仍然绿，但它证明的东西已经不是真的。这个成本没有自动化手段可以消除，只能靠定期对照真实网元行为复习。
- **v1 不对客户开放 testbed，意味着客户验收测试要用别的手段做。** 这是**交付边界**，必须在方案阶段说清，而不是在验收阶段发现。是否开放由 D6 裁决（M8）。
- **部分基线尚未抓取。** S5 / S6 / S7a / S8 在 M1 被裁决为"派生基线"（从 `S1-basic-call` 派生断言，不单独抓取）；S10 / S11 仅 README，留待 M2 probe 补。这两条裁决已记在 `docs/plan.md` §3 的 M1 裁决表里，不阻塞本 ADR，但意味着当前基线覆盖是不完整的。
- **探针当前没有产生证据。** `testbed/probe/` 的 E1 / E4 探针因本环境缺 reSIProcate 的 Python 绑定**未执行**（退出码 2，不是 skip）；E5 探针尚未编写。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 沿用 POC 的驱动回调 harness 测容量 | 绕过 socket 与事件循环，测的是业务逻辑不是系统；容量基线不可比，无法判断 CPS 是否撞墙，也无法裁决栈是否够用 |
| 只做契约层，不做仿真对等端 | S-CSCF / S-SBC 是运营商网元，本地没有；没有仿真，集成测试无处可跑 |
| 只做仿真，不做声明式契约 | 仿真验证"能不能跑通"，不验证"各实现是否等价"；跨实现移植失去共同锚点（ADR-0012） |
| 把 testbed 作为 v1 交付物（客户用它做验收） | 架构文档 §11.4 明确推迟到 v1.1；是否必须支持客户验收测试是未决项 D6（M8），本 ADR 不替 D6 裁决 |
| 让生产代码复用 testbed 的仿真器 / 契约加载器 | 违反 `AGENT.md` §4：testbed 是研发资产，绝不做运行时依赖；方向只能 testbed → platform |
| 三层 testbed + 真实 socket 压测 + 不作 v1 交付物（本决策） | 采纳 |

## Evidence（证据）

- `testbed/README.md` 三层表原文：「① 契约 / 单元 | `contracts/` + 每个包的 `tests/` | 决策是对的，且每个实现都一致」；「② 仿真集成 | `simulators/` | AS 能对着一个行为像运营商对等端的东西工作」；「③ 性能 | `load/` | 容量边界到底在哪」。同文件规则原文：**「压测必须走真实 socket。** 直接驱动回调的 harness 测的是业务逻辑，不是容量。」**「v1 不把 testbed 作为交付物交付。** 它是研发资产；客户验收测试能力留到 v1.1。」「这里可以用 SIPp。它是 GPL，仅**内部使用、绝不随产品分发**。」
- `testbed/load/README.md` 原文：**「压测走真实 socket。** POC 的 harness 直接驱动回调，绕过了 socket 与事件循环 —— 它测的是业务逻辑，不是系统。这种 harness 出来的数字无法回答" CPS 撞墙了没有"，因此也无法决定是否需要 Go（ADR-0014）。」同文件：「按栈：CPS、并发会话、呼叫建立时延 —— 以及最先饱和的资源。这是 O1 与 ADR-0011 的输入；它不是营销数字，在 M6 之前不发布」。历史澄清：上述引文反映的是 ADR-0014 于 2026-09-30 被接受时的 README / 栈选型语境；ADR-0019 后续已选定 reSIProcate，因此当前 M6 测量用于 O1 与运维容量规划，不在无新 ADR 的前提下重开栈选型。
- `AGENT.md` §4 分层图原文：`testbed/ ──may use──▶ platform/ 研发资产，绝不做运行时依赖`；并记「**内核绝不能 import 应用、服务或 testbed。** …… 靠 `platform/tests/test_library_independence.py` 来强制」。
- `AGENT.md` §2 非目标原文：「**M6 实测之前不发布任何容量数字。** 在真实 socket 压测测出之前，不公布任何 CPS 或并发数字。」§6 测试策略表：「容量 | `performance` | 只用真实 socket。绝不要靠驱动回调来测 —— 那测的是业务逻辑，不是系统（ADR-0014）」。
- 架构文档 §11.4「测试平台」关键点原文：1.「**性能测试必须从"驱动回调"升级到"真实 socket 压测"**：现有 `CapacityDriver` 直接调回调，绕过 socket 与事件循环，测的是业务逻辑而非系统容量。容量基线不可比，就无法判断"CPS 是否撞墙"、也就无法裁决 Go 是否够用。」2.「**仿真网元是一等资产**……iFC 链与 S-SBC 透明桥接行为必须能被仿真，否则集成测试无处可跑。」4.「⏳ **v1 不把 testbed 当交付物**，只作研发资产；客户验收测试能力留 v1.1。」
- 架构文档 §0 决策账本条目 16 原文：「测试平台 | testbed 三层；v1 不作交付物」。
- `docs/plan.md` §2.1 目录结构原文：「`testbed/` ⑥ contracts/（数据）· simulators/ · load/」。
- `docs/plan.md` §5.2 未决项 D6 原文：「testbed 是否必须在 v1 支持客户验收测试 | M8 | 架构文档把它推迟到 v1.1」；§5.1 O1 原文：「容量目标：CPS、并发会话、建立时延预算……**仍是未决项** …… M6 的实测，在 harness 跑真实 socket 之后」；§4 M6 行：「**容量研究** | 真实 socket 压测 harness；测出 CPS、并发会话、建立时延 —— 按栈分别 | 未开始 | 产出 O1 的答案；在这跑起来之前不假设任何目标」。
- `docs/plan.md` §3 M1 基线裁决表：S5 / S6 / S7a / S8 **接受为"派生基线"**（从 `S1-basic-call` 派生断言，"重复抓取不增加信息量，只增加维护面"）；S10 / S11 **接受为"M2 probe 补"**（与 PRD §2.4 已知缺口表一致）。派生断言已可执行化：`testbed/simulators/tests/test_derived_baseline.py`（marker `contract`）。
- `testbed/probe/README.md` 当前状态原文：「**当前状态：两个探针都未执行。** 本环境没有 reSIProcate 的 Python 绑定（构建选项 `BUILD_PYTHON=ON` 未构建）……以退出码 2 响亮失败并打印构建指引，不会静默 skip」；E5 探针「尚未编写，列为后续项」。
- **REQ 口径备注（历史）**：2026-09-30 接受时 `回应 REQ` 曾误写作 REQ-NF-13。PRD v0.2 中 REQ-NF-13 为 OTel（[ADR-0005](0005-observability-otel.md)）。**2026-10-05** 已新增 [REQ-NF-15](../../requirements/req-nf-15-testbed-performance.md) 并关闭 plan D8；追溯以 REQ-NF-15 为准。

## Related（相关）

- [ADR-0012](0012-cross-implementation-parity.md) 语言无关契约 + 跨实现对拍 —— 契约层（contracts）的消费者
- [ADR-0019](0019-sip-stack-selection.md) 生产 SIP 栈选型 —— `testbed/probe/` 是它的 E1 / E4 证据来源
- [ADR-0003](0003-s-sbc-transparent-bridge.md) 单一 ISC 接入语义 —— 仿真层要仿真的行为
- [ADR-0015](0015-engineering-discipline.md) 研发模式 —— `contract` / `integration` / `performance` 三个 marker 的归属层
- [`../新系统整体架构.md`](../新系统整体架构.md) §11.4 测试平台、§12.1 未决项 O1、§12.2 风险 R9
- 未决项 O1（容量目标 / M6）与 D6（testbed 是否支持客户验收测试 / M8）—— 均**未裁决**
