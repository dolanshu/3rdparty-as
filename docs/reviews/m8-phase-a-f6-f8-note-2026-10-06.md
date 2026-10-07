# M8 Phase A F6/F8 记录（2026-10-06）

> 上游：[`callload-remediation-adjudication-2026-10-05.md`](callload-remediation-adjudication-2026-10-05.md)
> （F6 `部分修复`，F8 `未闭合`）。本记录不改写该文件，只记录新状态。
> 计划依据：[`2026-10-06-m8-release-candidate-plan.md`](../handoff/2026-10-06-m8-release-candidate-plan.md) §4 Phase A（A-2/A-3）。

## 1. 评审对象

M8 Phase A 项 A-2（F8：结构化 SIP 运行时日志）与 A-3（F6：transport close 回调尾项），
分支 `master`，交付物见 §4。

## 2. 评审日期与评审人

- 日期：2026-10-06
- 评审人：agent（writing subagent；待维护者 adjudication 确认）

## 3. 评审结论

| ID | 结论 | 新状态 |
|----|------|--------|
| F8 | 有条件通过 | `字段契约已落地`：`resip_runtime_log_contract.py` + 契约测试 + acceptance 契约文档 + `emit_native_log_event` JSON 富化；C++→Python JSON 回调 defer 到 post-RC（计划允许的二选一路径） |
| F6 | 有条件通过（documented limitation，接受风险待裁决） | `documented limitation`：注册上限 + dialog 终止注销已验证存在；native transport-close 回调缺席是设计现状（reSIProcate Transport close hook 未接入，RC 范围外）；连接经 dialog 终止回收 + 指纹 LRU 淘汰兜底 |

## 4. 发现的问题清单与对应修改

1. **F8 — C++ 仍以 cout/cerr 为主。** 修改：冻结 `RESIP_RUNTIME_*` 行为字段契约
   （`platform/src/as_platform/sip/resip_runtime_log_contract.py`，`# See ADR-0005`/`# See ADR-0019`），
   `platform/tests/test_resip_runtime_log_contract.py`（13 例，格式漂移即红），
   `docs/acceptance/m8-resip-runtime-log-contract.md`（中英文：字段表/示例/富化说明），
   `resip_runtime.py` +~30 行 `emit_native_log_event` JSON 富化。REQ-NF-13 断言挂此契约。
2. **F6 — 无 native transport-close 回调。** 核查（`runtime_module.cxx` 全文 grep）：
   无 `onConnectionClosed` / `ConnectionTerminated` / Transport close 回调接入。
   现状：指纹表 2048 上限 LRU 淘汰（`ListenerState::storePeerFingerprint`，
   已补 `// See ADR-0019` 注释说明 close 回调缺席）；`TransportIngressGate`
   连接注册 4096 上限溢出减半（`ingress.py::register_connection`）；
   注销路径为 dialog 终止 piggyback（C++ `onTerminated` → Python terminated 回调 →
   `ResipRuntimeListener.notify_leg_terminated` → `on_connection_closed` 即
   `gate.unregister_connection`，见 `sip_stack_service.py` 接线）。
   长连接无 dialog 终止时仅靠上限淘汰回收——RC 接受为已知局限，不做 reSIProcate
   Transport close hook（超出 RC 范围）。
3. **REQ 影响：** 无直接 numbered-REQ 断言受影响（transport hygiene，非编号 REQ 条目）；
   作为 M8 退出评审的 operational note 记录。

## 5. 修改后的确认签字

| 项 | 签字 | 日期 | 备注 |
|----|------|------|------|
| F8 字段契约 + 测试绿 | agent 自检（`make gate` 层见 handoff 报告） | 2026-10-06 | 待维护者 adjudication |
| F6 documented limitation + 风险接受 | 待维护者裁决 | | RC 放行条件 |
