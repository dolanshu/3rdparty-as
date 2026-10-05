# M2 P2d TLS runtime review (2026-10-05)

## Object

Independent engineering review of M2 **P2d**: optional TLS transport on product
`ResipRuntimeListener` / `platform/native/resip_runtime`, peer certificate SHA-256
token on ingress, and `reject_plaintext_when_tls_required` when `tls_only` or
`TlsConfig.require_client_certificate`.

Cross-ref: [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md), P2c
[`m2-p2c-resip-runtime-adjudication-2026-10-05.md`](m2-p2c-resip-runtime-adjudication-2026-10-05.md).

## Date and reviewers

- Date: 2026-10-05
- Reviewer: Independent AI

## Conclusion

**Pass for the M2 P2d engineering slice** when `make m2-platform-resip-build` succeeds and
`platform/tests/test_resip_runtime_tls_integration.py` passes. REQ-S-2/3, operator PKI/S-SBC,
TCP product transport, and M2 milestone closure remain **open**. Maintainer signoff: **pending**.

## Findings and disposition

| Finding | Disposition |
|---|---|
| Product runtime UDP-only; no TLS material from `TransportSeam`. | **Fixed:** `start(callback, config)` wires cert/key/CA and optional TLS listener; `get_tls_port`. |
| No `certificate_id` on live TLS INVITE. | **Partial:** OpenSSL peer-verify hook stores `sha256:<hex>` when the stack invokes client-cert verification (mTLS); peer dict includes `transport` + `certificate_id`. Optional client-cert presentation without verify callback remains **open** for a follow-up binding slice. |
| Plaintext not rejected when mTLS/tls-only mandated. | **Fixed:** Python enforces `reject_plaintext_when_tls_required` for `tls_only` or `require_client_certificate`; native omits UDP when `tls_only`. |
| No integration proof. | **Fixed:** `test_resip_runtime_tls_integration.py` (gen-cert.sh tmpdir, openssl `s_client`, skip if extension missing). |
| Smoke entry point. | **Fixed:** `m2-native.sh smoke-tls-runtime` / `make m2-native-smoke-tls-runtime`. |

## Verification

```sh
make m2-platform-resip-build
uv run pytest platform/tests/test_resip_runtime_tls_integration.py -m integration -q
make gate
```

## Limits

Not REQ acceptance, not certificate hot-rotation wire proof (P3), not external S-SBC evidence,
not M2 exit.

## Sign-off

- Independent AI review recorded: 2026-10-05
- Maintainer signoff: **pending**
