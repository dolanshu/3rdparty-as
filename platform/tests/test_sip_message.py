"""Unit tests for the SIP message parser and builder of the kernel boundary.

Acceptance: RFC 3261 §7 (message syntax), §7.3.1 (header field names compare
case-insensitively), §8.1.1 (mandatory request header fields), §8.1.1.7 (the
``Via`` branch parameter and its ``z9hG4bK`` magic cookie) and REQ-F-4 (the SDP
body crosses the boundary byte for byte). Purity is asserted too: parsing and
building are functions of their arguments, with no clock and no socket
(ADR-0002).
"""

from __future__ import annotations

import random
import socket
import time
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Final

import pytest

from as_platform.sip.message import (
    SipMessage,
    build_request,
    build_response,
    call_id,
    header,
    headers_all,
    is_request,
    parse_message,
    request_uri,
    status_code,
)

pytestmark = pytest.mark.unit

CRLF: Final = b"\r\n"
LF: Final = b"\n"
CR: Final = b"\r"

METHOD: Final = "INVITE"
REQUEST_URI: Final = "sip:+8613800138000@127.0.0.1:45363"
CALL_ID: Final = "48f64baa94fdfcfdd79af4128905d375"
BRANCH_1: Final = "z9hG4bK-poc-branch-0001"
BRANCH_2: Final = "z9hG4bK-poc-branch-0002"
STATUS: Final = 200
REASON: Final = "OK"

# The SDP of the S1 baseline, byte for byte. REQ-F-4: it must cross the
# boundary unchanged, so the assertions compare against these exact bytes.
SDP: Final = (
    b"v=0\r\n"
    b"o=- 4101 4101 IN IP4 192.0.2.10\r\n"
    b"s=3rd-party AS POC call\r\n"
    b"c=IN IP4 192.0.2.10\r\n"
    b"t=0 0\r\n"
    b"m=audio 40000 RTP/AVP 0 8 101\r\n"
    b"a=rtpmap:0 PCMU/8000\r\n"
    b"a=rtpmap:101 telephone-event/8000\r\n"
    b"a=sendrecv\r\n"
)

# RFC 3261 §8.1.1: the six header fields every request must carry.
REQUIRED: Final = ("To", "From", "CSeq", "Call-ID", "Max-Forwards", "Via")

VIA_1: Final = f"SIP/2.0/UDP 127.0.0.1:47199;rport;branch={BRANCH_1}"
VIA_2: Final = f"SIP/2.0/UDP 127.0.0.1:45363;branch={BRANCH_2}"
ROUTE_1: Final = "<sip:127.0.0.1:47288;lr>"
ROUTE_2: Final = "<sip:127.0.0.1:45363;lr>"

BASELINE_SCENARIO: Final = "S1-basic-call"
BASELINE_INVITE: Final = "01-in-invite-trunk.txt"


def _invite_headers() -> tuple[tuple[str, str], ...]:
    """The header section of an INVITE, in wire order, without Content-Length."""
    return (
        ("Via", VIA_1),
        ("Max-Forwards", "70"),
        ("From", "<sip:+86216180001@127.0.0.1>;tag=b609018f3db67e29442268935be4c876"),
        ("To", "<sip:+8613800138000@127.0.0.1>"),
        ("Call-ID", CALL_ID),
        ("CSeq", "1319846983 INVITE"),
        ("Contact", "<sip:+86216180001@127.0.0.1:47199>"),
        ("Content-Type", "application/sdp"),
    )


def _assemble(
    start_line: str, headers: tuple[tuple[str, str], ...], body: bytes, eol: bytes
) -> bytes:
    """Render one message by hand, so the parser is never checked against itself."""
    lines = [start_line.encode()] + [f"{name}: {value}".encode() for name, value in headers]
    return eol.join(lines) + eol + eol + body


def _request_line() -> str:
    """The request line of the INVITE under test (RFC 3261 §7.1)."""
    return f"{METHOD} {REQUEST_URI} SIP/2.0"


def _status_line() -> str:
    """The status line of the 200 OK under test (RFC 3261 §7.2)."""
    return f"SIP/2.0 {STATUS} {REASON}"


def test_parse_crlf_message_keeps_start_line_headers_and_body() -> None:
    """A CRLF request parses into its start line, its headers and its body."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))

    assert parsed.start_line == _request_line()
    assert parsed.headers == _invite_headers()
    assert parsed.body == SDP


def test_parse_keeps_the_body_byte_for_byte() -> None:
    """REQ-F-4: the SDP is passed through untouched, not re-encoded or stripped."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))

    assert parsed.body is not SDP
    assert parsed.body == SDP
    assert parsed.body.endswith(b"a=sendrecv\r\n")


def test_parse_lf_only_message() -> None:
    """LF-only line breaks parse the same way; the body still keeps its bytes."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, LF))

    assert parsed.start_line == _request_line()
    assert parsed.headers == _invite_headers()
    assert parsed.body == SDP


def test_parse_cr_only_message() -> None:
    """CR-only line breaks parse the same way; the body still keeps its bytes."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CR))

    assert parsed.start_line == _request_line()
    assert parsed.headers == _invite_headers()
    assert parsed.body == SDP


def test_parse_splits_at_the_first_empty_line() -> None:
    """The earliest empty line ends the header section; later ones belong to the body."""
    body = b"v=0\r\n\r\na=sendrecv\r\n"
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), body, CRLF))

    assert parsed.body == body


def test_parse_message_without_body_has_an_empty_body() -> None:
    """A message with no empty line is all header section and carries no body."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), b"", CRLF).rstrip(CRLF))

    assert parsed.headers == _invite_headers()
    assert parsed.body == b""


def test_repeated_header_fields_stay_separate_and_in_order() -> None:
    """Repeated fields are never joined: wire order and multiplicity are kept."""
    headers = (
        ("Via", VIA_1),
        ("Via", VIA_2),
        ("Route", ROUTE_1),
        ("Route", ROUTE_2),
        ("To", "<sip:+8613800138000@127.0.0.1>"),
        ("From", "<sip:+86216180001@127.0.0.1>;tag=b609018f3db67e29442268935be4c876"),
        ("CSeq", "1319846983 INVITE"),
        ("Call-ID", CALL_ID),
        ("Max-Forwards", "70"),
    )
    parsed = parse_message(_assemble(_request_line(), headers, SDP, CRLF))

    assert parsed.headers == headers
    assert headers_all(parsed, "Via") == (VIA_1, VIA_2)
    assert headers_all(parsed, "Route") == (ROUTE_1, ROUTE_2)
    assert header(parsed, "Via") == VIA_1


def test_repeated_header_fields_keep_their_original_capitalisation() -> None:
    """The name is kept as the wire wrote it; only comparison is case-insensitive."""
    parsed = parse_message(_assemble(_request_line(), (("via", VIA_1), ("VIA", VIA_2)), b"", CRLF))

    assert parsed.headers == (("via", VIA_1), ("VIA", VIA_2))
    assert headers_all(parsed, "Via") == (VIA_1, VIA_2)


def test_header_lookup_is_case_insensitive() -> None:
    """RFC 3261 §7.3.1: `Call-ID`, `call-id` and `CALL-ID` name the same field."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))

    for spelling in ("Call-ID", "call-id", "CALL-ID", "Call-Id"):
        assert header(parsed, spelling) == CALL_ID
        assert headers_all(parsed, spelling) == (CALL_ID,)


def test_header_lookup_returns_none_when_the_field_is_absent() -> None:
    """An absent field yields `None` and an empty tuple, never an exception."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))

    assert header(parsed, "Record-Route") is None
    assert headers_all(parsed, "Record-Route") == ()


def test_is_request_tells_requests_from_responses() -> None:
    """A start line that begins with `SIP/` is a status line; anything else is not."""
    request = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))
    response = parse_message(_assemble(_status_line(), _invite_headers(), SDP, CRLF))

    assert is_request(request) is True
    assert is_request(response) is False


def test_request_uri_and_status_code_read_the_second_token() -> None:
    """The Request-URI of a request and the status code of a response, and nothing else."""
    request = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))
    response = parse_message(_assemble(_status_line(), _invite_headers(), SDP, CRLF))

    assert request_uri(request) == REQUEST_URI
    assert status_code(request) is None
    assert request_uri(response) is None
    assert status_code(response) == STATUS


def test_call_id_reads_the_call_id_field() -> None:
    """`call_id` is the convenience reader for the field the kernel keys on."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))

    assert call_id(parsed) == CALL_ID == header(parsed, "Call-ID")


def test_call_id_is_none_when_absent() -> None:
    """A message without a Call-ID reads as `None` rather than as empty text."""
    parsed = parse_message(_assemble(_request_line(), (("Via", VIA_1),), b"", CRLF))

    assert call_id(parsed) is None


def test_build_request_writes_crlf_and_a_correct_content_length() -> None:
    """RFC 3261 §7: CRLF line breaks, and Content-Length counts the body bytes."""
    built = build_request(METHOD, REQUEST_URI, _invite_headers(), SDP)

    assert built.startswith(_request_line().encode() + CRLF)
    assert built.endswith(SDP)
    assert built.replace(CRLF, b"").count(LF) == 0
    assert built.count(CRLF + CRLF) == 1

    parsed = parse_message(built)
    assert header(parsed, "Content-Length") == str(len(SDP))
    assert parsed.body == SDP


def test_build_request_writes_content_length_zero_for_an_empty_body() -> None:
    """A request with no body still carries `Content-Length: 0`."""
    parsed = parse_message(build_request(METHOD, REQUEST_URI, _invite_headers()))

    assert header(parsed, "Content-Length") == "0"
    assert parsed.body == b""


def test_build_request_overwrites_a_content_length_the_caller_supplied() -> None:
    """The byte count is computed here, so a caller's stale value cannot survive."""
    headers = _invite_headers() + (("Content-Length", "9999"),)

    parsed = parse_message(build_request(METHOD, REQUEST_URI, headers, SDP))

    assert header(parsed, "Content-Length") == str(len(SDP))
    assert headers_all(parsed, "Content-Length") == (str(len(SDP)),)


def test_build_request_accepts_a_mapping_of_headers() -> None:
    """A mapping is accepted as well as a sequence of pairs."""
    built = build_request(METHOD, REQUEST_URI, dict(_invite_headers()), SDP)

    assert parse_message(built).body == SDP


@pytest.mark.parametrize("missing", REQUIRED)
def test_build_request_rejects_a_request_missing_a_mandatory_field(missing: str) -> None:
    """RFC 3261 §8.1.1: every one of the six mandatory fields must be present."""
    headers = tuple(field for field in _invite_headers() if field[0].lower() != missing.lower())

    with pytest.raises(ValueError, match=missing):
        build_request(METHOD, REQUEST_URI, headers, SDP)


def test_build_request_names_every_missing_field_at_once() -> None:
    """The error says which fields are missing, so a caller fixes all of them at once."""
    headers = (("Via", VIA_1),)

    with pytest.raises(ValueError) as raised:
        build_request(METHOD, REQUEST_URI, headers, SDP)

    message = str(raised.value)
    for name in ("To", "From", "CSeq", "Call-ID", "Max-Forwards"):
        assert name in message


def test_build_request_rejects_a_via_without_a_branch() -> None:
    """RFC 3261 §8.1.1.7: a Via with no branch parameter cannot be sent."""
    headers = tuple(
        (name, "SIP/2.0/UDP 127.0.0.1:47199;rport" if name == "Via" else value)
        for name, value in _invite_headers()
    )

    with pytest.raises(ValueError, match="branch"):
        build_request(METHOD, REQUEST_URI, headers, SDP)


def test_build_request_rejects_a_branch_without_the_magic_cookie() -> None:
    """RFC 3261 §8.1.1.7: the branch must begin with `z9hG4bK`."""
    headers = tuple(
        (name, f"SIP/2.0/UDP 127.0.0.1:47199;branch={BRANCH_2[7:]}" if name == "Via" else value)
        for name, value in _invite_headers()
    )

    with pytest.raises(ValueError, match="z9hG4bK"):
        build_request(METHOD, REQUEST_URI, headers, SDP)


def test_build_request_rejects_every_via_that_lacks_a_valid_branch() -> None:
    """The rule holds for all Via fields, not only the first one."""
    headers = _invite_headers() + (("Via", "SIP/2.0/UDP 127.0.0.1:45363"),)

    with pytest.raises(ValueError, match="branch"):
        build_request(METHOD, REQUEST_URI, headers, SDP)


def test_build_response_writes_the_status_line_and_crlf() -> None:
    """RFC 3261 §7.2: the status line is `SIP-Version SP Status-Code SP Reason-Phrase`."""
    parsed = parse_message(build_response(STATUS, REASON, _invite_headers(), SDP))

    assert parsed.start_line == _status_line()
    assert is_request(parsed) is False
    assert status_code(parsed) == STATUS
    assert header(parsed, "Content-Length") == str(len(SDP))
    assert parsed.body == SDP


@pytest.mark.parametrize("code", [99, 700, 0, -1])
def test_build_response_rejects_a_status_code_outside_100_to_699(code: int) -> None:
    """RFC 3261 §7.2: the status code is three digits, 100 to 699."""
    with pytest.raises(ValueError, match=str(code)):
        build_response(code, REASON, _invite_headers(), SDP)


@pytest.mark.parametrize("code", [100, 699])
def test_build_response_accepts_the_ends_of_the_status_code_range(code: int) -> None:
    """100 and 699 are inside the range and are accepted."""
    assert status_code(parse_message(build_response(code, REASON, _invite_headers()))) == code


def test_build_request_round_trips_through_the_parser() -> None:
    """What is built is what parses back: start line, headers and body unchanged."""
    built = build_request(METHOD, REQUEST_URI, _invite_headers(), SDP)
    parsed = parse_message(built)

    assert parsed.start_line == _request_line()
    assert parsed.headers == _invite_headers() + (("Content-Length", str(len(SDP))),)
    assert parsed.body == SDP
    assert parsed.headers[: len(_invite_headers())] == _invite_headers()


def test_build_request_round_trips_repeated_header_fields() -> None:
    """Multiplicity and order survive the round trip as well."""
    headers = _invite_headers() + (("Via", VIA_2), ("Route", ROUTE_1))
    parsed = parse_message(build_request(METHOD, REQUEST_URI, headers, SDP))

    assert headers_all(parsed, "Via") == (VIA_1, VIA_2)
    assert headers_all(parsed, "Route") == (ROUTE_1,)


def test_build_response_round_trips_through_the_parser() -> None:
    """Responses round-trip the same way requests do."""
    built = build_response(STATUS, REASON, _invite_headers())
    parsed = parse_message(built)

    assert parsed.start_line == _status_line()
    assert parsed.body == b""
    assert call_id(parsed) == CALL_ID


def test_rebuilding_a_parsed_message_is_idempotent() -> None:
    """Parse, build, parse again: the second message equals the first."""
    headers = _invite_headers() + (("Content-Length", str(len(SDP))),)
    first = parse_message(_assemble(_request_line(), headers, SDP, CRLF))

    rebuilt = build_request(METHOD, REQUEST_URI, first.headers, first.body)
    second = parse_message(rebuilt)

    assert second == first
    assert rebuilt == _assemble(_request_line(), headers, SDP, CRLF)


def _repository_root() -> Path:
    """Return the workspace root, whichever directory the run started from.

    The root is the only ancestor holding both the workspace manifest and the
    ``testbed/`` tree, so the walk stops there and nowhere else.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "testbed").is_dir():
            return candidate
    return here.parents[2]


def test_the_s1_baseline_invite_parses_as_expected() -> None:
    """The captured S1 INVITE is the shape this parser has to reproduce."""
    path = (
        _repository_root()
        / "testbed"
        / "contracts"
        / "sip-baseline"
        / BASELINE_SCENARIO
        / BASELINE_INVITE
    )
    if not path.is_file():
        pytest.skip(f"baseline {BASELINE_SCENARIO} has no {BASELINE_INVITE} at {path}")

    raw = path.read_bytes()
    parsed = parse_message(raw)

    assert parsed.start_line.split()[0] == METHOD
    assert call_id(parsed) == CALL_ID
    assert parsed.body == raw.split(CRLF + CRLF, 1)[1]
    assert len(parsed.body) == int(header(parsed, "Content-Length") or "-1")
    assert b"m=audio 40000 RTP/AVP 0 8 101" in parsed.body


def _spy(name: str, calls: list[str]) -> Callable[..., object]:
    """Return a replacement that records its own name instead of doing its job."""

    def _record(*args: object, **kwargs: object) -> None:
        calls.append(name)

    return _record


def test_parsing_and_building_read_no_clock_and_open_no_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Purity: no clock, no socket and no randomness, so the output is reproducible."""
    calls: list[str] = []
    monkeypatch.setattr(time, "time", _spy("time.time", calls))
    monkeypatch.setattr(time, "monotonic", _spy("time.monotonic", calls))
    monkeypatch.setattr(random, "random", _spy("random.random", calls))
    monkeypatch.setattr(socket, "socket", _spy("socket.socket", calls))

    raw = _assemble(_request_line(), _invite_headers(), SDP, CRLF)
    parsed = parse_message(raw)
    build_request(METHOD, REQUEST_URI, parsed.headers, parsed.body)
    build_response(STATUS, REASON, parsed.headers, parsed.body)

    assert calls == []


def test_message_is_frozen_and_rejects_mutation() -> None:
    """The parsed message is a value: it cannot be changed after the fact."""
    parsed = parse_message(_assemble(_request_line(), _invite_headers(), SDP, CRLF))

    assert isinstance(parsed, SipMessage)
    with pytest.raises(FrozenInstanceError):
        parsed.start_line = "BYE sip:+8613800138000@127.0.0.1 SIP/2.0"
