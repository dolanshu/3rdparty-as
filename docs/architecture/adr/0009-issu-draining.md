# ADR-0009：ISSU 是 draining，不是在途状态迁移

- **Status**: accepted
- **Date**: 2026-09-30
- **Decides**: §0 账本 §6.2 —— ISSU 只能走 draining：摘流 → 等在途呼叫归零 → 退出，不迁移在途状态
- **回应 REQ**: REQ-NF-1, REQ-NF-4

---

## Context（背景）

ADR-0002 已经裁决了运行时模型：**一个用例一个进程，会话状态、对话状态、caller_state 全部外置到 Redis，进程自身不持有任何需要持久化的会话级状态**。这条裁决有一个直接推论，而且它比看上去更强 —— 既然进程不持有会话状态，升级就**不需要**把在途呼叫的状态从旧进程搬到新进程。状态搬移这一整类问题（序列化格式、版本兼容、搬运窗口内的一致性）根本不存在。

但推论的另一半同样必须说清，而这一半经常被省掉：**"不迁移状态"不等于"可以立刻杀进程"。** 状态在 Redis 里，不等于呼叫不在这个进程上。进程此刻仍然承载着若干在途呼叫 —— 它们的事务机、定时器、socket 与对话上下文都活在这个进程里，只是它们的**可恢复事实**存在 Redis 中。收到 `SIGTERM` 立刻退出，这些呼叫就断了：不是"状态丢了"，而是"没有人继续替这通呼叫发下一个 SIP 消息"。掉呼叫的损害与状态是否外置无关。ADR-0010 把这句话写得很直白：「进程里没有状态，不代表进程上没有在途呼叫」。

因此 ISSU 需要的是一个**排空**语义，而不是一个**迁移**语义：

1. **停止接收新请求**（摘流）—— 新请求去新版本进程；
2. **存量呼叫继续在原进程上跑完** —— 它们不需要被搬走，只需要不被打断；
3. **`active_calls` 归零后退出** —— 进程上没有呼叫了，退出不再损害任何东西。

架构文档 §6.2 把这一结论的前提事实写死了：「SIP 事务/对话状态**全在进程内存**、无序列化与迁移接口 —— 因此"把在途呼叫无缝移交给新版本"在架构上**不成立**。ISSU 只能走 **draining**。」注意这句话的两段是分开成立的：前半段（状态在进程内、无法迁移）是**当前栈的事实**，它可能随栈选型改变；后半段（因此 draining）是**在当前事实下的结论**。这意味着本决策不是永恒的 —— 它带一个明确的复核触发条件（见 Decision 第 5 条与 ADR-0019 §7 K6）。

## Decision（决策）

- **① 升级 / 重启一律走 draining。** 停止接收新请求 → 存量呼叫继续在原进程跑完 → `active_calls` 归零后退出。不存在"就地换成新版本继续服务"的路径，也不存在"收到终止信号立即退出"的路径。REQ-NF-4 的要求（「新请求路由到新版本进程，存量呼叫继续完成」）正是这一语义的需求侧表述。
- **② 机制落在两个地方，各管一段。** 编排侧：`preStop` hook + 延长的 `terminationGracePeriodSeconds`（已在 `deploy/helm/templates/deployment.yaml` 落地）—— `preStop` 先给 Endpoint 摘除的传播留出时间，避免"已经不接新流了但 LB 还在往这边发"；`terminationGracePeriodSeconds` 界定这次等待的上界，超时后由 K8s 发 `SIGKILL`。内核侧：由 `ProcessShell` 表达 draining —— `request_terminate()` 标记"不再接收新请求"，`run_until_drained()` 轮询 `active_calls` 直到归零或超时。二者是同一语义的上下半段：编排给时间窗，进程给排空行为。
- **③ 缩容同样受此约束。** 缩容是一次计划内的实例消失，与 ISSU 面对的是同一个约束 —— ADR-0010 的缩容保护控制器与之协同：HPA 决定"要不要缩"，控制器只挑选**在途呼叫数为零**的实例作为候选，摘除动作本身仍是 draining。已在 draining 中的实例不再被重复选为候选。
- **④ 必须有一个硬超时。** 无限等待等于让一个 Pod 永远活着（长呼叫、僵死呼叫、对端不挂断都会造成这种情况），发布流程因此被永久卡住。超时后强制退出。**超时值属运维参数，不在本 ADR 给容量或时间结论** —— 它进 `values.yaml`，与呼叫时长分布绑定，而不由架构推定。超时强制退出意味着掉呼叫，因此**必须告警**：这不是一个可以静默发生的降级。
- **⑤ 复核条款：若状态可序列化，本决策可被推翻，但不得静默改变。** 若未来生产栈支持"对话/事务状态的序列化与恢复"（ADR-0019 §4 E5 探针验证通过），在途状态迁移就从"架构上不成立"变为"可评估的备选"，届时 ISSU 可重新评估为在途状态迁移。**推翻本条必须新写一个 ADR**（按 ADR 注册表规则：推翻一个决策意味着写一个新的 ADR，并在同一次改动里更新架构文档），不得在实现里悄悄改成迁移语义。ADR-0019 §7 K6 已登记这条连带后果与复核触发条件。

## Consequences（后果）

### Positive（正面）

- **升级不掉呼叫。** 掉呼叫的条件从"进程被终止"变成"进程上没有呼叫时被终止"，逐进程判据直接对准要防止的损害。REQ-NF-1（进程重启不丢会话）与 REQ-NF-4（ISSU 不掉呼叫）在本语义下同时被满足。
- **与无状态模型一致，实现简单。** draining 不需要序列化格式、不需要版本兼容矩阵、不需要状态搬运窗口内的一致性保证 —— 这些正是 ADR-0002 排除掉的复杂度。内核侧只需一个"拒绝新请求 + 等领域计数器归零"的循环。
- **判定可测。** `ProcessShell` 注入时钟与 `active_calls`，draining 的三种结局（正常归零、超时强制、拒绝新请求）在没有集群的 CI 里就能被覆盖。

### Negative / accepted（负面 / 已接受）

- **长呼叫会拖长发布窗口。** 一次滚动升级的耗时下限是存量呼叫的最长剩余时长。长通话占比高的场景下，发布窗口会显著拉长。这与架构文档 §6.2「升级窗口 ≈ 存量呼叫最长时长」以及风险 R3（ISSU 窗口过长）是同一件事，缓解手段（呼叫时长硬顶 + 强制释放策略）属运维策略，不在本 ADR 定。
- **硬超时兜底意味着超时就掉呼叫。** 超时不是"优雅降级"，它是"放弃等待并接受损失"。因此超时必须告警而不是只写一条日志 —— 静默掉呼叫比掉呼叫本身更糟，它会让容量与体验问题长期不可见。
- **draining 期间容量实际下降。** 正在排空的副本不再接新流但仍占着副本数，新版本副本尚未全部就绪时，有效容量低于标称副本数。**具体数值属运维参数，本 ADR 不涉及任何容量结论**（`AGENT.md` §2：M6 实测之前不发布任何容量数字）。
- **本决策带一个未决的复核触发条件。** E5（状态外置 / 序列化）的探针尚未编写，ADR-0019 §7 已明确「E5 目前连可执行的判定都没有」。在此之前，"能否升级为在途状态迁移"这个问题无法被回答，本决策因此是"在当前事实下的结论"，不是终局结论。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 在途状态迁移（把在途呼叫交给新版本进程） | 当前栈不支持状态序列化与迁移 —— 架构文档 §6.2 的前提事实；ADR-0019 §4 E5 仍为"纸面通过 / 待 probe 验证"，且 §7 明确 E5 探针尚未编写。ADR-0002 已排除这一复杂度。将来若 E5 验证通过，按 Decision ⑤ 走新 ADR 推翻，不在此刻采纳 |
| 滚动重启强杀（收到 SIGTERM 立即退出） | 掉在途呼叫。状态在 Redis 中存活只保证"状态不丢"，不保证"呼叫不断" —— 没有人继续为这通呼叫发下一个 SIP 消息 |
| 双版本并行，由 LB 切流但不摘存量 | 这不是另一个方案，而是本决策的另一种说法：切流负责"新请求去新版本"，存量部分仍然只能靠 draining 归零，否则旧版本进程永远不能退出 |
| 进程内自杀式退出（收到缩容信号即退出） | ADR-0010 已明确否决：不等存量归零就退出，等于主动掉呼叫 |

## Evidence（证据）

- ADR-0002 已裁决运行时模型为"每用例一进程 + 状态外置 Redis"，并写明「ISSU（In-Service Upgrade）只需 draining（摘流、等存量呼叫归零），不需要状态迁移」以及「优雅下线 draining 需要 preStop hook + 延长 terminationGracePeriodSeconds」。
- 架构文档 §6.2 In-Service Upgrade（ISSU）：前提事实（状态全在进程内存、无序列化与迁移接口 → 无缝移交不成立、只能 draining）；编排方式（k8s RollingUpdate + `preStop` draining + 延长 `terminationGracePeriodSeconds` + PDB）；约束表记「升级窗口 ≈ 存量呼叫最长时长，grace window 可配；需定义"超时强制释放"策略与呼叫时长硬顶」。风险 R3（ISSU 窗口过长）缓解列为「呼叫时长硬顶 + 强制释放策略」。
- 内核实现：`platform/src/as_platform/shell.py` 的 `ProcessShell` —— `ShellConfig.drain_timeout_seconds`（排空上界）、`request_terminate()`（标记停止接收新请求）、`accepts_new_requests()`、`run_until_drained()`（轮询 `active_calls` 至归零或超时；注释「Force the exit: waiting forever would keep a Pod alive with calls that will never finish. See ADR-0009.」）。
- 入口实现：`platform/src/as_platform/__main__.py` —— 注册 `SIGTERM` / `SIGINT` 处理器调用 `shell.request_terminate()`（注释「Refuse new work before draining existing calls. See ADR-0009.」），排空完成返回退出码 0，超时返回非 0。
- 编排实现：`deploy/helm/templates/deployment.yaml` —— `terminationGracePeriodSeconds: {{ $.Values.draining.terminationGracePeriodSeconds }}`，注释「ISSU is draining, not state migration (ADR-0009) …… This window bounds that wait before SIGKILL; it is a timeout, not a capacity figure.」；`lifecycle.preStop.exec` 执行 `sleep {{ $.Values.draining.preStopSleepSeconds }}`，注释「Gives the Endpoint removal time to propagate before the process stops accepting new calls (ADR-0009). The draining wait itself is done by the process shell.」
- 实测：`docs/acceptance/report.md` M5 容器镜像一节 —— 「容器内 `docker stop`（SIGTERM）→ 停止接新请求 → 排空 → **退出码 0**，ADR-0009 的 draining 在镜像里真的能工作」；Chart 渲染出 `terminationGracePeriodSeconds: 300` 与 `preStop` 均在。同节记未完成项：真实 Kubernetes 集群上的滚动升级与缩容验证（本机无集群），列为 M5 剩余项。
- 复核触发条件：ADR-0019 §7 K6 —— 「可能连带重开 ADR-0005 / 0009 / 0010 …… 若状态可序列化，ADR-0009 可从 draining 升级为状态迁移」；§7 接受缺口第 3 条记 E5 未验证。

## Related（相关）

- [ADR-0002](0002-per-usecase-process-state-redis.md) 运行时模型：无状态进程使 draining 成为可能，不需要状态迁移
- [ADR-0010](0010-autoscaling-hpa-downscale-guard.md) 扩缩容：缩容保护控制器只挑选零在途呼叫的实例，摘除动作走本 ADR 的 draining
- [ADR-0019](0019-sip-stack-selection.md) §4 E5（状态外置）与 §7 K6（连带复核 ADR-0005/0009/0010）—— 本决策的复核触发条件
- [`../../../deploy/docker/README.md`](../../../deploy/docker/README.md) 容器镜像：入口点与 SIGTERM 行为
- [`../新系统整体架构.md`](../新系统整体架构.md) §6.2 In-Service Upgrade（ISSU）
