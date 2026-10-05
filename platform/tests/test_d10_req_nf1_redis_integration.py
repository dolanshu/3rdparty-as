"""REQ-NF-1 engineering: real Redis checkpoint + recovery BYE (not maintainer sign-off)."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest

from as_platform.runtime.active_calls import ActiveCallSource
from as_platform.runtime.sip_stack_service import SipStackService, SipStackServiceConfig
from as_platform.runtime.transport_env import SipListenConfig
from as_platform.sip.recovery import CallStateRecovery, ProcessStartRestoreResult
from as_platform.sip.recovery_coordinator import RecoveryCoordinator
from as_platform.sip.resip_recovery import RecoveryStackSession, load_resip_recovery_extension
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

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TIMEOUT = 12.0
_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/15"


def _redis_url() -> str:
    return os.environ.get("AS_REDIS_URL", _DEFAULT_REDIS_URL).strip() or _DEFAULT_REDIS_URL


def _require_redis() -> None:
    try:
        import redis
    except ImportError:
        pytest.skip("redis package not installed")
    try:
        client = redis.Redis.from_url(_redis_url())
        client.ping()
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
        "o=as-harness 0 0 IN IP4 127.0.0.1\r\n"
        "s=harness\r\n"
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


def _complete_uas_call(upstream: socket.socket, as_port: int, call_id: str) -> str:
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


def test_req_nf1_redis_save_reload_recovery_bye() -> None:
    """Establish, persist checkpoint in Redis, restore, in-dialog BYE → downstream 200.

    Optional local Redis::

        docker run -p 6379:6379 redis:7

    Uses ``AS_REDIS_URL`` or defaults to ``redis://127.0.0.1:6379/15``. Skips when
    Redis is unreachable. Engineering evidence only — not REQ-NF-1 maintainer sign-off.
    """
    _require_redis()
    _require_native()

    peer = bind_udp("peer")
    upstream = bind_udp("upstream")
    peer_port = peer.getsockname()[1]

    store = RedisStateStore.from_url(_redis_url(), "as", time.time)
    repository = CallStateCheckpointRepository(
        store=store, ttl_seconds=3600, allowed_header_namespaces={}
    )
    active = ActiveCallSource(is_terminating=lambda: False, now=time.monotonic)
    config = SipStackServiceConfig(
        recovery_case="translation",
        accept_all_invites=True,
        recovery_call_keys=(),
        enable_native_restore_on_start=False,
        listen=SipListenConfig(bind_address=_HOST, advertised_address=_HOST),
    )
    service = SipStackService(
        active_calls=active,
        repository=repository,
        config=config,
    )

    token = uuid.uuid4().hex[:8]
    call_id = f"d10-redis-uas-{token}@{_HOST}"

    try:
        service.start()
        as_port = service.listen_port
        to_tag = _complete_uas_call(upstream, as_port, call_id)

        deadline = time.monotonic() + _TIMEOUT
        checkpoint = None
        while time.monotonic() < deadline:
            checkpoint = service.committed_checkpoint(call_id)
            if checkpoint is not None:
                break
            time.sleep(0.05)
        assert checkpoint is not None
        checkpoint = service.rewrite_uas_local_tag(call_id, to_tag)

        uac = checkpoint.uac_leg
        checkpoint = CallStateCheckpoint(
            state="established",
            uas_leg=checkpoint.uas_leg,
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
        repository.save(case="translation", call_key=call_id, checkpoint=checkpoint)
        assert repository.load(case="translation", call_key=call_id) == checkpoint

        service.stop()

        recovery = CallStateRecovery(repository)
        coordinator = RecoveryCoordinator(recovery)
        restore_holder: list[object] = []
        done = threading.Event()

        def on_restored(result: object) -> None:
            restore_holder.append(result)
            done.set()

        coordinator.schedule_restore("translation", (call_id,), on_restored)
        assert done.wait(_TIMEOUT)
        coordinator.shutdown(wait=True)
        restore_result = restore_holder[0]
        assert isinstance(restore_result, ProcessStartRestoreResult)
        assert restore_result.native_recovery_started is True
        recovery.stop_native_recovery_sessions()

        session = RecoveryStackSession()
        try:
            session.start(checkpoint)
            recovery_port = session.listen_port
            upstream_port = upstream.getsockname()[1]
            upstream.sendto(
                _make_bye(checkpoint, recovery_port, upstream_port), (_HOST, recovery_port)
            )

            bye_deadline = time.monotonic() + _TIMEOUT
            saw_peer_bye = False
            while time.monotonic() < bye_deadline:
                session.process(25)
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
                        "\r\n".join(response_lines).encode("latin-1"), (_HOST, recovery_port)
                    )
                if session.status()["downstream_200"]:
                    break

            assert saw_peer_bye
            assert session.status()["downstream_200"]
        finally:
            session.stop()
            recovery.stop_native_recovery_sessions()
    finally:
        peer.close()
        upstream.close()
        with contextlib.suppress(Exception):
            store.delete(store.build_key("translation", "call", call_id))
