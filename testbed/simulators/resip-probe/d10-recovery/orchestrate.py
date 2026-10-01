"""Orchestrate the D10 call-state recovery integration probe."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import redis

ROOT = Path(__file__).resolve().parent
REPO = Path(os.environ.get("AS_REPO", str(ROOT.parents[3]))).resolve()
sys.path.insert(0, str(REPO / "platform" / "src"))

from as_platform.state.call_checkpoint import (  # noqa: E402
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.redis_store import RedisStateStore  # noqa: E402

CASE = "translation"
TTL_SECONDS = 3600
MAX_CHECKPOINT_TTL_SECONDS = 2_592_000
PROCESS_TIMEOUT_SECONDS = 25
MIDFLIGHT_TIMEOUT_SECONDS = 12
REDIS_START_TIMEOUT_SECONDS = 15
UNKNOWN_CALL_PREFIX = "d10-unknown-"
LOG_LINES: list[str] = []


def log(message: str) -> None:
    """Record and print one orchestration log message."""
    LOG_LINES.append(message)
    print(message, flush=True)


def require(condition: bool, message: str) -> None:
    """Raise an error when an orchestration invariant is false."""
    if not condition:
        raise RuntimeError(message)


def run_command(label: str, command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output and a bounded runtime."""
    log(f"{label}_COMMAND={shlex.join(command)}")
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        log(f"{label}_EXIT_STATUS=timeout")
        raise RuntimeError(f"{label} exceeded {timeout:g}s") from error
    log(f"{label}_EXIT_STATUS={result.returncode}")
    return result


def allocate_port(sock_type: int, used: set[int], label: str) -> int:
    """Allocate an unused loopback port for the requested socket type."""
    for _ in range(100):
        with socket.socket(socket.AF_INET, sock_type) as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port not in used:
            used.add(port)
            return port
    raise RuntimeError(f"could not allocate a distinct loopback port for {label}")


def allocate_ports() -> dict[str, int]:
    """Allocate and preflight the probe's TCP and UDP ports."""
    used: set[int] = set()
    ports = {
        "redis": allocate_port(socket.SOCK_STREAM, used, "Redis TCP"),
        "as": allocate_port(socket.SOCK_DGRAM, used, "AS UDP"),
        "peer": allocate_port(socket.SOCK_DGRAM, used, "fake peer UDP"),
        "upstream": allocate_port(socket.SOCK_DGRAM, used, "upstream UDP"),
    }
    preflight = [("tcp", ports["redis"])] + [
        ("udp", ports[name]) for name in ("as", "peer", "upstream")
    ]
    for protocol, port in preflight:
        sock_type = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
        with socket.socket(socket.AF_INET, sock_type) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(
                    f"loopback port preflight failed for {protocol} 127.0.0.1:{port}: {error}"
                ) from error
        log(f"PORT_PREFLIGHT_{protocol.upper()}=127.0.0.1:{port}:FREE")
    return ports


def ensure_redis_image(docker: str) -> None:
    """Ensure the Redis image is available locally, pulling it if needed."""
    inspect = run_command(
        "DOCKER_REDIS_IMAGE_INSPECT",
        [docker, "image", "inspect", "redis:7-alpine"],
        timeout=15,
    )
    if inspect.returncode == 0:
        return
    pull = run_command("DOCKER_REDIS_IMAGE_PULL", [docker, "pull", "redis:7-alpine"], timeout=120)
    require(pull.returncode == 0, "could not inspect or pull redis:7-alpine")


def create_redis_container(
    docker: str,
    run_dir: Path,
    redis_port: int,
    run_token: str,
) -> tuple[str, str, Path]:
    """Create and start a Redis container owned by this probe run."""
    name = f"d10-recovery-{run_token[:16]}"
    cid_file = run_dir / "redis-container.id"
    require(not cid_file.exists(), f"refusing to reuse container ID file: {cid_file}")
    owner_label = f"com.as.d10-recovery.owner={run_token}"
    command = [
        docker,
        "create",
        "--cidfile",
        str(cid_file),
        "--name",
        name,
        "--label",
        owner_label,
        "--publish",
        f"127.0.0.1:{redis_port}:6379",
        "--health-cmd",
        "redis-cli ping",
        "--health-interval",
        "1s",
        "--health-timeout",
        "2s",
        "--health-retries",
        "20",
        "redis:7-alpine",
    ]
    created = run_command("DOCKER_REDIS_CREATE", command, timeout=20)
    require(created.returncode == 0, "Docker could not create the disposable Redis container")
    container_id = cid_file.read_text(encoding="ascii").strip()
    require(bool(container_id), "Docker created no container ID file")
    require(
        container_id == created.stdout.strip(),
        "Docker container ID output did not match its cidfile",
    )
    log(f"REDIS_CONTAINER_NAME={name}")
    log(f"REDIS_CONTAINER_ID={container_id}")
    started = run_command("DOCKER_REDIS_START", [docker, "start", container_id], timeout=20)
    require(started.returncode == 0, "Docker could not start the disposable Redis container")
    return name, run_token, cid_file


def cleanup_redis_container(
    docker: str | None,
    expected_name: str,
    owner_token: str,
    cid_file: Path,
) -> None:
    """Remove the Redis container only after verifying this run owns it."""
    if not cid_file.exists():
        log("REDIS_CONTAINER_CLEANUP=not-created")
        return
    candidate_id = cid_file.read_text(encoding="ascii").strip()
    if not candidate_id:
        log("REDIS_CONTAINER_CLEANUP=empty-cidfile")
        return
    if docker is None:
        raise RuntimeError(
            "cannot verify or remove the runner-created Redis container: Docker is unavailable"
        )
    inspected = run_command(
        "DOCKER_REDIS_CLEANUP_INSPECT",
        [
            docker,
            "inspect",
            "--format",
            '{{.Id}}|{{.Name}}|{{ index .Config.Labels "com.as.d10-recovery.owner" }}',
            candidate_id,
        ],
        timeout=10,
    )
    if inspected.returncode != 0:
        log("REDIS_CONTAINER_CLEANUP=container-not-present")
        return
    actual_id, separator, rest = inspected.stdout.strip().partition("|")
    actual_name, separator2, actual_owner = rest.partition("|")
    if (
        not separator
        or not separator2
        or actual_id != candidate_id
        or actual_name != f"/{expected_name}"
        or actual_owner != owner_token
    ):
        raise RuntimeError("refusing to remove a container whose ID, name, or owner label differs")
    removed = run_command("DOCKER_REDIS_REMOVE", [docker, "rm", "-f", candidate_id], timeout=20)
    require(removed.returncode == 0, "could not remove the Redis container created by this runner")
    log(f"REDIS_CONTAINER_CLEANUP=removed:{candidate_id}")


def wait_for_redis(observer: redis.Redis) -> None:
    """Wait until Redis answers a health ping or the startup deadline expires."""
    deadline = time.monotonic() + REDIS_START_TIMEOUT_SECONDS
    last_error: redis.RedisError | None = None
    while time.monotonic() < deadline:
        try:
            if observer.ping():
                log("REDIS_HEALTH_PING=PONG")
                return
        except redis.RedisError as error:
            last_error = error
        time.sleep(0.05)
    raise RuntimeError(
        f"Redis did not become ready within {REDIS_START_TIMEOUT_SECONDS}s: {last_error}"
    ) from last_error


def parse_positive_integer(value: str, field: str) -> int:
    """Parse a positive ASCII decimal field from the phase-A source."""
    if not value.isascii() or not value.isdecimal():
        raise RuntimeError(f"phase-A source field {field} is not a positive decimal integer")
    parsed = int(value)
    require(parsed > 0, f"phase-A source field {field} must be positive")
    return parsed


def read_source_fields(path: Path) -> dict[str, str]:
    """Read and validate the phase-A source-field file."""
    fields: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        name, separator, value = line.partition("=")
        require(bool(separator) and bool(name), f"invalid phase-A source line {line_number}")
        require(name not in fields, f"duplicate phase-A source field: {name}")
        fields[name] = value
    require(fields.get("format") == "d10-phase-a-source-v1", "unsupported phase-A source format")

    expected = {"format"}
    for prefix in ("uas", "uac"):
        for suffix in (
            "call_id",
            "local_tag",
            "remote_tag",
            "local_uri",
            "remote_uri",
            "remote_target",
            "local_cseq",
            "remote_cseq",
            "route_count",
        ):
            expected.add(f"{prefix}_{suffix}")
        route_count = parse_nonnegative_count(fields.get(f"{prefix}_route_count", ""), prefix)
        expected.update(f"{prefix}_route_{index}" for index in range(route_count))
        for suffix in (
            "call_id",
            "local_tag",
            "remote_tag",
            "local_uri",
            "remote_uri",
            "remote_target",
        ):
            require(
                bool(fields.get(f"{prefix}_{suffix}", "").strip()), f"{prefix}_{suffix} is empty"
            )
        parse_positive_integer(fields[f"{prefix}_local_cseq"], f"{prefix}_local_cseq")
        parse_positive_integer(fields[f"{prefix}_remote_cseq"], f"{prefix}_remote_cseq")
        for index in range(route_count):
            require(
                bool(fields[f"{prefix}_route_{index}"].strip()), f"{prefix} route {index} is empty"
            )
    require(set(fields) == expected, "phase-A source has missing or unexpected fields")
    return fields


def parse_nonnegative_count(value: str, field: str) -> int:
    """Parse a bounded route count from the phase-A source."""
    if not value.isascii() or not value.isdecimal():
        raise RuntimeError(f"phase-A source field {field}_route_count is invalid")
    parsed = int(value)
    require(parsed <= 64, f"{field} route set exceeds the probe limit")
    return parsed


def source_routes(fields: dict[str, str], prefix: str) -> tuple[str, ...]:
    """Return one dialog leg's ordered route set from source fields."""
    count = parse_nonnegative_count(fields[f"{prefix}_route_count"], prefix)
    return tuple(fields[f"{prefix}_route_{index}"] for index in range(count))


def checkpoint_from_source(fields: dict[str, str]) -> CallStateCheckpoint:
    """Build a typed call checkpoint from phase-A source fields."""

    def leg(prefix: str) -> DialogLegCheckpoint:
        """Build one typed dialog leg from its prefixed source fields."""
        return DialogLegCheckpoint(
            call_id=fields[f"{prefix}_call_id"],
            local_tag=fields[f"{prefix}_local_tag"],
            remote_tag=fields[f"{prefix}_remote_tag"],
            local_uri=fields[f"{prefix}_local_uri"],
            remote_uri=fields[f"{prefix}_remote_uri"],
            remote_target=fields[f"{prefix}_remote_target"],
            route_set=source_routes(fields, prefix),
            local_cseq=parse_positive_integer(
                fields[f"{prefix}_local_cseq"], f"{prefix}_local_cseq"
            ),
            remote_cseq=parse_positive_integer(
                fields[f"{prefix}_remote_cseq"], f"{prefix}_remote_cseq"
            ),
        )

    return CallStateCheckpoint(state="established", uas_leg=leg("uas"), uac_leg=leg("uac"))


def fields_from_checkpoint(checkpoint: CallStateCheckpoint) -> dict[str, str]:
    """Serialize a checkpoint to the native adapter's field mapping."""
    fields = {"format": "d10-native-checkpoint-v1"}
    for prefix, leg in (("uas", checkpoint.uas_leg), ("uac", checkpoint.uac_leg)):
        fields.update(
            {
                f"{prefix}_call_id": leg.call_id,
                f"{prefix}_local_tag": leg.local_tag,
                f"{prefix}_remote_tag": leg.remote_tag,
                f"{prefix}_local_uri": leg.local_uri,
                f"{prefix}_remote_uri": leg.remote_uri,
                f"{prefix}_remote_target": leg.remote_target,
                f"{prefix}_local_cseq": str(leg.local_cseq),
                f"{prefix}_remote_cseq": str(leg.remote_cseq),
                f"{prefix}_route_count": str(len(leg.route_set)),
            }
        )
        fields.update(
            {f"{prefix}_route_{index}": route for index, route in enumerate(leg.route_set)}
        )
    return fields


def write_native_adapter(path: Path, checkpoint: CallStateCheckpoint) -> None:
    """Write checkpoint fields in the format consumed by the native probe."""
    fields = fields_from_checkpoint(checkpoint)
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in fields.items()),
        encoding="utf-8",
    )


def verify_repository_payload(payload: bytes, checkpoint: CallStateCheckpoint) -> None:
    """Verify that Redis bytes encode the expected checkpoint schema."""
    require(len(payload) <= 16 * 1024, "repository checkpoint exceeds the schema payload limit")
    document: Any = json.loads(payload.decode("utf-8"))
    require(
        isinstance(document, dict)
        and set(document) == {"schema_version", "state", "uas_leg", "uac_leg", "extensions"},
        "repository did not encode the current checkpoint schema",
    )
    require(
        document["schema_version"] == 1 and document["state"] == "established",
        "invalid schema header",
    )
    require(document["extensions"] == [], "probe checkpoint must not contain extension headers")
    leg_fields = {
        "call_id",
        "local_tag",
        "remote_tag",
        "local_uri",
        "remote_uri",
        "remote_target",
        "route_set",
        "local_cseq",
        "remote_cseq",
    }
    for name, expected in (("uas_leg", checkpoint.uas_leg), ("uac_leg", checkpoint.uac_leg)):
        leg = document[name]
        require(isinstance(leg, dict) and set(leg) == leg_fields, f"{name} schema fields differ")
        require(leg["local_uri"] == expected.local_uri, f"{name}.local_uri differs")
        require(leg["remote_uri"] == expected.remote_uri, f"{name}.remote_uri differs")
        require(leg["local_tag"] == expected.local_tag, f"{name}.local_tag differs")
        require(leg["remote_tag"] == expected.remote_tag, f"{name}.remote_tag differs")
        require(leg["remote_target"] == expected.remote_target, f"{name}.remote_target differs")
        require(leg["route_set"] == list(expected.route_set), f"{name}.route_set differs")
        require(leg["local_cseq"] == expected.local_cseq > 0, f"{name}.local_cseq differs")
        require(leg["remote_cseq"] == expected.remote_cseq > 0, f"{name}.remote_cseq differs")


def wait_for_process(process: subprocess.Popen[bytes], label: str) -> int:
    """Wait for a probe process, stopping it if its deadline expires."""
    try:
        return_code = process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise RuntimeError(
            f"{label} exceeded {PROCESS_TIMEOUT_SECONDS}s and was stopped"
        ) from error
    log(f"{label.upper().replace(' ', '_')}_EXIT_STATUS={return_code}")
    return return_code


def run_phase_a(
    binary: Path,
    run_dir: Path,
    ports: dict[str, int],
    run_token: str,
) -> tuple[Path, Path, int]:
    """Run phase A and return its source file, wire log, and process ID."""
    source_path = run_dir / "phase-a-source.fields"
    wire_path = run_dir / "phase-a-wire.log"
    output_path = run_dir / "phase-a.stdout.log"
    command = [
        str(binary),
        "phase-a",
        str(source_path),
        str(wire_path),
        run_token,
        str(ports["as"]),
        str(ports["peer"]),
        str(ports["upstream"]),
    ]
    log(f"PHASE_A_COMMAND={shlex.join(command)}")
    with output_path.open("wb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, cwd=run_dir)
        log(f"PHASE_A_PID={process.pid}")
        return_code = wait_for_process(process, "phase A")
    text = output_path.read_text(encoding="utf-8", errors="replace")
    require(return_code == 0, f"phase A exited {return_code}; see {output_path}")
    for marker in (
        "PHASE_A_UAS_ACCEPTED=1",
        "PHASE_A_DUM_UAC_INVITE_CREATED=1",
        "PHASE_A_DUM_UAC_INVITE_SENT=1",
        "PHASE_A_DUM_UAC_CONNECTED=1",
        "PHASE_A_DUM_UAC_ACK_CONFIRMED=1",
        "PHASE_A_DUM_UAC_PEER_SOURCE_AS_TRANSPORT=1",
        "PHASE_A_SOURCE_FIELDS_WRITTEN=1",
        "PHASE_A_UAS_AND_UAC_LEGS_ESTABLISHED=1",
    ):
        require(marker in text, f"phase A did not report {marker}")
    require(
        source_path.is_file() and wire_path.is_file(),
        "phase A did not emit its source or wire capture",
    )
    log("PHASE_A_PROCESS_EXITED_BEFORE_PHASE_B=1")
    return source_path, wire_path, process.pid


def capture_message(wire: str, label: str) -> str:
    """Extract one labeled SIP message from a wire capture."""
    marker = f"===== {label} =====\n"
    start_marker = wire.find(marker)
    require(start_marker >= 0, f"wire capture is missing {label}")
    start = start_marker + len(marker)
    end = wire.find("\n===== ", start)
    if end < 0:
        end = len(wire)
    return wire[start:end].strip("\r\n")


def message_headers(message: str) -> dict[str, str]:
    """Parse the headers from a captured SIP message."""
    headers: dict[str, str] = {}
    for line in message.splitlines()[1:]:
        if not line:
            break
        name, separator, value = line.partition(":")
        if separator:
            headers[name.strip().lower()] = value.strip()
    return headers


def address_tag(value: str) -> str:
    """Extract the SIP tag parameter from an address, if present."""
    match = re.search(r"(?:^|;)\s*tag=([^;\s]+)", value, re.IGNORECASE)
    return match.group(1) if match else ""


def address_uri(value: str) -> str:
    """Extract the URI from a SIP name-address or bare address."""
    match = re.search(r"<([^>]+)>", value)
    if match:
        return match.group(1).strip()
    return value.split(";", maxsplit=1)[0].strip()


def verify_phase_a_wire(fields: dict[str, str], wire_path: Path, ports: dict[str, int]) -> None:
    """Check phase-A SIP messages against the captured source fields."""
    wire = wire_path.read_text(encoding="utf-8", errors="replace")
    invite = capture_message(wire, "PHASE_A_DUM_UAC_PEER_RX_INVITE")
    peer_200 = capture_message(wire, "PHASE_A_DUM_UAC_PEER_TX_200")
    dum_200 = capture_message(wire, "PHASE_A_DUM_UAC_ON_CONNECTED_200")
    ack = capture_message(wire, "PHASE_A_DUM_UAC_PEER_RX_ACK")
    invite_headers = message_headers(invite)
    peer_200_headers = message_headers(peer_200)
    dum_200_headers = message_headers(dum_200)
    ack_headers = message_headers(ack)

    require(
        invite.splitlines()[0].startswith(f"INVITE sip:peer@127.0.0.1:{ports['peer']} "),
        "phase-A fake peer did not receive the DUM-generated INVITE",
    )
    require(peer_200.startswith("SIP/2.0 200"), "phase-A fake peer did not answer the DUM INVITE")
    require(dum_200.startswith("SIP/2.0 200"), "phase-A DUM did not process the peer 200 response")
    cseq_parts = invite_headers.get("cseq", "").split()
    require(
        len(cseq_parts) == 2 and cseq_parts[1].upper() == "INVITE",
        "phase-A DUM INVITE has an invalid CSeq",
    )
    invite_cseq = parse_positive_integer(cseq_parts[0], "uac_invite_cseq")
    call_id = fields["uac_call_id"]
    require(
        invite_headers.get("call-id") == call_id, "DUM INVITE Call-ID differs from UAC checkpoint"
    )
    require(
        peer_200_headers.get("call-id") == call_id,
        "fake peer 200 Call-ID differs from UAC checkpoint",
    )
    require(
        dum_200_headers.get("call-id") == call_id,
        "DUM-processed 200 Call-ID differs from UAC checkpoint",
    )
    require(peer_200_headers.get("cseq") == f"{invite_cseq} INVITE", "fake peer 200 CSeq differs")
    require(
        dum_200_headers.get("cseq") == f"{invite_cseq} INVITE", "DUM-processed 200 CSeq differs"
    )
    require(
        f"127.0.0.1:{ports['as']}" in invite_headers.get("via", ""),
        "phase-A DUM INVITE Via is not from the AS transport",
    )

    ack_cseq = f"{invite_cseq} ACK"
    require(ack.splitlines()[0].startswith("ACK "), "fake peer did not receive an ACK from DUM")
    require(ack_headers.get("call-id") == call_id, "DUM ACK Call-ID differs from UAC checkpoint")
    require(ack_headers.get("cseq") == ack_cseq, "DUM ACK CSeq differs from its INVITE transaction")
    require(
        address_tag(ack_headers.get("from", "")) == fields["uac_local_tag"],
        "DUM ACK From-tag differs",
    )
    require(
        address_tag(ack_headers.get("to", "")) == fields["uac_remote_tag"], "DUM ACK To-tag differs"
    )
    require(
        f"127.0.0.1:{ports['as']}" in ack_headers.get("via", ""),
        "phase-A DUM ACK Via is not from the AS transport",
    )

    require(
        address_uri(dum_200_headers.get("from", "")) == fields["uac_local_uri"],
        "UAC local URI differs from DUM 200",
    )
    require(
        address_tag(dum_200_headers.get("from", "")) == fields["uac_local_tag"],
        "UAC local tag differs from DUM 200",
    )
    require(
        address_uri(dum_200_headers.get("to", "")) == fields["uac_remote_uri"],
        "UAC remote URI differs from DUM 200",
    )
    require(
        address_tag(dum_200_headers.get("to", "")) == fields["uac_remote_tag"],
        "UAC remote tag differs from DUM 200",
    )
    require(
        address_uri(dum_200_headers.get("contact", "")) == fields["uac_remote_target"],
        "UAC remote target differs from DUM 200",
    )
    require(
        parse_positive_integer(fields["uac_local_cseq"], "uac_local_cseq") == invite_cseq + 1,
        "UAC local CSeq was not derived from the DUM INVITE transaction",
    )
    require(
        parse_positive_integer(fields["uac_remote_cseq"], "uac_remote_cseq") == invite_cseq,
        "UAC remote CSeq differs from the DUM 200 response",
    )

    record_routes = []
    for line in dum_200.splitlines()[1:]:
        if not line:
            break
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == "record-route":
            record_routes.append(value.strip())
    route_count = parse_nonnegative_count(fields["uac_route_count"], "uac")
    require(
        [fields[f"uac_route_{index}"] for index in range(route_count)] == record_routes,
        "UAC route set differs from the DUM 200 response",
    )


def run_phase_b(
    binary: Path,
    run_dir: Path,
    ports: dict[str, int],
    run_token: str,
    checkpoint: CallStateCheckpoint,
    repository: CallStateCheckpointRepository,
    redis_key: str,
    observer: redis.Redis,
) -> tuple[int, Path]:
    """Run phase B while checking the midflight Redis checkpoint."""
    adapter_path = run_dir / "phase-b-typed-checkpoint.fields"
    write_native_adapter(adapter_path, checkpoint)
    wire_path = run_dir / "phase-b-wire.log"
    output_path = run_dir / "phase-b.stdout.log"
    ready_path = run_dir / "phase-b.midflight.ready"
    release_path = run_dir / "phase-b.midflight.release"
    require(
        not ready_path.exists() and not release_path.exists(), "phase-B gate files already exist"
    )
    command = [
        str(binary),
        "phase-b",
        str(adapter_path),
        str(wire_path),
        str(ready_path),
        str(release_path),
        run_token,
        str(ports["as"]),
        str(ports["peer"]),
        str(ports["upstream"]),
    ]
    log(f"PHASE_B_COMMAND={shlex.join(command)}")
    with output_path.open("wb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, cwd=run_dir)
        log(f"PHASE_B_PID={process.pid}")
        try:
            deadline = time.monotonic() + MIDFLIGHT_TIMEOUT_SECONDS
            while not ready_path.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"phase B exited {process.returncode} before the Redis gate")
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"phase B did not reach its Redis gate within {MIDFLIGHT_TIMEOUT_SECONDS}s"
                    )
                time.sleep(0.01)

            require(process.poll() is None, "phase B exited before the midflight Redis check")
            midflight_checkpoint = repository.load(case=CASE, call_key=checkpoint.uas_leg.call_id)
            require(
                midflight_checkpoint == checkpoint, "typed Redis checkpoint changed during phase B"
            )
            ttl = int(observer.ttl(redis_key))
            require(
                0 < ttl <= TTL_SECONDS <= MAX_CHECKPOINT_TTL_SECONDS,
                "midflight Redis TTL is invalid",
            )
            log("PHASE_B_PROCESS_ALIVE_AT_REDIS_CHECK=1")
            log("REDIS_MIDFLIGHT_TYPED_LOAD_EQUAL=1")
            log(f"REDIS_MIDFLIGHT_TTL_SECONDS={ttl}")

            release_path.write_text("release\n", encoding="ascii")
            log("PHASE_B_MIDFLIGHT_RELEASED=1")
            return_code = wait_for_process(process, "phase B")
        except Exception:
            if process.poll() is None:
                if not release_path.exists():
                    release_path.write_text("abort\n", encoding="ascii")
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise

    text = output_path.read_text(encoding="utf-8", errors="replace")
    require(return_code == 0, f"phase B exited {return_code}; see {output_path}")
    for marker in (
        "PHASE_B_FRESH_DUM=1",
        "RECOVERY_TU_MATCHED_BEFORE_DUM=1",
        "RECOVERY_TU_DOWNSTREAM_200_RECEIVED=1",
        "RECOVERY_TU_UPSTREAM_200_QUEUED=1",
        "PHASE_B_RECOVERY_PASS=1",
        "RECOVERY_TU_NONCHECKPOINT_BYE_FILTER_FALSE=1",
        "FRESH_DUM_UNKNOWN_BYE_481=1",
        "UNKNOWN_BYE_NOT_FORWARDED=1",
        "UNKNOWN_BYE_WORKER_ERROR=0",
    ):
        require(marker in text, f"phase B did not report {marker}")
    require("ERROR:" not in text, "phase B reported a native error")
    return process.pid, wire_path


def verify_wire(
    checkpoint: CallStateCheckpoint,
    wire_path: Path,
    ports: dict[str, int],
    run_token: str,
) -> None:
    """Check recovered BYE and unknown-call signaling in the wire log."""
    wire = wire_path.read_text(encoding="utf-8", errors="replace")
    uas = checkpoint.uas_leg
    uac = checkpoint.uac_leg

    known_bye = message_headers(capture_message(wire, "PHASE_B_UPSTREAM_TX_BYE"))
    require(
        known_bye.get("call-id") == uas.call_id, "known BYE Call-ID differs from the UAS checkpoint"
    )
    require(address_tag(known_bye.get("from", "")) == uas.remote_tag, "known BYE From-tag differs")
    require(address_tag(known_bye.get("to", "")) == uas.local_tag, "known BYE To-tag differs")

    peer_bye = capture_message(wire, "FAKE_PEER_RX")
    peer_headers = message_headers(peer_bye)
    require(
        peer_headers.get("call-id") == uac.call_id, "downstream BYE Call-ID differs from checkpoint"
    )
    require(
        address_tag(peer_headers.get("from", "")) == uac.local_tag,
        "downstream BYE From-tag differs",
    )
    require(
        address_tag(peer_headers.get("to", "")) == uac.remote_tag, "downstream BYE To-tag differs"
    )
    require(peer_headers.get("cseq") == f"{uac.local_cseq} BYE", "downstream BYE CSeq differs")
    require(
        peer_bye.splitlines()[0].startswith(f"BYE {uac.remote_target} "),
        "downstream BYE target differs from checkpoint",
    )
    require(
        f"127.0.0.1:{ports['as']}" in peer_headers.get("via", ""),
        "downstream BYE Via is not from the fresh AS socket",
    )
    require(
        f"127.0.0.1:{ports['upstream']}" not in peer_headers.get("via", ""),
        "downstream BYE reused the upstream Via",
    )

    peer_200 = capture_message(wire, "FAKE_PEER_TX_200")
    upstream_200 = capture_message(wire, "PHASE_B_UPSTREAM_RX")
    require(peer_200.startswith("SIP/2.0 200"), "fake peer did not send UDP 200")
    require(upstream_200.startswith("SIP/2.0 200"), "upstream did not receive UDP 200")

    unknown_bye = message_headers(capture_message(wire, "PHASE_B_UNKNOWN_UPSTREAM_TX_BYE"))
    unknown_call_id = f"{UNKNOWN_CALL_PREFIX}{run_token}@127.0.0.1"
    require(unknown_bye.get("call-id") == unknown_call_id, "unknown BYE Call-ID is unexpected")
    require(unknown_call_id != uas.call_id, "unknown BYE reused the checkpoint Call-ID")
    unknown_481 = message_headers(capture_message(wire, "PHASE_B_UNKNOWN_UPSTREAM_RX"))
    require(
        capture_message(wire, "PHASE_B_UNKNOWN_UPSTREAM_RX").startswith("SIP/2.0 481"),
        "unknown BYE did not receive fresh DUM's 481",
    )
    require(unknown_481.get("call-id") == unknown_call_id, "481 does not match unknown BYE")
    require("UNEXPECTED_PEER_RX" not in wire, "unknown BYE was observed at the downstream peer")


def run_experiment(run_dir: Path, binary: Path) -> None:
    """Run the end-to-end recovery experiment with disposable Redis."""
    require(
        TTL_SECONDS <= MAX_CHECKPOINT_TTL_SECONDS,
        "probe TTL exceeds the repository's 30-day maximum",
    )
    require(binary.is_file(), f"native probe binary is missing: {binary}")
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError(
            "BLOCKER: docker executable is unavailable; real-Redis integration was not run"
        )

    run_token = uuid.uuid4().hex
    ports = allocate_ports()
    cid_file = run_dir / "redis-container.id"
    container_name = f"d10-recovery-{run_token[:16]}"
    owner_token = run_token
    redis_client: redis.Redis | None = None
    observer: redis.Redis | None = None
    state_store: RedisStateStore | None = None
    repository: CallStateCheckpointRepository | None = None
    owned_key: str | None = None

    try:
        daemon = run_command(
            "DOCKER_INFO",
            [docker, "info", "--format", "{{.ServerVersion}}"],
            timeout=10,
        )
        require(daemon.returncode == 0, "BLOCKER: Docker daemon is unavailable")
        ensure_redis_image(docker)
        created_name, owner_token, cid_file = create_redis_container(
            docker,
            run_dir,
            ports["redis"],
            run_token,
        )
        container_name = created_name
        redis_url = f"redis://127.0.0.1:{ports['redis']}/0"
        redis_client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        observer = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        state_store = RedisStateStore(client=redis_client, now=time.monotonic, namespace="as")
        repository = CallStateCheckpointRepository(
            store=state_store,
            ttl_seconds=TTL_SECONDS,
            allowed_header_namespaces={},
        )
        wait_for_redis(observer)
        log(f"REDIS_SERVER_VERSION={observer.info('server')['redis_version']}")
        log(f"REDIS_URL={redis_url}")

        source_path, phase_a_wire, phase_a_pid = run_phase_a(binary, run_dir, ports, run_token)
        fields = read_source_fields(source_path)
        verify_phase_a_wire(fields, phase_a_wire, ports)
        log("PHASE_A_DUM_UAC_INVITE_200_ACK_CHECK=PASS")
        checkpoint = checkpoint_from_source(fields)
        require(
            checkpoint.uas_leg.call_id != checkpoint.uac_leg.call_id,
            "phase-A dialog legs must have distinct Call-IDs",
        )
        call_key = checkpoint.uas_leg.call_id
        owned_key = state_store.build_key(CASE, "call", call_key)
        log(f"CHECKPOINT_CALL_ID={call_key}")
        log(f"REDIS_KEY={owned_key}")
        log(f"REDIS_TTL_REQUESTED_SECONDS={TTL_SECONDS}")

        repository.save(case=CASE, call_key=call_key, checkpoint=checkpoint)
        log("CHECKPOINT_REPOSITORY_SAVE=PASS")
        loaded = repository.load(case=CASE, call_key=call_key)
        require(
            loaded == checkpoint, "CallStateCheckpointRepository typed round trip changed the value"
        )
        raw_checkpoint = state_store.get(owned_key)
        require(
            raw_checkpoint is not None, "RedisStateStore did not return the repository checkpoint"
        )
        verify_repository_payload(raw_checkpoint, checkpoint)
        ttl_after_write = int(observer.ttl(owned_key))
        require(
            0 < ttl_after_write <= TTL_SECONDS, "Redis checkpoint TTL is absent or out of range"
        )
        log("REDIS_TYPED_REPOSITORY_ROUND_TRIP=PASS")
        log("REDIS_CURRENT_SCHEMA_FIELDS=PASS")
        log(f"REDIS_TTL_AFTER_WRITE_SECONDS={ttl_after_write}")

        log("PHASE_B_CHECKPOINT_SOURCE=CallStateCheckpointRepository.load")
        phase_b_pid, phase_b_wire = run_phase_b(
            binary,
            run_dir,
            ports,
            run_token,
            loaded,
            repository,
            owned_key,
            observer,
        )
        log(f"PHASE_A_PID_REAPED_BEFORE_PHASE_B_PID={phase_a_pid}:{phase_b_pid}")
        verify_wire(loaded, phase_b_wire, ports, run_token)
        log("RAW_UDP_CALL_ID_TAG_TARGET_CSEQ_ASSERTIONS=PASS")
        log("RAW_UDP_PEER_200_AND_UPSTREAM_200=PASS")
        log("RAW_UDP_UNKNOWN_481_AND_NO_FORWARD=PASS")

        final_checkpoint = repository.load(case=CASE, call_key=call_key)
        require(final_checkpoint == checkpoint, "checkpoint disappeared or changed before cleanup")
        require(int(observer.ttl(owned_key)) > 0, "checkpoint TTL expired before terminal cleanup")
        log("REDIS_PRESENT_AFTER_PHASE_B=1")
        state_store.delete(owned_key)
        owned_key = None
        require(
            repository.load(case=CASE, call_key=call_key) is None,
            "repository load found key after delete",
        )
        require(
            int(observer.exists(state_store.build_key(CASE, "call", call_key))) == 0,
            "Redis key remains after delete",
        )
        log("REDIS_STORE_DELETE_EXIT_STATUS=0")
        log("REDIS_DELETE_VERIFIED_ABSENT=1")
    finally:
        cleanup_errors: list[str] = []
        if owned_key is not None and state_store is not None and observer is not None:
            try:
                state_store.delete(owned_key)
                require(
                    int(observer.exists(owned_key)) == 0,
                    "runner-owned Redis checkpoint remains after cleanup",
                )
                log("REDIS_FAILURE_KEY_CLEANUP=removed-runner-key")
            except Exception as error:
                cleanup_errors.append(f"Redis key cleanup failed: {error}")
        if observer is not None:
            observer.close()
        if redis_client is not None:
            redis_client.close()
        try:
            cleanup_redis_container(docker, container_name, owner_token, cid_file)
        except Exception as error:
            cleanup_errors.append(str(error))
        if cleanup_errors:
            raise RuntimeError("; ".join(cleanup_errors))


def main() -> int:
    """Parse options, run the experiment, and persist its log."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    outcome = "FAIL"
    try:
        run_experiment(args.run_dir.resolve(), args.binary.resolve())
        outcome = "PASS"
        log("D10_ORCHESTRATION_RESULT=PASS")
    except Exception as error:
        log(f"D10_ORCHESTRATION_FAILURE={type(error).__name__}: {error}")
        log("D10_ORCHESTRATION_RESULT=FAIL")
    finally:
        (args.run_dir / "orchestrate.log").write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
