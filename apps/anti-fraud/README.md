# `apps/anti-fraud/` — anti-fraud AS

Single-leg. It screens the caller and either relays the call or answers
`608 Rejected` (RFC 8688) itself. It never originates a second leg.

**In scope here:** the screening verdict, expressed as a pure function.

**Not in scope here:** rate windows and reputation as process state. They move to
Redis with the rest of the run state (ADR-0002), because a replica that can be
killed at any time cannot hold a caller's rate window in its memory.

## Constraint that shapes this use case

The verdict must remain **acceptable under a Redis split-brain window**: during a
Sentinel failover the rate window may double-count. The design accepts a bounded
inaccuracy rather than a hard failure — see risk R5 in
[`../../docs/architecture/新系统整体架构.md`](../../docs/architecture/新系统整体架构.md).

## Status

Skeleton. The verdict function is written test-first.
