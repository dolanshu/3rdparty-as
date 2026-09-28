"""Transport seam: peer authorisation and TLS configuration hot rotation.

This module is the boundary half of ADR-0016. It answers exactly one question
--- is this peer one we accept traffic from --- and it answers it without IO,
without a clock and without global state, so the answer can be tested without a
network and replayed without a process.

Two properties are carried over from the rest of the kernel:

* **Fail-closed.** An empty policy authorises nobody, the same default-off
  stance as ``gating`` (ADR-0020). A whitelist that was never filled in must not
  become a hole that lets traffic through.
* **Immutability.** Rotation returns a new :class:`TransportSeam` instead of
  mutating the old one. That is what makes "in-flight calls are untouched" a
  property of the type rather than a promise in a comment.

The handshake itself is not here: TLS termination belongs to the stack binding
supplied in a later M2b step (ADR-0019, reSIProcate). What this module pins down
is which certificate files and which peers that binding must be pointed at, and
how those change while the process keeps running.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeerIdentity:
    """Who is on the other end of a connection, as far as we can tell.

    Attributes:
        address: The source address of the peer.
        port: The source port of the peer.
        certificate_id: The peer certificate identity --- a CN or a SAN --- or
            ``None`` when the peer presented no client certificate.
    """

    address: str
    port: int
    certificate_id: str | None = None


@dataclass(frozen=True)
class PeerPolicy:
    """The whitelist a peer is checked against (ADR-0016).

    Attributes:
        allowed_addresses: Source addresses we accept traffic from.
        allowed_certificate_ids: Peer certificate identities we accept; under
            mTLS this is the stronger of the two dimensions, because a source
            address can be spoofed and a certificate cannot.
    """

    allowed_addresses: frozenset[str]
    allowed_certificate_ids: frozenset[str]


@dataclass(frozen=True)
class TlsConfig:
    """Where the TLS material lives on disk.

    Attributes:
        certificate_path: Our certificate.
        private_key_path: Our private key.
        ca_path: The CA bundle used to verify peer certificates; ``None`` means
            no peer verification is configured.
        require_client_certificate: Whether a client certificate is demanded
            (mTLS). Defaults to ``True``: ADR-0016 prefers mTLS over
            server-only TLS, because TLS alone only proves that a peer holds a
            certificate inside our trust chain, not that it is the peer we
            expect.
    """

    certificate_path: str
    private_key_path: str
    ca_path: str | None = None
    require_client_certificate: bool = True


@dataclass(frozen=True)
class TransportSeam:
    """The transport configuration of one running process at one version.

    Attributes:
        tls: The TLS material currently in force.
        peer_policy: The whitelist currently in force.
        config_version: Monotonic counter bumped by every :meth:`reload`.
    """

    tls: TlsConfig
    peer_policy: PeerPolicy
    config_version: int

    def reload(self, tls: TlsConfig, peer_policy: PeerPolicy) -> TransportSeam:
        """Return a new seam carrying new certificates and a new whitelist.

        This is the **hot rotation** path of ADR-0016 and AGENT.md §13:
        "certificate rotation is a configuration hot update. Never restart the
        process, never drop an in-flight call." Certificate lifetimes are far
        shorter than process lifetimes, so the two must be decoupled --- and
        because the seam is immutable, a caller that already holds the previous
        version keeps judging by it until it picks up the new one. New
        connections use the new material; established calls are unaffected.

        Args:
            tls: The TLS material to rotate to.
            peer_policy: The whitelist to rotate to.

        Returns:
            A new :class:`TransportSeam` whose ``config_version`` is one higher
            than this one's. This object is unchanged.
        """
        return TransportSeam(
            tls=tls,
            peer_policy=peer_policy,
            config_version=self.config_version + 1,
        )

    def allows(self, peer: PeerIdentity) -> bool:
        """Whether this seam's policy authorises a peer.

        Args:
            peer: The peer to check.

        Returns:
            ``True`` when the peer is authorised, ``False`` otherwise.
        """
        return authorize_peer(peer, self.peer_policy)


def authorize_peer(peer: PeerIdentity, policy: PeerPolicy) -> bool:
    """Authorise one peer against one whitelist.

    A hit on **either** dimension is enough: the address whitelist or the
    certificate whitelist. Under mTLS the certificate is the dimension that
    actually identifies the peer, so a certificate hit authorises a peer whose
    address is not listed.

    An **empty policy authorises nobody** --- both collections empty means deny.
    ADR-0016 puts the reason plainly: anyone who can impersonate the S-SBC can
    inject calls, so the entry check is a precondition of correctness, not a
    hardening step; a whitelist that was never filled in must fail closed, in
    line with ``gating``'s default-off and AGENT.md §13 "trunk is untrusted".

    Pure function: no IO, no clock, no global state.

    Args:
        peer: The peer to check.
        policy: The whitelist to check it against.

    Returns:
        ``True`` when the peer is authorised, ``False`` otherwise.
    """
    if not policy.allowed_addresses and not policy.allowed_certificate_ids:
        return False  # Fail-closed: an empty policy authorises nobody. See ADR-0016

    # mTLS identity hit; the address need not be listed. See ADR-0016
    certificate_hit = (
        peer.certificate_id is not None and peer.certificate_id in policy.allowed_certificate_ids
    )
    return peer.address in policy.allowed_addresses or certificate_hit
