# S2：无匹配规则 → 404 Not Found

## 场景描述
called number 不匹配 routing_rules.yaml 中任何已启用规则时，AS 直接返回 404 终止呼叫，不出腿。

## 消息序列（4 条）
```
1. trunk→AS : INVITE sip:+99912345678@...
2. AS→trunk : 100 Trying
3. AS→trunk : 404 Not Found
4. trunk→AS : ACK
```

## 关键断言（ADR-0019 §5）
- 无匹配规则 → AS 直接返回 404
- **不发起出腿 INVITE**（无 B2BUA 翻腿）
- 404 响应带正确的 Via/From/To/Call-ID/CSeq/Server 头
- 无 4xx/5xx/6xx 之外的其他响应

## 来源
- POC 工具：`tools/capture_call.py --called +99912345678`
- 规则：R-DEFAULT-99（catch-all）已 `enabled: false`，故无匹配时返回 404
- 抓取日期：2026-09-28
