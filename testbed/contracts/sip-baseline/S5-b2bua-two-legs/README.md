# S5：双腿 B2BUA（两侧 Call-ID 不同）

## 场景描述
AS 作为 B2BUA，入腿和出腿使用不同的 Call-ID。

## 关键断言
- 入腿 Call-ID：`48f64baa94fdfcfdd79af4128905d375`（样本 run）
- 出腿 Call-ID：`48f64baa94fdfcfdd79af4128905d375-b2b_1`
- 出腿 Call-ID 由 sippy 的 `outbound_call_id()` 生成，规则是 `<trunk_call_id>-b2b_<n>`

## 消息来源
**与 S1 同一 capture**。请参考 `../S1-basic-call/` 目录下的 `01-in-invite-trunk.txt` 和 `03-out-invite-core.txt`，对比 Call-ID 字段。

## 抓取日期：2026-09-28
