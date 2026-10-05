# M2 native build matrix (testbed P0)

Short record for the **reproducible vendor restore + native build + UDP S1 smoke**
path (`testbed/simulators/resip-probe/scripts/m2-native.sh`). This validates
testbed tooling only; it does **not** close product M2 (no platform `SipStack`
adapter, no REQ-S acceptance).

## Validated environment

| Dimension | Value |
|---|---|
| OS | Ubuntu 20.04.2 LTS (incl. WSL2) |
| Arch | x86_64 |
| GCC | 9.4.0 (build-essential) |
| CMake | >= 3.21 (3.31.x used on handoff host) |
| Build deps | `libpopt-dev`, `libc-ares-dev`, `libssl-dev` |
| Runtime (reSIProcate `.so`) | `libssl.so.1.1`, `libcrypto.so.1.1`, `libcares.so.2`, glibc |

OpenSSL 3-only hosts must rebuild from the bundled source; prebuilt `.so` files
target the 1.1 ABI.

## Reproduce

From repository root:

```sh
make m2-native
```

Or stepwise:

```sh
make m2-native-restore
make m2-native-build
make m2-native-smoke
```

Cache layout (default):

- `.cache/m2-resiprocate/source` — extracted upstream 1.14.0 @ `632e215c`
- `.cache/m2-resiprocate/build` — CMake build of `rutil`, `resip`, `dum`
- `.cache/m2-resiprocate/probe-build/resip_probe` — linked probe binary

## Boundary

- **In scope:** vendor checksum, offline source build, probe link with repo cache
  RPATH, S1 UDP loopback smoke (`probe 退出 OK`).
- **Out of scope:** product integration, TLS/mTLS REQ-S gates,
  operator PKI or S-SBC evidence.
- **CI:** GitHub Actions job `m2-native-smoke` on `ubuntu-latest` (22.04 /
  OpenSSL 3) builds from bundled source only; prebuilt tarball is not used.
