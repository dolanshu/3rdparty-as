# `testbed/load/`

容量 harness：生成 SIP 负载，测出边界在哪。

## 要紧的那条规则

**压测走真实 socket。** POC 的 harness 直接驱动回调，绕过了 socket 与事件循环 —— 它测的是业务逻辑，
不是系统，也不能回答真实系统/O1 容量问题。M6 只用于测量当前已选定的生产 SIP 栈在真实 socket 路径下的容量与运行边界，用于 O1 与运维容量定界；除非有新的架构决策，本工作不重开 ADR-0019 的栈选型结论（ADR-0014，ADR-0019）。

## 它必须产出什么

按栈：CPS、并发会话、呼叫建立时延 —— 以及最先饱和的资源。这是 O1 与运维容量定界的输入；它不是营销
数字，在 M6 之前不发布（[`../../docs/plan.md`](../../docs/plan.md)）。

SIPp（GPL）这里可用：仅内部测试使用，绝不随产品分发。

## M6 status（2026-10-05）

**M6 工程关门**（[`docs/plan.md`](../../docs/plan.md) §4）：产品路径 harness、**D8→REQ-NF-15**、dev-host O1 正式批次 [`m6-o1-formal-report.sh`](scripts/m6-o1-formal-report.sh) 与报告 [`m6-o1-measurement-report-2026-10-05.md`](../../docs/acceptance/m6-o1-measurement-report-2026-10-05.md)。**非**对外 O1 目标发布或 M6 维护者里程碑签收。历史 `resip_probe` / SIPp smoke 仍为参考工件。

### 本切片建立的边界

- 只接受真实 socket 测量链路：负载发生器 -> 网络 socket -> 被测 SIP 栈/事件循环 -> 响应 socket。
- 任何绕过 socket 的驱动回调方案都不计入 M6 证据。
- M6 输出目标仅限 [`docs/plan.md`](../../docs/plan.md) 已批准范围：按栈给出 CPS、并发会话、建立时延，并回收[容量量级估算](../../docs/architecture/容量量级估算.md) §6 的 C1-C7 缺口。
- 在真实 socket 实测证据形成前，不在仓库中发布容量结论或阈值。

### 追溯与需求状态（D8 已关闭）

- 规则：[`AGENT.md`](../../AGENT.md) §2（M6 实测前不发布容量数字）、§6（`performance` 层必须使用真实 socket）。
- 架构决策：[`ADR-0014`](../../docs/architecture/adr/0014-three-layer-testbed.md) → [REQ-NF-15](../../docs/requirements/req-nf-15-testbed-performance.md)。
- 里程碑范围：[`docs/plan.md`](../../docs/plan.md) §4（M6）与 §5.1（O1）。
- D8 关闭：[`d8-req-nf-15-adjudication-2026-10-05.md`](../../docs/reviews/d8-req-nf-15-adjudication-2026-10-05.md)。

### 当前限制（需维护者裁决 / 后续补证）

1. REQ-NF-15 全量 test-plan（集群饱和、`performance` CI 阻塞）仍 open —— 见 test-plan §2-REQ-NF-15。
2. 当前证据仅覆盖 loopback socket 行为正确性与统计口径，不构成真实栈容量结论或 REQ 完成证据。
3. 上述单次 SIPp 3.6.0 UAS smoke 只覆盖基础 INVITE/ACK/BYE 互操作；不得据此推断 CPS、并发会话、建立时延或任何容量上限。
4. 若未接入目标侧遥测，本 harness 不能泛化给出"首个饱和目标资源"结论；该项必须在正式测量中按目标环境补证。
5. 当前实现显式 fail-closed 为 IPv4-only：IPv6 目标地址会被配置校验拒绝，避免发出未充分验证的 Via/SDP 组合或宣称双栈支持。
6. 当前 harness 不实现 SIP UDP 重传计时器，也不支持多 2xx / forked dialog 建立；这类运行画像不在支持范围内，相关结果不得表述为通用目标栈容量结论。
7. `summary.json` 中 `rates_cps` 聚合速率字段（`*_per_configured_injection_second`）使用配置注入时长做分母，不代表观测窗口 CPS；事件时间分布与峰值请看带时间戳的 `c6_windows`。`c6_windows` 的 coverage 仅来自配置注入时长、注入调度结束偏移和已观测事件偏移，不包含 worker drain 的 teardown 空闲尾段。

### 建议顺序（不越过审批边界）

1. 继续完成并校验现有 harness（真实 socket 链路、统计口径、证据可复算）。
2. 对目标 SIP 栈执行 smoke 级联调，确认目标可达、基本信令路径与失败分类稳定。
3. 接入并记录目标侧资源观测（CPU、内存、FD、网络/队列等），避免仅凭本机负载发生器侧数据下结论。
4. 明确 D8 与验收追溯：D8 未关闭不技术性阻断经维护者授权的工程推进，但会阻断 REQ 闭环与正式 acceptance 结论。
5. 在前述前提稳定后执行正式测量，并将证据回填到 [`docs/acceptance/report.md`](../../docs/acceptance/report.md) 与 M6 里程碑状态。

### 每次测量的最小证据包（模板）

- 被测对象：栈名、版本/commit、运行模式、主机规格。
- 测量配置：负载模型、并发档位、CPS 档位、呼叫时长、持续时间、端口与地址。
- 真实性证明：socket 监听/连接证据（例如 `ss` 输出）、关键命令行、原始日志路径。
- 结果原始数据：成功/失败呼叫计数、时延样本（至少可重算 p50/p95/p99）、错误码分布。
- C6 峰值分布（见[容量量级估算](../../docs/architecture/容量量级估算.md) §6）：记录带时间戳的尝试呼叫数与成功建立呼叫数；提供 1 秒和 100 秒窗口下可复算的 CPS 分布与峰值，并记录窗口聚合、时间边界及 CPS 计算方法。滑动峰值仅在 coverage 至少覆盖一个完整窗口宽度时报告；不足完整宽度时显式标记 unavailable。该序列是观测窗口速率（observed window rates）。
- summary 顶层 `rates_cps`：按已配置注入时长计算的平均值（configured-duration averages），例如 `transmitted_invites_per_configured_injection_second`。这些聚合值可包含 worker drain 期间才完成统计的会话，不等同于 C6 的时间窗速率序列。
- 饱和点观察：先触顶资源及对应观测（CPU、内存、FD、网络、队列丢弃等）。
- 复现信息：完整命令、时间戳、执行人、仓库 commit。

> 说明：以上是 M6 执行前的测量计划模板，不是容量结果，也不构成 D8 的需求裁决；C6 证据不预设目标阈值或容量数字。
