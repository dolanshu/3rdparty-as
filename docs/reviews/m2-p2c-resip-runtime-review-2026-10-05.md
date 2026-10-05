# M2 P2c resip runtime review (2026-10-05)

## Object

Independent engineering review of M2 **P2c**: product-path reSIProcate DUM UDP listener
(`platform/native/resip_runtime`) calling Python `TransportIngressGate` + `decide()` via
`as_platform.sip.resip_runtime.ResipRuntimeListener`. Patterns adapted from
`testbed/simulators/resip-probe/research/d9-dum-python/` without testbed imports.

Cross-ref: [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md), P2 ingress
contract [`m2-p2-ingress-adjudication-2026-10-05.md`](m2-p2-ingress-adjudication-2026-10-05.md).

## Date and reviewers

- Date: 2026-10-05
- Reviewer: Independent AI

## Conclusion

**Pass for the M2 P2c engineering slice** when the native extension is built and integration
tests pass. TCP/TLS/mTLS product transport, certificate identity on the wire, REQ-S-2/3, and M2
milestone closure remain **open**. Maintainer signoff: **pending**.

## Findings and disposition

| Finding | Disposition |
|---|---|
| Product `SipStack` accept path not wired to ingress + `decide()`. | **Fixed:** `_resip_runtime` DUM worker on `127.0.0.1:0`; `onNewSession` builds peer + SIP summary, GIL-safe Python callback. |
| No platform-native build hook. | **Fixed:** `make m2-platform-resip-build` / `m2-native.sh build-platform-resip`. |
| No focused integration proof. | **Fixed:** `test_resip_runtime_integration.py` — allowed peer + empty `RuleSet` → `404`; denied peer → `403` before `decide()`. |
| Extension optional in CI gate. | **Accepted:** `make gate` stays layer-① only; integration test skips with explicit message when `.so` absent. |

## Verification

From repository root (after `make m2-platform-resip-build` when reSIProcate cache exists):

```sh
uv run pytest platform/tests/test_resip_runtime_integration.py -m integration -q
make gate
```

## Limits

Not REQ acceptance, not TLS handshake or mTLS fingerprint extraction, not operator PKI/S-SBC
evidence, not M2 exit.

## Sign-off

- Independent AI review recorded: 2026-10-05
- Maintainer signoff: **pending**
