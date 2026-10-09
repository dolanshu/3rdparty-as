"""Integration: product-path reSIProcate TCP listener + ingress gate + decide()."""

from __future__ import annotations

import socket
import uuid

import pytest
from native_extensions import require_resip_runtime_extension

from as_platform.decision import RuleSet
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TLS = TlsConfig(
    certificate_path="/etc/as/tls/as.pem",
    private_key_path="/etc/as/tls/as.key",
    ca_path="/etc/as/tls/ca.pem",
    require_client_certificate=False,
)
_RESPONSE_TIMEOUT_SECONDS = 5.0


def _require_extension() -> None:
    require_resip_runtime_extension()


def _seam(*addresses: str) -> TransportSeam:
    return TransportSeam(
        tls=_TLS,
        peer_policy=PeerPolicy(
            allowed_addresses=frozenset(addresses),
            allowed_certificate_ids=frozenset(),
        ),
        config_version=1,
    )


def _make_tcp_invite(server_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:+15558675309@{_HOST}:{server_port};transport=tcp SIP/2.0",
        f"Via: SIP/2.0/TCP {_HOST}:0;branch={branch}",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=as-runtime-tcp",
        f"To: <sip:+15558675309@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@{_HOST};transport=tcp>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def _final_response_status_tcp(peer: socket.socket) -> int:
    peer.settimeout(_RESPONSE_TIMEOUT_SECONDS)
    buffer = b""
    while True:
        chunk = peer.recv(65535)
        if not chunk:
            raise AssertionError("TCP connection closed before a final response")
        buffer += chunk
        while b"\r\n" in buffer:
            line, _, buffer = buffer.partition(b"\r\n")
            if not line:
                continue
            if line.startswith(b"SIP/2.0"):
                fields = line.split()
                if len(fields) >= 2 and fields[1].isdigit():
                    code = int(fields[1])
                    if code >= 200:
                        return code


def test_tcp_invite_empty_ruleset_returns_404() -> None:
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), enable_tcp=True)
    peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    call_id = f"tcp-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        assert listener.tcp_port is not None
        peer.connect((_HOST, listener.tcp_port))
        peer.sendall(_make_tcp_invite(listener.tcp_port, call_id))
        assert _final_response_status_tcp(peer) == 404
    finally:
        listener.stop()
        peer.close()
