# 产品需求文档（PRD）— 3rdparty-as

> **谁读这个文档**：业务方、运维、开发、测试 —— 任何需要知道"这个产品是什么、干什么用、验收标准是什么"的人。
> **需求编号体系**：REQ-F-*（功能）/ REQ-NF-*（非功能）/ REQ-G-*（治理）。编号一经分配，只在语义发生根本变化时重编；增量需求追加新编号。
> **与 ADR 的关系**：每条 requirement 标注"对应 ADR"——指向已存在的架构决策；标注"M2 补 ADR"表示这个 requirement 在 M2 时才会被正式裁决。ADR 是 requirement 的技术实现决策，requirement 是 ADR 回应的"为什么"。

---

## 0. 产品概述

**这是什么产品。** 3rdparty-as 是一个部署在运营商 IMS（IP Multimedia Subsystem）核心网络**之外**的第三方应用服务器（Application Server）。当运营商的 S-CSCF 网元按 iFC（initial Filter Criteria，相当于运营商给业务方的"触发规则表"）判定一个呼叫需要第三方介入时，SIP 信令经由运营商的 S-SBC（边界会话控制器，承担**透明桥接**职责）送到我们。我们执行业务逻辑判断——例如号码翻译、反欺诈拦截、智能路由——再把结果经 S-SBC 返回给运营商侧。从运营商 S-CSCF 的视角看，我们就是一个"网内 AS"，S-SBC 对它隐藏了"网外"这个事实。

**给谁用、解决什么问题。** 服务对象分两类：① **运营商的业务配置人员**——通过我们提供的控制台配置号段匹配规则、策略（哪些号段需要翻译、哪些号段触发反诈）、审批变更单；② **业务使用方**——翻译服务商、反欺诈提供商、智能路由平台等需要把业务逻辑嵌入呼叫路径的第三方，他们不想自己去部署和维护 SIP 信令栈。运营商的价值是：用我们的 AS，不修改自己的 IMS 核心网配置就能灵活接入第三方业务；业务方的价值是：用我们提供的业务决策接口，不用管 SIP 协议细节。

**它不做什么（非目标，压缩版）。** 不做媒体（不碰 RTP、不做转码、不处理 DTMF、不锚定媒体流）、不做 CDR（计费话单）、不做合法监听、不做 Diameter Sh 接口、单租户、配置管理不走 GitOps（运营商运维不该为了改一个号段去学 Git）。媒体处理如果未来需要放音/录音/转码，触发后由运营商网内的 MRF（媒体资源功能）执行，我们只给判决。

---

## 1. 功能需求（REQ-F-*）

按功能域分组。每条标注 **P0 / P1** 优先级：
- **P0 = 产品不存在就没这个功能**（没有呼叫处理能力就不配叫 AS）
- **P1 = 关键但非核心**（产品能跑但缺了就不完整）

每条 requirement 格式：业务描述 → 技术注解 → 对应 ADR → 验收标准。

### 1.1 呼叫信令核心路径（P0）

**本组定义了"能接运营商的呼叫、能执行业务逻辑、能返回结果"这条最小闭环。**

---

#### REQ-F-1：运营商触发的基本呼叫，信令序列正确返回

**业务描述。** 当运营商的 S-CSCF 通过 S-SBC 触发我们执行业务逻辑时，我们必须接收 INVITE，执行业务判断（转译/反欺诈/路由），然后把结果返回。正常情况下整个信令序列是：INVITE → 100 Trying → 180 Ringing → 200 OK → ACK → BYE → 200 OK。消息经由双躯干（trunk）双核心（core）四段转发：trunk-in → core-in → core-out → trunk-out。

**技术注解。** "双躯干双核心四段转发"是因为我们作为 B2BUA（背对背用户代理），把一个呼叫拆成两条独立的 SIP 腿——上游 trunk 腿（连 S-SBC）和下游 core 腿（连对端），中间是我们的业务逻辑。

**对应 ADR。** ADR-0003（S-SBC 透明桥接 → ISC 单一语义，不做网内/网外双模适配器）。

**验收标准。**
- [ ] 启动仿真 S-SBC 和仿真对端（Return UAS）
- [ ] 从仿真 S-CSCF 发送 INVITE（目标号码命中业务规则）
- [ ] 依次断言收到 14 条消息：INVITE(trunk-in) → 100 Trying(trunk-out) → 100 Trying(trunk-in) → 180 Ringing(trunk-in) → 180 Ringing(trunk-out) → 200 OK(trunk-in) → 200 OK(trunk-out) → ACK(trunk-out) → ACK(trunk-in) → BYE(trunk-in) → 200 OK(trunk-out) → BYE(trunk-out) → 200 OK(trunk-in) → BYE 之后的 200 OK 确认
- [ ] 消息方法和响应码严格等于 POC 基线 `testbed/contracts/sip-baseline/S1-basic-call/` 中的 14 条
- [ ] Via branch 参数符合 z9hG4bK 模式（reSIProcate 会产生不同的 hex 值，模式对即算过）
- [ ] 不检查 SDP `o=` 时间戳、不检查头域书写顺序

---

#### REQ-F-2：B2BUA 双腿分离

**业务描述。** 我们作为 B2BUA，把一个呼叫拆成两条独立的 SIP 腿。两条腿的 Call-ID 不同（因为 Call-ID 标识对话，拆开后是两个独立对话），Request-URI 分别改写——每条腿看起来都是我们独立发起的。上游 trunk 腿的 Call-ID 与下游 core 腿的 Call-ID 之间由我们内部的 `DialogState` 建立映射关系。

**技术注解。** 双腿 Call-ID 不同、Request-URI 改写（trunk 侧路由 → core 侧路由）是 B2BUA 模式的直接推论，不是我们额外发明的行为。

**对应 ADR。** ADR-0003。

**验收标准。**
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取 trunk-in 的 INVITE Call-ID（记为 C1）和 trunk-in 的 BYE Call-ID（记为 C2）
- [ ] 断言 C1 ≠ C2（两条腿对话独立）
- [ ] 提取 trunk-in 200 OK 的 Call-ID，断言等于 C1
- [ ] 提取 trunk-in BYE 的 Call-ID，断言等于 C2

---

#### REQ-F-3：Request-URI 改写

**业务描述。** 上游 trunk 腿的 INVITE 带的 Request-URI 是运营商侧的路由地址（比如 `sip:+86123456789@s-cscf.operator.com`），到了下游 core 腿必须改写成我们内部选定的对端路由（比如 `sip:+86123456789@return-uas:5060`）。反向方向同样：core 腿的 BYE 要改回 trunk 腿的 Request-URI。改写由业务决策层的 `decide()` 函数完成，我们不做硬编码路由。

**技术注解。** Request-URI 改写发生在 B2BUA 状态机的 `call_controller` 层；改写规则来自配置的路由策略（REQ-F-6 到 REQ-F-7 覆盖"选什么路由"的决策）。

**对应 ADR。** ADR-0003。

**验收标准。**
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取 trunk-in INVITE 的 Request-URI
- [ ] 提取 core-out INVITE 的 Request-URI
- [ ] 断言两者 host/port 部分不同（trunk 侧是运营商 S-SBC，core 侧是我们内部选定的对端）
- [ ] 断言 user@部分一致（号码不变，只是路由地址变了）

---

#### REQ-F-4：SDP 完全透传（我们不碰媒体）

**业务描述。** 上游 INVITE 带的 SDP offer（描述"我准备好发语音了，用什么编解码、什么端口"），必须原样传递到下游对端；下游 200 OK 带的 SDP answer，必须原样传回上游。我们不在应用服务器层做媒体锚定（即不"截取"语音流、不自己处理 RTP、不触发 DTMF）。媒体锚定如果未来需要放音/录音/转码，由运营商网内的 MRF 执行，我们只通过信令（608 Rejected 或路由指令）告诉运营商侧该找 MRF。

**技术注解。** 媒体 seam 保留接口定义但不实现生产逻辑，SDP body 在 Transport seam 处做字节级透传。

**对应 ADR。** ADR-0004（媒体 seam，触发条件）。

**验收标准。**
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取 trunk-in INVITE 的 SDP body（bytes）
- [ ] 提取 core-out INVITE 的 SDP body（bytes）
- [ ] 断言两者逐字节相等
- [ ] 提取 trunk-in 200 OK 的 SDP body 和 core-out 200 OK 的 SDP body，同样逐字节相等

---

#### REQ-F-5：Route / Record-Route 头正确处理

**业务描述。** 如果上游 trunk 腿的 INVITE 带了 `Route` 头（告诉我们"这必须先转发到某跳"），我们必须在下游 core 腿的 INVITE 里保留这个 Route 头；如果下游 core 腿的对端返回了带 `Record-Route` 的响应，我们必须在 trunk 腿的响应里正确处理 Record-Route（RFC 3261 §16.13 规定：收到带 Record-Route 的响应后，后续对话内请求必须沿 Record-Route 记录的路径反向发送）。

**技术注解。** Route/Record-Route 是 SIP 对话链的"跳转历史"，POC 在 chained topology 下验证过基本行为，生产栈（reSIProcate）对此有内置处理。

**对应 ADR。** ADR-0003。

**验收标准。**
- [ ] 完成 REQ-F-1 的基本呼叫，其中 trunk-in INVITE 带一个 Route 头（例如 `Route: <sip:proxy.example.com:5060>`）
- [ ] 断言 core-out INVITE 的 Route 头存在且内容等于 trunk-in INVITE 的 Route 头
- [ ] 构造下游对端返回带 Record-Route 的 200 OK
- [ ] 断言 trunk-in 的 200 OK 里 Record-Route 头存在且值与 core 侧 Record-Route 一致

---

### 1.2 路由与策略决策（P0）

**本组是我们存在的意义。** 如果我们收到每个呼叫都只做"无条件转发"，那 S-CSCF 直接连对端就行了——我们之所以被触发，是因为我们要做**决策**：匹配规则、选路由、或拒绝。

---

#### REQ-F-6：无匹配规则返回 404 Not Found

**业务描述。** 如果呼叫号码在我们的业务规则表里**没有任何匹配项**（比如我们只配了 +86138* 和 +86139*，来的是 +86159*），我们必须返回 **404 Not Found**——告诉上游"这个号段没触发我们"。为什么是 404 不是 403？403 Forbidden 的语义是"我知道你是谁但不允许你"，404 才是"你找的东西不存在"。

**技术注解。** 规则匹配在 `decide()` 决策函数里执行，匹配表来自 config-service 下发的规则版本。"无匹配"是决策函数的 return case 之一。

**对应 ADR。** （暂无对应 ADR，属于业务决策语义，不是架构决策。M2 如出现规则引擎设计决策则补 ADR）

**验收标准。**
- [ ] 启动仿真环境，规则表只包含 +86138*（不含 +86199*）
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +861990000000
- [ ] 断言我们返回 404 Not Found
- [ ] 断言不创建 B2BUA 对话（即不发 trunk-out INVITE）
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S2-no-match-404/` 的 4 条消息

---

#### REQ-F-7：策略拒绝返回 603 Decline

**业务描述。** 如果呼叫号码**匹配到了"阻止"策略**（比如 +86168* 是反诈骗规则 R-BLOCK-90），我们必须立即返回 **603 Decline**——告诉上游"我拒绝这个呼叫，你别再试了"。为什么是 603 不是 403？RFC 3261 规定 603 Decline 明确表示"用户拒绝"，S-CSCF 收到 603 后会清理 iFC 链上的触发，不再重试。

**技术注解。** "阻止"策略是 `decide()` 的另一个 return case，返回值携带"拒绝"判决；决策本身是纯函数，不依赖 SIP 栈。

**对应 ADR。** （同 REQ-F-6，M2 补 ADR 若决策引擎有架构性设计）

**验收标准。**
- [ ] 启动仿真环境，规则表包含 +86168* → R-BLOCK-90（阻止策略）
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +861681000000
- [ ] 断言我们返回 603 Decline
- [ ] 断言不创建 B2BUA 对话
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S3-policy-reject-603/` 的 4 条消息
- [ ] 构造一个既匹配"阻止"又匹配"翻译"的优先级冲突场景，断言优先级逻辑正确（阻止 > 翻译）

---

### 1.3 呼叫生命周期（P1）

**本组覆盖基本呼叫之后的各种分支情况。**

---

#### REQ-F-8：主叫放弃——CANCEL 流程正确

**业务描述。** 如果主叫在 200 OK 之前发出 CANCEL（比如拨错号了、挂了），我们必须正确处理：收到 trunk-in 的 CANCEL → 返回 200 OK → 向下游发送 BYE → 收到 487 Request Terminated → 返回 ACK。整个流程是"取消在途呼叫并清理对话"。

**技术注解。** CANCEL 触发 B2BUA 状态机从 Early 状态转入 Terminating 状态，内部 `DialogState` 标记为 canceling。

**对应 ADR。** （暂无，M2 补对话状态机设计 ADR）

**验收标准。**
- [ ] 启动仿真环境
- [ ] 从仿真 S-CSCF 发送 INVITE（命中业务规则，下游 Return UAS 不立即返回 200 OK）
- [ ] 在 180 Ringing 之后、200 OK 之前，从仿真 S-CSCF 发送 CANCEL
- [ ] 断言收到 CANCEL 后我们立即返回 200 OK（对 CANCEL 的确认）
- [ ] 断言我们向下游发出 BYE
- [ ] 断言下游返回 487 Request Terminated
- [ ] 断言我们向下游返回 ACK
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S4-caller-cancel/` 的 12 条消息

---

#### REQ-F-9：in-dialog 请求路由（REQ-F-11）

**业务描述。** 对话建立之后（200 OK → ACK 交换完成），对话内的后续请求（re-INVITE、UPDATE、INFO、BYE）必须正确路由到**已经建立的那个活跃对话**——不能新建对话、不能路由到错误的对端。路由依据是 Via branch + Route 头 + Call-ID（RFC 3261 的对话匹配规则）。

**技术注解。** POC 有 chained topology 覆盖（`chained_as_probe.py`），但 capture_call.py 不跑这个场景，POC 基线缺失。生产栈 reSIProcate 对此有内置对话匹配机制，但我们需要确保对话状态外置后仍能正确路由（StateStore seam 是关键）。

**对应 ADR。** （M2 补对话状态外置设计 ADR）

**验收标准。**
- [ ] 启动仿真环境
- [ ] 完成一次基本呼叫（REQ-F-1），建立对话
- [ ] 对话建立后，从仿真 S-CSCF 发送一个 re-INVITE（携带正确的 Route 头 + 正确的 Call-ID + Via branch 匹配）
- [ ] 断言我们把 re-INVITE 路由到了正确的下游对端（不是新建对话、不是丢到黑洞）
- [ ] 同样测试 UPDATE 和 BYE 的 in-dialog 路由
- [ ] M2 阶段用 `testbed/simulators/` 写完整的 in-dialog 对拍场景

---

#### REQ-F-10：非 2xx 响应分支（486 / 480 / 408）

**业务描述。** 下游对端可能返回各种非 2xx 最终响应：486 Busy Here（占线）、480 Temporarily Unavailable（临时不可用）、408 Request Timeout（超时）。我们必须把这些响应正确透传回上游，而不是在中间"吃掉"或"改写"。对上游来说，"下游忙"和"被拒"在 SIP 协议层需要不同处理。

**技术注解。** POC 的 ReturnUas 只返回 200 OK，基线缺失。生产实现需要在 `call_controller` 层对非 2xx 做分支处理，不能硬编码"下游永远成功"。

**对应 ADR。** （M2 补错误分支处理 ADR）

**验收标准。**
- [ ] 启动仿真环境，下游对端配置为返回 486 Busy Here
- [ ] 从仿真 S-CSCF 发送 INVITE
- [ ] 断言我们向下游发出 INVITE 后收到 486
- [ ] 断言我们向上游转发 486（不是改成 404 或 200 OK）
- [ ] 同样测试下游返回 480 和 408 的场景
- [ ] 验证对话状态在收到非 2xx 后正确清理

---

#### REQ-F-11：CANCEL 与最终响应竞态

**业务描述。** CANCEL 和下游最终响应（200 OK 或非 2xx）几乎同时到达是一种真实的竞态场景——网络延迟导致 CANCEL 还没到达下游，下游已经回了 200 OK。我们必须正确处理这种竞态：CANCEL 到达后**不再 accept 新的最终响应**，而是取消已发送的 INVITE，清理对话。

**技术注解。** POC 没有显式竞态测试，基线缺失。生产实现需要在 `DialogState` 里维护一个 `canceling` 状态，CANCEL 到达后置位，之后收到任何最终响应都按"已取消"处理。

**对应 ADR。** （M2 补）

**验收标准。**
- [ ] 启动仿真环境
- [ ] 在 INVITE 发出后、对端 200 OK 即将返回前（用可控延迟或 mock 注入），同时注入 CANCEL 和 200 OK
- [ ] 断言 CANCEL 被优先处理：我们返回 487 Request Terminated（canceling 的最终状态）
- [ ] 断言后续的 BYE/ACK 序列正确完成
- [ ] 对话状态最终为 Terminated，无悬挂对话

---

### 1.4 已知缺口

| Requirement | 缺口说明 | 计划补齐 |
|---|---|---|
| REQ-F-9 | POC 无现成 capture，只有 chained topology 间接覆盖 | M2 probe 阶段在 testbed 补对拍场景 |
| REQ-F-10 | POC ReturnUas 只返回 200 OK，无 busy 分支 | M2 probe 阶段在 testbed 补对拍场景 |
| REQ-F-11 | POC 无显式竞态测试 | M2 probe 阶段在 testbed 补对拍场景 |

这三条不阻塞 M1（M1 聚焦 P0 核心路径和 P1 呼叫生命周期主干），但阻塞 M2 的"完整协议行为"验证。

---

## 2. 非功能需求（REQ-NF-*）

非功能需求定义了"产品必须怎样运行"，不是"产品必须做什么功能"。每条标注 **P0 / P1**：
- **P0 = 产品架构的基石**（不满足这个，功能需求就无从谈起）
- **P1 = 关键但非架构基石**（有缺陷不致命但运维会踩坑）

### 2.1 核心架构约束（P0）

---

#### REQ-NF-1：进程重启不丢会话

**业务描述。** 我们是 on-premises 交付，运营商要升级版本、或者某个进程不小心崩了——这个时候，用户正在进行中的呼叫**不能断**。我们的会话状态（哪个 Call-ID 在对话、对话的哪一侧是 trunk 哪一侧是 core、caller_state 是什么）绝对不能只存在于进程内存里。

**技术注解。** POC 使用的 InMemoryStateStore 重启即丢会话（ADR-0002 的 Context 节明确指出这个缺陷）。生产实现必须用 StateStore seam + Redis 外置，会话状态存 Redis（Sentinel 冗余），进程内存只做缓存。

**对应 ADR。** ADR-0002（每用例一进程 + 状态外置 Redis）。

**验收标准。**
- [ ] 启动仿真环境
- [ ] 发起一个基本呼叫（REQ-F-1），等待对话建立（ACK 交换完成）
- [ ] 在呼叫中途（对话活跃状态），强行 kill 承载该呼叫的进程
- [ ] 进程被 K8s 拉起后自动重启
- [ ] 从上游（S-CSCF/S-SBC）发送 BYE
- [ ] 断言重启后的新进程**仍能把 BYE 正确路由到对端**（说明对话状态没有丢失）
- [ ] 对话状态校验：Redis 中该 Call-ID 的对话记录完整存在

---

#### REQ-NF-2：单进程状态有界

**业务描述。** 我们不做阻塞事件循环（POC 的 sippy 模型）。一个用例一个进程，一个故障域。进程崩了只影响它承载的那个用例，不影响其他用例、不影响 config-service、不影响控制台。

**技术注解。** sippy 自带阻塞 ED2.loop()，天然一进程一用例。进程边界 = 故障域边界 = 独立灰度/扩缩容边界。

**对应 ADR。** ADR-0002。

**验收标准。**
- [ ] 目录结构：`apps/translation/` 和 `apps/anti-fraud/` 各自独立（不是一个进程里跑两个用例）
- [ ] K8s Deployment：每个用例一个 Deployment，副本数独立配置
- [ ] kill 承载 translation 用例的 Pod，断言 anti-fraud 用例不受影响（anti-fraud Pod 不重启、负载不掉）

---

#### REQ-NF-3：可水平扩展

**业务描述。** 每个用例进程必须能独立扩缩。运营商业务高峰时（比如节假日前夕反诈呼叫洪峰），HPA 能基于 `active_calls` 和 `cps`（每秒呼叫数）这两个自定义指标独立扩容反诈 AS 实例，不影响翻译 AS 实例的副本数。

**技术注解。** 进程无状态（REQ-NF-1）是水平扩展的硬前提。Redis 会话表做亲和兜底，LB 层再用 `sessionAffinity: ClientIP` 双保险。

**对应 ADR。** ADR-0002（扩缩容是无状态化的自然推论）。

**验收标准。**
- [ ] 配置 HPA：translation Deployment 基于 active_calls（阈值 500）
- [ ] 注入 1000 并发基本呼叫
- [ ] 断言 translation Deployment 的副本数从 3 扩到 ≥ 5
- [ ] 停止注入，等待 30 秒，断言副本数缩回到阈值以下
- [ ] 在扩缩过程中，已建立的呼叫不丢失（REQ-NF-1 同步验证）

---

#### REQ-NF-5：S-SBC 透明桥接——我们看不见"网内/网外"差异

**业务描述。** 从我们 AS 的视角看，从 S-SBC 来的消息就"是" S-CSCF 来的。我们不需要实现"网内 AS 适配层"和"网外 AS 适配层"两套逻辑——S-SBC 做了透明桥接，我们只需要实现**一种**接入语义。

**技术注解。** 这是 §0 产品概述中"单一 ISC 语义"的直接推论。S-SBC 是运营商侧网元，不属于我方交付物；testbed 中必须有 S-SBC 仿真器来验证这个认知。

**对应 ADR。** ADR-0003。

**验收标准。**
- [ ] testbed 中有一个 S-SBC 仿真器：它接收仿真 S-CSCF 发来的消息，转发给我们 AS；接收我们 AS 的响应，转回给仿真 S-CSCF
- [ ] AS 的代码中没有任何 "is_intranet" / "is_extranet" / "network_mode" 类型的分支判断
- [ ] 换一个不同实现的 S-SBC 仿真器（比如用 Kamailio），断言 AS 侧行为一致

---

#### REQ-NF-9：单租户 on-premises 部署

**业务描述。** 每客户独立实例，on-premises 交付（运营商机房内部署）。不做多租户（不做共享实例 + 逻辑隔离 + 租户命名空间）。选择单租户的理由：运营商的交付形态本身就是一客户一系统，多租户在此场景无收益，反而增加跨租户数据泄露风险。

**技术注解。** 单租户意味着 Helm chart 产出一个完整系统，每个客户一套 K8s namespace。

**对应 ADR。** ADR-0002 / 架构文档 §11。

**验收标准。**
- [ ] Helm chart 能独立部署一个完整系统到指定 namespace
- [ ] namespace 之间无共享（独立的 Redis、独立的 PG、独立的 AS Pod 组）
- [ ] 一个 namespace 中的故障（Redis 挂了、AS 进程崩了）不影响另一个 namespace

---

### 2.2 扩展与治理（P1）

本组定义了"运维和工程团队必须怎样合作才能长期维护这个产品"。

---

#### REQ-NF-4：In-Service Upgrade（ISSU）支持——draining 摘流

**业务描述。** 升级版本时不能丢呼叫。流程是：新版本副本就绪 → 旧版本副本标记 draining（摘流，不再接新呼叫）→ draining 副本上的存量呼叫继续处理、active_calls 归零 → 副本下线。grace window 可配置；如果超过 grace window 还没归零，触发强制释放策略。

**技术注解。** 前提事实：生产栈（reSIProcate）SIP 事务/对话状态在进程内存，无法"把在途呼叫无缝移交给新版本"——所以 ISSU 只能走 draining，不能走零流量切换。

**对应 ADR。** ADR-0009（已 accepted）。

**验收标准。**
- [ ] 发起滚动升级
- [ ] 在升级过程中注入基本呼叫
- [ ] 新呼叫被路由到新版本副本（旧版本副本已摘流）
- [ ] 旧版本副本上存量呼叫正常完成（BYE → 200 OK）
- [ ] 旧版本副本的 active_calls 归零后，Pod 被 K8s 删除
- [ ] 升级全程无呼叫丢失

---

#### REQ-NF-6：不做媒体

**业务描述。** 不实现 RTP、不做转码、不处理 DTMF、不做媒体锚定、不部署 MRF。保留一个 seam（接口定义）并写明触发条件（出现放音/录音/转码/DTMF 需求时才启用），生产实现为空壳。理由：网外第三方 AS 做媒体中继是三角路由（媒体绕出网再绕回，带宽翻倍 + 时延增加），且网外节点处理用户语音涉及合法监听与隐私合规。

**技术注解。** 媒体 seam 只定义接口（`MediaGatewayClient` 之类的抽象基类），不实现生产逻辑。

**对应 ADR。** ADR-0004。

**验收标准。**
- [ ] grep 生产代码，没有 RTP / G.711 / G.729 / DTMF / 转码 相关实现
- [ ] seam 文件存在（接口定义），生产实现是 stub / raise NotImplementedError / 空函数
- [ ] seam 注释写明"触发条件"和"什么情况下才需要实现"

---

#### REQ-NF-7：不做 CDR——用呼叫轨迹替代

**业务描述。** 不采集计费话单、不投递 CDR、不做 CDR 归档和批价。用按 Call-ID 的**呼叫轨迹**替代 CDR——每一条 SIP 消息（入/出/时间戳/方法/响应码）都可通过控制台查询，用于投诉追溯和反诈举证。呼叫轨迹不是话单：它没有投递通道、不批价、不做网间结算。

**技术注解。** 呼叫轨迹同时是运维信号（走 OTel trace 后端）和产品能力（走 AS 自身 `/api/v1/traces` 查询通道），两条通道用同一 Call-ID/TraceID 关联。

**对应 ADR。** ADR-0017。

**验收标准。**
- [ ] 控制台能按 Call-ID 查询完整的 SIP 消息轨迹（INVITE 到 BYE 的全部消息，入/出方向、时间戳、方法、响应码）
- [ ] 轨迹保留期可配置（默认 7 天，通过 PG 清理任务执行）
- [ ] grep 生产代码，没有 CDR / 批价 / 计费 相关实现

---

#### REQ-NF-8：不做合法监听（LI）

**业务描述。** 不实现合法监听。IRI（Intercept Related Information，监听相关信息）属于网内网元（S-CSCF、S-SBC）的职责；让第三方 AS 介入会引入跨法域暴露（监听指令、监听目标数据、监听回执三个要素不在同一法域）。我们不采集媒体内容，信令层 IRI 应由网内网元自行输出。

**技术注解。** 生产代码中无 LI / IRI / Intercept 相关实现。

**对应 ADR。** ADR-0016。

**验收标准。**
- [ ] grep 生产代码，没有 lawful_intercept / IRI / intercept 相关实现
- [ ] 架构文档 §9.2 明确"LI 由 S-CSCF/SBC 网内出，不在我方交付边界"

---

#### REQ-NF-10：配置不走 GitOps

**业务描述。** 运营商运维人员不应该为了改一个号段规则去学 Git、开 PR、等 CI。配置版本存为 PostgreSQL 中的行，藏在变更单状态机之后——变更路径是：控制台或内部 API 提交变更单 → 审批（对接客户 OSS/工单系统）→ 写入 PostgreSQL 新版本 → 灰度分发到各 AS 实例 → 全部健康后标记生效。

**技术注解。** 不是运维直接 UPDATE 数据库，也不是用 git 仓库管理配置。schema 版本化 + 兼容矩阵是 ISSU（REQ-NF-4）的硬前置。

**对应 ADR。** ADR-0006。

**验收标准。**
- [ ] 控制台能提交规则草稿、发起变更单、触发审批
- [ ] 审批通过后，config-service 写入 PG 新版本（不可变）
- [ ] 灰度分发：分批通知 AS 实例加载新版本，每批有健康检查
- [ ] 分发异常时自动回滚到上一版本
- [ ] 全流程有审计日志落 PG
- [ ] grep 代码，没有 git / github / gitlab 相关的配置加载逻辑

---

#### REQ-NF-11：版本单一来源

**业务描述。** `./VERSION` 文件是产品 release 版本的唯一源头。根目录一个 VERSION 文件，所有组件（`platform/`、`apps/*`、`services/*`）都从根 VERSION 读取版本号，各自的 `pyproject.toml` 只携带**接口语义化版本**（独立于 release 版本）。一个数字两个家（VERSION 文件和 pyproject 各写一个版本）是 POC 的硬伤，v1 必须消灭。

**技术注解。** 由 `tests/test_version_consistency.py` 守卫；CI 阻断任何 VERSION 与 pyproject 漂移的提交。

**对应 ADR。** ADR-0018。

**验收标准。**
- [ ] 根目录存在唯一的 `./VERSION` 文件
- [ ] `grep -r "VERSION=" platform/ apps/ services/` 无结果（各组件不拥有 VERSION 文件）
- [ ] `tests/test_version_consistency.py` 通过
- [ ] 修改根 VERSION 后，所有组件报告的产品版本号同步变化

---

#### REQ-NF-12：monorepo + uv workspace 统一依赖管理

**业务描述。** 所有组件（platform、apps/translation、apps/anti-fraud、services/config-service、services/console、testbed）在同一个仓库里，用 `pyproject.toml` 的 `[tool.uv.workspace]` 统一管理依赖。CI 每个 job 不再需要 `git clone ../as_platform`，Dockerfile 构建上下文不再因仓外依赖而失败。

**技术注解。** 这是架构文档 §11.1 决策账本第 3 条的落地。

**对应 ADR。** ADR-0001。

**验收标准。**
- [ ] `pyproject.toml` 包含 `[tool.uv.workspace]` 配置
- [ ] 运行 `uv sync` 能一次性拉齐所有依赖
- [ ] `git clone` 本仓库后直接 `make dev` 能起服务，不需要额外 `git clone` 其他仓库

---

## 3. 治理需求（REQ-G-*）

治理需求是开发纪律和工程方法论的约束。不满足不会让产品崩，但会让长期维护者痛不欲生。全部为 **P2**。

---

#### REQ-G-1：每个 feature 必须显式裁决 enablement

**业务描述。** 每个新 feature 在进入 HLD/LLD 之前，必须显式裁决三件事：① 是否引入 feature 开关、② 开关默认态（必须默认关）、③ 开关移除条件（防开关债务）。开关只做能力启停，**不改变接口契约**；关闭时走既有默认路径。

**技术注解。** 两层门控：部署级总开关（PG 版本库）+ 运行态细粒度覆盖（Redis，号段/呼叫/用户/百分比级别）。见 ADR-0020。

**对应 ADR。** ADR-0020。

**验收标准。**
- [ ] 每个 feature 的 HLD 节包含 "Enablement" 子节，写明默认态、灰度策略、移除条件
- [ ] feature 开关的开/关两态都有测试覆盖
- [ ] 代码中没有"开关存在了但没写移除条件"的情况（AST 扫描守卫）

---

#### REQ-G-2：改动必须贯通文档链

**业务描述。** 任何行为改动——无论大小——都必须贯通整条文档链：requirement → ADR → 设计 → 契约 → 代码 → 验收。只改代码不改上游文档是未完成。Requirement 是唯一标准，所有阶段必须能追溯到具体 REQ-* 编号。

**技术注解。** 文档链在 AGENT.md §3 定义。PR checklist 中必须包含"上游文档已更新"项；review record 必须标注对应 REQ-*。

**对应 ADR。** （工程方法论，非架构决策）

**验收标准。**
- [ ] PR checklist 包含"已更新 REQ-* / ADR / 设计文档 / 契约用例 / 验收记录"
- [ ] review record 能追溯到至少一个 REQ-* 编号
- [ ] 代码改动能追溯到 requirement（通过 ADR 或直接引用）

---

#### REQ-G-3：不显而易见的代码必须标注对应 ADR

**业务描述。** 代码里的设计决策点、非直观的工程取舍、有 ADR 支持的架构实现，必须在代码行末标注 `# See ADR-00NN`。审稿人从代码一步走到理由，不是自己猜。

**技术注解。** 由 AST 扫描守卫（`tests/` 目录下的扫描脚本）强制——新增"违反 ADR 标注纪律"的代码会被 CI 阻断。

**对应 ADR。** ADR-0015（已 accepted，ADR 标注强制化）。

**验收标准。**
- [ ] `make gate` 包含 AST 扫描步骤
- [ ] 故意写一行不标注的架构性代码，断言 CI 阻断
- [ ] 扫描覆盖率：所有非 trivial 的架构性代码都有 ADR 标注

---

#### REQ-G-4：make gate 必须全绿才能提交

**业务描述。** `make gate` = `ruff format --check` → `ruff check` → `mypy` → pytest（unit/contract 层）。本地门禁不绿，什么都不能提交。`--no-verify` 及其等价物禁止。

**技术注解。** CI 跑同样的四层（快 → 集成 → e2e → 性能）。M0 阶段 integration/e2e/performance 层无测试，用 `continue-on-error` 绕过；首个引入某层测试的里程碑必须同步把该层改为阻塞。

**对应 ADR。** （工程方法论）

**验收标准。**
- [ ] `make gate` 退出码为 0
- [ ] CI 流水线中 `make gate` 失败时阻断后续步骤
- [ ] pre-commit hook 在本地提交前运行 `make gate` 的 lint/format 部分

---

## 4. 与 ADR 的双向映射（快速查阅）

下表是"requirement ↔ ADR"的快速查找索引，不重复正文内容。完整上下文请到对应 ADR 文档。

| Requirement | 对应 ADR | ADR 文件 |
|---|---|---|
| REQ-F-1 / F-2 / F-3 / F-5 | ADR-0003 | `docs/architecture/adr/0003-s-sbc-transparent-bridge.md` |
| REQ-F-4 | ADR-0004 | （ADR 文件待创建，已在 AGENT.md 引用） |
| REQ-F-6 / F-7 / F-8 / F-9 / F-10 / F-11 | 暂缺 | 业务决策语义，非架构决策；M2 如有决策引擎设计补 ADR |
| REQ-NF-1 / NF-2 / NF-3 / NF-9 | ADR-0002 | `docs/architecture/adr/0002-per-usecase-process-state-redis.md` |
| REQ-NF-5 | ADR-0003 | 同上 |
| REQ-NF-4 | ADR-0009 | （ADR 文件待创建，已在 triage.md 引用） |
| REQ-NF-6 | ADR-0004 | 同上 |
| REQ-NF-7 | ADR-0017 | （ADR 文件待创建，已在 AGENT.md 引用） |
| REQ-NF-8 | ADR-0016 | （ADR 文件待创建，已在 AGENT.md 引用） |
| REQ-NF-10 | ADR-0006 | （ADR 文件待创建，已在 services/config-service/README.md 引用） |
| REQ-NF-11 | ADR-0018 | `docs/architecture/adr/0018-release-versioning.md` |
| REQ-NF-12 | ADR-0001 | `docs/architecture/adr/0001-monorepo-uv-workspace.md` |
| REQ-G-1 | ADR-0020 | `docs/architecture/adr/0020-feature-capability-gating.md` |
| REQ-G-3 | ADR-0015 | （ADR 文件待创建，已在 AGENT.md 引用） |

**空缺说明。** ADR-0004/0006/0009/0015/0016/0017 在仓库其他文档中被引用但尚未写成正式 ADR 文件。这不阻塞本 PRD——它们作为已确认决策被引用，但需要在 M2 之前补全 ADR 文档。

---

## 5. 补课说明

本 PRD 是在已有 ADR（0001、0002、0003、0011、0018、0019、0020）**之后**创建的。按 AGENT.md §3.1 的理想顺序，requirement 应该在 ADR **之前**。**本次是补课，不追溯修改已有 ADR 的 Context 节**——ADR 中的 Context 节隐含了对应的 requirement（比如 ADR-0002 Context 节说"POC InMemoryStateStore 重启丢会话"，隐含了 REQ-NF-1 的"进程重启不丢会话"），本文档把这些隐含的 requirement 显式化。

**M2 起的新决策流程要求：** 所有新 ADR 必须先写 requirement（追加到本文档），再写 ADR。ADR 文档头部须加入"本 ADR 回应 REQ-*"字段。已有 ADR 不追溯补这个字段，但 M2 起的新 ADR 必须遵守。
