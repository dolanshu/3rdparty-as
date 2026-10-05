# M2 P2 ingress runtime review (2026-10-05)

## Object

Independent engineering review of the M2 **P2** slice (partial): Python ingress binding seam —
`TransportIngressGate`, plaintext-when-TLS-required helper, and M2-only `UdpIngressServer` proving
runtime fail-closed peer policy on a real UDP accept path before native reSIProcate wiring.
Cross-ref: ADR-0016, [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md), handoff P2.

## Date and reviewers

- Date: 2026-10-05
- Reviewer: Independent AI

## Conclusion

**Pass for the M2 P2 engineering slice only** (ingress gate API + UDP proof listener). Full TLS/mTLS
handshake, certificate identity extraction, TCP/TLS product transport binding, REQ-S-2/3 acceptance,
and M2 milestone closure remain **open**. Maintainer signoff: **pending**.

## Findings and disposition

| Finding | Disposition |
|---|---|
| Transport policy existed only as pure `TransportSeam` with no runtime holder for new connections. | **Fixed:** `TransportIngressGate` with thread-safe `install` / `check_peer` delegating to `allows`. |
| Plaintext SIP when TLS is required was not expressed at ingress. | **Fixed:** `reject_plaintext_when_tls_required` helper (ADR-0016); binding must call before parse. |
| No real-socket evidence that denied peers are dropped at accept. | **Fixed:** `UdpIngressServer` (M2-only) + `integration` tests; denied datagrams not enqueued. |
| Product `SipStack` / reSIProcate accept path not wired. | **Accepted boundary:** same gate API is the contract for the upcoming C++ binding; TCP/TLS still open. |
| REQ-S-3 dual-cert overlap, mTLS fingerprint path on live TLS. | **Out of scope for this slice** — P3 / full P2 remainder. |

## Verification

From repository root:

```sh
make gate
uv run pytest platform/tests/test_transport_ingress_integration.py -m integration -q
```

Expected: unit tests for gate swap and plaintext helper green; integration tests show allowed
`127.0.0.1` peer delivers payload and deny-list peer does not appear in `received_payloads`.

## Confirmation

- Independent AI review recorded 2026-10-05.
- Maintainer signoff: **pending**.

## Limits

Not REQ acceptance, not M2 milestone closure, not operator PKI/S-SBC evidence, not TLS handshake
or client-certificate verification on the product stack.

## Independent second pass

**Date:** 2026-10-05  
**Reviewer:** Independent AI (second pass)  
**Scope:** `platform/src/as_platform/sip/ingress.py`, `udp_ingress.py`,
`platform/tests/test_transport_ingress.py`, `platform/tests/test_transport_ingress_integration.py`
against AGENT.md §5 (pure decision vs IO), §13 (fail-closed / untrusted trunk), and stated thread-safety
claims in module docs.

### Conclusion

**Agree with prior Pass** for the M2 P2 ingress slice. No **major** defects requiring code change in this
pass. Minor gaps and documentation nits are recorded below.

### AGENT.md layering (decision vs IO)

| Layer | Role | Verdict |
|---|---|---|
| `transport.authorize_peer` / `TransportSeam.allows` | Pure policy decision (no socket, no clock) | **Aligned** |
| `ingress.TransportIngressGate` + `reject_plaintext_when_tls_required` | Runtime holder + pure transport-shape guard for the binding seam | **Aligned** — not a “decision module” in the TDD sense; it delegates to `allows` and holds the active seam under a lock |
| `udp_ingress.UdpIngressServer` | M2-only integration proof (real UDP socket) | **Aligned** — explicit non-product stack; correct place for IO per slice boundary |

`reject_plaintext_when_tls_required` is intentionally decoupled from `TlsConfig`: the native binding must
pass `tls_required` derived from the installed seam **before** peer checks and parsing. The UDP proof
listener correctly exercises only `check_peer`; it does not imply plaintext UDP is acceptable when the
trunk mandates TLS.

### Thread safety

- **`TransportIngressGate`:** `install` and `check_peer` share one lock; seam read and `allows` run
  atomically — no TOCTOU between swap and evaluation. Returned `TransportSeam` from `install` supports
  rollback without affecting in-flight checks on the new seam reference.
- **`UdpIngressServer`:** Receive thread uses a stable `gate` reference; `received_payloads` snapshots under
  `_received_lock`. `stop()` sets `_stop` before `close()`, so the serve loop exits on post-close `OSError`
  when stopped.
- **Gap (minor):** No concurrent `install` + `check_peer` stress test (contrast `test_metrics.py` counter
  test). Design is sound; test would harden regression coverage only.

### Fail-closed

- Denied peers: `check_peer` → `False` → datagram dropped with no enqueue (**silent drop** = deny, not
  fail-open).
- Empty whitelist: covered at seam unit tests (`test_empty_policy_denies_everything`); gate adds no
  alternate path — **minor:** no integration test proving UDP path with empty policy (redundant with seam
  tests for this slice).
- Plaintext when TLS required: helper rejects any transport label outside `tls`/`sips` (case-insensitive);
  unknown labels (e.g. empty string) reject when `tls_required` is true — **fail-closed**.

### Minor findings (no code change this pass)

1. **`as_platform.sip` package docstring** (`__init__.py`) still states every judgement in the package is a
   pure function; `ingress` and `udp_ingress` are runtime binding/integration. Update when the package
   README/doc chain is next touched — not blocking P2 slice acceptance.
2. **Binding contract reminder:** Product accept path must call `reject_plaintext_when_tls_required` (when
   applicable) **then** `check_peer` with `PeerIdentity` including `certificate_id` once TLS binding exists.
   Not exercised on UDP proof — accepted boundary.
3. **Integration test latency:** `test_denied_peer_datagram_is_silently_dropped` polls for the full
   `_DELIVERY_TIMEOUT_SECONDS` (5s) on success path — correct but slow locally; acceptable for `integration`
   marker, not `make gate` default if deselected.

### Verification (this pass)

```sh
make gate
```

Result: **green** on 2026-10-05 (second pass) — `ruff format --check`, `ruff check`, `mypy`, pytest
`unit or contract`: 908 passed, 2 skipped.
