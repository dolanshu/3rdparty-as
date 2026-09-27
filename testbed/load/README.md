# `testbed/load/`

Capacity harness: generates SIP load and measures where the boundary is.

## The one rule that matters

**Load goes over real sockets.** The POC's harness drove callbacks directly, which
bypassed the socket and the event loop — it measured business logic, not the
system. Numbers from such a harness cannot answer "has CPS hit the wall", and
therefore cannot decide whether Go is needed (ADR-0014).

## What it must produce

Per stack: CPS, concurrent sessions, call setup latency — and the resource that
saturated first. This is the input to O1 and to ADR-0011; it is not a marketing
number and is not published before M6
([`../../docs/plan.md`](../../docs/plan.md)).

SIPp (GPL) is acceptable here: internal test use only, never distributed with the
product.
