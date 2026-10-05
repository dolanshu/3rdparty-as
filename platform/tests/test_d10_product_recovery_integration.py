"""M7.6 product-path D10 recovery integration (engineering; not REQ-NF-1 sign-off)."""

from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

from as_platform.sip.resip_recovery import RecoveryStackSession, load_resip_recovery_extension
from as_platform.state.call_checkpoint import (
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.in_memory import InMemoryStateStore

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "two_leg_udp_peer.py"
_spec = importlib.util.spec_from_file_location("two_leg_udp_peer", _FIXTURE_PATH)
assert _spec is not None and _spec.loader is not None
_peer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_peer)
bind_udp = _peer.bind_udp
reserve_udp_port = _peer.reserve_udp_port

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TIMEOUT = 8.0


def _checkpoint(uas_call_id: str, uac_call_id: str, peer_port: int) -> CallStateCheckpoint:
    uas = DialogLegCheckpoint(
        call_id=uas_call_id,
        local_tag="as-uas-local",
        remote_tag="upstream-remote",
        local_uri=f"sip:as@{_HOST}",
        remote_uri="sip:upstream@127.0.0.1",
        remote_target="sip:upstream@127.0.0.1",
        route_set=(),
        local_cseq=1,
        remote_cseq=2,
    )
    uac = DialogLegCheckpoint(
        call_id=uac_call_id,
        local_tag="as-uac-local",
        remote_tag="peer-remote",
        local_uri=f"sip:as@{_HOST}",
        remote_uri=f"sip:peer@{_HOST}",
        remote_target=f"sip:peer@{_HOST}:{peer_port}",
        route_set=(),
        local_cseq=3,
        remote_cseq=1,
    )
    return CallStateCheckpoint(state="established", uas_leg=uas, uac_leg=uac)


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


def test_product_recovery_bye_routes_to_peer_and_returns_200() -> None:
    if load_resip_recovery_extension() is None:
        pytest.skip(
            "platform _resip_recovery extension not built; run make m7-platform-recovery-build"
        )

    peer = bind_udp("peer")
    upstream = bind_udp("upstream")
    peer_port = peer.getsockname()[1]
    upstream_port = upstream.getsockname()[1]

    token = uuid.uuid4().hex[:8]
    uas_call_id = f"d10-product-uas-{token}@{_HOST}"
    uac_call_id = f"d10-product-uac-{token}@{_HOST}"
    checkpoint = _checkpoint(uas_call_id, uac_call_id, peer_port)

    store = InMemoryStateStore(now=lambda: 1.0)
    repository = CallStateCheckpointRepository(
        store=store, ttl_seconds=3600, allowed_header_namespaces={}
    )
    repository.save(case="translation", call_key=uas_call_id, checkpoint=checkpoint)

    session = RecoveryStackSession()
    try:
        session.start(checkpoint)
        as_port = session.listen_port
        upstream.sendto(_make_bye(checkpoint, as_port, upstream_port), (_HOST, as_port))

        deadline = time.monotonic() + _TIMEOUT
        saw_peer_bye = False
        while time.monotonic() < deadline:
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
                peer.sendto("\r\n".join(response_lines).encode("latin-1"), (_HOST, as_port))
            if session.status()["downstream_200"]:
                break

        assert saw_peer_bye
        assert session.status()["downstream_200"]
        session.send_upstream_200()

        upstream.settimeout(_TIMEOUT)
        final = b""
        while time.monotonic() < deadline:
            session.process(25)
            try:
                final, _ = upstream.recvfrom(65535)
                if final.startswith(b"SIP/2.0 200"):
                    break
            except OSError:
                continue
        assert final.startswith(b"SIP/2.0 200")
        assert repository.load(case="translation", call_key=uas_call_id) == checkpoint
    finally:
        session.stop()
