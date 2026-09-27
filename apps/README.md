# `apps/` — the signalling plane (layer ①)

One directory per use case, one process per use case. A process boundary is the
fault boundary, the independent scaling boundary and the independent rollout
boundary at the same time.

| Directory | Use case | Legs |
|---|---|---|
| `translation/` | number translation and routing | two-legged B2BUA |
| `anti-fraud/` | caller screening | single-leg, `608 Rejected` (RFC 8688) |

## Rules

- **Stateless.** All session, rate and reputation state lives in Redis through
  the `StateStore` seam. A pod may be killed at any time and lose nothing but
  the calls it is draining (ADR-0002).
- **Business decisions are pure functions.** No sockets, no clock, no global
  state inside the decision module. That is what makes TDD cheap here.
- **SIP mechanics are not reimplemented.** They come from `platform/`.
- An app must never import another app.

## Open decision

Where a second (Go) implementation of the same use case lives
(`apps/<case>/{py,go}` vs a separate tree) is settled by ADR-0012 before the Go
spike starts, not now.
