"""The AS boundary against the SIP world: seams only, no stack.

Everything under this package is the seam between the kernel and SIP. Before M2b
completes, this package carries **no SIP stack dependency at all** --- no
reSIProcate, no sippy, no socket. The point of that is testability: the kernel
must be provable without a stack, which is the M2 exit criterion in
``docs/plan.md`` ("build use cases on it without touching sippy").

What lives here therefore has a fixed shape:

* :mod:`as_platform.sip.adapter` --- what a SIP message looks like once it has
  been translated into a kernel data structure, and the :class:`SipAdapter`
  Protocol that a real binding must satisfy (ADR-0019, reSIProcate).
* :mod:`as_platform.sip.transport` --- who may talk to us (peer whitelist) and
  with which certificates (TLS, mTLS preferred), plus the hot-rotation path
  (ADR-0016).

The implementation behind those seams is injected by the stack-binding step of
M2b; the kernel depends only on the shapes defined here. Every judgement in
this package stays a pure function --- no IO, no clock, no global state --- so
that it can be driven by TDD exactly like ``decide()`` (AGENT.md §5).
"""

from __future__ import annotations
