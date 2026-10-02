from __future__ import annotations

import os
import re
import socket
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = Path("/home/shudong/project/3rdparty-as")
WIRE_DIR = ROOT / "wire"
sys.path.insert(0, str(REPO / "platform" / "src"))
sys.path.insert(0, str(ROOT))

import _resip_dum
from as_platform.decision.decide import DecisionAction, DecisionRequest, decide
from as_platform.decision.rules import Action, Rule, RuleSet


def configured_port(environment_name: str) -> int | None:
    value = os.environ.get(environment_name)
    if value is None:
        return None
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError(f"{environment_name} must be between 1 and 65535")
    return port


def reserve_server_port() -> int:
    requested_port = configured_port("SPIKE_UAS_PORT")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", requested_port or 0))
        port = reservation.getsockname()[1]
    print(f"PORT_RESERVED role=dum_uas address=127.0.0.1 port={port}", flush=True)
    return port


def bind_peer_socket(role: str, environment_name: str) -> socket.socket:
    requested_port = configured_port(environment_name)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind(("127.0.0.1", requested_port or 0))
    port = peer.getsockname()[1]
    print(f"PORT_RESERVED role={role} address=127.0.0.1 port={port}", flush=True)
    return peer


def save_wire_message(filename: str, message: bytes) -> None:
    destination = WIRE_DIR / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(message)
    print(f"WIRE_SAVED path={destination} bytes={len(message)}", flush=True)


def parse_sip_message(message: bytes) -> tuple[str, dict[str, list[str]]]:
    header_block = message.split(b"\r\n\r\n", 1)[0]
    lines = header_block.decode("latin-1").split("\r\n")
    if not lines or not lines[0]:
        raise AssertionError("empty SIP start line")

    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"malformed SIP header line: {line!r}")
        headers.setdefault(name.strip().lower(), []).append(value.strip())
    return lines[0], headers


def header_values(headers: dict[str, list[str]], name: str) -> list[str]:
    compact_names = {
        "via": ("via", "v"),
        "from": ("from", "f"),
        "to": ("to", "t"),
        "call-id": ("call-id", "i"),
        "cseq": ("cseq",),
    }
    values: list[str] = []
    for candidate in compact_names[name]:
        values.extend(headers.get(candidate, ()))
    return values


def required_header(headers: dict[str, list[str]], name: str) -> str:
    values = header_values(headers, name)
    if not values:
        raise AssertionError(f"outbound INVITE is missing {name}")
    return values[0]


def make_busy_response(request: bytes) -> bytes:
    _, headers = parse_sip_message(request)
    vias = header_values(headers, "via")
    from_value = required_header(headers, "from")
    to_value = required_header(headers, "to")
    call_id = required_header(headers, "call-id")
    cseq = required_header(headers, "cseq")
    if not vias:
        raise AssertionError("outbound INVITE is missing Via")
    if not re.search(r"\bINVITE\b", cseq, flags=re.IGNORECASE):
        raise AssertionError(f"unexpected outbound CSeq: {cseq!r}")
    if not re.search(r"(?:^|;)\s*tag\s*=", to_value, flags=re.IGNORECASE):
        to_value = f"{to_value};tag=two-leg-spike-peer"

    response_lines = ["SIP/2.0 486 Busy Here"]
    response_lines.extend(f"Via: {via}" for via in vias)
    response_lines.extend(
        (
            f"From: {from_value}",
            f"To: {to_value}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq}",
            "Content-Length: 0",
            "",
            "",
        )
    )
    return "\r\n".join(response_lines).encode("latin-1")


def assert_busy_response_matches(request: bytes, response: bytes) -> None:
    request_line, request_headers = parse_sip_message(request)
    response_line, response_headers = parse_sip_message(response)
    if response_line != "SIP/2.0 486 Busy Here":
        raise AssertionError(f"unexpected downstream response: {response_line!r}")
    if not request_line.startswith("INVITE "):
        raise AssertionError(f"response did not match an INVITE: {request_line!r}")
    for name in ("via", "from", "call-id", "cseq"):
        if header_values(response_headers, name) != header_values(request_headers, name):
            raise AssertionError(f"downstream 486 {name} does not match the INVITE")

    request_to = required_header(request_headers, "to")
    response_to = required_header(response_headers, "to")
    if response_to != request_to and not response_to.startswith(f"{request_to};tag="):
        raise AssertionError("downstream 486 To does not match the INVITE To")


def make_non2xx_ack(request: bytes, response: bytes) -> bytes:
    request_line, request_headers = parse_sip_message(request)
    response_line, response_headers = parse_sip_message(response)
    request_fields = request_line.split()
    response_fields = response_line.split()
    if len(request_fields) != 3 or request_fields[0] != "INVITE":
        raise AssertionError(f"cannot ACK non-INVITE request: {request_line!r}")
    if len(response_fields) < 2 or response_fields[1] not in {"300", "301", "302", "305", "380", "400", "401", "403", "404", "408", "480", "481", "486", "488", "500", "502", "503", "603"}:
        raise AssertionError(f"cannot build non-2xx ACK for {response_line!r}")

    sequence, method = required_header(request_headers, "cseq").split()
    if method.upper() != "INVITE":
        raise AssertionError(f"unexpected INVITE CSeq method: {method!r}")
    ack_lines = [f"ACK {request_fields[1]} SIP/2.0"]
    ack_lines.extend(f"Via: {via}" for via in header_values(request_headers, "via"))
    ack_lines.extend(
        (
            "Max-Forwards: 70",
            f"From: {required_header(request_headers, 'from')}",
            f"To: {required_header(response_headers, 'to')}",
            f"Call-ID: {required_header(request_headers, 'call-id')}",
            f"CSeq: {sequence} ACK",
            "Content-Length: 0",
            "",
            "",
        )
    )
    return "\r\n".join(ack_lines).encode("latin-1")


def assert_non2xx_ack_matches(request: bytes, response: bytes, ack: bytes) -> None:
    request_line, request_headers = parse_sip_message(request)
    response_line, _ = parse_sip_message(response)
    ack_line, ack_headers = parse_sip_message(ack)
    request_fields = request_line.split()
    ack_fields = ack_line.split()
    if len(ack_fields) != 3 or ack_fields[0] != "ACK":
        raise AssertionError(f"expected transaction ACK, got {ack_line!r}")
    if ack_fields[1] != request_fields[1]:
        raise AssertionError("transaction ACK Request-URI differs from the INVITE")
    for name in ("via", "from", "call-id"):
        if header_values(ack_headers, name) != header_values(request_headers, name):
            raise AssertionError(f"transaction ACK {name} does not match the INVITE")
    sequence = required_header(request_headers, "cseq").split()[0]
    if required_header(ack_headers, "cseq") != f"{sequence} ACK":
        raise AssertionError("transaction ACK CSeq does not match the INVITE")
    if required_header(ack_headers, "to") != required_header(
        parse_sip_message(response)[1], "to"
    ):
        raise AssertionError("transaction ACK To does not match the final response")
    if not response_line.startswith("SIP/2.0 4") and not response_line.startswith("SIP/2.0 5"):
        raise AssertionError("transaction ACK is not for a non-2xx final response")


def make_inbound_invite(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:+15558675309@127.0.0.1:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP 127.0.0.1:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        "From: <sip:+15551230001@127.0.0.1>;tag=two-leg-caller",
        "To: <sip:+15558675309@127.0.0.1>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@127.0.0.1:{caller_port}>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def receive_outbound_invite(
    downstream_peer: socket.socket,
) -> tuple[bytes, tuple[str, int]]:
    downstream_peer.settimeout(8.0)
    while True:
        request, address = downstream_peer.recvfrom(65535)
        start_line, _ = parse_sip_message(request)
        print(
            f"DOWNSTREAM_DATAGRAM start_line={start_line!r} "
            f"from={address[0]}:{address[1]} bytes={len(request)}",
            flush=True,
        )
        if start_line.startswith("INVITE "):
            save_wire_message("downstream-outbound-invite.sip", request)
            return request, address


def receive_downstream_ack(
    downstream_peer: socket.socket,
    outbound_invite: bytes,
    busy_response: bytes,
    dum_address: tuple[str, int],
) -> bytes:
    deadline = time.monotonic() + 8.0
    followup_index = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for DUM's non-2xx transaction ACK")
        downstream_peer.settimeout(remaining)
        message, address = downstream_peer.recvfrom(65535)
        start_line, _ = parse_sip_message(message)
        save_wire_message(f"downstream-followup-{followup_index:02d}.sip", message)
        followup_index += 1
        print(
            f"DOWNSTREAM_FOLLOWUP start_line={start_line!r} "
            f"from={address[0]}:{address[1]}",
            flush=True,
        )
        if start_line.startswith("ACK "):
            if address != dum_address:
                raise AssertionError(f"downstream ACK came from unexpected peer {address}")
            assert_non2xx_ack_matches(outbound_invite, busy_response, message)
            return message
        if start_line.startswith("INVITE ") and message == outbound_invite:
            downstream_peer.sendto(busy_response, address)
            print("DOWNSTREAM_RETRANSMISSION_REPLIED status=486", flush=True)
            continue
        raise AssertionError(f"unexpected downstream follow-up: {start_line!r}")


def receive_upstream_final(
    upstream_peer: socket.socket,
) -> tuple[bytes, tuple[str, int], list[int]]:
    upstream_peer.settimeout(8.0)
    statuses: list[int] = []
    response_index = 0
    while True:
        response, address = upstream_peer.recvfrom(65535)
        start_line, _ = parse_sip_message(response)
        fields = start_line.split()
        if len(fields) < 2 or not fields[1].isdigit():
            raise AssertionError(f"invalid SIP response start line: {start_line!r}")
        status = int(fields[1])
        statuses.append(status)
        save_wire_message(f"upstream-response-{response_index:02d}.sip", response)
        response_index += 1
        print(
            f"UPSTREAM_RESPONSE status={status} start_line={start_line!r} "
            f"from={address[0]}:{address[1]}",
            flush=True,
        )
        if status >= 200:
            return response, address, statuses


def run_case() -> None:
    started_at = time.perf_counter()
    upstream_peer = bind_peer_socket("upstream_client", "SPIKE_UPSTREAM_PORT")
    downstream_peer = bind_peer_socket("downstream_peer", "SPIKE_DOWNSTREAM_PORT")
    server_port = reserve_server_port()
    caller_port = upstream_peer.getsockname()[1]
    downstream_port = downstream_peer.getsockname()[1]
    if len({server_port, caller_port, downstream_port}) != 3:
        raise AssertionError("UAS, upstream, and downstream UDP ports must differ")

    call_id = f"two-leg-in-{uuid.uuid4()}@127.0.0.1"
    route_uri = (
        f"sip:+15559990002@127.0.0.1:{downstream_port};transport=udp"
    )
    route_rules = RuleSet(
        rules=(
            Rule(
                rule_id="two-leg-forward",
                prefix="+15558675309",
                action=Action.FORWARD,
                target=route_uri,
            ),
        )
    )
    callback_observations: list[dict[str, object]] = []

    def python_route_callback(
        received_call_id: str, calling_number: str, called_number: str
    ) -> str:
        callback_started_at = time.perf_counter()
        request = DecisionRequest(
            call_id=received_call_id,
            calling_number=calling_number,
            called_number=called_number,
            received_at=0.0,
        )
        decision = decide(request, route_rules)
        callback_elapsed_ms = (time.perf_counter() - callback_started_at) * 1000
        observation = {
            "call_id": received_call_id,
            "calling_number": calling_number,
            "called_number": called_number,
            "action": decision.action.value,
            "target": decision.target,
            "matched_rule_id": decision.matched_rule_id,
            "elapsed_ms": callback_elapsed_ms,
        }
        callback_observations.append(observation)
        print(f"PYTHON_POLICY_DECISION observation={observation!r}", flush=True)
        if decision.action is not DecisionAction.FORWARD:
            raise AssertionError(f"expected FORWARD, got {decision.action}")
        if decision.target != route_uri:
            raise AssertionError(
                f"expected route {route_uri!r}, got {decision.target!r}"
            )
        return decision.target

    server = None
    markers: dict[str, object] | None = None
    try:
        server = _resip_dum.start_uas(
            server_port, downstream_port, python_route_callback
        )
        started_server_at = time.perf_counter()
        inbound_invite = make_inbound_invite(server_port, caller_port, call_id)
        save_wire_message("upstream-inbound-invite.sip", inbound_invite)
        upstream_peer.sendto(inbound_invite, ("127.0.0.1", server_port))
        print(
            f"UPSTREAM_INVITE_SENT call_id={call_id} "
            f"target=127.0.0.1:{server_port}",
            flush=True,
        )

        outbound_invite, dum_address = receive_outbound_invite(downstream_peer)
        outbound_start_line, outbound_headers = parse_sip_message(outbound_invite)
        outbound_fields = outbound_start_line.split()
        if len(outbound_fields) != 3 or outbound_fields[0] != "INVITE":
            raise AssertionError(f"unexpected outbound request: {outbound_start_line}")
        actual_target_uri = outbound_fields[1]
        outgoing_call_id = required_header(outbound_headers, "call-id")
        if actual_target_uri != route_uri:
            raise AssertionError(
                f"outbound target {actual_target_uri!r} != expected {route_uri!r}"
            )
        if outgoing_call_id == call_id:
            raise AssertionError("the two SIP legs must use distinct Call-IDs")
        print(
            f"OUTBOUND_INVITE_ASSERTED incoming_call_id={call_id} "
            f"outgoing_call_id={outgoing_call_id} target_uri={actual_target_uri}",
            flush=True,
        )

        busy_response = make_busy_response(outbound_invite)
        assert_busy_response_matches(outbound_invite, busy_response)
        save_wire_message("downstream-486-busy-here.sip", busy_response)
        downstream_peer.sendto(busy_response, dum_address)
        print(
            f"DOWNSTREAM_486_SENT call_id={outgoing_call_id} "
            f"to={dum_address[0]}:{dum_address[1]}",
            flush=True,
        )
        downstream_ack = receive_downstream_ack(
            downstream_peer, outbound_invite, busy_response, dum_address
        )
        print(
            f"DOWNSTREAM_ACK_ASSERTED call_id={outgoing_call_id} "
            f"cseq=1 ACK bytes={len(downstream_ack)}",
            flush=True,
        )

        upstream_response, response_address, upstream_statuses = (
            receive_upstream_final(upstream_peer)
        )
        response_start_line, response_headers = parse_sip_message(upstream_response)
        response_status = int(response_start_line.split()[1])
        if response_status != 486:
            raise AssertionError(f"expected upstream 486, got {response_start_line}")
        if response_address != ("127.0.0.1", server_port):
            raise AssertionError(f"upstream response came from {response_address}")
        if required_header(response_headers, "call-id") != call_id:
            raise AssertionError("upstream failure must retain the inbound Call-ID")
        if required_header(response_headers, "cseq") != "1 INVITE":
            raise AssertionError("upstream response CSeq does not match inbound leg")
        if not upstream_statuses or upstream_statuses[-1] != 486:
            raise AssertionError(f"unexpected upstream response sequence: {upstream_statuses}")
        upstream_ack = make_non2xx_ack(inbound_invite, upstream_response)
        assert_non2xx_ack_matches(inbound_invite, upstream_response, upstream_ack)
        save_wire_message("upstream-client-ack.sip", upstream_ack)
        upstream_peer.sendto(upstream_ack, ("127.0.0.1", server_port))
        print(
            f"UPSTREAM_ACK_SENT call_id={call_id} to=127.0.0.1:{server_port}",
            flush=True,
        )
        print(
            f"UPSTREAM_FAILURE_ASSERTED status=486 call_id={call_id} "
            f"statuses={upstream_statuses}",
            flush=True,
        )
        final_received_at = time.perf_counter()
    finally:
        if server is not None:
            markers = _resip_dum.stop_and_join(server)
            print(f"DUM_MARKERS markers={markers!r}", flush=True)
        upstream_peer.close()
        downstream_peer.close()

    if markers is None:
        raise AssertionError("DUM server did not return completion markers")
    if len(callback_observations) != 1:
        raise AssertionError(f"expected one Python callback, got {callback_observations!r}")
    observation = callback_observations[0]
    if observation["call_id"] != call_id:
        raise AssertionError(f"callback received the wrong Call-ID: {observation!r}")
    if observation["calling_number"] != "+15551230001":
        raise AssertionError(f"callback received the wrong calling number: {observation!r}")
    if observation["called_number"] != "+15558675309":
        raise AssertionError(f"callback received the wrong called number: {observation!r}")
    if observation["action"] != DecisionAction.FORWARD.value:
        raise AssertionError(f"callback decision was not FORWARD: {observation!r}")
    if observation["target"] != route_uri:
        raise AssertionError(f"callback returned the wrong route: {observation!r}")
    if markers["callback_ran"] is not True:
        raise AssertionError(f"native callback marker missing: {markers!r}")
    if markers["outbound_invite_sent"] is not True:
        raise AssertionError(f"outbound DUM INVITE marker missing: {markers!r}")
    if markers["failure_mapped"] is not True:
        raise AssertionError(f"DUM failure was not mapped: {markers!r}")
    if markers["upstream_reject_sent"] is not True:
        raise AssertionError(f"DUM did not reject the inbound leg: {markers!r}")
    if markers["outbound_final_status"] != 486 or markers["upstream_status"] != 486:
        raise AssertionError(f"unexpected native failure mapping: {markers!r}")
    if markers["incoming_call_id"] != call_id:
        raise AssertionError(f"native inbound Call-ID mismatch: {markers!r}")
    if markers["outgoing_call_id"] != outgoing_call_id:
        raise AssertionError(f"native outbound Call-ID mismatch: {markers!r}")
    if markers["route_uri"] != route_uri:
        raise AssertionError(f"native route URI mismatch: {markers!r}")
    if markers["event_loop_thread_id"] != markers["callback_thread_id"]:
        raise AssertionError(f"Python callback crossed threads unexpectedly: {markers!r}")
    if markers["callback_error"] or markers["worker_error"]:
        raise AssertionError(f"native callback/worker reported an error: {markers!r}")

    total_elapsed_ms = (final_received_at - started_at) * 1000
    print(
        "TIMING "
        f"start_to_server_ready_ms={(started_server_at - started_at) * 1000:.3f} "
        f"callback_decide_ms={float(observation['elapsed_ms']):.3f} "
        f"start_to_upstream_486_ms={total_elapsed_ms:.3f}",
        flush=True,
    )
    print(
        "INTEGRATION_PASS "
        f"uas_port={server_port} upstream_port={caller_port} "
        f"downstream_port={downstream_port} upstream_status=486 "
        f"incoming_call_id={call_id} outgoing_call_id={outgoing_call_id} "
        f"target_uri={actual_target_uri}",
        flush=True,
    )


if __name__ == "__main__":
    run_case()