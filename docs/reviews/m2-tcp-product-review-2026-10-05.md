# M2 product TCP transport review (2026-10-05)

> **Subject:** Product `_resip_runtime` TCP listener (P2 remainder)  
> **Cross-ref:** [`m2-p2b-tcp-transport-review-2026-10-05.md`](m2-p2b-tcp-transport-review-2026-10-05.md) (testbed)

## Object

- `enable_tcp` on native `TransportConfig` + `ResipRuntimeListener(enable_tcp=True)`
- `platform/tests/test_resip_runtime_tcp_integration.py` — TCP INVITE → **404** (empty rules)
- `make m2-native-smoke-tcp-runtime`

## Conclusion

**Pass** for product TCP ingress engineering slice. REQ-S-2 TLS-only operator path unchanged.

## Verification

```sh
make m2-platform-resip-build
make m2-native-smoke-tcp-runtime
```

## Sign-off

- Engineering review recorded: 2026-10-05
- Maintainer sign-off: **pending**
