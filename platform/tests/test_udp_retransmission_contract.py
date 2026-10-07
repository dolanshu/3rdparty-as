"""Observe UDP INVITE retransmission on the socket, outside the call-load harness.

The product stack retransmits inside reSIProcate. This contract does not drive
``as_load``. It schedules RFC 3261 Timer A offsets and checks that a listening
socket sees every resent datagram.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from as_platform.sip.udp_retransmit_schedule import invite_timer_a_offsets

pytestmark = pytest.mark.contract

_INVITE = (
    b"INVITE sip:+155500010001@127.0.0.1 SIP/2.0\r\n"
    b"Via: SIP/2.0/UDP 127.0.0.1:9;branch=z9hG4bKretransmit\r\n"
    b"Max-Forwards: 70\r\n"
    b"From: <sip:+8613911111111@localhost>;tag=retransmit\r\n"
    b"To: <sip:+155500010001@127.0.0.1>\r\n"
    b"Call-ID: retransmit@as-contract\r\n"
    b"CSeq: 1 INVITE\r\n"
    b"Content-Length: 0\r\n\r\n"
)


def test_invite_timer_a_doubles_until_timer_b() -> None:
    """Timer A is T1, then 2*T1, then 4*T1, and nothing is scheduled at Timer B."""
    assert invite_timer_a_offsets(0.5, 4) == (0.0, 0.5, 1.5, 3.5)
    assert invite_timer_a_offsets(0.5, 1) == (0.0,)
    # 64*T1 is 32s. The geometric series reaches that bound before 20 copies.
    offsets = invite_timer_a_offsets(0.5, 20)
    assert offsets[-1] < 32.0
    assert all(later > earlier for earlier, later in zip(offsets, offsets[1:], strict=False))


def test_invite_timer_a_rejects_non_positive_inputs() -> None:
    """A zero timer or an empty schedule is not a SIP client transaction."""
    with pytest.raises(ValueError, match="t1_seconds"):
        invite_timer_a_offsets(0, 1)
    with pytest.raises(ValueError, match="transmissions"):
        invite_timer_a_offsets(0.5, 0)


def test_udp_listener_observes_each_timer_a_retransmission() -> None:
    """A socket sees one datagram per Timer A transmission, byte for byte."""
    offsets = invite_timer_a_offsets(0.02, 3)
    received: list[bytes] = []
    ready = threading.Event()
    done = threading.Event()

    def listen() -> None:
        while not done.is_set():
            try:
                payload, _peer = server.recvfrom(65535)
            except TimeoutError:
                continue
            received.append(payload)
            if len(received) >= len(offsets):
                ready.set()
                return

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(0.05)
    port = int(server.getsockname()[1])
    listener = threading.Thread(target=listen, daemon=True)
    listener.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        started = time.monotonic()
        for offset in offsets:
            delay = offset - (time.monotonic() - started)
            if delay > 0:
                time.sleep(delay)
            client.sendto(_INVITE, ("127.0.0.1", port))
        assert ready.wait(1.0)
    finally:
        done.set()
        client.close()
        server.close()
        listener.join(timeout=1)

    assert received == [_INVITE, _INVITE, _INVITE]
