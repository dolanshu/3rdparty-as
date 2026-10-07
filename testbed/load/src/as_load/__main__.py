"""Command-line entry point for the real-socket SIP load harness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from as_load.harness import DEFAULT_TIMEOUT_SECONDS, LoadConfig, run_load
from as_load.scenarios import FIRST_EDITION


def main(argv: Sequence[str] | None = None) -> int:
    """Parse a reproducible load profile, execute it, and print a summary."""
    parser = argparse.ArgumentParser(description="Run a real-UDP SIP load measurement")
    parser.add_argument("--host", required=True, help="SIP endpoint host or IP")
    parser.add_argument("--port", required=True, type=int, help="SIP endpoint port")
    parser.add_argument(
        "--transport",
        choices=("udp", "tcp", "tls"),
        default="udp",
        help="transport used toward the simulated S-CSCF",
    )
    parser.add_argument(
        "--tls-ca",
        type=Path,
        default=None,
        help="PEM test CA for --transport tls; not an operator PKI",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        choices=tuple(item.scenario_id for item in FIRST_EDITION),
        help="first-edition call type; repeat to enable several",
    )
    parser.add_argument(
        "--cps", required=True, type=float, help="scheduled INVITE attempts per second"
    )
    parser.add_argument(
        "--duration", required=True, type=float, help="injection duration in seconds"
    )
    parser.add_argument(
        "--hold", type=float, default=10.0, help="hold each established call before BYE"
    )
    parser.add_argument(
        "--workers", type=int, default=256, help="maximum simultaneous call workers"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="per-transaction response timeout",
    )
    parser.add_argument("--stack", required=True, help="target SIP stack and build identity")
    parser.add_argument("--stack-version", required=True, help="target SIP stack version or commit")
    parser.add_argument(
        "--out", required=True, type=Path, help="directory for raw and derived evidence"
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=None,
        help="minimum established/attempted ratio (0..1); non-zero exit if below",
    )
    parser.add_argument(
        "--max-unresolved",
        type=int,
        default=None,
        help="maximum allowed unresolved attempts before non-zero exit",
    )
    args = parser.parse_args(argv)
    config = LoadConfig(
        host=args.host,
        port=args.port,
        target_cps=args.cps,
        duration_seconds=args.duration,
        hold_seconds=args.hold,
        workers=args.workers,
        timeout_seconds=args.timeout,
        stack_name=args.stack,
        stack_version=args.stack_version,
        output_dir=args.out,
        transport=args.transport,
        tls_ca_file=args.tls_ca,
        scenarios=tuple(args.scenario),
    )
    summary = run_load(config)
    counts = summary["counts"]
    attempted = int(counts.get("scheduled_attempts", 0))
    established = int(counts.get("established_sessions", 0))
    unresolved = int(counts.get("unresolved_sessions", 0))
    success_rate = (established / attempted) if attempted else 0.0
    counts["success_rate"] = success_rate
    print(json.dumps(counts, sort_keys=True))
    print(f"evidence: {args.out.resolve()}")
    if args.scenario:
        finals = sum(int(value) for value in summary.get("response_code_distribution", {}).values())
        sent = int(counts.get("invite_datagrams_sent", 0))
        if sent <= 0 or finals < sent:
            return 1
        return 0
    if established <= 0:
        return 1
    if args.min_success_rate is not None and success_rate < args.min_success_rate:
        return 2
    if args.max_unresolved is not None and unresolved > args.max_unresolved:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
