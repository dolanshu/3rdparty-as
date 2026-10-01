# 呼叫状态恢复方案比较（联合决策输入）

- **状态：** 研究比较；Redis 应用层必要状态 checkpoint 已由维护者明确选为方向，但 ADR-0023 仍 proposed、未接受且未实现
- **日期：** 2026-10-01
- **范围：** 在保留 reSIProcate 生产栈方向下，比较满足 REQ-NF-1 的必要呼叫状态恢复方式
- **在线来源访问日期：** 2026-10-01

本文记录所选方向的边界和未来实现参考，不重新开放存储方向：当前方向是 Redis 中的应用层必要状态 checkpoint，不序列化完整 DUM / `SipStack` 对象。PostgreSQL、完整 native snapshot/replication 与其他 SIP 产品仅是未来实现参考，不是与 Redis 并列的当前提案，也不是已选方案。ADR-0023 仍为 proposed，方向尚未实现或正式接受。产品目标是恢复**明确支持的恢复点**所需状态，不承诺当前能恢复全部 dialog 或 transaction runtime。REQ-NF-1 保持硬要求；D10 仍未解决，并阻塞 M7/M8。参见[需求](../requirements/prd.md)、[D10 评审记录](../reviews/d10-state-recovery-gap-review-2026-09-30.md)、[ADR-0002](adr/0002-per-usecase-process-state-redis.md)、[提议中的 ADR-0022](adr/0022-resiprocate-b2bua-control.md)和[提议中的 ADR-0023](adr/0023-redis-call-state-checkpoint.md)。

## 1. 标准与产品边界

RFC 3261 把 dialog 与 transaction 定义为不同的状态机。Dialog 标识由 Call-ID、local tag 和 remote tag 组成；dialog state 还包括双方 sequence number、route set 和 remote target 等。B2BUA 的两条腿是独立 dialogs，不能用单一 Call-ID 或仅有业务映射替代各腿状态。[S1]

INVITE/CANCEL/final response 的相关性、重传、ACK 和 transaction timer 属于 transaction 行为。RFC 6026 进一步要求 INVITE 2xx 相关 transaction state 在规定的 Accepted 状态和时限内继续参与处理。RFC 规定在线 SIP 行为，**没有规定进程崩溃后的持久化格式、状态复制算法或高可用实现**；这些是产品设计与验收选项，不应误称为 RFC 已要求 Redis 或某个特定存储。[S1][S2]

本项目的实测边界是：reSIProcate 1.14.0 中，跨两个 OS 进程的 UAC `makeInviteSession(..., DialogSetId, ...)` 路径可在应用恢复 Call-ID、tags、Contact/remote target、Route 和 CSeq 后发出同 dialog re-INVITE 并收到 200。它没有恢复原 `InviteSession` 或 transaction runtime。相反，真实建立过的 UAS dialog 在旧进程退出后由 fresh DUM 收到同 dialog BYE，实际返回 481；源码路径按 `DialogSetId` 查 DUM 私有 map，找不到即返回 481。公开头文件中没有找到 UAS rehydrate 或 SipStack transaction snapshot/restore API。两进程双腿测试只通过了 UAC 重关联，不覆盖 UAS、pending transaction 或 fencing。[S3][D1]

**D10 范围说明。** 当前 D10/REQ-NF-1 [验收项](../acceptance/test-plan.md)严格限定为 ACK 已交换、INVITE transaction 已完成后的 established-dialog 恢复：建立基本两腿呼叫、kill 并重启 AS、从上游发送同一 dialog 的 BYE，验证新进程恢复 UAS/UAC 映射、将该 BYE 经已建立的 UAC leg 路由到对端，且 Redis 保留完整 dialog 记录。新进程处理的是新的 BYE transaction；当前验收不要求恢复已完成的 INVITE transaction，也不恢复崩溃时仍在途的 transaction。UAC `DialogSetId` re-INVITE 探针只是探索性证据，不是当前 test plan 的验收步骤。本基线也不包括重启后由下游/UAC 发起的 in-dialog re-INVITE 或 BYE。REQ-NF-1 仍是硬要求。本 AS 不承载也不锚定 RTP（REQ-NF-6/ADR-0004），该验收不测试媒体中断或恢复。fresh DUM 对同一 dialog 的 BYE 返回 481，证明 SIP dialog/control-state recovery 未达到当前基线，不证明 RTP 中断。此说明不引入媒体 blocker，也不新增媒体需求。矩阵中的“在途 transaction”列仅比较当前基线之外的可选扩展能力；任何将这些行为纳入 gate 的改动都须单独扩展/修改 requirement 与 test plan，并获维护者明确批准。

## 2. 选项矩阵

**决策地位：** Redis checkpoint 是本次明确选定的方向，尚未由 ADR 接受或实现。PostgreSQL 与完整 native recovery 是未选择的未来实现参考；OpenSIPS / Kamailio 是外部产品参考；UAC `DialogSetId` 是局部 probe 证据；active/standby 是 ownership pattern，不是另一项存储选择。下表用于比较后续实现细节，不表示这些方案是平级的当前提案。

| 模式 | 已建立 UAC dialog | 已建立 UAS dialog | 在途 transaction（当前 D10 基线外的可选扩展能力） | 两腿一致性与持久性 | 对本产品的适配与成本 |
|---|---|---|---|---|---|
| 应用层必要状态 checkpoint 到 Redis | 可由应用快照配合窄重关联路径尝试；目前只有 UAC 探针证据 | 当前默认 DUM 路径不行，BYE 返回 481；仍需 UAS rehydrate 扩展/机制 | 不由 dialog checkpoint 自动恢复；对当前基线外的 pending transaction 需另行恢复或安全收敛 | `MULTI/EXEC` 或 Lua 可组成一次 Redis 原子执行，但多键设计、命令错误处理、两腿版本和故障切换语义仍需设计；AOF/RDB 与异步复制带来不同丢失窗口 | 延续 ADR-0002 的存储方向，但需要写入边界、恢复适配、双腿原子检查点与 owner fencing；成本中高 [S4][S5] |
| 应用层必要状态 checkpoint 到事务型存储（如 PostgreSQL） | 同上：数据库不等于 DUM 重建 API | 同上：仍需 UAS 恢复机制 | 同上：当前基线不要求恢复崩溃前的 transaction；若扩展范围，数据库本身也不恢复 SipStack transaction state | 单个数据库事务可把多腿状态作为一个原子可见单元提交；同步复制可提高确认写的持久性，但会增加提交等待/可用性约束 | 可作一致性候选；与 ADR-0002 对高并发会话存储和时延的既有判断有张力，需另行评估，不能在本比较中改写该 ADR [S6] |
| 完整 protocol-native `SipStack` + DUM snapshot/replication | 目标上可覆盖，但当前未找到公开恢复 API | 目标上可覆盖，但当前无公开 UAS rehydrate API | 只有同时覆盖 transaction state、timers、分支和 DUM usages 才可能覆盖；目前未证明 | 若实现需定义完整状态一致性、timer 重建、socket/owner handoff 与版本兼容；不等于把对象 dump 到文件/Redis | 理论覆盖最完整，当前是自定义 DUM/SipStack 扩展或 fork 的研究方向；工程、协议正确性和长期升级成本最高 [S3] |
| DUM 重启 + UAC `DialogSetId` 重关联 | 已有窄 re-INVITE 探针通过 | 不覆盖；默认 fresh DUM 对同 dialog BYE 返回 481 | 不覆盖 SipStack 或原 transaction | 应用必须另存 UAC dialog 字段；未证明双腿原子快照、owner fencing 或 transaction 安全 | 可作为 UAC 恢复子机制的证据，不满足 REQ-NF-1 的完整目标 [S3][D1] |
| OpenSIPS dialog/B2B persistence 与 clusterer | 官方模块可持久化/复制 dialog 或 UAC B2B entity 状态 | `b2b_entities` 文档描述 UAS server entity，且支持数据库及 clusterer replication/restart persistence | OpenSIPS TM 文档描述 anycast transaction reply 路由回创建 transaction 的 owner；未证明 transaction 可跨进程故障恢复 | dialog DB、clusterer event sync、seed 节点和 B2B entity/logic DB 模式各有配置；官方文档未证明两腿 checkpoint 与 TM transaction 跨故障原子恢复 | 可作为已实现 SIP 产品的状态管理参考；采用其组件意味着另行评估栈、B2BUA 语义和集成，**不是** reSIProcate 替换建议 [S7] |
| Kamailio dialog DB + DMQ | `dialog` 模块可存储/加载 proxy dialog 记录；不是本产品两条独立 B2BUA leg 的证明 | 同左；未证明等同于 reSIProcate UAS rehydrate | TM 处理 transaction state；官方 dialog DMQ 说明不等于 transaction restore | DB 有 realtime、delayed、shutdown 模式；early/deleted 状态不写入 DB。DMQ 只同步足够维护 profile 的基础 dialog 信息，且非原始 proxy 节点不能发 in-dialog request | 可供对比数据结构、恢复入口和归属限制；不能据此宣称完整 stateful B2BUA restart recovery [S8] |
| SIP 层 active/standby 状态权威 | 取决于底层 dialog/B2B checkpoint 能力 | 取决于底层能力 | 本身不恢复 transaction | 可通过单一 active owner、backup 和显式 takeover 降低双主风险；仍需状态同步、fencing、peer routing 与 transaction 边界 | 是 ownership pattern，不是存储/协议恢复实现。OpenSIPS clusterer 的 sharing tag 展示 active/backup 模式；采用不同 SIP server 是单独架构裁决 [S7] |

表中“可覆盖”只表示官方文档/API 或当前探针呈现的功能边界，不代表这些替代产品满足本项目全部 RFC、REQ-NF-1 或 E1 验收。

## 3. 未来实现选项的证据与代价

### 3.1 Redis 应用层必要状态 checkpoint

这是已选方向的未来实现约束，不是当前代码能力：后续适配器需把 `CallController` 必要业务状态和每腿必要 dialog 字段写入 Redis，不保存 DUM pointer、`InviteSession` 对象或 transaction timer。checkpoint 应随已定义的 SIP/session 状态迁移更新，并明确每个外部 SIP side effect 与 durable acknowledgement 的顺序；否则进程可能在消息已发送但状态尚未持久化时崩溃。双腿须作为一个逻辑快照，以单一值或经验证的 Redis 原子操作提交，并通过 generation/owner fencing 拒绝旧 owner 与半套快照。[S4]

Redis 官方文档说明 `MULTI/EXEC` 内命令以单一隔离操作顺序执行，但运行时某条命令错误不会回滚队列中其他成功命令；Lua 脚本能以原子执行方式组合多 key 操作。故“使用 Redis”不自动等于“业务上的双腿全有或全无”：键布局、写入验证和恢复时版本检查仍要测试。持久性也需单独定：RDB 快照可能丢失最近数分钟写入；AOF `appendfsync everysec` 官方说明存在约一秒写入窗口，`always` 更慢；Redis 默认异步复制，Sentinel failover 可能丢失已确认但未复制的写入，`WAIT` 也不提供强一致 CP 保证。[S4][S5]

在恢复路径中还需明确：写失败如何阻止依赖该 checkpoint 的 INVITE/CANCEL/最终响应、callback 如何保持非阻塞、状态机如何等候 durable barrier 而不在 SIP callback 中阻塞、Redis failover 后旧 owner 如何被 fence、active call 的 TTL 如何避免早于终态过期。只收到异步写入排队确认不能标为 committed。它与 ADR-0002 的 runtime store 方向一致，但 ADR-0002 不等于已接受 protocol recovery 语义，也不等于当前 StateStore 已有这些能力。

### 3.2 事务型存储 checkpoint

例如 PostgreSQL 可在一个 SQL transaction 中写入逻辑 call 与两条 leg 记录，使提交在其他事务看来为原子单元。它仍只存储应用选定的数据，不会自动创建 reSIProcate UAS session 或 SipStack transaction。PostgreSQL streaming replication 默认异步；同步提交可等待 standby 确认，但会增加至少与主备往返相关的响应时延，也会受同步副本可用性影响。[S6]

对本产品的主要问题是成本与既有架构：ADR-0002 已接受 Redis 作为运行态数据方向，并记录 PostgreSQL 对高并发会话读写/时延的顾虑。把 PostgreSQL 作为恢复 checkpoint 候选是需要单独评审的产品选择，而不是本研究对 ADR-0002 的更改。也需设计数据库不可用时的信令行为、HA failover 的 RPO、连接池和迁移/备份。

### 3.3 reSIProcate 原生恢复与窄 UAC hook

在固定的 reSIProcate 1.14.0 commit 中，公开 `DialogUsageManager` overload `makeInviteSession(..., DialogSetId, ...)` 用给定 Call-ID/local tag 创建 UAC `DialogSet`，不是复活旧 `InviteSession`。同一类的 `mDialogSetMap` 是 private；`processRequest()` 对带 To-tag 但找不到 dialog set 的非 ACK 请求发 481。`SipStack` public header 提供 process、transport、send、shutdown 等接口，其 transaction controller 是内部成员；所查 public headers 未见 snapshot/restore 接口。这个源码查找不能证明自定义扩展绝对不可能，但说明当前 public API 证据不足以承诺 UAS 或 transaction recovery。[S3]

现有 UAC 探针支持一个有限选项：恢复足以构造新的 UAC dialog set 的字段，再发起同 dialog re-INVITE 重新关联。它不能覆盖 UAS BYE、正在等待响应的 INVITE/CANCEL、2xx/ACK 重传处理、原 DUM session 句柄或产品 CallController 的配对映射。因此只能作为更完整恢复设计中的一个机制候选，不能作为 D10 通过证据。[S3][D1]

### 3.4 SIP server 持久化/复制参考

OpenSIPS 3.6 的 `dialog` 模块支持 database mode，并通过 clusterer 的 binary replication 同步 dialog create/update/delete；启动时可从 seed node 同步。文档也把本地 DB 定位为所有 cluster nodes 均停机时的 dialog restart-persistence fallback，并说明 DB 中未在 cluster sync 中重新确认的 dialog 会被丢弃。OpenSIPS 的 `b2b_entities` 文档明确记录 UAS server entity 与 UAC client entity，可用 `cluster_id` 复制 B2B entities 并支持 clusterer sync restart persistence；`b2b_logic` 有自己的 DB mode/logic state。对应代价是 clusterer/proto_bin、seed 与能力同步、DB write-through/write-back 策略和对 SIP 行为的整体迁移验证。当前官方文档对 TM anycast 的描述是把异节点收到的响应送回创建 transaction 的 owner；这不是将该 transaction 迁移到新的 owner 的承诺。这里也未发现针对本产品的完整 transaction 恢复证明。[S7]

Kamailio 6.1 的 `dialog` 模块支持 DB storage/load，字段包括 dialog tags、双方 CSeq、route set、Contact 和状态；`db_mode` 有 realtime、delayed、shutdown 选项，early 与 deleted 状态不写入 DB。其 `enable_dmq` 选项的官方说明非常具体：DMQ 只共享足以同步 profiles 的基本 dialog 信息，不能在非原始 proxy 节点发送 in-dialog request。故此功能可比较 DB restoration/cluster ownership，却不能作为完整 UAS+UAC 双腿 B2BUA 或在途 TM transaction 恢复证据。Kamailio 的 DMQ 由各 peer 定义需复制的数据；DMQ 本身不是任意 SIP transaction snapshot。[S8]

以上产品文档是参考模式，不改变本仓库已选定的 reSIProcate 栈。直接选择 OpenSIPS 或 Kamailio、或新增 SIP server 作为外部状态权威，都需要单独讨论它们与现有 Python `CallController`、产品需求、部署、安全和运维边界的适配。

### 3.5 Active/standby 状态权威

这是与“所有副本都可接管”不同的 ownership 模式：指定一个当前 SIP 状态 owner，backup 接收状态复制但不主动执行会影响 dialog 的动作；故障时经显式 takeover 后由新 owner 接手。OpenSIPS clusterer sharing tags 使用 `active`/`backup`，切换 active 时广播并促使另一节点退为 backup；`dialog` 文档列出 backup 状态下禁止的 dialog 操作。[S7]

该机制提供可研究的 owner 语义，不单独解决状态完整性、在途 transaction 或旧节点隔离，也不等于数据库锁。要满足本项目合同仍须同步两腿必要状态、验证 takeover 原子性/代次 fencing，并让 peer routing 与 owner 一致。若沿用 reSIProcate 实现此模式，相关机制尚未设计；参考 OpenSIPS 功能不表示引入 OpenSIPS。

## 4. 恢复契约与待决问题

当前 D10 baseline 需要评估以下**状态类别**，不预设 schema：一个逻辑 call key；两条 leg 的 Call-ID/local tag/remote tag；每腿 remote target 与 route set；构造/处理重启后新 BYE 所需的 CSeq；`CallController` 跨腿映射、业务状态与配置上下文/版本；必要时的 recovery generation/owner fencing；以及状态终结、expiry 与不可恢复错误的处理。确切字段要由 ACK-complete call → restart → upstream BYE 轨迹推导并通过真实 SIP replay 验证。pending INVITE/CANCEL/final-response 的 transaction correlation、next action 与 SipStack transaction runtime 属于可选在途扩展，不是当前 D10 acceptance。此列表不表示这些字段可由 reSIProcate public DUM API 序列化或复原，也不选择存储方案。[S1][S2]

**当前验收范围（已确定，不是待决解释）：** REQ-NF-1/E5 的 D10 baseline 是 ACK-complete established dialog；重启后 replacement 处理新的上游 BYE、经既有 UAC leg 路由到对端，并验证 Redis 中完整 dialog record。旧 INVITE transaction 已在 ACK 后完成，当前 test plan 不要求恢复它，也不测试崩溃时仍在途的 transaction。

**可选未来扩展（不属于现行 gate）：** 可评估重启后由下游/UAC 发起的 in-dialog re-INVITE/BYE，以及崩溃时 pending INVITE/CANCEL/final-response/2xx-ACK transaction 的恢复或安全收敛。它们不是当前 test plan 范围的未决解释；任何要纳入验收 gate 的扩展，都需要单独或扩展的 REQ/test-plan 变更和维护者明确批准。

实现授权前仍需解决的问题：

- 若未来另行批准在途 transaction 扩展，每个新增恢复点应恢复 transaction、按已接收消息安全收敛，还是采取其他明确下一步？如何避免重复 INVITE/CANCEL/2xx/BYE 与错误 481？
- checkpoint 写入相对外发请求/响应的 durable ordering、可接受的写入延迟/积压、故障时的 backpressure 和 Redis/数据库故障策略是什么？
- 对当前 established-dialog baseline，两腿如何作为一个逻辑单元提交和接管？generation 如何防止过期 process 在新 owner 获权后继续发 SIP？in-dialog 请求如何路由到当前 owner？
- active call 的 TTL/终态清理如何定义？store 中缺失、过期或不一致时，如何同时避免静默丢呼叫与重复/冲突 SIP 行为？
- REQ-NF-1 没有在本设计文件中展开 RTO/RPO 数字；联合决策需明确故障范围、可接受数据丢失与恢复时间，并使之与原 requirement 的“正在进行的呼叫不能断”一致。

### 4.1 当前两个 app 的 per-call 状态核查

源码与对应测试显示，当前两个 app 的纯判决模块都没有写入 app-specific per-call checkpoint：

- [`apps/translation/src/as_translation/decision.py`](../../apps/translation/src/as_translation/decision.py) 只接收请求、规则和翻译规则并返回判决；没有 `StateStore` import/call，也没有额外的业务状态 payload。其 [unit tests](../../apps/translation/tests/test_decision.py) 验证纯函数行为，[contract replay](../../apps/translation/tests/test_contract_replay.py) 只重放判决数据。README 描述会话状态未来经 StateStore 保存，但当前决策源码/测试没有对应写入。
- [`apps/anti-fraud/src/as_anti_fraud/decision.py`](../../apps/anti-fraud/src/as_anti_fraud/decision.py) 接收 `Mapping[str, int]` counters，只按 rate-limit rule ID 读取，不改写 counters、不读时钟或开 socket；[unit tests](../../apps/anti-fraud/tests/test_decision.py) 明确断言 counters 不变，[contract test](../../apps/anti-fraud/tests/test_contract_replay.py) 从 case data 注入 counters。`RateLimit` 带有 `window_seconds`，决策模块将读取计数与计数/expiry 管理分开；README 描述的 Redis 状态方向并不证明已有接线，当前 app source/tests 没有 `StateStore` 写入。
- 因此 translation 的 app extension payload 当前为空；anti-fraud rate-window counter 是独立的 aggregate domain state，不是每通 dialog 的字段，也不应复制进每通呼叫 checkpoint。其计数、TTL 与幂等语义应由独立的 counter store/use-case adapter 管理；现有代码没有证明这段接线已实现。未来 `CallController` 若需要 AS 特定业务恢复数据，可使用 ADR-0023 规定的 namespaced/versioned extension slot。

## 5. 决策边界

当前方向已明确为 Redis 应用层必要状态 checkpoint，但 ADR-0023 仍 proposed，且没有 recovery adapter 或 D10 通过证据。本文矩阵中的 PostgreSQL、native recovery 与外部 SIP 产品是未来实现参考，不是平级方向提案；任何替代 Redis 的选择都须另行裁决。本比较不修改 ADR-0002、PRD、reSIProcate 栈选择或 D9/D11 状态，也不将 D10 标为 resolved。REQ-NF-1 保持硬要求，D10 继续阻塞 M7/M8。

## 6. 来源

在线资料均于 2026-10-01 访问。RFC 与产品官方手册定义的是其明确写出的协议/模块行为；“文档未证明”不等价于断言某种自定义扩展不可能。

- [S1] IETF, [RFC 3261](https://datatracker.ietf.org/doc/html/rfc3261)，§9 CANCEL、§12.1.2 Dialog State、§12.2 UAC/UAS Requests、§17 Transaction Layer。
- [S2] IETF, [RFC 6026](https://datatracker.ietf.org/doc/html/rfc6026)，§6、§7.1–7.2、§8.5–8.7；INVITE 2xx 对 server/client transaction state 的更新。
- [S3] reSIProcate 官方源代码，1.14.0 pinned commit [`632e215c2ca9aee5416bfe1808851ea6fa380044`](https://github.com/resiprocate/resiprocate/commit/632e215c2ca9aee5416bfe1808851ea6fa380044)：[`DialogUsageManager.hxx`](https://github.com/resiprocate/resiprocate/blob/632e215c2ca9aee5416bfe1808851ea6fa380044/resip/dum/DialogUsageManager.hxx)、[`DialogUsageManager.cxx`](https://github.com/resiprocate/resiprocate/blob/632e215c2ca9aee5416bfe1808851ea6fa380044/resip/dum/DialogUsageManager.cxx)、[`InviteSession.hxx`](https://github.com/resiprocate/resiprocate/blob/632e215c2ca9aee5416bfe1808851ea6fa380044/resip/dum/InviteSession.hxx)、[`SipStack.hxx`](https://github.com/resiprocate/resiprocate/blob/632e215c2ca9aee5416bfe1808851ea6fa380044/resip/stack/SipStack.hxx)。相关符号：`makeInviteSession(DialogSetId)`、`processRequest()`、`findDialogSet()`、private `mDialogSetMap` / `mTransactionController`。
- [S4] Redis 官方手册：[Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)（RDB、AOF durability）、[Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)（异步复制、`WAIT` 限制）、[Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)（failover 与一致性窗口）。
- [S5] Redis 官方开发手册：[Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)（`MULTI/EXEC`、错误与隔离）、[Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)（atomic execution、跨 key 更新）。
- [S6] PostgreSQL 官方手册：[Transactions, §3.4](https://www.postgresql.org/docs/current/tutorial-transactions.html)（原子提交）、[Warm Standby, §26.2.8](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION)（同步复制持久性、时延和可用性代价）。
- [S7] OpenSIPS 官方 3.6 手册：[`dialog`](https://docs.opensips.org/manual/3-6/modules/dialog/)（DB mode、Dialog clustering、seed/sync）；[`b2b_entities`](https://docs.opensips.org/manual/3-6/modules/b2b_entities/)（UAS/UAC entities、DB mode、`cluster_id`）；[`b2b_logic`](https://docs.opensips.org/manual/3-6/modules/b2b_logic/)（B2B logic DB state）；[`tm`](https://docs.opensips.org/manual/3-6/modules/tm/)（anycast owner/reply routing）；[`clusterer`](https://docs.opensips.org/manual/3-6/modules/clusterer/)（binary replication、capability sync、sharing tags active/backup）。该手册所查 replication path 使用 clusterer/proto_bin；本文不把它称为 OpenSIPS DMQ。
- [S8] Kamailio 官方 6.1 模块手册：[`dialog`](https://www.kamailio.org/docs/modules/6.1.x/modules/dialog.html)（DB modes、startup load、`enable_dmq` 限制）；[`dmq`](https://www.kamailio.org/docs/modules/6.1.x/modules/dmq.html)（peer/channel replication model）；[`tm`](https://www.kamailio.org/docs/modules/6.1.x/modules/tm.html)（transaction processing 与 anycast/transaction scope）。
- 本仓库代码核查：[`translation decision`](../../apps/translation/src/as_translation/decision.py)、[`translation tests`](../../apps/translation/tests/test_decision.py)、[`anti-fraud decision`](../../apps/anti-fraud/src/as_anti_fraud/decision.py)、[`anti-fraud tests`](../../apps/anti-fraud/tests/test_decision.py)、[`StateStore protocol`](../../platform/src/as_platform/state/store.py)、[`RedisStateStore`](../../platform/src/as_platform/state/redis_store.py) 与 [`StateStore contract tests`](../../platform/tests/test_state_store_contract.py)。

## 7. 本仓库相关文档

- [HLD](hld.md) 与 [LLD](lld.md)：恢复 contract 和概念生命周期。
- [计划与 D10](../plan.md)：阻塞状态和下一步。
- [ADR-0019](adr/0019-sip-stack-selection.md)：生产栈选择保持 reSIProcate。
- [ADR-0023](adr/0023-redis-call-state-checkpoint.md)：提议中的 Redis 应用层必要状态 checkpoint 方向。