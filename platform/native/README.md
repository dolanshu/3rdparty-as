# Platform native bindings

Optional C++ extensions for the product SIP stack (reSIProcate per ADR-0019). They
are **not** part of the Hatch wheel; build them with CMake when
`AS_RESIP_HOME` / `AS_RESIP_BUILD` (or the repo `.cache/m2-resiprocate` trees from
`make m2-native-restore`) are available.

## `resip_runtime/` (M2 P2c)

Python module: `_resip_runtime` (imported by `as_platform.sip.resip_runtime`).

| Target | Command |
|--------|---------|
| Build extension | `make m2-platform-resip-build` |
| Integration tests | `uv run pytest platform/tests/test_resip_runtime_integration.py -m integration -q` |

Environment:

| Variable | Default |
|----------|---------|
| `AS_RESIP_HOME` | `$AS_RESIP_CACHE_ROOT/source` or `.cache/m2-resiprocate/source` |
| `AS_RESIP_BUILD` | `$AS_RESIP_CACHE_ROOT/build` or `.cache/m2-resiprocate/build` |
| `AS_RESIP_RUNTIME_BUILD` | `platform/native/resip_runtime/build` (directory containing `_resip_runtime*.so`) |

The extension links `libdum`, `libresip`, and `librutil` from the same minimal
reSIProcate build used by `testbed/simulators/resip-probe`.

## `resip_two_leg/` (M7 minimal slice)

Python module: `_resip_two_leg` (imported by `as_platform.sip.resip_two_leg`).

| Target | Command |
|--------|---------|
| Build extension | `make m7-platform-two-leg-build` |
| Integration tests | `uv run pytest platform/tests/test_resip_two_leg_integration.py -m integration -q` |

Environment:

| Variable | Default |
|----------|---------|
| `AS_RESIP_TWO_LEG_BUILD` | `platform/native/resip_two_leg/build` |

Inbound INVITE → outbound INVITE to a loopback peer; downstream **486** maps to inbound **486**. Derived from the D9 research module; not the production adapter or full B2BUA.
