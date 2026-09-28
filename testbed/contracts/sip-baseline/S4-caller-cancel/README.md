# S4：Caller 放弃 → CANCEL

## 场景描述
Caller（mock trunk side）在收到 180 Ringing 之前发送 CANCEL。AS 需要：
1. 对 CANCEL 返回 200 OK
2. 终止入腿 INVITE（487 Request Terminated）
3. 转发 CANCEL 到出腿
4. 终止出腿 INVITE

## 消息序列（12 条）
```
 1. trunk→AS : INVITE
 2. AS→trunk : 100 Trying
 3. AS→core  : INVITE（B2BUA 翻腿）
 4. core→AS  : 100 Trying
 5. trunk→AS : CANCEL         ← caller abandon
 6. AS→trunk : 200 OK         ← 对 CANCEL 的应答
 7. AS→trunk : 487 Request Terminated  ← 终止入腿 INVITE
 8. AS→core  : CANCEL         ← 转发到出腿
 9. core→AS  : 200 OK         ← 出腿对 CANCEL 的应答
10. trunk→AS : ACK            ← 对 487 的 ACK
11. core→AS  : 487 Request Terminated  ← 出腿 INVITE 终止
12. AS→core  : ACK
```

## 关键断言（ADR-0019 §5）
- CANCEL → 200 OK（AS 对 CANCEL 的应答）
- 入腿 INVITE 以 487 终止
- AS **必须**将 CANCEL 转发到出腿 B2BUA
- 出腿 INVITE 也以 487 终止
- 所有 487 都收到 ACK

## 注意：这不是 S11
本场景是标准 CANCEL 流程。S11（CANCEL 与最终响应竞态）是 CANCEL 和 200 OK 同时到达 Caller 的极端竞态条件，POC 没有显式构造这种场景。

## 来源
- 抓取脚本：`testbed/contracts/sip-baseline/capture_abandon.py`（复用 POC run_call API，CallScenario(abandon=True)）
- 规则：R-MOB-CM-40（先路由出去再 CANCEL）
- 抓取日期：2026-09-28
