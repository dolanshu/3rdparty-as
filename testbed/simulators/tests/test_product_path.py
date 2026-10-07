"""First-edition calls through the simulated S-SBC and the product SIP runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from as_load.harness import LoadConfig, run_load
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener, load_resip_runtime_extension
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam
from as_simulators.bridge import TransparentBridge
from as_simulators.ca import generate_test_material
from as_simulators.demo_rules import demo_rules
from as_simulators.uas import PeerUas

pytestmark = pytest.mark.integration

_TRANSLATION_RULES = json.dumps(
    [
        {
            "rule_id": "t1-plus86",
            "prefix": "+86138",
            "strip_prefix": "+86",
            "add_prefix": "0",
        }
    ]
)


def test_product_runtime_handles_the_first_edition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport: str,
    also_cleartext: bool,
) -> None:
    """Load through S-CSCF and S-SBC. The product process decides and, for T1, rewrites."""
    if load_resip_runtime_extension() is None:
        pytest.skip("native runtime not built")

    host = "127.0.0.1"
    material = generate_test_material(tmp_path / "ca") if transport == "tls" else None
    cert = None if material is None else material.certificate
    key = None if material is None else material.private_key
    ca_file = None if material is None else material.ca_certificate
    rules, _translations = demo_rules()
    uas = PeerUas(host, transport, tls_certificate=cert, tls_private_key=key)
    south = TransparentBridge(
        advertised_host=host,
        next_hop=(host, uas.port),
        transport=transport,
        tls_certificate=cert,
        tls_private_key=key,
        tls_ca_file=ca_file,
    )
    monkeypatch.setenv("AS_SIP_ROUTE_HOOK", "as_translation.outbound")
    monkeypatch.setenv("AS_SIP_NEXT_HOP", host)
    monkeypatch.setenv("AS_SIP_NEXT_HOP_PORT", str(south.port))
    monkeypatch.setenv("AS_SIP_NEXT_HOP_TLS_PORT", str(south.port))
    monkeypatch.setenv("AS_TRANSLATION_RULES_JSON", _TRANSLATION_RULES)

    if material is None:
        tls = TlsConfig(
            certificate_path="",
            private_key_path="",
            ca_path=None,
            require_client_certificate=False,
        )
    else:
        tls = TlsConfig(
            certificate_path=str(material.certificate),
            private_key_path=str(material.private_key),
            ca_path=str(material.ca_certificate),
            require_client_certificate=False,
        )
    gate = TransportIngressGate(
        TransportSeam(
            tls=tls,
            peer_policy=PeerPolicy(
                allowed_addresses=frozenset({host}),
                allowed_certificate_ids=frozenset(),
            ),
            config_version=1,
        )
    )
    listener = ResipRuntimeListener(
        gate,
        rules,
        enable_udp=transport == "udp" or also_cleartext,
        enable_tcp=transport == "tcp" or also_cleartext,
        tls_only=transport == "tls" and not also_cleartext,
        bind_address=host,
        advertised_address=host,
    )
    listener.start()
    if transport == "tls":
        product_port = listener.tls_port
    elif transport == "tcp":
        product_port = listener.tcp_port
    else:
        product_port = listener.port
    assert product_port is not None
    north = TransparentBridge(
        advertised_host=host,
        next_hop=(host, product_port),
        transport=transport,
        tls_certificate=cert,
        tls_private_key=key,
        tls_ca_file=ca_file,
    )
    scscf = TransparentBridge(
        advertised_host=host,
        next_hop=(host, north.port),
        transport=transport,
        tls_certificate=cert,
        tls_private_key=key,
        tls_ca_file=ca_file,
    )
    hops = (uas, south, north, scscf)
    for hop in hops:
        hop.start()
    try:
        summary = run_load(
            LoadConfig(
                host=host,
                port=scscf.port,
                target_cps=25,
                duration_seconds=0.2,
                hold_seconds=0.05,
                workers=5,
                timeout_seconds=3,
                stack_name="ims-sim",
                stack_version="m7.1",
                output_dir=tmp_path / "load",
                transport=transport,
                tls_ca_file=ca_file,
                scenarios=("T1", "T4", "T5", "F1", "F2"),
            )
        )
    finally:
        for hop in reversed(hops):
            hop.stop()
        listener.stop()

    buckets = summary["by_scenario"]
    assert isinstance(buckets, dict)
    assert buckets["T1"]["response_codes"] == {"200": 1}
    assert buckets["T4"]["response_codes"] == {"404": 1}
    assert buckets["T5"]["response_codes"] == {"200": 1}
    assert buckets["F1"]["response_codes"] == {"200": 1}
    assert buckets["F2"]["response_codes"] == {"603": 1}
    assert "013800138000" in uas.request_users
    assert "+155500010001" in uas.request_users
    assert "+155500030003" not in uas.request_users
    errors = summary["error_distribution"]
    assert isinstance(errors, dict)
    bye_errors = {
        name: count
        for name, count in errors.items()
        if name.startswith("bye_") or name == "timeout_bye"
    }
    assert bye_errors == {}
    assert summary["counts"]["unresolved_sessions"] == 0
    assert uas.request_methods.count("BYE") == 3


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "transport" in metafunc.fixturenames and "also_cleartext" in metafunc.fixturenames:
        metafunc.parametrize(
            ("transport", "also_cleartext"),
            [
                ("udp", False),
                ("tcp", False),
                ("tls", False),
                ("tls", True),
            ],
        )
