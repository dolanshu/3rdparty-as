# `services/console/` — 运维控制台

运营商界面：经变更单编辑规则、按 Call-ID 查呼叫轨迹、实时统计。

## 规则

- **读写、鉴权、审计。** POC 控制台是只读且无鉴权的；对产品（ADR-0016）来说不可接受。
- 它**只**通过 AS 的内部 API（`/healthz`、`/metrics`、`/traces`）触及 AS。没有私有通道。
- **呼叫轨迹是产品能力，不是调试的副作用。** 它可不依赖客户是否部署了 trace 后端而按 Call-ID 查询
  （ADR-0005）。同一呼叫的 OTel trace 是另一条通道，用同一个 Call-ID / TraceID 关联。

## 未决决策

前端形态：保留 POC 的"纯 HTML / CSS / JS、无构建步骤"规则，还是接受一套工具链。产品控制台比 POC 的
大得多。作为 D4 在 [`../../docs/plan.md`](../../docs/plan.md) 中跟踪。

## 状态

骨架。
