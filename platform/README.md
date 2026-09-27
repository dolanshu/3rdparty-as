# `platform/` — the kernel (layer ②)

The shared shell that every AS instance is built on. It contains what is common
to all use cases and nothing that belongs to one of them:

| Concern | Why it lives here |
|---|---|
| Process shell (`main`, `bootstrap`) | one way to start, self-check and shut down an AS process |
| B2BUA state machine (`call_controller`) | the RFC 3261 leg handling every use case needs |
| `decide()` seam | the single point where a use case injects its business verdict |
| `Transport` seam | UDP today, TLS to the S-SBC in production (ADR-0016) |
| `StateStore` seam | in-memory today, Redis in production (ADR-0002) |
| Observability primitives | one OTel-based signal model for every process |

## Hard rule

**This package must never import `apps/*`, `services/*` or `testbed/*`.**
The dependency direction is one-way and is asserted by
`tests/test_library_independence.py`, not by the directory layout.

## Status

Skeleton only. The code arrives through the triage-driven migration in
`docs/migration/triage.md`; nothing is copied in wholesale.
