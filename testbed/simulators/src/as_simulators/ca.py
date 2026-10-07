"""Ephemeral test CA for the simulation platform.

Keys are written only under a caller-supplied directory, which tests and the
process use as a temporary path. Nothing here reads or writes a key that is
checked into the repository.
"""

from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TlsMaterial:
    """PEM paths for one short-lived test CA and one server certificate."""

    ca_certificate: Path
    certificate: Path
    private_key: Path


def generate_test_material(directory: Path, dns_names: tuple[str, ...] = ()) -> TlsMaterial:
    """Create a test CA and a server certificate that chains to it.

    Args:
        directory: Directory that will hold the PEM files. Created if needed.
        dns_names: Extra DNS subject alternative names.

    Returns:
        Paths to the CA certificate, the server certificate and the server key.

    Raises:
        RuntimeError: If ``openssl`` cannot create the material.
    """
    directory.mkdir(parents=True, exist_ok=True)
    ca_key = directory / "ca.key"
    ca_certificate = directory / "ca.crt"
    server_key = directory / "server.key"
    server_csr = directory / "server.csr"
    server_certificate = directory / "server.crt"
    extension = directory / "san.cnf"
    dns = ("localhost", "scscf", "ssbc-north", "ssbc-south", "uas", "sut", *dns_names)
    alt_names = ["IP:127.0.0.1", *(f"DNS:{name}" for name in dict.fromkeys(dns))]
    extension.write_text(
        "subjectAltName=" + ",".join(alt_names) + "\n"
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n",
        encoding="utf-8",
    )
    _openssl(
        [
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_certificate),
            "-days",
            "2",
            "-nodes",
            "-subj",
            "/CN=ims-sim-test-ca",
        ]
    )
    _openssl(
        [
            "req",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(server_key),
            "-out",
            str(server_csr),
            "-nodes",
            "-subj",
            "/CN=127.0.0.1",
        ]
    )
    _openssl(
        [
            "x509",
            "-req",
            "-in",
            str(server_csr),
            "-CA",
            str(ca_certificate),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(server_certificate),
            "-days",
            "2",
            "-extfile",
            str(extension),
        ]
    )
    for secret in (ca_key, server_key):
        secret.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return TlsMaterial(
        ca_certificate=ca_certificate,
        certificate=server_certificate,
        private_key=server_key,
    )


def material_from_env(directory: Path) -> TlsMaterial:
    """Load PEM paths from the environment, or generate them under ``directory``.

    ``AS_SIM_TLS_CERT``, ``AS_SIM_TLS_KEY`` and ``AS_SIM_TLS_CA`` select mounted
    material. ``AS_SIM_TLS_DNS`` is a comma-separated list of extra DNS names
    used only when this process generates the certificate.
    """
    cert = os.environ.get("AS_SIM_TLS_CERT", "").strip()
    key = os.environ.get("AS_SIM_TLS_KEY", "").strip()
    ca_certificate = os.environ.get("AS_SIM_TLS_CA", "").strip()
    if cert and key and ca_certificate:
        return TlsMaterial(
            ca_certificate=Path(ca_certificate),
            certificate=Path(cert),
            private_key=Path(key),
        )
    extra = tuple(
        item.strip() for item in os.environ.get("AS_SIM_TLS_DNS", "").split(",") if item.strip()
    )
    return generate_test_material(directory, extra)


def _openssl(args: list[str]) -> None:
    try:
        subprocess.run(["openssl", *args], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"")
        text = detail.decode("utf-8", errors="replace") if isinstance(detail, bytes) else str(error)
        raise RuntimeError(f"openssl failed: {text}") from error
