# S6：Request-URI 改写

## 场景描述
AS 根据 routing rule 的 `translate` action 改写 Request-URI。

## 关键断言（样本 run）
- 入腿 RURI：`sip:+8613800138000@127.0.0.1:45363`（E.164 格式）
- 出腿 RURI：`sip:013800138000@127.0.0.1:47288`（national 格式）
- 改写由 R-MOB-CM-40 规则完成：`strip_prefix: "+86"` + `prepend: "0"` + `to_format: national`

## 消息来源
**与 S1 同一 capture**。请参考 `../S1-basic-call/` 目录下的 `01-in-invite-trunk.txt`（入腿）和 `03-out-invite-core.txt`（出腿），对比 Request-URI 行。

## 抓取日期：2026-09-28
