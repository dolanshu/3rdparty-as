# S11：CANCEL 与最终响应竞态

## 场景描述
极端时序：Caller 发送 CANCEL 的同时，Callee 返回 200 OK。两者几乎同时到达 AS，AS 必须正确处理：
- RFC 3261 §9.1：如果 CANCEL 到达时 INVITE 事务已经进入 "Accepted" 状态（已发送 200 OK），则 CANCEL 被忽略，呼叫继续
- 如果 CANCEL 先到达且 INVITE 事务在 "Proceeding" 状态，则终止 INVITE（487）并转发 CANCEL

## POC 覆盖情况
**POC 无显式竞态测试**。POC S-SBC mock 的 CANCEL 由 `CallScenario.abandon=True` 触发，在收到 180 Ringing 后 50ms 发送 CANCEL，时序可控且固定，不是随机竞态。

## 建议处理
在 reSIProcate probe 阶段，在 `testbed/` 里写对拍脚本，构造以下竞态场景：
1. CANCEL 与 180 Ringing 同时到达
2. CANCEL 与 200 OK 同时到达
3. CANCEL 在 200 OK 之后到达（应被忽略）

## 缺口类型
❌ **POC 基线缺失** → probe 阶段补充
