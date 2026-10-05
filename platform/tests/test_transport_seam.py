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

TLS = TlsConfig(
    certificate_path="/etc/as/tls/as.pem",
    private_key_path="/etc/as/tls/as.key",
    ca_path="/etc/as/tls/ca.pem",
)
CERT_FINGERPRINT_A = "sha256:8f0e78fd4f5ff9b4796f8f34f2d6cb47b6de5b0d9fe30d4dbf536f89f8a3b8bd"
CERT_FINGERPRINT_B = "sha256:e2f5f3548ee6fb4f96f1fa6f6e0cc50c7fd7dd145d18da3de0f7bd4861be32c9"


def _peer(address: str, certificate_id: str | None = None, port: int = 5061) -> PeerIdentity:
    return PeerIdentity(address=address, port=port, certificate_id=certificate_id)


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


def test_ipv6_plain_address_whitelist_hit_with_expanded_source_address_authorises() -> None:
    """Expanded IPv6 source still matches a compressed plain-address token."""
    policy = _policy({"2001:db8::1"})

    assert authorize_peer(_peer("2001:0db8:0000:0000:0000:0000:0000:0001"), policy) is True


def test_ipv6_plain_address_whitelist_hit_with_compressed_source_address_authorises() -> None:
    """Compressed IPv6 source still matches an expanded plain-address token."""
    policy = _policy({"2001:0db8:0000:0000:0000:0000:0000:0001"})

    assert authorize_peer(_peer("2001:db8::1"), policy) is True


def test_endpoint_whitelist_hit_authorises() -> None:
    """A peer can be whitelisted as address:port, as REQ-S-1 allows."""
    policy = _policy({"10.0.0.1:5061"})

    assert authorize_peer(_peer("10.0.0.1"), policy) is True


def test_endpoint_whitelist_miss_by_port_denies() -> None:
    """An address:port whitelist entry must not authorise a different port."""
    policy = _policy({"10.0.0.1:5070"})

    assert authorize_peer(_peer("10.0.0.1"), policy) is False


def test_ipv6_endpoint_whitelist_hit_with_expanded_source_address_authorises() -> None:
    """Expanded IPv6 source still matches a compressed bracketed endpoint token."""
    policy = _policy({"[2001:db8::1]:5061"})

    assert authorize_peer(_peer("2001:0db8:0000:0000:0000:0000:0000:0001"), policy) is True


def test_ipv6_endpoint_whitelist_hit_with_compressed_source_address_authorises() -> None:
    """Compressed IPv6 source still matches an expanded bracketed endpoint token."""
    policy = _policy({"[2001:0db8:0000:0000:0000:0000:0000:0001]:5061"})

    assert authorize_peer(_peer("2001:db8::1"), policy) is True


def test_ipv6_endpoint_whitelist_miss_by_port_denies() -> None:
    """IPv6 endpoint whitelist entries are exact, including the port."""
    policy = _policy({"[2001:db8::1]:5061"})

    assert (
        authorize_peer(_peer("2001:0db8:0000:0000:0000:0000:0000:0001", port=5070), policy) is False
    )


def test_dns_endpoint_whitelist_hit_requires_same_host_and_port() -> None:
    """Hostname endpoints match by exact host token and exact port only."""
    policy = _policy({"sbc.example:5061"})

    assert authorize_peer(_peer("sbc.example"), policy) is True
    assert authorize_peer(_peer("SBC.EXAMPLE"), policy) is False
    assert authorize_peer(_peer("sbc.example", port=5070), policy) is False


def test_unbracketed_ipv6_endpoint_allowlist_token_is_rejected() -> None:
    """Unbracketed IPv6 endpoint tokens are ambiguous and do not match."""
    policy = _policy({"2001:db8::1:5061"})

    assert authorize_peer(_peer("2001:db8::1"), policy) is False


def test_certificate_whitelist_hit_authorises_without_address_hit() -> None:
    """Under mTLS the certificate identifies the peer; the address need not be listed."""
    policy = _policy({"10.0.0.1"}, {CERT_FINGERPRINT_A})

    assert authorize_peer(_peer("10.0.0.9", CERT_FINGERPRINT_A), policy) is True


def test_certificate_whitelist_mismatch_denies() -> None:
    """Certificate whitelist matching is exact for fingerprint tokens."""
    policy = _policy(set(), {CERT_FINGERPRINT_A})

    assert authorize_peer(_peer("10.0.0.9", CERT_FINGERPRINT_B), policy) is False


def test_certificate_is_ignored_when_absent() -> None:
    """A peer that presented no certificate cannot match the certificate whitelist."""
    policy = _policy(set(), {CERT_FINGERPRINT_A})

    assert authorize_peer(_peer("10.0.0.9"), policy) is False


def test_empty_policy_denies_everything() -> None:
    """Fail-closed: a policy that whitelists nothing authorises nobody."""
    empty = _policy(set(), set())

    assert authorize_peer(_peer("10.0.0.1"), empty) is False
    assert authorize_peer(_peer("10.0.0.1", CERT_FINGERPRINT_A), empty) is False


def test_require_client_certificate_defaults_to_true() -> None:
    """mTLS is the default; server-only TLS must be opted into explicitly."""
    assert (
        TlsConfig(
            certificate_path=TLS.certificate_path,
            private_key_path=TLS.private_key_path,
            ca_path=TLS.ca_path,
        ).require_client_certificate
        is True
    )


@pytest.mark.parametrize("ca_path", [None, "", "   "])
def test_require_client_certificate_rejects_missing_or_blank_ca_path(ca_path: str | None) -> None:
    """mTLS config is fail-closed when CA material is not configured."""
    with pytest.raises(
        ValueError,
        match=r"TlsConfig\.ca_path is required when require_client_certificate is True",
    ):
        TlsConfig(
            certificate_path=TLS.certificate_path,
            private_key_path=TLS.private_key_path,
            ca_path=ca_path,
        )


def test_server_only_tls_allows_no_ca_path_when_client_certificate_is_not_required() -> None:
    """Server-only TLS can be configured explicitly without peer-cert verification."""
    tls = TlsConfig(
        certificate_path=TLS.certificate_path,
        private_key_path=TLS.private_key_path,
        ca_path=None,
        require_client_certificate=False,
    )

    assert tls.require_client_certificate is False


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
