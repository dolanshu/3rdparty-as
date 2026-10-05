"""Real-socket tests for the load generator, not SIP-stack capacity evidence."""

from __future__ import annotations

import io
import json
import socket
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import as_load.harness as harness
from as_load.harness import LoadConfig, _parse_response, _sliding_peak, _window_report, run_load


class LoopbackUas:
    """Scripted UDP UAS used only to verify the harness's wire and accounting."""

    def __init__(
        self,
        final_status: int = 200,
        *,
        suppress_bye_response: bool = False,
        send_wrong_branch_invite_2xx_first: bool = False,
        send_wrong_sent_by_invite_2xx_first: bool = False,
        send_wrong_branch_bye_2xx_only: bool = False,
        send_wrong_sent_by_bye_2xx_only: bool = False,
        bye_final_status: int = 200,
        contact_value: str | None = "<sip:loopback@127.0.0.1:{port};transport=udp>",
        record_route_values: tuple[str, ...] = (),
        use_compact_headers: bool = False,
        add_compact_refer_to: bool = False,
        to_tag_value: str | None = "loopback-uas",
        malformed_bye_response: bytes | None = None,
    ) -> None:
        self._final_status = final_status
        self._suppress_bye_response = suppress_bye_response
        self._send_wrong_branch_invite_2xx_first = send_wrong_branch_invite_2xx_first
        self._send_wrong_sent_by_invite_2xx_first = send_wrong_sent_by_invite_2xx_first
        self._send_wrong_branch_bye_2xx_only = send_wrong_branch_bye_2xx_only
        self._send_wrong_sent_by_bye_2xx_only = send_wrong_sent_by_bye_2xx_only
        self._bye_final_status = bye_final_status
        self._contact_value = contact_value
        self._record_route_values = record_route_values
        self._use_compact_headers = use_compact_headers
        self._add_compact_refer_to = add_compact_refer_to
        self._to_tag_value = to_tag_value
        self._malformed_bye_response = malformed_bye_response
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.settimeout(0.1)
        self.port = int(self._socket.getsockname()[1])
        self.messages: list[bytes] = []
        self._closing = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closing.set()
        self._socket.close()
        self._thread.join(timeout=1)

    def _serve(self) -> None:
        while not self._closing.is_set():
            try:
                message, peer = self._socket.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                return
            self.messages.append(message)
            start_line = message.split(b"\r\n", 1)[0]
            method = start_line.split(b" ", 1)[0]
            headers = _headers(message)
            if method == b"INVITE":
                for status, reason in (
                    (100, b"Trying"),
                    (180, b"Ringing"),
                    (self._final_status, b"Final"),
                ):
                    contact_value = None
                    record_route_values: tuple[str, ...] = ()
                    if status >= 200:
                        contact_value = self._format_value(self._contact_value)
                        record_route_values = tuple(
                            self._format_value(value) for value in self._record_route_values
                        )

                    if status >= 200 and self._send_wrong_branch_invite_2xx_first:
                        self._socket.sendto(
                            _response(
                                status,
                                reason,
                                headers,
                                contact_value=contact_value,
                                record_route_values=record_route_values,
                                use_compact_headers=self._use_compact_headers,
                                add_compact_refer_to=self._add_compact_refer_to,
                                to_tag_value=self._to_tag_value,
                                via_value=_with_via_branch(
                                    headers["via"], "z9hG4bK-loopback-wrong-invite"
                                ),
                            ),
                            peer,
                        )
                        self._socket.sendto(
                            _response(
                                status,
                                reason,
                                headers,
                                contact_value=contact_value,
                                record_route_values=record_route_values,
                                use_compact_headers=self._use_compact_headers,
                                add_compact_refer_to=self._add_compact_refer_to,
                                to_tag_value=self._to_tag_value,
                            ),
                            peer,
                        )
                        break
                    if status >= 200 and self._send_wrong_sent_by_invite_2xx_first:
                        self._socket.sendto(
                            _response(
                                status,
                                reason,
                                headers,
                                contact_value=contact_value,
                                record_route_values=record_route_values,
                                use_compact_headers=self._use_compact_headers,
                                add_compact_refer_to=self._add_compact_refer_to,
                                to_tag_value=self._to_tag_value,
                                via_value=_with_via_sent_by(headers["via"], "forged.invalid:5099"),
                            ),
                            peer,
                        )
                        self._socket.sendto(
                            _response(
                                status,
                                reason,
                                headers,
                                contact_value=contact_value,
                                record_route_values=record_route_values,
                                use_compact_headers=self._use_compact_headers,
                                add_compact_refer_to=self._add_compact_refer_to,
                                to_tag_value=self._to_tag_value,
                            ),
                            peer,
                        )
                        break
                    self._socket.sendto(
                        _response(
                            status,
                            reason,
                            headers,
                            contact_value=contact_value,
                            record_route_values=record_route_values,
                            use_compact_headers=self._use_compact_headers,
                            add_compact_refer_to=self._add_compact_refer_to,
                            to_tag_value=self._to_tag_value,
                        ),
                        peer,
                    )
                    if status >= 200:
                        break
            elif method == b"BYE":
                if self._send_wrong_branch_bye_2xx_only:
                    self._socket.sendto(
                        _response(
                            200,
                            b"OK",
                            headers,
                            via_value=_with_via_branch(
                                headers["via"], "z9hG4bK-loopback-wrong-bye"
                            ),
                        ),
                        peer,
                    )
                    continue
                if self._send_wrong_sent_by_bye_2xx_only:
                    self._socket.sendto(
                        _response(
                            200,
                            b"OK",
                            headers,
                            via_value=_with_via_sent_by(headers["via"], "forged.invalid:5099"),
                        ),
                        peer,
                    )
                    continue
                if self._suppress_bye_response:
                    continue
                if self._malformed_bye_response is not None:
                    self._socket.sendto(self._malformed_bye_response, peer)
                    continue
                reason = b"OK" if self._bye_final_status == 200 else b"Final"
                self._socket.sendto(_response(self._bye_final_status, reason, headers), peer)

    def _format_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        return value.format(port=self.port)


def _headers(message: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in message.split(b"\r\n")[1:]:
        if not line:
            break
        name, separator, value = line.partition(b":")
        if separator:
            result[name.decode("ascii").lower()] = value.decode("latin-1").strip()
    return result


def _response(
    status: int,
    reason: bytes,
    headers: dict[str, str],
    *,
    via_value: str | None = None,
    contact_value: str | None = None,
    record_route_values: tuple[str, ...] = (),
    use_compact_headers: bool = False,
    add_compact_refer_to: bool = False,
    to_tag_value: str | None = "loopback-uas",
) -> bytes:
    to_value = headers["to"]
    if status >= 180 and ";tag=" not in to_value and to_tag_value is not None:
        to_value += f";tag={to_tag_value}"
    via_name = "v" if use_compact_headers else "Via"
    from_name = "f" if use_compact_headers else "From"
    to_name = "t" if use_compact_headers else "To"
    call_id_name = "i" if use_compact_headers else "Call-ID"
    contact_name = "m" if use_compact_headers else "Contact"
    content_length_name = "l" if use_compact_headers else "Content-Length"
    response_headers = [
        f"SIP/2.0 {status} ".encode("ascii") + reason,
        f"{via_name}: {via_value or headers['via']}".encode("latin-1"),
        f"{from_name}: {headers['from']}".encode("latin-1"),
        f"{to_name}: {to_value}".encode("latin-1"),
        f"{call_id_name}: {headers['call-id']}".encode("latin-1"),
        f"CSeq: {headers['cseq']}".encode("latin-1"),
    ]
    response_headers.extend(
        f"Record-Route: {value}".encode("latin-1") for value in record_route_values
    )
    if contact_value is not None:
        response_headers.append(f"{contact_name}: {contact_value}".encode("latin-1"))
    if add_compact_refer_to:
        response_headers.append(b"r: <sip:refer-target@example.com>")
    response_headers.append(f"{content_length_name}: 0".encode("latin-1"))
    response_headers.append(b"")
    response_headers.append(b"")
    response_headers = b"\r\n".join(response_headers)
    return response_headers


def _request_uri(message: bytes) -> str:
    line = message.split(b"\r\n", 1)[0].decode("ascii")
    return line.split(" ")[1]


def _header_values(message: bytes, name: str) -> list[str]:
    wanted = name.lower().encode("ascii") + b":"
    values: list[str] = []
    for line in message.split(b"\r\n")[1:]:
        if not line:
            break
        if line.lower().startswith(wanted):
            values.append(line.split(b":", 1)[1].decode("latin-1").strip())
    return values


def _header_parameter(value: str, name: str) -> str | None:
    for item in value.split(";")[1:]:
        parameter, _, parameter_value = item.partition("=")
        if parameter.strip().lower() == name.lower():
            return parameter_value.strip() or None
    return None


def _with_via_branch(via_value: str, branch: str) -> str:
    parts = via_value.split(";")
    rebuilt = [parts[0]]
    replaced = False
    for parameter in parts[1:]:
        name, equals, _ = parameter.partition("=")
        if equals and name.strip().lower() == "branch":
            rebuilt.append(f"branch={branch}")
            replaced = True
        else:
            rebuilt.append(parameter)
    if not replaced:
        rebuilt.append(f"branch={branch}")
    return ";".join(rebuilt)


def _with_via_sent_by(via_value: str, sent_by: str) -> str:
    transport_and_sent_by, separator, parameter_text = via_value.partition(";")
    tokens = transport_and_sent_by.split()
    if len(tokens) < 1:
        return via_value
    rewritten = f"{tokens[0]} {sent_by}"
    if not separator:
        return rewritten
    return f"{rewritten};{parameter_text}"


@pytest.mark.integration
def test_load_run_captures_real_udp_invite_ack_bye_and_metrics(tmp_path: Path) -> None:
    uas = LoopbackUas()
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=2,
                duration_seconds=1,
                hold_seconds=0,
                workers=2,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["scheduled_attempts"] == 2
    assert summary["counts"]["dialog_acks_sent"] == 2
    assert summary["counts"]["established_sessions"] == 2
    assert summary["counts"]["unresolved_sessions"] == 0
    assert summary["counts"]["final_active_sessions"] == 0
    assert summary["counts"]["peak_established_sessions"] >= 1
    assert summary["setup_latency_ms"]["count"] == 2
    assert summary["c6_windows"]["1s"]["transmitted_invites"]["sliding_peak"]["status"] == "ok"
    assert summary["c6_windows"]["1s"]["transmitted_invites"]["sliding_peak"]["count"] == 2
    assert (
        summary["c6_windows"]["100s"]["established_sessions"]["sliding_peak"]["status"]
        == "unavailable"
    )
    assert summary["target_resource_observations"]["status"] == "unavailable"
    methods = [message.split(b" ", 1)[0] for message in uas.messages]
    assert methods.count(b"INVITE") == 2
    assert methods.count(b"ACK") == 2
    assert methods.count(b"BYE") == 2

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    sent = [event for event in raw_events if event["kind"] == "datagram_sent"]
    assert {event["method"] for event in sent} == {"INVITE", "ACK", "BYE"}
    assert all(event["datagram_base64"] for event in sent)
    assert json.loads((tmp_path / "summary.json").read_text()) == summary


@pytest.mark.integration
def test_bye_timeout_keeps_established_session_active_and_unresolved(tmp_path: Path) -> None:
    uas = LoopbackUas(suppress_bye_response=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.2,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"timeout_bye": 1}


@pytest.mark.integration
def test_wrong_branch_invite_2xx_is_ignored_until_matching_branch_arrives(tmp_path: Path) -> None:
    uas = LoopbackUas(send_wrong_branch_invite_2xx_first=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 0
    assert summary["counts"]["final_active_sessions"] == 0

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    ignored = [event for event in raw_events if event["kind"] == "response_ignored"]
    assert any(
        event["reason"] == "Top Via branch did not match current transaction"
        and event["status"] == 200
        for event in ignored
    )


@pytest.mark.integration
def test_wrong_sent_by_invite_2xx_is_ignored_until_matching_sent_by_arrives(tmp_path: Path) -> None:
    uas = LoopbackUas(send_wrong_sent_by_invite_2xx_first=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 0
    assert summary["counts"]["final_active_sessions"] == 0

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    ignored = [event for event in raw_events if event["kind"] == "response_ignored"]
    assert any(
        event["reason"] == "Top Via sent-by did not match current transaction"
        and event["status"] == 200
        for event in ignored
    )


@pytest.mark.integration
def test_wrong_branch_bye_2xx_is_ignored_and_session_stays_active_after_timeout(
    tmp_path: Path,
) -> None:
    uas = LoopbackUas(send_wrong_branch_bye_2xx_only=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.2,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"timeout_bye": 1}

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    ignored = [event for event in raw_events if event["kind"] == "response_ignored"]
    assert any(
        event["reason"] == "Top Via branch did not match current transaction"
        and event["status"] == 200
        for event in ignored
    )


@pytest.mark.integration
def test_wrong_sent_by_bye_2xx_is_ignored_and_session_stays_active_after_timeout(
    tmp_path: Path,
) -> None:
    uas = LoopbackUas(send_wrong_sent_by_bye_2xx_only=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.2,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"timeout_bye": 1}

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    ignored = [event for event in raw_events if event["kind"] == "response_ignored"]
    assert any(
        event["reason"] == "Top Via sent-by did not match current transaction"
        and event["status"] == 200
        for event in ignored
    )


@pytest.mark.integration
def test_non_2xx_bye_keeps_established_session_active_and_unresolved(tmp_path: Path) -> None:
    uas = LoopbackUas(bye_final_status=481)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"bye_sip_481": 1}


@pytest.mark.integration
def test_non_2xx_invite_sends_transaction_ack_with_original_branch(tmp_path: Path) -> None:
    uas = LoopbackUas(final_status=486)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["planned_attempts"] == 1
    assert summary["counts"]["established_sessions"] == 0
    assert summary["error_distribution"] == {"sip_486": 1}
    methods = [message.split(b" ", 1)[0] for message in uas.messages]
    assert methods.count(b"INVITE") == 1
    assert methods.count(b"ACK") == 1
    invite = next(message for message in uas.messages if message.startswith(b"INVITE "))
    ack = next(message for message in uas.messages if message.startswith(b"ACK "))
    invite_via = _headers(invite)["via"]
    ack_via = _headers(ack)["via"]
    assert _header_parameter(invite_via, "branch") == _header_parameter(ack_via, "branch")


@pytest.mark.integration
def test_2xx_dialog_ack_and_bye_use_contact_and_reversed_loose_route_set(tmp_path: Path) -> None:
    uas = LoopbackUas(
        record_route_values=(
            "<sip:edge-a@127.0.0.1:{port};lr>",
            "<sip:edge-b@127.0.0.1:{port};lr>",
        )
    )
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    ack = next(message for message in uas.messages if message.startswith(b"ACK "))
    bye = next(message for message in uas.messages if message.startswith(b"BYE "))
    expected_remote_target = f"sip:loopback@127.0.0.1:{uas.port};transport=udp"
    assert _request_uri(ack) == expected_remote_target
    assert _request_uri(bye) == expected_remote_target
    expected_routes = [
        f"<sip:edge-b@127.0.0.1:{uas.port};lr>",
        f"<sip:edge-a@127.0.0.1:{uas.port};lr>",
    ]
    assert _header_values(ack, "Route") == expected_routes
    assert _header_values(bye, "Route") == expected_routes


@pytest.mark.integration
def test_2xx_dialog_ack_and_bye_apply_strict_route_rewrite(tmp_path: Path) -> None:
    uas = LoopbackUas(record_route_values=("<sip:strict-edge@127.0.0.1:{port}>",))
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    ack = next(message for message in uas.messages if message.startswith(b"ACK "))
    bye = next(message for message in uas.messages if message.startswith(b"BYE "))
    strict_uri = f"sip:strict-edge@127.0.0.1:{uas.port}"
    remote_target_route = f"<sip:loopback@127.0.0.1:{uas.port};transport=udp>"
    assert _request_uri(ack) == strict_uri
    assert _request_uri(bye) == strict_uri
    assert _header_values(ack, "Route") == [remote_target_route]
    assert _header_values(bye, "Route") == [remote_target_route]


@pytest.mark.integration
def test_malformed_contact_after_2xx_is_counted_as_unresolved(tmp_path: Path) -> None:
    uas = LoopbackUas(contact_value="not-a-sip-uri")
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"unsupported_dialog_target": 1}


@pytest.mark.integration
def test_worker_limit_drops_do_not_inflate_actual_invite_cps(tmp_path: Path) -> None:
    uas = LoopbackUas()
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=20,
                duration_seconds=0.2,
                hold_seconds=0.3,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    counts = summary["counts"]
    rates = summary["rates_cps"]
    assert counts["scheduled_attempts"] == 4
    assert counts["worker_limit_drops"] >= 1
    assert counts["invite_datagrams_sent"] < counts["scheduled_attempts"]
    assert counts["datagrams_sent"] > counts["invite_datagrams_sent"]
    assert rates["transmitted_invites_per_configured_injection_second"] == pytest.approx(
        counts["invite_datagrams_sent"] / 0.2
    )
    assert rates["scheduled_attempts_per_configured_injection_second"] == pytest.approx(
        counts["scheduled_attempts"] / 0.2
    )
    assert (
        rates["transmitted_invites_per_configured_injection_second"]
        < rates["scheduled_attempts_per_configured_injection_second"]
    )
    assert "configured injection duration" in summary["aggregate_rate_method"]

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    scheduled = [event for event in raw_events if event["kind"] == "attempt_scheduled"]
    sent_invites = [
        event
        for event in raw_events
        if event["kind"] == "datagram_sent" and event.get("method") == "INVITE"
    ]
    assert len(scheduled) == counts["scheduled_attempts"]
    assert len(sent_invites) == counts["invite_datagrams_sent"]


@pytest.mark.unit
def test_response_parser_rejects_invalid_start_line() -> None:
    with pytest.raises(ValueError, match="invalid SIP response"):
        _parse_response(b"not SIP\r\n\r\n")


@pytest.mark.unit
def test_response_parser_rejects_malformed_header_line() -> None:
    with pytest.raises(ValueError, match="malformed header line"):
        _parse_response(b"SIP/2.0 200 OK\r\nCall-ID abc\r\n\r\n")


@pytest.mark.unit
def test_response_parser_rejects_non_ascii_header_name() -> None:
    with pytest.raises(ValueError, match="non-ASCII header name"):
        _parse_response(b"SIP/2.0 200 OK\r\n\xff: value\r\n\r\n")


@pytest.mark.parametrize(
    "header_block, expected",
    [
        (b"Call-ID: first\r\nCall-ID: second\r\n", "call-id"),
        (b"To: <sip:b@localhost>;tag=b\r\nTo: <sip:c@localhost>;tag=c\r\n", "to"),
        (b"CSeq: 1 INVITE\r\nCSeq: 2 INVITE\r\n", "cseq"),
    ],
)
@pytest.mark.unit
def test_response_parser_rejects_duplicate_singleton_headers(
    header_block: bytes, expected: str
) -> None:
    with pytest.raises(ValueError, match=rf"duplicate singleton header: {expected}"):
        _parse_response(b"SIP/2.0 200 OK\r\n" + header_block + b"\r\n")


@pytest.mark.unit
def test_response_parser_compact_headers_map_call_id_without_record_route_alias() -> None:
    status, headers = _parse_response(
        b"SIP/2.0 200 OK\r\n"
        b"v: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bKx\r\n"
        b"f: <sip:a@localhost>;tag=a\r\n"
        b"t: <sip:b@localhost>;tag=b\r\n"
        b"i: compact-call-id\r\n"
        b"CSeq: 1 INVITE\r\n"
        b"r: <sip:refer-target@example.com>\r\n"
        b"m: <sip:b@127.0.0.1:5060;transport=udp>\r\n"
        b"l: 0\r\n\r\n"
    )
    assert status == 200
    assert headers["call-id"] == "compact-call-id"
    assert "record-route" not in headers
    assert headers["refer-to"] == "<sip:refer-target@example.com>"


@pytest.mark.unit
def test_response_parser_allows_multiple_route_related_list_headers() -> None:
    status, headers = _parse_response(
        b"SIP/2.0 200 OK\r\n"
        b"Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK1\r\n"
        b"Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK2\r\n"
        b"Record-Route: <sip:edge-a@127.0.0.1:5070;lr>\r\n"
        b"Record-Route: <sip:edge-b@127.0.0.1:5071;lr>\r\n"
        b"Call-ID: test\r\n"
        b"From: <sip:a@localhost>;tag=a\r\n"
        b"To: <sip:b@localhost>;tag=b\r\n"
        b"CSeq: 1 INVITE\r\n\r\n"
    )

    assert status == 200
    assert headers["via"] == [
        "SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK1",
        "SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK2",
    ]
    assert headers["record-route"] == [
        "<sip:edge-a@127.0.0.1:5070;lr>",
        "<sip:edge-b@127.0.0.1:5071;lr>",
    ]


@pytest.mark.unit
def test_top_via_branch_parser_rejects_missing_branch_parameter() -> None:
    _, headers = _parse_response(
        b"SIP/2.0 200 OK\r\n"
        b"Via: SIP/2.0/UDP 127.0.0.1:5060;rport\r\n"
        b"Call-ID: test\r\n"
        b"From: <sip:a@localhost>;tag=a\r\n"
        b"To: <sip:b@localhost>;tag=b\r\n"
        b"CSeq: 1 INVITE\r\n\r\n"
    )
    with pytest.raises(ValueError, match="branch parameter is missing"):
        harness._top_via_branch(headers)


@pytest.mark.unit
def test_top_via_branch_parser_rejects_duplicate_branch_parameters() -> None:
    _, headers = _parse_response(
        b"SIP/2.0 200 OK\r\n"
        b"v: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK1;branch=z9hG4bK2\r\n"
        b"i: test\r\n"
        b"f: <sip:a@localhost>;tag=a\r\n"
        b"t: <sip:b@localhost>;tag=b\r\n"
        b"CSeq: 1 INVITE\r\n\r\n"
    )
    with pytest.raises(ValueError, match="duplicate branch"):
        harness._top_via_branch(headers)


@pytest.mark.unit
def test_top_via_parser_rejects_malformed_protocol() -> None:
    _, headers = _parse_response(
        b"SIP/2.0 200 OK\r\n"
        b"Via: SIP/3.0/UDP 127.0.0.1:5060;branch=z9hG4bK1\r\n"
        b"Call-ID: test\r\n"
        b"From: <sip:a@localhost>;tag=a\r\n"
        b"To: <sip:b@localhost>;tag=b\r\n"
        b"CSeq: 1 INVITE\r\n\r\n"
    )
    with pytest.raises(ValueError, match="protocol is malformed"):
        harness._top_via_branch(headers)


@pytest.mark.unit
def test_top_via_parser_rejects_missing_sent_by_host() -> None:
    _, headers = _parse_response(
        b"SIP/2.0 200 OK\r\n"
        b"Via: SIP/2.0/UDP :5060;branch=z9hG4bK1\r\n"
        b"Call-ID: test\r\n"
        b"From: <sip:a@localhost>;tag=a\r\n"
        b"To: <sip:b@localhost>;tag=b\r\n"
        b"CSeq: 1 INVITE\r\n\r\n"
    )
    with pytest.raises(ValueError, match="sent-by host is missing"):
        harness._top_via_branch(headers)


@pytest.mark.integration
def test_compact_call_id_2xx_response_is_correlated_and_establishes(tmp_path: Path) -> None:
    uas = LoopbackUas(use_compact_headers=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 0


@pytest.mark.integration
def test_compact_refer_to_r_header_does_not_add_dialog_routes(tmp_path: Path) -> None:
    uas = LoopbackUas(add_compact_refer_to=True)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 0
    ack = next(message for message in uas.messages if message.startswith(b"ACK "))
    assert _header_values(ack, "Route") == []


@pytest.mark.integration
def test_2xx_without_remote_to_tag_is_rejected(tmp_path: Path) -> None:
    uas = LoopbackUas(to_tag_value=None)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"unsupported_dialog_target": 1}


@pytest.mark.integration
def test_2xx_with_malformed_remote_to_tag_is_rejected(tmp_path: Path) -> None:
    uas = LoopbackUas(to_tag_value="bad tag")
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"unsupported_dialog_target": 1}


@pytest.mark.integration
def test_route_set_rejects_unsupported_uri_parameter_anywhere_in_chain(tmp_path: Path) -> None:
    uas = LoopbackUas(
        record_route_values=(
            "<sip:edge-a@127.0.0.1:{port};lr>",
            "<sip:edge-b@127.0.0.1:{port};maddr=239.1.1.1>",
        )
    )
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"unsupported_dialog_target": 1}


@pytest.mark.integration
def test_post_2xx_ack_send_failure_is_counted_once_as_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uas = LoopbackUas()
    real_send = harness._send

    def failing_send(
        client: socket.socket,
        payload: bytes,
        evidence: harness._Evidence,
        attempt_id: str,
        method: str,
    ) -> int:
        if method == "ACK":
            raise OSError("simulated ACK send failure")
        return real_send(client, payload, evidence, attempt_id, method)

    monkeypatch.setattr(harness, "_send", failing_send)
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["dialog_acks_sent"] == 0
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"post_2xx_socket_or_protocol": 1}


@pytest.mark.integration
def test_post_2xx_malformed_bye_response_is_counted_once_as_unresolved(tmp_path: Path) -> None:
    uas = LoopbackUas(malformed_bye_response=b"malformed\r\n\r\n")
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    assert summary["counts"]["established_sessions"] == 1
    assert summary["counts"]["unresolved_sessions"] == 1
    assert summary["counts"]["final_active_sessions"] == 1
    assert summary["error_distribution"] == {"post_2xx_socket_or_protocol": 1}


@pytest.mark.unit
def test_window_report_one_event_uses_nonzero_bucket_duration() -> None:
    origin_ns = 1_000_000_000
    report = _window_report([origin_ns], origin_ns, 1_000_000_000, 1.0)
    first = report["tumbling_windows"][0]
    assert first["actual_seconds"] == pytest.approx(1.0)
    assert first["count"] == 1
    assert first["cps"] == pytest.approx(1.0)


@pytest.mark.unit
def test_window_report_exact_boundary_event_falls_in_next_half_open_bucket() -> None:
    origin_ns = 1_000_000_000
    report = _window_report([origin_ns + 1_000_000_000], origin_ns, 2_000_000_000, 1.0)
    counts = [row["count"] for row in report["tumbling_windows"]]
    assert counts == [0, 1]


@pytest.mark.unit
def test_c6_coverage_uses_observed_end_without_artificial_1ns_tail() -> None:
    origin_ns = 1_000_000_000
    evidence = harness._Evidence(io.StringIO(), origin_ns)
    evidence.invite_sent_ns.append(origin_ns + 1_000_000_000)
    coverage_ns = harness._c6_coverage_ns(
        LoadConfig(
            host="127.0.0.1",
            port=5060,
            target_cps=1,
            duration_seconds=1,
            hold_seconds=0,
            workers=1,
            timeout_seconds=0.5,
            stack_name="scripted-loopback-peer",
            stack_version="test-only",
            output_dir=Path("."),
        ),
        evidence,
        origin_ns,
        origin_ns + 1_250_000_000,
    )
    report = _window_report([origin_ns + 1_000_000_000], origin_ns, coverage_ns, 1.0)
    rows = report["tumbling_windows"]
    assert [row["count"] for row in rows] == [0, 1]
    assert rows[1]["actual_seconds"] == pytest.approx(0.25)
    assert rows[1]["actual_seconds"] > 0.001


@pytest.mark.integration
def test_setup_latency_uses_final_2xx_receive_timestamp(tmp_path: Path) -> None:
    uas = LoopbackUas()
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=uas.port,
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=0.5,
                stack_name="scripted-loopback-peer",
                stack_version="test-only",
                output_dir=tmp_path,
            )
        )
    finally:
        uas.close()

    raw_events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    invite_sent = next(
        event
        for event in raw_events
        if event["kind"] == "datagram_sent" and event.get("method") == "INVITE"
    )
    final_received = next(
        event
        for event in raw_events
        if event["kind"] == "datagram_received" and _parse_response(socket_base64(event))[0] == 200
    )
    expected_latency = (final_received["offset_seconds"] - invite_sent["offset_seconds"]) * 1000
    assert summary["setup_latency_ms"]["count"] == 1
    assert summary["setup_latency_ms"]["p50"] == pytest.approx(expected_latency, abs=5.0)


def socket_base64(event: dict[str, object]) -> bytes:
    import base64

    return base64.b64decode(str(event["datagram_base64"]))


@pytest.mark.unit
def test_git_commit_uses_repository_root_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path | None]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        cwd_value = kwargs.get("cwd")
        calls.append((" ".join(command), cwd_value if isinstance(cwd_value, Path) else None))
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(stdout="/tmp/repo\n")
        if command == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="abc123\n")
        raise AssertionError(f"unexpected git command {command}")

    monkeypatch.setattr(harness.subprocess, "run", fake_run)

    assert harness._git_commit() == "abc123"
    assert calls[0] == (
        "git rev-parse --show-toplevel",
        Path(harness.__file__).resolve().parent,
    )
    assert calls[1] == ("git rev-parse HEAD", Path("/tmp/repo"))


@pytest.mark.unit
def test_source_provenance_distinguishes_tracked_and_untracked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(harness.__file__).resolve().parents[4]

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(stdout=f"{repo_root}\n")
        if command == ["git", "status", "--porcelain"]:
            return SimpleNamespace(stdout=" M docs/plan.md\n")
        if command == ["git", "status", "--porcelain", "--", "testbed/load/src/as_load"]:
            return SimpleNamespace(
                stdout=(
                    " M testbed/load/src/as_load/harness.py\n?? testbed/load/src/as_load/new.py\n"
                )
            )
        raise AssertionError(f"unexpected git command {command}")

    monkeypatch.setattr(harness.subprocess, "run", fake_run)

    result = harness._source_provenance()
    assert result["worktree_dirty"] is True
    assert result["harness_sources_dirty"] is True
    assert result["harness_sources_tracked_dirty"] is True
    assert result["harness_sources_untracked"] is True
    assert result["harness_sources_status"] == [
        " M testbed/load/src/as_load/harness.py",
        "?? testbed/load/src/as_load/new.py",
    ]


@pytest.mark.unit
def test_ipv6_host_is_rejected_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IPv6 targets are not supported"):
        LoadConfig(
            host="::1",
            port=5060,
            target_cps=1,
            duration_seconds=1,
            hold_seconds=0,
            workers=1,
            timeout_seconds=0.5,
            stack_name="scripted-loopback-peer",
            stack_version="test-only",
            output_dir=tmp_path,
        )


@pytest.mark.unit
def test_sliding_peak_uses_half_open_windows() -> None:
    peak = _sliding_peak([0.0, 0.5, 1.0, 1.5], 1.0, 2.0)
    assert peak == {
        "status": "ok",
        "reason": None,
        "count": 2,
        "cps": 2.0,
        "start_offset_seconds": 0.0,
    }


@pytest.mark.unit
def test_sliding_peak_is_unavailable_when_coverage_is_shorter_than_window() -> None:
    one_second = _window_report([100_000_000], 0, 100_000_000, 1.0)
    hundred_seconds = _window_report([100_000_000], 0, 100_000_000, 100.0)

    assert one_second["sliding_peak"] == {
        "status": "unavailable",
        "reason": "coverage_shorter_than_window",
        "count": None,
        "cps": None,
        "start_offset_seconds": None,
    }
    assert hundred_seconds["sliding_peak"] == {
        "status": "unavailable",
        "reason": "coverage_shorter_than_window",
        "count": None,
        "cps": None,
        "start_offset_seconds": None,
    }


@pytest.mark.unit
def test_sliding_peak_is_valid_for_full_100s_coverage() -> None:
    peak = _sliding_peak([0.0, 50.0, 99.999, 100.0], 100.0, 100.0)
    assert peak == {
        "status": "ok",
        "reason": None,
        "count": 3,
        "cps": 0.03,
        "start_offset_seconds": 0.0,
    }


@pytest.mark.unit
def test_sliding_peak_considers_last_full_window_before_coverage_end() -> None:
    peak = _sliding_peak([7.0], 5.0, 10.0)
    assert peak == {
        "status": "ok",
        "reason": None,
        "count": 1,
        "cps": 0.2,
        "start_offset_seconds": 5.0,
    }


@pytest.mark.unit
def test_window_report_coverage_boundary_event_uses_zero_duration_bucket_without_cps() -> None:
    origin_ns = 1_000_000_000
    report = _window_report([origin_ns + 1_000_000_000], origin_ns, 1_000_000_000, 1.0)
    rows = report["tumbling_windows"]

    assert rows[0] == {
        "start_offset_seconds": 0.0,
        "actual_seconds": pytest.approx(1.0),
        "count": 0,
        "cps": 0.0,
    }
    assert rows[1] == {
        "start_offset_seconds": 1.0,
        "actual_seconds": 0.0,
        "count": 1,
        "cps": None,
    }
    assert report["tumbling_cps_distribution"]["count"] == 1


@pytest.mark.unit
def test_run_load_c6_coverage_excludes_worker_drain_idle_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_call(
        config: LoadConfig,
        evidence: harness._Evidence,
        attempt_id: str,
        workers: threading.BoundedSemaphore,
    ) -> None:
        del config, evidence, attempt_id
        try:
            harness.time.sleep(0.25)
        finally:
            workers.release()

    monkeypatch.setattr(harness, "_run_call", fake_run_call)
    summary = run_load(
        LoadConfig(
            host="127.0.0.1",
            port=5060,
            target_cps=1,
            duration_seconds=0.1,
            hold_seconds=0,
            workers=1,
            timeout_seconds=0.1,
            stack_name="scripted-loopback-peer",
            stack_version="test-only",
            output_dir=tmp_path,
        )
    )

    assert summary["rates_cps"]["elapsed_seconds_including_drain"] >= 0.2
    assert summary["c6_windows"]["measurement_span_seconds"] == pytest.approx(0.1, abs=0.02)
