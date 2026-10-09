"""REQ-S engineering: TLS peer certificate fingerprint policy on product runtime."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from native_extensions import require_resip_runtime_extension

from as_platform.decision import RuleSet
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_GEN_CERT = (
    Path(__file__).resolve().parents[2] / "testbed" / "simulators" / "resip-probe" / "gen-cert.sh"
)
_RESPONSE_TIMEOUT_SECONDS = 10.0


def _require_extension() -> Any:
    return require_resip_runtime_extension()


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


def _certificate_fingerprint_sha256(cert_path: Path) -> str:
    proc = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-noout", "-fingerprint", "-sha256"],
        check=True,
        capture_output=True,
        text=True,
    )
    hex_part = proc.stdout.split("=", 1)[1].strip().replace(":", "").lower()
    return f"sha256:{hex_part}"


def _tls_invite_bytes(server_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sips:+15558675309@{_HOST}:{server_port} SIP/2.0",
        f"Via: SIP/2.0/TLS {_HOST}:5060;branch={branch}",
        "Max-Forwards: 70",
        f"From: <sip:+15551230001@{_HOST}>;tag=as-runtime-tls-policy",
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


def _seam_fingerprint_policy(
    cert: Path,
    key: Path,
    *,
    allowed_certificate_ids: frozenset[str],
) -> TransportSeam:
    return TransportSeam(
        tls=TlsConfig(
            certificate_path=str(cert),
            private_key_path=str(key),
            ca_path=None,
            require_client_certificate=False,
        ),
        peer_policy=PeerPolicy(
            allowed_addresses=frozenset(),
            allowed_certificate_ids=allowed_certificate_ids,
        ),
        config_version=1,
    )


def test_tls_fingerprint_policy_denies_when_token_not_in_allowlist(tmp_path: Path) -> None:
    """REQ-S peer policy: wrong sha256 token → 403 before decide()."""
    _require_extension()
    cert, key = _generate_certs(tmp_path)
    client_cert, client_key = _generate_client_cert(tmp_path, cert, key)
    wrong_fingerprint = "sha256:" + ("0" * 64)
    gate = TransportIngressGate(
        _seam_fingerprint_policy(cert, key, allowed_certificate_ids=frozenset({wrong_fingerprint}))
    )
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), tls_only=True)
    try:
        listener.start()
        assert listener.tls_port is not None
        call_id = f"tls-policy-deny-{uuid.uuid4()}@{_HOST}"
        status = _final_response_status_from_tls(
            client_cert,
            listener.tls_port,
            _tls_invite_bytes(listener.tls_port, call_id),
            key_path=client_key,
            extra_ca=cert,
        )
        assert status == 403
    finally:
        listener.stop()


def test_tls_fingerprint_policy_allows_when_token_in_allowlist(tmp_path: Path) -> None:
    """REQ-S peer policy: matching sha256 token passes ingress; empty rules → 404."""
    _require_extension()
    cert, key = _generate_certs(tmp_path)
    client_cert, client_key = _generate_client_cert(tmp_path, cert, key)
    fingerprint = _certificate_fingerprint_sha256(client_cert)
    gate = TransportIngressGate(
        _seam_fingerprint_policy(cert, key, allowed_certificate_ids=frozenset({fingerprint}))
    )
    listener = ResipRuntimeListener(gate, RuleSet(rules=()), tls_only=True)
    try:
        listener.start()
        assert listener.tls_port is not None
        call_id = f"tls-policy-allow-{uuid.uuid4()}@{_HOST}"
        status = _final_response_status_from_tls(
            client_cert,
            listener.tls_port,
            _tls_invite_bytes(listener.tls_port, call_id),
            key_path=client_key,
            extra_ca=cert,
        )
        assert status == 404
    finally:
        listener.stop()
