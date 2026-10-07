"""Outbound reads survive a quiet socket timeout."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from as_simulators.bridge import TransparentBridge

pytestmark = pytest.mark.integration


def test_bridge_forwards_a_response_after_the_outbound_socket_times_out() -> None:
    """A response that arrives after the outbound timeout is still forwarded."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    next_port = int(listener.getsockname()[1])
    done = threading.Event()

    def _answer_late() -> None:
        connection, _peer = listener.accept()
        try:
            payload = b""
            while b"\r\n\r\n" not in payload:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                payload += chunk
            time.sleep(0.25)
            head = payload.split(b"\r\n\r\n", 1)[0].decode("ascii")
            vias = [line for line in head.split("\r\n") if line.lower().startswith("via:")]
            response = "\r\n".join(
                [
                    "SIP/2.0 200 OK",
                    *vias,
                    "From: <sip:alice@example>;tag=a",
                    "To: <sip:bob@example>;tag=late",
                    "Call-ID: bridge-quiet",
                    "CSeq: 1 INVITE",
                    "Content-Length: 0",
                    "",
                    "",
                ]
            )
            connection.sendall(response.encode("ascii"))
            done.wait(2)
        finally:
            connection.close()

    thread = threading.Thread(target=_answer_late, daemon=True)
    thread.start()
    bridge = TransparentBridge(
        advertised_host="127.0.0.1",
        next_hop=("127.0.0.1", next_port),
        transport="tcp",
        outbound_timeout=0.05,
    )
    bridge.start()
    client = socket.create_connection(("127.0.0.1", bridge.port), 2)
    client.settimeout(2)
    try:
        client.sendall(
            b"\r\n".join(
                [
                    b"INVITE sip:bob@example SIP/2.0",
                    b"Via: SIP/2.0/TCP 127.0.0.1:9;branch=z9hG4bK-from-test",
                    b"Max-Forwards: 70",
                    b"From: <sip:alice@example>;tag=a",
                    b"To: <sip:bob@example>",
                    b"Call-ID: bridge-quiet",
                    b"CSeq: 1 INVITE",
                    b"Content-Length: 0",
                    b"",
                    b"",
                ]
            )
        )
        received = b""
        while b"\r\n\r\n" not in received:
            received += client.recv(4096)
    finally:
        done.set()
        client.close()
        bridge.stop()
        listener.close()
        thread.join(timeout=2)

    assert b"SIP/2.0 200" in received
