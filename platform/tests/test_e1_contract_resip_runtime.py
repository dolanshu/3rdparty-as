"""E1 contract smoke: product ``_resip_runtime`` S1/S2 shapes (REQ-F-6).

Maps to ``testbed/contracts/sip-baseline/S2-no-match-404`` (empty ruleset → 404) and a
narrow S1-style accept-all harness 200. Full S1–S4 contract replay lives in
``test_e1_contract_resip_runtime_full.py``.
"""

from __future__ import annotations

import socket
import uuid
from typing import Any

import pytest
from native_extensions import require_resip_runtime_extension

from as_platform.decision import Rule, RuleSet
from as_platform.decision.rules import Action
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.contract

_HOST = "127.0.0.1"
# S2 baseline: called number with no matching rule (see S2-no-match-404 README).
_S2_CALLED = "+99912345678"
# S3 baseline: block rule hit → 603 (see S3-policy-reject-603 README).
_S3_CALLED = "+8616800000000"
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


def _make_s2_invite(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:{_S2_CALLED}@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=e1-s2-caller",
        f"To: <sip:{_S2_CALLED}@{_HOST}>",
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


def _make_s1_invite_with_sdp(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    sdp = (
        "v=0\r\n"
        "o=e1-s1 0 0 IN IP4 127.0.0.1\r\n"
        "s=e1\r\n"
        "c=IN IP4 127.0.0.1\r\n"
        "t=0 0\r\n"
        "m=audio 9 RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
    )
    lines = (
        f"INVITE sip:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=e1-s1-caller",
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


def test_e1_s1_accept_all_harness_returns_200() -> None:
    """S1-style basic INVITE with SDP → 200 when ``accept_all_invites`` harness mode is on."""
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), accept_all_invites=True)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"e1-s1-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_s1_invite_with_sdp(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        assert _final_response_status(peer) == 200
    finally:
        listener.stop()
        peer.close()


def _make_s3_invite(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:{_S3_CALLED}@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=e1-s3-caller",
        f"To: <sip:{_S3_CALLED}@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@{_HOST}:{caller_port}>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def test_e1_s3_block_rule_returns_603() -> None:
    """REQ-F-7 / S3 shape: block rule → 603 Decline, no outbound leg."""
    _require_extension()
    rules = RuleSet(
        rules=(
            Rule(
                rule_id="R-BLOCK-90",
                prefix="+86168",
                action=Action.BLOCK,
            ),
        )
    )
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, rules)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"e1-s3-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_s3_invite(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        assert _final_response_status(peer) == 603
        assert listener.call_controller.active_call_count() == 0
    finally:
        listener.stop()
        peer.close()


def test_e1_s2_no_match_empty_rules_returns_404() -> None:
    """REQ-F-6: no routing rule match → 404 Not Found on product runtime (S2 shape)."""
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()))
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"e1-s2-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_s2_invite(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        assert _final_response_status(peer) == 404
        assert listener.call_controller.active_call_count() == 0
    finally:
        listener.stop()
        peer.close()
