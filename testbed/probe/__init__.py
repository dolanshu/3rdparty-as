"""SIP stack selection probes for ADR-0019.

ADR-0019 selected reSIProcate and accepted three gaps: E1 (S1-S11 behaviour has
not been replayed on a real socket), E4 (TLS certificate hot rotation has not
been verified) and E5 (state externalisation has not been verified). Consequence
K2 of that ADR says the SIP adapter in ``platform/`` must not be started until
the probes have run, so a probe that quietly passes is worse than no probe at
all: it would release K2 on nothing.

This package holds the probes and the one thing they share --- the loud failure
that stands in for a missing stack binding. Both probes import the selected
stack lazily; when it cannot be imported they print guidance and exit with
:data:`EXIT_BINDINGS_MISSING`. They never skip, because a skipped probe is not
evidence and must not lift K2.

Modules:
    ``sequence_compare``: pure byte-level comparison of two SIP message
        sequences (no IO, no clock, no global state).
    ``e1_baseline_probe``: replays the M1 baseline of
        ``testbed/contracts/sip-baseline/`` against the stack under probe (E1).
    ``tls_hot_rotation_probe``: asserts a certificate rotation survives an
        in-flight call without a restart (E4, scenario S12).
"""

from __future__ import annotations

from typing import Final

#: Exit code used by both probes when the stack's Python bindings are missing.
#: Deliberately not 0 and not a pytest skip: the run must look failed.
EXIT_BINDINGS_MISSING: Final = 2

#: The entry point a bindings module may expose to hand the probe a stack
#: handle. It is optional; see the probes' ``_open_stack`` for the fallback.
BINDINGS_FACTORY: Final = "create_stack_under_probe"

#: What to print before exiting with :data:`EXIT_BINDINGS_MISSING`.
BINDING_GUIDANCE: Final = """\
The Python bindings of the selected SIP stack are not importable here, so this
probe cannot run. It is failing loudly on purpose: a skipped probe is not
evidence, and ADR-0019 consequence K2 must not be released on a skip.

ADR-0019 selected reSIProcate and drives it from Python through its bindings,
which are built with BUILD_PYTHON=ON. Until those bindings import, E1 (S1-S11
baseline replay) and E4 (TLS certificate hot rotation) stay open as accepted
gaps.

How to make the bindings importable:

  1. Build reSIProcate with the Python bindings enabled:
         git clone https://github.com/resiprocate/resiprocate.git
         cd resiprocate && mkdir -p _build && cd _build
         cmake .. -DBUILD_PYTHON=ON -DCMAKE_BUILD_TYPE=Release
         make -j"$(nproc)"
     Note: testbed/simulators/resip-probe/build-req.sh already builds
     reSIProcate for the C++ probe, but it does not pass BUILD_PYTHON=ON.

  2. Put the built module on the import path and check it:
         export PYTHONPATH="<resiprocate>/_build/python:$PYTHONPATH"
         uv run python -c "import resip"

  3. Re-run this probe, pointing it at the module name if it is not `resip`:
         uv run python testbed/probe/e1_baseline_probe.py \\
             --bindings-module resip

If the binding is unavailable in your environment, run this probe on a host
where step 1 can be completed; the result belongs in docs/acceptance/report.md.
"""
