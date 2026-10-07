"""RFC 3261 Timer A send offsets for an INVITE on an unreliable transport.

reSIProcate owns retransmission inside the product stack. This module does not
send packets and the call-load harness does not import it. A contract test uses
the offsets to emit datagrams and observe the resent copies on a real socket.
"""

from __future__ import annotations


def invite_timer_a_offsets(t1_seconds: float, transmissions: int) -> tuple[float, ...]:
    """Return send times for an INVITE client transaction.

    The first transmission is at ``0``. Each later transmission follows Timer A,
    which starts at ``T1`` and doubles after every firing (RFC 3261 §17.1.1.2).
    INVITE Timer A is not capped at ``T2``; Timer B (``64*T1``) bounds how long
    the transaction keeps sending.

    Args:
        t1_seconds: SIP ``T1``, in seconds. Must be positive.
        transmissions: How many INVITE copies to schedule, including the first.
            Must be at least 1. Offsets that would fall after Timer B are omitted.

    Returns:
        Monotonic send times in seconds, starting at ``0``.
    """
    if t1_seconds <= 0:
        raise ValueError("t1_seconds must be positive")
    if transmissions < 1:
        raise ValueError("transmissions must be at least 1")

    timer_b = 64 * t1_seconds
    offsets = [0.0]
    delay = t1_seconds
    while len(offsets) < transmissions:
        next_offset = offsets[-1] + delay
        if next_offset >= timer_b:
            break
        offsets.append(next_offset)
        delay *= 2
    return tuple(offsets)
