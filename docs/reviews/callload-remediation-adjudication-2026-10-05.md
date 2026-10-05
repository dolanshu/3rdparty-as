# callload 评审修复 — 裁决记录（2026-10-05）

> 输入：[`callload-m2-m6-m7-demo-branch-review-2026-10-05.md`](callload-m2-m6-m7-demo-branch-review-2026-10-05.md)  
> 计划：[`../handoff/2026-10-05-callload-review-response-plan.md`](../handoff/2026-10-05-callload-review-response-plan.md)  
> 验证：本机 `make gate`（964 passed, 2 skipped）；native 集成需 `make m2-platform-resip-build` + CI `m2-platform-resip` job。

| ID | 状态 | 证据 |
|----|------|------|
| F1 | 已修复 | `bind_address`/`advertised_address` 贯穿 C++ + `transport_env.py` |
| F7 | 已修复 | `AS_TLS_*` / `AS_PEER_*` + `SipStackService.from_env` |
| F10 | 已修复（内容） | 故事 C 话术 + `pre-m8-demo-review-plan.md` F10 对账段 |
| F9 | 部分修复 | `native_extensions.py` + 本地 `make m2-platform-resip-build`；**origin CI workflow 未变更**（push 需 PAT `workflow` scope） |
| F4 | 已修复 | `map_outbound_failure_to_inbound_status` + C++ `mapUpstreamFailureStatus` |
| F3 | 已修复（FORWARD 路径） | `buildUacLegDict` + `sip_stack_service` `uac_leg` |
| F2 | 已修复 | recovery BYE Contact + `Route` 回放 |
| F5 | 已修复 | fingerprint map 2048 上限淘汰 |
| F6 | 部分修复 | connection 注册上限 + dialog 终止注销；无 native transport close 回调 |
| F8 | 未闭合 | C++ 仍以 cout/cerr 为主；M8 前需 JSON 回调或宏契约 |
| F11 | 维护者 | 不纳入 agent 队列 |
| F12–F18 | 已修复 | 见各条目 CHANGELOG 0.2.0 |

**仍不构成**：M2/M6/M7 里程碑退出、REQ 全绿、客户 NF-1 正式签收。

---

## 合入 master（2026-10-06）

| 项 | 状态 |
|----|------|
| 工程修复（上表） | 已记录；F8 开放、F6 部分 |
| F9 CI workflow | **未 push** — `.github/workflows/ci.yml` 保持 `origin/master`；blocking job 待 PAT `workflow` scope |
| 维护者 merge 清单 | [`../handoff/2026-10-06-callload-merge-to-master.md`](../handoff/2026-10-06-callload-merge-to-master.md) |
| 合入 master @ SHA | **`764aa75`**（2026-10-06；工程合入 `4b4566b`） |
