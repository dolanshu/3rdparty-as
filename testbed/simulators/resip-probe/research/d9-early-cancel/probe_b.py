from __future__ import annotations

import os
import re
import socket
import time
from pathlib import Path

import _resip_dum_sdp_roundtrip
from probe_a import (
    Action,
    DecisionAction,
    DecisionRequest,
    FIXTURE_DIR,
    INPUT_DIR,
    Rule,
    RuleSet,
    WIRE_DIR,
    adapt_inbound_invite,
    assert_content_length,
    bind_peer_socket,
    has_tag,
    header_values,
    parse_sip_message,
    preflight_ports,
    required_header,
    save_artifact,
    sha256,
    decide,
)


def configured_port(environment_name: str) -> int:
    value = os.environ.get(environment_name)
    if value is None:
        raise ValueError(f"{environment_name} must be explicitly selected")
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError(f"{environment_name} must be between 1 and 65535")
    return port


def configured_timeout_seconds() -> float:
    value = float(os.environ.get("CANCEL_SOCKET_TIMEOUT_SECONDS", "8"))
    if not 0.1 <= value <= 30:
        raise ValueError("CANCEL_SOCKET_TIMEOUT_SECONDS must be in [0.1, 30]")
    return value


def configured_dum_timeout_ms() -> int:
    value = int(os.environ.get("CANCEL_DUM_TIMEOUT_MS", "5000"))
    if not 100 <= value <= 30000:
        raise ValueError("CANCEL_DUM_TIMEOUT_MS must be in [100, 30000]")
    return value


def branch_value(via: str) -> str:
    match = re.search(r"(?:^|;)\s*branch\s*=\s*([^;]+)", via, re.IGNORECASE)
    if match is None:
        raise AssertionError(f"Via has no branch parameter: {via!r}")
    return match.group(1).strip()


def status_code(start_line: str) -> int:
    fields = start_line.split()
    if len(fields) < 2 or fields[0] != "SIP/2.0" or not fields[1].isdigit():
        raise AssertionError(f"invalid SIP response start line: {start_line!r}")
    return int(fields[1])


def request_fields(message: bytes) -> tuple[list[str], dict[str, list[str]]]:
    start_line, headers, _ = parse_sip_message(message)
    fields = start_line.split()
    if len(fields) != 3 or fields[2] != "SIP/2.0":
        raise AssertionError(f"invalid SIP request start line: {start_line!r}")
    return fields, headers


def build_response(
    request: bytes,
    status: int,
    phrase: str,
    to_value: str | None = None,
    contact: str | None = None,
) -> bytes:
    _, headers, _ = assert_content_length(request, "response source request")
    vias = header_values(headers, "via")
    if not vias:
        raise AssertionError("response source request is missing Via")
    response_lines = [f"SIP/2.0 {status} {phrase}"]
    response_lines.extend(f"Via: {via}" for via in vias)
    response_lines.extend(
        (
            f"From: {required_header(headers, 'from')}",
            f"To: {to_value or required_header(headers, 'to')}",
            f"Call-ID: {required_header(headers, 'call-id')}",
            f"CSeq: {required_header(headers, 'cseq')}",
        )
    )
    if contact is not None:
        response_lines.append(f"Contact: {contact}")
    response_lines.extend(("Content-Length: 0", "", ""))
    return "\r\n".join(response_lines).encode("latin-1")


def assert_response_correlated(
    response: bytes,
    request: bytes,
    expected_status: int,
    expected_method: str,
    expected_to: str | None = None,
    require_to_tag: bool = False,
) -> None:
    response_line, response_headers, response_body = assert_content_length(
        response, f"SIP {expected_status} response"
    )
    _, request_headers, _ = assert_content_length(request, "correlated request")
    if status_code(response_line) != expected_status:
        raise AssertionError(
            f"expected SIP {expected_status}, got response {response_line!r}"
        )
    response_vias = header_values(response_headers, "via")
    request_vias = header_values(request_headers, "via")
    if not response_vias or not request_vias:
        raise AssertionError("transaction-correlated message is missing Via")
    if branch_value(response_vias[0]) != branch_value(request_vias[0]):
        raise AssertionError("response Via branch does not match its request")
    for name in ("from", "call-id"):
        if header_values(response_headers, name) != header_values(request_headers, name):
            raise AssertionError(f"response {name} does not match its request")
    request_sequence = required_header(request_headers, "cseq").split()[0]
    if required_header(response_headers, "cseq").upper() != (
        f"{request_sequence} {expected_method}"
    ).upper():
        raise AssertionError("response CSeq method/number does not match its request")
    request_to = expected_to or required_header(request_headers, "to")
    response_to = required_header(response_headers, "to")
    if not response_to.startswith(request_to):
        raise AssertionError("response To does not match its request")
    if require_to_tag and not has_tag(response_to):
        raise AssertionError("response To is missing its dialog tag")
    if response_body:
        raise AssertionError("unexpected body in cancellation response")


def make_downstream_provisional(invite: bytes, status: int, downstream_port: int) -> bytes:
    _, headers, _ = assert_content_length(invite, "outbound DUM INVITE")
    to_value = required_header(headers, "to")
    if status == 180 and not has_tag(to_value):
        to_value += ";tag=probe-b-early"
    contact = None
    if status == 180:
        contact = f"<sip:+8613800138000@127.0.0.1:{downstream_port}>"
    phrase = {100: "Trying", 180: "Ringing"}[status]
    response = build_response(invite, status, phrase, to_value, contact)
    assert_response_correlated(
        response,
        invite,
        status,
        "INVITE",
        expected_to=to_value,
        require_to_tag=status == 180,
    )
    return response


def make_upstream_cancel(invite: bytes) -> bytes:
    fields, headers = request_fields(invite)
    lines = [f"CANCEL {fields[1]} SIP/2.0"]
    lines.extend(f"Via: {via}" for via in header_values(headers, "via"))
    if "max-forwards" in headers:
        lines.append(f"Max-Forwards: {required_header(headers, 'max-forwards')}")
    lines.extend(f"Route: {route}" for route in headers.get("route", []))
    lines.extend(
        (
            f"From: {required_header(headers, 'from')}",
            f"To: {required_header(headers, 'to')}",
            f"Call-ID: {required_header(headers, 'call-id')}",
            f"CSeq: {required_header(headers, 'cseq').split()[0]} CANCEL",
            "Content-Length: 0",
            "",
            "",
        )
    )
    cancel = "\r\n".join(lines).encode("latin-1")
    cancel_line, cancel_headers, cancel_body = assert_content_length(
        cancel, "upstream caller CANCEL"
    )
    if cancel_line != f"CANCEL {fields[1]} SIP/2.0" or cancel_body:
        raise AssertionError("constructed upstream CANCEL has an invalid request line/body")
    for name in ("via", "from", "to", "call-id"):
        if header_values(cancel_headers, name) != header_values(headers, name):
            raise AssertionError(f"upstream CANCEL did not preserve original {name}")
    if required_header(cancel_headers, "cseq").split()[0] != required_header(
        headers, "cseq"
    ).split()[0]:
        raise AssertionError("upstream CANCEL changed the original CSeq number")
    if required_header(cancel_headers, "cseq").split()[1].upper() != "CANCEL":
        raise AssertionError("upstream CANCEL CSeq method is not CANCEL")
    return cancel


def make_upstream_non2xx_ack(invite: bytes, response: bytes) -> bytes:
    fields, invite_headers = request_fields(invite)
    _, response_headers, _ = assert_content_length(response, "upstream INVITE 487")
    lines = [f"ACK {fields[1]} SIP/2.0"]
    lines.extend(f"Via: {via}" for via in header_values(invite_headers, "via"))
    if "max-forwards" in invite_headers:
        lines.append(
            f"Max-Forwards: {required_header(invite_headers, 'max-forwards')}"
        )
    lines.extend(f"Route: {route}" for route in invite_headers.get("route", []))
    lines.extend(
        (
            f"From: {required_header(invite_headers, 'from')}",
            f"To: {required_header(response_headers, 'to')}",
            f"Call-ID: {required_header(invite_headers, 'call-id')}",
            f"CSeq: {required_header(invite_headers, 'cseq').split()[0]} ACK",
            "Content-Length: 0",
            "",
            "",
        )
    )
    ack = "\r\n".join(lines).encode("latin-1")
    ack_line, ack_headers, ack_body = assert_content_length(
        ack, "upstream caller non-2xx ACK"
    )
    if ack_line != f"ACK {fields[1]} SIP/2.0" or ack_body:
        raise AssertionError("upstream non-2xx ACK has an invalid request line/body")
    if header_values(ack_headers, "via") != header_values(invite_headers, "via"):
        raise AssertionError("upstream non-2xx ACK did not preserve the INVITE Via branch")
    if required_header(ack_headers, "to") != required_header(response_headers, "to"):
        raise AssertionError("upstream non-2xx ACK To does not match the 487")
    if required_header(ack_headers, "cseq").split()[1].upper() != "ACK":
        raise AssertionError("upstream non-2xx ACK CSeq method is not ACK")
    return ack


def assert_downstream_cancel(invite: bytes, cancel: bytes) -> None:
    invite_fields, invite_headers = request_fields(invite)
    cancel_line, cancel_headers, cancel_body = assert_content_length(
        cancel, "DUM downstream CANCEL"
    )
    if cancel_line != f"CANCEL {invite_fields[1]} SIP/2.0":
        raise AssertionError(f"DUM CANCEL does not target the INVITE URI: {cancel_line!r}")
    for name in ("via", "from", "to", "call-id"):
        if header_values(cancel_headers, name) != header_values(invite_headers, name):
            raise AssertionError(f"DUM CANCEL {name} does not match its outbound INVITE")
    invite_sequence = required_header(invite_headers, "cseq").split()[0]
    if required_header(cancel_headers, "cseq").upper() != f"{invite_sequence} CANCEL":
        raise AssertionError("DUM CANCEL CSeq does not match the outbound INVITE")
    if cancel_body:
        raise AssertionError("DUM CANCEL unexpectedly has a body")


def make_downstream_cancel_ok(cancel: bytes) -> bytes:
    return build_response(cancel, 200, "OK")


def make_downstream_invite_487(invite: bytes) -> bytes:
    _, headers, _ = assert_content_length(invite, "outbound DUM INVITE")
    to_value = required_header(headers, "to")
    if not has_tag(to_value):
        to_value += ";tag=probe-b-final"
    response = build_response(invite, 487, "Request Terminated", to_value)
    assert_response_correlated(
        response, invite, 487, "INVITE", expected_to=to_value, require_to_tag=True
    )
    return response


def assert_downstream_non2xx_ack(invite: bytes, response: bytes, ack: bytes) -> None:
    invite_fields, invite_headers = request_fields(invite)
    _, response_headers, _ = assert_content_length(response, "downstream INVITE 487")
    ack_line, ack_headers, ack_body = assert_content_length(
        ack, "DUM downstream non-2xx ACK"
    )
    if ack_line != f"ACK {invite_fields[1]} SIP/2.0" or ack_body:
        raise AssertionError(f"expected transaction ACK, got {ack_line!r}")
    ack_vias = header_values(ack_headers, "via")
    invite_vias = header_values(invite_headers, "via")
    if not ack_vias or branch_value(ack_vias[0]) != branch_value(invite_vias[0]):
        raise AssertionError("DUM non-2xx ACK does not reuse the INVITE transaction branch")
    for name in ("from", "call-id"):
        if header_values(ack_headers, name) != header_values(invite_headers, name):
            raise AssertionError(f"DUM non-2xx ACK {name} does not match the INVITE")
    if required_header(ack_headers, "to") != required_header(response_headers, "to"):
        raise AssertionError("DUM non-2xx ACK To does not match the downstream 487")
    invite_sequence = required_header(invite_headers, "cseq").split()[0]
    if required_header(ack_headers, "cseq").upper() != f"{invite_sequence} ACK":
        raise AssertionError("DUM non-2xx ACK CSeq does not match the INVITE")


def receive_datagram(
    peer: socket.socket,
    artifact_prefix: str,
    index: int,
    deadline: float,
    expected_address: tuple[str, int],
) -> tuple[bytes, tuple[str, int], str, dict[str, list[str]]]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"timed out waiting for {artifact_prefix} datagram")
    peer.settimeout(remaining)
    message, address = peer.recvfrom(65535)
    start_line, headers, _ = assert_content_length(
        message, f"{artifact_prefix}-{index:02d}"
    )
    save_artifact(WIRE_DIR, f"{artifact_prefix}-{index:02d}.sip", message)
    print(
        f"DATAGRAM label={artifact_prefix} start_line={start_line!r} "
        f"from={address[0]}:{address[1]} bytes={len(message)}",
        flush=True,
    )
    if address != expected_address:
        raise AssertionError(
            f"{artifact_prefix} came from {address}, expected {expected_address}"
        )
    return message, address, start_line, headers


def send_peer_datagram(
    peer: socket.socket,
    message: bytes,
    destination: tuple[str, int],
    artifact_name: str,
    label: str,
) -> None:
    save_artifact(WIRE_DIR, artifact_name, message)
    sent = peer.sendto(message, destination)
    if sent != len(message):
        raise AssertionError(f"{label} sent {sent} of {len(message)} bytes")
    print(
        f"PEER_SENT label={label} to={destination[0]}:{destination[1]} "
        f"bytes={sent}",
        flush=True,
    )


def assert_upstream_response(response: bytes, invite: bytes, expected_status: int) -> None:
    request_line, request_headers, _ = assert_content_length(invite, "upstream INVITE")
    _, response_headers, _ = assert_content_length(response, "upstream DUM response")
    line, _, _ = assert_content_length(response, "upstream DUM response")
    if status_code(line) != expected_status:
        raise AssertionError(f"expected upstream {expected_status}, got {line!r}")
    if branch_value(header_values(response_headers, "via")[0]) != branch_value(
        header_values(request_headers, "via")[0]
    ):
        raise AssertionError("upstream response Via branch does not match INVITE")
    for name in ("from", "call-id"):
        if header_values(response_headers, name) != header_values(request_headers, name):
            raise AssertionError(f"upstream response {name} does not match INVITE")
    sequence = required_header(request_headers, "cseq").split()[0]
    if required_header(response_headers, "cseq").upper() != f"{sequence} INVITE":
        raise AssertionError("upstream response CSeq does not match INVITE")
    response_to = required_header(response_headers, "to")
    if not response_to.startswith(required_header(request_headers, "to")):
        raise AssertionError("upstream response To does not match INVITE")
    if expected_status == 180 and not has_tag(response_to):
        raise AssertionError("upstream 180 is missing its early-dialog tag")


def run_case() -> None:
    started_at = time.perf_counter()
    timeout_seconds = configured_timeout_seconds()
    dum_timeout_ms = configured_dum_timeout_ms()
    ports = {
        "dum_uas": configured_port("CANCEL_UAS_PORT"),
        "upstream_peer": configured_port("CANCEL_UPSTREAM_PORT"),
        "downstream_peer": configured_port("CANCEL_DOWNSTREAM_PORT"),
    }
    if len(set(ports.values())) != len(ports):
        raise AssertionError("Probe B UAS, upstream, and downstream ports must differ")
    print(
        f"CONFIG ports={ports!r} socket_timeout_seconds={timeout_seconds} "
        f"dum_timeout_ms={dum_timeout_ms}",
        flush=True,
    )
    preflight_ports(ports)

    source_invite = (FIXTURE_DIR / "01-in-invite-trunk.txt").read_bytes()
    source_line, source_headers, source_offer = assert_content_length(
        source_invite, "S1 inbound INVITE source"
    )
    if not source_line.startswith("INVITE "):
        raise AssertionError("S1 source fixture is not an INVITE")
    if required_header(source_headers, "content-type").split(";", 1)[0].lower() != (
        "application/sdp"
    ):
        raise AssertionError("S1 inbound INVITE fixture does not contain SDP")

    upstream_peer = bind_peer_socket("cancel_upstream_peer", ports["upstream_peer"])
    downstream_peer = bind_peer_socket(
        "cancel_downstream_peer", ports["downstream_peer"]
    )
    server = None
    markers: dict[str, object] | None = None
    callback_observations: list[dict[str, object]] = []
    incoming_call_id = ""
    outgoing_call_id = ""
    route_uri = (
        f"sip:+8613800138000@127.0.0.1:{ports['downstream_peer']};transport=udp"
    )
    route_rules = RuleSet(
        rules=(
            Rule(
                rule_id="s1-cancel-forward",
                prefix="+8613800138000",
                action=Action.FORWARD,
                target=route_uri,
            ),
        )
    )

    def python_route_callback(
        received_call_id: str, calling_number: str, called_number: str
    ) -> str:
        decision = decide(
            DecisionRequest(
                call_id=received_call_id,
                calling_number=calling_number,
                called_number=called_number,
                received_at=0.0,
            ),
            route_rules,
        )
        observation = {
            "call_id": received_call_id,
            "calling_number": calling_number,
            "called_number": called_number,
            "action": decision.action.value,
            "target": decision.target,
            "matched_rule_id": decision.matched_rule_id,
        }
        callback_observations.append(observation)
        print(f"PYTHON_POLICY_DECISION observation={observation!r}", flush=True)
        if decision.action is not DecisionAction.FORWARD or decision.target != route_uri:
            raise AssertionError(f"unexpected Python route decision: {observation!r}")
        return decision.target

    try:
        server = _resip_dum_sdp_roundtrip.start_uas(
            ports["dum_uas"], ports["downstream_peer"], python_route_callback, True
        )
        inbound_invite = adapt_inbound_invite(
            source_invite, ports["dum_uas"], ports["upstream_peer"]
        )
        _, inbound_headers, inbound_offer = assert_content_length(
            inbound_invite, "upstream caller INVITE"
        )
        incoming_call_id = required_header(inbound_headers, "call-id")
        inbound_path = save_artifact(
            INPUT_DIR, "probe-b-upstream-invite.sip", inbound_invite
        )
        save_artifact(WIRE_DIR, "probe-b-upstream-inbound-invite.sip", inbound_invite)
        print(
            f"SOURCE_INPUT path={inbound_path} offer_bytes={len(inbound_offer)} "
            f"offer_sha256={sha256(inbound_offer)}",
            flush=True,
        )
        send_peer_datagram(
            upstream_peer,
            inbound_invite,
            ("127.0.0.1", ports["dum_uas"]),
            "probe-b-upstream-invite-sent.sip",
            "upstream INVITE",
        )

        response_index = 0
        upstream_deadline = time.monotonic() + timeout_seconds
        upstream_100, _, start_line, _ = receive_datagram(
            upstream_peer,
            "probe-b-upstream-provisional",
            response_index,
            upstream_deadline,
            ("127.0.0.1", ports["dum_uas"]),
        )
        response_index += 1
        if status_code(start_line) != 100:
            raise AssertionError(f"expected initial upstream 100, got {start_line!r}")
        assert_upstream_response(upstream_100, inbound_invite, 100)

        outbound_invite, dum_address, outbound_line, outbound_headers = receive_datagram(
            downstream_peer,
            "probe-b-downstream-outbound-invite",
            0,
            time.monotonic() + timeout_seconds,
            ("127.0.0.1", ports["dum_uas"]),
        )
        outbound_fields = outbound_line.split()
        if len(outbound_fields) != 3 or outbound_fields[0] != "INVITE":
            raise AssertionError(
                f"expected DUM outbound INVITE, got {outbound_line!r}"
            )
        if outbound_fields[1] != route_uri:
            raise AssertionError(
                f"outbound target {outbound_fields[1]!r} != {route_uri!r}"
            )
        _, _, outbound_offer = assert_content_length(
            outbound_invite, "downstream DUM INVITE"
        )
        if inbound_offer != outbound_offer:
            raise AssertionError("DUM changed the S1 offer on the downstream leg")
        outgoing_call_id = required_header(outbound_headers, "call-id")
        if outgoing_call_id == incoming_call_id:
            raise AssertionError("inbound and outbound Call-IDs unexpectedly match")

        downstream_100 = make_downstream_provisional(
            outbound_invite, 100, ports["downstream_peer"]
        )
        send_peer_datagram(
            downstream_peer,
            downstream_100,
            dum_address,
            "probe-b-downstream-peer-100.sip",
            "downstream 100 Trying",
        )
        downstream_180 = make_downstream_provisional(
            outbound_invite, 180, ports["downstream_peer"]
        )
        send_peer_datagram(
            downstream_peer,
            downstream_180,
            dum_address,
            "probe-b-downstream-peer-180.sip",
            "downstream 180 Ringing",
        )

        downstream_180_processed = _resip_dum_sdp_roundtrip.wait_for_downstream_180(
            server, dum_timeout_ms
        )
        print(
            f"DUM_DOWNSTREAM_180_PROCESSED received={downstream_180_processed} "
            f"timeout_ms={dum_timeout_ms}",
            flush=True,
        )
        if not downstream_180_processed:
            raise TimeoutError("DUM did not process downstream 180 in time")

        upstream_180 = None
        while upstream_180 is None:
            upstream_message, _, start_line, _ = receive_datagram(
                upstream_peer,
                "probe-b-upstream-provisional",
                response_index,
                time.monotonic() + timeout_seconds,
                ("127.0.0.1", ports["dum_uas"]),
            )
            response_index += 1
            status = status_code(start_line)
            if status == 100:
                assert_upstream_response(upstream_message, inbound_invite, 100)
                continue
            if status != 180:
                raise AssertionError(
                    f"unexpected upstream provisional before CANCEL: {start_line!r}"
                )
            assert_upstream_response(upstream_message, inbound_invite, 180)
            upstream_180 = upstream_message

        upstream_cancel = make_upstream_cancel(inbound_invite)
        _, cancel_headers, _ = assert_content_length(
            upstream_cancel, "upstream caller CANCEL"
        )
        if branch_value(header_values(cancel_headers, "via")[0]) != branch_value(
            header_values(inbound_headers, "via")[0]
        ):
            raise AssertionError("upstream CANCEL changed the original Via branch")
        send_peer_datagram(
            upstream_peer,
            upstream_cancel,
            ("127.0.0.1", ports["dum_uas"]),
            "probe-b-upstream-cancel.sip",
            "upstream CANCEL",
        )

        upstream_cancel_200 = None
        upstream_invite_487 = None
        while upstream_cancel_200 is None or upstream_invite_487 is None:
            response, _, start_line, response_headers = receive_datagram(
                upstream_peer,
                "probe-b-upstream-cancel-result",
                response_index,
                time.monotonic() + timeout_seconds,
                ("127.0.0.1", ports["dum_uas"]),
            )
            response_index += 1
            status = status_code(start_line)
            response_cseq = required_header(response_headers, "cseq").split()
            if status == 200 and len(response_cseq) == 2 and response_cseq[1].upper() == "CANCEL":
                assert_response_correlated(response, upstream_cancel, 200, "CANCEL")
                upstream_cancel_200 = response
            elif status == 487 and len(response_cseq) == 2 and response_cseq[1].upper() == "INVITE":
                assert_response_correlated(
                    response,
                    inbound_invite,
                    487,
                    "INVITE",
                    require_to_tag=True,
                )
                upstream_invite_487 = response
            else:
                raise AssertionError(
                    f"unexpected upstream response after CANCEL: {start_line!r}"
                )

        upstream_ack = make_upstream_non2xx_ack(inbound_invite, upstream_invite_487)
        send_peer_datagram(
            upstream_peer,
            upstream_ack,
            ("127.0.0.1", ports["dum_uas"]),
            "probe-b-upstream-non2xx-ack.sip",
            "upstream ACK to 487",
        )

        downstream_followup_index = 0
        downstream_deadline = time.monotonic() + timeout_seconds
        while True:
            dum_cancel, dum_address, dum_line, _ = receive_datagram(
                downstream_peer,
                "probe-b-downstream-followup",
                downstream_followup_index,
                downstream_deadline,
                ("127.0.0.1", ports["dum_uas"]),
            )
            downstream_followup_index += 1
            if dum_line.startswith("BYE "):
                raise AssertionError(
                    "FAIL: cancellation failed; DUM emitted BYE instead of CANCEL"
                )
            if dum_line.startswith("CANCEL "):
                assert_downstream_cancel(outbound_invite, dum_cancel)
                break
            raise AssertionError(
                f"FAIL: cancellation failed; expected DUM CANCEL, got {dum_line!r}"
            )

        downstream_cancel_200 = make_downstream_cancel_ok(dum_cancel)
        assert_response_correlated(
            downstream_cancel_200, dum_cancel, 200, "CANCEL"
        )
        send_peer_datagram(
            downstream_peer,
            downstream_cancel_200,
            dum_address,
            "probe-b-downstream-peer-200-cancel.sip",
            "downstream 200 to DUM CANCEL",
        )
        downstream_invite_487 = make_downstream_invite_487(outbound_invite)
        send_peer_datagram(
            downstream_peer,
            downstream_invite_487,
            dum_address,
            "probe-b-downstream-peer-487-invite.sip",
            "downstream 487 to DUM INVITE",
        )

        downstream_ack = None
        while downstream_ack is None:
            message, address, start_line, _ = receive_datagram(
                downstream_peer,
                "probe-b-downstream-followup",
                downstream_followup_index,
                time.monotonic() + timeout_seconds,
                ("127.0.0.1", ports["dum_uas"]),
            )
            downstream_followup_index += 1
            if start_line.startswith("BYE "):
                raise AssertionError(
                    "FAIL: cancellation failed; DUM emitted BYE instead of non-2xx ACK"
                )
            if start_line.startswith("ACK "):
                assert_downstream_non2xx_ack(
                    outbound_invite, downstream_invite_487, message
                )
                downstream_ack = message
            elif start_line == parse_sip_message(dum_cancel)[0]:
                repeat_ok = make_downstream_cancel_ok(dum_cancel)
                send_peer_datagram(
                    downstream_peer,
                    repeat_ok,
                    address,
                    f"probe-b-downstream-peer-200-cancel-retrans-{downstream_followup_index:02d}.sip",
                    "retransmitted downstream 200 to DUM CANCEL",
                )
            elif start_line == parse_sip_message(outbound_invite)[0]:
                repeat_487 = make_downstream_invite_487(outbound_invite)
                send_peer_datagram(
                    downstream_peer,
                    repeat_487,
                    address,
                    f"probe-b-downstream-peer-487-invite-retrans-{downstream_followup_index:02d}.sip",
                    "retransmitted downstream 487 to DUM INVITE",
                )
            else:
                raise AssertionError(
                    f"unexpected DUM downstream follow-up: {start_line!r}"
                )

        cancel_completed = _resip_dum_sdp_roundtrip.wait_for_cancel_completion(
            server, dum_timeout_ms
        )
        print(
            f"DUM_CANCEL_CALLBACKS_COMPLETED received={cancel_completed} "
            f"timeout_ms={dum_timeout_ms}",
            flush=True,
        )
        if not cancel_completed:
            raise TimeoutError("DUM terminal cancellation callbacks timed out")
    finally:
        if server is not None:
            markers = _resip_dum_sdp_roundtrip.stop_and_join(server)
            print(f"DUM_MARKERS markers={markers!r}", flush=True)
        upstream_peer.close()
        downstream_peer.close()

    if markers is None:
        raise AssertionError("DUM server did not return completion markers")
    if len(callback_observations) != 1:
        raise AssertionError(f"expected one Python route callback, got {callback_observations!r}")
    observation = callback_observations[0]
    if observation["call_id"] != incoming_call_id:
        raise AssertionError(f"Python callback Call-ID mismatch: {observation!r}")
    if observation["calling_number"] != "+86216180001":
        raise AssertionError(f"Python callback caller mismatch: {observation!r}")
    if observation["called_number"] != "+8613800138000":
        raise AssertionError(f"Python callback callee mismatch: {observation!r}")
    if observation["action"] != DecisionAction.FORWARD.value:
        raise AssertionError(f"Python callback did not forward: {observation!r}")
    if observation["target"] != route_uri:
        raise AssertionError(f"Python callback route mismatch: {observation!r}")
    expected_markers = (
        "callback_ran",
        "outbound_invite_sent",
        "cancel_probe",
        "downstream_180_received",
        "upstream_remote_cancel_received",
        "outbound_cancel_requested",
        "downstream_local_cancel_terminated",
    )
    for marker in expected_markers:
        if markers[marker] is not True:
            raise AssertionError(f"DUM marker {marker} was not true: {markers!r}")
    if markers["upstream_status"] != 487 or markers["downstream_final_status"] != 487:
        raise AssertionError(f"DUM did not terminate both INVITE legs with 487: {markers!r}")
    if markers["incoming_call_id"] != incoming_call_id:
        raise AssertionError(f"DUM inbound Call-ID mismatch: {markers!r}")
    if markers["outgoing_call_id"] != outgoing_call_id:
        raise AssertionError(f"DUM outbound Call-ID mismatch: {markers!r}")
    if markers["route_uri"] != route_uri:
        raise AssertionError(f"DUM route URI mismatch: {markers!r}")
    if markers["event_loop_thread_id"] != markers["callback_thread_id"]:
        raise AssertionError(f"Python callback thread mismatch: {markers!r}")
    if markers["callback_error"] or markers["worker_error"]:
        raise AssertionError(f"DUM callback/worker reported an error: {markers!r}")

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    print(
        "PROBE_B_PASS "
        f"uas_port={ports['dum_uas']} upstream_port={ports['upstream_peer']} "
        f"downstream_port={ports['downstream_peer']} upstream_status=487 "
        f"downstream_status=487 remote_cancel=True outbound_cancel=True "
        f"downstream_non2xx_ack=True incoming_call_id={incoming_call_id} "
        f"outgoing_call_id={outgoing_call_id} elapsed_ms={elapsed_ms:.3f}",
        flush=True,
    )


if __name__ == "__main__":
    run_case()