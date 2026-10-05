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
    mutating the old one. This guarantees old and new policy/config snapshots can
    coexist, but by itself it does not guarantee how live dialogs or transport
    connections behave at runtime.

The handshake itself is not here: TLS termination belongs to the stack binding
supplied in a later M2b step (ADR-0019, reSIProcate). What this module pins down
is which certificate files and which peers that binding must be pointed at, and
how those change while the process keeps running.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass


@dataclass(frozen=True)
class PeerIdentity:
    """Who is on the other end of a connection, as far as we can tell.

    Attributes:
        address: The source address of the peer.
        port: The source port of the peer.
        certificate_id: The peer certificate fingerprint identifier required by
            REQ-S-1 (for example, a precomputed SHA-256 token), or ``None``
            when the peer presented no client certificate. In this M2 seam,
            the identifier is supplied by the future TLS stack binding.
    """

    address: str
    port: int
    certificate_id: str | None = None


@dataclass(frozen=True)
class PeerPolicy:
    """The whitelist a peer is checked against (ADR-0016).

    Attributes:
        allowed_addresses: Source peers we accept traffic from, as either
            plain addresses (``10.0.0.1``) or endpoint tokens
            (``10.0.0.1:5061``).
        allowed_certificate_ids: Peer certificate fingerprint identifiers we
            accept (for example, precomputed SHA-256 tokens from the future TLS
            binding). Under mTLS this is the stronger of the two dimensions,
            because a source address can be spoofed and a certificate cannot.
    """

    allowed_addresses: frozenset[str]
    allowed_certificate_ids: frozenset[str]


@dataclass(frozen=True)
class TlsConfig:
    """Where the TLS material lives on disk.

    Attributes:
        certificate_path: Our certificate.
        private_key_path: Our private key.
        ca_path: The CA bundle used to verify peer certificates. This is
            required when ``require_client_certificate`` is ``True``.
        require_client_certificate: Whether a client certificate is demanded
            (mTLS). Defaults to ``True``: ADR-0016 prefers mTLS over
            server-only TLS, because TLS alone only proves that a peer holds a
            certificate inside our trust chain, not that it is the peer we
            expect. ``False`` remains available only as an explicit server-only
            TLS configuration.
    """

    certificate_path: str
    private_key_path: str
    ca_path: str | None = None
    require_client_certificate: bool = True

    def __post_init__(self) -> None:
        """Fail closed for mTLS config: client-cert verification needs a CA."""
        if self.require_client_certificate and (self.ca_path is None or self.ca_path.strip() == ""):
            raise ValueError(
                "TlsConfig.ca_path is required when require_client_certificate is True"
            )


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

        This immutable value models ADR-0016's hot-rotation contract: callers
        receive the next configuration version while holders of older versions
        continue to judge peers with their prior policy. It does not install
        certificates or rotate live connections by itself; runtime application
        of the returned version to new connections, while preserving established
        ones, remains a future stack-binding responsibility.

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


def _canonical_endpoint_token(address: str, port: int) -> str:
    """Build the endpoint token used by whitelist matching.

    IPv6 endpoints are represented as ``[addr]:port`` to avoid the ambiguity of
    raw ``addr:port`` strings.
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return f"{address}:{port}"

    if parsed.version == 6:
        return f"[{parsed.compressed}]:{port}"
    return f"{parsed.compressed}:{port}"


def _canonical_ip_literal(address: str) -> str | None:
    """Return canonical text for IP literals, or ``None`` for non-IP tokens."""
    try:
        return ipaddress.ip_address(address).compressed
    except ValueError:
        return None


def _parse_port_literal(raw_port: str) -> int | None:
    """Parse a decimal port literal, returning ``None`` when malformed."""
    if not raw_port.isdecimal():
        return None

    port = int(raw_port)
    if port < 0 or port > 65535:
        return None
    return port


def _canonical_allowed_endpoint_token(token: str) -> str | None:
    """Canonicalise one allowlist endpoint token, or reject malformed strings.

    Accepted endpoint syntax is intentionally narrow:

    * bracketed IPv6 literals: ``[2001:db8::1]:5061``
    * unbracketed host/IPv4 tokens: ``sbc.example:5061`` or ``10.0.0.1:5061``

    Unbracketed IPv6 endpoint strings are ambiguous and therefore rejected.
    """
    if token.startswith("["):
        closing = token.find("]")
        if closing <= 1:
            return None

        raw_host = token[1:closing]
        remainder = token[closing + 1 :]
        if not remainder.startswith(":"):
            return None

        port = _parse_port_literal(remainder[1:])
        if port is None:
            return None

        parsed_host = _canonical_ip_literal(raw_host)
        if parsed_host is None:
            return None

        if ipaddress.ip_address(parsed_host).version != 6:
            return None

        return _canonical_endpoint_token(parsed_host, port)

    if token.count(":") != 1:
        return None

    raw_host, raw_port = token.rsplit(":", 1)
    if raw_host == "" or "[" in raw_host or "]" in raw_host:
        return None

    port = _parse_port_literal(raw_port)
    if port is None:
        return None

    return _canonical_endpoint_token(raw_host, port)


def authorize_peer(peer: PeerIdentity, policy: PeerPolicy) -> bool:
    """Authorise one peer against one whitelist.

    A hit on **either** dimension is enough: the address/endpoint whitelist or
    the certificate whitelist. Under mTLS the certificate is the dimension that
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

    # See ADR-0016: either an accepted address/endpoint or a certificate token
    # authorises the peer.
    endpoint = _canonical_endpoint_token(peer.address, peer.port)
    peer_ip = _canonical_ip_literal(peer.address)
    canonical_plain_address_hit = peer_ip is not None and any(
        _canonical_ip_literal(token) == peer_ip for token in policy.allowed_addresses
    )
    canonical_endpoint_hit = any(
        _canonical_allowed_endpoint_token(token) == endpoint for token in policy.allowed_addresses
    )
    address_hit = (
        peer.address in policy.allowed_addresses
        or canonical_plain_address_hit
        or endpoint in policy.allowed_addresses
        or canonical_endpoint_hit
    )
    return address_hit or certificate_hit
