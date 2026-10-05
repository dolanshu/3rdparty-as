"""Unit tests for the transport ingress gate and plaintext TLS helper."""

from __future__ import annotations

import pytest

from as_platform.sip.ingress import TransportIngressGate, reject_plaintext_when_tls_required
from as_platform.sip.transport import PeerIdentity, PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.unit

_TLS = TlsConfig(
    certificate_path="/etc/as/tls/as.pem",
    private_key_path="/etc/as/tls/as.key",
    ca_path="/etc/as/tls/ca.pem",
)


def _policy(addresses: set[str]) -> PeerPolicy:
    return PeerPolicy(
        allowed_addresses=frozenset(addresses),
        allowed_certificate_ids=frozenset(),
    )


def _seam(addresses: set[str], version: int = 1) -> TransportSeam:
    return TransportSeam(tls=_TLS, peer_policy=_policy(addresses), config_version=version)


def test_gate_check_peer_uses_installed_seam() -> None:
    gate = TransportIngressGate(_seam({"10.0.0.1"}))
    allowed = PeerIdentity(address="10.0.0.1", port=5060)
    denied = PeerIdentity(address="10.0.0.2", port=5060)

    assert gate.check_peer(allowed) is True
    assert gate.check_peer(denied) is False


def test_gate_install_swaps_policy_for_new_checks() -> None:
    gate = TransportIngressGate(_seam({"10.0.0.1"}, version=1))
    peer = PeerIdentity(address="10.0.0.2", port=5060)

    assert gate.check_peer(peer) is False

    previous = gate.install(_seam({"10.0.0.2"}, version=2))
    assert previous.config_version == 1
    assert gate.check_peer(peer) is True


def test_reject_plaintext_when_tls_not_required() -> None:
    assert reject_plaintext_when_tls_required(False, "udp") is False
    assert reject_plaintext_when_tls_required(False, "tcp") is False


def test_reject_plaintext_when_tls_required_denies_plain_transports() -> None:
    assert reject_plaintext_when_tls_required(True, "udp") is True
    assert reject_plaintext_when_tls_required(True, "tcp") is True


def test_reject_plaintext_when_tls_required_allows_tls_transports() -> None:
    assert reject_plaintext_when_tls_required(True, "tls") is False
    assert reject_plaintext_when_tls_required(True, "sips") is False
    assert reject_plaintext_when_tls_required(True, "TLS") is False
