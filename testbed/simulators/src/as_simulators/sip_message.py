"""Minimal SIP message parsing for the contract tests.

The baselines under ``testbed/contracts/sip-baseline/`` are captured wire bytes.
Comparing two legs of a B2BUA call needs a parser that keeps what the wire
carried: header order, repeated header fields and an untouched body. A parser
that normalises anything would hide exactly the drift these tests exist to
catch, so the body is kept as raw bytes and header names keep their original
capitalisation while lookups stay case-insensitive (RFC 3261 §7.3.1).

The module is pure: no sockets, no clocks, no global state. The same functions
work on a capture file and on bytes read off a socket.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# CRLF is what RFC 3261 mandates; CR-only and LF-only are accepted because
# captured traffic and hand-written fixtures both show up in practice.
_LINE_BREAK = re.compile(rb"\r\n|\r|\n")

# The empty line that ends the header section, in each accepted flavour.
_HEAD_BODY_SEPARATORS = (b"\r\n\r\n", b"\n\n", b"\r\r")


@dataclass(frozen=True)
class SipMessage:
    """A SIP message as it appeared on the wire.

    Attributes:
        start_line: The request line or the status line, without the trailing
            line break and without surrounding whitespace.
        headers: Every header field in wire order as ``(name, value)`` pairs.
            Repeated fields stay repeated and are never joined into one value;
            the name keeps the capitalisation of the wire.
        body: Everything after the empty line, byte for byte. It is never
            re-encoded, re-wrapped or stripped, so two bodies can be compared
            byte for byte.
    """

    start_line: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


def parse_message(raw: bytes) -> SipMessage:
    """Parse wire bytes into a message.

    Args:
        raw: One complete SIP message, body included.

    Returns:
        The parsed message, with the body left exactly as received.

    Raises:
        ValueError: If ``raw`` holds no start line. Header lines without a colon
            are ignored rather than rejected: captures carry folded lines.
    """
    head, body = _split_head_from_body(raw)
    lines = [line for line in _LINE_BREAK.split(head) if line.strip()]
    if not lines:
        raise ValueError("SIP message carries no start line")

    start_line = _decode(lines[0]).strip()
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        field = _parse_header(line)
        if field is not None:
            headers.append(field)
    return SipMessage(start_line=start_line, headers=tuple(headers), body=body)


def header(msg: SipMessage, name: str) -> str | None:
    """Return the value of the first header field with this name.

    Args:
        msg: The message to look in.
        name: The header field name; the match is case-insensitive, as RFC 3261
            requires, so ``"call-id"`` finds ``Call-ID``.

    Returns:
        The value of the first matching field, or ``None`` when the message
        carries no such field.
    """
    wanted = name.lower()
    for field_name, value in msg.headers:
        if field_name.lower() == wanted:
            return value
    return None


def headers_all(msg: SipMessage, name: str) -> tuple[str, ...]:
    """Return the values of every header field with this name.

    Args:
        msg: The message to look in.
        name: The header field name; the match is case-insensitive.

    Returns:
        The values in wire order. Repeated fields stay separate instead of being
        joined, which is what a proxy test needs to see.
    """
    wanted = name.lower()
    return tuple(value for field_name, value in msg.headers if field_name.lower() == wanted)


def call_id(msg: SipMessage) -> str | None:
    """Return the Call-ID of a message.

    Args:
        msg: The message to read.

    Returns:
        The value of the ``Call-ID`` field, or ``None`` when it is absent.
    """
    return header(msg, "Call-ID")


def request_uri(msg: SipMessage) -> str | None:
    """Return the Request-URI of a request.

    Args:
        msg: The message to read.

    Returns:
        The second token of the request line, or ``None`` for a response, which
        carries no Request-URI at all.
    """
    if not is_request(msg):
        return None
    tokens = msg.start_line.split()
    if len(tokens) < 2:
        return None
    return tokens[1]


def is_request(msg: SipMessage) -> bool:
    """Tell a request from a response.

    Args:
        msg: The message to classify.

    Returns:
        ``True`` for a request. A start line that begins with ``SIP/`` is a
        status line, everything else is a request line.
    """
    return not msg.start_line.upper().startswith("SIP/")


def _split_head_from_body(raw: bytes) -> tuple[bytes, bytes]:
    """Split a message at the empty line that ends its header section.

    Args:
        raw: The complete message.

    Returns:
        The header section and the body, both without the separator. A message
        with no empty line is all headers and has an empty body.
    """
    cut = -1
    width = 0
    for separator in _HEAD_BODY_SEPARATORS:
        found = raw.find(separator)
        if found != -1 and (cut == -1 or found < cut):
            cut, width = found, len(separator)
    if cut == -1:
        return raw, b""
    return raw[:cut], raw[cut + width :]


def _parse_header(line: bytes) -> tuple[str, str] | None:
    """Parse one header line into a name and value pair.

    Args:
        line: One line of the header section, without its line break.

    Returns:
        The name as written on the wire and the value with surrounding
        whitespace removed, or ``None`` for a line that is not a header field.
    """
    name, separator, value = _decode(line).partition(":")
    if not separator:
        return None
    return name.strip(), value.strip()


def _decode(raw: bytes) -> str:
    """Decode header bytes without losing information.

    Args:
        raw: The bytes to decode.

    Returns:
        The decoded text. Bytes that are not valid UTF-8 are kept as
        surrogates, so a header value can be written back to the wire unchanged.
    """
    return raw.decode("utf-8", errors="surrogateescape")
