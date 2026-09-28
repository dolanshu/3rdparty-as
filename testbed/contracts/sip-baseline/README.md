# POC SIP 行为基线（sippy）

本目录存放 POC（`3rtparty_AS_POC` @ `4ddf3df3`）在 sippy 上抓取的 SIP 消息样例。

**重要**：基线以**外部可观测消息行为**形式记录，不以 sippy API 形式记录。
对拍时只校验：方法、响应码、关键头域存在性、消息顺序。不校验头域顺序、Via branch 具体值、SDP `o=` 时间戳。

## 场景映射

| S# | 场景 | POC 工具/测试 | 状态 |
|---|---|---|---|
| S1 | 基本呼叫（INVITE→100→180→200→ACK→BYE→200） | capture_call.py | ✅ 已抓取 |
| S2 | 无匹配规则→404 | capture_call.py（传无匹配号码） | ✅ 已抓取 |
| S3 | 策略拒绝→603 | capture_call.py（传 +86168* 匹配 R-BLOCK-90） | ✅ 已抓取 |
| S4 | Caller 放弃→CANCEL→200 OK | 复用 POC run_call()，CallScenario(abandon=True) | ✅ 已抓取 |
| S5 | 双腿 B2BUA（两侧 Call-ID 不同） | capture_call.py（S1 已验证） | ✅ S1 同 capture |
| S6 | Request-URI 改写 | capture_call.py（S1 已验证） | ✅ S1 同 capture |
| S7a | SDP 完全透传 | capture_call.py（S1 已验证） | ✅ S1 同 capture |
| S7b | SDP 按契约改写 | POC 无此功能（sippy 端不做媒体锚定，ADR-0006） | ❌ 基线缺失 → probe 阶段补充 |
| S8 | Route/Record-Route 处理 | capture_call.py（S1 有 Route 头） | ✅ S1 同 capture |
| S9 | in-dialog 请求路由 | POC chained topology 覆盖（RFC 3261 Route set 处理） | ⚠️ POC 有 chained_as_probe.py，但 capture_call.py 不跑，需从 POC chain 测试间接推断 |
| S10 | 非 2xx 分支（486 Busy Here / 480 Temporarily Unavailable / 408 Request Timeout） | POC ReturnUas 只返回 200 OK，无 busy 分支 | ❌ 基线缺失 → probe 阶段补充 |
| S11 | CANCEL 与最终响应竞态 | POC 无显式竞态测试 | ❌ 基线缺失 → probe 阶段补充 |

## POC 基线覆盖度总结

| 类别 | 覆盖 S 编号 |
|---|---|
| ✅ 已抓取 | S1, S2, S3, S4（S5/S6/S7a/S8 在 S1 capture 中验证） |
| ❌ POC 无现成工具 | S7b, S9, S10, S11 → probe 阶段在 testbed/ 里写对拍脚本 |

## 来源

- POC 仓库：`/home/shudong/project/3rtparty_AS_POC` @ `4ddf3df3`
- 抓取工具：`tools/capture_call.py`（S1/S2/S3）；testbed 下的 `capture_abandon.py`（S4，复用 POC run_call API）
- 抓取日期：2026-09-28
