# REQ-NF-15：三层 testbed 与真实 socket 容量研究

> **状态：** reviewed（2026-10-05，D8 关闭）  
> **承载 ADR：** [ADR-0014](../architecture/adr/0014-three-layer-testbed.md)  
> **PRD 索引：** [prd.md](prd.md) §3 REQ-NF-15

## 业务描述

产品交付物不包含 testbed；testbed 是研发资产，方向为 testbed → platform，运行时不得依赖 testbed。testbed 分三层，各层职责不得互相冒充：

| 层 | 路径 | 回答的问题 |
|---|---|---|
| 契约 | `testbed/contracts/` | 判决与跨实现一致性（ADR-0012） |
| 仿真 | `testbed/simulators/`、`testbed/probe/` | AS 能否对着行为像运营商对等端的对象工作 |
| 性能 | `testbed/load/` | 在**真实 socket** 路径上观测容量边界与运行画像 |

容量与 O1 研究**只能**使用真实 socket 压测（UDP/TCP/TLS 经网络栈与事件循环），禁止用驱动回调冒充系统容量测量。GPL 工具（如 SIPp）仅内部测试使用，不得随产品分发。

本 REQ **不**规定对外 SLA、营销 CPS/并发承诺或 HPA 最终阈值；那些由 O1 维护者裁决与 M8 验收链单独处理（`AGENT.md` §2）。

## 验收标准

见 [../acceptance/test-plan.md](../acceptance/test-plan.md) §2-REQ-NF-15。

## 证据与报告

- Harness 与脚本：`testbed/load/`、`testbed/load/scripts/m6-*.sh`
- M6 O1 内部测量报告（dev host，非 SLA）：[../acceptance/m6-o1-measurement-report-2026-10-05.md](../acceptance/m6-o1-measurement-report-2026-10-05.md)
- D8 评审：[../reviews/d8-req-nf-15-review-2026-10-05.md](../reviews/d8-req-nf-15-review-2026-10-05.md)
