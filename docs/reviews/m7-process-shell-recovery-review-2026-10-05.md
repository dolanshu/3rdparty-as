# M7 process shell + recovery wiring review (2026-10-05)

> **Scope:** `SipStackService`, `__main__.py`, `CallStateRecovery` native restore per loaded checkpoint  
> **Not:** D10 / REQ-NF-1 maintainer sign-off

## Evidence

| Item | Result |
|------|--------|
| `make gate` | Pass |
| `make m2-platform-resip-build` + `make m7-platform-recovery-build` | Pass |
| `test_d10_req_nf1_harness_integration.py` | Pass (`-m integration`) |
| `m6-product-runtime-smoke.sh` | Pass |

## Findings

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | `NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED=True` only when `AS_ENABLE_SIP_RUNTIME=1` + `AS_RECOVERY_CALL_KEYS` schedules coordinator restore that starts `RecoveryStackSession` per loaded checkpoint | Info | **Documented** |
| 2 | Dialog-established native hook deferred to listener loop (avoids DUM/GIL deadlock); harness rewrites UAS local tag from 200 OK To-tag | Engineering seam | **Accepted** |
| 3 | Full D10 baseline (kill/restart AS + real Redis + maintainer env) | Blocker (milestones) | **Open** |

## Recommendation

**Accept** as M7 process-shell engineering slice. **Deny** D10 / REQ-NF-1 closure.
