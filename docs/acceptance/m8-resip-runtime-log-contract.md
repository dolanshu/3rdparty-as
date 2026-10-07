# M8 字段契约：reSIProcate 运行时日志（F8 Phase A）

> REQ-NF-13 取证挂载点：JSON 日志 `timestamp/level/trace_id/call_id/direction/method` + metrics/traces 关联（`test-plan.md` §2）。
> 上游裁决：[`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md)（F8 `未闭合` → 本契约落地后转 `字段契约已落地`，C++→Python JSON 回调 defer，见 §5）。

## 1. 背景

C++ 绑定（`platform/native/resip_runtime/runtime_module.cxx`）以 `cout/cerr` 输出 `RESIP_RUNTIME_*` 行为主，
Python 侧此前无结构化解析。本契约把现有 `key=value` 行格式冻结为可断言的字段表，
使 REQ-NF-13 断言有证据可挂（完整 JSON 回调是 post-RC 工作，见 §5）。

## 2. 字段契约表（event → fields → NF-13 映射）

解析器：`platform/src/as_platform/sip/resip_runtime_log_contract.py`
（`parse_resip_runtime_log_line` / `is_resip_runtime_log_line` / `ResipRuntimeLogEvent.to_nf13_fields`）；
测试：`platform/tests/test_resip_runtime_log_contract.py`（`contract` marker，13 例）。

| event（C++ 行位置） | fields | NF-13 映射（`to_nf13_fields`） |
|---|---|---|
| `RESIP_RUNTIME_LISTENING`（`runListener`，udp/tcp/tls 三行） | `address, advertised, udp_port/tcp_port/tls_port` | `level=info`，其余 `None`（无呼叫上下文） |
| `RESIP_RUNTIME_UAC_INVITE_SENT`（`onNewSession` 转发） | `outgoing_call_id, inbound_call_id, route_uri` | `call_id/trace_id=outgoing_call_id`，`direction=outbound`，`method=INVITE` |
| `RESIP_RUNTIME_UAC_NEW_SESSION`（`onNewSession` UAC） | `outgoing_call_id` | 同上（`outbound/INVITE`） |
| `RESIP_RUNTIME_UAC_FAILURE`（`onFailure`） | `outgoing_call_id, status` | 同上（`outbound/INVITE`，`level=info`：下游失败是业务事件） |
| `RESIP_RUNTIME_UAS_FAILURE_MAPPED`（`onFailure` 映射后） | `outgoing_call_id, downstream_status, upstream_status` | 同上（`outbound/INVITE`） |
| `RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD`（`onTerminated` RemoteCancel） | `inbound_call_id` | `call_id/trace_id=inbound_call_id`，`direction=inbound`，`method=CANCEL` |
| `RESIP_RUNTIME_UAS_ANSWER_RELAYED`（`onAnswer` 200 中继） | `outgoing_call_id` | `outbound/INVITE` |
| `RESIP_RUNTIME_RELOAD_CERTIFICATES`（`runListener`） | `detail=invoked`（唯一无 `=` 的固定字面） | `level=info`，其余 `None` |
| `*_ERROR / *_CALLBACK_ERROR / *_CORRELATION_MISS / *_WORKER_ERROR`（各 `cerr` 点） | `message=<单字>` 或对应 id 字段；**含空格的 message 行按格式漂移 fail-closed（返回 `None`）** | `level=error`，`call_id/trace_id` 取 `outgoing_call_id/inbound_call_id`（若有） |

## 3. 示例行

```text
RESIP_RUNTIME_LISTENING address=127.0.0.1 advertised=127.0.0.1 udp_port=5060
RESIP_RUNTIME_UAC_INVITE_SENT outgoing_call_id=out-1@127.0.0.1 inbound_call_id=in-1@127.0.0.1 route_uri=sip:downstream@127.0.0.1:5070
RESIP_RUNTIME_UAC_NEW_SESSION outgoing_call_id=out-1@127.0.0.1
RESIP_RUNTIME_UAC_FAILURE outgoing_call_id=out-1@127.0.0.1 status=486
RESIP_RUNTIME_UAS_FAILURE_MAPPED outgoing_call_id=out-1@127.0.0.1 downstream_status=486 upstream_status=486
RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD inbound_call_id=in-1@127.0.0.1
RESIP_RUNTIME_UAS_ANSWER_RELAYED outgoing_call_id=out-1@127.0.0.1
```

## 4. Python 侧 JSON 富化

`platform/src/as_platform/sip/resip_runtime.py::emit_native_log_event`（~30 行新增）：
解析一行 native 行 → 用 `to_nf13_fields()` 补 `timestamp`（`time.time()`，可注入）、
`level/trace_id/call_id/direction/method`（`trace_id` 可覆盖）→ 经
`as_platform.sip.resip_runtime.native` logger 输出 `json.dumps` 单行。
native 行本身不经过 Python logging，因此富化发生在**采集转发侧**（抓 worker 控制台后逐行调用）；
REQ-NF-13 断言挂在此 JSON 输出上，字段稳定性由契约测试守卫（C++ 改名/改键即红）。

## 5. 与 F8 裁决的关系

- 本契约关闭 Phase A 对 F8 的要求（“C++→Python JSON 回调 **或** 字段契约 + 测试”二选一，走后者）。
- 完整的 C++→Python JSON 回调（native 侧直接调 Python 日志回调，含 `timestamp/level/trace_id`
  原生注入）**defer 到 post-RC**，若维护者要求再做；届时本契约的事件/字段表即回调 payload 的 schema 起点。
