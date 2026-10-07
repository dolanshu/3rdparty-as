"""Transparent SIP bridge used by the simulated S-CSCF and S-SBC.

The hop prepends its own Via and, on an initial INVITE, its own Record-Route.
It does not change the Request-URI, From, To, Call-ID, P-Asserted-Identity or
body. Responses are forwarded after the hop's Via is removed.

The ACK for a non-2xx final response belongs to the hop that sent that
response upstream (RFC 3261 §17.1.1.3), so the bridge absorbs it instead of
forwarding it.
"""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass
from pathlib import Path

from as_platform.sip.message import SipMessage, header, is_request, parse_message, status_code
from as_simulators.endpoint import SipServer, _connect_stream, read_chunk, split_message
from as_simulators.wire import (
    decrement_max_forwards,
    drop_top_route_if_self,
    forward_target,
    method_of,
    new_branch,
    pop_first,
    record_route_value,
    render_message,
    request_has_to_tag,
    simple_response,
    via_branch,
    via_value,
    with_headers,
)


@dataclass(frozen=True)
class _Pending:
    peer: tuple[str, int]
    connection: socket.socket | None
    upstream_branch: str | None
    method: str


@dataclass
class _Outbound:
    sock: socket.socket
    io: threading.Lock


class TransparentBridge:
    """One listening hop that forwards to a configured next hop."""

    def __init__(
        self,
        *,
        advertised_host: str,
        next_hop: tuple[str, int],
        transport: str,
        tls_certificate: Path | None = None,
        tls_private_key: Path | None = None,
        tls_ca_file: Path | None = None,
        listen_port: int = 0,
        outbound_timeout: float = 2.0,
        bind_host: str | None = None,
    ) -> None:
        """Bind the hop.

        Args:
            advertised_host: Name or address written into Via and Record-Route.
            next_hop: Where initial requests go.
            transport: ``udp``, ``tcp`` or ``tls``.
            tls_certificate: Server certificate for ``tls``.
            tls_private_key: Server key for ``tls``.
            tls_ca_file: CA used to verify the next hop for ``tls``.
            listen_port: Bind port. ``0`` asks the kernel for one.
            outbound_timeout: Connect and write timeout toward the next hop.
            bind_host: Listen address when it differs from ``advertised_host``,
                for example the pod IP behind a Service name.
        """
        if advertised_host in {"0.0.0.0", "::"}:
            advertised_host = "127.0.0.1"
        self.advertised_host = advertised_host
        self.next_hop = next_hop
        self.transport = transport
        self._tls_ca_file = tls_ca_file
        self._outbound_timeout = outbound_timeout
        self._pending: dict[str, _Pending] = {}
        self._absorb: set[str] = set()
        self._lock = threading.Lock()
        self._outbounds: dict[tuple[str, int], _Outbound] = {}
        self._outbound_lock = threading.Lock()
        self.server = SipServer(
            bind_host or advertised_host,
            transport,
            self._on_message,
            tls_certificate=tls_certificate,
            tls_private_key=tls_private_key,
            port=listen_port,
        )

    @property
    def port(self) -> int:
        """UDP or TCP port this hop is bound to."""
        return self.server.port

    def start(self) -> None:
        """Start accepting SIP."""
        self.server.start()

    def stop(self) -> None:
        """Stop the listener and every outbound connection."""
        self.server.stop()
        with self._outbound_lock:
            outbounds = list(self._outbounds.values())
            self._outbounds.clear()
        for outbound in outbounds:
            outbound.sock.close()

    def _on_message(
        self,
        server: SipServer,
        payload: bytes,
        peer: tuple[str, int],
        connection: socket.socket | None,
    ) -> None:
        try:
            message = parse_message(payload)
        except ValueError:
            return
        if is_request(message):
            self._forward_request(server, message, peer, connection)
            return
        self._forward_response(server, message)

    def _forward_request(
        self,
        server: SipServer,
        message: SipMessage,
        peer: tuple[str, int],
        connection: socket.socket | None,
    ) -> None:
        method = method_of(message)
        upstream_branch = _top_branch(message)
        if method == "ACK" and upstream_branch is not None:
            with self._lock:
                if upstream_branch in self._absorb:
                    self._absorb.discard(upstream_branch)
                    return
        routed = drop_top_route_if_self(message.headers, self.advertised_host, self.port)
        forwarded = decrement_max_forwards(routed)
        if forwarded is None:
            refused = simple_response(message, 483, "Too Many Hops")
            server.send(peer, render_message(refused), connection)
            return
        branch = new_branch()
        headers: tuple[tuple[str, str], ...] = (
            ("Via", via_value(self.transport, self.advertised_host, self.port, branch)),
            *forwarded,
        )
        if method == "INVITE" and not request_has_to_tag(message):
            headers = (
                (
                    "Record-Route",
                    record_route_value(self.transport, self.advertised_host, self.port),
                ),
                *headers,
            )
        try:
            target = forward_target(message, headers, self.next_hop)
        except ValueError:
            return
        if self._is_self(target):
            target = self.next_hop
        if method != "ACK":
            with self._lock:
                self._pending[branch] = _Pending(peer, connection, upstream_branch, method)
        rendered = render_message(with_headers(message, headers))
        try:
            if self.transport == "udp":
                server.send(target, rendered)
            else:
                self._send_outbound(target, rendered)
        except OSError:
            with self._lock:
                self._pending.pop(branch, None)

    def _is_self(self, target: tuple[str, int]) -> bool:
        """Return whether ``target`` is this hop, which would make a forwarding loop."""
        host, port = target
        if port != self.port:
            return False
        if host == self.advertised_host:
            return True
        try:
            theirs = {item[4][0] for item in socket.getaddrinfo(host, port)}
            ours = {item[4][0] for item in socket.getaddrinfo(self.advertised_host, port)}
        except socket.gaierror:
            return False
        return bool(theirs & ours)

    def _send_outbound(self, target: tuple[str, int], payload: bytes) -> None:
        with self._outbound_lock:
            outbound = self._outbounds.get(target)
            fresh = outbound is None
            if outbound is None:
                host, port = target
                sock = _connect_stream(
                    host, port, self.transport, self._tls_ca_file, self._outbound_timeout
                )
                outbound = _Outbound(sock, threading.Lock())
                self._outbounds[target] = outbound
        try:
            with outbound.io:
                outbound.sock.sendall(payload)
        except OSError:
            self._drop_outbound(target, outbound)
            raise
        if fresh:
            threading.Thread(
                target=self._read_outbound,
                args=(target, outbound),
                name="bridge-out",
                daemon=True,
            ).start()

    def _read_outbound(self, target: tuple[str, int], outbound: _Outbound) -> None:
        buffer = b""
        while self._outbounds.get(target) is outbound:
            payload, buffer = split_message(buffer)
            if payload is None:
                try:
                    buffer += read_chunk(outbound.sock, outbound.io)
                except TimeoutError:
                    continue
                except OSError:
                    self._drop_outbound(target, outbound)
                    return
                continue
            try:
                message = parse_message(payload)
            except ValueError:
                continue
            if is_request(message):
                continue
            self._forward_response(self.server, message)

    def _drop_outbound(self, target: tuple[str, int], outbound: _Outbound) -> None:
        with self._outbound_lock:
            if self._outbounds.get(target) is outbound:
                del self._outbounds[target]
        outbound.sock.close()

    def _forward_response(self, server: SipServer, message: SipMessage) -> None:
        branch = _top_branch(message)
        if branch is None:
            return
        with self._lock:
            pending = self._pending.get(branch)
        if pending is None:
            return
        popped = pop_first(message.headers, "Via")
        if popped is None:
            return
        status = status_code(message)
        final = status is not None and status >= 200
        if final:
            with self._lock:
                self._pending.pop(branch, None)
                if (
                    pending.method == "INVITE"
                    and status is not None
                    and status >= 300
                    and pending.upstream_branch is not None
                ):
                    self._absorb.add(pending.upstream_branch)
        rendered = render_message(with_headers(message, popped))
        try:
            server.send(pending.peer, rendered, pending.connection)
        except OSError:
            return


def _top_branch(message: SipMessage) -> str | None:
    top = header(message, "Via")
    if top is None:
        return None
    try:
        return via_branch(top)
    except ValueError:
        return None
