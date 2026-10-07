"""One simulation role per process, for the kind chart.

The local all-in-one platform remains :func:`as_simulators.platform.start_local_platform`.
These roles are the same hops split so a NetworkPolicy can tell the call load
from the S-SBC.
"""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from types import FrameType

from as_simulators.bridge import TransparentBridge
from as_simulators.ca import material_from_env
from as_simulators.demo_rules import demo_rules
from as_simulators.platform import LocalPlatform
from as_simulators.sut import DecisionSut, PeerGate
from as_simulators.uas import PeerUas
from as_simulators.ui import serve_ui

_TRANSPORTS = ("udp", "tcp", "tls")


def _port_for(transport: str, udp_port: int, tls_port: int) -> int:
    if transport == "tls":
        return tls_port
    return udp_port


def run_role(
    *,
    role: str,
    advertise: str,
    bind: str,
    next_host: str,
    allow_peer_host: str,
    udp_port: int,
    tls_port: int,
    ui_host: str,
    ui_port: int,
    output_dir: Path,
) -> None:
    """Run one role until SIGTERM or SIGINT.

    Args:
        role: ``scscf``, ``ssbc-north``, ``ssbc-south``, ``uas``, ``sut`` or ``ui``.
        advertise: Name placed in Via, Record-Route and Contact. In the chart
            this is the headless Service name, so TLS peers can verify it.
        bind: Listen address, normally the pod IP.
        next_host: DNS name of the next hop. Unused by ``uas`` and ``ui``.
        allow_peer_host: Headless Service of the north S-SBC. Used by ``sut``.
        udp_port: UDP and TCP listen port.
        tls_port: TLS listen port.
        ui_host: Bind address of the test page.
        ui_port: Port of the test page.
        output_dir: Where a UI run writes its summary.
    """
    if role == "ui":
        _serve_remote_ui(
            scscf_host=next_host or "scscf",
            udp_port=udp_port,
            tls_port=tls_port,
            ui_host=ui_host,
            ui_port=ui_port,
            output_dir=output_dir,
        )
        return

    directory = Path(os.environ.get("AS_SIM_TLS_DIR", "/tmp/ims-sim-ca"))
    material = material_from_env(directory)
    hops: list[TransparentBridge | PeerUas | DecisionSut] = []
    rules, translations = demo_rules()
    for transport in _TRANSPORTS:
        port = _port_for(transport, udp_port, tls_port)
        if role == "uas":
            hops.append(
                PeerUas(
                    advertise,
                    transport,
                    tls_certificate=material.certificate,
                    tls_private_key=material.private_key,
                    listen_port=port,
                    bind_host=bind,
                )
            )
            continue
        if role == "sut":
            gate = PeerGate()
            gate.peer_host = allow_peer_host
            hops.append(
                DecisionSut(
                    host=advertise,
                    transport=transport,
                    rules=rules,
                    translations=translations,
                    gate=gate,
                    south=(next_host, port),
                    tls_certificate=material.certificate,
                    tls_private_key=material.private_key,
                    tls_ca_file=material.ca_certificate,
                    listen_port=port,
                    bind_host=bind,
                )
            )
            continue
        if role not in {"scscf", "ssbc-north", "ssbc-south"}:
            raise ValueError(f"unknown role {role!r}")
        hops.append(
            TransparentBridge(
                advertised_host=advertise,
                next_hop=(next_host, port),
                transport=transport,
                tls_certificate=material.certificate,
                tls_private_key=material.private_key,
                tls_ca_file=material.ca_certificate,
                listen_port=port,
                bind_host=bind,
            )
        )
    for hop in hops:
        hop.start()
    _wait_for_stop()
    for hop in hops:
        hop.stop()


def _serve_remote_ui(
    *,
    scscf_host: str,
    udp_port: int,
    tls_port: int,
    ui_host: str,
    ui_port: int,
    output_dir: Path,
) -> None:
    ca_text = os.environ.get("AS_SIM_TLS_CA", "").strip()
    platform = LocalPlatform(
        host=scscf_host,
        transports=_TRANSPORTS,
        ports={
            ("scscf", "udp"): udp_port,
            ("scscf", "tcp"): udp_port,
            ("scscf", "tls"): tls_port,
        },
        tls_ca=Path(ca_text) if ca_text else None,
    )
    serve_ui(platform, ui_host, ui_port, output_dir)


def _wait_for_stop() -> None:
    stopped = threading.Event()

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    stopped.wait()
