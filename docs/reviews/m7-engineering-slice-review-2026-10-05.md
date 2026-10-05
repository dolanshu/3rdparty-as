# M7 engineering slice review (2026-10-05)

> **Subject:** First M7 product control-layer slice (ADR-0022 acceptance + `CallController` + minimal two-leg native)  
> **Authority:** [`plan.md`](../plan.md) §4 M7; handoff M7 engineering authorization via ADR-0022 acceptance

## Deliverables in scope

| # | Deliverable | Artifact |
|---|-------------|----------|
| 1 | ADR-0022 **Accepted** + amendment | [`0022-resiprocate-b2bua-control.md`](../architecture/adr/0022-resiprocate-b2bua-control.md); [`adr-0022-acceptance-review-2026-10-05.md`](adr-0022-acceptance-review-2026-10-05.md) |
| 2 | Python `CallController` | `platform/src/as_platform/sip/call_controller.py`; `platform/tests/test_call_controller.py` |
| 3 | Minimal native two-leg | `platform/native/resip_two_leg/`; `platform/tests/test_resip_two_leg_integration.py` (`-m integration`; requires `make m7-platform-two-leg-build`) |
| 4 | D10 honesty | [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md) |
| 5 | Plan M7 row | **进行中** in [`plan.md`](../plan.md) §4 |

## What this slice is

- Pure in-process **leg correlation** and **FORWARD/REJECT** effect generation for the adapter to execute (no sockets in the controller).
- A **product-path** copy of the D9 two-leg 486 experiment, built via CMake under `platform/native/resip_two_leg/`, with threaded UDP peer fixture coverage in integration tests.

## What this slice is not

- Not production DUM adapter API selection (D9 still open).
- Not `CallController` wired into `_resip_runtime` callbacks.
- Not D10, E5, REQ-NF-1, REQ-F-4, E1, forks, CANCEL races, or M7 milestone sign-off.
- Not RecoveryTU / Redis recovery product integration.

## Gate

Repository **`make gate`** (lint, type, unit + contract) is the required pre-merge check for this slice. Native two-leg integration is **optional** in gate (integration marker; skip when extension not built).

## Recommendation

**Accept** as an M7 **engineering slice**; keep D10 and milestone gates **open**.

## Sign-off

- Slice review recorded: 2026-10-05  
- Maintainer sign-off on M7 milestone: **not requested**

---

## Second-pass addendum (2026-10-05, M7 continuation)

| # | Addition | Assessment |
|---|----------|------------|
| 1 | `ResipRuntimeListener` wires `decide()` → `CallController` on non-`accept_all_invites` path | **Accept** — reject status preserved (e.g. 404); FORWARD registers controller state; product `_resip_runtime` still returns 500 for outbound until UAC binding exists |
| 2 | `notify_outbound_response` / `notify_leg_terminated` on listener | **Accept** — minimal hooks; native callbacks not yet attached |
| 3 | `as_platform.sip.recovery.CallStateRecovery` + unit tests | **Accept** — matches testbed `CallStateCheckpointRepository.load`; native restore explicitly **not** implemented |
| 4 | Engineering closure adjudication | [`m7-engineering-closure-adjudication-2026-10-05.md`](m7-engineering-closure-adjudication-2026-10-05.md) — **not** milestone exit |
| 5 | CI `m7-two-leg` job (optional) | See closure doc — runs two-leg integration after platform resip job when present |

**Unchanged limits:** D10, REQ-NF-1, D9, E1, M7 milestone sign-off remain **open**. Recommendation: **Accept** continuation as M7 engineering only.
