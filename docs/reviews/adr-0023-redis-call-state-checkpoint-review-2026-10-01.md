# ADR-0023 Redis 呼叫状态检查点评审记录

- **评审对象**：[ADR-0023](../architecture/adr/0023-redis-call-state-checkpoint.md) 及其 REQ / source trace
- **日期**：2026-10-01
- **评审人**：GitHub Copilot（写作子代理；技术审查）
- **结论**：**有条件技术通过；维护者正式评审与签字待定**

## 结论与范围

ADR-0023 准确记录了本次用户明确选择的方向：Redis 应用层必要状态 checkpoint，而不是序列化完整 `SipStack` / DUM 对象。该方向来自用户决策，不是 AI 独立选择。ADR 状态仍为 `proposed`、注册表状态为 `draft`；本记录的有条件技术通过不代表 ADR 被接受、实现已完成或 REQ-NF-1 / D10 已验收。

本记录只评审 ADR-0023 的技术边界与来源追溯，不修改代码、测试、PRD 或 test plan。正式维护者评审、架构接受与签字仍待完成。

## REQ 与证据追溯

| 需求 / 边界 | 追溯结论 |
|---|---|
| REQ-NF-1 | 原文“正在进行的呼叫不能断”保持硬要求。当前 [`test-plan.md`](../acceptance/test-plan.md) 的 D10 可执行基线是 ACK 完成后的 established dialog；重启后新到达的上游 BYE 必须路由到 peer，且 Redis 有完整 dialog record。D10 review 记录 fresh DUM UAS 对 BYE 返回 481，故当前基线失败，不能声称通过。 |
| REQ-NF-2 | 每个 use case 一个独立进程/故障域保持不变；Redis checkpoint 是进程外数据方向，不合并两个 app。 |
| REQ-NF-4 | checkpoint 方向可支持后续 ISSU 状态设计，但 ADR-0023 本身不证明滚动升级、owner takeover 或存量呼叫验收已完成。 |
| REQ-F-1 / F-2 / F-5 / F-8 / F-9 / F-11 | 呼叫建立、B2BUA 两腿、路由信息、CANCEL/BYE、in-dialog routing 和竞态仍是产品 SIP 行为约束；本 ADR 只规定这些状态在指定恢复点的持久化方向，不改变正常呼叫语义。 |
| REQ-NF-6 | 本 checkpoint 是 signaling/dialog/controller data；不含 RTP、媒体锚定或媒体恢复，沿用 ADR-0004 边界。 |

需求语义以[产品 PRD](../requirements/prd.md)为准，D10 的精确验收以[acceptance test plan](../acceptance/test-plan.md)为准。

逐文件核查结果：translation 的 [`README.md`](../../apps/translation/README.md) 描述未来经 StateStore 外置会话状态；但 [`decision.py`](../../apps/translation/src/as_translation/decision.py) 是纯判决函数，[unit tests](../../apps/translation/tests/test_decision.py) 验证纯函数行为，[contract replay](../../apps/translation/tests/test_contract_replay.py) 只重放判决数据，当前没有 translation-specific per-call checkpoint payload 或 StateStore 写入。anti-fraud 的 [`README.md`](../../apps/anti-fraud/README.md) 描述 rate-window / reputation 外置方向；实际 [`decision.py`](../../apps/anti-fraud/src/as_anti_fraud/decision.py) 接收只读 `Mapping[str, int]` counters 并仅读取，[unit tests](../../apps/anti-fraud/tests/test_decision.py) 断言 counters 不变，[contract replay](../../apps/anti-fraud/tests/test_contract_replay.py) 从 case data 注入 counters。counter 是独立 aggregate state，不是每通 dialog 的字段；现有 app source/tests 没有 StateStore 读写接线。

共享内核 [`as_platform/__init__.py`](../../platform/src/as_platform/__init__.py) 仅描述/导出 seam；[`state/__init__.py`](../../platform/src/as_platform/state/__init__.py) 导出 protocol 与实现；[`store.py`](../../platform/src/as_platform/state/store.py)、[`redis_store.py`](../../platform/src/as_platform/state/redis_store.py)、[`in_memory.py`](../../platform/src/as_platform/state/in_memory.py) 和 [contract tests](../../platform/tests/test_state_store_contract.py) 证明当前 store 是通用键值/TTL seam，契约没有双腿原子提交、owner fencing 或 durable commit acknowledgement。

## 有条件项与开放风险

| 项目 | 评审意见 / ADR 中的处理 |
|---|---|
| D10 与 UAS rehydrate | 现行 baseline 仍失败：fresh DUM UAS 收到同 dialog BYE 返回 481。必须实现 recovery adapter 并验证 BYE 路由及完整 Redis record 后才能解除 D10。窄 UAC `DialogSetId` re-INVITE probe 不是完整恢复证据。 |
| early / in-flight phase | inbound INVITE checkpoint 前、outbound INVITE pending/early/provisional、final 2xx waiting ACK、崩溃时 pending in-dialog transaction 均未纳入现行 D10 acceptance，也不获本 ADR 保证。若产品要求这些阶段，须单独扩展 requirement 与 test plan；不得静默缩窄 REQ-NF-1。 |
| 双腿一致性与 fencing | 必须以一个逻辑 checkpoint 保存/恢复两腿，使用单调 generation/revision，并 fence 已被 takeover 的旧 owner；不得让半恢复的 pair 服务呼叫。物理 Redis 表示可后续决定。 |
| durability 与 callback 顺序 | 依赖的 SIP side effect 必须晚于 durable acknowledgement。SIP callback 不能阻塞等待 Redis；异步写入没有符合持久性边界的 ack 时不得称为 committed，也不得执行依赖该提交的 side effect。Redis 故障模型/RPO 与错误路径仍待设计和验收。 |
| S-CSCF header 扩展 | 只允许未来经 peer authentication 和 allowlist 校验的 selected values，放入 namespaced/versioned extension；必须限制大小、保留期与分类。不得保存任意 SIP 消息/全部 headers；重复值/顺序只按经批准的 contract 保留。不指定或虚构当前使用的 header；安全边界见 [ADR-0016](../architecture/adr/0016-in-boundary-security.md)。 |
| ADR-0002 与需求边界 | [ADR-0002](../architecture/adr/0002-per-usecase-process-state-redis.md) 保持 accepted/unchanged；“所有 session state externalized”措辞与 default DUM UAS/transaction runtime 不能由当前外置记录恢复之间的冲突仍开放。ADR-0023 不 supersede ADR-0002，也不修改 PRD/test plan。 |

详细 recovery evidence 以[现有 D10 review](d10-state-recovery-gap-review-2026-09-30.md) 和[呼叫状态恢复方案比较](../architecture/call-state-recovery-options.md)为准。这里没有运行新的 D10 SIP probe；文中报告的是仓库现存 probe 记录及当前源码核查。

## 签字

| 项 | 值 |
|---|---|
| 技术结论 | 有条件通过；仅限 ADR draft 的方向与边界完整性 |
| ADR 状态 | `proposed`；注册表 `draft` |
| D10 / REQ-NF-1 | 未通过 / 未解决；继续阻塞 |
| 维护者正式评审 | 待完成 |
| 维护者决定与签字 | 待填 |