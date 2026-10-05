# M2→M6 session progress and blockers (2026-10-04)

> Orchestration session on branch `callload`. Engineering slices only; maintainer signoff pending on all review records.

## Completed slices

| Track | Item | Evidence |
|---|---|---|
| M2 P0 | Vendor restore + repo-local native build + UDP S1 smoke | `make m2-native`, `docs/acceptance/m2-native-build-matrix.md`, [`m2-p0-native-repro-review-2026-10-04.md`](m2-p0-native-repro-review-2026-10-04.md) |
| M2 P1 | Adapter boundary (not ADR-0022 acceptance) | [`m2-adapter-boundary-adjudication-2026-10-04.md`](m2-adapter-boundary-adjudication-2026-10-04.md) |
| M2 P4 (partial) | CI job `m2-native-smoke` in `.github/workflows/ci.yml` | Source build on `ubuntu-latest` |
| M6 | `resip_probe` external UAS + `as_load` smoke | `testbed/load/scripts/m6-resip-probe-smoke.sh`, [`m6-resip-probe-smoke-review-2026-10-04.md`](m6-resip-probe-smoke-review-2026-10-04.md) |
| M6 | Micro measurement precursor (no O1 publication) | `m6-resip-probe-micro-measure.sh`, [`m6-micro-measure-adjudication-2026-10-04.md`](m6-micro-measure-adjudication-2026-10-04.md) |

Local gate: `make gate` — 901 passed, 2 skipped (2026-10-04).

## Not complete (explicit)

| Milestone | Gap | Why not closed in this session |
|---|---|---|
| **M2** | P2 runtime TLS/mTLS + peer policy on live connections | Requires product `SipStack` binding / M7 adapter; seam is pure policy today |
| **M2** | P3 REQ-S-3 dual-cert overlap window | Needs runtime cert install + overlap semantics on product transport |
| **M2** | REQ-S-2/3 acceptance, operator PKI, S-SBC | Out of testbed scope |
| **M2** | D3 Redis Sentinel | Still OPEN per plan |
| **M6** | Formal O1 (CPS, concurrency, latency budgets, saturation) | AGENT.md forbids publishing capacity numbers without full measurement; only micro precursor run |
| **M6** | D8 REQ traceability | Maintainer decision still required |
| **M7** | Product DUM / `CallController` / D10 recovery | Unstarted; blocks product E1 |

## Recommended next steps

1. Maintainer signoff on P0/P1/M6 review records.
2. Authorize M7 adapter spike API (ADR-0022) before P2 product wiring.
3. Extend M6: longer runs + target-side metrics + C6 window evidence; then revisit O1 estimate doc §6.
4. Commit/push `callload` when ready (vendor archives + all new files still uncommitted in working tree).
