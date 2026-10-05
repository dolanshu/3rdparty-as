"""Unit tests for REQ-S-3 TLS overlap state and ingress gate policy."""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest

from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.tls_rotation import TlsRotationState
from as_platform.sip.transport import PeerIdentity, PeerPolicy, TlsConfig, TransportSeam

pytestmark = pytest.mark.unit

_TLS_A = TlsConfig(
    certificate_path="/etc/as/tls/a.pem",
    private_key_path="/etc/as/tls/a.key",
    ca_path="/etc/as/tls/ca.pem",
)
_TLS_B = TlsConfig(
    certificate_path="/etc/as/tls/b.pem",
    private_key_path="/etc/as/tls/b.key",
    ca_path="/etc/as/tls/ca.pem",
)


def _policy(addresses: set[str]) -> PeerPolicy:
    return PeerPolicy(
        allowed_addresses=frozenset(addresses),
        allowed_certificate_ids=frozenset(),
    )


def _seam(tls: TlsConfig, addresses: set[str], version: int = 1) -> TransportSeam:
    return TransportSeam(tls=tls, peer_policy=_policy(addresses), config_version=version)


def test_tls_rotation_state_start_and_expire() -> None:
    state = TlsRotationState(active=_TLS_A)
    now = 1000.0
    overlapped = state.start_overlap(_TLS_B, 30.0, now=now)

    assert overlapped.active == _TLS_B
    assert overlapped.retiring == _TLS_A
    assert overlapped.tls_for_new_connections() == _TLS_B
    assert overlapped.tls_for_existing_connections(now + 1) == _TLS_A
    assert overlapped.tls_for_existing_connections(now + 30) is None

    expired = overlapped.expire(now + 30)
    assert expired.retiring is None
    assert expired.active == _TLS_B


def test_tls_rotation_state_rejects_negative_overlap() -> None:
    state = TlsRotationState(active=_TLS_A)
    with pytest.raises(ValueError, match="overlap_seconds"):
        state.start_overlap(_TLS_B, -1.0, now=0.0)


def test_gate_overlap_legacy_connection_uses_retiring_policy() -> None:
    gate = TransportIngressGate(_seam(_TLS_A, {"10.0.0.1"}, version=1))
    legacy_id = "conn-legacy"
    gate.register_connection(legacy_id)

    peer_old = PeerIdentity(address="10.0.0.1", port=5060)
    peer_new = PeerIdentity(address="10.0.0.2", port=5060)

    gate.install_with_overlap(_seam(_TLS_B, {"10.0.0.2"}, version=2), overlap_seconds=60.0)

    assert gate.check_peer(peer_old, connection_id=legacy_id) is True
    assert gate.check_peer(peer_new, connection_id=legacy_id) is False
    assert gate.check_peer(peer_new, connection_id="conn-fresh") is True
    assert gate.check_peer(peer_old, connection_id="conn-fresh") is False


def test_gate_overlap_expires_to_active_only() -> None:
    gate = TransportIngressGate(_seam(_TLS_A, {"10.0.0.1"}))
    legacy_id = "conn-1"
    gate.register_connection(legacy_id)

    gate.install_with_overlap(_seam(_TLS_B, {"10.0.0.2"}), overlap_seconds=0.0)
    time.sleep(0.01)

    peer_old = PeerIdentity(address="10.0.0.1", port=5060)
    peer_new = PeerIdentity(address="10.0.0.2", port=5060)
    assert gate.check_peer(peer_old, connection_id=legacy_id) is False
    assert gate.check_peer(peer_new, connection_id=legacy_id) is True


def test_gate_install_with_overlap_invokes_hook() -> None:
    hook = Mock()
    gate = TransportIngressGate(_seam(_TLS_A, {"10.0.0.1"}), on_overlap_started=hook)
    gate.install_with_overlap(_seam(_TLS_B, {"10.0.0.2"}), overlap_seconds=10.0)
    hook.assert_called_once()


def test_gate_tls_rotation_property_tracks_active_tls() -> None:
    gate = TransportIngressGate(_seam(_TLS_A, {"10.0.0.1"}))
    gate.install_with_overlap(_seam(_TLS_B, {"10.0.0.2"}), overlap_seconds=30.0)
    rotation = gate.tls_rotation
    assert rotation.active == _TLS_B
    assert rotation.retiring == _TLS_A
