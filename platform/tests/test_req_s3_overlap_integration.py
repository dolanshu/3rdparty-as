"""REQ-S-3 product overlap integration: policy window + native reload hook."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from native_extensions import require_resip_runtime_extension

from as_platform.decision import RuleSet
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener
from as_platform.sip.transport import PeerIdentity, PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.integration

_GEN_CERT = (
    Path(__file__).resolve().parents[2] / "testbed" / "simulators" / "resip-probe" / "gen-cert.sh"
)


def _tls_config(cert_dir: Path) -> TlsConfig:
    return TlsConfig(
        certificate_path=str(cert_dir / "cert.pem"),
        private_key_path=str(cert_dir / "key.pem"),
        ca_path=str(cert_dir / "cert.pem"),
        require_client_certificate=False,
    )


def _seam(tls: TlsConfig, *addresses: str, version: int = 1) -> TransportSeam:
    return TransportSeam(
        tls=tls,
        peer_policy=PeerPolicy(
            allowed_addresses=frozenset(addresses),
            allowed_certificate_ids=frozenset(),
        ),
        config_version=version,
    )


def _generate_certs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(["bash", str(_GEN_CERT)], check=True, cwd=directory)


def test_req_s3_overlap_policy_and_native_reload(tmp_path: Path) -> None:
    """Maps test-plan REQ-S-3 engineering bullets (overlap policy + in-process reload)."""
    extension = require_resip_runtime_extension()

    cert_a = tmp_path / "cert-a"
    cert_b = tmp_path / "cert-b"
    _generate_certs(cert_a)
    _generate_certs(cert_b)

    seam_a = _seam(_tls_config(cert_a), "10.0.0.1", version=1)
    seam_b = _seam(_tls_config(cert_b), "10.0.0.2", version=2)
    gate = TransportIngressGate(seam_a)

    native_reload_calls: list[int] = []
    original_reload = extension.reload_certificates

    def tracking_reload(handle: object) -> None:
        native_reload_calls.append(1)
        original_reload(handle)

    extension.reload_certificates = tracking_reload

    overlap_hook = Mock()
    listener_holder: list[ResipRuntimeListener] = []

    def on_overlap_started() -> None:
        overlap_hook()
        listener_holder[0]._reload_certificates_on_overlap()

    listener = ResipRuntimeListener(
        gate,
        RuleSet(rules=()),
        tls_only=True,
        extension=extension,
        on_overlap_started=on_overlap_started,
    )
    listener_holder.append(listener)

    legacy_id = "legacy-req-s3"
    peer_old = PeerIdentity(address="10.0.0.1", port=5061)
    peer_new = PeerIdentity(address="10.0.0.2", port=5061)

    try:
        listener.start()
        gate.register_connection(legacy_id)
        gate.install_with_overlap(seam_b, overlap_seconds=60.0)

        overlap_hook.assert_called_once()
        deadline = time.monotonic() + 2.0
        while not native_reload_calls and time.monotonic() < deadline:
            time.sleep(0.05)
        assert native_reload_calls, "native reload_certificates was not invoked on overlap"

        rotation = gate.tls_rotation
        assert rotation.active.certificate_path == seam_b.tls.certificate_path
        assert rotation.retiring is not None
        assert rotation.retiring.certificate_path == seam_a.tls.certificate_path

        assert gate.check_peer(peer_old, connection_id=legacy_id) is True
        assert gate.check_peer(peer_new, connection_id=legacy_id) is False
        assert gate.check_peer(peer_new, connection_id="fresh-after-overlap") is True
        assert gate.check_peer(peer_old, connection_id="fresh-after-overlap") is False
    finally:
        extension.reload_certificates = original_reload
        listener.stop()
