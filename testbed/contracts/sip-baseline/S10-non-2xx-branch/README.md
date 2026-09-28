# S10：非 2xx 分支（486 Busy Here / 480 / 408）

## 场景描述
被叫返回非 2xx 最终响应，AS 必须正确处理：
- 486 Busy Here（被叫忙）
- 480 Temporarily Unavailable（临时不可用）
- 408 Request Timeout（出腿 INVITE 超时）

## POC 覆盖情况
**POC 无此场景现成工具**。`ReturnUas`（S-SBC mock return side）只返回 200 OK 流程（180 Ringing → 200 OK → BYE），不构造 busy/no_answer/timeout 分支。

## 建议处理
在 reSIProcate probe 阶段，在 `testbed/` 里写对拍脚本，让 mock UAS 返回 486 Busy Here 等非 2xx 响应，观察 AS 是否：
1. 将非 2xx 响应透传到 trunk 侧（不改状态码）
2. 正确终止入腿和出腿的 INVITE 事务
3. 发送 ACK

## 缺口类型
❌ **POC 基线缺失** → probe 阶段补充
