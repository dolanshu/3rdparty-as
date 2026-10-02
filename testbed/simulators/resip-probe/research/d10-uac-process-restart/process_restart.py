#!/usr/bin/env python3
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MESSAGES = ROOT / "messages"
LOGS = ROOT / "logs"
PROCESSES = ROOT / "processes"
STATE_PATH = ROOT / "state.json"
REMOTE_TAG = "uas-process-restart-stable-tag"
BUSINESS_CONTEXT_KEY = "as-call-process-restart-2026-09-30"
ANSWER_SDP = (
    "v=0\r\n"
    "o=- 5001 2 IN IP4 127.0.0.1\r\n"
    "s=DUM process restart peer\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 49172 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
).encode("ascii")


class ProbeFailure(RuntimeError):
    pass


class Recorder:
    def __init__(self):
        self.sequence = 0
        self.events_path = ROOT / "wire-events.jsonl"
        self.events_path.write_text("", encoding="utf-8")

    def record(self, phase, direction, packet, address):
        self.sequence += 1
        first_line = packet.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        if first_line.startswith("SIP/2.0 "):
            label = "response-" + first_line.split(" ", 2)[1]
        else:
            label = first_line.split(" ", 1)[0].lower() if first_line else "empty"
        label = re.sub(r"[^a-zA-Z0-9-]", "_", label)
        filename = f"{phase}-{self.sequence:03d}-{direction}-{label}.sip"
        path = MESSAGES / filename
        path.write_bytes(packet)
        event = {
            "sequence": self.sequence,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "phase": phase,
            "direction": direction,
            "address": list(address) if address else None,
            "size": len(packet),
            "first_line": first_line,
            "path": str(path.relative_to(ROOT)),
        }
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def parse_sip(packet):
    text = packet.decode("utf-8", errors="replace")
    head, separator, body = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise ProbeFailure("empty or malformed SIP datagram")
    unfolded = []
    for line in lines[1:]:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += " " + line.strip()
        else:
            unfolded.append(line)
    headers = {}
    for line in unfolded:
        name, colon, value = line.partition(":")
        if colon:
            headers.setdefault(name.strip().lower(), []).append(value.strip())
    return {"first_line": lines[0], "headers": headers, "body": body if separator else ""}


def header_values(message, name):
    return message["headers"].get(name.lower(), [])


def first_header(message, name):
    values = header_values(message, name)
    if not values:
        raise ProbeFailure(f"missing {name} header")
    return values[0]


def address_tag(value):
    match = re.search(r"(?:^|;)\s*tag=([^;>\s]+)", value, re.IGNORECASE)
    return match.group(1) if match else ""


def uri_value(value):
    left = value.find("<")
    if left < 0:
        return value.strip()
    right = value.find(">", left + 1)
    if right < 0:
        raise ProbeFailure(f"unterminated name-addr: {value}")
    return value[left + 1 : right]


def request_uri(message):
    parts = message["first_line"].split()
    if len(parts) < 3:
        raise ProbeFailure(f"malformed SIP request line: {message['first_line']}")
    return parts[1]


def cseq(message):
    value = first_header(message, "CSeq").split()
    if len(value) != 2:
        raise ProbeFailure(f"malformed CSeq: {first_header(message, 'CSeq')}")
    try:
        return int(value[0]), value[1].upper()
    except ValueError as error:
        raise ProbeFailure(f"malformed CSeq number: {value[0]}") from error


def normalized(value):
    return value.strip().lower()


def tagged_to(value):
    if address_tag(value):
        return value
    return value + ";tag=" + REMOTE_TAG


def make_response(request_packet, status, contact, record_route=None):
    request = parse_sip(request_packet)
    reason = {"200": "OK", "400": "Bad Request", "481": "Call/Transaction Does Not Exist"}[status]
    lines = [f"SIP/2.0 {status} {reason}\r\n"]
    for via in header_values(request, "Via"):
        lines.append(f"Via: {via}\r\n")
    lines.extend(
        [
            f"From: {first_header(request, 'From')}\r\n",
            f"To: {tagged_to(first_header(request, 'To'))}\r\n",
            f"Call-ID: {first_header(request, 'Call-ID')}\r\n",
            f"CSeq: {first_header(request, 'CSeq')}\r\n",
        ]
    )
    if status == "200":
        lines.append(f"Contact: <{contact}>\r\n")
        if record_route:
            lines.append(f"Record-Route: <{record_route}>\r\n")
        lines.append(f"Content-Type: application/sdp\r\n")
        lines.append(f"Content-Length: {len(ANSWER_SDP)}\r\n\r\n")
        return "".join(lines).encode("ascii") + ANSWER_SDP
    lines.append("Content-Length: 0\r\n\r\n")
    return "".join(lines).encode("ascii")


def send_peer(sock, recorder, phase, packet, address):
    recorder.record(phase, "peer-to-child", packet, address)
    sent = sock.sendto(packet, address)
    if sent != len(packet):
        raise ProbeFailure(f"short UDP send: {sent}/{len(packet)} bytes")


def receive_packet(sock, recorder, phase, deadline, process):
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        sock.settimeout(min(0.25, max(0.01, remaining)))
        try:
            packet, address = sock.recvfrom(65535)
        except socket.timeout:
            if process.poll() is not None:
                raise ProbeFailure(
                    f"child PID {process.pid} exited with {process.returncode} before next SIP datagram"
                )
            continue
        recorder.record(phase, "child-to-peer", packet, address)
        return packet, address
    raise ProbeFailure(f"{phase} timed out waiting for SIP datagram")


def require(condition, failures, message):
    if not condition:
        failures.append(message)


def validate_peer_address(address, client_port, phase):
    failures = []
    require(address[0] == "127.0.0.1", failures, f"{phase} source address was {address[0]}")
    require(address[1] == client_port, failures, f"{phase} source port was {address[1]}, expected {client_port}")
    return failures


def validate_phase_a_request(packet, address, client_port, target):
    failures = validate_peer_address(address, client_port, "phase A")
    message = parse_sip(packet)
    require(message["first_line"].startswith("INVITE "), failures, "phase A was not an INVITE")
    require(normalized(request_uri(message)) == normalized(target), failures, "phase-A Request-URI did not match peer target")
    require(bool(first_header(message, "Call-ID")), failures, "phase-A Call-ID was empty")
    require(bool(address_tag(first_header(message, "From"))), failures, "phase-A From tag was empty")
    require(not address_tag(first_header(message, "To")), failures, "phase A unexpectedly carried a To-tag")
    number, method = cseq(message)
    require(method == "INVITE", failures, "phase-A CSeq method was not INVITE")
    require(not header_values(message, "Route"), failures, "phase-A initial INVITE unexpectedly had Route headers")
    return message, failures, number


def state_from_phase_a(request, response, call_id, local_tag, last_cseq):
    contact = uri_value(first_header(response, "Contact"))
    routes = [uri_value(value) for value in header_values(response, "Record-Route")]
    routes.reverse()
    return {
        "schema_version": 1,
        "dialog_set_id": {"call_id": call_id, "local_tag": local_tag},
        "remote_to_tag": address_tag(first_header(response, "To")),
        "remote_target_contact": contact,
        "route_set": routes,
        "last_cseq": last_cseq,
        "business_context_key": BUSINESS_CONTEXT_KEY,
    }


def validate_phase_b_request(packet, address, client_port, state):
    failures = validate_peer_address(address, client_port, "phase B")
    message = parse_sip(packet)
    identity = state["dialog_set_id"]
    require(message["first_line"].startswith("INVITE "), failures, "phase B was not an INVITE")
    require(first_header(message, "Call-ID") == identity["call_id"], failures, "phase-B Call-ID differs from retained phase-A identity")
    require(address_tag(first_header(message, "From")) == identity["local_tag"], failures, "phase-B From tag differs from retained phase-A identity")
    require(address_tag(first_header(message, "To")) == state["remote_to_tag"], failures, "phase-B To-tag differs from retained phase-A identity")
    require(normalized(request_uri(message)) == normalized(state["remote_target_contact"]), failures, "phase-B Request-URI differs from retained Contact target")
    actual_routes = [uri_value(value) for value in header_values(message, "Route")]
    require(len(actual_routes) == len(state["route_set"]), failures, "phase-B Route count differs from retained route set")
    require(
        [normalized(value) for value in actual_routes] == [normalized(value) for value in state["route_set"]],
        failures,
        "phase-B Route headers differ from retained route set",
    )
    number, method = cseq(message)
    require(method == "INVITE", failures, "phase-B CSeq method was not INVITE")
    require(number == state["last_cseq"] + 1, failures, "phase-B CSeq was not exactly the incremented retained CSeq")
    return message, failures, number


def validate_ack(packet, phase, state, expected_cseq, expected_route_set):
    failures = []
    message = parse_sip(packet)
    require(message["first_line"].startswith("ACK "), failures, f"{phase} DUM did not send ACK")
    require(first_header(message, "Call-ID") == state["dialog_set_id"]["call_id"], failures, f"{phase} ACK Call-ID differed")
    require(address_tag(first_header(message, "From")) == state["dialog_set_id"]["local_tag"], failures, f"{phase} ACK From tag differed")
    require(address_tag(first_header(message, "To")) == state["remote_to_tag"], failures, f"{phase} ACK To-tag differed")
    number, method = cseq(message)
    require(method == "ACK" and number == expected_cseq, failures, f"{phase} ACK CSeq was {number} {method}, expected {expected_cseq} ACK")
    actual_routes = [uri_value(value) for value in header_values(message, "Route")]
    require(
        [normalized(value) for value in actual_routes] == [normalized(value) for value in expected_route_set],
        failures,
        f"{phase} ACK Route headers differed from expected route set",
    )
    return failures


def wait_for_ack(sock, recorder, phase, process, request_packet, response_packet, state, expected_cseq, expected_routes, timeout):
    deadline = time.monotonic() + timeout
    while True:
        packet, address = receive_packet(sock, recorder, phase, deadline, process)
        message = parse_sip(packet)
        line = message["first_line"]
        if line.startswith("ACK "):
            failures = validate_peer_address(address, process.client_port, phase)
            failures.extend(validate_ack(packet, phase, state, expected_cseq, expected_routes))
            return failures
        if line.startswith("INVITE ") and packet == request_packet:
            send_peer(sock, recorder, phase, response_packet, address)
            continue
        return [f"{phase} peer received unexpected datagram while waiting for ACK: {line}"]


def preflight_client_port(port):
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as error:
        raise ProbeFailure(f"client UDP port 127.0.0.1:{port} is not available: {error}") from error
    finally:
        probe.close()


def start_child(phase, args, state=None):
    executable = ROOT / "dum_phase_child"
    command = [
        str(executable),
        phase,
        "--peer-port",
        str(args.peer_port),
        "--client-port",
        str(args.client_port),
    ]
    if state is not None:
        command.extend(
            [
                "--call-id",
                state["dialog_set_id"]["call_id"],
                "--local-tag",
                state["dialog_set_id"]["local_tag"],
                "--remote-tag",
                state["remote_to_tag"],
                "--remote-target",
                state["remote_target_contact"],
                "--last-cseq",
                str(state["last_cseq"]),
                "--business-context-key",
                state["business_context_key"],
            ]
        )
        for route in state["route_set"]:
            command.extend(["--route", route])
    name = phase.replace("-", "_")
    (PROCESSES / f"{name}-command.json").write_text(
        json.dumps(command, indent=2) + "\n", encoding="utf-8"
    )
    log_path = LOGS / f"{name}-child.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    process.client_port = args.client_port
    return process


def wait_child(process, timeout, phase):
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ProbeFailure(f"{phase} child PID {process.pid} did not exit within {timeout:.1f}s") from error
    return {
        "pid": process.pid,
        "return_code": returncode,
        "wait_reaped": process.poll() is not None,
        "procfs_entry_after_wait": Path(f"/proc/{process.pid}").exists(),
        "wait_observed_monotonic_ns": time.monotonic_ns(),
    }


def stop_child(process, phase):
    if process.poll() is not None:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    (PROCESSES / f"{phase}-forced-stop.json").write_text(
        json.dumps(
            {"pid": process.pid, "return_code": process.returncode, "forced_after_failure": True},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_failure(failures, phase, detail):
    failures.append({"phase": phase, "detail": detail})


def record_child_exit(phase, exit_record):
    name = phase.replace("-", "_")
    write_json(PROCESSES / f"{name}-exit.json", exit_record)


def run(args):
    for directory in (MESSAGES, LOGS, PROCESSES):
        directory.mkdir(parents=True, exist_ok=True)
    recorder = Recorder()
    failures = []
    lifecycle = {
        "parent_pid": os.getpid(),
        "peer_address": ["127.0.0.1", args.peer_port],
        "client_address": ["127.0.0.1", args.client_port],
        "peer_socket_bound_before_phase_a": False,
        "peer_socket_kept_bound_through_both_phases": False,
        "events": [],
    }
    process = None
    peer = None
    try:
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(("127.0.0.1", args.peer_port))
        lifecycle["peer_socket_bound_before_phase_a"] = True
        preflight_client_port(args.client_port)
        lifecycle["peer_socket_kept_bound_through_both_phases"] = True
        target = f"sip:uas@127.0.0.1:{args.peer_port};transport=udp"
        route = f"sip:127.0.0.1:{args.peer_port};lr;transport=udp"

        phase_a_start = time.monotonic_ns()
        process = start_child("phase-a", args)
        lifecycle["events"].append(
            {"event": "phase-a-start", "pid": process.pid, "monotonic_ns": phase_a_start}
        )
        deadline = time.monotonic() + args.timeout
        request_packet, address = receive_packet(peer, recorder, "phase-a", deadline, process)
        request, request_failures, phase_a_cseq = validate_phase_a_request(
            request_packet, address, args.client_port, target
        )
        if request_failures:
            for failure in request_failures:
                append_failure(failures, "phase-a-peer-validation", failure)
            rejection = make_response(request_packet, "400", target)
            send_peer(peer, recorder, "phase-a", rejection, address)
            raise ProbeFailure("phase-A INVITE failed initial-dialog validation")

        call_id = first_header(request, "Call-ID")
        local_tag = address_tag(first_header(request, "From"))
        response_packet = make_response(request_packet, "200", target, route)
        send_peer(peer, recorder, "phase-a", response_packet, address)
        response = parse_sip(response_packet)
        if address_tag(first_header(response, "To")) != REMOTE_TAG:
            raise ProbeFailure("phase-A peer response did not contain the configured stable To-tag")
        state = state_from_phase_a(request, response, call_id, local_tag, phase_a_cseq)
        if not state["remote_target_contact"] or not state["route_set"]:
            raise ProbeFailure("phase-A 200 did not provide a remote target and route set")
        if state["remote_to_tag"] != REMOTE_TAG:
            raise ProbeFailure("phase-A state did not retain the stable remote To-tag")
        write_json(STATE_PATH, state)

        phase_a_ack_failures = wait_for_ack(
            peer,
            recorder,
            "phase-a",
            process,
            request_packet,
            response_packet,
            state,
            phase_a_cseq,
            state["route_set"],
            args.timeout,
        )
        for failure in phase_a_ack_failures:
            append_failure(failures, "phase-a-ack-validation", failure)
        phase_a_exit = wait_child(process, args.timeout, "phase-a")
        record_child_exit("phase-a", phase_a_exit)
        lifecycle["events"].append(
            {
                "event": "phase-a-reaped",
                "pid": process.pid,
                "return_code": phase_a_exit["return_code"],
                "monotonic_ns": phase_a_exit["wait_observed_monotonic_ns"],
                "procfs_entry_after_wait": phase_a_exit["procfs_entry_after_wait"],
            }
        )
        if phase_a_exit["return_code"] != 0:
            raise ProbeFailure(f"phase-A child exited with status {phase_a_exit['return_code']}")
        if phase_a_exit["procfs_entry_after_wait"]:
            raise ProbeFailure("phase-A PID still had a /proc entry after wait()")
        if failures:
            raise ProbeFailure("phase-A peer/ACK validation failed")
        process = None
        state["phase_a_process_exit_code"] = phase_a_exit["return_code"]
        write_json(STATE_PATH, state)

        persisted_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        phase_b_start = time.monotonic_ns()
        if phase_b_start <= phase_a_exit["wait_observed_monotonic_ns"]:
            raise ProbeFailure("phase B start timestamp did not follow phase-A reap")
        process = start_child("phase-b", args, persisted_state)
        lifecycle["events"].append(
            {"event": "phase-b-start", "pid": process.pid, "monotonic_ns": phase_b_start}
        )
        deadline = time.monotonic() + args.timeout
        request_packet, address = receive_packet(peer, recorder, "phase-b", deadline, process)
        request, request_failures, phase_b_cseq = validate_phase_b_request(
            request_packet, address, args.client_port, persisted_state
        )
        if request_failures:
            for failure in request_failures:
                append_failure(failures, "phase-b-peer-validation", failure)
            response_packet = make_response(request_packet, "481", target)
            send_peer(peer, recorder, "phase-b", response_packet, address)
            raise ProbeFailure("phase-B request was not an in-dialog re-INVITE for the retained phase-A dialog")

        response_packet = make_response(request_packet, "200", target)
        send_peer(peer, recorder, "phase-b", response_packet, address)
        response_message = parse_sip(response_packet)
        response_cseq, response_method = cseq(response_message)
        if response_cseq != phase_b_cseq or response_method != "INVITE":
            append_failure(failures, "phase-b-response-validation", "phase-B 200 was not correlated to the re-INVITE CSeq")
        if address_tag(first_header(response_message, "From")) != persisted_state["dialog_set_id"]["local_tag"]:
            append_failure(failures, "phase-b-response-validation", "phase-B 200 From tag differed")
        if address_tag(first_header(response_message, "To")) != persisted_state["remote_to_tag"]:
            append_failure(failures, "phase-b-response-validation", "phase-B 200 To tag differed")
        phase_b_ack_failures = wait_for_ack(
            peer,
            recorder,
            "phase-b",
            process,
            request_packet,
            response_packet,
            persisted_state,
            phase_b_cseq,
            persisted_state["route_set"],
            args.timeout,
        )
        for failure in phase_b_ack_failures:
            append_failure(failures, "phase-b-ack-validation", failure)
        phase_b_exit = wait_child(process, args.timeout, "phase-b")
        record_child_exit("phase-b", phase_b_exit)
        lifecycle["events"].append(
            {
                "event": "phase-b-reaped",
                "pid": process.pid,
                "return_code": phase_b_exit["return_code"],
                "monotonic_ns": phase_b_exit["wait_observed_monotonic_ns"],
                "procfs_entry_after_wait": phase_b_exit["procfs_entry_after_wait"],
            }
        )
        if phase_b_exit["return_code"] != 0:
            raise ProbeFailure(f"phase-B child exited with status {phase_b_exit['return_code']}")
        if phase_b_exit["procfs_entry_after_wait"]:
            raise ProbeFailure("phase-B PID still had a /proc entry after wait()")
        process = None
        if failures:
            raise ProbeFailure("phase-B SIP validation failed")

        lifecycle["phase_a_pid"] = phase_a_exit["pid"]
        lifecycle["phase_a_reaped_before_phase_b_start"] = (
            phase_a_exit["wait_reaped"]
            and not phase_a_exit["procfs_entry_after_wait"]
            and phase_a_exit["wait_observed_monotonic_ns"] < phase_b_start
        )
        lifecycle["phase_b_pid"] = phase_b_exit["pid"]
        lifecycle["phase_a_exit_code"] = phase_a_exit["return_code"]
        lifecycle["phase_b_exit_code"] = phase_b_exit["return_code"]
        if not lifecycle["phase_a_reaped_before_phase_b_start"]:
            raise ProbeFailure("phase-A child was not verified reaped before phase B")
        return 0
    except Exception as error:
        append_failure(failures, "harness", str(error))
        return 1
    finally:
        if process is not None:
            stop_child(process, "active-child")
        if peer is not None:
            peer.close()
        lifecycle["finished_monotonic_ns"] = time.monotonic_ns()
        lifecycle["peer_socket_closed_after_run"] = peer is not None
        write_json(ROOT / "process-lifecycle.json", lifecycle)
        write_json(ROOT / "failures.json", {"failures": failures})
        lines = ["PASS" if not failures else "FAIL"]
        for failure in failures:
            lines.append(f"{failure['phase']}: {failure['detail']}")
        (ROOT / "validation.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (ROOT / "validation.json").write_text(
            json.dumps({"passed": not failures, "failures": failures}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--peer-port", type=int, default=39841)
    parser.add_argument("--client-port", type=int, default=39842)
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()
    if not (1024 <= args.peer_port <= 65535 and 1024 <= args.client_port <= 65535):
        parser.error("ports must be in the range 1024..65535")
    if args.peer_port == args.client_port:
        parser.error("peer and client ports must differ")
    if not (2.0 <= args.timeout <= 30.0):
        parser.error("timeout must be between 2 and 30 seconds")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
