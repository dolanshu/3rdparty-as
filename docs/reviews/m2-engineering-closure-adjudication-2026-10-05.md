# M2 engineering closure adjudication — stack binding slice (2026-10-05)

> **Subject:** M2 **transport/runtime stack binding** engineering closure (handoff P0–P4 slices), not full M2 milestone  
> **Authority:** [`handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md); [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md); [`plan.md`](../plan.md) §4 M2 row  
> **Acceptance report cross-ref:** [`report.md`](../acceptance/report.md) §「M2 transport/runtime engineering closure（2026-10-05）」

## Scope of this closure

This adjudication bundles the **authorized engineering path** for continuing M2 work on:

| Layer | Delivered slice |
|-------|-----------------|
| Testbed native transport | P0 vendor restore + build; UDP S1 (`m2-native-smoke`); TCP S1 (`m2-native-smoke-tcp`) via `resip_probe` |
| Product runtime binding | P2c `ResipRuntimeListener` + `make m2-platform-resip-build`; UDP DUM→Python ingress + `decide()` integration tests |
| TLS / ingress policy | P2d TLS listener, certificate fingerprint token, plaintext reject when TLS required; optional `m2-native-smoke-tls-runtime` |
| Rotation seam | P3 `TlsRotationState`, `TransportIngressGate.install_with_overlap`, native `reload_certificates` hook; `test_tls_rotation.py` |
| CI / integration gate | P4 blocking jobs `m2-native-smoke` and `m2-platform-resip` (native build + `test_resip_runtime_integration.py` + rotation unit tests) |

## Adjudication

| Item | Verdict |
|------|---------|
| P0 native repro + UDP smoke (testbed) | **Accept** (engineering slice) — [`m2-p0-adjudication-2026-10-05.md`](m2-p0-adjudication-2026-10-05.md) |
| P1 adapter boundary recorded | **Accept** (boundary) — [`m2-adapter-boundary-adjudication-2026-10-04.md`](m2-adapter-boundary-adjudication-2026-10-04.md) |
| P2 ingress + testbed TCP + product UDP/TLS runtime slices | **Accept** (partial P2; slices P2b–P2d) — linked P2 adjudications 2026-10-05 |
| P3 overlap policy + reload hook | **Accept** (partial P3) — [`m2-p3-tls-rotation-adjudication-2026-10-05.md`](m2-p3-tls-rotation-adjudication-2026-10-05.md) |
| P4 focused real-socket CI + platform integration pytest gate | **Accept** (P4 engineering slice) |
| **Full M2 milestone / M2 exit** | **Deny** |
| REQ-S-2 / REQ-S-3 acceptance | **Deny** — not claimed by this closure |
| Operator PKI / external S-SBC evidence | **Open** |

## Rationale

The register and prior slice adjudications show a **coherent stack-binding story**: reproducible native testbed probes, a product `_resip_runtime` extension with integration tests, ingress/TLS policy seams, and rotation policy wired to a native reload hook. Adding CI job `m2-platform-resip` makes the platform integration path **blocking on the same class of environment** as P0 (source build on `ubuntu-latest` / OpenSSL 3).

Accepting this **engineering closure** means maintainers may treat the listed artifacts as the current **baseline for further M2 work** (D3, REQ-S, operator PKI, product TCP, M7 product CallController). It does **not** substitute for test-plan REQ acceptance or milestone sign-off.

## Remains open for maintainer sign-off

1. **M2 exit criteria** — P2 remainder (product TCP, full mTLS operator path), P3 wire/active-call dual-cert proof, P4 operator PKI when available, plus any plan §4 M2 gate items not covered above.  
2. **D3** — Redis Sentinel / split-brain idempotency on `RedisStateStore`.  
3. **REQ-S-2 / REQ-S-3** — full test-plan bullets including REQ-S-3 overlap on live product TLS transport.  
4. **Maintainer signature** — P0–P4 slice adjudications recorded **pending** maintainer sign-off; this document does not auto-approve M2.  
5. **M6 / M7** — **M6 milestone exit** and **M7** remain blocked per [`plan.md`](../plan.md) until M2 exit. **M6 engineering** against the product `ResipRuntimeListener` (harness smoke / micro-measure) may proceed after this stack-binding closure — **not** O1 publication or formal capacity numbers.

## Limits

Not REQ acceptance, not deployment certification, not M7 D9–D11 product integration. CI green on `m2-platform-resip` certifies the **repository repro path** for the listed tests, not operator production PKI.

## Sign-off

- Engineering closure adjudication recorded: 2026-10-05  
- Maintainer sign-off on M2 stack binding slice: **pending**  
- Maintainer sign-off on **M2 milestone**: **not requested** — explicitly **open**
