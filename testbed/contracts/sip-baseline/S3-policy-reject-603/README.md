# S3：策略拒绝 → 603 Decline

## 场景描述
called number 匹配 `reject` 类型规则（R-BLOCK-90 premium-rate blocklist），AS 返回 603 Decline，不出腿。

## 消息序列（4 条）
```
1. trunk→AS : INVITE sip:+8616800000000@...
2. AS→trunk : 100 Trying
3. AS→trunk : 603 Decline
4. trunk→AS : ACK
```

## 关键断言（ADR-0019 §5）
- `action.kind: reject` 规则 → AS 返回 603
- **不发起出腿 INVITE**
- 603 响应结构与 404 相同（Via/From/To/Call-ID/CSeq/Server），仅状态码不同
- `status` 字段由规则指定（本场景为 603）

## 来源
- POC 工具：`tools/capture_call.py --called +8616800000000`
- 规则命中：R-BLOCK-90（premium-rate blocklist, priority 400, action=reject status=603）
- 抓取日期：2026-09-28
