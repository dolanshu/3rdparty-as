# M2 P2 ingress adjudication (2026-10-05)

> **Subject:** M2 handoff **P2** (partial) — runtime peer-policy enforcement at ingress (Python seam)  
> **Prior review:** [`m2-p2-ingress-runtime-review-2026-10-05.md`](m2-p2-ingress-runtime-review-2026-10-05.md) (**Pass** for P2 slice only)  
> **Authority:** [`handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md) P2; [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md)

## Adjudication

| Item | Verdict |
|------|---------|
| Python `TransportIngressGate` + `reject_plaintext_when_tls_required` + M2 `UdpIngressServer` proof | **Accept** |
| TCP/TLS/mTLS on product reSIProcate accept path | **Open** — requires stack binding calling the same gate API |
| Full P2 (live TLS identity, chain verification, atomic config apply on all transports) | **Open** |
| Maintainer sign-off on P2 | **Pending** |
| M2 milestone closure | **Deny** — P2–P4 incomplete per task register |

## Rationale

The independent review recorded **Pass** for the ingress seam and UDP enforcement proof. Accepting
this slice records the **authorized binding contract** for reSIProcate: consult `check_peer` (and
plaintext helper where applicable) before handing SIP to the kernel. It does **not** accept product
transport adapter completion or REQ-S acceptance.

## Limits

Not REQ acceptance, not CI certification unless separately recorded, not production PKI/mTLS evidence.

## Sign-off

- Engineering adjudication recorded: 2026-10-05  
- Maintainer sign-off: **pending**
