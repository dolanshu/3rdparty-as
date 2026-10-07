"""The call-load harness writes each INVITE once.

Retransmission belongs to the SIP stack. This test delays the only response
past a short T1 and checks that the socket still saw a single INVITE.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from as_load.harness import LoadConfig, run_load

pytestmark = pytest.mark.contract


def test_load_generator_does_not_retransmit_invite(tmp_path: Path) -> None:
    """One INVITE datagram arrives even when the response waits longer than T1."""
    invites: list[bytes] = []
    ready = threading.Event()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(0.2)
    port = int(server.getsockname()[1])

    def serve() -> None:
        while not ready.is_set():
            try:
                payload, peer = server.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                return
            if payload.startswith(b"INVITE "):
                invites.append(payload)
                time.sleep(0.6)
                server.sendto(_ok(payload), peer)
                ready.set()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=2,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        ready.set()
        server.close()
        thread.join(timeout=2)

    assert len(invites) == 1
    assert summary["counts"]["invite_datagrams_sent"] == 1
    assert summary["capacity_commitment"] is False


def _ok(invite: bytes) -> bytes:
    headers: list[bytes] = []
    for line in invite.split(b"\r\n")[1:]:
        if not line:
            break
        name = line.split(b":", 1)[0].lower()
        if name in {b"via", b"from", b"call-id", b"cseq"}:
            headers.append(line)
        elif name == b"to":
            headers.append(line + b";tag=once")
    headers.append(b"Contact: <sip:once@127.0.0.1:9;transport=udp>")
    headers.append(b"Content-Length: 0")
    return b"SIP/2.0 200 OK\r\n" + b"\r\n".join(headers) + b"\r\n\r\n"
