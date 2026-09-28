# S1：基本呼叫

## 场景描述
标准 office-to-mobile 呼叫流程，无异常，呼叫正常完成并释放。

## 消息序列（sippy 基线，14 条）
```
 1. trunk→AS : INVITE sip:+8613800138000@...
 2. AS→trunk : 100 Trying
 3. AS→core  : INVITE sip:013800138000@...  (B2BUA 翻腿，新 Call-ID)
 4. core→AS  : 100 Trying
 5. core→AS  : 180 Ringing
 6. AS→trunk : 180 Ringing
 7. core→AS  : 200 OK
 8. AS→core  : ACK
 9. AS→trunk : 200 OK
10. trunk→AS : ACK
   ======= 通话建立（talk_seconds=0.2s） =======
11. core→AS  : BYE
12. AS→core  : 200 OK
13. AS→trunk : BYE
14. trunk→AS : 200 OK
```

## 关键断言（ADR-0019 §5）
- INVITE → 100 Trying → 180 Ringing → 200 OK → ACK 流程完整
- 之后 BYE → 200 OK 释放完成
- **S5 断言**：双腿 Call-ID 不同，出腿带 `-b2b_1` 后缀
- **S6 断言**：Request-URI 从 `sip:+8613800138000@...` 改写为 `sip:013800138000@...`（E.164 → national，R-MOB-CM-40 规则）
- **S7a 断言**：SDP 体（v=0 到 a=sendrecv）完全透传，字段顺序不变
- **S8 断言**：入腿 INVITE 带 `Route: <sip:...;lr>` 头，AS 正确将 INVITE 转发到该 next-hop port
- 不做媒体锚定（ADR-0006）

## 来源
- POC 工具：`tools/capture_call.py`（默认 scenario office-to-mobile）
- 规则命中：R-MOB-CM-40（China Mobile, priority 100, action=route+translate）
- 抓取日期：2026-09-28
