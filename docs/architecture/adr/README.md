# ADR 注册表（ADR register）

`3rdparty-as` 的架构决策记录（architecture decision records）。它们记录的设计是
[`../新系统整体架构.md`](../新系统整体架构.md)；下表把该文档 §0 账本中的每一项已确认决策，映射到
承载其背景、后果与已接受缺口的 ADR。

**状态图例** —— `skeleton`：决策已确认但 ADR 还没写；`draft`：写了，未评审；
`accepted`：评审过且有约束力；`superseded-in-part`：部分前提被新 ADR 推翻，框架仍有效。

ADR 与它所授权的改动**一起**写，不事后、不最后批量补。没有 ADR 的决策，是要被重新争论的决策。

## 注册表

| ADR | 决策 | §0 | 状态 |
|---|---|---|---|
| [0000](0000-adr-template.md) | 下面每个 ADR 使用的模板 | — | accepted |
| [0001](0001-monorepo-uv-workspace.md) | 单一 monorepo + uv workspace；POC 与 `as_platform` 并入 | 3 | accepted ✓ |
| [0002](0002-per-usecase-process-state-redis.md) | 运行时模型：一个用例一个进程，状态外置到 Redis | 2 | accepted ✓ |
| [0003](0003-s-sbc-transparent-bridge.md) | 单一 ISC 接入语义 —— S-SBC 是透明桥接，不是第二种业务语义 | 10 | accepted ✓ |
| 0004 | 不做媒体；保留一个媒体 seam 并写明触发条件 | 11 | skeleton |
| [0005](0005-observability-otel.md) | OTel 三信号，后端中立，导出绝不能阻塞呼叫路径；呼叫轨迹保留独立查询通道 | 12 | accepted ✓ |
| [0006](0006-config-governance.md) | 配置治理：PostgreSQL 版本库 + 变更单状态机，而非 GitOps | 13 | accepted ✓ |
| [0007](0007-data-plane-split.md) | 数据面拆分：Redis 存运行态，PostgreSQL 存治理态 | 14 | accepted ✓ |
| 0008 | 冗余：站点内 N+1 零单点；跨站点 1+1 温备，非双活 | 7 | skeleton |
| 0009 | ISSU 是 draining，不是在途状态迁移 | §6.2 | skeleton |
| [0010](0010-autoscaling-hpa-downscale-guard.md) | 扩缩容：自定义指标 HPA + 缩容保护控制器 | 15 | accepted ✓ |
| 0011 | ~~SIP 栈：双栈，`sippy` 保生产，`go-b2bua` 试点~~ **栈前提被 ADR-0019 推翻**：sippy 退出生产栈；双栈并行框架仍有效 | 8 | superseded-in-part |
| 0012 | 语言无关契约 + 跨实现对拍作为转正门槛 | 9 | skeleton |
| 0013 | Helm 是唯一生产形态；compose 仅作开发环境 | 6 | skeleton |
| 0014 | 三层 testbed；真实 socket 压测；不是 v1 交付物 | 16 | skeleton |
| 0015 | 研发模式：分层 TDD、ADR 制度化、四层 CI 门禁 | 17 | skeleton |
| [0016](0016-in-boundary-security.md) | 边界内安全：对端白名单、端到端 TLS、控制台鉴权、全量审计。不做 LI、不做计费 | 18 | accepted ✓ |
| 0017 | 不做 CDR：不采集、不投递、不归档 —— 由呼叫轨迹替代 | 4 | skeleton |
| [0018](0018-release-versioning.md) | 一个产品 release 版本，独立的组件接口版本 | §11.3 | accepted ✓ |
| [0019](0019-sip-stack-selection.md) | 生产 SIP 协议栈选型（推翻 0011 的栈前提；选定 reSIProcate；go-b2bua / libre 为备选；rsipstack 因 Rust 不在团队技术栈内被否决） | 8 | **accepted** |
| [0020](0020-feature-capability-gating.md) | Feature 能力门控：分层（部署级总开关 + 运行态细粒度覆盖），复用配置治理变更流水线 | 19 | accepted ✓ |
| [0021](0021-runtime-override-granularity.md) | 运行态覆盖的判定粒度与 schema：号段 + 稳定哈希百分比，判定幂等（裁决未决项 D7） | — | accepted ✓ |

## 规则

- **编号只追加。** 被取代的 ADR 保留编号并标为被新 ADR 取代；编号绝不重用或重排。
- **一个 ADR 一个决策。** "架构"不是决策。
- **ADR 必须写明它接受了什么。** 它明知故犯的缺口是记录的一部分；没有 consequences 节的 ADR 是宣传。
- **代码指向它的 ADR。** 一行不显而易见的代码带 `# See ADR-00NN`，审稿人能从代码一步走到理由。
- **推翻一个决策** 意味着写一个新的 ADR，并在同一次改动里更新
  [`../新系统整体架构.md`](../新系统整体架构.md)。

## 与 POC ADR 的关系

POC 在 `3rtparty_AS_POC/docs/architecture/adr/` 里带了 ADR-0001 … ADR-0016。它们**不**导入。
它们记录的是一个概念验证 —— 一个有着不同非目标的不同系统 —— 的决策。某条 POC 决策存活进产品时，
要在这里对着产品约束重新论证，POC 原文作为背景引用。没存活的，就干脆缺席，迁移甄别
（[`../../migration/triage.md`](../../migration/triage.md)）记录原因。
