"""E1 contract replay: S1/S2/S3/S4 shapes on product ``_resip_runtime``."""

from __future__ import annotations

import socket
import uuid
from pathlib import Path
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
_RESPONSE_TIMEOUT_SECONDS = 8.0
_BASELINE_ROOT = Path(__file__).resolve().parents[2] / "testbed" / "contracts" / "sip-baseline"
_TLS = TlsConfig(
    certificate_path="/etc/as/tls/as.pem",
    private_key_path="/etc/as/tls/as.key",
    ca_path="/etc/as/tls/ca.pem",
    require_client_certificate=False,
)
_S2_CALLED = "+99912345678"
_S3_CALLED = "+8616800000000"


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


def _load_contract_message(scenario: str, filename: str) -> bytes:
    path = _BASELINE_ROOT / scenario / filename
    if not path.is_file():
        pytest.skip(f"missing contract fixture {path}")
    text = path.read_text(encoding="utf-8")
    if "\r\n\r\n" in text:
        return text.encode("latin-1")
    if "\n\n" in text:
        head, body = text.split("\n\n", 1)
        head_crlf = head.replace("\n", "\r\n")
        body_crlf = body.replace("\n", "\r\n")
        if not body_crlf.endswith("\r\n"):
            body_crlf += "\r\n"
        return (head_crlf + "\r\n\r\n" + body_crlf).encode("latin-1")
    return text.replace("\n", "\r\n").encode("latin-1")


def _rewrite_request_uri(
    message: bytes,
    server_port: int,
    caller_port: int,
    *,
    via_branch: str | None = None,
) -> bytes:
    text = message.decode("latin-1")
    lines = text.split("\r\n")
    if not lines[0].startswith("INVITE ") and not lines[0].startswith("CANCEL "):
        return message
    method, rest = lines[0].split(" ", 1)
    uri = rest.split(" ", 1)[0]
    if "@" in uri:
        user_part, _host = uri.split("@", 1)
        new_uri = f"{user_part}@{_HOST}:{server_port}"
    else:
        new_uri = rest
    if method == "CANCEL":
        lines[0] = f"CANCEL {new_uri} SIP/2.0"
    else:
        lines[0] = f"{method} {new_uri} SIP/2.0"
    out: list[str] = []
    for line in lines:
        lower = line.lower()
        if lower.startswith("route:"):
            continue
        if line.lower().startswith("contact:"):
            out.append(f"Contact: <sip:peer@{_HOST}:{caller_port}>")
        elif line.lower().startswith("via:") and "branch=" in line:
            branch = via_branch or f"z9hG4bK-{uuid.uuid4().hex}"
            out.append(f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport")
        else:
            out.append(line)
    return "\r\n".join(out).encode("latin-1")


def _final_response_status(peer: socket.socket) -> int:
    peer.settimeout(_RESPONSE_TIMEOUT_SECONDS)
    while True:
        response, _address = peer.recvfrom(65535)
        status_line = response.split(b"\r\n", 1)[0]
        fields = status_line.split()
        if len(fields) >= 2 and fields[1].isdigit() and int(fields[1]) >= 200:
            return int(fields[1])


def _wait_provisional(peer: socket.socket, code: int) -> None:
    peer.settimeout(_RESPONSE_TIMEOUT_SECONDS)
    while True:
        response, _ = peer.recvfrom(65535)
        status_line = response.split(b"\r\n", 1)[0]
        fields = status_line.split()
        if len(fields) >= 2 and fields[1].isdigit() and int(fields[1]) == code:
            return


def test_e1_s1_accept_all_from_contract_invite() -> None:
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), accept_all_invites=True)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    try:
        listener.start()
        invite = _rewrite_request_uri(
            _load_contract_message("S1-basic-call", "01-in-invite-trunk.txt"),
            listener.port,
            peer.getsockname()[1],
        )
        peer.sendto(invite, (_HOST, listener.port))
        assert _final_response_status(peer) == 200
    finally:
        listener.stop()
        peer.close()


def test_e1_s2_no_match_from_contract_shape() -> None:
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()))
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    try:
        listener.start()
        raw = _load_contract_message("S2-no-match-404", "01-in-invite-trunk.txt")
        text = raw.decode("latin-1")
        text = text.replace("+8613800138000", _S2_CALLED, 1)
        invite = _rewrite_request_uri(text.encode("latin-1"), listener.port, peer.getsockname()[1])
        peer.sendto(invite, (_HOST, listener.port))
        assert _final_response_status(peer) == 404
    finally:
        listener.stop()
        peer.close()


def test_e1_s3_block_rule_from_contract_shape() -> None:
    _require_extension()
    rules = RuleSet(rules=(Rule(rule_id="R-BLOCK-90", prefix="+86168", action=Action.BLOCK),))
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(gate, rules)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    try:
        listener.start()
        invite = _rewrite_request_uri(
            _load_contract_message("S3-policy-reject-603", "01-in-invite-trunk.txt"),
            listener.port,
            peer.getsockname()[1],
        )
        peer.sendto(invite, (_HOST, listener.port))
        assert _final_response_status(peer) == 603
    finally:
        listener.stop()
        peer.close()


def test_e1_s4_caller_cancel_returns_487() -> None:
    """S4 early cancel: 100/180 then CANCEL → 487 on product runtime."""
    _require_extension()
    gate = TransportIngressGate(_seam(_HOST))
    listener = ResipRuntimeListener(
        gate,
        RuleSet(rules=()),
        accept_all_invites=True,
        early_cancel_harness=True,
    )
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    try:
        listener.start()
        caller_port = peer.getsockname()[1]
        branch = f"z9hG4bK-{uuid.uuid4().hex}"
        invite = _rewrite_request_uri(
            _load_contract_message("S4-caller-cancel", "01-in-invite-trunk.txt"),
            listener.port,
            caller_port,
            via_branch=branch,
        )
        cancel = _rewrite_request_uri(
            _load_contract_message("S4-caller-cancel", "05-in-cancel-trunk.txt"),
            listener.port,
            caller_port,
            via_branch=branch,
        )
        peer.sendto(invite, (_HOST, listener.port))
        _wait_provisional(peer, 100)
        _wait_provisional(peer, 180)
        peer.sendto(cancel, (_HOST, listener.port))
        peer.settimeout(_RESPONSE_TIMEOUT_SECONDS)
        saw_487 = False
        while not saw_487:
            response, _ = peer.recvfrom(65535)
            if response.startswith(b"SIP/2.0 487"):
                saw_487 = True
        assert saw_487
    finally:
        listener.stop()
        peer.close()
