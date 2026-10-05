# M7 engineering closure adjudication — control layer slice (2026-10-05)

> **Subject:** M7 **CallController + two-leg + runtime wiring** engineering closure, not M7 milestone exit  
> **Authority:** [`plan.md`](../plan.md) §4 M7 row; [`m7-engineering-slice-review-2026-10-05.md`](m7-engineering-slice-review-2026-10-05.md); [`m7-engineering-slice-adjudication-2026-10-05.md`](m7-engineering-slice-adjudication-2026-10-05.md)  
> **Acceptance report cross-ref:** [`report.md`](../acceptance/report.md) §「M7 control-layer engineering closure（2026-10-05）」

## Scope of this closure

This adjudication bundles the **authorized engineering path** for continuing M7 work on:

| Layer | Delivered slice |
|-------|-----------------|
| Pure Python control | `CallController` + unit tests in gate |
| Minimal native two-leg | `platform/native/resip_two_leg/` + `test_resip_two_leg_integration.py` (`make m7-platform-two-leg-build`) |
| Product runtime wiring | `ResipRuntimeListener` non-`accept_all_invites` path: ingress → `decide()` → `CallController` → SIP status; `notify_outbound_response` / `notify_leg_terminated` hooks for future native callbacks |
| D10 product hook (groundwork) | `as_platform.sip.recovery.CallStateRecovery.on_process_start_restore` via `CallStateCheckpointRepository.load`; `NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED = False` |
| ADR / honesty | ADR-0022 **accepted** with amendment; [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md) unchanged |

## Adjudication

| Item | Verdict |
|------|---------|
| First M7 slice (`CallController` + `_resip_two_leg`) | **Accept** — prior slice adjudication stands |
| `CallController` wired into `ResipRuntimeListener` (reject path + forward state registration) | **Accept** (engineering slice) |
| `CallStateRecovery` Python load contract | **Accept** (unit-tested hook only) |
| Native `on_process_start_restore` / DUM rehydrate | **Deny** — not implemented |
| D10 / REQ-NF-1 | **Deny** — see [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md) |
| D9 adapter API / full E1 | **Open** |
| **M7 milestone exit** | **Deny** |

## Rationale

The first slice proved leg correlation and one native 486 branch in isolation. This continuation places the **same decision path** on the product `_resip_runtime` listener so inbound INVITEs update `CallController` before the native binding returns a status code. FORWARD still returns 500 on `_resip_runtime` until outbound UAC wiring lands on the product extension (two-leg behavior remains on `_resip_two_leg`). Recovery loads typed checkpoints the same way as testbed Phase B but does not rehydrate DUM or controller context.

Accepting this **engineering closure** means maintainers may treat these artifacts as the baseline for D10 blockers (M7.1–M7.6), adapter selection, and full E1 — **not** as REQ acceptance or milestone sign-off.

## Remains open

1. **M7.1–M7.6** — product recovery, non-blocking Redis continuation, controller restoration, fencing, TTL lifecycle, D10 test-plan gate per [`plan.md`](../plan.md) §5.  
2. **D9** — production C++/Python bridge API.  
3. **D11 / REQ-F-4** — full product SDP wire identity.  
4. **E1 / E4 / E5** — protocol behavior and restart semantics on the shipping stack.  
5. **Maintainer signature** — engineering closure recorded **pending**; M7 milestone sign-off **not requested**.

## CI note

Optional job **`m7-two-leg`** runs after **`m2-platform-resip`** when the workflow includes it: native two-leg build + `test_resip_two_leg_integration.py`. If job duration or flake rate is unacceptable, maintainers may remove the job and document skip here; gate remains `make gate` + existing M2 platform job.

## Limits

Not REQ acceptance, not D10 closure, not K2 release. CI green on `m7-two-leg` (when enabled) certifies the repository repro path for that integration test only.

## Sign-off

- Engineering closure adjudication recorded: 2026-10-05  
- Maintainer sign-off on M7 control-layer slice: **pending**  
- Maintainer sign-off on **M7 milestone**: **not requested** — explicitly **open**
