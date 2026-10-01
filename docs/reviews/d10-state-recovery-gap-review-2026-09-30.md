# D10 状态恢复设计缺口评审记录

- **评审对象**：reSIProcate DUM / `SipStack` 进程重启恢复路径（D10、E5、REQ-NF-1）
- **日期**：2026-10-01
- **评审人**：GitHub Copilot（AI agent）
- **上游版本**：reSIProcate 1.14.0，commit `632e215c2ca9aee5416bfe1808851ea6fa380044`
- **结论**：**不通过 / 未解决（Not passed / unresolved）；需维护者裁决**

## 范围与证据

本记录评审两个隔离的双进程重启探针，以及它们对 D10/REQ-NF-1 当前验收的证明边界。现行基线按 [`test-plan.md`](../acceptance/test-plan.md)：基本呼叫完成 ACK 交换后 kill/restart AS，再由上游发送 in-dialog BYE，验证 replacement 将 BYE 路由到对端且 Redis 有完整 dialog record。该项测试 SIP dialog/control-state continuity，不测试 RTP/media interruption 或恢复；replacement 需要处理新 BYE transaction，不需要恢复已完成的 INVITE transaction。实验使用 uv CPython 3.10.21；全部构建产物、日志均在 `/tmp`，没有修改仓库代码。

- **UAC DialogSet 重建 hook**：`/tmp/as-resip-dum-process-restart/RESULTS.md`。Phase A 建立 dialog 后进程退出；Phase B 创建新的 SipStack+DUM，使用 `makeInviteSession(..., DialogSetId, ...)` 并手工恢复 To-tag、Route、remote target、递增 CSeq，在相同 Call-ID/tags 下发送 in-dialog re-INVITE，收到 200 并 ACK。此结果仅证明一个 UAC DialogSet 重建 hook 可行；没有恢复旧 `InviteSession` 或 `SipStack` transaction，也没有证明产品 `CallController` 映射恢复。当前 baseline 的 INVITE transaction 已在 ACK 后完成，因此旧 transaction 未恢复不构成当前 gate 的失败；探针没有测试 RTP/media。
- **UAS 同 dialog 请求**：`/tmp/as-resip-dum-uas-restart/RESULTS.md`。Phase A 建立 UAS dialog 并完成 200/ACK 后退出；fresh DUM 收到格式正确的同 dialog BYE，实际返回 481。对应源码路径中，带 To-tag 请求按 `DialogSetId` 查询 DUM 私有 map；缺少旧 dialog-set 时返回 481。没有找到公开的 UAS DialogSet/session rehydrate API。该 BYE 正是当前 D10 基线要求 replacement 处理的请求；481 使 SIP dialog/control-state baseline 失败。此探针未验证 Redis 完整记录，也没有测试 RTP/media。

UAS 探针说明默认 DUM 的此重启路径失败，但不证明自定义 DUM patch/extension 不可能。该 481 是当前 established-dialog BYE acceptance 的失败证据，不是媒体中断证据。两个探针均未恢复 `SipStack` transaction runtime；当前基线不要求恢复已由 ACK 完成的 INVITE transaction。进程在 pending INVITE/CANCEL/final-response/2xx-ACK 时崩溃后的 transaction recovery 尚未测试，属于现行范围外的可选扩展。产品 `CallController` 的两腿映射恢复也未验证；单独把业务上下文存入 Redis 不构成这些状态可恢复的证据。

## 裁决与待决事项

D10 **不通过 / 未解决**，因为当前 ACK-established-dialog baseline 中，replacement 的 fresh DUM 对上游同 dialog BYE 返回 481，未能完成要求的 BYE peer routing；完整 Redis dialog record 也未由该 probe 验证。UAC hook 不能代表 UAS dialog/session 或产品跨腿状态恢复。当前基线的 INVITE/ACK transaction 已完成，故未恢复旧 transaction 不是 D10 失败原因；pending transaction recovery 仅属未测试的可选扩展。REQ-NF-1 保持原文和硬验收属性；本记录不放宽需求、不接受架构 workaround，也不替换 ADR-0019 已选定的 reSIProcate 栈。该结论只针对 SIP control-state recovery，不涉及 RTP/media。

维护者须明确选择后续路径：

1. 设计/实现能满足当前 ACK-established-dialog BYE/Redis baseline 的 UAS/dialog 与 `CallController` recovery mechanism，并按 test plan 验证 BYE 路由和完整 Redis dialog record；或
2. 启动正式 ADR/design review，评估现有产品架构与 REQ-NF-1 当前 established-dialog baseline 的冲突及可行架构边界。若要加入进程崩溃时仍在途的 INVITE/CANCEL/final-response/2xx-ACK recovery，须另行修改/扩展 requirement 与 test plan 并由维护者裁决；本文不选择 Redis、PostgreSQL 或其他 recovery store/design。

这两项是待裁决选项，不是已接受的方案。完成维护者决定前，D10、E5、REQ-NF-1 与 M7/M8 recovery acceptance 均保持阻塞。

## 签字

| 项 | 值 |
|---|---|
| 评审结论 | 不通过 / 未解决；维护者裁决待定 |
| 维护者决定 | 待填：自定义 UAS recovery/extension + transaction 证明，或正式 ADR/design review |
| 维护者签字 | 待填 |