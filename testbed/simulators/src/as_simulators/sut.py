"""SIP front for the product decision kernel.

The listener is the system under test in the ``as-sut`` namespace. It calls
:func:`as_platform.decision.decide.decide` and, for a translation, rewrites the
called number with :func:`as_translation.decision.translate_number`. It is not
the reSIProcate product process; that process is what a later image binds.
Calls are accepted only from the simulated S-SBC.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from as_platform.decision import RuleSet
from as_platform.decision.decide import DecisionAction, DecisionRequest, decide
from as_platform.sip.message import header, is_request, parse_message, status_code
from as_simulators.endpoint import DialogClient, SipServer
from as_simulators.wire import (
    header_values,
    method_of,
    new_branch,
    render_message,
    simple_response,
    uri_user,
    via_sent_by,
    via_value,
)
from as_translation.decision import TranslationRule, find_translation_rule, translate_number


class PeerGate:
    """Reject SIP that did not arrive from the simulated S-SBC.

    On one host every socket shares ``127.0.0.1``, so UDP is admitted only when
    the packet source port and the top Via port are the S-SBC listen port.
    TCP and TLS admit the S-SBC's Via port. When ``peer_host`` is set, the
    source address must resolve to that name instead. This is the application
    check; the chart's NetworkPolicy is the cluster check.
    """

    def __init__(self) -> None:
        """Start with no admitted peer until the platform fills one in."""
        self.via_ports: set[int] = set()
        self.peer_host: str | None = None

    def permit(self, peer: tuple[str, int], via_port: int, transport: str) -> bool:
        """Return whether this request may enter the system under test."""
        if self.peer_host:
            try:
                addresses = socket.getaddrinfo(self.peer_host, None)
            except socket.gaierror:
                return False
            allowed = {item[4][0] for item in addresses}
            return peer[0] in allowed
        if not self.via_ports:
            return False
        if transport == "udp":
            return peer[1] in self.via_ports and via_port in self.via_ports
        return via_port in self.via_ports


@dataclass
class _Dialog:
    outbound_call_id: str
    outbound_from: str
    outbound_to: str
    outbound_uri: str
    south: tuple[str, int]
    client: DialogClient
    transport: str


class DecisionSut:
    """B2BUA that applies the product rule set and speaks SIP to the south bridge."""

    def __init__(
        self,
        *,
        host: str,
        transport: str,
        rules: RuleSet,
        translations: tuple[TranslationRule, ...],
        gate: PeerGate,
        south: tuple[str, int],
        tls_certificate: Path | None = None,
        tls_private_key: Path | None = None,
        tls_ca_file: Path | None = None,
        listen_port: int = 0,
        bind_host: str | None = None,
    ) -> None:
        """Bind the system under test.

        ``host`` goes into Via and Contact. ``bind_host`` overrides the listen
        address, for example the pod IP behind a Service name.
        """
        self.host = host
        self.transport = transport
        self._rules = rules
        self._translations = translations
        self.gate = gate
        self._south = south
        self._tls_ca_file = tls_ca_file
        self._dialogs: dict[str, _Dialog] = {}
        self._lock = threading.Lock()
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
        """Port the system under test is bound to."""
        return self.server.port

    def start(self) -> None:
        """Start accepting SIP from the S-SBC."""
        self.server.start()

    def stop(self) -> None:
        """Stop the listener and open outbound clients."""
        self.server.stop()
        with self._lock:
            dialogs = list(self._dialogs.values())
            self._dialogs.clear()
        for dialog in dialogs:
            dialog.client.close()

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
        if not is_request(message):
            return
        via = header(message, "Via")
        via_port = -1
        if via is not None:
            try:
                _host, via_port = via_sent_by(via)
            except ValueError:
                via_port = -1
        if not self.gate.permit(peer, via_port, self.transport):
            if method_of(message) == "INVITE":
                refused = simple_response(message, 403, "Forbidden", to_tag="denied")
                server.send(peer, render_message(refused), connection)
            return
        method = method_of(message)
        if method == "INVITE":
            self._on_invite(server, message, peer, connection)
        elif method == "BYE":
            self._on_bye(server, message, peer, connection)
        elif method != "ACK":
            refused = simple_response(message, 405, "Method Not Allowed")
            server.send(peer, render_message(refused), connection)

    def _on_invite(
        self,
        server: SipServer,
        message: object,
        peer: tuple[str, int],
        connection: socket.socket | None,
    ) -> None:
        from as_platform.sip.message import SipMessage

        assert isinstance(message, SipMessage)
        call_id = header(message, "Call-ID") or ""
        called = uri_user(message.start_line.split(" ", 2)[1])
        pai = header(message, "P-Asserted-Identity")
        calling = uri_user(pai or header(message, "From") or "")
        verdict = decide(
            DecisionRequest(
                call_id=call_id,
                calling_number=calling,
                called_number=called,
                received_at=time.time(),
            ),
            self._rules,
        )
        if verdict.action is DecisionAction.NOT_FOUND:
            server.send(
                peer,
                render_message(simple_response(message, 404, "Not Found", to_tag="nomatch")),
                connection,
            )
            return
        if verdict.action is DecisionAction.DECLINE:
            server.send(
                peer,
                render_message(simple_response(message, 603, "Decline", to_tag="blocked")),
                connection,
            )
            return
        if verdict.target is None:
            server.send(
                peer,
                render_message(simple_response(message, 500, "Server Internal Error")),
                connection,
            )
            return
        user = called
        if verdict.action is DecisionAction.TRANSLATE:
            rule = find_translation_rule(called, self._translations)
            user = translate_number(called, rule) if rule is not None else called
        self._bridge_invite(server, message, peer, connection, call_id, calling, user)

    def _bridge_invite(
        self,
        server: SipServer,
        message: object,
        peer: tuple[str, int],
        connection: socket.socket | None,
        inbound_call_id: str,
        calling: str,
        user: str,
    ) -> None:
        from as_platform.sip.message import SipMessage

        assert isinstance(message, SipMessage)
        south_host, south_port = self._south
        client = DialogClient(south_host, south_port, self.transport, self._tls_ca_file)
        outbound_call_id = f"{uuid.uuid4()}@as-sut"
        from_tag = uuid.uuid4().hex[:8]
        outbound_from = f"<sip:{calling}@as-sut>;tag={from_tag}"
        outbound_to = f"<sip:{user}@{south_host}>"
        request_uri = f"sip:{user}@{south_host}:{south_port}"
        branch = new_branch()
        via = via_value(self.transport, self.host, client.local_port, branch)
        pai = header(message, "P-Asserted-Identity")
        lines = [
            f"INVITE {request_uri} SIP/2.0",
            f"Via: {via}",
            "Max-Forwards: 70",
            f"From: {outbound_from}",
            f"To: {outbound_to}",
            f"Call-ID: {outbound_call_id}",
            "CSeq: 1 INVITE",
            f"Contact: <sip:sut@{self.host}:{self.port};transport={self.transport}>",
        ]
        if pai:
            lines.append(f"P-Asserted-Identity: {pai}")
        if message.body:
            lines.append("Content-Type: application/sdp")
        lines.append(f"Content-Length: {len(message.body)}")
        payload = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + message.body
        try:
            client.send(payload)
            final = client.read_final()
        except (OSError, TimeoutError, ValueError):
            client.close()
            server.send(
                peer,
                render_message(simple_response(message, 504, "Server Time-out", to_tag="timeout")),
                connection,
            )
            return
        downstream = parse_message(final)
        code = status_code(downstream) or 502
        remote_to = header(downstream, "To") or outbound_to
        contact = header(downstream, "Contact")
        outbound_uri = uri_user_uri(contact) if contact else request_uri
        if code < 300:
            self._ack_downstream(client, downstream, outbound_from, remote_to, outbound_uri)
            with self._lock:
                self._dialogs[inbound_call_id] = _Dialog(
                    outbound_call_id=outbound_call_id,
                    outbound_from=outbound_from,
                    outbound_to=remote_to,
                    outbound_uri=outbound_uri,
                    south=(south_host, south_port),
                    client=client,
                    transport=self.transport,
                )
        else:
            client.close()
        to_tag = "sut" if code >= 300 else uuid.uuid4().hex[:8]
        upstream = simple_response(
            message,
            code,
            _reason(code),
            to_tag=to_tag,
            contact=f"<sip:sut@{self.host}:{self.port};transport={self.transport}>",
        )
        server.send(peer, render_message(upstream), connection)

    def _ack_downstream(
        self,
        client: DialogClient,
        response: object,
        outbound_from: str,
        remote_to: str,
        outbound_uri: str,
    ) -> None:
        from as_platform.sip.message import SipMessage

        assert isinstance(response, SipMessage)
        call_id = header(response, "Call-ID") or ""
        routes = header_values(response, "Record-Route")
        branch = new_branch()
        via = via_value(self.transport, self.host, client.local_port, branch)
        lines = [
            f"ACK {outbound_uri} SIP/2.0",
            f"Via: {via}",
            "Max-Forwards: 70",
            f"From: {outbound_from}",
            f"To: {remote_to}",
            f"Call-ID: {call_id}",
            "CSeq: 1 ACK",
        ]
        for route in reversed(routes):
            lines.append(f"Route: {route}")
        lines.append("Content-Length: 0")
        client.send(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))

    def _on_bye(
        self,
        server: SipServer,
        message: object,
        peer: tuple[str, int],
        connection: socket.socket | None,
    ) -> None:
        from as_platform.sip.message import SipMessage

        assert isinstance(message, SipMessage)
        call_id = header(message, "Call-ID") or ""
        with self._lock:
            dialog = self._dialogs.get(call_id)
        if dialog is None:
            server.send(
                peer,
                render_message(simple_response(message, 481, "Call Does Not Exist")),
                connection,
            )
            return
        branch = new_branch()
        via = via_value(self.transport, self.host, dialog.client.local_port, branch)
        lines = [
            f"BYE {dialog.outbound_uri} SIP/2.0",
            f"Via: {via}",
            "Max-Forwards: 70",
            f"From: {dialog.outbound_from}",
            f"To: {dialog.outbound_to}",
            f"Call-ID: {dialog.outbound_call_id}",
            "CSeq: 2 BYE",
            "Content-Length: 0",
        ]
        try:
            dialog.client.send(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
            dialog.client.read_final()
        except (OSError, TimeoutError, ValueError):
            server.send(
                peer,
                render_message(simple_response(message, 504, "Server Time-out")),
                connection,
            )
            return
        server.send(peer, render_message(simple_response(message, 200, "OK")), connection)


def uri_user_uri(contact: str) -> str:
    """Return the SIP URI inside a Contact value."""
    text = contact.strip()
    if "<" in text and ">" in text:
        return text.split("<", 1)[1].split(">", 1)[0]
    return text.split(";", 1)[0].strip()


def _reason(status: int) -> str:
    if status == 200:
        return "OK"
    if status == 404:
        return "Not Found"
    if status == 603:
        return "Decline"
    return "Final"
