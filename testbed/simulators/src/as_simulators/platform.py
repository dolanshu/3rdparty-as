"""In-process IMS simulation path: S-CSCF, S-SBC, system under test, callee."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from as_simulators.bridge import TransparentBridge
from as_simulators.ca import TlsMaterial, generate_test_material
from as_simulators.demo_rules import demo_rules
from as_simulators.sut import DecisionSut, PeerGate
from as_simulators.uas import PeerUas


@dataclass
class LocalPlatform:
    """The sockets that make up one local simulation path."""

    host: str
    transports: tuple[str, ...]
    ports: dict[tuple[str, str], int]
    tls_ca: Path | None
    callees: list[PeerUas] = field(default_factory=list)
    _closers: list[Callable[[], None]] = field(default_factory=list)

    def port(self, role: str, transport: str) -> int:
        """Return the bound port for a role and transport."""
        return self.ports[(role, transport)]

    def close(self) -> None:
        """Stop every hop."""
        for closer in reversed(self._closers):
            closer()
        self._closers.clear()

    def __enter__(self) -> LocalPlatform:
        """Return this platform."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Stop every hop."""
        self.close()


def start_local_platform(
    *,
    host: str = "127.0.0.1",
    transports: tuple[str, ...] = ("udp", "tcp", "tls"),
    tls_directory: Path | None = None,
) -> LocalPlatform:
    """Start S-CSCF, both S-SBC legs, the decision SUT and the callee.

    Args:
        host: Address every hop advertises. Tests use ``127.0.0.1``.
        transports: Which of ``udp``, ``tcp`` and ``tls`` to bind.
        tls_directory: Where to write the test CA when ``tls`` is requested.
            A temporary directory is used when this is omitted.

    Returns:
        A started platform. Close it when the test or the UI is done.
    """
    unknown = [item for item in transports if item not in {"udp", "tcp", "tls"}]
    if unknown:
        raise ValueError(f"unsupported transports: {unknown}")
    material: TlsMaterial | None = None
    if "tls" in transports:
        directory = tls_directory or Path(tempfile.mkdtemp(prefix="ims-sim-ca-"))
        material = generate_test_material(directory)
    rules, translations = demo_rules()
    gate = PeerGate()
    platform = LocalPlatform(
        host=host,
        transports=transports,
        ports={},
        tls_ca=None if material is None else material.ca_certificate,
        callees=[],
    )
    cert = None if material is None else material.certificate
    key = None if material is None else material.private_key
    ca_file = None if material is None else material.ca_certificate

    for transport in transports:
        uas = PeerUas(host, transport, tls_certificate=cert, tls_private_key=key)
        south = TransparentBridge(
            advertised_host=host,
            next_hop=(host, uas.port),
            transport=transport,
            tls_certificate=cert,
            tls_private_key=key,
            tls_ca_file=ca_file,
        )
        sut = DecisionSut(
            host=host,
            transport=transport,
            rules=rules,
            translations=translations,
            gate=gate,
            south=(host, south.port),
            tls_certificate=cert,
            tls_private_key=key,
            tls_ca_file=ca_file,
        )
        north = TransparentBridge(
            advertised_host=host,
            next_hop=(host, sut.port),
            transport=transport,
            tls_certificate=cert,
            tls_private_key=key,
            tls_ca_file=ca_file,
        )
        gate.via_ports.add(north.port)
        scscf = TransparentBridge(
            advertised_host=host,
            next_hop=(host, north.port),
            transport=transport,
            tls_certificate=cert,
            tls_private_key=key,
            tls_ca_file=ca_file,
        )
        for hop in (uas, south, sut, north, scscf):
            hop.start()
            platform._closers.append(hop.stop)
        platform.callees.append(uas)
        platform.ports[("uas", transport)] = uas.port
        platform.ports[("ssbc-south", transport)] = south.port
        platform.ports[("sut", transport)] = sut.port
        platform.ports[("ssbc-north", transport)] = north.port
        platform.ports[("scscf", transport)] = scscf.port
    return platform
