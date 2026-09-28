# ADR-0002：每用例一进程 + 状态外置 Redis

- **Status**: accepted
- **Date**: 2026-09-28
- **Decides**: §0 决策 2 —— 运行时模型：每用例一进程 + 状态外置 Redis，AS 无状态多副本
- **回应 REQ**: REQ-NF-1, REQ-NF-2, REQ-NF-3, REQ-NF-4, REQ-NF-9

---

## Context（背景）

产品 SIP 栈选型前的 POC 使用 `sippy`，其核心模型是阻塞的 `ED2.loop()` —— 一个进程跑一个事件循环，天然只能承载一个用例的 SIP 事务与对话状态。这一硬约束在 POC 阶段没有暴露问题，但产品化时带来三个后果：

1. **进程边界即故障域边界。** sippy 阻塞模型下，一个进程崩了只影响它承载的那个用例，不会波及其他。这个边界同时也是独立灰度单元、独立扩缩容单元。
2. **POC 用了 `InMemoryStateStore`。** 进程重启即丢所有会话。架构文档 §4.1 明确：生产不可用 —— 运营商 on-prem 交付要求多副本水平扩展，单节点不能扛全量话务。
3. **`AGENT.md` §4 分层规则已确立：一个用例一个进程、一个故障域、一个灰度单元。** `apps/` 下每个包对应一个独立的业务用例，`services/` 是控制面（规则治理、控制台），`platform/` 是内核、`testbed/` 是研发资产。

`as_platform/state_store.py` 中已有 `StateStore` seam 接口，预留了 `RedisStateStore` 的接入点。这个 seam 是状态外置的基础。

## Decision（决策）

- **一个用例 = 一个进程 = 一个 K8s Deployment。** `apps/translation`、`apps/anti-fraud` 各自独立进程，不共享事件循环、不共享进程内存。`services/config-service`、`services/console` 是控制面进程，与信令面进程独立部署。
- **会话状态、对话状态、caller_state（速率窗口、信誉衰减）全部外置到 Redis。** 进程自身不持有任何需要持久化的会话级状态；进程重启不影响正在处理的呼叫（状态全部在 Redis 中存活）。
- StateStore seam 是这一模型的核心接口，由 `platform/state_store.py` 定义，`RedisStateStore` 是生产实现。

## Consequences（后果）

### Positive（正面）

- **进程无状态 → 可水平扩展**：K8s HPA 可基于自定义指标（`active_calls`、`cps`）独立扩缩容每个用例的 Deployment，无需考虑状态迁移。
- **进程无状态 → 可随时重启**：ISSU（In-Service Upgrade）只需 draining（摘流、等存量呼叫归零），不需要状态迁移。ADR-0009 确立了这一 draining 语义。
- **进程边界 = 故障域边界**：一个用例进程崩溃不影响其他用例，多副本容错天然成立。

### Negative / accepted（负面 / 已接受）

- **Redis + Sentinel 成为硬依赖。** Redis 是状态的唯一持有者，其可用性直接等价于 AS 的会话状态可用性。Sentinel 拓扑（1 主 + 2 从 + 3 哨兵）需在 M2 前设计完毕（未决项 O5、D3）。Redis Sentinel 切换窗口内，反诈速率窗口可能重复计数（风险 R5）—— 判决需保持幂可接受。
- **亲和性需要双保险。** sippy 是阻塞事件循环，LB 层 `sessionAffinity: ClientIP` 不能保证 S-SBC 不复用源端口时对话请求落到同一副本。需应用层 Redis 会话表兜底（架构 §4.1 风险 R1）。
- **优雅下线 draining 需要 preStop hook + 延长 terminationGracePeriodSeconds。** sippy 阻塞模型下，进程不能在 `SIGTERM` 到来时立刻退出——它要先处理完 in-flight 呼叫。具体 grace window 与强制释放策略由呼叫时长硬顶定义。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 多用例一进程 | 进程内路由，破坏故障域隔离；sippy 阻塞模型无法处理多路信令（一个阻塞事件循环只有一个线程） |
| 数据库存储状态（PostgreSQL） | PostgreSQL 不是为高并发会话读写设计的。每次 INVITE 需要读写多条会话/速率/信誉记录，延迟不可接受；且 PostgreSQL 事务语义对呼叫时延有硬约束 |
| 进程内状态 + 进程间同步 | 同步本身有一致性问题且复杂度高；会话状态在多个进程间镜像、竞态条件处理、同步延迟叠加，收益为负 |

## Evidence（证据）

- `AGENT.md` §4 分层规则明确 platform 是内核、apps 是用例、services 是控制面，一个 app 绝不能 import 另一个 app。
- `as_platform/state_store.py` 已有 `StateStore` seam 接口，`RedisStateStore` 接入点预留。
- 架构文档 §4.1 进程与副本模型确立了进程边界、无状态化前提、亲和性双保险、优雅下线 draining 四个核心要点。

## Related（相关）

- [`../新系统整体架构.md`](../新系统整体架构.md) §4.1 进程与副本模型
- [ADR-0010](0010-autoscaling-hpa-downscale-guard.md) 扩缩容 HPA + 缩容保护
- [ADR-0009](0009-issu-draining.md) ISSU 是 draining，不是状态迁移
- 未决项 O5（容灾等级 N+1 vs N+M）、D3（Redis 接线）
