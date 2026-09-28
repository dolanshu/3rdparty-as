# 高层设计（HLD）— 3rdparty-as 内核（M2）

- **版本**：v0.1（reviewed）
- **日期**：2026-09-28
- **状态**：reviewed — 2026-09-28 评审通过，见 docs/reviews/m2-design-review.md
- **依据 ADR**：ADR-0002 / ADR-0003 / ADR-0005 / ADR-0007 / ADR-0016 / ADR-0019 / ADR-0020
- **对应 REQ**：见 §8 追溯表

---

## 1. 范围与非目标

### 1.1 M2a —— 本设计覆盖

`platform` 内核的**非 SIP 部分**：

- 进程壳（shell）：启动、依赖注入、信号与 draining、就绪探针。
- `decide()` 缝与其背后的判决纯函数：规则匹配、冲突裁决、产出 `Decision`。
- `StateStore` seam：Protocol 定义 + `InMemoryStateStore`（测试与本地开发）+ `RedisStateStore`（生产）。
- feature 门控 seam：`is_enabled(name, scope)` 与可注入的 `ToggleSource`。
- 遥测 seam：有界队列 + 后台导出线程，呼叫路径只做内存入队。
- 内部 API 契约：内核对外暴露的数据结构与函数签名。

### 1.2 M2b —— 本设计只落 seam 与契约，不实现

- SIP adapter：SIP 消息与内核数据结构之间的翻译层。
- Transport / TLS 绑定：生产栈为 **reSIProcate**（ADR-0019 已接受，经 Python 绑定接入）。

**理由**：绑定一个 C++ 栈需要独立的构建集成（CMake + submodule vendoring）与跨语言契约工作，本身就是一份独立工作量；同时内核必须先能在**没有栈**的情况下被测试 —— 这正是 `docs/plan.md` 中 M2 的退出标准「能在其上构建用例而不碰 sippy」的含义。因此 M2b 只把 seam 的形状定死（什么进、什么出、谁负责 TLS），不写实现。

### 1.3 非目标

- 不做媒体（REQ-NF-6）：不实现 RTP、不转码、不做媒体锚定。
- 不做 CDR（REQ-NF-7）：不采集话单、不批价。
- 不做合法监听（LI）。
- 不做业务用例实现 —— 那是 M3（`apps/translation`、`apps/anti-fraud`）。
- 不做控制面 —— 那是 M4（`services/config-service`、`services/console`），治理态的 PostgreSQL 版本库随之延后。

---

## 2. 上下文与边界

```text
S-CSCF ──iFC 触发──▶ S-SBC ──透明桥接──▶ AS
                                          │
                                          ├── platform 内核（本设计）
                                          └── apps/<case> 用例进程
```

- S-CSCF 按 iFC（3GPP TS 24.229）触发，S-SBC 做**透明桥接**（ADR-0003）：我们从来看不见「网内 / 网外」的差异，因此只有一种接入语义。
- AS = `platform` 内核 + `apps` 用例进程。ADR-0002 确立：**一个用例一个进程、一个故障域、一个灰度单元**。进程内不持有需要持久化的会话级状态。
- 内核的单向依赖规则：内核**不得** import `apps` / `services` / `testbed`。monorepo 里任何 import 都能解析成功，这条规则由 `platform/tests/test_library_independence.py` 强制。

---

## 3. 模块视图

| 模块 | 职责 | 是否纯函数 | 依赖的 ADR |
|---|---|---|---|
| 进程壳（shell） | 加载配置、注入依赖、注册信号、就绪探针、主循环、draining | 否（有 IO 与信号） | ADR-0002、ADR-0009（skeleton，未落地） |
| 入口校验（peer guard） | 对端白名单校验，失败即丢弃并记安全事件 | 否（读配置） | ADR-0016 |
| 决策（decision：`rules` + `decide`） | 规则匹配、冲突裁决、产出 `Decision` | **是** | ADR-0002 |
| 状态（state：`StateStore` Protocol / InMemory / Redis） | 运行态读写，键命名空间与 TTL，写入幂等 | 否（IO），但契约幂等 | ADR-0002、ADR-0007 |
| 门控（gating） | `is_enabled(name, scope)` 判定，默认关、fail-closed | **是**（值由注入的 `ToggleSource` 提供） | ADR-0020 |
| 遥测（telemetry） | 有界队列入队 + 后台线程导出，`dropped` 计数 | 入队是内存操作，导出在独立线程 | ADR-0005 |
| SIP 适配 seam（sip adapter，M2b） | SIP 消息 ↔ 内核数据结构翻译（seam 已落：纯函数与 Protocol，不含栈实现；评审见 `docs/reviews/m2b-seam-review.md`） | 否 | ADR-0019、ADR-0003 |
| 传输 seam（transport / TLS，M2b） | TLS 终止、mTLS、证书热轮换（seam 已落：纯函数与 Protocol，不含栈实现；评审见 `docs/reviews/m2b-seam-review.md`） | 否 | ADR-0016、ADR-0019 |
| 内部 API 契约（api） | 内核对用例进程暴露的数据结构与签名 | —（契约层） | ADR-0002 |

---

## 4. 运行模型

- **每用例进程独立部署。** 一用例一进程、一故障域、一灰度单元（ADR-0002）。进程内不持有会话级状态，进程随时可重启。
- **运行态在 Redis，治理态在 PostgreSQL。** 运行态（会话、对话、速率窗口）走 `RedisStateStore`（ADR-0007），治理态（规则版本、变更单、审计）归 M4 控制面。两者不互为主备、不做跨存储事务。
- **升级走 draining（ADR-0009，skeleton，未落地）。** 语义固定为：`SIGTERM` → 摘流（不再接收新请求）→ 等 `active_calls` 归零 → 退出。因为没有进程内状态，draining 不需要状态迁移。grace window 与强制释放策略由呼叫时长硬顶定义，属 M2b / 部署侧参数。
- **状态键命名空间 `as:{case}:{kind}:{id}`。** 运行态键**必须带 TTL**（ADR-0007：没有 TTL 的运行态键就是事实上的治理态数据，是误用）。写入**幂等**：同一 Call-ID 的重复写入产生一致结果，用于承受 Redis 脑裂窗口（风险 R5、未决 D3）。
- **水平扩展与缩容**依赖上述无状态性；HPA 指标（`active_calls`、`cps`）与缩容保护属 ADR-0010（skeleton，未落地），M2 只保证指标可被遥测 seam 产出。

---

## 5. 关键流（INVITE 判决）

1. **入口。** TLS 终止 + 对端白名单校验（ADR-0016）。校验失败即丢弃，并记一条**安全事件**（不是普通日志）。该步由 transport / peer guard 承担，**M2b 落实现**。
2. **适配。** SIP adapter 把 SIP 消息翻成 `DecisionRequest` —— 内核数据结构，**不含任何 SIP 概念**（没有 header、没有 dialog、没有事务）。这样判决逻辑对栈无感知。
3. **求值。** `decide()` 纯函数对 `DecisionRequest` 求值，产出 `Decision`（action / target / reason_code / matched_rule_id）。
4. **判决分支。**
   - `FORWARD`：建 B2BUA 出腿，按 `target` 转发。
   - `TRANSLATE`：改号后转发（REQ-F-16 语义，M3 用例侧实现）。
   - `DECLINE`：**603 Decline**（REQ-F-7）。
   - `NOT_FOUND`：**404 Not Found**（REQ-F-6）。
5. **状态写入。** 判决结果与呼叫状态写入 `StateStore`，写入**幂等**。
6. **遥测。** 事件投递到**有界队列**，不阻塞；队列满则丢弃并自增 `dropped`。
7. **返回。** 判决回到适配层，由适配层翻译成 SIP 行为并继续。

**明确写出**：`decide()` 里**没有 socket、没有时钟、没有全局状态**（AGENT.md §5）。这一条不是风格偏好，而是它可被 TDD 的前提 —— 同输入必同输出，测试不需要任何 fixture 之外的世界。

---

## 6. 数据模型

| 结构 | 字段 |
|---|---|
| `DecisionRequest` | `call_id`、`calling_number`、`called_number`、`method`、`leg`、`received_at` |
| `Decision` | `action`、`target`、`reason_code`、`matched_rule_id` |
| `Rule` | `prefix`、`action`、`priority` |
| `RuleSet` | 一组 `Rule` 及其版本标识 |
| `CallState` | `call_id`、`leg_state`、`created_at`、`ttl` |

`received_at` **由调用方注入，而不是函数内部取时钟**。原因就是 §5 那条：`decide()` 一旦自己读时钟，它就不再是对同一输入给出同一输出的函数 —— 时间成了隐藏入参，测试必须打桩时钟，幂等性也无法陈述。把时间作为显式入参，纯函数性质才成立，规则中的时段类判定也才可测。

`CallState` 的 `ttl` 是硬要求的直接体现（ADR-0007）：运行态键必须有 TTL。

---

## 7. Feature enablement 设计（AGENT.md §3.4 强制项）

### 7.1 分层（ADR-0020）

| 层 | 粒度 | 存储 | 生效方式 |
|---|---|---|---|
| ① 部署级总开关 | 整个部署 | PostgreSQL 版本库 | 热加载，不重启；走变更单 → 审批 → 灰度 → 回滚 |
| ② 运行态细粒度覆盖 | 号段 / 呼叫 | Redis | 判决时求值；判定结果必须幂等 |

两层共用 [ADR-0006](adr/0006-config-governance.md) 的变更流水线，不开第二套交付形态。

### 7.2 M2 落什么

- 判定入口 `is_enabled(name, scope) -> bool`。
- 默认态**关**（ADR-0020：默认关；未注册的开关名 → 关，fail-closed）。
- 求值走**注入的 `ToggleSource`** —— 测试注入 `StaticToggleSource`（固定值），不需要 Redis 即可覆盖开 / 关两态。
- 判定**幂等**：同一 `scope` 重复求值结果一致，以承受脑裂窗口（风险 R5 / 未决 D3）。
- 层 ① 的存储与热加载在 M4 控制面落地；M2 只定义 `ToggleSource` 契约。

### 7.3 M2 是否引入新开关

**M2 不引入新开关，只落 seam。**

判定标准（对每个候选能力逐条问，全答「是」才引入）：

1. 它是否有**独立的失效模式** —— 关掉它，系统仍能走既有默认路径完成呼叫？
2. 它是否需要在**客户现场按范围灰度**（号段 / 百分比），而不是随版本一起生效？
3. 它是否**尚未稳定**到可以直接作为默认行为发布？
4. 关掉它是否会**改变接口契约**？（若是，则它不是开关问题，ADR-0020 明确排除。）

M2 的产出（判决纯函数、StateStore、遥测队列、进程壳）都是**系统本来就必须有的路径**，没有「既有默认路径」可以退回，因此不满足标准 1 与 3 —— 给它们加开关只会制造开关债务。`decision.rule_priority_v2` 一类的候选同理：优先级语义若在 M2 内定稿，就不需要开关；若未定稿，则应先在 ADR 层裁决语义，而不是用开关把未定稿的语义带进生产。

**移除条件条款**（将来每引入一个开关都必须写明，AGENT.md §3.4）：默认态、灰度策略、移除条件，三者在 ADR 与本文件同步登记；缺失任一项的开关不得合入。

---

## 8. REQ / ADR 追溯表

| REQ | 需求（摘要） | 本设计中承载它的模块 / 章节 | ADR |
|---|---|---|---|
| REQ-F-1 | 基本呼叫信令序列遵循 RFC 3261 | 进程壳 §4、适配 seam §3、判决流 §5、SIP adapter（M2b） | ADR-0002、ADR-0019 |
| REQ-F-2 | B2BUA 对话分离，两侧 Call-ID 不同 | 状态模块 §3、`CallState.leg_state` §6 | ADR-0002 |
| REQ-F-3 | Request-URI 改写 | 决策模块 §3、`Decision.target` §6、适配 seam（M2b） | ADR-0002、ADR-0003 |
| REQ-F-6 | 无匹配 → 404 Not Found | `decide()` 无匹配分支 §5 步骤 4、§3 决策模块 | ADR-0002 |
| REQ-F-7 | 命中阻止 → 603 Decline | `decide()` `DECLINE` 分支 §5 步骤 4；冲突裁决 block 优先 | ADR-0002 |
| REQ-F-9 | in-dialog 请求路由 | 状态模块 §3（`CallState` 按 call_id + leg 定位活跃对话）、适配 seam（M2b） | ADR-0002、ADR-0003 |
| REQ-F-10 | 非 2xx 响应分支（486 / 480 / 408） | 适配 seam §3（M2b）、遥测事件 §5 步骤 6 | ADR-0002、ADR-0019 |
| REQ-F-11 | CANCEL 与最终响应竞态 | 状态模块幂等写入 §4、判决幂等 §5 步骤 5 | ADR-0002、ADR-0009（skeleton，未落地） |
| REQ-NF-1 | 进程重启不丢会话 | 状态模块 `RedisStateStore` §3 §4、进程无状态 §4 | ADR-0002、ADR-0007 |
| REQ-NF-2 | 单进程状态有界 | 一用例一进程 §2 §4、故障域边界 | ADR-0002 |
| REQ-NF-3 | 可水平扩展 | 无状态 + 状态外置 §4、draining 语义 §4 | ADR-0002、ADR-0010（skeleton，未落地） |
| REQ-NF-4 | ISSU 支持 | draining 流程 §4、进程壳 §7（LLD） | ADR-0009（skeleton，未落地）、ADR-0002 |
| REQ-NF-13 | OTel 三信号导出 | 遥测模块 §3、有界队列 + 后台导出 §5 步骤 6 | ADR-0005 |
| REQ-NF-14 | 告警规则集 | 遥测模块指标语义（前置：`active_calls` / `cps` / `dropped` 等指标准确定义后才能写告警）§3 | ADR-0005 |
| REQ-S-1 | 对端白名单校验 | 入口校验（peer guard）§3、判决流步骤 1 | ADR-0016 |
| REQ-S-2 | 与 S-SBC 端到端 TLS | 传输 seam（M2b）§3、判决流步骤 1；决策模块不感知 TLS | ADR-0016、ADR-0019 |
| REQ-S-3 | 证书热轮换 | 传输 seam（M2b）+ 配置热更新 seam（进程壳）§3 §7 | ADR-0016 |

> REQ-F-4 / F-5 / F-8 / F-12~F-16、REQ-NF-5 ~ NF-12、REQ-S-4 由 M3 / M4 承载，不在 M2a 范围（§1.3），M2b 的 SIP adapter 是它们的前置。

---

## 9. 风险与未决

| # | 风险 / 未决 | 说明与当前处置 |
|---|---|---|
| R5 | **Redis 成为新的 SPoF** | 运行态的唯一持有者，其可用性等价于会话状态可用性。缓解：Sentinel 拓扑（1 主 + 2 从 + 3 哨兵）+ 写入幂等。彻底消除要等未决项 O5 定稿。 |
| D3 | **Sentinel 脑裂窗口下的判决幂等** | 窗口内速率窗口可能重复计数、运行态覆盖读可能抖动。处置：判决与写入都按幂等设计（§4、§5 步骤 5、§7.2）；具体 Redis 客户端与 Sentinel 接线属未决项，M2 内定。 |
| M2b | **绑定 reSIProcate 的构建与跨语言契约** | CMake + submodule vendoring 进 monorepo 构建与 CI；Python 绑定（`BUILD_PYTHON=ON`）的版本 pin 与契约边界未定。ADR-0019 已把它登记为接受的缺口（E1 / E4 / E5 待 probe 验证）。 |
| M2b / ADR-0016 | **TLS 证书热轮换实现** | 要求换证书不重启进程、不丢在途呼叫；reSIProcate 的 TCP/TLS 传输层是已知短板（ADR-0019 K8）。M2 只落 `ConfigSource` 热更新 seam 与契约，实现与 probe（S12）随后。 |
| O1 | **容量数字未定** | 在 M6 容量报告出具前不对外发布任何容量数字。M2 只保证容量指标可被采集（遥测 seam），不做承诺。 |
