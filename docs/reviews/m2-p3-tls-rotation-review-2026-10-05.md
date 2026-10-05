# M2 P3 TLS overlap review (2026-10-05)

## Object

Independent engineering review of M2 **P3** (partial): REQ-S-3 dual-material overlap
**policy** on the product ingress seam (`TlsRotationState`, `TransportIngressGate.install_with_overlap`,
native `reload_certificates` hook on overlap start).

Cross-ref: [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md), handoff P3 in
[`handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md).

## Date and reviewers

- Date: 2026-10-05
- Reviewer: Independent AI

## Conclusion

**Pass for the P3 engineering slice (pure overlap policy + native reload request path)** when unit
tests pass. Full REQ-S-3 acceptance (live TLS new-cert handshakes, in-flight dialog preservation on
operator PKI, post-window rejection of stale peers) remains **open**. Maintainer signoff: **pending**.

## REQ-S-3 mapping (test-plan §3)

| Criterion | Slice disposition |
|-----------|-------------------|
| In-flight calls unaffected during overlap | **Partial** — legacy `connection_id` tokens consult retiring seam until monotonic deadline; no live TLS dialog proof. |
| New connections use new certificate | **Partial** — active seam/TLS for new tokens; native `reloadCertificates` queued on overlap start; UDP P2c listener only. |
| Stale peers rejected after window | **Partial** — overlap expiry clears retiring seam; no wire-level cert verification test. |
| No process restart | **Aligned** — in-process rotation hook; no restart in API. |

## Findings and disposition

| Finding | Disposition |
|---------|-------------|
| No dual-material holder or overlap-aware `check_peer`. | **Fixed:** `tls_rotation.py` + `install_with_overlap` with legacy connection tokens. |
| Testbed SIGHUP smokes ≠ product binding. | **Accepted** — documented; product path adds Python gate policy + native reload queue. |
| `reloadCertificates` not wired on platform runtime. | **Fixed:** `_resip_runtime.reload_certificates` + `ResipRuntimeListener` default overlap hook. |
| REQ-S-3 checklist in test-plan still open. | **Open** — requires P4 integration and operator evidence. |

## Verification

```sh
uv run pytest platform/tests/test_tls_rotation.py platform/tests/test_transport_ingress.py -m unit -q
make gate
```

Optional (when extension built):

```sh
make m2-platform-resip-build
uv run pytest platform/tests/test_resip_runtime_integration.py -m integration -q
```

## Limits

Not REQ-S-3 acceptance, not product TCP/TLS/mTLS handshake, not concurrent multi-call rotation
stress, not M2 exit.

## Sign-off

- Independent AI review recorded: 2026-10-05
- Maintainer signoff: **pending**
