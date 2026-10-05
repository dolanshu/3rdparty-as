# M2 P2d TLS runtime adjudication (2026-10-05)

> **Subject:** M2 handoff **P2** (partial) — product TLS listener + ingress fingerprint path
> **Prior review:** [`m2-p2d-tls-runtime-review-2026-10-05.md`](m2-p2d-tls-runtime-review-2026-10-05.md)
> **Authority:** [`handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md) P2; [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md)

## Disposition

| Item | Verdict |
|------|---------|
| TLS transport + `TlsConfig` paths on `ResipRuntimeListener` | **Accept** (engineering slice) |
| `certificate_id` SHA-256 token on TLS INVITE (peer cert when presented) | **Accept** (slice) |
| `reject_plaintext_when_tls_required` for `tls_only` / `require_client_certificate` | **Accept** |
| `test_resip_runtime_tls_integration.py` + `smoke-tls-runtime` | **Accept** |
| Full P2 (TCP product transport, operator PKI, REQ-S-2/3) | **Open** |
| M2 milestone closure | **Deny** — P2 remainder, P3–P4 incomplete |

## Sign-off

- Independent AI adjudication recorded: 2026-10-05
- Maintainer signoff: **pending**
