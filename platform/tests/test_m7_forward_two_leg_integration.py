"""M7: product ``_resip_runtime`` FORWARD maps downstream 486 to inbound 486."""

from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

from as_platform.decision import Rule, RuleSet
from as_platform.decision.rules import Action
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener, load_resip_runtime_extension
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "two_leg_udp_peer.py"
_spec = importlib.util.spec_from_file_location("two_leg_udp_peer", _FIXTURE_PATH)
assert _spec is not None and _spec.loader is not None
_peer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_peer)
bind_udp = _peer.bind_udp
make_busy_response = _peer.make_busy_response
make_inbound_invite = _peer.make_inbound_invite
make_non2xx_ack = _peer.make_non2xx_ack
parse_sip_message = _peer.parse_sip_message
required_header = _peer.required_header

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TIMEOUT = 8.0
_TLS = TlsConfig(
    certificate_path="",
    private_key_path="",
    require_client_certificate=False,
)


def _require_extension():
    extension = load_resip_runtime_extension()
    if extension is None:
        pytest.skip("platform _resip_runtime extension not built; run make m2-platform-resip-build")
    return extension


def test_runtime_forward_downstream_486_maps_to_inbound_486() -> None:
    _require_extension()
    upstream = bind_udp("upstream")
    downstream = bind_udp("downstream")
    downstream_port = downstream.getsockname()[1]
    caller_port = upstream.getsockname()[1]
    route_uri = f"sip:+15559990002@{_HOST}:{downstream_port};transport=udp"
    rules = RuleSet(
        rules=(
            Rule(
                rule_id="runtime-forward",
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
    call_id = f"runtime-forward-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        inbound_invite = make_inbound_invite(listener.port, caller_port, call_id)
        upstream.sendto(inbound_invite, (_HOST, listener.port))

        downstream.settimeout(_TIMEOUT)
        outbound_invite = b""
        dum_address = ("", 0)
        while True:
            request, address = downstream.recvfrom(65535)
            start_line, _ = parse_sip_message(request)
            if start_line.startswith("INVITE "):
                outbound_invite = request
                dum_address = address
                break

        busy = make_busy_response(outbound_invite)
        downstream.sendto(busy, dum_address)

        deadline = time.monotonic() + _TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pytest.fail("timed out waiting for downstream ACK")
            downstream.settimeout(remaining)
            followup, address = downstream.recvfrom(65535)
            start_line, _ = parse_sip_message(followup)
            if start_line.startswith("ACK "):
                break

        upstream.settimeout(_TIMEOUT)
        upstream_response = b""
        while True:
            response, address = upstream.recvfrom(65535)
            status = int(parse_sip_message(response)[0].split()[1])
            if status >= 200:
                upstream_response = response
                assert address == (_HOST, listener.port)
                break

        assert int(parse_sip_message(upstream_response)[0].split()[1]) == 486
        assert required_header(parse_sip_message(upstream_response)[1], "call-id") == call_id
        upstream.sendto(
            make_non2xx_ack(inbound_invite, upstream_response),
            (_HOST, listener.port),
        )
    finally:
        listener.stop()
        upstream.close()
        downstream.close()
