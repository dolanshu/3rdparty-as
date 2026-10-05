# M2 adapter boundary adjudication (2026-10-04)

> **Subject:** Handoff P1 — reconcile M2 runnable endpoint vs product DUM / `CallController` / Python bridge (D9)  
> **Authority:** [`docs/handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md) §Prioritized M2 Continuation Plan **P1**  
> **Related:** [ADR-0019](../architecture/adr/0019-sip-stack-selection.md) (accepted stack), [ADR-0022](../architecture/adr/0022-resiprocate-b2bua-control.md) (**proposed**, not accepted here)

Does **not** accept ADR-0022 as fully accepted. Does **not** close M2, M7, E1/E4/E5, or REQ acceptance.

## Adjudication

| Question | Decision |
|---|---|
| What is M2’s **authorized runnable endpoint** for engineering continuation? | **Testbed native transport path only:** vendor restore + native `SipStack`/DUM smoke via `resip_probe`, **plus** the in-repo **transport-policy seam** (`platform/sip` transport/TLS config and pure peer-matching policy). Runnable proof = `make m2-native` (ends in `make m2-native-smoke`) and existing transport seam unit/contract tests. |
| What is **explicitly not** M2 P0–P1 deliverable? | Product **DUM adapter**, **`CallController`**, production Python/native bridge API, two-leg B2BUA, DUM→`decide()` wiring, and any claim that isolated D9 spikes are the approved integration surface. |
| Who owns product SIP integration and D9 bridge work? | **M7**, subject to existing D9/D10/D11 and E1/E4/E5 gates in `plan.md` §5. |
| Is engineering authorized on the P0 path? | **Yes** — maintainers may treat P0 native repro + policy seam as the approved M2 engineering slice while M2 remains open. |
| Is ADR-0022 accepted? | **No.** Status remains **proposed**. This adjudication records **boundary only** per handoff P1; maintainer must still authorize any production bridge/adapter API before implementation proceeds as product code. |

## Evidence pointers

- P0 repro: [`m2-native-build-matrix.md`](../acceptance/m2-native-build-matrix.md), review [`m2-p0-native-repro-review-2026-10-04.md`](m2-p0-native-repro-review-2026-10-04.md).
- Transport seam: [`m2-native-probe-review-2026-10-04.md`](m2-native-probe-review-2026-10-04.md) (engineering slice; not M2 closure).
- D9 feasibility (non-product): `docs/acceptance/report.md` §D9-D11; does not substitute for M7 integration.

## Maintainer signoff

**Pending** (boundary recorded; does not imply ADR-0022 acceptance or M2 exit).
