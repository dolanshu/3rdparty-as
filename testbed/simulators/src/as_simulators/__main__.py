"""Command line for the local simulation platform."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from as_simulators.ca import generate_test_material
from as_simulators.platform import start_local_platform
from as_simulators.roles import run_role
from as_simulators.ui import serve_ui


def main() -> None:
    """Start the all-in-one platform and its page, or write a test CA."""
    parser = argparse.ArgumentParser(description="IMS simulation platform")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="listen on UDP, TCP and TLS and serve the test page")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--ui-host", default="127.0.0.1")
    serve.add_argument("--ui-port", type=int, default=8088)
    serve.add_argument("--output", type=Path, default=Path("artifacts/m71"))

    issue = sub.add_parser("issue-certs", help="write a short-lived test CA outside the repository")
    issue.add_argument("--out", type=Path, required=True)
    issue.add_argument("--dns", default="", help="comma-separated extra DNS names")

    run = sub.add_parser("run", help="run one chart role until SIGTERM")
    run.add_argument(
        "--role",
        required=True,
        choices=("scscf", "ssbc-north", "ssbc-south", "uas", "sut", "ui"),
    )
    run.add_argument("--advertise", default="")
    run.add_argument("--next-host", default="")
    run.add_argument("--allow-peer-host", default="")
    run.add_argument("--udp-port", type=int, default=5060)
    run.add_argument("--tls-port", type=int, default=5061)
    run.add_argument("--ui-host", default="0.0.0.0")
    run.add_argument("--ui-port", type=int, default=8088)
    run.add_argument("--output", type=Path, default=Path("/tmp/ims-sim-run"))

    args = parser.parse_args()
    if args.command == "issue-certs":
        extra = tuple(item.strip() for item in args.dns.split(",") if item.strip())
        material = generate_test_material(args.out, extra)
        print(material.ca_certificate)
        return
    if args.command == "run":
        bind = os.environ.get("POD_IP", "127.0.0.1")
        run_role(
            role=args.role,
            advertise=args.advertise or bind,
            bind=bind,
            next_host=args.next_host,
            allow_peer_host=args.allow_peer_host,
            udp_port=args.udp_port,
            tls_port=args.tls_port,
            ui_host=args.ui_host,
            ui_port=args.ui_port,
            output_dir=args.output,
        )
        return
    directory = Path(tempfile.mkdtemp(prefix="ims-sim-ca-"))
    platform = start_local_platform(host=args.host, tls_directory=directory)
    try:
        print(f"S-CSCF udp {platform.port('scscf', 'udp')}")
        print(f"S-CSCF tcp {platform.port('scscf', 'tcp')}")
        print(f"S-CSCF tls {platform.port('scscf', 'tls')}")
        print("非运营商 PKI")
        print(f"ui http://{args.ui_host}:{args.ui_port}")
        serve_ui(platform, args.ui_host, args.ui_port, args.output)
    finally:
        platform.close()


if __name__ == "__main__":
    main()
