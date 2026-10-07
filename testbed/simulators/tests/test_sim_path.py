"""UDP, TCP and TLS calls through S-CSCF, S-SBC and the decision SUT."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from as_load.harness import LoadConfig, run_load
from as_simulators.platform import start_local_platform

pytestmark = pytest.mark.integration


def _run(tmp_path: Path, platform: object, transport: str) -> dict[str, object]:
    from as_simulators.platform import LocalPlatform

    assert isinstance(platform, LocalPlatform)
    summary = run_load(
        LoadConfig(
            host="127.0.0.1",
            port=platform.port("scscf", transport),
            target_cps=25,
            duration_seconds=0.2,
            hold_seconds=0.05,
            workers=5,
            timeout_seconds=3,
            stack_name="ims-sim",
            stack_version="m7.1",
            output_dir=tmp_path,
            transport=transport,
            tls_ca_file=platform.tls_ca,
            scenarios=("T1", "T4", "T5", "F1", "F2"),
        )
    )
    return summary


def test_udp_path_covers_first_edition_and_rejects_a_direct_invite(tmp_path: Path) -> None:
    """Load through S-CSCF succeeds per scenario. A direct INVITE to the SUT is 403."""
    platform = start_local_platform(transports=("udp",))
    try:
        summary = _run(tmp_path / "via-scscf", platform, "udp")
        direct = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=platform.port("sut", "udp"),
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0,
                workers=1,
                timeout_seconds=2,
                stack_name="ims-sim",
                stack_version="m7.1",
                output_dir=tmp_path / "direct",
                scenarios=("T5",),
            )
        )
    finally:
        platform.close()

    buckets = summary["by_scenario"]
    assert isinstance(buckets, dict)
    assert buckets["T1"]["response_codes"] == {"200": 1}
    assert buckets["T4"]["response_codes"] == {"404": 1}
    assert buckets["T5"]["response_codes"] == {"200": 1}
    assert buckets["F1"]["response_codes"] == {"200": 1}
    assert buckets["F2"]["response_codes"] == {"603": 1}
    assert summary["capacity_commitment"] is False
    users = [user for callee in platform.callees for user in callee.request_users]
    assert "013800138000" in users
    assert "+155500010001" in users
    assert "+155500020002" in users
    assert "10010" not in users
    assert "+155500030003" not in users
    assert direct["response_code_distribution"] == {"403": 1}
    assert direct["counts"]["established_sessions"] == 0


def test_tcp_path_connects_a_translated_call(tmp_path: Path) -> None:
    """The same bridge path accepts one T1 call over TCP."""
    platform = start_local_platform(transports=("tcp",))
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=platform.port("scscf", "tcp"),
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0.05,
                workers=1,
                timeout_seconds=3,
                stack_name="ims-sim",
                stack_version="m7.1",
                output_dir=tmp_path,
                transport="tcp",
                scenarios=("T1",),
            )
        )
    finally:
        platform.close()
    assert summary["by_scenario"]["T1"]["response_codes"] == {"200": 1}


def test_tls_path_uses_the_test_ca_and_plaintext_is_not_a_sip_success(tmp_path: Path) -> None:
    """TLS completes T5. A raw TCP write to that port is not a SIP 200."""
    platform = start_local_platform(transports=("tls",), tls_directory=tmp_path / "ca")
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=platform.port("scscf", "tls"),
                target_cps=1,
                duration_seconds=0.1,
                hold_seconds=0.05,
                workers=1,
                timeout_seconds=3,
                stack_name="ims-sim",
                stack_version="m7.1",
                output_dir=tmp_path / "run",
                transport="tls",
                tls_ca_file=platform.tls_ca,
                scenarios=("T5",),
            )
        )
        tls_port = platform.port("scscf", "tls")
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(1)
        raw.connect(("127.0.0.1", tls_port))
        raw.sendall(b"INVITE sip:+155500010001@127.0.0.1 SIP/2.0\r\n\r\n")
        try:
            payload = raw.recv(2048)
        except (TimeoutError, ConnectionError):
            payload = b""
        finally:
            raw.close()
    finally:
        platform.close()

    assert summary["by_scenario"]["T5"]["established"] == 1
    assert b"SIP/2.0 200" not in payload


@pytest.mark.parametrize("transport", ["udp", "tcp", "tls"])
def test_concurrent_mixed_calls_all_finish_and_tear_down(tmp_path: Path, transport: str) -> None:
    """Overlapping calls of every first-edition type each get a final answer and a BYE 200.

    The 404 and 603 ACKs are absorbed by the first bridge, so they do not loop
    between hops and starve the stream connections other calls share.
    """
    platform = start_local_platform(transports=(transport,), tls_directory=tmp_path / "ca")
    try:
        summary = run_load(
            LoadConfig(
                host="127.0.0.1",
                port=platform.port("scscf", transport),
                target_cps=20,
                duration_seconds=1.5,
                hold_seconds=0.5,
                workers=40,
                timeout_seconds=4,
                stack_name="ims-sim",
                stack_version="m7.1",
                output_dir=tmp_path / "run",
                transport=transport,
                tls_ca_file=platform.tls_ca,
                scenarios=("T1", "T4", "T5", "F1", "F2"),
            )
        )
    finally:
        platform.close()

    counts = summary["counts"]
    assert counts["invite_datagrams_sent"] == 30
    assert summary["response_code_distribution"] == {"200": 18, "404": 6, "603": 6}
    assert summary["error_distribution"] == {"sip_404": 6, "sip_603": 6}
    assert counts["unresolved_sessions"] == 0
    assert counts["peak_established_sessions"] > 1
    # A send that waits behind a blocked read on the same socket shows up here first.
    assert summary["setup_latency_ms"]["p95"] < 1000
    # A send that waits behind a blocked read on the same socket shows up here first.
    assert summary["setup_latency_ms"]["p95"] < 1000
