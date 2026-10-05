# M6 resip_probe external UAS smoke review (2026-10-04)

> **SUPERSEDED for milestone purposes (2026-10-05).** Premature relative to agreed sequencing (M2 must complete before M6 milestone credit). Retain as WIP engineering reference only; does not advance M6 status in [`plan.md`](../plan.md). See [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md).

## Object

Independent engineering review of M6 step 2: real-socket smoke cascade from `as_load` to native `resip_probe` in external UAS mode (reSIProcate 1.14.0 @ `632e215c`). Cross-ref: [`testbed/load/README.md`](../../testbed/load/README.md) suggested sequence §2, [`m6-harness-current-review-2026-10-03.md`](m6-harness-current-review-2026-10-03.md).

## Spec (plan)

M6 harness against the selected stack (ADR-0019 reSIProcate) with real UDP sockets; smoke only — not O1 capacity measurement or acceptance.

## Evidence

- Script: `testbed/load/scripts/m6-resip-probe-smoke.sh` (`resip_probe --external S1` + `uv run python -m as_load` with `stack=resip-probe`, `stack-version=1.14.0-632e215c`).
- Integration test: `testbed/load/tests/test_resip_probe_smoke.py` (`@pytest.mark.integration`; skips when probe binary absent).

## Findings

1. **Pass (engineering slice).** One-call loopback path establishes a session (`established_sessions >= 1`) over real UDP between harness and native DUM UAS; aligns with authorized M6 smoke scope.
2. **D8 open.** No REQ/contract trace added; requirement closure and maintainer signoff remain blocked per prior M6 reviews.
3. **Not capacity evidence.** No CPS/concurrency/latency targets, no target-side resource telemetry, no saturation observation.

## Verdict

**Pass** for the M6 resip_probe smoke engineering slice only.

## Adjudication

Maintainer sign-off **pending**.

## Limits

Not M6 completion, not O1 numbers, not product-path acceptance, not REQ closure. SIPp smoke remains separate interoperability evidence only.
