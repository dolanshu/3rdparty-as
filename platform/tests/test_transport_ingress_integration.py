"""Integration tests: real UDP socket with ingress peer-policy enforcement."""

from __future__ import annotations

import socket
import time

import pytest

from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam
from as_platform.sip.udp_ingress import UdpIngressServer

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_TLS = TlsConfig(
    certificate_path="/etc/as/tls/as.pem",
    private_key_path="/etc/as/tls/as.key",
    ca_path="/etc/as/tls/ca.pem",
)
_DELIVERY_TIMEOUT_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.05


def _seam(*addresses: str) -> TransportSeam:
    return TransportSeam(
        tls=_TLS,
        peer_policy=PeerPolicy(
            allowed_addresses=frozenset(addresses),
            allowed_certificate_ids=frozenset(),
        ),
        config_version=1,
    )


def _wait_for_payload(server: UdpIngressServer, expected_count: int) -> None:
    deadline = time.monotonic() + _DELIVERY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if len(server.received_payloads()) >= expected_count:
            return
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"expected {expected_count} payload(s), got {len(server.received_payloads())}"
    )


def test_allowed_peer_datagram_is_enqueued() -> None:
    gate = TransportIngressGate(_seam(_HOST))
    server = UdpIngressServer(gate, host=_HOST, port=0)
    server.start()
    try:
        payload = b"OPTIONS sip:as.test SIP/2.0\r\n\r\n"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.sendto(payload, (server.host, server.port))

        _wait_for_payload(server, 1)
        assert server.received_payloads() == (payload,)
    finally:
        server.stop()


def test_denied_peer_datagram_is_silently_dropped() -> None:
    gate = TransportIngressGate(_seam("10.255.255.254"))
    server = UdpIngressServer(gate, host=_HOST, port=0)
    server.start()
    try:
        payload = b"OPTIONS sip:as.test SIP/2.0\r\n\r\n"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.sendto(payload, (server.host, server.port))

        deadline = time.monotonic() + _DELIVERY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if server.received_payloads():
                pytest.fail("denied peer payload was enqueued")
            time.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        server.stop()
