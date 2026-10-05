# M7 final engineering adjudication (2026-10-05)

> **Subject:** M7 control-layer + D10 engineering slices through Redis/restart tests  
> **Authority:** [`plan.md`](../plan.md) §4 M7, §5 D10; [`acceptance/test-plan.md`](../acceptance/test-plan.md)

## Done (engineering evidence)

| Area | Artifact | Review |
|------|----------|--------|
| CallController + two-leg native | `call_controller.py`, `resip_two_leg/` | [`m7-engineering-slice-review-2026-10-05.md`](m7-engineering-slice-review-2026-10-05.md) |
| RecoveryTU + coordinator + checkpoints | M7.1–M7.5 slices | `m7-*-review-2026-10-05.md` |
| Product D10 loopback | `test_d10_product_recovery_integration.py` | [`m7-6-d10-product-integration-review-2026-10-05.md`](m7-6-d10-product-integration-review-2026-10-05.md) |
| In-memory REQ-NF-1 harness | `test_d10_req_nf1_harness_integration.py` | [`d10-req-nf1-harness-review-2026-10-05.md`](d10-req-nf1-harness-review-2026-10-05.md) |
| **Real Redis** checkpoint + restore BYE | `test_d10_req_nf1_redis_integration.py` | [`d10-redis-restart-review-2026-10-05.md`](d10-redis-restart-review-2026-10-05.md) |
| **Subprocess kill/restart** + Redis | `test_d10_process_restart_integration.py`, `_d10_child.py` | same |
| E1 contract guards (S1 harness 200, S2 404, S3 603; S4 skip) | `test_e1_contract_resip_runtime.py` | engineering only |
| M6 product 60s measure (resources.json) | `m6-product-runtime-measure-60s.sh` | [`m6-product-60s-review-2026-10-05.md`](m6-product-60s-review-2026-10-05.md) — **not** O1 |

## Not done (M8 / maintainer)

| Item | Owner |
|------|-------|
| REQ-NF-1 maintainer sign-off | Maintainer |
| D10 **passed** per `test-plan.md` (unified product process, no harness tag seams) | M8 |
| ADR-0023 accepted protocol semantics | Maintainer |
| Redis owner fencing / CAS under failover | M8+ |
| Full E1 S1–S11 on shipping stack | M8 / E1 program |
| M7 milestone exit | Maintainer |
| K2 release | Blocked on above |

## Verdict

**Accept** accumulated M7 engineering slices including Redis and restart harness. **Deny** M7 milestone completion, **Deny** D10/REQ-NF-1 acceptance, **Deny** K2.
