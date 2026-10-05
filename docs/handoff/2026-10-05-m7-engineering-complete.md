# Handoff — M7 engineering complete (2026-10-05)

> **Purpose:** Inventory engineering tail delivered on this date and open items for **M8**.  
> **Not:** Maintainer sign-off, REQ acceptance, or milestone exit for M2/M6/M7.

## Delivered in this tail

| # | Item | Primary artifacts |
|---|------|-------------------|
| 1 | M2 REQ-S TLS fingerprint policy | `platform/tests/test_resip_runtime_tls_policy_integration.py`; [`reviews/m2-p2d-second-pass-review-2026-10-05.md`](../reviews/m2-p2d-second-pass-review-2026-10-05.md) |
| 2 | M6 60s product measure | `testbed/load/scripts/m6-product-runtime-measure-60s.sh`; [`reviews/m6-product-60s-review-2026-10-05.md`](../reviews/m6-product-60s-review-2026-10-05.md) |
| 3 | E1 contract extension | `platform/tests/test_e1_contract_resip_runtime.py` (S3 603; S4 skip reason in file) |
| 4 | Translation SIP runtime docs | `apps/translation/README.md`, `apps/translation/translation_sip_main.py` |
| 5 | Cross-milestone review | [`reviews/cross-milestone-final-review-2026-10-05.md`](../reviews/cross-milestone-final-review-2026-10-05.md), [`reviews/cross-milestone-final-adjudication-2026-10-05.md`](../reviews/cross-milestone-final-adjudication-2026-10-05.md) |

Prior M7 engineering slices (D10, Redis/restart harness, E1 S1/S2, micro-measure) remain documented under [`reviews/m7-final-engineering-adjudication-2026-10-05.md`](../reviews/m7-final-engineering-adjudication-2026-10-05.md) and [`reviews/m7-milestone-engineering-closure-adjudication-2026-10-05.md`](../reviews/m7-milestone-engineering-closure-adjudication-2026-10-05.md).

## Review inventory (2026-10-05, representative)

### M2

- [`m2-engineering-closure-adjudication-2026-10-05.md`](../reviews/m2-engineering-closure-adjudication-2026-10-05.md)
- [`m2-p2d-second-pass-review-2026-10-05.md`](../reviews/m2-p2d-second-pass-review-2026-10-05.md)
- P2/P3 slice reviews: `m2-p2*-`, `m2-p3-*` under `docs/reviews/`

### M6

- [`m6-product-runtime-smoke-review-2026-10-05.md`](../reviews/m6-product-runtime-smoke-review-2026-10-05.md)
- [`m6-product-runtime-micro-review-2026-10-05.md`](../reviews/m6-product-runtime-micro-review-2026-10-05.md)
- [`m6-product-60s-review-2026-10-05.md`](../reviews/m6-product-60s-review-2026-10-05.md)
- [`m6-product-runtime-adjudication-2026-10-05.md`](../reviews/m6-product-runtime-adjudication-2026-10-05.md)

### M7 / D10 / E1

- [`m7-milestone-engineering-closure-adjudication-2026-10-05.md`](../reviews/m7-milestone-engineering-closure-adjudication-2026-10-05.md)
- [`m7-final-engineering-adjudication-2026-10-05.md`](../reviews/m7-final-engineering-adjudication-2026-10-05.md)
- D10: `m7-d10-*`, `d10-*` harness/redis/restart reviews through third pass
- E1: [`m7-e1-contract-review-2026-10-05.md`](../reviews/m7-e1-contract-review-2026-10-05.md)

### Cross-milestone

- [`cross-milestone-final-review-2026-10-05.md`](../reviews/cross-milestone-final-review-2026-10-05.md)
- [`cross-milestone-final-adjudication-2026-10-05.md`](../reviews/cross-milestone-final-adjudication-2026-10-05.md)

## Commands (local verification)

```bash
# Pre-merge bar
make gate

# Native runtime (optional; unlocks integration/contract tests that need _resip_runtime)
make m2-platform-resip-build

# M2 REQ-S policy integration
uv run pytest platform/tests/test_resip_runtime_tls_policy_integration.py -m integration -q

# E1 contract (includes S3 + skipped S4)
uv run pytest platform/tests/test_e1_contract_resip_runtime.py -m contract -q

# M6 harness (engineering; not CI gate)
bash testbed/load/scripts/m6-product-runtime-smoke.sh
bash testbed/load/scripts/m6-product-runtime-micro-measure.sh
bash testbed/load/scripts/m6-product-runtime-measure-60s.sh

# Translation process shell + SIP runtime (empty rules → 404 on no match)
export AS_ENABLE_SIP_RUNTIME=1 AS_USE_CASE=translation
uv run python apps/translation/translation_sip_main.py
```

## Open for M8 (non-exhaustive)

1. **Milestone sign-off** — M2, M6, M7 maintainer exit criteria per [`plan.md`](../plan.md) §4.
2. **REQ / test-plan** — REQ-NF-1, full D10 baseline, E1 S1–S11 on shipping stack, REQ-F-4 product SDP proof (D11).
3. **D9 adapter** — Outbound UAC, CANCEL forward (E1 S4), forking/race coverage.
4. **O1 / D8** — Formal capacity study and PRD trace for testbed/performance REQ.
5. **D3** — Redis Sentinel client wiring (M2 open item).
6. **Config → runtime** — DB-backed rules into `SipStackService`, not empty `RuleSet`.
7. **Release candidate** — M8 evidence chain, unified VERSION, acceptance report refresh.

## Explicit denials

- No O1 CPS/concurrency/latency publication from M6 scripts.
- No REQ-S-2/3, REQ-NF-1, or full E1 acceptance claimed by this handoff.
- No git commit or maintainer signature attached to this document.
