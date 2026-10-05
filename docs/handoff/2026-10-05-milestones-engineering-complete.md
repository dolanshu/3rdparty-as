# Handoff — M2 / M6 / M7 engineering complete (2026-10-05)

> **Purpose:** Milestone engineering inventory and **true blockers** only.  
> **Not:** Maintainer sign-off or REQ/test-plan full green.

## Engineering complete (plan §4)

| Milestone | Status | Adjudication |
|-----------|--------|--------------|
| **M2** | 工程完成，**M8 验收** | [`m2-milestone-engineering-complete-adjudication-2026-10-05.md`](../reviews/m2-milestone-engineering-complete-adjudication-2026-10-05.md) |
| **M6** | 工程完成，**M8 验收** | [`m6-engineering-complete-adjudication-2026-10-05.md`](../reviews/m6-engineering-complete-adjudication-2026-10-05.md) |
| **M7** | 工程完成，**M8 验收** | [`m7-milestone-engineering-complete-adjudication-2026-10-05.md`](../reviews/m7-milestone-engineering-complete-adjudication-2026-10-05.md) |

## M7 tail inventory

| # | Item | Tests / artifacts |
|---|------|-------------------|
| 1 | E1 S1/S2/S3/S4 on `_resip_runtime` | `test_e1_contract_resip_runtime_full.py` |
| 2 | D9 FORWARD + 486 | `test_m7_forward_two_leg_integration.py`, native `runtime_module.cxx` |
| 3 | D11 SDP offer bytes | `test_req_f4_sdp_identity_integration.py` |
| 4 | Config → runtime rules | `ruleset_loader.py`, `test_ruleset_loader.py` |
| 5 | D10 establish checkpoint | `SipStackService._on_dialog_established` (all modes with native callback) |

Slice reviews: [`m7-m7-tail-engineering-review-2026-10-05.md`](../reviews/m7-m7-tail-engineering-review-2026-10-05.md)

## Verification

```bash
make m2-platform-resip-build
make gate
uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q
uv run pytest platform/tests/test_m7_forward_two_leg_integration.py \
  platform/tests/test_req_f4_sdp_identity_integration.py -m integration -q
```

## True blockers (only)

1. **Operator PKI lab** — REQ-S-2/3 external S-SBC / mTLS evidence  
2. **Customer K8s NF-1** — REQ-NF-1 live kill/restart/BYE acceptance  
3. **Maintainer signature** — M2/M6/M7 milestone exit per `plan.md` §4  

No other plan §5 items are deferred as engineering blockers; remaining work is **M8 验收** scope.
