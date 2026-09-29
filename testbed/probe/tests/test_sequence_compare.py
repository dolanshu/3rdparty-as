"""Unit tests for the sequence comparator the E1 probe stands on.

The comparator is the part of the probe that must not be wrong: if it says two
sequences match when they do not, E1 passes and ADR-0019 consequence K2 is
released on nothing. So every field it claims to compare has a test that flips
only that field, and every failure message is asserted to name the message
number and both values --- a difference a reader cannot act on is no better
than no difference at all.

These tests are pure: no sockets, no clock, no fixtures on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from as_platform.sip.message import build_request, build_response

# The probe package is not a workspace member, so it is not installed; put its
# parent on the path the way running the probe as a script does.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from probe.sequence_compare import (  # noqa: E402
    MessageExpectation,
    compare_sequence,
    to_expectation,
)

pytestmark = pytest.mark.unit

CALL_ID: str = "48f64baa94fdfcfdd79af4128905d375"
OTHER_CALL_ID: str = "9c1f22ae0011d4b7c0a5ee63f21b8d40"
TRUNK_HOST: str = "127.0.0.1:45363"
CORE_HOST: str = "127.0.0.1:47199"
BRANCH: str = "z9hG4bKf2108578683121bd892c5d5d99e686bf"

SDP: bytes = (
    b"v=0\r\n"
    b"o=- 4101 4101 IN IP4 192.0.2.10\r\n"
    b"s=3rd-party AS POC call\r\n"
    b"c=IN IP4 192.0.2.10\r\n"
    b"t=0 0\r\n"
    b"m=audio 40000 RTP/AVP 0 8 101\r\n"
    b"a=rtpmap:0 PCMU/8000\r\n"
    b"a=sendrecv\r\n"
)


def _request(
    method: str, host: str = TRUNK_HOST, call_id: str = CALL_ID, body: bytes = SDP
) -> bytes:
    """Build a SIP request with the fields the comparator looks at.

    Args:
        method: The SIP method.
        host: The ``host:port`` to put in the Request-URI.
        call_id: The Call-ID.
        body: The body, carried through unchanged.

    Returns:
        The request as wire bytes.
    """
    return build_request(
        method,
        f"sip:+8613800138000@{host}",
        [
            ("Via", f"SIP/2.0/UDP {host};rport;branch={BRANCH}"),
            ("Max-Forwards", "70"),
            ("From", "<sip:+86216180001@127.0.0.1>;tag=b609018f3db67e29442268935be4c876"),
            ("To", "<sip:+8613800138000@127.0.0.1>"),
            ("Call-ID", call_id),
            ("CSeq", f"1319846983 {method}"),
            ("Content-Type", "application/sdp"),
        ],
        body,
    )


def _response(code: int, call_id: str = CALL_ID) -> bytes:
    """Build a SIP response with the fields the comparator looks at.

    Args:
        code: The status code.
        call_id: The Call-ID.

    Returns:
        The response as wire bytes.
    """
    return build_response(
        code,
        "Trying" if code == 100 else "OK",
        [
            ("Via", f"SIP/2.0/UDP {TRUNK_HOST};rport;branch={BRANCH}"),
            ("From", "<sip:+86216180001@127.0.0.1>;tag=b609018f3db67e29442268935be4c876"),
            ("To", "<sip:+8613800138000@127.0.0.1>"),
            ("Call-ID", call_id),
            ("CSeq", "1319846983 INVITE"),
        ],
    )


def _sequence() -> tuple[bytes, ...]:
    """Build a short, plausible sequence: INVITE, 100, 180, 200, ACK.

    Returns:
        The five messages, in wire order.
    """
    return (
        _request("INVITE"),
        _response(100),
        _response(180),
        _response(200, call_id=CALL_ID),
        _request("ACK", body=b""),
    )


def test_identical_sequences_match() -> None:
    """A sequence compared with itself matches, with nothing to report."""
    sequence = _sequence()

    matched, differences = compare_sequence(sequence, sequence)

    assert matched is True
    assert differences == ()


def test_message_count_difference_is_reported() -> None:
    """A missing trailing message is a failure, and the count is in the reason."""
    sequence = _sequence()

    matched, differences = compare_sequence(sequence[:-1], sequence)

    assert matched is False
    assert len(differences) == 1
    assert "message count" in differences[0]
    assert "4" in differences[0]
    assert "5" in differences[0]


def test_method_difference_is_reported() -> None:
    """A different method fails, naming the position and both methods."""
    expected = _sequence()
    actual = (expected[0], expected[1], expected[2], expected[3], _request("BYE", body=b""))

    matched, differences = compare_sequence(actual, expected)

    assert matched is False
    assert len(differences) == 1
    assert "message 5" in differences[0]
    assert "BYE" in differences[0]
    assert "ACK" in differences[0]


def test_status_code_difference_is_reported() -> None:
    """A different status code fails, naming the position and both codes."""
    expected = _sequence()
    actual = (expected[0], expected[1], _response(183), expected[3], expected[4])

    matched, differences = compare_sequence(actual, expected)

    assert matched is False
    assert len(differences) == 1
    assert "message 3" in differences[0]
    assert "183" in differences[0]
    assert "180" in differences[0]


def test_call_id_difference_is_reported() -> None:
    """A different Call-ID fails, naming the position and both values."""
    expected = _sequence()
    actual = (
        expected[0],
        _response(100, call_id=OTHER_CALL_ID),
        expected[2],
        expected[3],
        expected[4],
    )

    matched, differences = compare_sequence(actual, expected)

    assert matched is False
    assert len(differences) == 1
    assert "message 2" in differences[0]
    assert "Call-ID" in differences[0]
    assert OTHER_CALL_ID in differences[0]
    assert CALL_ID in differences[0]


def test_request_uri_host_difference_is_reported() -> None:
    """A rewritten Request-URI host fails; responses carry no Request-URI."""
    expected = _sequence()
    actual = (
        _request("INVITE", host=CORE_HOST),
        expected[1],
        expected[2],
        expected[3],
        expected[4],
    )

    matched, differences = compare_sequence(actual, expected)

    assert matched is False
    assert len(differences) == 1
    assert "message 1" in differences[0]
    assert "Request-URI" in differences[0]
    assert CORE_HOST in differences[0]
    assert TRUNK_HOST in differences[0]


def test_request_uri_host_is_not_compared_on_responses() -> None:
    """A response imposes no Request-URI expectation, so none is extracted."""
    expectation = to_expectation(_response(200))

    assert expectation.request_uri_host is None


def test_single_byte_body_difference_is_reported() -> None:
    """One flipped byte in the body fails, and the byte offset is named."""
    expected = _sequence()
    altered = bytearray(SDP)
    altered[9] = 0x39  # '4' -> '9' in the o= line of the SDP
    actual = (
        _request("INVITE", body=bytes(altered)),
        expected[1],
        expected[2],
        expected[3],
        expected[4],
    )

    matched, differences = compare_sequence(actual, expected)

    assert matched is False
    assert len(differences) == 1
    assert "message 1" in differences[0]
    assert "body differs at byte 9" in differences[0]
    assert "0x39" in differences[0]
    assert "0x34" in differences[0]


def test_comparison_is_pure() -> None:
    """The same two sequences give the same verdict twice: no hidden state."""
    expected = _sequence()
    actual = (expected[0], _response(183), expected[2], expected[3], expected[4])

    first = compare_sequence(actual, expected)
    second = compare_sequence(actual, expected)

    assert first == second


def test_to_expectation_reads_the_fields_the_baseline_records() -> None:
    """A request reduces to its method, Call-ID, Request-URI host and body."""
    raw = _request("INVITE")

    expectation = to_expectation(raw)

    assert expectation == MessageExpectation(
        method_or_code="INVITE",
        call_id=CALL_ID,
        request_uri_host=TRUNK_HOST,
        body=SDP,
    )
