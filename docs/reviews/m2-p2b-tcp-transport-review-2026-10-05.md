# M2 P2b TCP transport review (2026-10-05)

> **Subject:** M2 handoff **P2** (partial) — reSIProcate testbed `resip_probe` TCP listener + S1 loopback self-test  
> **Authority:** [`handoff/2026-10-04-m2.md`](../handoff/2026-10-04-m2.md) P2; [`m2-task-register-2026-10-05.md`](m2-task-register-2026-10-05.md)

## Object

`testbed/simulators/resip-probe/resip_probe.cxx` `--tcp` flag, `scripts/m2-native.sh smoke-tcp`, Makefile `m2-native-smoke-tcp`, README usage. TLS path unchanged (`--tls`).

## Conclusion

**Pass** for the TCP testbed slice only. Product reSIProcate transport binding, ingress peer policy on TCP/TLS, and REQ-S acceptance remain **open**.

## Scope delivered

| Item | Status |
|------|--------|
| Register TCP transport alongside UDP (`port=0`) | Done |
| `--external` exposes UDP + TCP (+ TLS when `--tls`) | Done |
| Self-test S1 over TCP when `--tcp` without `--tls` (`;transport=tcp`) | Done |
| `make m2-native-smoke-tcp` / `smoke-tcp` SIGINT pattern | Done |
| Document path to TLS via existing `--tls` | Documented in README |

## Verification

```sh
make m2-native-build      # if probe binary stale
make m2-native-smoke-tcp  # expect RemoteBye + probe exit OK
make gate                 # repository gate (Python layers)
```

## Residual boundaries

- Testbed evidence only; not `TransportIngressGate` on live TCP connections in the product adapter.
- No mTLS, operator PKI, or REQ-S-2/3 claims.
- Maintainer sign-off on P2 overall remains **pending** per task register.

## Adjudication

| Item | Verdict |
|------|---------|
| TCP listener + S1 loopback smoke on native probe | **Accept** |
| TLS on product accept path + peer policy | **Open** — use `--tls` in probe; product binding separate |
| M2 milestone closure | **Deny** — P2–P4 incomplete |

- Engineering adjudication recorded: 2026-10-05  
- Maintainer sign-off: **pending**
