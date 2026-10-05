"""Minimal UDP listener proving M2 ingress peer-policy enforcement.

M2 integration only — not the product SIP stack. reSIProcate binding will call the
same :class:`~as_platform.sip.ingress.TransportIngressGate` API on the real
accept path and replace this module.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Sequence

from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.transport import PeerIdentity

_MAX_DATAGRAM_BYTES = 65535
_RECV_TIMEOUT_SECONDS = 0.2


class UdpIngressServer:
    """Threaded UDP socket that enforces :meth:`TransportIngressGate.check_peer`."""

    def __init__(
        self,
        gate: TransportIngressGate,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        """Configure a listener; call :meth:`start` to bind and receive.

        Args:
            gate: Ingress gate consulted for each datagram's source address.
            host: Address to bind (loopback by default for tests).
            port: UDP port, or ``0`` for an OS-assigned ephemeral port.
        """
        self._gate = gate
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._received_lock = threading.Lock()
        self._received: list[bytes] = []

    @property
    def port(self) -> int:
        """The bound UDP port after :meth:`start`."""
        if self._socket is None:
            raise RuntimeError("UdpIngressServer is not started")
        return int(self._socket.getsockname()[1])

    @property
    def host(self) -> str:
        """The bound host after :meth:`start`."""
        if self._socket is None:
            raise RuntimeError("UdpIngressServer is not started")
        return str(self._socket.getsockname()[0])

    def received_payloads(self) -> Sequence[bytes]:
        """Snapshots payloads that passed the ingress gate."""
        with self._received_lock:
            return tuple(self._received)

    def start(self) -> None:
        """Bind, spawn the receive thread, and begin dropping denied peers."""
        if self._thread is not None:
            raise RuntimeError("UdpIngressServer is already started")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(_RECV_TIMEOUT_SECONDS)
        sock.bind((self._host, self._port))
        self._socket = sock
        self._stop.clear()

        def _serve() -> None:
            while not self._stop.is_set():
                try:
                    payload, addr = sock.recvfrom(_MAX_DATAGRAM_BYTES)
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    continue

                peer = PeerIdentity(address=addr[0], port=addr[1])
                if not self._gate.check_peer(peer):
                    continue

                with self._received_lock:
                    self._received.append(payload)

        self._thread = threading.Thread(target=_serve, name="udp-ingress", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the receive thread and close the socket."""
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
