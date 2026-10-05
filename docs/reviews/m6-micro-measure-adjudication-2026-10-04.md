# M6 micro-measure adjudication (2026-10-04)

> **SUPERSEDED for milestone purposes (2026-10-05).** Premature relative to agreed sequencing (M2 must complete before M6 milestone credit). Retain as WIP engineering reference only; does not advance M6 status in [`plan.md`](../plan.md). See [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md).

## Object

Engineering adjudication of M6 **step 3 precursor**: a short real-socket micro measurement from `as_load` to native `resip_probe` external UAS (reSIProcate 1.14.0 @ `632e215c`), with harness `summary.json` and a basic probe-side RSS snapshot in `resources.json`. Cross-ref: [`testbed/load/README.md`](../../testbed/load/README.md) suggested sequence §3, [`m6-resip-probe-smoke-review-2026-10-04.md`](m6-resip-probe-smoke-review-2026-10-04.md).

## Spec (plan)

Precursor evidence toward formal M6 measurement (target-side resource observation and reproducible evidence bundles). **Not** O1 publication, not milestone completion, not REQ acceptance.

## Evidence

- Script: `testbed/load/scripts/m6-resip-probe-micro-measure.sh` (5s injection, configured load model; `summary.json` + `resources.json` with probe PID RSS).
- Performance test: `testbed/load/tests/test_resip_probe_micro_perf.py` (`@pytest.mark.performance`; skips when probe binary absent; asserts `established_sessions > 0` only).

## Findings

1. **Accept (engineering precursor).** Extends smoke with a bounded multi-worker run and records load-generator summary plus a minimal probe RSS observation. Aligns with README §3 (target-side resource note) as a first slice — not saturation or formal capacity study.
2. **D8 open.** No REQ/contract trace added; requirement closure and maintainer signoff remain blocked per prior M6 reviews.
3. **No published O1.** Harness rates and RSS are lab observations only; AGENT.md §2 forbids treating them as product capacity claims.

## Verdict

**Accept** for the M6 micro-measure engineering precursor only.

## Milestone status

**M6 is NOT milestone-complete.** Formal O1 measurement, C6 window evidence at scale, and maintainer capacity adjudication remain **open**.

## Adjudication

Maintainer sign-off **pending** (same bar as smoke slice).

## Limits

Not M6 completion, not O1 numbers, not HPA thresholds, not product-path acceptance, not REQ closure.
