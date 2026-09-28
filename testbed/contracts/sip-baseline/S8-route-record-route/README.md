# S8：Route/Record-Route 处理

## 场景描述
入腿 INVITE 携带 S-SBC 插入的 Route 头（RFC 3261），AS 必须将 INVITE 路由到该 Route 指向的地址。

## 关键断言
- 入腿 INVITE 带 `Route: <sip:127.0.0.1:47288;lr>`
- AS 将 INVITE 正确发送到 `127.0.0.1:47288`（即 core side 监听端口）
- Route 头在 AS 侧被消耗（翻腿后的出腿 INVITE 不再携带 Route）
- 当 AS 作为 UAC 发出 INVITE 时，会在 Via 中携带自己的地址，不需要 Record-Route（AS 是 B2BUA，每条腿独立）

## 消息来源
**与 S1 同一 capture**。参考：
- `../S1-basic-call/01-in-invite-trunk.txt` 第 11 行：Route 头
- `../S1-basic-call/03-out-invite-core.txt`：出腿 INVITE 正确送达 core 端口

## 抓取日期：2026-09-28
