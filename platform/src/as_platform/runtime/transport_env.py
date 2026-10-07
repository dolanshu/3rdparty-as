"""Load product SIP transport seam and listen addresses from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

_DEFAULT_BIND = "127.0.0.1"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(name: str) -> frozenset[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class SipListenConfig:
    """Socket bind vs SIP Contact/SDP advertisement."""

    bind_address: str
    advertised_address: str


def load_sip_listen_config_from_env() -> SipListenConfig:
    """Resolve bind and advertised addresses (REQ-NF-9 / S-SBC facing)."""
    bind = os.environ.get("AS_SIP_BIND_ADDRESS", "").strip()
    if not bind:
        bind = os.environ.get("SIP_LISTEN_ADDR", "").strip() or _DEFAULT_BIND
    advertised_raw = os.environ.get("AS_SIP_ADVERTISED_ADDRESS", "").strip()
    if advertised_raw:
        advertised = advertised_raw
    elif bind == "0.0.0.0":
        raise ValueError(
            "AS_SIP_ADVERTISED_ADDRESS is required when AS_SIP_BIND_ADDRESS is 0.0.0.0"
        )
    else:
        advertised = bind
    return SipListenConfig(bind_address=bind, advertised_address=advertised)


def load_transport_seam_from_env() -> TransportSeam:
    """Build :class:`TransportSeam` from ``AS_TLS_*`` and ``AS_PEER_*`` variables."""
    chart_tls = _env_flag("SIP_TLS_ENABLED")
    cert = os.environ.get("AS_TLS_CERT_PATH", "").strip()
    key = os.environ.get("AS_TLS_KEY_PATH", "").strip()
    ca = os.environ.get("AS_TLS_CA_PATH", "").strip() or None
    if chart_tls:
        if not cert:
            cert = os.environ.get("SIP_TLS_CERT_PATH", "").strip()
        if not key:
            key = os.environ.get("SIP_TLS_KEY_PATH", "").strip()
        if ca is None:
            ca = os.environ.get("SIP_TLS_CA_PATH", "").strip() or None
    tls_requested = _env_flag("AS_TLS_ENABLE") or chart_tls or bool(cert or key)
    if os.environ.get("AS_TLS_REQUIRE_CLIENT_CERT") is not None:
        require_client = _env_flag("AS_TLS_REQUIRE_CLIENT_CERT", default=True)
    elif os.environ.get("SIP_TLS_REQUIRE_CLIENT_CERT") is not None:
        require_client = _env_flag("SIP_TLS_REQUIRE_CLIENT_CERT", default=True)
    else:
        require_client = True

    if tls_requested and (not cert or not key):
        raise ValueError(
            "TLS enabled (AS_TLS_ENABLE or cert paths) but AS_TLS_CERT_PATH/AS_TLS_KEY_PATH "
            "are missing"
        )

    tls = TlsConfig(
        certificate_path=cert,
        private_key_path=key,
        ca_path=ca,
        require_client_certificate=require_client if tls_requested else False,
    )

    allowed_addresses = _split_csv("AS_PEER_ALLOWED_ADDRESSES")
    if not allowed_addresses:
        allowed_addresses = _split_csv("SIP_PEER_ALLOWLIST")
    allowed_fps = _split_csv("AS_PEER_ALLOWED_CERT_FINGERPRINTS")
    if not allowed_addresses and not allowed_fps:
        listen = load_sip_listen_config_from_env()
        allowed_addresses = frozenset(
            {listen.advertised_address, listen.bind_address, "127.0.0.1", "::1"}
        )

    return TransportSeam(
        tls=tls,
        peer_policy=PeerPolicy(
            allowed_addresses=allowed_addresses,
            allowed_certificate_ids=allowed_fps,
        ),
        config_version=1,
    )
