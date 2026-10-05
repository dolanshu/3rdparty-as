# M2 task register (2026-10-05)

> **Spec source:** [`handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md) §Prioritized M2 Continuation Plan (P0–P4); [`plan.md`](../plan.md) §4 M2 row and §0 status.  
> **Sequencing:** Maintainer order **M2 complete (all P0–P4 + exit criteria) → M6 → M7**. **M6 and M7 are blocked** until M2 exit.  
> **Legend:** **Pass** = engineering slice meets handoff scope for that priority (not M2 milestone closure). **Pending** = not done or partial. **Fail** = known gap blocking that priority.

| Priority | Handoff scope (summary) | Status | Evidence / review | Notes |
|----------|-------------------------|--------|-------------------|-------|
| **P0** | Native vendor restore + reproducible build + real `SipStack` testbed smoke (UDP S1) | **Pass** (engineering slice) | `make m2-native`, [`m2-native-build-matrix.md`](../acceptance/m2-native-build-matrix.md), [`m2-p0-native-repro-review-2026-10-04.md`](m2-p0-native-repro-review-2026-10-04.md) | Formal adjudication: [`m2-p0-adjudication-2026-10-05.md`](m2-p0-adjudication-2026-10-05.md). Maintainer signoff **pending**. **Not** M2 exit. |
| **P1** | Adapter boundary: testbed transport vs product DUM/`CallController` | **Pass** (boundary recorded) | [`m2-adapter-boundary-adjudication-2026-10-04.md`](m2-adapter-boundary-adjudication-2026-10-04.md); ADR-0022 **accepted** — [`adr-0022-acceptance-adjudication-2026-10-05.md`](adr-0022-acceptance-adjudication-2026-10-05.md) | Maintainer signoff **pending**. |
| **P2** | Runtime TLS/mTLS + fail-closed peer policy on live connection path | **Pass** (engineering slice) | P2 ingress/TLS adjudications 2026-10-05; [`m2-tcp-product-review-2026-10-05.md`](m2-tcp-product-review-2026-10-05.md); product TCP `enable_tcp` + `test_resip_runtime_tcp_integration.py` + `m2-native-smoke-tcp-runtime` | Full operator mTLS / external S-SBC path **M8** env evidence. |
| **P3** | REQ-S-3 dual-certificate overlap window on product transport | **Pass** (engineering slice) | [`m2-p3-tls-rotation-adjudication-2026-10-05.md`](m2-p3-tls-rotation-adjudication-2026-10-05.md); [`m2-req-s3-review-2026-10-05.md`](m2-req-s3-review-2026-10-05.md), [`m2-req-s3-adjudication-2026-10-05.md`](m2-req-s3-adjudication-2026-10-05.md); `test_req_s3_overlap_integration.py` | Operator PKI wire proof **M8**; not full test-plan REQ-S-3 sign-off. |
| **P4** | Focused real-socket integration + blocking CI/native gate; review; docs; then operator PKI when available | **Pass** (engineering slice) | CI `m2-native-smoke` + `m2-platform-resip`; [`m2-engineering-closure-adjudication-2026-10-05.md`](m2-engineering-closure-adjudication-2026-10-05.md); D3 client wiring — [`m2-d3-sentinel-adjudication-2026-10-05.md`](m2-d3-sentinel-adjudication-2026-10-05.md) | Operator PKI when available; **M2 exit** maintainer signoff **pending M8** acceptance path only for PKI tail. |

## Milestone gates (blocked downstream)

| Milestone | Register verdict | Reason |
|-----------|------------------|--------|
| **M2 exit (engineering)** | **Complete** | P0–P4 engineering slices + D3 client wiring delivered; [`m2-d3-sentinel-adjudication-2026-10-05.md`](m2-d3-sentinel-adjudication-2026-10-05.md). |
| **M2 exit (maintainer)** | **Pending M8** | Maintainer M2 sign-off and REQ-S operator PKI bullets remain for **M8**; not blocking further in-repo engineering. |
| **M6** | **Unblocked for engineering** | Per stack-binding closure; formal M6 milestone still after maintainer M2 sign-off per plan. |
| **M7** | **Engineering in progress** | Product control/recovery slices; D9–D11 acceptance still open. |

## Local verification snapshot (2026-10-05)

```sh
make m2-native-smoke
make m2-native-smoke-tcp
make m2-platform-resip-build
make m2-native-smoke-tls-runtime
make m2-native-smoke-tcp-runtime
uv run pytest platform/tests/test_redis_sentinel_store.py platform/tests/test_req_s3_overlap_integration.py -q
make gate
```

Does **not** imply M2 milestone maintainer sign-off or full REQ acceptance.
