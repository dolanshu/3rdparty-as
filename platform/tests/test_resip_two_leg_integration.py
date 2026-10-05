"""Integration: product-path two-leg DUM maps downstream 486 to inbound 486."""

from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from as_platform.decision import RuleSet, decide
from as_platform.decision.decide import DecisionAction, DecisionRequest
from as_platform.decision.rules import Action, Rule
from as_platform.sip.resip_two_leg import load_resip_two_leg_extension

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
reserve_udp_port = _peer.reserve_udp_port

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TIMEOUT = 8.0


def _require_extension() -> Any:
    extension = load_resip_two_leg_extension()
    if extension is None:
        pytest.skip(
            "platform _resip_two_leg extension not built; run make m7-platform-two-leg-build"
        )
    return extension


def test_downstream_486_maps_to_inbound_486() -> None:
    two_leg = _require_extension()
    upstream = bind_udp("upstream")
    downstream = bind_udp("downstream")
    server_port = reserve_udp_port()
    caller_port = upstream.getsockname()[1]
    downstream_port = downstream.getsockname()[1]
    assert len({server_port, caller_port, downstream_port}) == 3

    call_id = f"two-leg-in-{uuid.uuid4()}@{_HOST}"
    route_uri = f"sip:+15559990002@{_HOST}:{downstream_port};transport=udp"
    rules = RuleSet(
        rules=(
            Rule(
                rule_id="two-leg-forward",
                prefix="+15558675309",
                action=Action.FORWARD,
                target=route_uri,
            ),
        )
    )

    def route_callback(received_call_id: str, calling_number: str, called_number: str) -> str:
        decision = decide(
            DecisionRequest(
                call_id=received_call_id,
                calling_number=calling_number,
                called_number=called_number,
                received_at=0.0,
            ),
            rules,
        )
        assert decision.action is DecisionAction.FORWARD
        assert decision.target == route_uri
        return decision.target or ""

    server = None
    markers: dict[str, Any] | None = None
    outgoing_call_id = ""
    try:
        server = two_leg.start_uas(server_port, downstream_port, route_callback)
        inbound_invite = make_inbound_invite(server_port, caller_port, call_id)
        upstream.sendto(inbound_invite, (_HOST, server_port))

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

        _, outbound_headers = parse_sip_message(outbound_invite)
        outgoing_call_id = required_header(outbound_headers, "call-id")
        assert outgoing_call_id != call_id

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
                assert address == dum_address
                break
            if start_line.startswith("INVITE ") and followup == outbound_invite:
                downstream.sendto(busy, address)

        upstream.settimeout(_TIMEOUT)
        upstream_statuses: list[int] = []
        upstream_response = b""
        while True:
            response, address = upstream.recvfrom(65535)
            status = int(parse_sip_message(response)[0].split()[1])
            upstream_statuses.append(status)
            if status >= 200:
                upstream_response = response
                assert address == (_HOST, server_port)
                break

        assert upstream_statuses[-1] == 486
        assert required_header(parse_sip_message(upstream_response)[1], "call-id") == call_id
        upstream.sendto(
            make_non2xx_ack(inbound_invite, upstream_response),
            (_HOST, server_port),
        )
    finally:
        if server is not None:
            markers = two_leg.stop_and_join(server)
        upstream.close()
        downstream.close()

    assert markers is not None
    assert markers["failure_mapped"] is True
    assert markers["upstream_status"] == 486
    assert markers["outbound_final_status"] == 486
    assert markers["incoming_call_id"] == call_id
    assert markers["outgoing_call_id"] == outgoing_call_id
