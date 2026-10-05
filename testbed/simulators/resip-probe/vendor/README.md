# reSIProcate Handoff Bundle

This directory preserves the exact upstream source snapshot and native build
outputs used for the 2026-10-04 M2 probe work. These are testbed handoff assets;
they are not a product SIP-stack integration.

## Contents

| File | Contents |
|---|---|
| `resiprocate-1.14.0-632e215c-source.tar.gz` | Tracked source at tag `resiprocate-1.14.0`, commit `632e215c2ca9aee5416bfe1808851ea6fa380044`; excludes the upstream clone's `.git` metadata. |
| `resiprocate-m2-ubuntu20.04-x86_64-prebuilt-20261004.tar.gz` | The reSIProcate CMake build tree and `resip_probe` CMake build tree from the validated Ubuntu 20.04 x86_64 environment. |
| `SHA256SUMS` | Integrity hashes for both archives. |

## Restore For A Compatible Host

From this directory, verify and extract into the original `/tmp` paths. Use a
clean target host or empty destinations; do not extract over another person's
working build.

```sh
sha256sum -c SHA256SUMS
mkdir -p /tmp/as-resiprocate-m2-20261004
tar -xzf resiprocate-1.14.0-632e215c-source.tar.gz \
  --strip-components=1 -C /tmp/as-resiprocate-m2-20261004
tar -xzf resiprocate-m2-ubuntu20.04-x86_64-prebuilt-20261004.tar.gz -C /tmp
ldd /tmp/as-resiprocate-m2-probe-build-20261004/resip_probe
/tmp/as-resiprocate-m2-probe-build-20261004/resip_probe S1
```

The executable's RUNPATH points at `/tmp/as-resiprocate-m2-build-20261004`.
The native libraries require the Ubuntu 20.04-era OpenSSL ABI (`libssl.so.1.1`
and `libcrypto.so.1.1`) plus c-ares and the normal C/C++ runtime libraries.
Reuse the binaries only when `ldd` resolves every dependency. Newer Ubuntu
releases commonly provide OpenSSL 3 instead; in that case rebuild from the
bundled source as described in
[`../../../../docs/handoff/2026-10-04-m2.md`](../../../../docs/handoff/2026-10-04-m2.md).

The CMake cache files are preserved as evidence but contain author-machine
absolute paths. To rebuild only the probe on a different checkout path, use a
new probe build directory and pass explicit `RESIP_HOME` and `RESIP_BUILD`
values; do not reuse the archived probe CMake cache.

The source archive retains upstream test fixtures, including test certificate
and key files. They are public upstream test data and must never be used as
deployment credentials. No locally generated M2 self-test certificate or key
was included.

## Prebuilt archive shelf life

The `resiprocate-m2-ubuntu20.04-x86_64-prebuilt-20261004` tarball is a
**2026-10-04** handoff artifact only. Rebuild from the bundled source on any
host where `ldd` fails or OpenSSL ABI differs (see `docs/handoff/2026-10-04-m2.md`).
Prefer CI `make m2-native-restore m2-native-build` over long-term git storage of
prebuilt trees when policy allows.