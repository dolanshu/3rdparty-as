# M6 product ResipRuntimeListener smoke review (2026-10-05)

## Object

Independent engineering review of M6 harness slice: real-socket smoke from `as_load` to the **product** `ResipRuntimeListener` (`_resip_runtime` + ingress gate), not testbed `resip_probe`. Prerequisite: [`m2-engineering-closure-adjudication-2026-10-05.md`](m2-engineering-closure-adjudication-2026-10-05.md) authorizes **M6 engineering** against the product listener; it does **not** authorize O1 publication or M6 milestone exit.

## Spec (plan)

M6 capacity research uses real sockets per stack (ADR-0019 reSIProcate). This slice proves the harness can drive the product runtime UAS path with `established_sessions >= 1` — smoke only.

## Evidence

| Artifact | Role |
|----------|------|
| `ResipRuntimeListener(accept_all_invites=True)` + native `accept_all_invites` transport flag | Testbed UAS: 100/180/200 + minimal SDP after ingress policy |
| `platform/tests/fixtures/load_uas_runtime.py` | Long-running UAS process for scripts |
| `testbed/load/scripts/m6-product-runtime-smoke.sh` | Shell smoke (`cps=1`, `duration=0.2`) |
| `testbed/load/tests/test_product_runtime_smoke.py` | `@pytest.mark.integration` (skips when extension absent) |
| `platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200` | Platform integration guard |

## Findings

1. **Pass (engineering slice).** One-call UDP loopback establishes a session against the product listener; aligns with authorized M6 harness scope post M2 stack-binding closure.
2. **D8 open.** No REQ/contract trace for testbed three-layer / capacity REQ; requirement closure and maintainer signoff remain blocked.
3. **Not capacity evidence.** No O1 CPS/concurrency/latency targets, no saturation, no operator PKI/TLS path on this slice.

## Verdict

**Pass** for the M6 product-runtime smoke engineering slice only.

## Limits

Not M6 milestone completion, not O1 numbers, not REQ acceptance, not M7 CallController integration.

## Independent second-pass review

| Check | Result |
|-------|--------|
| Harness targets product `_resip_runtime`, not `resip_probe` | **OK** — `stack=as-platform-resip-runtime` |
| Ingress policy still enforced before accept-all path | **OK** — denied peer test unchanged; accept mode skips `decide()` only after gate |
| Docs/plan avoid O1 publication | **OK** — adjudication companion explicitly denies O1 |
| `accept_all_invites` scoped to testbed | **OK** — documented on listener; not production routing |

Second-pass verdict: **concurs** with Pass above; no additional blockers for continued M6 engineering precursors.
