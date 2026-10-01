# reSIProcate DUM 层功能与 B2BUA 控制层接口设计

> 适用场景：外部第三方 AS、SIP 中继、号码翻译、规则引擎、404/603/CANCEL、SDP 透传。

> **源码核验说明（2026-09-30）**：本文是探索性架构设计笔记，不是 API 契约。下方 C++ 代码片段未经编译或验证；多个回调签名及操作与 reSIProcate 1.14.0 不符，不可据此实现。唯一已选方向是 reSIProcate（ADR-0019）；本文中的栈比较、实现建议和风险等级均为背景材料，不构成新的产品决策。分层上，SipStack 负责传输与事务处理/事务 timer；DUM 作为 TransactionUser/UA 层使用 SipStack，管理 dialog、InviteSession 与 session-level 行为；产品 controller 负责跨腿语义和业务控制。

### reSIProcate 1.14.0 源码核验更正

核验版本：tag `1.14.0`，commit `632e215c2ca9aee5416bfe1808851ea6fa380044`。

| 本文中的假设/示例 | 源码核验结果 |
|---|---|
| `onNewSession` 使用两参数签名 | 两个重载分别接收 `(ClientInviteSessionHandle, OfferAnswerType, const SipMessage&)` 和 `(ServerInviteSessionHandle, OfferAnswerType, const SipMessage&)`。`onProvisional`、`onFailure` 是 client-session 回调；`onConnected` 有 client 专用重载和通用/server 重载；`onTerminated` 接收 handle、reason 和可选关联消息。没有 `InviteSessionHandler::onCancel` 虚函数。 |
| `makeInviteSession(...)` 返回 `ClientInviteSessionHandle` | 它返回待发送的 `shared_ptr<SipMessage>`；会话 handle 后续通过 DUM 回调取得。 |
| UAS CANCEL 由 `ServerInviteSession::cancel()` 处理，应用重写 `onCancel` | `ServerInviteSession` 没有 `cancel()`。初始 UAS INVITE 收到 CANCEL 时，DUM 的该腿路径对 CANCEL 回 200、对 INVITE 回 487，并以 `onTerminated(... RemoteCancel ...)` 通知。产品 controller 仍须协调相反的 UAC 腿及清理/竞态。 |
| `InviteSession::end()` 或 early-state `ClientInviteSession::end()` 表示 CANCEL | `InviteSession::end()` 表示 BYE；此版本中 `ClientInviteSession::end()` 在 early state 也走 BYE 路径。`ClientInviteSession::cancel()` 存在，`DialogUsageManager::end(DialogSetId)` 则按 DialogSet 状态分派。具体取消 API 选择须由 adapter spike 与 CANCEL/final-response race 测试决定。 |
| 所有 session timer / retry 均由应用管理 | DUM 源码包含 RFC session-timer 支持；SipStack 负责事务处理、重传及 transaction timer，DUM 负责其 session-level timer 行为。产品策略及其他重试与协议 timer 分开处理。 |
| 使用 `Contents` 或不改回调即可保证 SDP 字节原样透传 | 默认 session-handler 路径通过 `Helper::getSdp` 提取 SDP；generic offer-answer 模式克隆 `Contents`。这些源码事实不能证明产品线上 REQ-F-4 的 SDP 字节恒等。须由 native adapter 与 wire capture 测试验证；当前结论未定。 |
| 两腿可使用统一 Call-ID 或原始 Call-ID 作为关联标识 | REQ-F-2 要求两腿 Call-ID 独立。controller 应以内部逻辑呼叫 key / session handles 建立关联，不合并两腿 Call-ID。 |

以上核验基于指定上游源码，不等于产品 adapter 已实现或通过协议验收。

### 进程重启探针补充（2026-10-01；探索性、非规范性）

`/tmp/as-resip-dum-process-restart/RESULTS.md` 只证明一个 UAC `DialogSetId` 重建 hook：Phase A 进程退出后，Phase B 的 fresh SipStack+DUM 手工恢复 To-tag、Route、remote target 并递增 CSeq，在相同 Call-ID/tags 下发送 re-INVITE 并收到 200/ACK。它没有恢复旧 `InviteSession`、transaction 或 active media/call state。

相反，`/tmp/as-resip-dum-uas-restart/RESULTS.md` 证明默认 DUM 的 UAS 恢复路径失败：旧进程建立 dialog 并完成 200/ACK 后退出，fresh DUM 收到格式正确的同 dialog BYE 并返回 481。源码中带 To-tag 的请求需在 DUM 私有 dialog-set map 中查找，缺少映射即返回 481；未找到公开 UAS DialogSet/session rehydrate API。该探针不证明自定义 DUM 扩展不可能，但 REQ-NF-1 仍未证明满足。本文仍为非规范性参考，不选定恢复 API 或架构 workaround。

---

## 一、DUM 层完成什么功能

DUM（Dialog Usage Manager）是 reSIProcate 提供的**高层 UA/session API**。`SipStack` 负责传输、SIP transaction processing、事务定时器及其 process loop；DUM 是 `TransactionUser`，由 `SipStack&` 构造并持有该引用，在其上提供 dialog、`InviteSession` 与 session-level 行为。产品 `CallController` 再位于 DUM 之上，处理跨腿关联和业务控制。

### 1.1 对话/邀请会话状态机

- 自动维护 UAS 和 UAC 的 **InviteSession** 状态（Calling / Proceeding / Connected / Terminated）。
- 处理 INVITE 的 1xx、2xx、3xx-6xx、ACK、BYE、CANCEL、re-INVITE、UPDATE 等。
- 自动生成 from-tag、to-tag、branch、CSeq 递增。
- 管理 early dialog 和 confirmed dialog 的 route set、remote target。

### 1.2 回调（Observer 模式）

DUM 通过事件回调报告 InviteSession 生命周期。以下描述的是事件角色，不是可复制的函数签名；具体重载和参数以已核验的 1.14.0 源码为准。

| 事件 | 事件含义 | 控制层责任 |
|------|---------|------|
| `onNewSession` | UAC 或 UAS 会话建立/关联到 DUM 的会话事件；两种角色有不同重载 | 记录腿身份并开始相应的路由或状态处理 |
| `onProvisional` | client/UAC 腿收到 provisional 响应 | 按业务策略协调向另一腿发送 provisional 响应 |
| `onConnected`（client/UAC） | client 腿收到最终 2xx；DUM 按其 UAC 协议流程处理 ACK | 协调另一腿的成功响应；不要假设此事件表示 UAS 已收到 ACK |
| `onConnected`（server/UAS） | server 腿收到 ACK 后进入 connected 状态 | 按实际 ACK 事件更新呼叫状态 |
| `onFailure` | client/UAC 腿收到非 2xx 最终响应 | 映射结果并协调 server 腿及其他待处理分支 |
| `onTerminated` | 会话终止事件，携带终止原因以及可选的关联 SIP 消息 | 按原因（包括 `RemoteCancel`）协调另一腿并清理状态 |
| `onReadyToSend`、`onRedirected`、offer-answer 相关事件 | 发送前、重定向或 offer-answer 生命周期中的其他事件 | 仅在 adapter 设计和测试明确要求时处理；不据此推断消息字节不变 |

`InviteSessionHandler` 没有 `onCancel` 虚函数。初始 UAS INVITE 收到 CANCEL 时，DUM 对 CANCEL 发送 200、对原 INVITE 发送 487，并通过带 `RemoteCancel` 原因的终止事件通知应用；产品 controller 仍负责协调相反的 UAC 腿和竞态清理。

### 1.3 传输与消息收发

- DUM 依赖底层的 `SipStack` 处理传输（UDP/TCP/TLS）、transaction processing、事务重传/timer 与消息收发；DUM 使用这些机制实现 UA/dialog/session 行为。
- 控制层通过经 adapter 验证的 DUM 操作驱动会话和消息；不要把本文当作具体发送 API 契约。

### 1.4 会话管理

- 维护 `InviteSessionHandle` 集合，允许你查找、遍历活跃会话。
- `InviteSession::end()` 表示结束已建立的会话（BYE 语义），不能当作 CANCEL 使用；已核验版本中，early-state `ClientInviteSession::end()` 也不是 CANCEL。
- CANCEL 是针对尚未完成的 INVITE 事务/早期会话的状态相关操作。具体采用的 DUM 操作必须由 D9 spike 和覆盖竞态的 adapter 测试证明。

### 1.5 不提供的功能（留给上层控制层）

- **两腿关联**：DUM 不知道 ServerInviteSession 和 ClientInviteSession 属于同一个 B2BUA 呼叫。
- **业务路由**：号码翻译、规则匹配、错误码映射。
- **协议和产品策略分层**：DUM 处理其支持的 SIP 协议及 session timer 行为；应用负责产品重试、退避、路由重试等策略，不应将二者混为一谈。
- **多腿协调**：CANCEL 需要同时取消两条腿；re-INVITE 需要在两腿间传递。
- **状态持久化**：DUM 不负责将呼叫状态写入数据库。

---

## 二、控制层如何与 DUM 接口

B2BUA 控制层位于 DUM 之上，核心任务是**接收 DUM 的回调事件，执行业务逻辑，然后调用 DUM 的 API 发送消息或修改对话**。

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────┐
│               Your B2BUA Controller                  │
│  - 接收 DUM 回调                                    │
│  - 维护两腿映射表 (ServerLeg <-> ClientLeg)          │
│  - 调用 routing/engine 做号码翻译/路由决策           │
│  - 处理错误分支 (404/603/CANCEL)                     │
│  - 生成 telemetry 事件                               │
├─────────────────────────────────────────────────────┤
│                  DUM Layer                           │
│  - TransactionUser / UA 层                           │
│  - Dialog / InviteSession 状态机                     │
│  - session-level 行为与 session timer                │
├─────────────────────────────────────────────────────┤
│                  SipStack                            │
│  - 传输层 (UDP/TCP/TLS)                             │
│  - 事务层                                           │
│  - 安全 (TLS证书)                                   │
└─────────────────────────────────────────────────────┘
```

### 2.2 核心接口模式：事件驱动的生命周期

控制层消费 DUM 生命周期事件，并通过 adapter 驱动相应的会话操作。下表描述职责边界，不定义 C++ 接口或方法签名：

| 生命周期阶段/事件 | 控制层职责 | 约束 |
|------|------|------|
| 新的 inbound UAS session | 分配内部逻辑呼叫 key，记录 server-leg session identity，执行业务路由 | 不以 SIP Call-ID 充当跨腿的唯一身份 |
| 建立 outbound UAC leg | 请求 adapter 按已验证流程创建并关联 client-leg session identity | 创建流程和精确 API 仍由 D9 spike 与 adapter tests 决定 |
| provisional、connected、failure | 根据事件所属腿及其 session identity 协调另一腿 | client/UAC 与 server/UAS 的 connected 事件语义不同，不能合并为“收到 2xx” |
| terminated | 依据终止原因和可选关联消息处理取消、失败或正常结束，并清理映射 | 清理需考虑另一腿及仍在竞态中的分支 |

两腿用内部逻辑呼叫 key 和各自的 session identity 关联。REQ-F-2 下，两条 SIP 腿的 Call-ID 必须保持独立；映射中可记录各自 Call-ID 供诊断，但不得合并或改作共享 Call-ID。

### 2.3 控制层的关键生命周期

1. **收到 inbound INVITE（UAS 腿）**：DUM 建立/关联 UAS session 并报告事件。控制层创建内部逻辑呼叫 key，保存 server-leg session identity，调用路由决策；拒绝、临时响应等行为通过 adapter 已验证的 DUM 操作完成。
2. **建立 outbound INVITE（UAC 腿）**：控制层根据路由结果请求 adapter 建立 UAC session，保存其独立 session identity，并关联到同一个内部逻辑呼叫 key。精确创建及发送调用仍待 D9 spike 和 adapter tests 验证。两腿 SIP Call-ID 按 REQ-F-2 保持不同。
3. **处理 provisional 和最终响应**：client/UAC provisional 事件可促使控制层按策略协调 UAS 腿。client/UAC 收到最终 2xx 后，DUM 按 UAC 协议流程处理 ACK；控制层再协调 UAS 腿的成功响应。UAS 的 connected 事件发生在收到 ACK 时，因此两种 connected 事件是不同生命周期事实。
4. **处理 client/UAC 非 2xx 最终响应**：`onFailure` 是 client-leg 事件。控制层按产品规则映射到 UAS 腿，并协调尚未完成的其他分支后再清理状态。
5. **处理 inbound 初始 UAS INVITE 的 CANCEL**：DUM 对 CANCEL 回 200、对原 INVITE 回 487，随后以 `RemoteCancel` 终止原因通知控制层；没有 `onCancel` 虚函数。产品 controller 负责协调 outbound UAC 腿、fork/并行分支清理及 CANCEL 与最终响应的竞态。出向早期腿必须采用状态适用的 DUM 操作，且该选择须由 adapter 测试证明；不得把 `end()` 当作 CANCEL。
6. **处理已建立会话的结束**：BYE/end 语义与 CANCEL 不同。控制层按会话状态协调两腿并清理映射，具体 DUM 操作以 adapter 验证结果为准。
7. **处理发送前消息和 SDP**：若产品确需改写头域或 offer-answer 内容，必须通过经验证的 adapter 路径实现。回调中的 `Contents` 解析/克隆或不改内容都不能证明 REQ-F-4 的 SDP wire byte identity；只有真实 wire capture 验证后才能声称符合该要求。

### 2.4 控制层的职责边界总结

| 职责 | 归属 |
|------|------|
| 创建/销毁对话 | DUM |
| 传输、SIP transaction processing、事务重传及 transaction timer | SipStack |
| Dialog / InviteSession 语义、session-level 行为及 DUM 支持的 session timer | DUM（使用 SipStack） |
| 产品消息/会话命令的适配与跨腿业务语义 | adapter / product controller；不得复制 stack transaction/timer |
| 两腿关联 | 控制层（你自己的 map） |
| 号码翻译、路由决策 | 控制层（调用 routing/engine） |
| 错误码映射（404/603） | 控制层 |
| 两腿 CANCEL/BYE 协调与产品级竞态清理 | 控制层，使用经 adapter 测试验证的状态适用操作；`end()` 为 BYE 语义 |
| 产品重试/退避策略 | 控制层；与 DUM 的协议/session timer 区分 |
| SDP/头透传及 REQ-F-4 验收 | 控制层与 adapter；必须 wire capture 验证，未验证前不得宣称 SDP 字节恒等 |
| Telemetry 日志 | 控制层 |
| 规则热加载 | 控制层（独立线程，不影响 DUM 回调） |

### 2.5 线程安全注意事项

- 回调运行时的线程归属取决于宿主及其事件循环集成；不要假设它必然运行在 DUM 自有线程或固定的单线程 EventLoop。
- 控制层回调必须**不阻塞**，不做长时间 IO（如数据库查询、HTTP 请求）。若需异步处理，应遵循宿主事件循环和 adapter 的线程/句柄安全约束，将会话操作调度回允许操作它们的执行上下文。
- 路由引擎如果是纯函数且无状态，可在回调中调用；如果有缓存/热加载，需要按宿主并发模型保证线程安全（如读写锁或原子指针交换）。

---

## 三、与 sippy B2BUA 对比

| 特性 | sippy B2BUA | reSIProcate + DUM 自研 |
|------|------------|------------------------|
| 开箱 B2BUA | 是（b2bua_simple） | 否，需自研控制层 |
| 两腿关联 | 自动 | 手动 |
| 回调模型 | 事件驱动（类似） | 虚函数回调 |
| 错误分支 | 内置 | 自实现 |
| TLS | 支持（需编译） | 原生支持 |
| 社区活跃度 | 较低（个人项目） | 较高（VoIP 行业广泛使用） |
| 学习曲线 | 低 | 中高 |

> 背景比较，不是产品决策：团队能力、POC 速度和迁移建议均不改变 ADR-0019。生产栈方向仅选择 reSIProcate；sippy 内容不构成候选或迁移授权。

---

## 四、自研 B2BUA（reSIProcate DUM）风险点

按场景（信令 only、SDP/头透传、改 Request-URI+号码、规则引擎、404/603/CANCEL、Call-ID 跟踪）重点防这些：

1. **两 leg 对话关联**：UAS leg 收到 INVITE 后，控制层按规则产生 UAC leg。用内部逻辑呼叫 key 和每腿 session identity 建立映射；两端 Call-ID 按 REQ-F-2 保持独立，并按需记录各自的 tag、route-set 等信息，否则 BYE/CANCEL/重协商会错腿。

2. **早期对话与 provisional**：180 无 SDP、180 带 SDP、183 会走不同路径；PRACK 若 S-SBC/核心要（IMS 常涉 early-media/PRACK），DUM 可支持但要在控制层处理，不然卡在早媒体。

3. **重传/定时器/事务**：RFC3261 transaction processing、重传与 transaction timer 属于 SipStack；DUM 提供 dialog/session 行为及其支持的 session timer。绕过 SipStack 自行处理原始事务容易造成错误。

4. **CANCEL/487/200 关联**：初始 UAS CANCEL 由 DUM 对 CANCEL 回 200、对 INVITE 回 487，并报告 `RemoteCancel`。controller 仍要协调 outbound UAC 腿及 fork，并处理 CANCEL 与最终响应的竞态；出向 early-leg 操作必须由状态适用性测试证明，不能用 `end()` 代替 CANCEL。

5. **re-INVITE/UPDATE/hold/resume**：即使 SDP 透传，会话中途改 SDP、session timer 刷新，要双向转发且不破坏 dialog route。

6. **SDP 透传的"纯透传"边界**：RFC7092 把只改信令不改 SDP 归 signaling-only，改 SDP 归 SDP-modifying signaling-only。REQ-F-4 的 SDP wire byte identity 当前未证明；`Contents` parse/clone 或 no-op 回调不足以证明恒等。必须进行真实 wire capture，只有验证通过后才能声称符合；若要规范化、过滤 codec、改 IP，则须另行验证相应 SDP 修改行为。

7. **TLS 长连与并发**：宿主和事件循环集成决定线程所有权与并发模型；B2BUA 状态要避免竞态，DUM 回调里别做阻塞 IO。

8. **可测试性**：纯函数路由引擎放外面，DUM 回调只做"收事件→查规则→改消息→发对端"，这样单测不依赖网络。

> 背景风险评级，不是产品决策：用 DUM 自研薄控制层＝中；从 SipStack 裸写＝高；用 DUM 但把全部业务塞回调＝中高（难测）。行为与 API 仍须按源码、adapter spike 和 wire-level 测试验证。
