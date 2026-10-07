"""Simulated callee. It answers INVITE with 200 and BYE with 200.

The user part of the Request-URI is recorded so a test can see a translated
number. This process does not apply routing policy.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from as_platform.sip.message import is_request, parse_message
from as_simulators.endpoint import SipServer
from as_simulators.wire import method_of, render_message, simple_response, uri_user

# Minimal answer so the product B2BUA can complete offer/answer. The simulated
# callee does not process media.
_ANSWER_SDP = (
    b"v=0\r\n"
    b"o=- 0 0 IN IP4 127.0.0.1\r\n"
    b"s=-\r\n"
    b"c=IN IP4 127.0.0.1\r\n"
    b"t=0 0\r\n"
    b"m=audio 9 RTP/AVP 0\r\n"
    b"a=rtpmap:0 PCMU/8000\r\n"
)


class PeerUas:
    """A single-transport UAS that accepts every INVITE."""

    def __init__(
        self,
        host: str,
        transport: str,
        *,
        tls_certificate: Path | None = None,
        tls_private_key: Path | None = None,
        listen_port: int = 0,
        bind_host: str | None = None,
    ) -> None:
        """Bind the callee.

        ``host`` goes into Contact. ``bind_host`` overrides the listen address.
        """
        self.host = host
        self.transport = transport
        self.request_users: list[str] = []
        self.request_methods: list[str] = []
        self._lock = threading.Lock()
        self._to_tag = uuid.uuid4().hex[:8]
        self.server = SipServer(
            bind_host or host,
            transport,
            self._on_message,
            tls_certificate=tls_certificate,
            tls_private_key=tls_private_key,
            port=listen_port,
        )

    @property
    def port(self) -> int:
        """Port the callee is bound to."""
        return self.server.port

    def start(self) -> None:
        """Start answering SIP."""
        self.server.start()

    def stop(self) -> None:
        """Stop the callee."""
        self.server.stop()

    def _on_message(
        self,
        server: SipServer,
        payload: bytes,
        peer: tuple[str, int],
        connection: object,
    ) -> None:
        import socket

        conn = connection if isinstance(connection, socket.socket) else None
        try:
            message = parse_message(payload)
        except ValueError:
            return
        if not is_request(message):
            return
        method = method_of(message)
        with self._lock:
            self.request_methods.append(method)
        if method == "INVITE":
            uri = message.start_line.split(" ", 2)[1]
            with self._lock:
                self.request_users.append(uri_user(uri))
            contact = f"<sip:uas@{self.host}:{self.port};transport={self.transport}>"
            response = simple_response(
                message,
                200,
                "OK",
                to_tag=self._to_tag,
                contact=contact,
                extra=(("Content-Type", "application/sdp"),),
                body=_ANSWER_SDP,
            )
            server.send(peer, render_message(response), conn)
            return
        if method == "BYE":
            response = simple_response(message, 200, "OK")
            server.send(peer, render_message(response), conn)
            return
        if method != "ACK":
            response = simple_response(message, 405, "Method Not Allowed")
            server.send(peer, render_message(response), conn)
