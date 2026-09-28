# S7a：SDP 完全透传

## 场景描述
AS 不做媒体锚定（ADR-0006），SDP 体在 B2BUA 翻腿时原样透传。

## 关键断言
- 入腿 SDP 和出腿 SDP 的 **每个字节** 完全一致
- `v=0` / `o=- 4101 4101 IN IP4 192.0.2.10` / `c=IN IP4 192.0.2.10`（文档地址 RFC 5737）
- `m=audio 40000 RTP/AVP 0 8 101`（PCMU/PCMA/telephone-event）
- 所有 `a=` 属性原样保留

## 消息来源
**与 S1 同一 capture**。请参考 `../S1-basic-call/01-in-invite-trunk.txt` 和 `../S1-basic-call/03-out-invite-core.txt` 的 SDP body 部分，逐行对比。

## 抓取日期：2026-09-28
