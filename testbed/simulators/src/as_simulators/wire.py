"""SIP header edits for the transparent bridge.

Parsing and rendering stay on :mod:`as_platform.sip.message`. This module only
inserts the Via and Record-Route a hop needs so responses can return, and it
leaves the Request-URI, From, To, Call-ID, P-Asserted-Identity and body alone
unless a caller passes a replacement it has already decided.
"""

from __future__ import annotations

import uuid

from as_platform.sip.message import SipMessage, header, headers_all, is_request, request_uri

_TRANSPORT_TOKEN = {"udp": "UDP", "tcp": "TCP", "tls": "TLS"}


def render_message(message: SipMessage) -> bytes:
    """Render a message, refreshing Content-Length from the body.

    Args:
        message: The message to write.

    Returns:
        Wire bytes. The body is appended unchanged.
    """
    fields: list[tuple[str, str]] = []
    replaced = False
    length = str(len(message.body))
    for name, value in message.headers:
        if name.lower() == "content-length":
            fields.append((name, length))
            replaced = True
        else:
            fields.append((name, value))
    if not replaced:
        fields.append(("Content-Length", length))
    lines = [message.start_line, *(f"{name}: {value}" for name, value in fields)]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + message.body


def with_headers(message: SipMessage, headers: tuple[tuple[str, str], ...]) -> SipMessage:
    """Return a copy that carries ``headers`` and the same start line and body."""
    return SipMessage(start_line=message.start_line, headers=headers, body=message.body)


def with_start_line(message: SipMessage, start_line: str) -> SipMessage:
    """Return a copy with a different start line."""
    return SipMessage(start_line=start_line, headers=message.headers, body=message.body)


def method_of(message: SipMessage) -> str:
    """Return the SIP method of a request."""
    return message.start_line.split(" ", 1)[0]


def transport_token(transport: str) -> str:
    """Return the Via token for ``udp``, ``tcp`` or ``tls``."""
    try:
        return _TRANSPORT_TOKEN[transport]
    except KeyError as error:
        raise ValueError(f"unsupported transport {transport!r}") from error


def new_branch() -> str:
    """Return a Via branch with the RFC 3261 magic cookie."""
    return f"z9hG4bK{uuid.uuid4().hex}"


def via_value(transport: str, host: str, port: int, branch: str) -> str:
    """Build one Via header value for this hop."""
    return f"SIP/2.0/{transport_token(transport)} {host}:{port};branch={branch};rport"


def record_route_value(transport: str, host: str, port: int) -> str:
    """Build a loose-routing Record-Route for this hop."""
    return f"<sip:bridge@{host}:{port};transport={transport};lr>"


def via_branch(value: str) -> str:
    """Return the branch parameter of a Via value.

    Raises:
        ValueError: If the Via has no branch.
    """
    for item in value.split(";")[1:]:
        name, separator, parameter = item.partition("=")
        if name.strip().lower() == "branch" and separator:
            return parameter.strip()
    raise ValueError("Via has no branch")


def via_sent_by(value: str) -> tuple[str, int]:
    """Return the host and port of a Via sent-by.

    Raises:
        ValueError: If the sent-by is not ``host:port``.
    """
    parts = value.split()
    if len(parts) < 2:
        raise ValueError("Via is missing sent-by")
    sent_by = parts[1].split(";", 1)[0]
    return split_host_port(sent_by)


def split_host_port(host_port: str) -> tuple[str, int]:
    """Split ``host:port`` or ``[ipv6]:port``.

    Raises:
        ValueError: If the port is missing or not numeric.
    """
    if host_port.startswith("["):
        host, separator, port_text = host_port[1:].partition("]")
        if separator != "]" or not port_text.startswith(":"):
            raise ValueError(f"invalid host:port {host_port!r}")
        port_text = port_text[1:]
    else:
        host, separator, port_text = host_port.rpartition(":")
        if not separator:
            raise ValueError(f"invalid host:port {host_port!r}")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError(f"invalid port in {host_port!r}") from error
    if not host or not 1 <= port <= 65535:
        raise ValueError(f"invalid host:port {host_port!r}")
    return host, port


def uri_host_port(uri: str) -> tuple[str, int]:
    """Return the host and port of a SIP URI or name-addr."""
    text = uri.strip()
    if "<" in text and ">" in text:
        text = text.split("<", 1)[1].split(">", 1)[0]
    text = text.split(";", 1)[0].strip()
    if text.lower().startswith("sip:"):
        text = text[4:]
    elif text.lower().startswith("sips:"):
        text = text[5:]
    host_port = text.rsplit("@", 1)[-1]
    return split_host_port(host_port)


def uri_user(uri: str) -> str:
    """Return the user part of a SIP URI or name-addr."""
    text = uri.strip()
    if "<" in text and ">" in text:
        text = text.split("<", 1)[1].split(">", 1)[0]
    text = text.split(";", 1)[0].strip()
    lowered = text.lower()
    if lowered.startswith("sip:"):
        text = text[4:]
    elif lowered.startswith("sips:"):
        text = text[5:]
    return text.split("@", 1)[0]


def prepend_header(
    headers: tuple[tuple[str, str], ...], name: str, value: str
) -> tuple[tuple[str, str], ...]:
    """Insert a header field at the front, which is where Via and Record-Route go."""
    return ((name, value), *headers)


def pop_first(
    headers: tuple[tuple[str, str], ...], name: str
) -> tuple[tuple[str, str], ...] | None:
    """Remove the first header with ``name``.

    Returns:
        The remaining fields, or ``None`` when the field is absent.
    """
    wanted = name.lower()
    updated: list[tuple[str, str]] = []
    removed = False
    for field_name, value in headers:
        if not removed and field_name.lower() == wanted:
            removed = True
            continue
        updated.append((field_name, value))
    if not removed:
        return None
    return tuple(updated)


def drop_top_route_if_self(
    headers: tuple[tuple[str, str], ...], host: str, port: int
) -> tuple[tuple[str, str], ...]:
    """Pop the first Route when it names this hop."""
    routes = [value for name, value in headers if name.lower() == "route"]
    if not routes:
        return headers
    try:
        route_host, route_port = uri_host_port(routes[0])
    except ValueError:
        return headers
    if route_host != host or route_port != port:
        return headers
    popped = pop_first(headers, "Route")
    return headers if popped is None else popped


def decrement_max_forwards(
    headers: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...] | None:
    """Decrement Max-Forwards.

    A missing field is treated as 70. ``None`` means the value was already 0
    and the proxy must not forward the request.
    """
    updated: list[tuple[str, str]] = []
    seen = False
    for name, value in headers:
        if name.lower() == "max-forwards" and not seen:
            seen = True
            try:
                current = int(value.strip())
            except ValueError:
                return None
            if current <= 0:
                return None
            updated.append((name, str(current - 1)))
            continue
        updated.append((name, value))
    if not seen:
        updated.insert(0, ("Max-Forwards", "69"))
    return tuple(updated)


def request_has_to_tag(message: SipMessage) -> bool:
    """Whether the To header already carries a tag (in-dialog request)."""
    to_value = header(message, "To") or ""
    return "tag=" in to_value.lower()


def top_via(message: SipMessage) -> str | None:
    """Return the first Via value, if any."""
    return header(message, "Via")


def forward_target(
    message: SipMessage,
    headers: tuple[tuple[str, str], ...],
    default_next: tuple[str, int],
) -> tuple[str, int]:
    """Choose where a request goes after this hop has popped its own Route.

    An initial INVITE keeps the configured next hop. The Request-URI of an
    initial request names the called party, not the next network element. An
    in-dialog request with a remaining Route follows that Route; otherwise it
    follows the Request-URI.
    """
    routes = [value for name, value in headers if name.lower() == "route"]
    if routes:
        return uri_host_port(routes[0])
    if is_request(message) and request_has_to_tag(message):
        uri = request_uri(message)
        if uri is not None:
            return uri_host_port(uri)
    return default_next


def echoed_headers(message: SipMessage, names: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Copy selected header fields in wire order."""
    wanted = {name.lower() for name in names}
    return tuple((name, value) for name, value in message.headers if name.lower() in wanted)


def header_values(message: SipMessage, name: str) -> tuple[str, ...]:
    """Return every value of one header field."""
    return headers_all(message, name)


def simple_response(
    request: SipMessage,
    status: int,
    reason: str,
    *,
    to_tag: str | None = None,
    contact: str | None = None,
    extra: tuple[tuple[str, str], ...] = (),
    body: bytes = b"",
) -> SipMessage:
    """Build a response that copies the request's transaction headers.

    Via, From, Call-ID, CSeq and Record-Route are copied in wire order. To is
    copied and gains ``to_tag`` when the request had none.
    """
    fields: list[tuple[str, str]] = []
    for name, value in request.headers:
        lowered = name.lower()
        if lowered in {"via", "from", "call-id", "cseq", "record-route"}:
            fields.append((name, value))
        elif lowered == "to":
            if to_tag and "tag=" not in value.lower():
                fields.append((name, f"{value};tag={to_tag}"))
            else:
                fields.append((name, value))
    if contact is not None:
        fields.append(("Contact", contact))
    fields.extend(extra)
    return SipMessage(
        start_line=f"SIP/2.0 {status} {reason}",
        headers=tuple(fields),
        body=body,
    )
