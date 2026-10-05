# ADR-0022 acceptance review — B2BUA control layer (2026-10-05)

> **Subject:** Accept ADR-0022 after M2 product ingress/runtime and start of M7 `CallController` implementation  
> **Authority:** [`adr-0022-b2bua-control-review-2026-09-30.md`](adr-0022-b2bua-control-review-2026-09-30.md); [`m2-engineering-closure-adjudication-2026-10-05.md`](m2-engineering-closure-adjudication-2026-10-05.md); [`plan.md`](../plan.md) §4 M7 row  
> **ADR:** [`0022-resiprocate-b2bua-control.md`](../architecture/adr/0022-resiprocate-b2bua-control.md)

## Scope

This review records **acceptance of the architectural decision** (DUM + product `CallController` layering), not REQ acceptance, not M7 milestone exit, and not D10/REQ-NF-1 closure.

## Evidence reviewed

| Item | Location / note |
|------|-----------------|
| Prior technical review (conditional) | [`adr-0022-b2bua-control-review-2026-09-30.md`](adr-0022-b2bua-control-review-2026-09-30.md) |
| M2 product ingress + `decide()` path | `ResipRuntimeListener`, `platform/tests/test_resip_runtime_integration.py` |
| M7 `CallController` pure state machine | `platform/src/as_platform/sip/call_controller.py`, `platform/tests/test_call_controller.py` |
| Minimal product two-leg native slice | `platform/native/resip_two_leg/`, D9 pattern; not full adapter API |
| D10 / recovery | **Still not passed** — see [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md) |

## Findings

- Responsibility split (SipStack → DUM → `CallController` → Python `decide()`) remains consistent with ADR-0019 and HLD/LLD §5.1.
- M2 stack-binding closure authorizes product runtime work; ADR-0022 acceptance authorizes **continued M7 product control-layer code** without selecting the production C++/Python bridge API.
- Accepting ADR-0022 does **not** weaken REQ-NF-1, does **not** claim D10 passed, and does **not** release K2.

## Recommendation

**Accept ADR-0022** with the 2026-10-05 amendment (M2 ingress/runtime present; `CallController` implementation begins M7).

## Sign-off

- Acceptance review recorded: 2026-10-05  
- Maintainer sign-off on ADR-0022 acceptance: **pending**
