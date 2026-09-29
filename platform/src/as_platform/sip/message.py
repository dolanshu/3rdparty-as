"""SIP message parsing and construction for the kernel's SIP boundary.

This is the wire-format half of the SIP seam. It does two things and nothing
else: it turns bytes off the wire into a :class:`SipMessage`, and it turns a
:class:`SipMessage`-shaped argument list back into bytes. It deliberately does
**not** know about transactions, dialogs, retransmissions or sockets --- those
belong to the stack binding, which ADR-0019 assigns to reSIProcate and which is
a later step. Until that binding lands, this module is what lets the kernel be
tested against real wire bytes without a stack.

Three properties are carried over from the rest of the kernel:

* **The body is untouched.** REQ-F-4: the SDP crosses the boundary byte for
  byte. Nothing here re-encodes, re-wraps or strips it, so two bodies can be
  compared byte for byte and a diff means a real difference.
* **Nothing is generated here.** The ``Via`` branch, the tags and the Call-ID
  come from the caller. ADR-0002: the moment this module reads a clock or draws
  a random number, its output stops being a function of its arguments.
* **Purity.** No IO, no clock, no global state. The same bytes in, the same
  bytes out, which is what makes the round-trip property testable at all.

Line breaks: RFC 3261 §7 mandates CRLF, and that is what is written. CR-only
and LF-only are accepted on input because captured traffic and hand-written
fixtures both show up in practice (the S1 baseline under
``testbed/contracts/sip-baseline/`` is CRLF).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

# CRLF is what RFC 3261 §7 mandates and what this module always writes.
CRLF: Final = b"\r\n"

#: The only SIP version this module writes (RFC 3261 §7.1, §7.2).
SIP_VERSION: Final = "SIP/2.0"

#: The header field this module writes from the body's byte count (RFC 3261 §20.14).
CONTENT_LENGTH: Final = "Content-Length"

#: The six header fields every request must carry (RFC 3261 §8.1.1).
REQUIRED_REQUEST_HEADERS: Final = ("To", "From", "CSeq", "Call-ID", "Max-Forwards", "Via")

#: The magic cookie every request's Via branch must begin with (RFC 3261 §8.1.1.7).
BRANCH_MAGIC_COOKIE: Final = "z9hG4bK"

#: The closed range of SIP status codes (RFC 3261 §7.2).
MIN_STATUS_CODE: Final = 100
MAX_STATUS_CODE: Final = 699

# CR-only and LF-only are tolerated on input; see the module docstring.
_LINE_BREAK: Final = re.compile(rb"\r\n|\r|\n")

# The empty line that ends the header section, one per accepted line break.
_HEAD_BODY_SEPARATORS: Final = (b"\r\n\r\n", b"\n\n", b"\r\r")


@dataclass(frozen=True)
class SipMessage:
    """A SIP message as it appeared on the wire.

    Attributes:
        start_line: The request line or the status line, without its trailing
            line break and without surrounding whitespace.
        headers: Every header field in wire order as ``(name, value)`` pairs.
            Repeated fields stay repeated and are never folded into one value;
            the name keeps the capitalisation of the wire, because only
            comparison is case-insensitive (RFC 3261 §7.3.1).
        body: Everything after the empty line, byte for byte. It is never
            re-encoded or stripped, so REQ-F-4 can be asserted by equality.
    """

    start_line: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


def parse_message(raw: bytes) -> SipMessage:
    """Parse wire bytes into a message.

    The head is split from the body at the **earliest** empty line, so a body
    that itself contains empty lines survives intact (RFC 3261 §7). Line
    breaks may be CRLF, CR or LF.

    Args:
        raw: One complete SIP message, body included.

    Returns:
        The parsed message, with the body left exactly as received.

    Raises:
        ValueError: If ``raw`` holds no start line. A header line without a
            colon is ignored rather than rejected: captures carry folded
            lines, and a folded continuation is not part of this contract.
    """
    head, body = _split_head_from_body(raw)
    lines = [line for line in _LINE_BREAK.split(head) if line.strip()]
    if not lines:
        raise ValueError("SIP message carries no start line")

    start_line = _decode(lines[0]).strip()
    fields: list[tuple[str, str]] = []
    for line in lines[1:]:
        field = _parse_header(line)
        if field is not None:
            fields.append(field)
    return SipMessage(start_line=start_line, headers=tuple(fields), body=body)


def header(message: SipMessage, name: str) -> str | None:
    """Return the value of the first header field with this name.

    Args:
        message: The message to look in.
        name: The header field name. The match is case-insensitive (RFC 3261
            §7.3.1), so ``"call-id"`` finds ``Call-ID``.

    Returns:
        The value of the first matching field, or ``None`` when the message
        carries no such field.
    """
    wanted = name.lower()
    for field_name, value in message.headers:
        if field_name.lower() == wanted:
            return value
    return None


def headers_all(message: SipMessage, name: str) -> tuple[str, ...]:
    """Return the values of every header field with this name.

    Args:
        message: The message to look in.
        name: The header field name; the match is case-insensitive.

    Returns:
        The values in wire order. Repeated fields stay separate instead of being
        joined, which is what a B2BUA test needs to see (RFC 3261 §7.3.1: a
        field may appear more than once and the order is significant).
    """
    wanted = name.lower()
    return tuple(value for field_name, value in message.headers if field_name.lower() == wanted)


def is_request(message: SipMessage) -> bool:
    """Tell a request from a response.

    Args:
        message: The message to classify.

    Returns:
        ``True`` for a request. A start line that begins with ``SIP/`` is a
        status line (RFC 3261 §7.2); everything else is a request line (§7.1).
    """
    return not message.start_line.upper().startswith("SIP/")


def request_uri(message: SipMessage) -> str | None:
    """Return the Request-URI of a request.

    Args:
        message: The message to read.

    Returns:
        The second token of the request line (RFC 3261 §7.1), or ``None`` for a
        response, which carries no Request-URI at all.
    """
    if not is_request(message):
        return None
    tokens = message.start_line.split()
    if len(tokens) < 2:
        return None
    return tokens[1]


def status_code(message: SipMessage) -> int | None:
    """Return the status code of a response.

    Args:
        message: The message to read.

    Returns:
        The second token of the status line as an integer (RFC 3261 §7.2), or
        ``None`` for a request, or for a status line whose second token is not
        a number.
    """
    if is_request(message):
        return None
    tokens = message.start_line.split()
    if len(tokens) < 2:
        return None
    try:
        return int(tokens[1])
    except ValueError:
        return None


def call_id(message: SipMessage) -> str | None:
    """Return the Call-ID of a message.

    Args:
        message: The message to read.

    Returns:
        The value of the ``Call-ID`` field (RFC 3261 §8.1.1.4), or ``None`` when
        it is absent. The kernel keys state and traces on this value.
    """
    return header(message, "Call-ID")


def build_request(
    method: str,
    request_uri: str,
    headers: Mapping[str, str] | Sequence[tuple[str, str]],
    body: bytes = b"",
) -> bytes:
    """Build the bytes of a SIP request.

    The request line is ``Method SP Request-URI SP SIP-Version`` (RFC 3261
    §7.1). The six mandatory fields of §8.1.1 must be present, each ``Via`` must
    carry a ``branch`` parameter beginning with the ``z9hG4bK`` magic cookie
    (§8.1.1.7), and ``Content-Length`` is computed here from ``body`` and
    written over whatever the caller supplied, because it counts bytes and a
    stale value would misframe the message (§20.14).

    Args:
        method: The SIP method, for example ``INVITE``.
        request_uri: The Request-URI as it is to go on the wire.
        headers: The header fields, either as a mapping or as a sequence of
            ``(name, value)`` pairs. A sequence is the only way to send a field
            more than once; both keep the caller's order.
        body: The message body. Carried through unchanged.

    Returns:
        The request as bytes with CRLF line breaks, ready to send.

    Raises:
        ValueError: If a mandatory field is missing, if a ``Via`` lacks a valid
            ``branch``, or if any name or value carries a line break.
    """
    fields = _normalise_headers(headers)
    _require_mandatory_fields(fields)
    _require_via_branch(fields)
    start_line = " ".join(
        (
            _forbid_line_breaks("method", method),
            _forbid_line_breaks("Request-URI", request_uri),
            SIP_VERSION,
        )
    )
    return _render(start_line, fields, body)


def build_response(
    status_code: int,
    reason_phrase: str,
    headers: Mapping[str, str] | Sequence[tuple[str, str]],
    body: bytes = b"",
) -> bytes:
    """Build the bytes of a SIP response.

    The status line is ``SIP-Version SP Status-Code SP Reason-Phrase`` (RFC 3261
    §7.2). ``Content-Length`` is computed here from ``body`` exactly as it is
    for a request.

    Unlike :func:`build_request`, the mandatory fields of §8.1.1 are not
    enforced: they are a requirement on requests, and a response that the AS
    originates itself carries whatever the caller puts in.

    Args:
        status_code: The three-digit status code, ``100`` to ``699``.
        reason_phrase: The reason phrase; may be empty.
        headers: The header fields, as a mapping or as a sequence of pairs.
        body: The message body. Carried through unchanged.

    Returns:
        The response as bytes with CRLF line breaks, ready to send.

    Raises:
        ValueError: If ``status_code`` is outside ``100..699``, or if a header
            name or value carries a line break.
    """
    if not MIN_STATUS_CODE <= status_code <= MAX_STATUS_CODE:
        raise ValueError(
            f"SIP status code must be in {MIN_STATUS_CODE}..{MAX_STATUS_CODE}, got {status_code}"
        )
    fields = _normalise_headers(headers)
    start_line = " ".join(
        (SIP_VERSION, str(status_code), _forbid_line_breaks("reason phrase", reason_phrase))
    )
    return _render(start_line, fields, body)


def _render(start_line: str, fields: tuple[tuple[str, str], ...], body: bytes) -> bytes:
    """Render a start line, header fields and a body as wire bytes.

    Args:
        start_line: The request line or the status line.
        fields: The header fields in the order they are to be written.
        body: The body, appended after the empty line without any change.

    Returns:
        The message as bytes, CRLF-separated, with ``Content-Length`` set to
        the body's byte count.
    """
    lines = [start_line]
    lines.extend(f"{name}: {value}" for name, value in _with_content_length(fields, len(body)))
    return _encode("\r\n".join(lines) + "\r\n\r\n") + body


def _with_content_length(
    fields: tuple[tuple[str, str], ...], length: int
) -> tuple[tuple[str, str], ...]:
    """Return the fields with ``Content-Length`` set to a byte count.

    A ``Content-Length`` already present is overwritten **in place**, so the
    field order the caller chose is kept; otherwise the field is appended.

    Args:
        fields: The header fields to complete.
        length: The body length in bytes (RFC 3261 §20.14 counts bytes, not
            characters).

    Returns:
        The completed fields.
    """
    value = str(length)
    wanted = CONTENT_LENGTH.lower()
    if any(name.lower() == wanted for name, _ in fields):
        return tuple(
            (name, value if name.lower() == wanted else field_value) for name, field_value in fields
        )
    return fields + ((CONTENT_LENGTH, value),)


def _normalise_headers(
    headers: Mapping[str, str] | Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Turn either accepted header shape into an ordered tuple of pairs.

    Args:
        headers: A mapping, or a sequence of ``(name, value)`` pairs.

    Returns:
        The fields as an ordered tuple; a mapping yields its insertion order.

    Raises:
        ValueError: If a name is empty, or if a name or a value carries a line
            break --- a CR or LF there would let one field forge another.
    """
    fields = tuple(headers.items()) if isinstance(headers, Mapping) else tuple(headers)
    for name, value in fields:
        if not name.strip():
            raise ValueError("SIP header field name must not be empty")
        if "\r" in name or "\n" in name:
            raise ValueError(f"SIP header field name must not carry a line break: {name!r}")
        if "\r" in value or "\n" in value:
            raise ValueError(f"SIP header field {name!r} value must not carry a line break")
    return fields


def _require_mandatory_fields(fields: tuple[tuple[str, str], ...]) -> None:
    """Check that every header field a request must carry is present.

    Args:
        fields: The header fields of the request being built.

    Raises:
        ValueError: If any field of RFC 3261 §8.1.1 is missing. The message
            names **all** of them, so a caller fixes them in one pass.
    """
    present = {name.lower() for name, _ in fields}
    missing = [name for name in REQUIRED_REQUEST_HEADERS if name.lower() not in present]
    if missing:
        raise ValueError(f"SIP request is missing mandatory header field(s): {', '.join(missing)}")


def _require_via_branch(fields: tuple[tuple[str, str], ...]) -> None:
    """Check that every ``Via`` carries a branch with the magic cookie.

    RFC 3261 §8.1.1.7 requires the branch parameter on every Via a request
    carries, and requires it to begin with ``z9hG4bK``. The value is the
    caller's: this module never invents one, because inventing it would mean
    reading a clock or drawing a random number, and ADR-0002 forbids that on a
    path whose output must be reproducible.

    Args:
        fields: The header fields of the request being built.

    Raises:
        ValueError: If a ``Via`` carries no branch, or carries one that does not
            begin with the magic cookie.
    """
    for name, value in fields:
        if name.lower() != "via":
            continue
        branch = _via_parameter(value, "branch")
        if branch is None:
            raise ValueError(f"Via header field carries no branch parameter: {value!r}")
        if not branch.startswith(BRANCH_MAGIC_COOKIE):
            raise ValueError(f"Via branch must start with {BRANCH_MAGIC_COOKIE!r}, got {branch!r}")


def _via_parameter(value: str, key: str) -> str | None:
    """Return one parameter of a ``Via`` header field value.

    Args:
        value: The Via value, for example ``SIP/2.0/UDP host;branch=z9hG4bKx``.
        key: The parameter name to look for; the match is case-insensitive.

    Returns:
        The parameter value, or ``None`` when the Via does not carry it.
    """
    for parameter in value.split(";"):
        name, separator, found = parameter.strip().partition("=")
        if separator and name.strip().lower() == key:
            return found.strip()
    return None


def _forbid_line_breaks(what: str, text: str) -> str:
    """Return text that is known to carry no CR and no LF.

    Args:
        what: What the text is, for the error message.
        text: The text to check.

    Returns:
        The text, unchanged.

    Raises:
        ValueError: If the text carries a line break.
    """
    if "\r" in text or "\n" in text:
        raise ValueError(f"SIP {what} must not carry a line break: {text!r}")
    return text


def _split_head_from_body(raw: bytes) -> tuple[bytes, bytes]:
    """Split a message at the empty line that ends its header section.

    Args:
        raw: The complete message.

    Returns:
        The header section and the body, both without the separator, split at
        the **earliest** empty line. A message with no empty line is all header
        section and has an empty body.
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
        The name as the wire wrote it and the value with surrounding whitespace
        removed (RFC 3261 §7.3.1), or ``None`` for a line that is not a header
        field.
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
        surrogates, so a value can be written back to the wire unchanged.
    """
    return raw.decode("utf-8", errors="surrogateescape")


def _encode(text: str) -> bytes:
    """Encode header text, reversing :func:`_decode`.

    Args:
        text: The text to encode.

    Returns:
        The bytes, with surrogates turned back into the bytes they came from.
    """
    return text.encode("utf-8", errors="surrogateescape")
