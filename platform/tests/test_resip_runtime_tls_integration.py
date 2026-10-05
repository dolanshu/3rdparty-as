"""Integration: product-path reSIProcate TLS listener + ingress gate."""

from __future__ import annotations

import socket
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from as_platform.decision import RuleSet
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener, load_resip_runtime_extension
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_GEN_CERT = (
    Path(__file__).resolve().parents[2] / "testbed" / "simulators" / "resip-probe" / "gen-cert.sh"
)
_RESPONSE_TIMEOUT_SECONDS = 10.0


def _require_extension() -> Any:
    extension = load_resip_runtime_extension()
    if extension is None:
        pytest.skip("platform resip_runtime extension not built; run make m2-platform-resip-build")
    return extension


def _generate_certs(tmp_path: Path) -> tuple[Path, Path]:
    subprocess.run(["bash", str(_GEN_CERT)], check=True, cwd=tmp_path)
    return tmp_path / "cert.pem", tmp_path / "key.pem"


def _generate_client_cert(tmp_path: Path, ca_cert: Path, ca_key: Path) -> tuple[Path, Path]:
    client_key = tmp_path / "client.key"
    client_csr = tmp_path / "client.csr"
    client_cert = tmp_path / "client.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(client_key),
            "-out",
            str(client_csr),
            "-subj",
            "/CN=as-runtime-client",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(client_csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(client_cert),
            "-days",
            "1",
        ],
        check=True,
        capture_output=True,
    )
    return client_cert, client_key


def _make_udp_invite(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP {_HOST}:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=as-runtime-tls-udp",
        f"To: <sip:+15558675309@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@{_HOST}:{caller_port}>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def _tls_invite_bytes(server_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sips:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/TLS {_HOST}:5060;branch={branch}",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=as-runtime-tls",
        f"To: <sip:+15558675309@{_HOST}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sips:+15551230001@{_HOST}:5060>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def _final_response_status_from_tls(
    cert_path: Path,
    server_port: int,
    invite: bytes,
    *,
    key_path: Path | None = None,
    extra_ca: Path | None = None,
) -> int:
    ca_file = extra_ca if extra_ca is not None else cert_path
    cmd = [
        "openssl",
        "s_client",
        "-connect",
        f"{_HOST}:{server_port}",
        "-CAfile",
        str(ca_file),
        "-verify_return_error",
        "-verify_ip",
        _HOST,
        "-quiet",
    ]
    if key_path is not None:
        cmd.extend(["-cert", str(cert_path), "-key", str(key_path)])
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, _stderr = proc.communicate(input=invite, timeout=_RESPONSE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as expired:
        proc.kill()
        stdout = expired.output or b""
        proc.wait(timeout=5)
    for line in stdout.splitlines():
        if not line.startswith(b"SIP/2.0"):
            continue
        fields = line.split()
        if len(fields) >= 2 and fields[1].isdigit() and int(fields[1]) >= 200:
            return int(fields[1])
    raise AssertionError(f"no final SIP response in openssl output: {stdout!r}")


def _seam_tls(
    cert: Path,
    key: Path,
    *,
    require_client_certificate: bool = False,
    allowed_addresses: frozenset[str] = frozenset({_HOST}),
    allowed_certificate_ids: frozenset[str] = frozenset(),
) -> TransportSeam:
    ca_path = str(cert) if require_client_certificate else None
    return TransportSeam(
        tls=TlsConfig(
            certificate_path=str(cert),
            private_key_path=str(key),
            ca_path=ca_path,
            require_client_certificate=require_client_certificate,
        ),
        peer_policy=PeerPolicy(
            allowed_addresses=allowed_addresses,
            allowed_certificate_ids=allowed_certificate_ids,
        ),
        config_version=1,
    )


def test_tls_allowed_peer_empty_ruleset_returns_404(tmp_path: Path) -> None:
    _require_extension()
    cert, key = _generate_certs(tmp_path)
    gate = TransportIngressGate(_seam_tls(cert, key))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), tls_only=True)
    try:
        listener.start()
        assert listener.tls_port is not None
        call_id = f"tls-allowed-{uuid.uuid4()}@{_HOST}"
        status = _final_response_status_from_tls(
            cert,
            listener.tls_port,
            _tls_invite_bytes(listener.tls_port, call_id),
        )
        assert status == 404
    finally:
        listener.stop()


def test_udp_rejected_when_require_client_certificate(tmp_path: Path) -> None:
    _require_extension()
    cert, key = _generate_certs(tmp_path)
    gate = TransportIngressGate(_seam_tls(cert, key, require_client_certificate=True))
    listener = ResipRuntimeListener(gate, RuleSet(rules=()))
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((_HOST, 0))
    call_id = f"tls-reject-udp-{uuid.uuid4()}@{_HOST}"
    try:
        listener.start()
        peer.sendto(
            _make_udp_invite(listener.port, peer.getsockname()[1], call_id),
            (_HOST, listener.port),
        )
        peer.settimeout(_RESPONSE_TIMEOUT_SECONDS)
        response, _ = peer.recvfrom(65535)
        status_line = response.split(b"\r\n", 1)[0]
        assert status_line.split()[1] == b"403"
    finally:
        listener.stop()
        peer.close()


def test_tls_peer_dict_reports_transport_tls(tmp_path: Path) -> None:
    extension = _require_extension()
    cert, key = _generate_certs(tmp_path)
    captured: list[dict[str, Any]] = []

    def on_invite(peer: dict[str, Any], _summary: dict[str, Any]) -> int:
        captured.append(dict(peer))
        return 404

    config = {
        "enable_udp": False,
        "enable_tls": True,
        "tls_only": True,
        "require_client_certificate": False,
        "certificate_path": str(cert),
        "private_key_path": str(key),
        "ca_path": "",
    }
    handle = extension.start(on_invite, config)
    try:
        tls_port = int(extension.get_tls_port(handle))
        call_id = f"tls-transport-{uuid.uuid4()}@{_HOST}"
        _final_response_status_from_tls(
            cert,
            tls_port,
            _tls_invite_bytes(tls_port, call_id),
        )
        assert captured, "expected native callback to run"
        assert captured[0].get("transport") == "tls"
    finally:
        extension.stop(handle)
