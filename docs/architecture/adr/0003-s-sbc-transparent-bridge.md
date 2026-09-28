# ADR-0003：单一 ISC 接入语义 —— S-SBC 是透明桥接

- **Status**: accepted
- **Date**: 2026-09-28
- **Decides**: §0 决策 10 —— IMS 位置：网外部署、iFC 触发、S-SBC 透明桥接 → 单一 ISC 语义
- **回应 REQ**: REQ-F-1, REQ-F-2, REQ-F-3, REQ-F-5, REQ-NF-5

---

## Context（背景）

本产品定位为**产品化的第三方 IMS Application Server**，单租户 on-premises，部署在运营商 IMS 网络之外（`AGENT.md` §1）。它的触发路径是：S-CSCF 按 iFC（initial Filter Criteria，3GPP TS 24.229）触发 AS，消息经由运营商的 S-SBC（Session-SBC）出站转发。

架构文档 §1.1 的关键认知修正如下：

- **对 S-CSCF 侧**：第三方 AS 被视作**网内 AS**。S-CSCF 完全无感，它按 iFC 发送 ISC（IMS Service Centralization and Continuity）触发消息，消息的 Request-URI、Route 集、P-Asserted-Identity 等所有头域对 S-CSCF 来说，就像发给了一个网内 AS。
- **对 AS 侧**：从 S-SBC 来的 SIP trunk 消息"就是"S-CSCF 发来的。AS 不需要识别"这个消息是从 S-SBC 来的、还是从 S-CSCF 直接来的"—— 两条路径语义等价。S-SBC 承担了透明桥接与拓扑隐藏，不引入第二种业务语义。

POC 中的 `s_sbc_mock` 仿真器已经按这个行为建模：前向 `:15060`、返回 `:15061`，消息原样透传，AS 侧收到的消息头域与 S-CSCF 直接发送的一致。

这一认知修正的架构推论是：**AS 只需要实现一种接入语义**。不需要为 trunk（网外）和 S-CSCF 直接（网内）各写一套适配层 —— 两种场景在 AS 看来是同一种 ISC 触发。

## Decision（决策）

AS **只实现 ISC 语义**（被 S-CSCF 按 iFC 触发），不实现"网外特殊适配"。trunk 只是承载层，不是第二种业务语义。

`testbed/simulators/` 必须包含一个 S-SBC 仿真器，以透明桥接行为作为基线 —— 它对上游（仿 S-CSCF）呈现"AS 是网内"，对下游（AS）呈现"我就是 S-CSCF"。所有生产接入路径都必须以这个仿真器作为行为基线验证。

## Consequences（后果）

### Positive（正面）

- **只实现一种接入语义，消除双模适配器的额外复杂度。** 如果要支持"网内/网外双模"，需要为每条 SIP 消息写两套适配层：一套处理 S-CSCF 直接来的 ISC 触发，一套处理经过 trunk 的适配（包括可能的号码翻译、端口映射、信令字段调整等）。按 POC 的规模估算，这会增加 50%+ 的信令处理代码量。
- **AS 对 S-SBC 的正确桥接行为无需特殊处理。** AS 只认标准 ISC 消息格式；S-SBC 的任何非标准行为都属于 testbed 仿真器需要覆盖的边界情况，而不是 AS 实现需要适配的特殊路径。

### Negative / accepted（负面 / 已接受）

- **依赖运营商 S-SBC 正确执行透明桥接。** 如果 S-SBC 有非标准行为（例如改写某些头域、添加额外 Route、对 in-dialog 请求做异常处理），AS 需要适配这些边界。缓解方式：testbed/simulators 中的 S-SBC 仿真器必须先跑通与 S-SBC 厂商提供的真实行为抓包对比，再作为基线；生产接入前做联调验证。
- **安全边界需要额外收紧。** 既然 AS 侧认为"对端就是 S-CSCF"，S-SBC 链路的对端真实性必须靠 TLS + 白名单双重保证（ADR-0016），否则任何人伪装成 S-SBC 即可灌入呼叫。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 网内 / 网外双模适配 | 为 trunk 和网内两种接入各写一套适配层。按 POC 规模估算会增加 50%+ 的信令处理代码量，且两套逻辑的维护成本与一致性风险无法接受 |
| 绕过 S-SBC 直接与 S-CSCF 通信 | 运营商网络边界设计不允许。S-CSCF 不暴露网外接口；iFC 触发的 ISC 消息必须经过 S-SBC 的拓扑隐藏 |

## Evidence（证据）

- 架构文档 §1.1 完成了 IMS 网络位置分析与关键认知修正，明确 S-SBC 透明桥接的双向视角。
- `AGENT.md` §1 明确定位："由 S-CSCF 经运营商的 S-SBC 触发，S-SBC 做透明桥接"。
- POC 的 `s_sbc_mock` 已按透明桥接行为建模，消息原样透传，不引入业务语义差异。

## Related（相关）

- [`../新系统整体架构.md`](../新系统整体架构.md) §1.1 关键认知修正
- `testbed/simulators/` 仿真器设计 —— S-SBC 透明桥接行为基线
- [ADR-0016](0016-security-boundary.md) 边界内安全：对端白名单 + 端到端 TLS
