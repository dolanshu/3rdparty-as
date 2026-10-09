"""Integration: product-path reSIProcate listener + ingress gate + decide()."""

from __future__ import annotations

import socket
import uuid
from typing import Any

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


def _seam(*addresses: str) -> TransportSeam:
    return TransportSeam(
        tls=_TLS,
        peer_policy=PeerPolicy(
            allowed_addresses=frozenset(addresses),
            allowed_certificate_ids=frozenset(),
        ),
        config_version=1,
    )


def _require_extension() -> Any:
    return require_resip_runtime_extension()


def _make_invite(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=as-runtime-caller",
        f"To: <sip:+15558675309@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@{_HOST}:{caller_port}>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def _final_response_status(peer: socket.socket) -> int:
    peer.settimeout(_RESPONSE_TIMEOUT_SECONDS)
    while True:
        response, _address = peer.recvfrom(65535)
        status_line = response.split(b"\r\n", 1)[0]
        fields = status_line.split()
        if len(fields) >= 2 and fields[1].isdigit() and int(fields[1]) >= 200:
            return int(fields[1])


def _make_invite_with_sdp(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    sdp = (
        "v=0\r\n"
        "o=as-runtime 0 0 IN IP4 127.0.0.1\r\n"
        "s=runtime-test\r\n"
        "c=IN IP4 127.0.0.1\r\n"
        "t=0 0\r\n"
        "m=audio 9 RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
    )
    lines = (
        f"INVITE sip:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=as-runtime-caller",
        f"To: <sip:+15558675309@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@{_HOST}:{caller_port}>",
        "Content-Type: application/sdp",
        f"Content-Length: {len(sdp)}",
        "",
        sdp,
    )
    return "\r\n".join(lines).encode("ascii")


def test_allowed_peer_empty_ruleset_returns_404() -> None:
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()))
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"allowed-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_invite(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        assert _final_response_status(peer) == 404
    finally:
        listener.stop()
        peer.close()


def test_accept_all_invites_harness_mode_returns_200() -> None:
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), accept_all_invites=True)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"accept-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_invite_with_sdp(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        assert _final_response_status(peer) == 200
    finally:
        listener.stop()
        peer.close()


def test_denied_peer_is_rejected_before_decide() -> None:
    _require_extension()
    gate = TransportIngressGate(_seam("10.255.255.254"))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()))
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"denied-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_invite(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        assert _final_response_status(peer) == 403
    finally:
        listener.stop()
        peer.close()
