#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import select
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOGICAL_TOKEN = "as-call-two-leg-restart-2026-10-01"
LEG_NAMES = ("leg-a", "leg-b")
REMOTE_TAGS = {
    "leg-a": "uas-leg-a-restart-stable-tag",
    "leg-b": "uas-leg-b-restart-stable-tag",
}
ANSWER_SDP = (
    "v=0\r\n"
    "o=- 7201 2 IN IP4 127.0.0.1\r\n"
    "s=Two-leg restart peer SDP answer\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 49172 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
).encode("ascii")


class ProbeFailure(RuntimeError):
    pass


class Recorder:
    def __init__(self, artifact_root):
        self.artifact_root = artifact_root
        self.messages = artifact_root / "messages"
        self.messages.mkdir(parents=True, exist_ok=True)
        self.events_path = artifact_root / "wire-events.jsonl"
        self.events_path.write_text("", encoding="utf-8")
        self.sequence = 0

    def record(self, phase, direction, packet, address, peer_name):
        self.sequence += 1
        first_line = packet.partition(b"\r\n")[0].decode("ascii", errors="replace")
        if first_line.startswith("SIP/2.0 "):
            label = "response-" + first_line.split(" ", 2)[1]
        else:
            label = first_line.split(" ", 1)[0].lower() if first_line else "empty"
        label = re.sub(r"[^a-zA-Z0-9-]", "_", label)
        filename = f"{phase}-{self.sequence:03d}-{direction}-{label}.sip"
        path = self.messages / filename
        path.write_bytes(packet)
        event = {
            "sequence": self.sequence,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "phase": phase,
            "direction": direction,
            "peer": peer_name,
            "address": list(address) if address else None,
            "size": len(packet),
            "sha256": hashlib.sha256(packet).hexdigest(),
            "first_line": first_line,
            "path": str(path.relative_to(self.artifact_root)),
        }
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def write_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def parse_sip(packet):
    head, separator, body = packet.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    if not lines or not lines[0]:
        raise ProbeFailure("empty or malformed SIP datagram")
    unfolded = []
    for line in lines[1:]:
        if line.startswith((b" ", b"\t")) and unfolded:
            unfolded[-1] += b" " + line.strip()
        else:
            unfolded.append(line)
    aliases = {
        "v": "via",
        "f": "from",
        "t": "to",
        "i": "call-id",
        "m": "contact",
        "l": "content-length",
        "c": "content-type",
    }
    headers = {}
    for line in unfolded:
        name, colon, value = line.partition(b":")
        if colon:
            header_name = name.decode("ascii", errors="replace").strip().lower()
            header_name = aliases.get(header_name, header_name)
            header_value = value.decode("utf-8", errors="replace").strip()
            headers.setdefault(header_name, []).append(header_value)
    return {
        "first_line": lines[0].decode("ascii", errors="replace"),
        "headers": headers,
        "body": body if separator else b"",
    }


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
    if len(parts) != 3 or parts[2] != "SIP/2.0":
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


def route_values(message):
    return [uri_value(value) for value in header_values(message, "Route")]


def tagged_to(value, expected_tag):
    actual_tag = address_tag(value)
    if actual_tag and actual_tag != expected_tag:
        raise ProbeFailure(
            f"peer response To-tag mismatch: received {actual_tag}, expected {expected_tag}"
        )
    return value if actual_tag else value + ";tag=" + expected_tag


def make_200(request_packet, peer_state, phase):
    request = parse_sip(request_packet)
    request_tag = address_tag(first_header(request, "To"))
    if request_tag and request_tag != peer_state["remote_to_tag"]:
        raise ProbeFailure("peer was asked to answer a different remote To-tag")
    cseq_number, method = cseq(request)
    if method != "INVITE":
        raise ProbeFailure("fake peer only accepts INVITE in this experiment")
    lines = ["SIP/2.0 200 OK\r\n"]
    lines.extend(f"Via: {via}\r\n" for via in header_values(request, "Via"))
    lines.extend(
        [
            f"From: {first_header(request, 'From')}\r\n",
            f"To: {tagged_to(first_header(request, 'To'), peer_state['remote_to_tag'])}\r\n",
            f"Call-ID: {first_header(request, 'Call-ID')}\r\n",
            f"CSeq: {cseq_number} INVITE\r\n",
            f"Contact: <{peer_state['remote_target_contact']}>\r\n",
        ]
    )
    if phase == "phase-a":
        for route in peer_state["route_set"]:
            lines.append(f"Record-Route: <{route}>\r\n")
    lines.extend(
        [
            "Content-Type: application/sdp\r\n",
            f"Content-Length: {len(ANSWER_SDP)}\r\n\r\n",
        ]
    )
    return "".join(lines).encode("ascii") + ANSWER_SDP


def send_peer(sock, recorder, phase, packet, destination, peer_name):
    recorder.record(phase, "peer-to-child", packet, destination, peer_name)
    sent = sock.sendto(packet, destination)
    if sent != len(packet):
        raise ProbeFailure(f"short UDP send to {peer_name}: {sent}/{len(packet)} bytes")


def peer_port_map(peer_sockets):
    return {sock.getsockname()[1]: name for name, sock in peer_sockets.items()}


def receive_any(peer_sockets, recorder, phase, deadline, process):
    sockets = list(peer_sockets.values())
    port_to_name = peer_port_map(peer_sockets)
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        ready, _, _ = select.select(sockets, [], [], min(0.2, max(0.01, remaining)))
        if ready:
            sock = ready[0]
            packet, address = sock.recvfrom(65535)
            peer_name = port_to_name[sock.getsockname()[1]]
            recorder.record(phase, "child-to-peer", packet, address, peer_name)
            return peer_name, packet, address
        if process.poll() is not None:
            raise ProbeFailure(
                f"child PID {process.pid} exited with {process.returncode} before next datagram"
            )
    raise ProbeFailure(f"{phase} timed out waiting for a child datagram")


def require(condition, message):
    if not condition:
        raise ProbeFailure(message)


def assert_peer_sockets_bound(peer_sockets, expected_ports, phase):
    for name, port in expected_ports.items():
        peer = peer_sockets.get(name)
        require(peer is not None, f"{phase} {name} peer socket is missing")
        require(peer.fileno() >= 0, f"{phase} {name} peer socket is closed")
        require(
            peer.getsockname() == ("127.0.0.1", port),
            f"{phase} {name} peer socket is not bound to port {port}",
        )


def validate_peer_source(address, client_port, phase, name):
    require(address[0] == "127.0.0.1", f"{phase} {name} source was {address[0]}")
    require(
        address[1] == client_port,
        f"{phase} {name} source port was {address[1]}, expected {client_port}",
    )


def validate_sdp_offer(message, phase, name):
    require(
        normalized(first_header(message, "Content-Type")).startswith("application/sdp"),
        f"{phase} {name} request did not carry application/sdp",
    )
    require(message["body"].startswith(b"v=0\r\n"), f"{phase} {name} SDP offer malformed")
    content_length = int(first_header(message, "Content-Length"))
    require(content_length == len(message["body"]), f"{phase} {name} SDP length mismatch")


def validate_phase_a_invite(packet, address, client_port, name, target):
    validate_peer_source(address, client_port, "phase-a", name)
    message = parse_sip(packet)
    parts = message["first_line"].split()
    require(
        len(parts) == 3 and parts[0] == "INVITE" and parts[2] == "SIP/2.0",
        f"phase-a {name} was not a valid initial INVITE",
    )
    require(normalized(parts[1]) == normalized(target), f"phase-a {name} target mismatch")
    call_id = first_header(message, "Call-ID")
    local_tag = address_tag(first_header(message, "From"))
    require(bool(call_id), f"phase-a {name} Call-ID was empty")
    require(bool(local_tag), f"phase-a {name} From-tag was empty")
    require(not address_tag(first_header(message, "To")), f"phase-a {name} had a To-tag")
    sequence, method = cseq(message)
    require(sequence == 1 and method == "INVITE", f"phase-a {name} CSeq was not 1 INVITE")
    require(not header_values(message, "Route"), f"phase-a {name} initial request had Route")
    validate_sdp_offer(message, "phase-a", name)
    return message, call_id, local_tag, sequence


def state_from_phase_a(name, peer_port, request, response, cseq_number):
    contact = uri_value(first_header(response, "Contact"))
    routes = [uri_value(value) for value in header_values(response, "Record-Route")]
    routes.reverse()
    require(bool(contact), f"phase-a {name} response Contact was empty")
    require(bool(routes), f"phase-a {name} response Record-Route was empty")
    require(
        address_tag(first_header(response, "To")) == REMOTE_TAGS[name],
        f"phase-a {name} response To-tag differed from its configured stable tag",
    )
    return {
        "name": name,
        "peer_port": peer_port,
        "dialog_set_id": {
            "call_id": first_header(request, "Call-ID"),
            "local_tag": address_tag(first_header(request, "From")),
        },
        "remote_to_tag": address_tag(first_header(response, "To")),
        "remote_target_contact": contact,
        "route_set": routes,
        "last_cseq": cseq_number,
        "business_context_key": LOGICAL_TOKEN,
        "phase_a_ack_confirmed": False,
    }


def validate_ack(packet, address, client_port, name, state, phase):
    validate_peer_source(address, client_port, phase, name)
    message = parse_sip(packet)
    parts = message["first_line"].split()
    require(
        len(parts) == 3 and parts[0] == "ACK" and parts[2] == "SIP/2.0",
        f"{phase} {name} DUM did not send ACK",
    )
    require(
        normalized(parts[1]) == normalized(state["remote_target_contact"]),
        f"{phase} {name} ACK Request-URI differed from the retained remote target",
    )
    identity = state["dialog_set_id"]
    require(first_header(message, "Call-ID") == identity["call_id"], f"{phase} {name} ACK Call-ID differed")
    require(address_tag(first_header(message, "From")) == identity["local_tag"], f"{phase} {name} ACK From-tag differed")
    require(address_tag(first_header(message, "To")) == state["remote_to_tag"], f"{phase} {name} ACK To-tag differed")
    sequence, method = cseq(message)
    expected_sequence = state["last_cseq"] if phase == "phase-a" else state["last_cseq"] + 1
    require(
        sequence == expected_sequence and method == "ACK",
        f"{phase} {name} ACK CSeq was {sequence} {method}, expected {expected_sequence} ACK",
    )
    actual_routes = route_values(message)
    expected_routes = state["route_set"]
    require(
        [normalized(route) for route in actual_routes]
        == [normalized(route) for route in expected_routes],
        f"{phase} {name} ACK Route set differed from the retained state",
    )
    return message


def preflight_and_bind(args, artifact_root):
    ports = [args.client_port, args.peer_a_port, args.peer_b_port]
    require(len(set(ports)) == 3, "client and both peer UDP ports must be distinct")
    require(all(1024 <= port <= 65535 for port in ports), "all UDP ports must be in 1024..65535")
    peer_sockets = {}
    preflight = {
        "address": "127.0.0.1",
        "ports": {
            "dum_client": args.client_port,
            "peer_a": args.peer_a_port,
            "peer_b": args.peer_b_port,
        },
        "all_distinct": True,
        "checks": [],
    }
    try:
        for name, port in (("leg-a", args.peer_a_port), ("leg-b", args.peer_b_port)):
            peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            peer.bind(("127.0.0.1", port))
            peer_sockets[name] = peer
            preflight["checks"].append(
                {"name": name, "port": port, "bound_and_reserved": True}
            )
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.bind(("127.0.0.1", args.client_port))
        finally:
            probe.close()
        preflight["checks"].append(
            {
                "name": "dum-client",
                "port": args.client_port,
                "bind_preflight_passed": True,
                "probe_socket_closed_before_child": True,
            }
        )
        preflight["completed_before_phase_a"] = True
        write_json_atomic(artifact_root / "port-preflight.json", preflight)
        return peer_sockets
    except Exception:
        for peer in peer_sockets.values():
            peer.close()
        preflight["completed_before_phase_a"] = False
        write_json_atomic(artifact_root / "port-preflight.json", preflight)
        raise


def start_child(phase, args, artifact_root, snapshot_path):
    command = [
        sys.executable,
        str(ROOT / "dum_child.py"),
        "--phase",
        phase,
        "--client-port",
        str(args.client_port),
        "--snapshot",
        str(snapshot_path),
    ]
    if phase == "phase-a":
        command.extend(["--peer-a-port", str(args.peer_a_port)])
        command.extend(["--peer-b-port", str(args.peer_b_port)])
    phase_name = phase.replace("-", "_")
    write_json_atomic(
        artifact_root / "processes" / f"{phase_name}-command.json",
        {"argv": command, "working_directory": str(ROOT)},
    )
    log_path = artifact_root / "logs" / f"{phase_name}-child.log"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            env=environment,
        )
    write_json_atomic(
        artifact_root / "processes" / f"{phase_name}-start.json",
        {"pid": process.pid, "command": command, "log": str(log_path)},
    )
    print(f"CHILD_STARTED phase={phase} pid={process.pid} log={log_path}", flush=True)
    return process


def wait_child(process, timeout, phase, artifact_root):
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ProbeFailure(
            f"{phase} child PID {process.pid} did not exit within {timeout:.1f}s"
        ) from error
    record = {
        "pid": process.pid,
        "return_code": return_code,
        "wait_reaped": process.poll() is not None,
        "procfs_entry_after_wait": Path(f"/proc/{process.pid}").exists(),
        "wait_observed_monotonic_ns": time.monotonic_ns(),
    }
    phase_name = phase.replace("-", "_")
    write_json_atomic(artifact_root / "processes" / f"{phase_name}-exit.json", record)
    print(
        f"CHILD_REAPED phase={phase} pid={process.pid} "
        f"exit={return_code} procfs_present={record['procfs_entry_after_wait']}",
        flush=True,
    )
    return record


def stop_child(process, phase, artifact_root):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        return_code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        return_code = process.wait(timeout=2)
    write_json_atomic(
        artifact_root / "processes" / f"{phase}-forced-stop.json",
        {"pid": process.pid, "return_code": return_code, "forced_after_failure": True},
    )


def wait_phase_a_acks(peer_sockets, recorder, process, args, peer_states, requests, responses):
    pending = set(LEG_NAMES)
    deadline = time.monotonic() + args.timeout
    while pending:
        name, packet, address = receive_any(peer_sockets, recorder, "phase-a", deadline, process)
        if packet == requests[name]:
            send_peer(peer_sockets[name], recorder, "phase-a", responses[name], address, name)
            continue
        validate_ack(packet, address, args.client_port, name, peer_states[name], "phase-a")
        peer_states[name]["phase_a_ack_confirmed"] = True
        pending.discard(name)
        print(f"PEER_ACK_CONFIRMED phase=phase-a peer={name}", flush=True)


def validate_phase_b_invite(packet, address, client_port, name, peer_state, snapshot_leg):
    validate_peer_source(address, client_port, "phase-b", name)
    require(peer_state["phase_a_ack_confirmed"], f"phase-b {name} peer state was not ACK-confirmed")
    message = parse_sip(packet)
    parts = message["first_line"].split()
    require(
        len(parts) == 3 and parts[0] == "INVITE" and parts[2] == "SIP/2.0",
        f"phase-b {name} was not an in-dialog re-INVITE",
    )
    identity = peer_state["dialog_set_id"]
    require(first_header(message, "Call-ID") == identity["call_id"], f"phase-b {name} Call-ID differed from Phase A")
    require(address_tag(first_header(message, "From")) == identity["local_tag"], f"phase-b {name} From-tag differed from Phase A")
    require(address_tag(first_header(message, "To")) == peer_state["remote_to_tag"], f"phase-b {name} To-tag differed from Phase A")
    require(
        normalized(parts[1]) == normalized(peer_state["remote_target_contact"]),
        f"phase-b {name} Request-URI differed from the retained Contact",
    )
    require(
        snapshot_leg["dialog_set_id"] == identity
        and snapshot_leg["remote_to_tag"] == peer_state["remote_to_tag"]
        and snapshot_leg["remote_target_contact"] == peer_state["remote_target_contact"]
        and snapshot_leg["route_set"] == peer_state["route_set"]
        and snapshot_leg["last_cseq"] == peer_state["last_cseq"],
        f"phase-b {name} request does not match both peer memory and JSON snapshot",
    )
    number, method = cseq(message)
    require(method == "INVITE", f"phase-b {name} CSeq method was not INVITE")
    require(number == peer_state["last_cseq"] + 1, f"phase-b {name} CSeq was not exactly last_cseq + 1")
    actual_routes = route_values(message)
    require(
        [normalized(route) for route in actual_routes]
        == [normalized(route) for route in peer_state["route_set"]],
        f"phase-b {name} Route headers differed from Phase-A routing state",
    )
    validate_sdp_offer(message, "phase-b", name)
    return message, number


def validate_200_correlation(packet, request, peer_state, expected_cseq, phase):
    response = parse_sip(packet)
    require(response["first_line"] == "SIP/2.0 200 OK", f"{phase} {peer_state['name']} peer did not create a 200 OK")
    require(first_header(response, "Call-ID") == first_header(request, "Call-ID"), f"{phase} {peer_state['name']} 200 Call-ID was not correlated")
    require(address_tag(first_header(response, "From")) == address_tag(first_header(request, "From")), f"{phase} {peer_state['name']} 200 From-tag was not correlated")
    require(address_tag(first_header(response, "To")) == peer_state["remote_to_tag"], f"{phase} {peer_state['name']} 200 To-tag was not correlated")
    number, method = cseq(response)
    require(number == expected_cseq and method == "INVITE", f"{phase} {peer_state['name']} 200 CSeq was not correlated")
    require(
        normalized(first_header(response, "Content-Type")).startswith("application/sdp")
        and response["body"].startswith(b"v=0\r\n"),
        f"{phase} {peer_state['name']} 200 did not carry an SDP answer",
    )
    require(int(first_header(response, "Content-Length")) == len(response["body"]), f"{phase} {peer_state['name']} 200 SDP length mismatch")
    if phase == "phase-b":
        response_routes = [
            uri_value(value) for value in header_values(response, "Record-Route")
        ]
        response_routes.reverse()
        if response_routes:
            require(
                [normalized(route) for route in response_routes]
                == [normalized(route) for route in peer_state["route_set"]],
                f"phase-b {peer_state['name']} 200 Record-Route differed from the saved Route set",
            )
    return response


def compare_snapshot(snapshot, peer_states, phase_a_pid):
    require(snapshot.get("schema_version") == 1, "app snapshot schema version mismatch")
    require(snapshot.get("logical_call_token") == LOGICAL_TOKEN, "app snapshot token mismatch")
    require(snapshot.get("created_by_pid") == phase_a_pid, "snapshot was not written by child A")
    snapshot_legs = snapshot.get("legs")
    require(isinstance(snapshot_legs, list) and len(snapshot_legs) == 2, "snapshot leg count mismatch")
    by_name = {leg.get("name"): leg for leg in snapshot_legs}
    require(set(by_name) == set(LEG_NAMES), "snapshot did not contain the two expected legs")
    for name in LEG_NAMES:
        saved = by_name[name]
        peer = peer_states[name]
        require(saved["dialog_set_id"] == peer["dialog_set_id"], f"snapshot DialogSetId differed from parent peer state for {name}")
        require(saved["remote_to_tag"] == peer["remote_to_tag"], f"snapshot To-tag mismatch for {name}")
        require(saved["remote_target_contact"] == peer["remote_target_contact"], f"snapshot remote target mismatch for {name}")
        require(saved["route_set"] == peer["route_set"], f"snapshot Route set mismatch for {name}")
        require(saved["last_cseq"] == peer["last_cseq"], f"snapshot CSeq mismatch for {name}")
        require(saved["business_context_key"] == LOGICAL_TOKEN, f"snapshot app token mismatch for {name}")
        require(
            not any("handle" in key.lower() or "pointer" in key.lower() for key in saved),
            f"snapshot improperly contains DUM handle material for {name}",
        )
    return by_name


def run(args):
    artifact_root = args.artifact_root.resolve()
    for directory in ("logs", "processes", "messages"):
        (artifact_root / directory).mkdir(parents=True, exist_ok=True)
    recorder = Recorder(artifact_root)
    failures = []
    peer_sockets = {}
    active_process = None
    peer_states = {}
    lifecycle = {
        "parent_pid": os.getpid(),
        "logical_call_token": LOGICAL_TOKEN,
        "client_address": ["127.0.0.1", args.client_port],
        "peer_addresses": {
            "leg-a": ["127.0.0.1", args.peer_a_port],
            "leg-b": ["127.0.0.1", args.peer_b_port],
        },
        "peer_sockets_bound_before_phase_a": False,
        "peer_sockets_bound_after_phase_a": False,
        "peer_sockets_bound_before_phase_b": False,
        "peer_sockets_bound_after_phase_b": False,
        "peer_sockets_kept_bound_through_both_phases": False,
        "events": [],
    }
    try:
        peer_sockets = preflight_and_bind(args, artifact_root)
        lifecycle["peer_sockets_bound_before_phase_a"] = True
        lifecycle["peer_sockets_kept_bound_through_both_phases"] = False
        peer_ports = {"leg-a": args.peer_a_port, "leg-b": args.peer_b_port}
        assert_peer_sockets_bound(peer_sockets, peer_ports, "after-bind")
        targets = {
            name: f"sip:uas-{name}@127.0.0.1:{peer_ports[name]};transport=udp"
            for name in LEG_NAMES
        }
        routes = {
            name: [f"sip:127.0.0.1:{peer_ports[name]};lr;transport=udp"]
            for name in LEG_NAMES
        }
        snapshot_path = artifact_root / "snapshot.json"

        phase_a_start = time.monotonic_ns()
        active_process = start_child("phase-a", args, artifact_root, snapshot_path)
        phase_a_process = active_process
        lifecycle["events"].append(
            {"event": "phase-a-start", "pid": phase_a_process.pid, "monotonic_ns": phase_a_start}
        )
        phase_a_requests = {}
        phase_a_responses = {}
        while len(peer_states) < 2:
            name, packet, address = receive_any(
                peer_sockets,
                recorder,
                "phase-a",
                time.monotonic() + args.timeout,
                phase_a_process,
            )
            if name in phase_a_requests:
                if packet != phase_a_requests[name]:
                    raise ProbeFailure(f"phase-a {name} sent a different second initial INVITE")
                send_peer(peer_sockets[name], recorder, "phase-a", phase_a_responses[name], address, name)
                continue
            request, call_id, local_tag, initial_cseq = validate_phase_a_invite(
                packet, address, args.client_port, name, targets[name]
            )
            require(
                call_id not in {state["dialog_set_id"]["call_id"] for state in peer_states.values()},
                "Phase-A legs unexpectedly shared a Call-ID",
            )
            require(
                local_tag not in {state["dialog_set_id"]["local_tag"] for state in peer_states.values()},
                "Phase-A legs unexpectedly shared a local From-tag",
            )
            provisional_state = {
                "name": name,
                "remote_to_tag": REMOTE_TAGS[name],
                "remote_target_contact": targets[name],
                "route_set": routes[name],
            }
            response_packet = make_200(packet, provisional_state, "phase-a")
            response = parse_sip(response_packet)
            validate_200_correlation(
                response_packet, request, provisional_state, initial_cseq, "phase-a"
            )
            state = state_from_phase_a(name, peer_ports[name], request, response, initial_cseq)
            state["phase_a_request_sha256"] = hashlib.sha256(packet).hexdigest()
            state["phase_a_response_sha256"] = hashlib.sha256(response_packet).hexdigest()
            peer_states[name] = state
            phase_a_requests[name] = packet
            phase_a_responses[name] = response_packet
            response_event = recorder.record(
                "phase-a", "peer-to-child", response_packet, address, name
            )
            sent = peer_sockets[name].sendto(response_packet, address)
            if sent != len(response_packet):
                raise ProbeFailure(f"short Phase-A 200 send to {name}")
            state["phase_a_response_wire_path"] = response_event["path"]
            print(
                f"PEER_PHASE_A_ESTABLISHED peer={name} call_id={call_id} "
                f"local_tag={local_tag} remote_tag={state['remote_to_tag']} cseq={initial_cseq}",
                flush=True,
            )

        wait_phase_a_acks(
            peer_sockets,
            recorder,
            phase_a_process,
            args,
            peer_states,
            phase_a_requests,
            phase_a_responses,
        )
        for name in LEG_NAMES:
            require(peer_states[name]["phase_a_ack_confirmed"], f"Phase-A {name} ACK was not confirmed")
        assert_peer_sockets_bound(peer_sockets, peer_ports, "phase-a-end")
        lifecycle["peer_sockets_bound_after_phase_a"] = True
        phase_a_exit = wait_child(phase_a_process, args.child_timeout, "phase-a", artifact_root)
        lifecycle["events"].append(
            {
                "event": "phase-a-reaped",
                "pid": phase_a_process.pid,
                "return_code": phase_a_exit["return_code"],
                "monotonic_ns": phase_a_exit["wait_observed_monotonic_ns"],
                "procfs_entry_after_wait": phase_a_exit["procfs_entry_after_wait"],
            }
        )
        require(phase_a_exit["return_code"] == 0, "child A did not exit successfully")
        require(not phase_a_exit["procfs_entry_after_wait"], "child A still exists in procfs after wait")
        active_process = None
        lifecycle["phase_a_pid"] = phase_a_exit["pid"]
        lifecycle["phase_a_exit_code"] = phase_a_exit["return_code"]
        lifecycle["phase_a_procfs_absent"] = not phase_a_exit["procfs_entry_after_wait"]

        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_legs = compare_snapshot(snapshot, peer_states, phase_a_exit["pid"])
        assert_peer_sockets_bound(peer_sockets, peer_ports, "phase-b-start")
        lifecycle["peer_sockets_bound_before_phase_b"] = True
        phase_b_start = time.monotonic_ns()
        require(phase_b_start > phase_a_exit["wait_observed_monotonic_ns"], "Phase B started before child A was reaped")
        require(not Path(f"/proc/{phase_a_exit['pid']}").exists(), "child A PID exists immediately before phase B")
        phase_b_process = start_child("phase-b", args, artifact_root, snapshot_path)
        active_process = phase_b_process
        lifecycle["phase_a_reaped_before_phase_b_start"] = True
        lifecycle["phase_b_pid"] = phase_b_process.pid
        lifecycle["events"].append(
            {"event": "phase-b-start", "pid": phase_b_process.pid, "monotonic_ns": phase_b_start}
        )
        require(phase_b_process.pid != phase_a_exit["pid"], "child PIDs were not distinct")

        for name in LEG_NAMES:
            observed_name, packet, address = receive_any(
                peer_sockets,
                recorder,
                "phase-b",
                time.monotonic() + args.timeout,
                phase_b_process,
            )
            require(
                observed_name == name,
                f"Phase-B requests were not sequential: expected {name}, got {observed_name}",
            )
            state = peer_states[name]
            request, request_cseq = validate_phase_b_invite(
                packet, address, args.client_port, name, state, snapshot_legs[name]
            )
            response_packet = make_200(packet, state, "phase-b")
            response = validate_200_correlation(
                response_packet, request, state, request_cseq, "phase-b"
            )
            state["phase_b_response_record_route_present"] = bool(
                header_values(response, "Record-Route")
            )
            state["phase_b_request_sha256"] = hashlib.sha256(packet).hexdigest()
            state["phase_b_request_validated"] = True
            state["phase_b_response_sha256"] = hashlib.sha256(response_packet).hexdigest()
            response_event = recorder.record(
                "phase-b", "peer-to-child", response_packet, address, name
            )
            sent = peer_sockets[name].sendto(response_packet, address)
            if sent != len(response_packet):
                raise ProbeFailure(f"short Phase-B 200 send to {name}")
            state["phase_b_response_wire_path"] = response_event["path"]
            wait_deadline = time.monotonic() + args.timeout
            while True:
                ack_name, ack_packet, ack_address = receive_any(
                    peer_sockets,
                    recorder,
                    "phase-b",
                    wait_deadline,
                    phase_b_process,
                )
                if ack_name == name and ack_packet == packet:
                    send_peer(
                        peer_sockets[name],
                        recorder,
                        "phase-b",
                        response_packet,
                        ack_address,
                        name,
                    )
                    continue
                require(
                    ack_name == name,
                    f"Phase-B {ack_name} request arrived before {name} ACK was confirmed",
                )
                ack = validate_ack(
                    ack_packet, ack_address, args.client_port, name, state, "phase-b"
                )
                state["phase_b_ack_route_set"] = route_values(ack)
                state["phase_b_route_set_retained"] = True
                state["phase_b_ack_confirmed"] = True
                print(
                    f"PEER_ACK_CONFIRMED phase=phase-b peer={name} "
                    f"route_set={state['phase_b_ack_route_set']}",
                    flush=True,
                )
                break

        phase_b_exit = wait_child(phase_b_process, args.child_timeout, "phase-b", artifact_root)
        lifecycle["events"].append(
            {
                "event": "phase-b-reaped",
                "pid": phase_b_process.pid,
                "return_code": phase_b_exit["return_code"],
                "monotonic_ns": phase_b_exit["wait_observed_monotonic_ns"],
                "procfs_entry_after_wait": phase_b_exit["procfs_entry_after_wait"],
            }
        )
        require(phase_b_exit["return_code"] == 0, "child B did not exit successfully")
        require(not phase_b_exit["procfs_entry_after_wait"], "child B still exists in procfs after wait")
        active_process = None
        lifecycle["phase_b_exit_code"] = phase_b_exit["return_code"]
        lifecycle["phase_b_procfs_absent"] = not phase_b_exit["procfs_entry_after_wait"]
        for name in LEG_NAMES:
            require(peer_states[name]["phase_b_request_validated"], f"Phase-B {name} request was not validated")
            require(peer_states[name]["phase_b_ack_confirmed"], f"Phase-B {name} ACK was not confirmed")
            require(peer_states[name]["phase_b_route_set_retained"], f"Phase-B {name} ACK did not retain the supplied Route set")
        assert_peer_sockets_bound(peer_sockets, peer_ports, "phase-b-end")
        lifecycle["peer_sockets_bound_after_phase_b"] = True

        write_json_atomic(artifact_root / "parent-peer-state.json", peer_states)
        return 0
    except Exception as error:
        failures.append({"phase": "harness", "detail": str(error)})
        lifecycle["error"] = str(error)
        print(f"HARNESS_FAIL error={error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if active_process is not None:
            stop_child(active_process, "active-child", artifact_root)
        for peer in peer_sockets.values():
            peer.close()
        if peer_states:
            write_json_atomic(artifact_root / "parent-peer-state.json", peer_states)
        lifecycle["finished_monotonic_ns"] = time.monotonic_ns()
        lifecycle["peer_sockets_closed_after_run"] = bool(peer_sockets) and all(
            peer.fileno() < 0 for peer in peer_sockets.values()
        )
        lifecycle["peer_sockets_kept_bound_through_both_phases"] = (
            lifecycle.get("phase_a_exit_code") == 0
            and lifecycle.get("peer_sockets_bound_after_phase_a", False)
            and lifecycle.get("peer_sockets_bound_before_phase_b", False)
            and lifecycle.get("phase_b_exit_code") == 0
            and lifecycle.get("peer_sockets_bound_after_phase_b", False)
        )
        write_json_atomic(artifact_root / "process-lifecycle.json", lifecycle)
        write_json_atomic(artifact_root / "failures.json", {"failures": failures})
        write_json_atomic(
            artifact_root / "validation.json",
            {"passed": not failures, "failures": failures},
        )
        lines = ["PASS" if not failures else "FAIL"]
        lines.extend(f"{failure['phase']}: {failure['detail']}" for failure in failures)
        (artifact_root / "validation.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("HARNESS_RESULT=" + ("PASS" if not failures else "FAIL"), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-port", type=int, default=52641)
    parser.add_argument("--peer-a-port", type=int, default=52642)
    parser.add_argument("--peer-b-port", type=int, default=52643)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--child-timeout", type=float, default=18.0)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    if not 2.0 <= args.timeout <= 30.0:
        parser.error("timeout must be between 2 and 30 seconds")
    if not args.timeout < args.child_timeout <= 45.0:
        parser.error("child-timeout must be greater than timeout and at most 45 seconds")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())