"""UDP peer helpers for two-leg native integration tests."""

from __future__ import annotations

import re
import socket
import uuid


def parse_sip_message(message: bytes) -> tuple[str, dict[str, list[str]]]:
    header_block = message.split(b"\r\n\r\n", 1)[0]
    lines = header_block.decode("latin-1").split("\r\n")
    if not lines or not lines[0]:
        msg = "empty SIP start line"
        raise AssertionError(msg)

    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if not separator:
            msg = f"malformed SIP header line: {line!r}"
            raise AssertionError(msg)
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
        msg = f"missing header {name}"
        raise AssertionError(msg)
    return values[0]


def bind_udp(role: str) -> socket.socket:
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind(("127.0.0.1", 0))
    return peer


def reserve_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


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


def make_busy_response(request: bytes) -> bytes:
    _, headers = parse_sip_message(request)
    vias = header_values(headers, "via")
    from_value = required_header(headers, "from")
    to_value = required_header(headers, "to")
    call_id = required_header(headers, "call-id")
    cseq = required_header(headers, "cseq")
    if not vias:
        raise AssertionError("outbound INVITE is missing Via")
    if not re.search(r"(?:^|;)\s*tag\s*=", to_value, flags=re.IGNORECASE):
        to_value = f"{to_value};tag=two-leg-peer"

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


def make_non2xx_ack(request: bytes, response: bytes) -> bytes:
    request_line, request_headers = parse_sip_message(request)
    response_line, response_headers = parse_sip_message(response)
    request_fields = request_line.split()
    sequence = required_header(request_headers, "cseq").split()[0]
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
