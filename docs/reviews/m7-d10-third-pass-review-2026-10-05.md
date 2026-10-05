# M7/D10 third-pass review (2026-10-05)

> **Follows:** [`m7-d10-second-pass-review-2026-10-05.md`](m7-d10-second-pass-review-2026-10-05.md)

## Fixes in this pass

| Area | Change |
|------|--------|
| Product shell | `SipStackService` + `__main__.py` (`AS_ENABLE_SIP_RUNTIME=1`) |
| Native runtime | Optional `on_dialog_established` / `on_dialog_terminated`; deferred notify on listener loop |
| Restore | `CallStateRecovery` starts `RecoveryStackSession` per loaded checkpoint; `NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED=True` (scoped to shell restore path) |
| Harness | `test_d10_req_nf1_harness_integration.py` + `scripts/d10-req-nf1-harness.sh` |
| CI | `m7-recovery` job runs harness integration test |

## Test results (2026-10-05)

| Command | Result |
|---------|--------|
| `make gate` | Pass (944 unit/contract) |
| `make m2-platform-resip-build` | Pass |
| `make m7-platform-recovery-build` | Pass |
| `uv run pytest platform/tests/test_d10_req_nf1_harness_integration.py -m integration -q` | Pass |
| `uv run pytest platform/tests/test_d10_product_recovery_integration.py platform/tests/test_resip_runtime_integration.py -m integration -q` | Pass |
| `bash testbed/load/scripts/m6-product-runtime-smoke.sh` | Pass |

## Verdict

**Accept** third-pass engineering alignment between product shell and harness. **D10 / REQ-NF-1 remain not passed** per [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md).
