"""REQ-F-4 engineering: SDP offer bytes preserved on runtime FORWARD path."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from native_extensions import require_resip_runtime_extension

from as_platform.decision import Rule, RuleSet
from as_platform.decision.rules import Action
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "two_leg_udp_peer.py"
_spec = importlib.util.spec_from_file_location("two_leg_udp_peer", _FIXTURE_PATH)
assert _spec is not None and _spec.loader is not None
_peer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_peer)
bind_udp = _peer.bind_udp
parse_sip_message = _peer.parse_sip_message

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TIMEOUT = 8.0
_TLS = TlsConfig(
    certificate_path="",
    private_key_path="",
    require_client_certificate=False,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "d11_sdp_offers"


def _load_offer_bytes(name: str) -> bytes:
    path = _FIXTURE_DIR / name
    if not path.is_file():
        pytest.skip(f"missing SDP fixture {path}")
    return path.read_bytes()


def _require_extension() -> object:
    return require_resip_runtime_extension()


def _invite_with_sdp(server_port: int, caller_port: int, call_id: str, sdp: bytes) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=sdp-offer",
        f"To: <sip:+15558675309@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@{_HOST}:{caller_port}>",
        "Content-Type: application/sdp",
        f"Content-Length: {len(sdp)}",
        "",
    )
    return ("\r\n".join(lines) + "\r\n").encode("ascii") + sdp


def _message_body(raw: bytes) -> bytes:
    if b"\r\n\r\n" not in raw:
        return b""
    return raw.split(b"\r\n\r\n", 1)[1]


@pytest.mark.parametrize(
    ("fixture_name", "expected_len"),
    (
        ("offer-230.bin", 230),
        ("offer-143.bin", 143),
        ("offer-233.bin", 233),
    ),
)
def test_forward_path_preserves_sdp_offer_bytes(fixture_name: str, expected_len: int) -> None:
    sdp = _load_offer_bytes(fixture_name)
    assert len(sdp) == expected_len
    _require_extension()
    upstream = bind_udp("upstream")
    downstream = bind_udp("downstream")
    downstream_port = downstream.getsockname()[1]
    route_uri = f"sip:peer@{_HOST}:{downstream_port};transport=udp"
    rules = RuleSet(
        rules=(
            Rule(
                rule_id="sdp-forward",
                prefix="+15558675309",
                action=Action.FORWARD,
                target=route_uri,
            ),
        )
    )
    gate = TransportIngressGate(
        TransportSeam(
            tls=_TLS,
            peer_policy=PeerPolicy(
                allowed_addresses=frozenset({_HOST}),
                allowed_certificate_ids=frozenset(),
            ),
            config_version=1,
        )
    )
    listener = ResipRuntimeListener(gate, rules)
    call_id = f"sdp-{expected_len}-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        invite = _invite_with_sdp(listener.port, upstream.getsockname()[1], call_id, sdp)
        upstream.sendto(invite, (_HOST, listener.port))
        downstream.settimeout(_TIMEOUT)
        while True:
            request, _ = downstream.recvfrom(65535)
            start_line, _ = parse_sip_message(request)
            if start_line.startswith("INVITE "):
                assert _message_body(request) == sdp
                break
    finally:
        listener.stop()
        upstream.close()
        downstream.close()
