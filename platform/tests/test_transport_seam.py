"""Unit tests for the transport seam: peer whitelist and TLS hot rotation.

Acceptance: ADR-0016 (peer whitelist, mTLS, certificate rotation) and AGENT.md
§13 ("trunk is untrusted", "certificate rotation is a configuration hot update;
never restart the process, never drop an in-flight call").
"""

from __future__ import annotations

import pytest

from as_platform.sip.transport import (
    PeerIdentity,
    PeerPolicy,
    TlsConfig,
    TransportSeam,
    authorize_peer,
)

pytestmark = pytest.mark.unit

TLS = TlsConfig(certificate_path="/etc/as/tls/as.pem", private_key_path="/etc/as/tls/as.key")


def _peer(address: str, certificate_id: str | None = None) -> PeerIdentity:
    return PeerIdentity(address=address, port=5061, certificate_id=certificate_id)


def _policy(addresses: set[str], certificates: set[str] | None = None) -> PeerPolicy:
    return PeerPolicy(
        allowed_addresses=frozenset(addresses),
        allowed_certificate_ids=frozenset(certificates or set()),
    )


def test_address_whitelist_hit_authorises() -> None:
    """A peer whose address is listed is authorised."""
    assert authorize_peer(_peer("10.0.0.1"), _policy({"10.0.0.1"})) is True


def test_address_whitelist_miss_denies() -> None:
    """A peer whose address is not listed is denied."""
    assert authorize_peer(_peer("10.0.0.9"), _policy({"10.0.0.1"})) is False


def test_certificate_whitelist_hit_authorises_without_address_hit() -> None:
    """Under mTLS the certificate identifies the peer; the address need not be listed."""
    policy = _policy({"10.0.0.1"}, {"s-sbc.core.example"})

    assert authorize_peer(_peer("10.0.0.9", "s-sbc.core.example"), policy) is True


def test_certificate_is_ignored_when_absent() -> None:
    """A peer that presented no certificate cannot match the certificate whitelist."""
    policy = _policy(set(), {"s-sbc.core.example"})

    assert authorize_peer(_peer("10.0.0.9"), policy) is False


def test_empty_policy_denies_everything() -> None:
    """Fail-closed: a policy that whitelists nothing authorises nobody."""
    empty = _policy(set(), set())

    assert authorize_peer(_peer("10.0.0.1"), empty) is False
    assert authorize_peer(_peer("10.0.0.1", "s-sbc.core.example"), empty) is False


def test_require_client_certificate_defaults_to_true() -> None:
    """mTLS is the default; server-only TLS must be opted into explicitly."""
    assert (
        TlsConfig(
            certificate_path=TLS.certificate_path, private_key_path=TLS.private_key_path
        ).require_client_certificate
        is True
    )


def test_reload_returns_a_new_object_and_leaves_the_old_one_intact() -> None:
    """Hot rotation is immutable: the old seam keeps its own material and version."""
    old = TransportSeam(tls=TLS, peer_policy=_policy({"10.0.0.1"}), config_version=1)
    new_tls = TlsConfig(
        certificate_path="/etc/as/tls/as-2.pem",
        private_key_path="/etc/as/tls/as-2.key",
        ca_path="/etc/as/tls/ca.pem",
    )

    new = old.reload(tls=new_tls, peer_policy=_policy({"10.0.0.2"}))

    assert new is not old
    assert new.config_version == old.config_version + 1
    assert old.tls is TLS
    assert old.peer_policy == _policy({"10.0.0.1"})
    assert new.tls is new_tls


def test_reload_leaves_in_flight_calls_judging_by_the_old_policy() -> None:
    """The old seam still answers by the old whitelist; new connections get the new one."""
    old = TransportSeam(tls=TLS, peer_policy=_policy({"10.0.0.1"}), config_version=1)
    new = old.reload(tls=TLS, peer_policy=_policy({"10.0.0.2"}))

    assert old.allows(_peer("10.0.0.1")) is True
    assert new.allows(_peer("10.0.0.1")) is False
    assert new.allows(_peer("10.0.0.2")) is True


def test_seam_allows_delegates_to_the_policy() -> None:
    """`allows` and `authorize_peer` agree, so the seam adds no second rule."""
    seam = TransportSeam(tls=TLS, peer_policy=_policy({"10.0.0.1"}), config_version=1)

    assert seam.allows(_peer("10.0.0.1")) is authorize_peer(_peer("10.0.0.1"), seam.peer_policy)
    assert seam.allows(_peer("10.0.0.9")) is False
