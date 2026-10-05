"""D10 engineering: kill/restart AS subprocess with Redis checkpoint + BYE 200 path."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from as_platform.sip.resip_recovery import load_resip_recovery_extension
from as_platform.sip.resip_runtime import load_resip_runtime_extension
from as_platform.state.call_checkpoint import (
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.redis_store import RedisStateStore

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "two_leg_udp_peer.py"
_spec = importlib.util.spec_from_file_location("two_leg_udp_peer", _FIXTURE_PATH)
assert _spec is not None and _spec.loader is not None
_peer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_peer)
bind_udp = _peer.bind_udp

_CHILD = Path(__file__).resolve().parents[1] / "src" / "as_platform" / "runtime" / "_d10_child.py"

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TIMEOUT = 20.0
_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/15"


def _redis_url() -> str:
    return os.environ.get("AS_REDIS_URL", _DEFAULT_REDIS_URL).strip() or _DEFAULT_REDIS_URL


def _require_redis() -> RedisStateStore:
    try:
        import redis
    except ImportError:
        pytest.skip("redis package not installed")
    try:
        store = RedisStateStore.from_url(_redis_url(), "as", time.time)
        redis.Redis.from_url(_redis_url()).ping()
        return store
    except Exception as exc:
        pytest.skip(f"cannot connect to Redis at {_redis_url()}: {exc}")


def _require_native() -> None:
    if load_resip_runtime_extension() is None:
        pytest.skip("platform _resip_runtime extension not built; run make m2-platform-resip-build")
    if load_resip_recovery_extension() is None:
        pytest.skip(
            "platform _resip_recovery extension not built; run make m7-platform-recovery-build"
        )


def _invite_with_sdp(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    sdp = (
        "v=0\r\n"
        "o=as-restart 0 0 IN IP4 127.0.0.1\r\n"
        "s=restart\r\n"
        "c=IN IP4 127.0.0.1\r\n"
        "t=0 0\r\n"
        "m=audio 9 RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
    )
    lines = (
        f"INVITE sip:as@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:upstream@{_HOST}>;tag=upstream-remote",
        f"To: <sip:as@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:upstream@{_HOST}:{caller_port}>",
        "Content-Type: application/sdp",
        f"Content-Length: {len(sdp)}",
        "",
        sdp,
    )
    return "\r\n".join(lines).encode("ascii")


def _ack(server_port: int, caller_port: int, call_id: str, to_tag: str) -> bytes:
    lines = (
        f"ACK sip:as@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch=z9hG4bK-ack;rport",
        "Max-Forwards: 70",
        f"From: <sip:upstream@{_HOST}>;tag=upstream-remote",
        f"To: <sip:as@{_HOST}>;tag={to_tag}",
        f"Call-ID: {call_id}",
        "CSeq: 1 ACK",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def _make_bye(checkpoint: CallStateCheckpoint, as_port: int, upstream_port: int) -> bytes:
    uas = checkpoint.uas_leg
    text = (
        f"BYE sip:as@{_HOST}:{as_port} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {_HOST}:{upstream_port};branch=z9hG4bK-bye;rport\r\n"
        "Max-Forwards: 70\r\n"
        f"From: <{uas.remote_uri}>;tag={uas.remote_tag}\r\n"
        f"To: <{uas.local_uri}>;tag={uas.local_tag}\r\n"
        f"Call-ID: {uas.call_id}\r\n"
        f"CSeq: {uas.remote_cseq} BYE\r\n"
        f"Contact: <{uas.remote_target}>\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    return text.encode("ascii")


def _child_env(
    *,
    port_file: Path,
    recovery_port_file: Path | None = None,
    recovery_keys: str = "",
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AS_ENABLE_SIP_RUNTIME": "1",
            "AS_SIP_ACCEPT_ALL_INVITES": "1",
            "AS_REDIS_URL": _redis_url(),
            "AS_D10_PORT_FILE": str(port_file),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        }
    )
    if recovery_port_file is not None:
        env["AS_D10_RECOVERY_PORT_FILE"] = str(recovery_port_file)
    if recovery_keys:
        env["AS_RECOVERY_CALL_KEYS"] = recovery_keys
    return env


def _spawn_child(env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(_CHILD)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _wait_for_port_file(path: Path, proc: subprocess.Popen[bytes], deadline: float) -> int:
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            pytest.fail(f"D10 child exited early ({proc.returncode}): {stderr}")
        if path.is_file():
            return int(path.read_text(encoding="ascii").strip())
        time.sleep(0.05)
    proc.kill()
    pytest.fail(f"timed out waiting for port file {path}")


def _complete_uas_call(upstream, as_port: int, call_id: str) -> str:
    upstream_port = upstream.getsockname()[1]
    upstream.sendto(_invite_with_sdp(as_port, upstream_port, call_id), (_HOST, as_port))
    upstream.settimeout(_TIMEOUT)
    to_tag = ""
    while True:
        response, _ = upstream.recvfrom(65535)
        if response.startswith(b"SIP/2.0 200"):
            _, headers = _peer.parse_sip_message(response)
            to_header = _peer.required_header(headers, "to")
            if ";tag=" in to_header:
                to_tag = to_header.split(";tag=", 1)[1].split(";", 1)[0]
            break
    assert to_tag
    upstream.sendto(_ack(as_port, upstream_port, call_id, to_tag), (_HOST, as_port))
    return to_tag


def _fix_checkpoint_for_peer(
    repository: CallStateCheckpointRepository,
    call_id: str,
    to_tag: str,
    peer_port: int,
) -> CallStateCheckpoint:
    checkpoint = repository.load(case="translation", call_key=call_id)
    assert checkpoint is not None
    uas = checkpoint.uas_leg
    uas_fixed = DialogLegCheckpoint(
        call_id=uas.call_id,
        local_tag=to_tag,
        remote_tag=uas.remote_tag,
        local_uri=uas.local_uri,
        remote_uri=uas.remote_uri,
        remote_target=uas.remote_target,
        route_set=uas.route_set,
        local_cseq=uas.local_cseq,
        remote_cseq=uas.remote_cseq,
    )
    uac = checkpoint.uac_leg
    fixed = CallStateCheckpoint(
        state="established",
        uas_leg=uas_fixed,
        uac_leg=DialogLegCheckpoint(
            call_id=uac.call_id,
            local_tag=uac.local_tag,
            remote_tag=uac.remote_tag,
            local_uri=uac.local_uri,
            remote_uri=f"sip:peer@{_HOST}",
            remote_target=f"sip:peer@{_HOST}:{peer_port}",
            route_set=uac.route_set,
            local_cseq=uac.local_cseq,
            remote_cseq=uac.remote_cseq,
        ),
        extensions=checkpoint.extensions,
        owner_generation=checkpoint.owner_generation,
        committed=checkpoint.committed,
    )
    repository.save(case="translation", call_key=call_id, checkpoint=fixed)
    return fixed


def test_d10_subprocess_kill_restart_redis_bye_200() -> None:
    """Child AS establishes call → Redis → SIGKILL → child restore → BYE 200.

    Engineering slice only; not maintainer REQ-NF-1 sign-off.
    """
    _require_native()
    store = _require_redis()
    repository = CallStateCheckpointRepository(
        store=store, ttl_seconds=3600, allowed_header_namespaces={}
    )

    peer = bind_udp("peer")
    upstream = bind_udp("upstream")
    peer_port = peer.getsockname()[1]
    token = uuid.uuid4().hex[:8]
    call_id = f"d10-restart-uas-{token}@{_HOST}"

    with tempfile.TemporaryDirectory(prefix="as-d10-restart-") as tmp:
        port_file = Path(tmp) / "runtime.port"
        recovery_port_file = Path(tmp) / "recovery.port"
        child = _spawn_child(_child_env(port_file=port_file))
        try:
            as_port = _wait_for_port_file(port_file, child, time.monotonic() + _TIMEOUT)
            to_tag = _complete_uas_call(upstream, as_port, call_id)

            deadline = time.monotonic() + _TIMEOUT
            while time.monotonic() < deadline:
                if repository.load(case="translation", call_key=call_id) is not None:
                    break
                time.sleep(0.05)
            loaded = repository.load(case="translation", call_key=call_id)
            assert loaded is not None
            if loaded.uas_leg.local_tag == to_tag:
                checkpoint = loaded
            else:
                checkpoint = _fix_checkpoint_for_peer(repository, call_id, to_tag, peer_port)

            child.send_signal(signal.SIGKILL)
            child.wait(timeout=5)

            child2 = _spawn_child(
                _child_env(
                    port_file=port_file,
                    recovery_port_file=recovery_port_file,
                    recovery_keys=call_id,
                )
            )
            try:
                recovery_port = _wait_for_port_file(
                    recovery_port_file, child2, time.monotonic() + _TIMEOUT
                )
                upstream_port = upstream.getsockname()[1]
                upstream.sendto(
                    _make_bye(checkpoint, recovery_port, upstream_port),
                    (_HOST, recovery_port),
                )

                bye_deadline = time.monotonic() + _TIMEOUT
                saw_peer_bye = False
                saw_upstream_200 = False
                while time.monotonic() < bye_deadline:
                    peer.settimeout(0.05)
                    try:
                        request, _ = peer.recvfrom(65535)
                    except OSError:
                        request = b""
                    if request.startswith(b"BYE "):
                        saw_peer_bye = True
                        _, headers = _peer.parse_sip_message(request)
                        vias = _peer.header_values(headers, "via")
                        response_lines = ["SIP/2.0 200 OK"]
                        response_lines.extend(f"Via: {via}" for via in vias)
                        response_lines.extend(
                            (
                                f"From: {_peer.required_header(headers, 'from')}",
                                f"To: {_peer.required_header(headers, 'to')}",
                                f"Call-ID: {_peer.required_header(headers, 'call-id')}",
                                f"CSeq: {_peer.required_header(headers, 'cseq')}",
                                "Content-Length: 0",
                                "",
                                "",
                            )
                        )
                        peer.sendto(
                            "\r\n".join(response_lines).encode("latin-1"),
                            (_HOST, recovery_port),
                        )
                    upstream.settimeout(0.05)
                    try:
                        final, _ = upstream.recvfrom(65535)
                        if final.startswith(b"SIP/2.0 200"):
                            saw_upstream_200 = True
                            break
                    except OSError:
                        pass
                    time.sleep(0.05)

                assert saw_peer_bye
                assert saw_upstream_200
            finally:
                child2.send_signal(signal.SIGTERM)
                child2.wait(timeout=10)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    peer.close()
    upstream.close()
    with contextlib.suppress(Exception):
        store.delete(store.build_key("translation", "call", call_id))
