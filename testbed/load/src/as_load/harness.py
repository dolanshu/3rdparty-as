"""Real-socket SIP load generation and evidence capture.

The runner is a small UDP UAC for controlled capacity experiments. It sends
INVITE, ACK, and BYE datagrams to a configured SIP endpoint and records each
wire datagram alongside monotonic timestamps. It does not implement a SIP
stack and its loopback tests are not stack-capacity measurements.
"""

from __future__ import annotations

import base64
import bisect
import hashlib
import json
import math
import os
import platform
import resource
import socket
import subprocess
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HARNESS_VERSION = "0.1.0"
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_DATAGRAM_BYTES = 65535
SDP_OFFER = (
    b"v=0\r\n"
    b"o=as-load 1 1 IN IP4 127.0.0.1\r\n"
    b"s=as-load\r\n"
    b"c=IN IP4 127.0.0.1\r\n"
    b"t=0 0\r\n"
    b"m=audio 9 RTP/AVP 0\r\n"
    b"a=rtpmap:0 PCMU/8000\r\n"
)


@dataclass(frozen=True)
class LoadConfig:
    """Inputs that fully describe one load run."""

    host: str
    port: int
    target_cps: float
    duration_seconds: float
    hold_seconds: float
    workers: int
    timeout_seconds: float
    stack_name: str
    stack_version: str
    output_dir: Path

    def __post_init__(self) -> None:
        """Validate run inputs before any socket activity begins."""
        if not self.host:
            raise ValueError("host must not be empty")
        if ":" in self.host:
            # See ADR-0014: fail closed until end-to-end IPv6 wire compatibility is proven.
            raise ValueError("IPv6 targets are not supported by this harness yet")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.target_cps <= 0:
            raise ValueError("target_cps must be greater than zero")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")
        if self.hold_seconds < 0:
            raise ValueError("hold_seconds must not be negative")
        if self.workers < 1:
            raise ValueError("workers must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not self.stack_name.strip():
            raise ValueError("stack_name must identify the target stack")
        if not self.stack_version.strip():
            raise ValueError("stack_version must identify the target version")


class _Evidence:
    """Serialize events and maintain the run's concurrent counters."""

    def __init__(self, stream: Any, origin_ns: int) -> None:
        self._stream = stream
        self._origin_ns = origin_ns
        self._lock = threading.Lock()
        self.attempt_ns: list[int] = []
        self.sent_ns: list[int] = []
        self.invite_sent_ns: list[int] = []
        self.dialog_ack_sent_ns: list[int] = []
        self.established_ns: list[int] = []
        self.latencies_ms: list[float] = []
        self.errors: Counter[str] = Counter()
        self.active_sessions = 0
        self.peak_sessions = 0
        self.unresolved_sessions = 0

    def record(
        self, kind: str, *, attempt_id: str, payload: bytes | None = None, **fields: Any
    ) -> int:
        """Write one event and return its monotonic offset from run start."""
        now_ns = time.perf_counter_ns()
        event: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "offset_seconds": (now_ns - self._origin_ns) / 1_000_000_000,
            "kind": kind,
            "attempt_id": attempt_id,
            **fields,
        }
        if payload is not None:
            event["datagram_base64"] = base64.b64encode(payload).decode("ascii")
        line = json.dumps(event, sort_keys=True) + "\n"
        with self._lock:
            self._stream.write(line)
        return now_ns

    def record_attempt(self, attempt_id: str, scheduled_ns: int) -> None:
        line = (
            json.dumps(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "offset_seconds": (scheduled_ns - self._origin_ns) / 1_000_000_000,
                    "kind": "attempt_scheduled",
                    "attempt_id": attempt_id,
                },
                sort_keys=True,
            )
            + "\n"
        )
        with self._lock:
            self.attempt_ns.append(scheduled_ns)
            self._stream.write(line)

    def record_error(self, attempt_id: str, category: str, detail: str) -> None:
        with self._lock:
            self.errors[category] += 1
        self.record("attempt_failed", attempt_id=attempt_id, category=category, detail=detail)

    def record_established(self, attempt_id: str, latency_ms: float, established_ns: int) -> None:
        with self._lock:
            self.established_ns.append(established_ns)
            self.latencies_ms.append(latency_ms)
            self.active_sessions += 1
            self.peak_sessions = max(self.peak_sessions, self.active_sessions)
        self.record("session_established", attempt_id=attempt_id, latency_ms=latency_ms)

    def record_ended(self, attempt_id: str, reason: str) -> None:
        with self._lock:
            self.active_sessions -= 1
        self.record("session_ended", attempt_id=attempt_id, reason=reason)

    def record_unresolved(self, attempt_id: str, reason: str, *, detail: str) -> None:
        with self._lock:
            self.unresolved_sessions += 1
        self.record("session_end_unconfirmed", attempt_id=attempt_id, reason=reason, detail=detail)

    def record_dialog_ack_sent(self, sent_ns: int) -> None:
        with self._lock:
            self.dialog_ack_sent_ns.append(sent_ns)


class UnsupportedDialogTargetError(ValueError):
    """Raised when dialog routing cannot be safely derived from SIP headers."""


def run_load(config: LoadConfig) -> dict[str, Any]:
    """Run the configured UDP SIP load and write raw and derived evidence.

    Every scheduled call is retained in the event log, including calls dropped
    because the worker limit was reached. A call is counted as established only
    after a correlated 2xx response to INVITE; SIP setup latency ends there.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)
    events_path = config.output_dir / "events.jsonl"
    summary_path = config.output_dir / "summary.json"
    start_utc = datetime.now(timezone.utc)
    start_cpu = _cpu_snapshot()
    origin_ns = time.perf_counter_ns()
    interval_ns = int(1_000_000_000 / config.target_cps)
    planned_attempts = max(1, math.ceil(config.target_cps * config.duration_seconds))
    workers = threading.BoundedSemaphore(config.workers)

    with events_path.open("w", encoding="utf-8") as stream:
        evidence = _Evidence(stream, origin_ns)
        with ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="as-load") as pool:
            for index in range(planned_attempts):
                attempt_id = f"{index + 1:08d}"
                scheduled_ns = origin_ns + index * interval_ns
                remaining = (scheduled_ns - time.perf_counter_ns()) / 1_000_000_000
                if remaining > 0:
                    time.sleep(remaining)
                evidence.record_attempt(attempt_id, scheduled_ns)
                if not workers.acquire(blocking=False):
                    evidence.record_error(
                        attempt_id, "worker_limit", "all configured workers are busy"
                    )
                    continue
                try:
                    # See ADR-0014: capacity evidence must traverse real sockets.
                    pool.submit(_run_call, config, evidence, attempt_id, workers)
                except Exception:
                    workers.release()
                    raise
            injection_end_ns = time.perf_counter_ns()

    end_ns = time.perf_counter_ns()
    end_cpu = _cpu_snapshot()
    summary = _make_summary(
        config=config,
        evidence=evidence,
        start_utc=start_utc,
        origin_ns=origin_ns,
        injection_end_ns=injection_end_ns,
        end_ns=end_ns,
        start_cpu=start_cpu,
        end_cpu=end_cpu,
        planned_attempts=planned_attempts,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _run_call(
    config: LoadConfig,
    evidence: _Evidence,
    attempt_id: str,
    workers: threading.BoundedSemaphore,
) -> None:
    """Run one INVITE / ACK / hold / BYE exchange using a connected UDP socket."""
    call_id = f"{uuid.uuid4()}@as-load"
    local_tag = uuid.uuid4().hex[:16]
    branch = f"z9hG4bK{uuid.uuid4().hex}"
    cseq = 1
    uri_host = f"[{config.host}]" if ":" in config.host else config.host
    request_uri = f"sip:load@{uri_host}:{config.port}"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(config.timeout_seconds)
            client.connect((config.host, config.port))
            local_host, local_port = client.getsockname()[:2]
            local_contact = f"<sip:load@{local_host}:{local_port};transport=udp>"
            via = f"SIP/2.0/UDP {local_host}:{local_port};branch={branch};rport"
            _, request_sent_by = _parse_top_via_value(via)
            from_value = f"<sip:load@localhost>;tag={local_tag}"
            to_value = f"<sip:load@{uri_host}>"
            invite = _request(
                "INVITE",
                request_uri,
                via,
                from_value,
                to_value,
                call_id,
                cseq,
                SDP_OFFER,
                branch=branch,
                contact=local_contact,
            )
            invite_sent_ns = _send(client, invite, evidence, attempt_id, "INVITE")
            final = _wait_for_response(
                client,
                evidence,
                attempt_id,
                call_id,
                "1 INVITE",
                expected_branch=branch,
                expected_sent_by=request_sent_by,
            )
            if final is None:
                evidence.record_error(
                    attempt_id, "timeout_invite", "no final INVITE response before timeout"
                )
                return
            status, response_headers, final_response_ns = final
            if not 200 <= status < 300:
                transaction_ack = _request(
                    "ACK",
                    request_uri,
                    via,
                    from_value,
                    _single_header(response_headers, "to") or to_value,
                    call_id,
                    cseq,
                    b"",
                    branch=branch,
                )
                _send(client, transaction_ack, evidence, attempt_id, "ACK")
                evidence.record_error(
                    attempt_id, f"sip_{status}", f"INVITE final response was {status}"
                )
                return
            latency_ms = (final_response_ns - invite_sent_ns) / 1_000_000
            # See ADR-0014: count establishment at correlated INVITE 2xx reception on the wire.
            evidence.record_established(attempt_id, latency_ms, final_response_ns)
            unresolved_recorded = False

            def mark_unresolved_once(reason: str, detail: str) -> None:
                nonlocal unresolved_recorded
                if unresolved_recorded:
                    return
                evidence.record_unresolved(attempt_id, reason, detail=detail)
                unresolved_recorded = True

            try:
                to_value = _single_header(response_headers, "to") or ""
                contact_value = _single_header(response_headers, "contact")
                if not to_value or contact_value is None:
                    raise UnsupportedDialogTargetError(
                        "2xx INVITE response is missing To or Contact for dialog routing"
                    )
                _require_to_tag(to_value)
                remote_target = _parse_address_uri(contact_value, "Contact")
                route_values = _header_values(response_headers, "record-route")
                # See ADR-0014: preserve explicit route-set handling to keep wire
                # evidence reproducible.
                route_set = tuple(reversed(route_values))
                dialog_uri, dialog_routes, next_hop = _dialog_routing(remote_target, route_set)
                _connect_uri(client, next_hop)
            except (UnsupportedDialogTargetError, ValueError, OSError) as error:
                # See ADR-0014: reject unsupported dialog targets instead of misrouting traffic.
                evidence.record_error(
                    attempt_id,
                    "unsupported_dialog_target",
                    f"{type(error).__name__}: {error}",
                )
                mark_unresolved_once(
                    "unsupported_dialog_target",
                    "dialog end state is unknown because 2xx dialog routing is unsupported",
                )
                return
            try:
                ack = _request(
                    "ACK",
                    dialog_uri,
                    via,
                    from_value,
                    to_value,
                    call_id,
                    cseq,
                    b"",
                    route_set=dialog_routes,
                )
                ack_sent_ns = _send(client, ack, evidence, attempt_id, "ACK")
                evidence.record_dialog_ack_sent(ack_sent_ns)
                deadline = time.perf_counter() + config.hold_seconds
                while (remaining := deadline - time.perf_counter()) > 0:
                    time.sleep(min(remaining, 0.05))

                bye_branch = f"z9hG4bK{uuid.uuid4().hex}"
                bye = _request(
                    "BYE",
                    dialog_uri,
                    via,
                    from_value,
                    to_value,
                    call_id,
                    cseq + 1,
                    b"",
                    branch=bye_branch,
                    route_set=dialog_routes,
                )
                _send(client, bye, evidence, attempt_id, "BYE")
                bye_response = _wait_for_response(
                    client,
                    evidence,
                    attempt_id,
                    call_id,
                    "2 BYE",
                    expected_branch=bye_branch,
                    expected_sent_by=request_sent_by,
                )
            except (OSError, ValueError) as error:
                evidence.record_error(
                    attempt_id,
                    "post_2xx_socket_or_protocol",
                    f"{type(error).__name__}: {error}",
                )
                mark_unresolved_once(
                    "post_2xx_socket_or_protocol",
                    "dialog end state is unknown because post-2xx signaling failed",
                )
                return

            if bye_response is None:
                evidence.record_error(
                    attempt_id, "timeout_bye", "no final BYE response before timeout"
                )
                # See ADR-0014: unresolved dialogs stay active without a correlated BYE 2xx.
                mark_unresolved_once(
                    "bye_timeout",
                    "dialog end state is unknown without a correlated 2xx BYE",
                )
            elif 200 <= bye_response[0] < 300:
                evidence.record_ended(attempt_id, "bye_2xx")
            else:
                evidence.record_error(
                    attempt_id,
                    f"bye_sip_{bye_response[0]}",
                    f"BYE final response was {bye_response[0]}",
                )
                mark_unresolved_once(
                    f"bye_sip_{bye_response[0]}",
                    detail="dialog end state is unknown without a correlated 2xx BYE",
                )
    except (OSError, ValueError) as error:
        evidence.record_error(attempt_id, "socket_or_protocol", f"{type(error).__name__}: {error}")
    finally:
        workers.release()


def _request(
    method: str,
    request_uri: str,
    via: str,
    from_value: str,
    to_value: str,
    call_id: str,
    cseq: int,
    body: bytes,
    *,
    branch: str | None = None,
    contact: str | None = None,
    route_set: tuple[str, ...] = (),
) -> bytes:
    """Build a minimal SIP request; ACK to a 2xx gets a fresh branch."""
    request_branch = branch or f"z9hG4bK{uuid.uuid4().hex}"
    headers = (
        f"{method} {request_uri} SIP/2.0\r\n"
        f"Via: {via.split(';branch=')[0]};branch={request_branch};rport\r\n"
        f"Max-Forwards: 70\r\n"
        f"From: {from_value}\r\n"
        f"To: {to_value}\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: {cseq} {method}\r\n"
        + (f"Contact: {contact}\r\n" if contact is not None else "")
        + "".join(f"Route: {route}\r\n" for route in route_set)
        + "Content-Type: application/sdp\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n"
    ).encode("ascii")
    return headers + body


def _send(
    client: socket.socket,
    payload: bytes,
    evidence: _Evidence,
    attempt_id: str,
    method: str,
) -> int:
    # See ADR-0014: count an attempt only after its datagram reaches the real socket.
    client.send(payload)
    sent_ns = evidence.record(
        "datagram_sent", attempt_id=attempt_id, payload=payload, method=method
    )
    with evidence._lock:
        evidence.sent_ns.append(sent_ns)
        if method == "INVITE":
            evidence.invite_sent_ns.append(sent_ns)
    return sent_ns


def _wait_for_response(
    client: socket.socket,
    evidence: _Evidence,
    attempt_id: str,
    call_id: str,
    expected_cseq: str,
    *,
    expected_branch: str,
    expected_sent_by: tuple[str, int | None],
) -> tuple[int, dict[str, str | list[str]], int] | None:
    """Receive until a matching final response arrives or socket timeout expires."""
    while True:
        try:
            payload = client.recv(MAX_DATAGRAM_BYTES)
        except TimeoutError:
            return None
        received_ns = evidence.record("datagram_received", attempt_id=attempt_id, payload=payload)
        status, headers = _parse_response(payload)
        try:
            actual_branch, actual_sent_by = _top_via_branch_and_sent_by(headers)
        except ValueError as error:
            evidence.record(
                "response_ignored",
                attempt_id=attempt_id,
                status=status,
                reason=f"top Via was missing or malformed: {error}",
            )
            continue
        call_id_value = _single_header(headers, "call-id")
        cseq_value = _single_header(headers, "cseq")
        if actual_branch != expected_branch:
            # See ADR-0014: correlate SIP responses by transaction branch before counting outcomes.
            evidence.record(
                "response_ignored",
                attempt_id=attempt_id,
                status=status,
                reason="Top Via branch did not match current transaction",
                expected_branch=expected_branch,
                actual_branch=actual_branch,
            )
            continue
        if not _sent_by_matches(actual_sent_by, expected_sent_by):
            evidence.record(
                "response_ignored",
                attempt_id=attempt_id,
                status=status,
                reason="Top Via sent-by did not match current transaction",
                expected_sent_by=_sent_by_text(expected_sent_by),
                actual_sent_by=_sent_by_text(actual_sent_by),
            )
            continue
        if (
            call_id_value != call_id
            or cseq_value is None
            or cseq_value.lower() != expected_cseq.lower()
        ):
            evidence.record(
                "response_ignored",
                attempt_id=attempt_id,
                status=status,
                reason="Call-ID or CSeq did not match current transaction",
            )
            continue
        if status < 200:
            evidence.record("provisional_response", attempt_id=attempt_id, status=status)
            continue
        return status, headers, received_ns


def _parse_response(payload: bytes) -> tuple[int, dict[str, str | list[str]]]:
    """Parse status and case-insensitive headers from one SIP response datagram."""
    lines = payload.split(b"\r\n")
    try:
        start_line = lines[0].decode("ascii")
        tokens = start_line.split()
        if len(tokens) < 2 or tokens[0] != "SIP/2.0":
            raise ValueError("response has an invalid status line")
        status = int(tokens[1])
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid SIP response: {error}") from error
    headers: dict[str, str | list[str]] = {}
    compact_map = {
        "c": "content-type",
        "f": "from",
        "i": "call-id",
        "l": "content-length",
        "m": "contact",
        "r": "refer-to",
        "t": "to",
        "v": "via",
    }
    singleton_headers = {"call-id", "cseq", "to", "from"}
    list_headers = {"contact", "record-route", "via"}
    for line in lines[1:]:
        if not line:
            break
        name, separator, value = line.partition(b":")
        if not separator:
            raise ValueError("response has malformed header line")
        try:
            raw_header_name = name.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("response has non-ASCII header name") from error
        header_name = raw_header_name.strip().lower()
        if not header_name:
            raise ValueError("response has empty header name")
        if any(
            not (character.isalnum() or character in "!#$%&'*+-.^_`|~") for character in header_name
        ):
            raise ValueError(f"response has invalid header name: {raw_header_name!r}")
        header_name = compact_map.get(header_name, header_name)
        decoded = value.decode("latin-1").strip()
        if header_name in list_headers:
            values = _split_header_values(decoded)
            previous = headers.setdefault(header_name, [])
            if isinstance(previous, list):
                previous.extend(values)
            continue
        if header_name in singleton_headers and header_name in headers:
            raise ValueError(f"response has duplicate singleton header: {header_name}")
        headers[header_name] = decoded
    return status, headers


def _require_to_tag(to_value: str) -> None:
    if ";" not in to_value:
        raise ValueError("2xx INVITE To header is missing remote tag")
    tag_value: str | None = None
    for item in to_value.split(";")[1:]:
        name, equals, value = item.partition("=")
        if name.strip().lower() != "tag":
            continue
        if not equals:
            break
        candidate = value.strip()
        if not candidate:
            break
        allowed = "-.!%*_+`'~"
        if any(not (character.isalnum() or character in allowed) for character in candidate):
            break
        tag_value = candidate
        break
    if tag_value is None:
        raise ValueError("2xx INVITE To header has a missing or malformed remote tag")


def _single_header(headers: dict[str, str | list[str]], name: str) -> str | None:
    value = headers.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return None


def _header_values(headers: dict[str, str | list[str]], name: str) -> list[str]:
    value = headers.get(name)
    if isinstance(value, str):
        return [value]
    return value or []


def _top_via_branch(headers: dict[str, str | list[str]]) -> str:
    branch, _ = _top_via_branch_and_sent_by(headers)
    return branch


def _top_via_branch_and_sent_by(
    headers: dict[str, str | list[str]],
) -> tuple[str, tuple[str, int | None]]:
    via_values = _header_values(headers, "via")
    if not via_values:
        raise ValueError("top Via header is missing")
    return _parse_top_via_value(via_values[0])


def _parse_top_via_value(top_via: str) -> tuple[str, tuple[str, int | None]]:
    transport_and_sent_by, separator, parameter_text = top_via.partition(";")
    tokens = transport_and_sent_by.strip().split()
    if len(tokens) != 2:
        raise ValueError("top Via transport or sent-by is malformed")
    protocol, sent_by_text = tokens
    if protocol.upper() != "SIP/2.0/UDP":
        raise ValueError("top Via protocol is malformed")
    sent_by = _parse_sent_by(sent_by_text)

    branch: str | None = None
    allowed = "-.!%*_+`'~"
    if not separator:
        raise ValueError("top Via branch parameter is missing")
    for item in parameter_text.split(";"):
        parameter = item.strip()
        if not parameter:
            raise ValueError("top Via has an empty parameter")
        name, equals, value = parameter.partition("=")
        if name.strip().lower() != "branch":
            continue
        if branch is not None:
            raise ValueError("top Via has duplicate branch parameters")
        if not equals:
            raise ValueError("top Via branch parameter is malformed")
        candidate = value.strip()
        if not candidate:
            raise ValueError("top Via branch parameter is empty")
        if any(not (character.isalnum() or character in allowed) for character in candidate):
            raise ValueError("top Via branch parameter is malformed")
        branch = candidate
    if branch is None:
        raise ValueError("top Via branch parameter is missing")
    return branch, sent_by


def _parse_sent_by(value: str) -> tuple[str, int | None]:
    host: str
    port_text: str | None = None
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            raise ValueError("top Via sent-by is malformed")
        host = value[1:closing]
        remainder = value[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise ValueError("top Via sent-by is malformed")
            port_text = remainder[1:]
    else:
        host, separator, tail = value.partition(":")
        if separator:
            if ":" in tail:
                raise ValueError("top Via sent-by is malformed")
            port_text = tail
    host = host.strip().lower()
    if not host:
        raise ValueError("top Via sent-by host is missing")

    port: int | None = None
    if port_text is not None:
        if not port_text:
            raise ValueError("top Via sent-by port is malformed")
        try:
            port = int(port_text)
        except ValueError as error:
            raise ValueError("top Via sent-by port is malformed") from error
        if not 1 <= port <= 65535:
            raise ValueError("top Via sent-by port is out of range")
    return host, port


def _sent_by_matches(actual: tuple[str, int | None], expected: tuple[str, int | None]) -> bool:
    return actual == expected


def _sent_by_text(value: tuple[str, int | None]) -> str:
    host, port = value
    return f"{host}:{port}" if port is not None else host


def _split_header_values(value: str) -> list[str]:
    """Split a SIP name-address list without splitting quoted or bracketed commas."""
    values: list[str] = []
    start = 0
    quoted = False
    escaped = False
    angle_depth = 0
    for index, character in enumerate(value):
        if escaped:
            escaped = False
        elif character == "\\" and quoted:
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif not quoted and character == "<":
            angle_depth += 1
        elif not quoted and character == ">":
            angle_depth -= 1
            if angle_depth < 0:
                raise ValueError("invalid SIP name-address list")
        elif character == "," and not quoted and angle_depth == 0:
            values.append(value[start:index].strip())
            start = index + 1
    if quoted or angle_depth != 0:
        raise ValueError("invalid SIP name-address list")
    values.append(value[start:].strip())
    if any(not item for item in values):
        raise ValueError("empty SIP name-address value")
    return values


def _parse_address_uri(value: str, header_name: str) -> str:
    value = value.strip()
    if "<" in value:
        open_angle = value.find("<")
        close_angle = value.find(">", open_angle + 1)
        if close_angle < 0 or "<" in value[open_angle + 1 : close_angle]:
            raise ValueError(f"invalid {header_name} name-address")
        uri = value[open_angle + 1 : close_angle].strip()
        trailing = value[close_angle + 1 :].strip()
        if trailing and not trailing.startswith(";"):
            raise ValueError(f"invalid parameters after {header_name} URI")
    else:
        if "," in value or " " in value:
            raise ValueError(f"ambiguous {header_name} URI")
        uri = value
    _parse_sip_uri(uri)
    return uri


def _parse_sip_uri(uri: str) -> tuple[str, int, dict[str, str | None]]:
    if not uri.lower().startswith("sip:") or any(character.isspace() for character in uri):
        raise ValueError("only valid SIP/UDP dialog URIs are supported")
    address = uri[4:].split("?", 1)[0]
    authority, separator, parameter_text = address.partition(";")
    host_port = authority.rsplit("@", 1)[-1]
    if host_port.startswith("["):
        closing = host_port.find("]")
        if closing < 0:
            raise ValueError("invalid bracketed IPv6 SIP URI")
        host = host_port[1:closing]
        remainder = host_port[closing + 1 :]
        if remainder and not remainder.startswith(":"):
            raise ValueError("invalid SIP URI port")
        port_text = remainder[1:] if remainder else "5060"
    else:
        if host_port.count(":") > 1:
            raise ValueError("IPv6 SIP URI hosts must be bracketed")
        host, separator_port, port_text = host_port.partition(":")
        if not separator_port:
            port_text = "5060"
    if not host:
        raise ValueError("SIP URI host is empty")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("SIP URI port must be numeric") from error
    if not 1 <= port <= 65535:
        raise ValueError("SIP URI port is out of range")
    parameters: dict[str, str | None] = {}
    if separator:
        for item in parameter_text.split(";"):
            name, equals, parameter_value = item.partition("=")
            if not name:
                raise ValueError("invalid SIP URI parameter")
            parameters[name.lower()] = parameter_value.lower() if equals else None
    if parameters.get("transport") not in (None, "udp"):
        raise ValueError("dialog URI requests an unsupported transport")
    unsupported_parameters = sorted(set(parameters).difference({"transport", "lr"}))
    if unsupported_parameters:
        raise ValueError(
            "dialog URI has unsupported routing parameters: " + ",".join(unsupported_parameters)
        )
    return host, port, parameters


def _dialog_routing(
    remote_target: str, route_set: tuple[str, ...]
) -> tuple[str, tuple[str, ...], str]:
    """Apply RFC dialog routing for the harness's supported SIP/UDP URI subset."""
    _parse_sip_uri(remote_target)
    if not route_set:
        return remote_target, (), remote_target

    validated_route_set = tuple(route_set)
    for route in validated_route_set:
        route_uri = _parse_address_uri(route, "Route")
        _parse_sip_uri(route_uri)

    first_route_uri = _parse_address_uri(validated_route_set[0], "Route")
    _, _, parameters = _parse_sip_uri(first_route_uri)
    if "lr" in parameters:
        return remote_target, validated_route_set, first_route_uri

    strict_routes = (*validated_route_set[1:], f"<{remote_target}>")
    return first_route_uri, strict_routes, first_route_uri


def _connect_uri(client: socket.socket, uri: str) -> None:
    host, port, _ = _parse_sip_uri(uri)
    candidates = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    if not candidates:
        raise OSError(f"no UDP address found for SIP next hop {host}")
    client.connect(candidates[0][4])


def _make_summary(
    *,
    config: LoadConfig,
    evidence: _Evidence,
    start_utc: datetime,
    origin_ns: int,
    injection_end_ns: int,
    end_ns: int,
    start_cpu: dict[str, Any],
    end_cpu: dict[str, Any],
    planned_attempts: int,
) -> dict[str, Any]:
    """Derive counts, latency percentiles, C6 windows, and host metadata."""
    elapsed = max((end_ns - origin_ns) / 1_000_000_000, 0.000001)
    attempted = len(evidence.attempt_ns)
    sent = len(evidence.sent_ns)
    sent_invites = len(evidence.invite_sent_ns)
    established = len(evidence.established_ns)
    coverage_ns = _c6_coverage_ns(config, evidence, origin_ns, injection_end_ns)
    span = coverage_ns / 1_000_000_000
    return {
        "schema_version": 1,
        "measurement": {
            "started_at_utc": start_utc.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "host": config.host,
            "port": config.port,
            "transport": "UDP",
            "target_stack": config.stack_name,
            "target_stack_version": config.stack_version,
            "harness_version": HARNESS_VERSION,
            "git_commit": _git_commit(),
            "source_provenance": _source_provenance(),
            "config": {**asdict(config), "output_dir": str(config.output_dir)},
        },
        "host": {
            "os": platform.platform(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "load_average": _load_average(),
        },
        "counts": {
            "scheduled_attempts": attempted,
            "planned_attempts": planned_attempts,
            "datagrams_sent": sent,
            "invite_datagrams_sent": sent_invites,
            "dialog_acks_sent": len(evidence.dialog_ack_sent_ns),
            "established_sessions": established,
            "worker_limit_drops": evidence.errors["worker_limit"],
            "unresolved_sessions": evidence.unresolved_sessions,
            "final_active_sessions": evidence.active_sessions,
            "peak_established_sessions": evidence.peak_sessions,
        },
        "rates_cps": {
            "scheduled_attempts_per_configured_injection_second": (
                attempted / config.duration_seconds
            ),
            "transmitted_invites_per_configured_injection_second": (
                sent_invites / config.duration_seconds
            ),
            "established_sessions_per_configured_injection_second": (
                established / config.duration_seconds
            ),
            "configured_target": config.target_cps,
            "elapsed_seconds_including_drain": elapsed,
            "injection_duration_seconds": config.duration_seconds,
        },
        "aggregate_rate_method": (
            "rates_cps aggregate rates divide total scheduled/invite/established counts by "
            "configured injection duration; c6_windows are event-time distributions"
        ),
        "setup_latency_ms": _distribution(evidence.latencies_ms),
        "error_distribution": dict(sorted(evidence.errors.items())),
        "c6_window_method": (
            "C6 attempted-call CPS uses successfully transmitted INVITE datagrams; "
            "successful-call CPS uses correlated final 2xx INVITE responses. Scheduled "
            "attempts and worker-limit drops are reported separately. Fixed tumbling "
            "windows are anchored at measurement start; exact sliding windows use "
            "[start, start + width). Coverage is max(configured injection duration, "
            "injection scheduler end offset, latest scheduled/invite/established "
            "event offset). Sliding peaks are reported only when coverage contains "
            "at least one full window of the requested width; zero-duration boundary "
            "buckets are excluded from tumbling CPS distributions."
        ),
        "c6_windows": {
            "measurement_span_seconds": span,
            "1s": _window_series(evidence, origin_ns, coverage_ns, 1.0),
            "100s": _window_series(evidence, origin_ns, coverage_ns, 100.0),
        },
        "load_generator_resources": {
            "user_cpu_seconds": end_cpu["user_cpu_seconds"] - start_cpu["user_cpu_seconds"],
            "system_cpu_seconds": end_cpu["system_cpu_seconds"] - start_cpu["system_cpu_seconds"],
            "max_rss_platform_units": end_cpu["max_rss_platform_units"],
            "open_file_descriptors_at_finish": _open_fd_count(),
        },
        "target_resource_observations": {
            "status": "unavailable",
            "reason": "target-side telemetry is not connected to this harness",
        },
        "evidence_files": {"events": "events.jsonl", "summary": "summary.json"},
    }


def _c6_coverage_ns(
    config: LoadConfig,
    evidence: _Evidence,
    origin_ns: int,
    injection_end_ns: int,
) -> int:
    configured_ns = int(config.duration_seconds * 1_000_000_000)
    scheduler_end_ns = max(0, injection_end_ns - origin_ns)
    event_ns = evidence.attempt_ns + evidence.invite_sent_ns + evidence.established_ns
    # See ADR-0014: derive C6 coverage from scheduled/event offsets,
    # excluding worker-drain idle time.
    latest_offset_ns = max((timestamp - origin_ns for timestamp in event_ns), default=0)
    return max(configured_ns, scheduler_end_ns, latest_offset_ns, 1)


def _window_report(
    event_ns: list[int],
    origin_ns: int,
    coverage_ns: int,
    width: float,
) -> dict[str, Any]:
    """Return every tumbling bucket and exact sliding peak for one event series."""
    width_ns = max(1, int(width * 1_000_000_000))
    window_count = max(1, math.ceil(coverage_ns / width_ns))
    rows: list[dict[str, Any]] = []
    counts = [0] * window_count
    boundary_counts: dict[int, int] = {}
    for timestamp in event_ns:
        offset_ns = max(0, timestamp - origin_ns)
        index = offset_ns // width_ns
        if index < window_count:
            counts[int(index)] += 1
        elif offset_ns == coverage_ns and coverage_ns % width_ns == 0:
            boundary_counts[int(index)] = boundary_counts.get(int(index), 0) + 1
    for index in range(window_count):
        start = index * width
        start_ns = index * width_ns
        actual_ns = min(width_ns, max(coverage_ns - start_ns, 0))
        actual = actual_ns / 1_000_000_000
        count = counts[index]
        rows.append(
            {
                "start_offset_seconds": start,
                "actual_seconds": actual,
                "count": count,
                "cps": count / actual if actual > 0 else None,
            }
        )
    for index in sorted(boundary_counts):
        rows.append(
            {
                "start_offset_seconds": index * width,
                "actual_seconds": 0.0,
                "count": boundary_counts[index],
                "cps": None,
            }
        )
    offsets = sorted((timestamp - origin_ns) / 1e9 for timestamp in event_ns)
    return {
        "width_seconds": width,
        "tumbling_windows": rows,
        "tumbling_cps_distribution": _distribution(
            [float(row["cps"]) for row in rows if row["cps"] is not None]
        ),
        "sliding_peak": _sliding_peak(offsets, width, coverage_ns / 1_000_000_000),
    }


def _window_series(
    evidence: _Evidence, origin_ns: int, coverage_ns: int, width: float
) -> dict[str, dict[str, Any]]:
    return {
        "scheduled_attempts": _window_report(evidence.attempt_ns, origin_ns, coverage_ns, width),
        "transmitted_invites": _window_report(
            evidence.invite_sent_ns, origin_ns, coverage_ns, width
        ),
        "established_sessions": _window_report(
            evidence.established_ns, origin_ns, coverage_ns, width
        ),
    }


def _sliding_peak(
    offsets: list[float], width: float, coverage_seconds: float
) -> dict[str, str | float | int | None]:
    if coverage_seconds < width:
        return {
            "status": "unavailable",
            "reason": "coverage_shorter_than_window",
            "count": None,
            "cps": None,
            "start_offset_seconds": None,
        }

    included_offsets = [value for value in offsets if value < coverage_seconds]
    if not included_offsets:
        return {
            "status": "ok",
            "reason": None,
            "count": 0,
            "cps": 0.0,
            "start_offset_seconds": 0.0,
        }

    max_start = coverage_seconds - width
    best_start = 0.0
    best_count = 0
    last_right = 0
    candidates = sorted(
        {0.0, max_start, *[value for value in included_offsets if value <= max_start]}
    )
    for start in candidates:
        left = bisect.bisect_left(included_offsets, start)
        if last_right < left:
            last_right = left
        while last_right < len(included_offsets) and included_offsets[last_right] < start + width:
            last_right += 1
        count = last_right - left
        if count > best_count:
            best_count = count
            best_start = start

    return {
        "status": "ok",
        "reason": None,
        "count": best_count,
        "cps": best_count / width,
        "start_offset_seconds": best_start,
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)

    def percentile(percent: float) -> float:
        index = max(0, int((percent / 100) * len(ordered) + 0.999999) - 1)
        return ordered[index]

    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": percentile(50),
        "p95": percentile(95),
        "p99": percentile(99),
        "max": ordered[-1],
    }


def _cpu_snapshot() -> dict[str, float | int]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "max_rss_platform_units": usage.ru_maxrss,
    }


def _load_average() -> list[float] | None:
    try:
        return list(os.getloadavg())
    except (AttributeError, OSError):
        return None


def _open_fd_count() -> int | None:
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return None


def _repository_root() -> Path | None:
    source_dir = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
            cwd=source_dir,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    root = result.stdout.strip()
    return Path(root) if root else None


def _git_commit() -> str | None:
    repository = _repository_root()
    if repository is None:
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
            cwd=repository,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _source_provenance() -> dict[str, bool | str | list[str] | None]:
    """Identify the harness source and whether its checkout contains local edits."""
    source_dir = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for source_path in sorted(source_dir.glob("*.py")):
        digest.update(source_path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_path.read_bytes())
        digest.update(b"\0")

    repository = _repository_root()
    if repository is None:
        return {
            "worktree_dirty": None,
            "harness_sources_dirty": None,
            "harness_sources_tracked_dirty": None,
            "harness_sources_untracked": None,
            "harness_sources_status": None,
            "harness_sources_sha256": digest.hexdigest(),
        }
    try:
        source_pathspec = source_dir.relative_to(repository).as_posix()
        worktree_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
            cwd=repository,
        )
        source_result = subprocess.run(
            ["git", "status", "--porcelain", "--", source_pathspec],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
            cwd=repository,
        )
        source_lines = [line for line in source_result.stdout.splitlines() if line.strip()]
        tracked_dirty = any(not line.startswith("??") for line in source_lines)
        has_untracked = any(line.startswith("??") for line in source_lines)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {
            "worktree_dirty": None,
            "harness_sources_dirty": None,
            "harness_sources_tracked_dirty": None,
            "harness_sources_untracked": None,
            "harness_sources_status": None,
            "harness_sources_sha256": digest.hexdigest(),
        }
    return {
        "worktree_dirty": bool(worktree_result.stdout.strip()),
        "harness_sources_dirty": bool(source_lines),
        "harness_sources_tracked_dirty": tracked_dirty,
        "harness_sources_untracked": has_untracked,
        "harness_sources_status": source_lines,
        "harness_sources_sha256": digest.hexdigest(),
    }
