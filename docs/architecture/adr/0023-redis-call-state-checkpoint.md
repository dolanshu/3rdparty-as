# ADR-0023：Redis 应用层呼叫状态检查点（必要状态）

- **Status**: proposed
- **Date**: 2026-10-01
- **Decides**: 对 §0 决策 2 记录实现方向：在 Redis 中检查点保存恢复点所需的最小应用层呼叫状态；不序列化全部 `SipStack` / DUM 对象
- **回应 REQ**: REQ-NF-1, REQ-NF-2, REQ-NF-4；相关 REQ-F-1、REQ-F-2、REQ-F-5、REQ-F-8、REQ-F-9、REQ-F-11；边界 REQ-NF-6

## Context（背景）

生产 SIP 栈方向保持 reSIProcate C++；产品判决与应用逻辑保持 Python。DUM 持有活跃 SIP dialog、session 和 transaction runtime。把产品选择的业务/对话字段写进 Redis，不等于序列化或恢复这些 native runtime 对象。

REQ-NF-1 仍是硬要求，原文要求进程重启或故障时正在进行的呼叫不能断。当前 [`test-plan.md`](../../acceptance/test-plan.md) 为其规定的可执行基线较精确：基本呼叫完成 ACK 交换后 kill/restart AS，再从上游发送同 dialog BYE；新进程须把 BYE 路由到对端，且 Redis 中存在完整 dialog record。该基线只覆盖 ACK 已完成的 established dialog 和重启后到达的新 BYE，不覆盖进程崩溃时仍在途的 INVITE、CANCEL、最终响应或 2xx/ACK transaction。REQ-NF-1 的宽泛表述可能超过现行 test plan 的精确验收范围；本 ADR 不修改或缩窄该需求。

现有 D10 证据显示：跨进程 UAC `DialogSetId` 窄路径可以重建 UAC dialog set 并发起同 dialog re-INVITE，但不恢复旧 `InviteSession` 或 transaction runtime；fresh DUM 收到已建立 UAS dialog 的同 dialog BYE 时返回 481。D10 当前验收因此仍失败，UAS rehydrate 与产品 `CallController` 双腿恢复尚未解决。详见 [D10 review](../../reviews/d10-state-recovery-gap-review-2026-09-30.md) 与[恢复方案比较](../call-state-recovery-options.md)。

ADR-0002 仍为 accepted 且本 ADR 不修改它。其“会话状态全部外置”的架构措辞不能证明 default DUM 的 UAS dialog 或 `SipStack` transaction runtime 能从外置数据重建；这项架构目标与当前恢复能力之间的冲突仍待解决，不能借本 ADR 宣称已满足 REQ-NF-1。

当前 [`StateStore`](../../../platform/src/as_platform/state/store.py) 只提供 `get`、`set`、`delete`、`expire` 等通用原语；[`RedisStateStore`](../../../platform/src/as_platform/state/redis_store.py) 和其契约测试未提供双腿原子 checkpoint、owner fencing 或 durable-commit 语义。两个 app 的现有决策代码也没有呼叫状态写入：translation 的决策是纯函数；anti-fraud 的纯函数接收只读 rate-window counter 输入。它们的具体证据见本文 Evidence 和[恢复方案比较](../call-state-recovery-options.md)。

本决策处理 SIP signaling / dialog / controller 数据，不包含 RTP 或媒体状态。媒体仍由 REQ-NF-6 与 [ADR-0004](0004-media-seam.md) 排除。

## Decision（决策）

1. 记录已明确选择的**实现方向**：使用 Redis 保存恢复点所需的应用层必要呼叫状态。此选择是方向，不代表本 ADR 已接受、代码已实现或 D10 已通过。
2. checkpoint 的逻辑单元是一通呼叫的完整 controller 状态及其两条 B2BUA leg 的必要 signaling/dialog 数据。确切字段、序列化 schema、迁移策略和生命周期须在后续 HLD/LLD 中根据真实 SIP replay 冻结；checkpoint 不包含 DUM pointer、完整 `InviteSession` 对象、SipStack transaction、timer 或任意 SIP 消息。
3. 两条 leg 必须作为一个逻辑一致的 checkpoint 提交和恢复。checkpoint 带 schema version、单调递增的 generation/revision 和 owner fencing 信息。接管后旧 owner 的 fence 失效；任何旧进程都不得在新 owner 接管后继续产生 SIP side effect。恢复端只能看到一个完整且已提交的双腿 revision，不能用半套 leg 状态服务呼叫。
4. 单一 Redis value，或经验证的 Redis 原子脚本/事务，都是后续可选的物理表示；具体表示是从属实现细节，但双腿全有或全无、revision 检查与 fencing 是硬约束。当前通用 `StateStore` contract 本身不满足这些约束。
5. 对依赖 checkpoint 的 SIP side effect 必须先有对应 revision 的 durable commit acknowledgement。SIP callback 不得阻塞等待 Redis：写入在 callback 外完成，状态机只能在收到满足已定义持久性边界的确认后以非阻塞 continuation 继续。仅排入队列、写入客户端缓冲区或发起异步命令不代表 checkpoint 已提交；没有 durable acknowledgement 时不得宣称已提交，也不得执行依赖该提交的 side effect。持久性配置、故障策略与可接受的数据丢失窗口须由后续设计和验收明确。
6. checkpoint 为未来 AS 特定业务数据保留 namespaced、versioned extension payload；当前 translation payload 为空，anti-fraud rate-window counters 不放进每通 dialog checkpoint。未来如需保留经 S-CSCF 提供的 signaling context/header 值，只能保存经对端认证和 allowlist 校验后的选定值；须限制大小、保留期限和数据分类。不得保存任意完整 SIP 消息或全部 headers。重复 header 的值与顺序仅在获批的 header contract 明确要求时保留。本 ADR 不指定 header 名称，也不声称当前 app 已消费此类 header；信任与隐私边界遵循 [ADR-0016](0016-in-boundary-security.md)。

当前 restart phase 的承诺边界如下：

| 崩溃时的阶段 | 当前承诺与边界 |
|---|---|
| 空闲 | 没有活跃呼叫需要恢复；本 ADR 不为 idle 状态作呼叫连续性承诺。 |
| 入向 INVITE，durable checkpoint / decision 之前 | 不支持从未提交输入重建呼叫，不承诺无损恢复。 |
| 出向 INVITE pending、early 或 provisional | 不支持恢复 pending transaction、分支、重传或 timer；不属于当前 D10 test-plan gate。 |
| 已发送最终 2xx、等待 ACK | 不支持恢复该 transaction/ACK 处理；不属于当前 D10 test-plan gate。 |
| ACK 完成后的 established dialog | **当前 D10 必须通过的基线**：目标是从完整 Redis 双腿记录恢复并把重启后新到达的上游同 dialog BYE 路由至 peer。当前尚不能承诺成功：fresh DUM 对 UAS BYE 返回 481，须先有可工作的 recovery adapter 并通过现行验收。 |
| 崩溃时有 in-dialog request / transaction pending | 不保证恢复崩溃前未完成的请求/响应 transaction。当前 baseline 是进程重启后才发送一条新 BYE，不代表已验证 pending BYE、UPDATE 或 re-INVITE 恢复。 |
| terminal cleanup | 不把已终结呼叫重新服务为 active call；终态标记、幂等清理、TTL 与 owner fence 的交互仍须实现并测试。 |

INVITE/CANCEL/final-response/2xx-ACK 与其他崩溃时在途 transaction 不是当前 D10 可执行验收的一部分，也不在本 ADR 中承诺恢复。若产品要求这些阶段，须单独审查并扩展 requirement 与 test plan；REQ-NF-1 的宽泛原文仍保持不变。

## Consequences（后果）

### Positive（正面）

- 在维持 reSIProcate C++ 和 Python 产品逻辑边界的同时，选择了与 ADR-0002 一致的 Redis 方向，不把“进程无状态”误解成序列化整个 SIP 栈。
- 把呼叫 checkpoint 与反诈 rate-window aggregate state、PostgreSQL governance state 分开，避免把非呼叫级计数复制到每一通呼叫记录。
- 为未来经治理允许的 AS 特定数据和 selected signaling context 留下有界扩展点。

### Negative / accepted（负面 / 已接受）

- **D10 仍 blocked，REQ-NF-1 未通过。** 当前 D10 acceptance 直到完整 Redis dialog record 存在且重启后的同 dialog BYE 被路由到 peer 才能通过；fresh DUM 当前返回 481。方向选择不替代 recovery adapter、产品 CallController 双腿重建或验收。
- UAS dialog rehydrate 尚无已验证实现。SipStack in-flight transaction、DUM session/timer 恢复同样未解决；当前 ADR 不承诺恢复它们。
- 双腿原子提交、durability/write-before-side-effect、generation 与 fencing、非阻塞持久化 continuation、故障/清理策略都需要新增设计和行为测试。现有 `StateStore` contract 不能单独证明这些语义。
- ADR-0002 的“所有会话状态外置”措辞与 default DUM UAS/transaction runtime 无法从当前 Redis 记录恢复之间仍有待决冲突。ADR-0002 保持 accepted / unchanged；本 ADR 不 supersede 它，也不静默缩窄 REQ-NF-1。
- pending INVITE/CANCEL/final response/2xx-ACK recovery 超出现行 D10 test-plan；更宽的产品保证需要单独 requirement/test-plan review。
- Redis durable commit 的故障模型、确认语义和 RPO 尚未定义。若配置的 Redis acknowledgement 不代表所需持久性，产品不得把它当作已提交检查点。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 只把状态留在当前进程 | 进程重启会丢失应用状态，不满足 REQ-NF-1 的目标；ADR-0002 已排除此运行态模型。 |
| 用 PostgreSQL 保存必要呼叫状态 | 本次明确选择 Redis 方向；PostgreSQL 只作为未来实现参考，需另行评审 ADR-0002 的时延/运行态存储约束，且事务型存储也不会重建 DUM/UAS/transaction runtime。 |
| 序列化全部 reSIProcate `SipStack` / DUM 对象 | 当前没有此类可验证恢复契约；对象 dump 也不能自动定义 timer、transport、owner handoff 和版本兼容语义。本 ADR 不把它设为目标。 |
| 以支持持久化的其他 SIP 产品替换 reSIProcate | SIP 栈选择由 ADR-0019 决定。替换需要独立架构裁决与产品语义/部署评估，不是本 ADR 的实现选项。 |

## Evidence（证据）

- [`docs/acceptance/test-plan.md`](../../acceptance/test-plan.md) §2 REQ-NF-1：ACK 交换完成后 kill/restart、上游 BYE 路由到对端、Redis 中存在完整 dialog record。
- [D10 review](../../reviews/d10-state-recovery-gap-review-2026-09-30.md)：记录了 UAC `DialogSetId` 窄 re-INVITE probe 通过、fresh DUM UAS 同 dialog BYE 返回 481、Redis 完整记录及产品 controller mapping 尚未验证。
- [translation decision](../../../apps/translation/src/as_translation/decision.py) 与 [translation unit tests](../../../apps/translation/tests/test_decision.py)：纯决策输入/输出，无 app-owned per-call checkpoint 或 `StateStore` 写入。
- [anti-fraud decision](../../../apps/anti-fraud/src/as_anti_fraud/decision.py) 与 [anti-fraud unit tests](../../../apps/anti-fraud/tests/test_decision.py)：`counters` 是只读 `Mapping[str, int]` 输入；测试断言函数不修改 counters；未发现 app source/test 对 `StateStore` 的接线。
- [`StateStore` protocol](../../../platform/src/as_platform/state/store.py)、[`RedisStateStore`](../../../platform/src/as_platform/state/redis_store.py) 与 [store contract tests](../../../platform/tests/test_state_store_contract.py)：现有 API 和契约覆盖通用键值/TTL/idempotent 单键写，不覆盖双腿事务、owner fencing 或 durable acknowledgement。
- [ADR-0016](0016-in-boundary-security.md) 建立网外部署下的 peer authentication、allowlist、payload/privacy 边界；[ADR-0004](0004-media-seam.md) 与 REQ-NF-6 排除媒体。

## Related（相关）

- [`../新系统整体架构.md`](../新系统整体架构.md) §0、§4.1、§7
- [ADR-0002](0002-per-usecase-process-state-redis.md)：accepted 的每用例一进程 + Redis 运行态方向；本 ADR 不修改
- [ADR-0019](0019-sip-stack-selection.md)：reSIProcate 生产 SIP 栈
- [ADR-0022](0022-resiprocate-b2bua-control.md)：proposed 的 DUM/CallController 边界
- [ADR-0016](0016-in-boundary-security.md)、[ADR-0004](0004-media-seam.md)
- [呼叫状态恢复方案比较](../call-state-recovery-options.md)
- [D10 状态恢复缺口评审](../../reviews/d10-state-recovery-gap-review-2026-09-30.md)