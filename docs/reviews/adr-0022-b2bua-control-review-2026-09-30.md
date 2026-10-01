# ADR-0022 技术评审记录

- **日期**：2026-09-30
- **评审人**：GitHub Copilot（AI agent）
- **结论**：有条件技术通过（仅限职责划分；D10 不通过 / 未解决）；维护者正式评审与签字待完成

## 评审范围与证据

评审 ADR-0022 对 reSIProcate DUM 与产品 `CallController` 的职责划分、需求追溯、证据边界及未决门禁，并审阅用户提供的 [`resiprocate-dum-b2bua.md`](../architecture/resiprocate-dum-b2bua.md)。核对了 reSIProcate 1.14.0（commit `632e215c2ca9aee5416bfe1808851ea6fa380044`）的 DUM API/状态行为、`BUILD_PYTHON` 语义、E1 导入失败记录、native S1/S4 本地自环 smoke，以及 native TLS S1 失败记录。

## 发现

- DUM 被限定为协议 session/dialog/transaction 机制；跨腿语义映射和 Python 决策调用归产品 `CallController`，未把 DUM 描述为完整产品 B2BUA。
- 不重复实现事务重传与定时器，并明确回调非阻塞要求。
- Python/C++ 集成方式没有预先选定；native S1/S4 仅记为 smoke，不冒充产品 E1 或需求验收。
- ADR-0002 的外置状态表述与 REQ-NF-1 硬要求，与 DUM 活协议对象恢复能力之间的缺口及 E5 未验证状态均明确保留。
- 用户提供的设计笔记保留了职责分层洞见，但其示例并非可靠 API 契约；需明确更正的 1.14.0 源码事实如下：
	- `onNewSession` 的两个重载分别为 `(ClientInviteSessionHandle, OfferAnswerType, const SipMessage&)` 和 `(ServerInviteSessionHandle, OfferAnswerType, const SipMessage&)`，不是示例中的两参数形式；`onProvisional`/`onFailure` 为 client-session 回调，`onConnected` 有 client 与通用/server 重载，`onTerminated` 接收 reason 和可选关联消息；不存在 `InviteSessionHandler::onCancel`。
	- `makeInviteSession(...)` 返回待发送的 `shared_ptr<SipMessage>`，session handle 由后续 DUM 回调提供。
	- `ServerInviteSession` 没有 `cancel()`；初始 UAS INVITE CANCEL 时 DUM 对 CANCEL 回 200、对 INVITE 回 487，并以 `RemoteCancel` 通知终止。controller 仍负责相反 UAC 腿与清理/竞态协调。
	- `InviteSession::end()` 是 BYE；client early state 的 `end()` 在此版本也走 BYE 路径。具体取消 API 待 adapter spike 与竞态测试，不据伪代码定案。DUM 有 RFC session-timer 支持，协议 timer 不应统称为应用管理。
	- 两腿关联用内部逻辑呼叫 key/session handles，不能统一 Call-ID（REQ-F-2）。
- 初审时 REQ-F-4 SDP body 字节恒等尚无线上证据；2026-10-01 的 D11 有限样本比较已通过，但 `Contents` 的提取/克隆及未修改回调仍不能证明产品路径 wire identity。完整 adapter、更多边界输入与 review 未完成，故 REQ-F-4 acceptance 仍待定。
- 2026-10-01 补充的 D9 隔离探针显著推进了 native bridge 可行性：primitive CPython callback、真实 DUM→Python `decide()`→404（异常为 500）和一条两腿 486 分支均有实测。但这不是产品 adapter/API，forking、final-response race 与完整 E1 仍未实现/验收。证据：`/tmp/as-resip-python-bridge-spike/RESULTS.md`、`/tmp/as-resip-dum-python-slice/RESULTS.md`、`/tmp/as-resip-dum-two-leg-spike/RESULTS.md`。
- D11 有限 native DUM on-wire 样本现通过：143/233-byte offer、230-byte S1 offer及一个 distinct 238-byte answer均在被测两腿间保持字节恒等。此前 S1 230-byte answer 恰与 offer 相同，不单独算 distinct-answer 证明。完整 adapter、更多边界输入及 review 仍缺，REQ-F-4 不得标为通过。证据：`/tmp/as-resip-dum-sdp-spike/RESULTS.md`、`/tmp/as-resip-dum-sdp-roundtrip/RESULTS.md`、`/tmp/as-resip-dum-final-probes/logs/probe-a-final.log`。
- D10 重启证据不支持通过：UAC `DialogSetId` hook 在两个进程间可重建 re-INVITE，但默认 DUM 的 UAS 同 dialog BYE 在 fresh process 中返回 481；没有恢复旧事务或产品跨腿映射，也未发现公开 UAS rehydrate API。该结果不证明定制扩展不可能。证据：`/tmp/as-resip-dum-process-restart/RESULTS.md`、`/tmp/as-resip-dum-uas-restart/RESULTS.md`。
- 单一 early CANCEL 隔离分支通过，但不覆盖 final-response race 或 forking：`/tmp/as-resip-dum-final-probes/logs/probe-b-final-isolated.log`。这些 spike 均在 `/tmp`，不是产品验收。

## 裁决

技术职责方向与原有生产栈方向一致：ADR-0019 选定的 reSIProcate C++ 保持不变；D9 现在有强可行性证据，但产品 adapter/API 和完整 E1 尚未落地。D11 有限样本的字节比较通过，产品 REQ-F-4 acceptance 仍待补。D10 结论为**不通过 / 未解决**：默认 DUM 的 UAS 同 dialog BYE 重启测试返回 481，REQ-NF-1 未证明，必须由维护者决定自定义 UAS recovery/extension 加 transaction 行为证明，或启动正式 ADR/design review。此有条件技术结论不代表 REQ-NF-1 满足，不构成维护者批准、ADR 接受、代码开工授权、K2 放行或发布验收。

**维护者正式评审 / 签字：待完成**