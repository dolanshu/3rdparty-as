"""Comparison of two SIP message sequences, as pure functions.

The E1 probe replays the M1 baseline (``testbed/contracts/sip-baseline/``)
against the stack ADR-0019 selected and has to answer one question: does the
stack emit the same messages, in the same order, as the POC did? This module is
that answer, and nothing else.

What is compared is what ADR-0019 §5 calls externally observable: the method or
the status code, the Call-ID, the ``host[:port]`` of the Request-URI and the
body byte for byte. What is deliberately **not** compared is header order, the
``Via`` branch value and the SDP ``o=`` timestamp: those differ between any two
implementations and comparing them would only produce noise.

The body is compared byte for byte because REQ-F-4 says so --- the SDP crosses
the AS untouched --- and because this module never re-encodes what it reads.
That is also why the parser of ``as_platform.sip.message`` is reused instead of
a second, subtly different one: a probe that disagreed with the kernel about
where a body starts would be measuring itself.

Purity is a requirement, not a style choice. No IO, no clock, no global state:
the same two sequences in, the same verdict out, which is what lets the verdict
be re-derived from the captured evidence files instead of trusted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from as_platform.sip.message import (
    SipMessage,
    call_id,
    is_request,
    parse_message,
    request_uri,
    status_code,
)


@dataclass(frozen=True)
class MessageExpectation:
    """The comparable fields of one SIP message.

    Attributes:
        method_or_code: The SIP method for a request (``INVITE``, ``ACK``,
            ``BYE``, ``CANCEL``) or the status code as text for a response
            (``100``, ``180``, ``200``, ``404``, ``603``).
        call_id: The ``Call-ID`` field value (RFC 3261 §8.1.1.4), or ``None``
            when the message carries none.
        request_uri_host: The ``host[:port]`` of the Request-URI (RFC 3261
            §7.1), or ``None`` for a response, which carries no Request-URI at
            all.
        body: The body as it came off the wire, or ``None`` when the message
            carries no body. An empty body and an absent body are the same
            thing on the wire, so both reduce to ``None``.
    """

    method_or_code: str
    call_id: str | None
    request_uri_host: str | None
    body: bytes | None


def to_expectation(raw: bytes) -> MessageExpectation:
    """Reduce one wire message to the fields this probe compares.

    Args:
        raw: One complete SIP message, body included, exactly as it appeared on
            the wire.

    Returns:
        The comparable fields of that message.

    Raises:
        ValueError: If ``raw`` holds no start line. Propagated from the kernel
            parser on purpose: a byte string that is not a SIP message must not
            be silently turned into an expectation that matches nothing.
    """
    message = parse_message(raw)
    return MessageExpectation(
        method_or_code=_method_or_code(message),
        call_id=call_id(message),
        request_uri_host=_request_uri_host(request_uri(message)),
        body=message.body or None,
    )


def compare_sequence(
    actual: Sequence[bytes],
    expected: Sequence[bytes],
) -> tuple[bool, tuple[str, ...]]:
    """Compare two SIP message sequences field by field, in order.

    Args:
        actual: The messages the stack under probe emitted, in wire order.
        expected: The baseline messages of the scenario, in wire order.

    Returns:
        A pair: whether every message matched, and the differences. The
        differences are empty when the sequences match; otherwise each one
        names the message number, the field and both values, so a reader can
        act on it without re-running the probe.

    Raises:
        ValueError: If any message is not parseable. See :func:`to_expectation`.
    """
    if len(actual) != len(expected):
        return False, (f"message count differs: actual {len(actual)}, expected {len(expected)}",)

    differences: list[str] = []
    for number, (actual_raw, expected_raw) in enumerate(
        zip(actual, expected, strict=False), start=1
    ):
        differences.extend(
            _compare_one(number, to_expectation(actual_raw), to_expectation(expected_raw))
        )
    return not differences, tuple(differences)


def _compare_one(
    number: int,
    actual: MessageExpectation,
    expected: MessageExpectation,
) -> list[str]:
    """Compare one message and describe every field that differs.

    Args:
        number: The 1-based position of the message in the sequence. It is what
            makes a difference actionable, so it is part of every message.
        actual: What the stack under probe emitted.
        expected: What the baseline says it should have emitted.

    Returns:
        One description per differing field, empty when the message matches.
        Fields are all checked rather than stopping at the first difference:
        one round of the probe should report everything that is wrong.
    """
    found: list[str] = []

    if actual.method_or_code != expected.method_or_code:
        found.append(
            f"message {number}: method/status differs: "
            f"actual {actual.method_or_code!r}, expected {expected.method_or_code!r}"
        )

    # A baseline message without a Call-ID cannot constrain anything.
    if expected.call_id is not None and actual.call_id != expected.call_id:
        found.append(
            f"message {number}: Call-ID differs: "
            f"actual {actual.call_id!r}, expected {expected.call_id!r}"
        )

    # Only requests carry a Request-URI, so a response imposes no expectation.
    if expected.request_uri_host is not None and (
        actual.request_uri_host != expected.request_uri_host
    ):
        found.append(
            f"message {number}: Request-URI host differs: "
            f"actual {actual.request_uri_host!r}, expected {expected.request_uri_host!r}"
        )

    if actual.body != expected.body:
        found.append(_describe_body_difference(number, actual.body, expected.body))

    return found


def _describe_body_difference(number: int, actual: bytes | None, expected: bytes | None) -> str:
    """Describe a body difference at byte granularity.

    Args:
        number: The 1-based position of the message in the sequence.
        actual: The body the stack under probe emitted, ``None`` for none.
        expected: The body the baseline carries, ``None`` for none.

    Returns:
        A description naming the first byte at which the two bodies disagree,
        or their lengths when one is a prefix of the other. Naming the byte
        beats dumping two SDP bodies: SDP is mostly identical by design.
    """
    if actual is None or expected is None:
        return f"message {number}: body differs: actual {actual!r}, expected {expected!r}"
    if len(actual) != len(expected):
        return (
            f"message {number}: body length differs: "
            f"actual {len(actual)} bytes, expected {len(expected)} bytes"
        )

    offset = 0
    while offset < len(actual) and actual[offset] == expected[offset]:
        offset += 1
    return (
        f"message {number}: body differs at byte {offset}: "
        f"actual {actual[offset]:#04x}, expected {expected[offset]:#04x}"
    )


def _method_or_code(message: SipMessage) -> str:
    """Return the method of a request or the status code of a response.

    Args:
        message: The parsed message.

    Returns:
        The first token of the request line (RFC 3261 §7.1) or the status code
        of the status line as text (§7.2). A start line that yields neither
        gives an empty string, which then differs from any real expectation
        instead of crashing the run.
    """
    if is_request(message):
        tokens = message.start_line.split()
        return tokens[0] if tokens else ""
    code = status_code(message)
    return str(code) if code is not None else ""


def _request_uri_host(uri: str | None) -> str | None:
    """Return the ``host[:port]`` part of a Request-URI.

    Args:
        uri: The Request-URI as it appears in the request line, for example
            ``sip:+8613800138000@127.0.0.1:45363``, or ``None`` for a response.

    Returns:
        The host and port, with the scheme, the user part and any URI
        parameters or headers removed, or ``None`` when there is nothing to
        compare. The port is kept exactly as written: a baseline captured on
        port 45363 and a stack that rewrote it to 5060 are a real difference,
        and silently adding a default port would hide it.
    """
    if uri is None:
        return None

    host_part = uri.rpartition("@")[2]
    if not host_part:
        return None
    if "@" not in uri:
        host_part = host_part.partition(":")[2]

    host_part = host_part.split(";", 1)[0].split("?", 1)[0]
    return host_part or None
