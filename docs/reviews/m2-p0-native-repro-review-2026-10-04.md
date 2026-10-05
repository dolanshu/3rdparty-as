# M2 P0 native repro review (2026-10-04)

## Object

Independent engineering review of the M2 **P0** slice: offline vendor restore, reproducible native reSIProcate build under `.cache/m2-resiprocate`, `resip_probe` link, and UDP S1 loopback smoke via `testbed/simulators/resip-probe/scripts/m2-native.sh` and Makefile targets `m2-native-*`. Cross-ref: [`m2-native-build-matrix.md`](../acceptance/m2-native-build-matrix.md), [`m2-handoff-review-2026-10-04.md`](m2-handoff-review-2026-10-04.md), [`m2-native-probe-review-2026-10-04.md`](m2-native-probe-review-2026-10-04.md). Adapter boundary: [`m2-adapter-boundary-adjudication-2026-10-04.md`](m2-adapter-boundary-adjudication-2026-10-04.md).

## Date and reviewers

- Date: 2026-10-04
- Reviewer: Independent AI

## Conclusion

**Pass for the M2 P0 engineering slice only.** M2 milestone completion, product SIP adapter/runtime binding, REQ-S acceptance, and REQ/E1 acceptance remain **open**. Maintainer signoff: **pending**.

## Findings and disposition

| Finding | Disposition |
|---|---|
| P0 path depended on handoff `/tmp` trees or implicit network clone; not reproducible from a fresh clone. | **Fixed:** checked-in vendor archives + `m2-native.sh restore` / `build-resip` / `build-probe` / `smoke`; default cache under `.cache/m2-resiprocate`; documented in build matrix. |
| Prebuilt bundle targets Ubuntu 20.04 + OpenSSL 1.1 ABI; OpenSSL 3 hosts cannot load prebuilt `.so` without rebuild. | **Accepted boundary:** default CI/local path builds from bundled source (`AS_RESIP_USE_PREBUILT` optional); matrix documents ABI mismatch. |
| `make m2-native-smoke` alone does not build; full repro is `make m2-native` or restore + build + smoke. | **Documented** in build matrix and Makefile help; CI job runs restore + build before smoke. |
| Integration test `test_m2_native_probe_smoke.py` needs `AS_RESIP_PROBE_BIN` when probe is not at default cache path. | **Fixed:** `m2-native.sh` `build-probe` / `smoke` export and log `AS_RESIP_PROBE_BIN`. |
| P0 does not implement platform transport adapter, TLS runtime enforcement, DUM→Python product bridge, or `CallController`. | **Out of scope for this review**; see adapter boundary adjudication; M7 owns D9 product integration. |

## Verification

From repository root (after `libpopt-dev`, `libc-ares-dev`, `libssl-dev`, `cmake`, `build-essential`):

```sh
make m2-native-restore m2-native-build
make m2-native-smoke
make gate
```

Full one-shot P0 chain:

```sh
make m2-native
make gate
```

Expected smoke markers include `reason=RemoteBye` and `probe 退出 OK` / `probe exit OK`.

## Confirmation

- Independent AI review recorded 2026-10-04.
- Maintainer signoff: **pending**.

## Limits

Not REQ acceptance, not M2 milestone closure, not CI certification unless separately recorded, not production S-SBC/operator PKI evidence.
