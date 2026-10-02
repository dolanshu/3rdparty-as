#!/usr/bin/env python3
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MESSAGES = ROOT / "messages"
LOGS = ROOT / "logs"
PROCESSES = ROOT / "processes"
STATE_PATH = ROOT / "state.json"
OFFER_SDP = (
    "v=0\r\n"
    "o=- 4001 2 IN IP4 127.0.0.1\r\n"
    "s=UAS restart negative recovery probe\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 49170 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
    "a=sendrecv\r\n"
).encode("ascii")


class ProbeFailure(RuntimeError):
    pass


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


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


def parse_sip(packet):
    head, separator, body = packet.partition(b"\r\n\r\n")
    lines = head.decode("utf-8", errors="replace").split("\r\n")
    if not separator or not lines or not lines[0]:
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
    return {"first_line": lines[0], "headers": headers, "body": body}


def header_values(message, name):
    return message["headers"].get(name.lower(), [])


def header(message, name):
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


def cseq(message):
    parts = header(message, "CSeq").split()
    if len(parts) != 2:
        raise ProbeFailure(f"malformed CSeq: {header(message, 'CSeq')}")
    try:
        return int(parts[0]), parts[1].upper()
    except ValueError as error:
        raise ProbeFailure(f"malformed CSeq number: {parts[0]}") from error


def response_status(message):
    parts = message["first_line"].split(" ", 2)
    if len(parts) < 2 or parts[0] != "SIP/2.0" or not parts[1].isdigit():
        raise ProbeFailure(f"not a SIP response: {message['first_line']}")
    return int(parts[1])


def record_check(checks, failures, name, passed, detail):
    checks[name] = {"passed": bool(passed), "detail": detail}
    if not passed:
        failures.append(f"{name}: {detail}")


def preflight_udp_port(port, label):
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as error:
        raise ProbeFailure(
            f"preflight failed for {label} UDP port 127.0.0.1:{port}: {error}"
        ) from error
    finally:
        probe.close()
    return {"label": label, "address": ["127.0.0.1", port], "available": True}


def sip_host_port(uri):
    scheme, separator, rest = uri.partition(":")
    if not separator or scheme.lower() not in ("sip", "sips"):
        raise ProbeFailure(f"not a SIP URI: {uri}")
    authority = rest.split(";", 1)[0].split("?", 1)[0]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    if authority.startswith("["):
        closing = authority.find("]")
        if closing < 0:
            raise ProbeFailure(f"malformed IPv6 SIP URI: {uri}")
        host = authority[1:closing]
        suffix = authority[closing + 1 :]
        port = int(suffix[1:]) if suffix.startswith(":") else (5061 if scheme.lower() == "sips" else 5060)
    else:
        host, colon, port_text = authority.rpartition(":")
        if colon and port_text.isdigit():
            port = int(port_text)
        else:
            host = authority
            port = 5061 if scheme.lower() == "sips" else 5060
    if not host:
        raise ProbeFailure(f"SIP URI has no host: {uri}")
    return host, port


def route_next_hop(route_set, remote_target):
    return sip_host_port(route_set[0] if route_set else remote_target)


def build_request(start_line, via_branch, from_value, to_value, call_id, cseq_value,
                  peer_port, body=b"", contact=None, route_set=()):
    lines = [
        f"{start_line}\r\n",
        f"Via: SIP/2.0/UDP 127.0.0.1:{peer_port};branch={via_branch};rport\r\n",
        "Max-Forwards: 70\r\n",
        f"From: {from_value}\r\n",
        f"To: {to_value}\r\n",
        f"Call-ID: {call_id}\r\n",
        f"CSeq: {cseq_value}\r\n",
    ]
    if contact:
        lines.append(f"Contact: <{contact}>\r\n")
    for route in route_set:
        lines.append(f"Route: <{route}>\r\n")
    if body:
        lines.append("Content-Type: application/sdp\r\n")
    lines.append(f"Content-Length: {len(body)}\r\n\r\n")
    return "".join(lines).encode("ascii") + body


def build_initial_invite(server_port, peer_port, call_id, caller_uri, caller_contact,
                         caller_tag, record_route, branch):
    to_value = f"<sip:uas@127.0.0.1:{server_port}>"
    return build_request(
        f"INVITE sip:uas@127.0.0.1:{server_port};transport=udp SIP/2.0",
        branch,
        f"<{caller_uri}>;tag={caller_tag}",
        to_value,
        call_id,
        "1 INVITE",
        peer_port,
        OFFER_SDP,
        contact=caller_contact,
        route_set=(),
    ).replace(
        f"Contact: <{caller_contact}>\r\n".encode("ascii"),
        (
            f"Contact: <{caller_contact}>\r\n"
            f"Record-Route: <{record_route}>\r\n"
        ).encode("ascii"),
        1,
    )


def wait_for_ready(process, log_path, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            log_text = ""
        if "DUM_READY " in log_text:
            return
        if process.poll() is not None:
            raise ProbeFailure(
                f"child PID {process.pid} exited before DUM_READY with {process.returncode}"
            )
        time.sleep(0.05)
    raise ProbeFailure(f"child PID {process.pid} did not report DUM_READY within {timeout:.1f}s")


def start_child(phase, server_port, timeout):
    executable = ROOT / "uas_dum_process"
    runtime_ms = min(30000, int((timeout + 6.0) * 1000))
    command = [
        str(executable),
        phase,
        "--port",
        str(server_port),
        "--runtime-ms",
        str(runtime_ms),
    ]
    name = phase.replace("-", "_")
    write_json(PROCESSES / f"{name}-command.json", command)
    log_path = LOGS / f"{name}-dum.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            cwd=ROOT,
        )
    process.log_path = log_path
    process.phase = phase
    return process


def send_packet(peer, recorder, phase, packet, destination, label):
    recorder.record(phase, "peer-to-dum-" + label, packet, destination)
    sent = peer.sendto(packet, destination)
    if sent != len(packet):
        raise ProbeFailure(f"short UDP send: {sent}/{len(packet)} bytes")


def receive_packet(peer, recorder, phase, deadline, process):
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        peer.settimeout(min(0.25, max(0.01, remaining)))
        try:
            packet, address = peer.recvfrom(65535)
        except socket.timeout:
            if process.poll() is not None:
                raise ProbeFailure(
                    f"{phase} child PID {process.pid} exited with {process.returncode} before response"
                )
            continue
        recorder.record(phase, "dum-to-peer", packet, address)
        return packet, address
    raise ProbeFailure(f"{phase} timed out waiting for a SIP datagram")


def wait_for_process(process, timeout, phase):
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
        return {
            "pid": process.pid,
            "already_exited": True,
            "return_code": process.wait(),
            "procfs_entry_after_wait": Path(f"/proc/{process.pid}").exists(),
        }
    process.terminate()
    try:
        returncode = process.wait(timeout=2.0)
        forced = False
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = process.wait(timeout=2.0)
        forced = True
    record = {
        "pid": process.pid,
        "return_code": returncode,
        "forced_kill": forced,
        "procfs_entry_after_wait": Path(f"/proc/{process.pid}").exists(),
    }
    write_json(PROCESSES / f"{phase}-cleanup.json", record)
    return record


def response_matches_dialog(message, state, expected_cseq, expected_method):
    number, method = cseq(message)
    return {
        "call_id": header(message, "Call-ID") == state["call_id"],
        "from_tag": address_tag(header(message, "From")) == state["caller_from_tag"],
        "to_tag": address_tag(header(message, "To")) == state["as_to_tag"],
        "cseq": number == expected_cseq and method == expected_method,
    }


def run(args):
    for directory in (MESSAGES, LOGS, PROCESSES):
        directory.mkdir(parents=True, exist_ok=True)

    recorder = Recorder()
    checks = {}
    failures = []
    lifecycle = {
        "parent_pid": os.getpid(),
        "server_address": ["127.0.0.1", args.server_port],
        "peer_address": ["127.0.0.1", args.peer_port],
        "events": [],
        "phase_a_started": False,
        "phase_b_started": False,
    }
    result = {
        "expected_phase_b_status": 481,
        "phase_a": {},
        "phase_b": {},
        "checks": checks,
    }
    processes = []
    peer = None

    try:
        preflight = [
            preflight_udp_port(args.server_port, "DUM server"),
            preflight_udp_port(args.peer_port, "peer harness"),
        ]
        if args.server_port == args.peer_port:
            raise ProbeFailure("server and peer ports must differ")
        write_json(ROOT / "port-preflight.json", preflight)

        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(("127.0.0.1", args.peer_port))
        lifecycle["peer_socket_bound_for_both_phases"] = True

        run_id = uuid.uuid4().hex[:16]
        call_id = f"uas-restart-{run_id}@127.0.0.1"
        caller_tag = f"caller-{run_id}"
        caller_uri = f"sip:caller@127.0.0.1:{args.peer_port}"
        caller_contact = f"{caller_uri};transport=udp"
        record_route = f"sip:127.0.0.1:{args.server_port};lr;transport=udp"
        initial_request = build_initial_invite(
            args.server_port,
            args.peer_port,
            call_id,
            caller_uri,
            caller_contact,
            caller_tag,
            record_route,
            f"z9hG4bK-invite-{run_id}",
        )

        phase_a_start_ns = time.monotonic_ns()
        phase_a = start_child("phase-a", args.server_port, args.timeout)
        processes.append(phase_a)
        lifecycle["phase_a_started"] = True
        lifecycle["phase_a_pid"] = phase_a.pid
        lifecycle["events"].append(
            {"event": "phase-a-start", "pid": phase_a.pid, "monotonic_ns": phase_a_start_ns}
        )
        wait_for_ready(phase_a, phase_a.log_path, args.timeout)
        send_packet(
            peer,
            recorder,
            "phase-a",
            initial_request,
            ("127.0.0.1", args.server_port),
            "invite",
        )

        provisional_statuses = []
        response_200 = None
        response_200_address = None
        response_deadline = time.monotonic() + args.timeout
        while response_200 is None:
            packet, address = receive_packet(peer, recorder, "phase-a", response_deadline, phase_a)
            response = parse_sip(packet)
            status = response_status(response)
            record_check(
                checks,
                failures,
                f"phase_a_source_{len(provisional_statuses) + 1}",
                address == ("127.0.0.1", args.server_port),
                f"received from {address}, expected ('127.0.0.1', {args.server_port})",
            )
            if 100 <= status < 200:
                provisional_statuses.append(status)
                if status == 180:
                    result["phase_a"]["response_180"] = response["first_line"]
                continue
            if 200 <= status < 300:
                response_200 = response
                response_200_address = address
                result["phase_a"]["response_200"] = response["first_line"]
                break
            raise ProbeFailure(f"phase-A INVITE received unexpected final response {response['first_line']}")

        record_check(
            checks,
            failures,
            "phase_a_received_180",
            180 in provisional_statuses,
            f"observed provisional status codes {provisional_statuses}",
        )
        response_cseq, response_method = cseq(response_200)
        as_to = header(response_200, "To")
        as_to_tag = address_tag(as_to)
        as_contact = uri_value(header(response_200, "Contact"))
        response_record_routes = [uri_value(value) for value in header_values(response_200, "Record-Route")]
        caller_route_set = list(reversed(response_record_routes))
        answer_sdp = response_200["body"].decode("utf-8", errors="replace")
        initial_parsed = parse_sip(initial_request)
        state = {
            "schema_version": 1,
            "phase_a_process_pid": phase_a.pid,
            "server_address": ["127.0.0.1", args.server_port],
            "peer_address": ["127.0.0.1", args.peer_port],
            "call_id": call_id,
            "caller_from": header(initial_parsed, "From"),
            "caller_from_tag": caller_tag,
            "caller_contact": caller_contact,
            "as_to": as_to,
            "as_to_tag": as_to_tag,
            "as_contact": as_contact,
            "response_record_route_order": response_record_routes,
            "caller_route_set": caller_route_set,
            "invite_cseq": 1,
            "last_phase_a_cseq": response_cseq,
            "phase_b_bye_cseq": response_cseq + 1,
            "invite_request_uri": f"sip:uas@127.0.0.1:{args.server_port};transport=udp",
            "offer_sdp": OFFER_SDP.decode("ascii"),
            "answer_sdp": answer_sdp,
            "phase_a_provisional_statuses": provisional_statuses,
            "phase_a_response_200": response_200["first_line"],
            "phase_a_response_source": list(response_200_address),
            "snapshot_retained_only_by_harness": True,
        }
        write_json(STATE_PATH, state)
        result["phase_a"].update(
            {
                "call_id": call_id,
                "caller_from_tag": caller_tag,
                "as_to_tag": as_to_tag,
                "as_contact": as_contact,
                "response_record_route_order": response_record_routes,
                "caller_route_set": caller_route_set,
                "sdp_answer_bytes": len(response_200["body"]),
            }
        )

        record_check(checks, failures, "phase_a_call_id", header(response_200, "Call-ID") == call_id,
                     f"200 Call-ID={header(response_200, 'Call-ID')}")
        record_check(checks, failures, "phase_a_from_tag",
                     address_tag(header(response_200, "From")) == caller_tag,
                     f"200 From tag={address_tag(header(response_200, 'From'))}")
        record_check(checks, failures, "phase_a_to_tag", bool(as_to_tag), f"200 To tag={as_to_tag!r}")
        record_check(checks, failures, "phase_a_cseq",
                     response_cseq == 1 and response_method == "INVITE",
                     f"200 CSeq={response_cseq} {response_method}")
        record_check(checks, failures, "phase_a_contact", as_contact.lower().startswith(("sip:", "sips:")),
                     f"AS Contact={as_contact}")
        record_check(checks, failures, "phase_a_route_set", bool(caller_route_set),
                     f"caller route set={caller_route_set}")
        record_check(checks, failures, "phase_a_answer_sdp",
                     "application/sdp" in header(response_200, "Content-Type").lower()
                     and "m=audio " in answer_sdp
                     and "a=rtpmap:0 PCMU/8000" in answer_sdp,
                     f"Content-Type={header(response_200, 'Content-Type')}; SDP bytes={len(response_200['body'])}")

        ack_next_hop = route_next_hop(caller_route_set, as_contact)
        record_check(checks, failures, "phase_a_route_next_hop",
                     ack_next_hop == ("127.0.0.1", args.server_port),
                     f"ACK next hop={ack_next_hop}")
        ack = build_request(
            f"ACK {as_contact} SIP/2.0",
            f"z9hG4bK-ack-{run_id}",
            state["caller_from"],
            state["as_to"],
            call_id,
            "1 ACK",
            args.peer_port,
            route_set=caller_route_set,
        )
        send_packet(peer, recorder, "phase-a", ack, ack_next_hop, "ack")

        phase_a_exit = wait_for_process(phase_a, args.timeout, "phase-a")
        write_json(PROCESSES / "phase_a-exit.json", phase_a_exit)
        lifecycle["phase_a_exit"] = phase_a_exit
        lifecycle["events"].append(
            {
                "event": "phase-a-reaped",
                "pid": phase_a.pid,
                "return_code": phase_a_exit["return_code"],
                "monotonic_ns": phase_a_exit["wait_observed_monotonic_ns"],
                "procfs_entry_after_wait": phase_a_exit["procfs_entry_after_wait"],
            }
        )
        phase_a_log = phase_a.log_path.read_text(encoding="utf-8", errors="replace")
        record_check(checks, failures, "phase_a_clean_exit", phase_a_exit["return_code"] == 0,
                     f"return_code={phase_a_exit['return_code']}")
        record_check(checks, failures, "phase_a_pid_gone",
                     phase_a_exit["wait_reaped"] and not phase_a_exit["procfs_entry_after_wait"],
                     f"wait_reaped={phase_a_exit['wait_reaped']}; /proc entry={phase_a_exit['procfs_entry_after_wait']}")
        record_check(checks, failures, "phase_a_dum_connected",
                     "CALLBACK UAS_CONNECTED status=200" in phase_a_log,
                     "searched phase-a-dum.log for DUM's onConnected(200) callback")
        record_check(checks, failures, "phase_a_dum_ack_confirmed",
                     "CALLBACK UAS_CONNECTED_CONFIRMED cseq=1" in phase_a_log,
                     "searched phase-a-dum.log for onConnectedConfirmed after ACK")
        if phase_a_exit["return_code"] != 0 or phase_a_exit["procfs_entry_after_wait"]:
            raise ProbeFailure("phase A did not exit cleanly with its PID gone")

        persisted_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        phase_b_start_ns = time.monotonic_ns()
        if phase_b_start_ns <= phase_a_exit["wait_observed_monotonic_ns"]:
            raise ProbeFailure("phase B started before phase A was reaped")
        phase_b = start_child("phase-b", args.server_port, args.timeout)
        processes.append(phase_b)
        lifecycle["phase_b_started"] = True
        lifecycle["phase_b_pid"] = phase_b.pid
        lifecycle["events"].append(
            {"event": "phase-b-start", "pid": phase_b.pid, "monotonic_ns": phase_b_start_ns}
        )
        record_check(checks, failures, "independent_processes", phase_b.pid != phase_a.pid,
                     f"phase-A PID={phase_a.pid}; phase-B PID={phase_b.pid}")
        wait_for_ready(phase_b, phase_b.log_path, args.timeout)
        phase_b_command = json.loads((PROCESSES / "phase_b-command.json").read_text(encoding="utf-8"))
        record_check(checks, failures, "phase_b_no_state_restore_input",
                     len(phase_b_command) == 6
                     and "--call-id" not in phase_b_command
                     and "--local-tag" not in phase_b_command,
                     f"fresh process argv={phase_b_command}; only phase, port, and runtime are passed")
        record_check(checks, failures, "same_listening_port",
                     "listen=127.0.0.1:" + str(args.server_port) in phase_a_log
                     and "listen=127.0.0.1:" + str(args.server_port) in phase_b.log_path.read_text(encoding="utf-8", errors="replace"),
                     f"both DUM processes configured for 127.0.0.1:{args.server_port}")

        bye_cseq = persisted_state["phase_b_bye_cseq"]
        bye_next_hop = route_next_hop(persisted_state["caller_route_set"], persisted_state["as_contact"])
        bye = build_request(
            f"BYE {persisted_state['as_contact']} SIP/2.0",
            f"z9hG4bK-bye-{run_id}",
            persisted_state["caller_from"],
            persisted_state["as_to"],
            persisted_state["call_id"],
            f"{bye_cseq} BYE",
            args.peer_port,
            contact=persisted_state["caller_contact"],
            route_set=persisted_state["caller_route_set"],
        )
        bye_message = parse_sip(bye)
        bye_line = bye_message["first_line"].split()
        bye_number, bye_method = cseq(bye_message)
        bye_routes = [uri_value(value) for value in header_values(bye_message, "Route")]
        record_check(checks, failures, "phase_b_bye_request_uri",
                     len(bye_line) == 3 and bye_line[1] == persisted_state["as_contact"],
                     f"wire BYE Request-URI={bye_line[1] if len(bye_line) >= 2 else '<missing>'}")
        record_check(checks, failures, "phase_b_bye_dialog_identity",
                     header(bye_message, "Call-ID") == persisted_state["call_id"]
                     and address_tag(header(bye_message, "From")) == persisted_state["caller_from_tag"]
                     and address_tag(header(bye_message, "To")) == persisted_state["as_to_tag"],
                     "wire BYE Call-ID and From/To tags match phase-A snapshot")
        record_check(checks, failures, "phase_b_bye_contact",
                     uri_value(header(bye_message, "Contact")) == persisted_state["caller_contact"],
                     f"wire BYE Contact={uri_value(header(bye_message, 'Contact'))}")
        record_check(checks, failures, "phase_b_bye_route_set",
                     bye_routes == persisted_state["caller_route_set"],
                     f"wire BYE Route headers={bye_routes}")
        record_check(checks, failures, "phase_b_bye_incremented_cseq",
                     bye_number == persisted_state["last_phase_a_cseq"] + 1 and bye_method == "BYE",
                     f"wire BYE CSeq={bye_number} {bye_method}")
        record_check(checks, failures, "phase_b_route_next_hop",
                     bye_next_hop == ("127.0.0.1", args.server_port),
                     f"BYE next hop={bye_next_hop}; route set={persisted_state['caller_route_set']}")
        send_packet(peer, recorder, "phase-b", bye, bye_next_hop, "bye")

        response_deadline = time.monotonic() + args.timeout
        phase_b_provisionals = []
        bye_response = None
        bye_response_address = None
        while bye_response is None:
            packet, address = receive_packet(peer, recorder, "phase-b", response_deadline, phase_b)
            response = parse_sip(packet)
            status = response_status(response)
            if 100 <= status < 200:
                phase_b_provisionals.append(response["first_line"])
                continue
            bye_response = response
            bye_response_address = address
        actual_status = response_status(bye_response)
        response_correlations = response_matches_dialog(
            bye_response, persisted_state, bye_cseq, "BYE"
        )
        result["phase_b"] = {
            "actual_dum_response": bye_response["first_line"],
            "actual_status": actual_status,
            "response_source": list(bye_response_address),
            "provisional_responses": phase_b_provisionals,
            "correlation_checks": response_correlations,
            "request_uri": persisted_state["as_contact"],
            "route_set": persisted_state["caller_route_set"],
            "bye_cseq": bye_cseq,
            "response_body_bytes": len(bye_response["body"]),
        }
        record_check(checks, failures, "phase_b_expected_default_481", actual_status == 481,
                     f"actual DUM response={bye_response['first_line']}")
        record_check(checks, failures, "phase_b_response_source",
                     bye_response_address == ("127.0.0.1", args.server_port),
                     f"response source={bye_response_address}")
        for field, passed in response_correlations.items():
            record_check(checks, failures, f"phase_b_response_{field}", passed,
                         f"correlation={passed}; response={bye_response['first_line']}")

        if phase_b.poll() is None:
            phase_b.terminate()
        phase_b_exit = wait_for_process(phase_b, 3.0, "phase-b")
        write_json(PROCESSES / "phase_b-exit.json", phase_b_exit)
        lifecycle["phase_b_exit"] = phase_b_exit
        lifecycle["events"].append(
            {
                "event": "phase-b-reaped",
                "pid": phase_b.pid,
                "return_code": phase_b_exit["return_code"],
                "monotonic_ns": phase_b_exit["wait_observed_monotonic_ns"],
                "procfs_entry_after_wait": phase_b_exit["procfs_entry_after_wait"],
            }
        )
        record_check(checks, failures, "phase_b_clean_signal_exit",
                     phase_b_exit["return_code"] == 0,
                     f"return_code={phase_b_exit['return_code']}")
        record_check(checks, failures, "phase_b_pid_gone",
                     phase_b_exit["wait_reaped"] and not phase_b_exit["procfs_entry_after_wait"],
                     f"wait_reaped={phase_b_exit['wait_reaped']}; /proc entry={phase_b_exit['procfs_entry_after_wait']}")
        result["phase_b"]["process_exit"] = phase_b_exit
        lifecycle["phase_a_reaped_before_phase_b_start"] = (
            phase_a_exit["wait_reaped"]
            and not phase_a_exit["procfs_entry_after_wait"]
            and phase_a_exit["wait_observed_monotonic_ns"] < phase_b_start_ns
        )
        record_check(checks, failures, "phase_a_reaped_before_phase_b",
                     lifecycle["phase_a_reaped_before_phase_b_start"],
                     "phase A wait/PID verification completed before phase B start")
        result["phase_a"]["process_exit"] = phase_a_exit
        result["phase_a"]["response_180"] = result["phase_a"].get("response_180")
        result["phase_a"]["phase_a_200"] = response_200["first_line"]

    except Exception as error:
        failures.append(f"harness: {error}")
        result["harness_error"] = str(error)
    finally:
        for process in processes:
            if process.poll() is None:
                cleanup = stop_child(process, process.phase)
                lifecycle.setdefault("cleanup", []).append(cleanup)
        if peer is not None:
            peer.close()
        lifecycle["finished_monotonic_ns"] = time.monotonic_ns()
        lifecycle["peer_socket_closed"] = peer is not None
        result["passed"] = not failures
        result["failures"] = failures
        write_json(ROOT / "process-lifecycle.json", lifecycle)
        write_json(ROOT / "failures.json", {"failures": failures})
        write_json(ROOT / "validation.json", result)
        lines = ["PASS" if not failures else "FAIL"]
        lines.extend(failures)
        (ROOT / "validation.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0 if not failures else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--peer-port", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    if not (1024 <= args.server_port <= 65535 and 1024 <= args.peer_port <= 65535):
        parser.error("ports must be in the range 1024..65535")
    if args.server_port == args.peer_port:
        parser.error("server and peer ports must differ")
    if not (2.0 <= args.timeout <= 20.0):
        parser.error("timeout must be between 2 and 20 seconds")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
