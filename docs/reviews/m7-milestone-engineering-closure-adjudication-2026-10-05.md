# M7 milestone engineering closure adjudication (2026-10-05)

> **Subject:** M7 **plan-item engineering closure** for implemented slices (control, runtime, D10 groundwork, E1 contract smoke) — **not** M7 milestone exit  
> **Authority:** [`plan.md`](../plan.md) §4 M7 row, §5 D10 M7.1–M7.6; prior slices [`m7-engineering-closure-adjudication-2026-10-05.md`](m7-engineering-closure-adjudication-2026-10-05.md), [`m7-d10-second-pass-review-2026-10-05.md`](m7-d10-second-pass-review-2026-10-05.md)

## Engineering closure (implemented plan items)

| Area | Delivered | Evidence |
|------|-----------|----------|
| M7 control + two-leg | `CallController`, `_resip_two_leg`, runtime `decide()` wiring | Prior closure + `make gate` |
| M7.1–M7.6 D10 slices | RecoveryTU, coordinator, controller restore, checkpoint v2, lifecycle, product integration test | §5 D10 checkboxes; second-pass review |
| E1 contract smoke (tail) | `platform/tests/test_e1_contract_resip_runtime.py` (`@pytest.mark.contract`): product `_resip_runtime` S2-no-match → 404, REQ-F-6 trace | Skips when extension missing |
| Recovery env hook (test-only) | `CallStateRecovery.on_process_start_restore` + `AS_RESIP_RECOVERY_CHECKPOINT_FILE` → optional `RecoveryStackSession` | `test_sip_recovery.py`; `NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED` remains **`False`** (prod shell unwired) |

**Adjudication:** **Accept** as **M7 engineering closure** for the above artifacts. Maintainers may use this baseline for D9 adapter work and expanded E1 replay.

## Explicit deny (unchanged)

| Gate | Verdict |
|------|---------|
| **M7 milestone exit** | **Deny** |
| **REQ-NF-1** / full D10 acceptance | **Deny** |
| **Full E1 S1–S11** on shipping product stack | **Deny** |
| **Operator acceptance** / maintainer milestone sign-off | **Deny** — not requested |

## Remaining open

1. **Wire recovery to production process shell** — env hook is test-only; no automatic restart orchestration in AS main.  
2. **Redis HA** — cluster deployment and failover behavior not proven for checkpoint continuity.  
3. **E1 full replay** — contract suite S1–S11 on `_resip_runtime` / adapter, not single S2 smoke.  
4. **D9** — product C++/Python adapter API.  
5. **D11 / REQ-F-4** — full product SDP wire identity.

## CI / gate

Repository **`make gate`** remains the required pre-merge check. E1 contract test participates in layer ① (`unit or contract`); skips when `_resip_runtime` is not built.

## Second-pass review

See [`m7-e1-contract-review-2026-10-05.md`](m7-e1-contract-review-2026-10-05.md).

## Sign-off

- Milestone **engineering** closure adjudication: 2026-10-05  
- M7 **milestone** sign-off: **not requested** — **open**
