"""UDP, TCP and TLS clients for the call-load harness.

Each request is written once. Nothing in this module schedules Timer A or any
other retransmission.
"""

from __future__ import annotations

import socket
import ssl
from pathlib import Path


class SipClient:
    """One connected SIP client.

    ``send`` writes the payload a single time. ``recv`` returns one complete
    SIP message or raises ``TimeoutError``.
    """

    def send(self, payload: bytes) -> None:
        """Write one SIP message. Implementations must not repeat it."""
        raise NotImplementedError

    def recv(self) -> bytes:
        """Return the next complete SIP message."""
        raise NotImplementedError

    def local_address(self) -> tuple[str, int]:
        """Return the local host and port placed in Via and Contact."""
        raise NotImplementedError

    def reconnect(self, host: str, port: int) -> None:
        """Point later sends at a dialog hop without changing the transport."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the underlying socket."""
        raise NotImplementedError


class _UdpClient(SipClient):
    """Connected UDP socket. One ``send`` is one datagram."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self._timeout = timeout
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(timeout)
        self._socket.connect((host, port))

    def send(self, payload: bytes) -> None:
        """Send one datagram."""
        self._socket.send(payload)

    def recv(self) -> bytes:
        """Return one datagram."""
        return self._socket.recv(65535)

    def local_address(self) -> tuple[str, int]:
        """Return the connected local address."""
        host, port = self._socket.getsockname()[:2]
        return str(host), int(port)

    def reconnect(self, host: str, port: int) -> None:
        """Connect the same UDP socket at the next hop. The local port stays."""
        candidates = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
        if not candidates:
            raise OSError(f"no UDP address found for SIP next hop {host}")
        self._socket.connect(candidates[0][4])

    def close(self) -> None:
        """Close the UDP socket."""
        self._socket.close()


class _StreamClient(SipClient):
    """TCP or TLS client. Messages are framed with Content-Length."""

    def __init__(self, sock: socket.socket) -> None:
        self._socket = sock
        self._buffer = b""

    def send(self, payload: bytes) -> None:
        """Write one message. The call returns after a single ``sendall``."""
        self._socket.sendall(payload)

    def recv(self) -> bytes:
        """Read until one Content-Length framed message is complete."""
        message, self._buffer = _take_message(self._socket, self._buffer)
        return message

    def local_address(self) -> tuple[str, int]:
        """Return the connected local address."""
        host, port = self._socket.getsockname()[:2]
        return str(host), int(port)

    def reconnect(self, host: str, port: int) -> None:
        """Open a new connection to the dialog hop and drop the old buffer."""
        timeout = self._socket.gettimeout()
        tls = self._socket
        self._socket.close()
        self._buffer = b""
        self._socket = _connect_stream(host, port, timeout if timeout is not None else 5.0, tls)

    def close(self) -> None:
        """Close the stream socket."""
        self._socket.close()


def open_client(
    *,
    host: str,
    port: int,
    transport: str,
    timeout: float,
    tls_ca_file: Path | None,
) -> SipClient:
    """Connect to a SIP hop.

    Args:
        host: Remote host or IPv4 address.
        port: Remote port.
        transport: ``udp``, ``tcp`` or ``tls``.
        timeout: Socket timeout in seconds.
        tls_ca_file: PEM CA used when ``transport`` is ``tls``.

    Returns:
        A client that writes each payload once.

    Raises:
        ValueError: If the transport is unknown or TLS has no CA file.
    """
    if transport == "udp":
        return _UdpClient(host, port, timeout)
    if transport not in {"tcp", "tls"}:
        raise ValueError(f"unsupported transport {transport!r}")
    if transport == "tls" and tls_ca_file is None:
        raise ValueError("tls transport requires tls_ca_file")
    sock = _connect(host, port, timeout, transport, tls_ca_file)
    return _StreamClient(sock)


def _connect(
    host: str,
    port: int,
    timeout: float,
    transport: str,
    tls_ca_file: Path | None,
) -> socket.socket:
    raw = socket.create_connection((host, port), timeout)
    raw.settimeout(timeout)
    if transport == "tcp":
        return raw
    if tls_ca_file is None:
        raw.close()
        raise ValueError("tls transport requires tls_ca_file")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(tls_ca_file))
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context.wrap_socket(raw, server_hostname=host)


def _connect_stream(host: str, port: int, timeout: float, previous: socket.socket) -> socket.socket:
    """Reconnect using the same transport as ``previous``."""
    raw = socket.create_connection((host, port), timeout)
    raw.settimeout(timeout)
    if isinstance(previous, ssl.SSLSocket):
        return previous.context.wrap_socket(raw, server_hostname=host)
    return raw


def _take_message(sock: socket.socket, buffer: bytes) -> tuple[bytes, bytes]:
    """Read one Content-Length framed SIP message from a stream."""
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise TimeoutError("SIP stream closed before a complete message")
        buffer += chunk
        if len(buffer) > 1_048_576:
            raise ValueError("SIP stream header exceeds 1 MiB")
    head, rest = buffer.split(b"\r\n\r\n", 1)
    length = _content_length(head)
    while len(rest) < length:
        chunk = sock.recv(4096)
        if not chunk:
            raise TimeoutError("SIP stream closed before the message body")
        rest += chunk
    message = head + b"\r\n\r\n" + rest[:length]
    return message, rest[length:]


def _content_length(head: bytes) -> int:
    for line in head.split(b"\r\n"):
        name, separator, value = line.partition(b":")
        if separator and name.lower() in {b"content-length", b"l"}:
            return int(value.strip() or b"0")
    return 0
