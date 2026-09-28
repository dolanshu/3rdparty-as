# `testbed/simulators/`

运营商网元的仿真。我们不交付的东西必须被建模，否则集成测试无处可跑。

| 仿真器 | 替代 | 必须建模 |
|---|---|---|
| S-SBC | 运营商边界 | **透明桥接**与拓扑隐藏，双向。AS 的单一 ISC 语义依赖它（ADR-0003） |
| P-CSCF / S-CSCF | IMS 核心 | iFC 链：S-CSCF#1 → S-SBC → AS → S-SBC → S-CSCF#2 … |

构建于与 AS 相同的 SIP 栈之上，所以测试双方说相同的协议行为 —— 这是 POC 用的同一条规则，也是这个包
依赖 `as-platform` 的原因。

研发与 CI 资产。**不是 v1 交付物**（ADR-0014）。
