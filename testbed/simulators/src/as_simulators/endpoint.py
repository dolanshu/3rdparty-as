"""UDP, TCP and TLS listeners and one-shot clients for the simulators.

Each send writes the bytes it is given a single time.
"""

from __future__ import annotations

import select
import socket
import ssl
import threading
from collections.abc import Callable
from pathlib import Path

MessageHandler = Callable[["SipServer", bytes, tuple[str, int], socket.socket | None], None]

_HANDSHAKE_SECONDS = 2.0
_WRITE_SECONDS = 2.0
_POLL_SECONDS = 0.2
_READ_SECONDS = 0.05
_TLS_PEEK_SECONDS = 0.001


class SipServer:
    """Listen for SIP and hand each message to ``handler`` on its own thread."""

    def __init__(
        self,
        host: str,
        transport: str,
        handler: MessageHandler,
        *,
        tls_certificate: Path | None = None,
        tls_private_key: Path | None = None,
        port: int = 0,
    ) -> None:
        """Bind a socket. Call :meth:`start` to accept traffic.

        Args:
            host: Bind address.
            transport: ``udp``, ``tcp`` or ``tls``.
            handler: Called as ``handler(server, payload, peer, connection)``.
                ``connection`` is set for TCP and TLS and is ``None`` for UDP.
            tls_certificate: PEM certificate for ``tls``.
            tls_private_key: PEM key for ``tls``.
            port: Bind port. ``0`` asks the kernel for a free port.
        """
        if transport not in {"udp", "tcp", "tls"}:
            raise ValueError(f"unsupported transport {transport!r}")
        self.host = host
        self.transport = transport
        self._handler = handler
        self._closing = threading.Event()
        self._threads: list[threading.Thread] = []
        self._socket_locks: dict[int, threading.Lock] = {}
        self._socket_locks_guard = threading.Lock()
        self._tls_context: ssl.SSLContext | None = None
        if transport == "udp":
            self._listen: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._listen.bind((host, port))
        else:
            if transport == "tls" and (tls_certificate is None or tls_private_key is None):
                raise ValueError("tls server requires a certificate and key")
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            raw.bind((host, port))
            raw.listen(64)
            self._listen = raw
            if transport == "tls":
                assert tls_certificate is not None
                assert tls_private_key is not None
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(str(tls_certificate), str(tls_private_key))
                self._tls_context = context
        self._listen.settimeout(0.2)
        self.port = int(self._listen.getsockname()[1])

    def start(self) -> None:
        """Start the accept loop."""
        target = self._udp_loop if self.transport == "udp" else self._tcp_loop
        thread = threading.Thread(target=target, name=f"sip-{self.transport}", daemon=True)
        thread.start()
        self._threads.append(thread)

    def stop(self) -> None:
        """Stop the accept loop and close the listening socket."""
        self._closing.set()
        self._listen.close()
        for thread in self._threads:
            thread.join(timeout=1)

    def send(
        self, peer: tuple[str, int], payload: bytes, connection: socket.socket | None = None
    ) -> None:
        """Write ``payload`` once, on ``connection`` or as one UDP datagram.

        The write shares a lock with the read loop for that socket. An SSL
        socket raises or drops the connection if one thread reads it while
        another writes it.
        """
        if connection is None:
            self._listen.sendto(payload, peer)
            return
        with self._io_lock(connection):
            connection.sendall(payload)

    def _io_lock(self, sock: socket.socket) -> threading.Lock:
        with self._socket_locks_guard:
            lock = self._socket_locks.get(id(sock))
            if lock is None:
                lock = threading.Lock()
                self._socket_locks[id(sock)] = lock
            return lock

    def _udp_loop(self) -> None:
        while not self._closing.is_set():
            try:
                payload, peer = self._listen.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                return
            self._dispatch(payload, (str(peer[0]), int(peer[1])), None)

    def _tcp_loop(self) -> None:
        while not self._closing.is_set():
            try:
                connection, peer = self._listen.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            thread = threading.Thread(
                target=self._read_connection,
                args=(connection, (str(peer[0]), int(peer[1]))),
                daemon=True,
            )
            thread.start()

    def _read_connection(self, connection: socket.socket, peer: tuple[str, int]) -> None:
        try:
            if self._tls_context is not None:
                connection.settimeout(_HANDSHAKE_SECONDS)
                try:
                    connection = self._tls_context.wrap_socket(connection, server_side=True)
                except (ssl.SSLError, OSError):
                    return
            connection.settimeout(_WRITE_SECONDS)
            lock = self._io_lock(connection)
            buffer = b""
            while not self._closing.is_set():
                message, buffer = split_message(buffer)
                if message is not None:
                    self._dispatch(message, peer, connection)
                    continue
                try:
                    buffer += read_chunk(connection, lock)
                except TimeoutError:
                    continue
                except OSError:
                    return
        finally:
            with self._socket_locks_guard:
                self._socket_locks.pop(id(connection), None)
            connection.close()

    def _dispatch(
        self, payload: bytes, peer: tuple[str, int], connection: socket.socket | None
    ) -> None:
        threading.Thread(
            target=self._handle,
            args=(payload, peer, connection),
            daemon=True,
        ).start()

    def _handle(
        self, payload: bytes, peer: tuple[str, int], connection: socket.socket | None
    ) -> None:
        try:
            self._handler(self, payload, peer, connection)
        except OSError:
            # The peer went away while this message was being answered.
            return


class DialogClient:
    """Client used by the system-under-test leg toward the south bridge."""

    def __init__(self, host: str, port: int, transport: str, tls_ca_file: Path | None) -> None:
        """Open a client toward ``host:port``."""
        self.transport = transport
        self._peer = (host, port)
        self._buffer = b""
        self._tls_ca_file = tls_ca_file
        if transport == "udp":
            self._socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind(("0.0.0.0", 0))
            self._socket.settimeout(2.0)
        else:
            self._socket = _connect_stream(host, port, transport, tls_ca_file)
        self.local_port = int(self._socket.getsockname()[1])

    def send(self, payload: bytes) -> None:
        """Write one message."""
        if self.transport == "udp":
            self._socket.sendto(payload, self._peer)
            return
        self._socket.sendall(payload)

    def read_final(self, timeout: float = 2.0) -> bytes:
        """Read until a final response (status >= 200) arrives."""
        from as_platform.sip.message import parse_message, status_code

        deadline_socket_timeout = timeout
        self._socket.settimeout(deadline_socket_timeout)
        while True:
            if self.transport == "udp":
                payload, _peer = self._socket.recvfrom(65535)
            else:
                payload, self._buffer = _take_message(self._socket, self._buffer)
            message = parse_message(payload)
            code = status_code(message)
            if code is not None and code >= 200:
                return payload

    def close(self) -> None:
        """Close the client socket."""
        self._socket.close()


def _connect_stream(
    host: str, port: int, transport: str, tls_ca_file: Path | None, timeout: float = 2.0
) -> socket.socket:
    raw = socket.create_connection((host, port), timeout)
    raw.settimeout(timeout)
    if transport == "tcp":
        return raw
    if tls_ca_file is None:
        raw.close()
        raise ValueError("tls client requires a CA file")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(tls_ca_file))
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context.wrap_socket(raw, server_hostname=host)


def split_message(buffer: bytes) -> tuple[bytes | None, bytes]:
    """Return the first complete Content-Length framed message and the rest.

    Returns ``(None, buffer)`` while the message is still incomplete.
    """
    if b"\r\n\r\n" not in buffer:
        return None, buffer
    head, rest = buffer.split(b"\r\n\r\n", 1)
    length = 0
    for line in head.split(b"\r\n"):
        name, separator, value = line.partition(b":")
        if separator and name.strip().lower() in {b"content-length", b"l"}:
            length = int(value.strip() or b"0")
    if len(rest) < length:
        return None, buffer
    return head + b"\r\n\r\n" + rest[:length], rest[length:]


def read_chunk(sock: socket.socket, lock: threading.Lock) -> bytes:
    """Read whatever bytes are ready on a stream socket.

    The wait happens without ``lock`` so a writer on the same socket is not
    held up. Only the read itself takes the lock, with a short timeout,
    because an SSL socket must not be read and written at the same moment.

    Raises:
        TimeoutError: Nothing arrived during the poll interval.
        ConnectionError: The peer closed the stream.
    """
    if sock.fileno() < 0:
        raise ConnectionError("SIP stream closed")
    is_tls = isinstance(sock, ssl.SSLSocket)
    ready = isinstance(sock, ssl.SSLSocket) and sock.pending() > 0
    if not ready:
        try:
            readable, _writable, _failed = select.select([sock], [], [], _POLL_SECONDS)
        except ValueError as error:
            raise ConnectionError("SIP stream closed") from error
        ready = bool(readable)
    if not ready and not is_tls:
        raise TimeoutError("no SIP bytes yet")
    # OpenSSL can hold a whole record that select() does not report.
    read_seconds = _READ_SECONDS if ready else _TLS_PEEK_SECONDS
    with lock:
        previous = sock.gettimeout()
        sock.settimeout(read_seconds)
        try:
            chunk = sock.recv(65535)
        finally:
            sock.settimeout(previous)
    if not chunk:
        raise ConnectionError("SIP stream closed")
    return chunk


def _take_message(sock: socket.socket, buffer: bytes) -> tuple[bytes, bytes]:
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("SIP stream closed before a complete message")
        buffer += chunk
    head, rest = buffer.split(b"\r\n\r\n", 1)
    length = 0
    for line in head.split(b"\r\n"):
        name, separator, value = line.partition(b":")
        if separator and name.lower() in {b"content-length", b"l"}:
            length = int(value.strip() or b"0")
    while len(rest) < length:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("SIP stream closed before the message body")
        rest += chunk
    return head + b"\r\n\r\n" + rest[:length], rest[length:]
