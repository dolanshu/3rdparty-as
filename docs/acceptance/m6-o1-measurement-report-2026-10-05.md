# M6 O1 internal measurement report (2026-10-05)

> **Audience:** Maintainers / capacity research only  
> **Not:** Public SLA, marketing CPS/concurrency claims, HPA values, or M6 milestone maintainer sign-off (`AGENT.md` §2)

## Methodology

| Item | Value |
|------|-------|
| Host | Developer WSL2/Linux workstation (local run 2026-10-05) |
| Target stack | `as-platform-resip-runtime` / reSIProcate 1.14.0 (`632e215c`) |
| UAS | `platform/tests/fixtures/load_uas_runtime.py` — product `ResipRuntimeListener`, UDP loopback |
| Load generator | `as_load` real UDP sockets (`testbed/load/`) |
| Batch script | `testbed/load/scripts/m6-o1-formal-report.sh` |
| Scenarios | 30s×cps10, 30s×cps20, 60s×cps10, 60s×cps20; hold=0; workers 4 (cps10) or 8 (cps20) |
| Evidence root | `/tmp/as-m6-o1-formal-20261005-092643/` |
| Manifest | `formal_manifest.json` (C6 1s/100s sliding peaks extracted from each `summary.json`) |

Per-scenario artifacts: `summary.json` (counts, setup latency percentiles, `c6_windows`), `resources.json` (UAS VmRSS snapshot), `events.jsonl`.

**C6 interpretation:** 1s sliding peaks are observed window rates over transmitted INVITEs / established sessions. 100s **sliding** peaks are `unavailable` (`coverage_shorter_than_window`) because injection lasted ≤60s. Single-bucket **tumbling** 100s rows exist but do not substitute for a full 100s sliding peak (see harness `c6_window_method` in `summary.json`).

## Measured results (dev host)

Configured injection matched scheduler (`worker_limit_drops=0` everywhere). No saturation run — levels are smoke/formal batch only.

| Scenario | Established | Peak concurrent | Config avg invite CPS | C6 1s sliding peak (invites / established) | Setup p50 / p95 (ms) | UAS RSS (KB) |
|----------|-------------|-----------------|------------------------|---------------------------------------------|----------------------|--------------|
| d30s-cps10 | 300 | 300 | 10 | 11 / 11 | 51.6 / 52.8 | 45068 |
| d30s-cps20 | 600 | 600 | 20 | 21 / 22 | 10.6 / 32.1 | 44588 |
| d60s-cps10 | 600 | 600 | 10 | 11 / 11 | 51.7 / 52.6 | 44480 |
| d60s-cps20 | 1200 | 1200 | 20 | 21 / 22 | 8.0 / 32.4 | 44772 |

At cps20, `unresolved_sessions` equals established count because hold=0 leaves dialogs active until harness teardown (expected for this load model); this is **not** a production call-completion profile.

## O1 research questions (plan §5.1 / M6) — answered on this host only

| Question | Finding on dev host |
|----------|---------------------|
| Can formal real-socket measurement run on the **product** runtime path? | **Yes** — four scenarios completed with evidence bundle. |
| CPS observability (C6) | 1s sliding peaks track configured 10/20 CPS within scheduler granularity; no wall observed. |
| Concurrent sessions | Peak established equals cumulative at hold=0 (300–1200 in batch); not a steady-state concurrency ceiling. |
| Call setup latency | ~52ms p50 at cps10; wider spread at cps20 (p50 ~8–11ms, p95 ~32ms) — loopback UDP, accept-all UAS, not S-SBC path. |
| First saturated resource | **Not observed** — CPU/RSS flat; no target-side telemetry wired (`target_resource_observations.status=unavailable` in harness). |
| HPA / capacity alert thresholds | **Still open** — requires higher load, cluster topology, and maintainer O1 target decision. |
| 容量量级估算 §6 C6 (peak vs hour-average) | Partial: 1s peaks recorded; 100s sliding peaks **not** available at these durations. C1–C5, C7 unchanged (market model gaps). |

## Limits (do not extrapolate)

1. Loopback UDP only; no TLS, no operator PKI, no multi-replica Kubernetes.
2. UAS is a test fixture (`accept` path), not full translation/anti-fraud + Redis + config rules.
3. Load model: zero hold → does not model in-dialog concurrency or BYE completion under load.
4. RSS is a single post-run snapshot, not time-series saturation.
5. Numbers are valid **only** for reproducing this batch on a similar dev machine; they are **not** product capacity guarantees.

## Reproduce

```bash
make m2-platform-resip-build
bash testbed/load/scripts/m6-o1-formal-report.sh
```

## Related reviews

- [`m6-o1-formal-review-2026-10-05.md`](../reviews/m6-o1-formal-review-2026-10-05.md)
- [`m6-engineering-complete-adjudication-2026-10-05.md`](../reviews/m6-engineering-complete-adjudication-2026-10-05.md)
- D8: [`d8-req-nf-15-adjudication-2026-10-05.md`](../reviews/d8-req-nf-15-adjudication-2026-10-05.md)
