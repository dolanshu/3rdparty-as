#!/usr/bin/env python3
"""E1 probe: replay the M1 SIP baseline against the stack ADR-0019 selected.

ADR-0019 accepted E1 --- "S1-S11 behaviour has not been replayed on a real
socket" --- as an open gap, and consequence K2 keeps the SIP adapter in
``platform/`` closed until this probe passes. The probe therefore has to be
capable of failing, and it has to fail loudly when it cannot run at all.

What it does, per scenario:

1. Read the ``in-*`` messages of a scenario directory in
   ``testbed/contracts/sip-baseline/`` --- the messages that enter the AS.
2. Deliver them, in file order, to the AS the stack under probe plays.
3. Collect what the AS emits and compare it with the ``out-*`` messages of the
   same directory, using :func:`probe.sequence_compare.compare_sequence`.
4. Write what was captured to ``--out-dir/<scenario>/`` as evidence, print
   ``PASS`` / ``FAIL`` / ``NO_BASELINE``, and exit non-zero on any ``FAIL``.

The AS is spoken to over a real socket: the bytes in the baseline go on the
wire, and what comes back is what the stack produced. Nothing here mocks the
transport.

The stack itself is reached through the :class:`StackUnderProbe` seam. That
seam is **not** implemented in this repository --- the adapter that wraps the
reSIProcate Python bindings is a later step. Until then the probe stops at the
bindings gate with exit code 2, because comparing against some other stack
would validate the wrong thing and lift K2 on a false positive.

Exit codes:
    0  every scenario with a baseline matched.
    1  at least one scenario failed.
    2  the stack's Python bindings are missing; nothing was run.
    4  no scenario failed, but at least one had no baseline to compare against.
       This is a warning, not a failure: S5-S11 have no message files yet.
"""

from __future__ import annotations

import argparse
import importlib
import socket
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol, cast

from as_platform.sip.message import header, parse_message

# Running this file as a script puts ``testbed/probe`` on sys.path, not
# ``testbed``; the package the script belongs to lives one level up.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe import BINDING_GUIDANCE, BINDINGS_FACTORY, EXIT_BINDINGS_MISSING  # noqa: E402
from probe.sequence_compare import compare_sequence  # noqa: E402

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
BASELINE_ROOT: Final = REPOSITORY_ROOT / "testbed" / "contracts" / "sip-baseline"
DEFAULT_OUT_DIR: Final = REPOSITORY_ROOT / "testbed" / "probe" / "out"

#: Every scenario ADR-0019 §5 names as the E1 gate.
KNOWN_SCENARIOS: Final = (
    "S1",
    "S2",
    "S3",
    "S4",
    "S5",
    "S6",
    "S7a",
    "S7b",
    "S8",
    "S9",
    "S10",
    "S11",
)

#: The default run: the only scenarios that carry message files today. S5-S11
#: exist as directories with a README but no capture, so they report
#: ``NO_BASELINE`` and only show up when asked for explicitly.
DEFAULT_SCENARIOS: Final = ("S1", "S2", "S3", "S4")

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 5060

PASS: Final = "PASS"
FAIL: Final = "FAIL"
NO_BASELINE: Final = "NO_BASELINE"

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_NO_BASELINE: Final = 4

#: How long to wait for the AS to emit the next message before giving up on it.
READ_TIMEOUT_SECONDS: Final = 5.0
RECV_BYTES: Final = 65536

#: The empty line that ends the header section, one per accepted line break.
HEAD_BODY_SEPARATORS: Final = (b"\r\n\r\n", b"\n\n", b"\r\r")


class StackUnderProbe(Protocol):
    """The seam between this probe and the SIP stack under evaluation.

    One method is enough: the probe delivers a message and gets the next
    message the stack emits back. Everything else --- transactions, dialogs,
    retransmissions --- stays inside the stack, which is exactly what is being
    probed.
    """

    def send(self, payload: bytes) -> bytes | None:
        """Deliver one message and return the next message the stack emits.

        Args:
            payload: One complete SIP message, as it goes on the wire.

        Returns:
            The next message the stack emits, or ``None`` when it emits none
            before the probe stops waiting. A stack that emits bursts must
            buffer them and hand them out one per call, so that the comparison
            stays a one-to-one walk over the baseline.
        """
        ...


@dataclass(frozen=True)
class ScenarioBaseline:
    """The messages of one captured scenario.

    Attributes:
        name: The directory name of the capture, for example ``S1-basic-call``.
        inbound: The ``in-*`` messages --- what enters the AS --- in file order.
        outbound: The ``out-*`` messages --- what the AS must emit --- in file
            order.
    """

    name: str
    inbound: tuple[bytes, ...]
    outbound: tuple[bytes, ...]


@dataclass(frozen=True)
class ScenarioResult:
    """The outcome of one scenario.

    Attributes:
        scenario: The scenario id that was asked for (``S1``, ``S7a``, ...).
        status: ``PASS``, ``FAIL`` or ``NO_BASELINE``.
        detail: Why. Empty for ``PASS``; the differences for ``FAIL``; the
            reason there is nothing to compare for ``NO_BASELINE``.
    """

    scenario: str
    status: str
    detail: tuple[str, ...] = ()


class _SocketPeer:
    """The probe's own side of the conversation: a real socket.

    It connects to the AS under probe at a configured host and port and keeps
    the connection open for the whole scenario, so retransmissions and
    in-dialog messages of one call share one transport, the way they would in
    production.

    Framing follows RFC 3261 §20.14: a message ends once the body holds as
    many bytes as ``Content-Length`` declares. On a stream transport the peer
    cannot know a message ended any other way.
    """

    def __init__(self, host: str, port: int, timeout: float = READ_TIMEOUT_SECONDS) -> None:
        """Remember where the AS is; connect on the first message.

        Args:
            host: The host the AS listens on.
            port: The port the AS listens on.
            timeout: How long to wait for the AS to emit a message.
        """
        self._host = host
        self._port = port
        self._timeout = timeout
        self._connection: socket.socket | None = None

    def send(self, payload: bytes) -> bytes | None:
        """Write one message and read the next one the AS emits.

        Args:
            payload: One complete SIP message.

        Returns:
            The message the AS emitted, or ``None`` when it emitted none.

        Raises:
            OSError: If the AS cannot be reached. The caller turns this into a
                ``FAIL``: an unreachable AS is a failed probe, not a crash.
        """
        connection = self._connect()
        connection.sendall(payload)
        return self._read_one_message(connection)

    def close(self) -> None:
        """Close the connection to the AS if one was opened."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self) -> socket.socket:
        """Open the connection to the AS, once.

        Returns:
            The connected socket.
        """
        if self._connection is None:
            self._connection = socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            )
        return self._connection

    def _read_one_message(self, connection: socket.socket) -> bytes | None:
        """Read one complete SIP message from the socket.

        Args:
            connection: The connected socket.

        Returns:
            The message as it came off the wire, or ``None`` when the AS fell
            silent before a complete message arrived.
        """
        buffer = b""
        while True:
            try:
                chunk = connection.recv(RECV_BYTES)
            except TimeoutError:
                return buffer or None
            if not chunk:
                return buffer or None
            buffer += chunk
            if _carries_complete_message(buffer):
                return buffer


def _carries_complete_message(buffer: bytes) -> bool:
    """Tell whether a buffer already holds one complete SIP message.

    Args:
        buffer: What has been read from the socket so far.

    Returns:
        ``True`` once the header section has ended and the body holds at least
        as many bytes as ``Content-Length`` declares (RFC 3261 §20.14).
    """
    if not any(separator in buffer for separator in HEAD_BODY_SEPARATORS):
        return False
    try:
        message = parse_message(buffer)
    except ValueError:
        return False
    declared = header(message, "Content-Length")
    if declared is None:
        return True
    try:
        return len(message.body) >= int(declared)
    except ValueError:
        return True


def _load_bindings(module_name: str) -> ModuleType:
    """Import the Python bindings of the stack ADR-0019 selected.

    Args:
        module_name: The module to import, for example ``resip``.

    Returns:
        The imported module.

    Raises:
        SystemExit: With :data:`probe.EXIT_BINDINGS_MISSING` when the module
            cannot be imported. This is the point of the probe: a missing
            binding is a failed run, never a skipped one.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        print(
            f"probe aborted: Python bindings {module_name!r} are not importable ({error})",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print(BINDING_GUIDANCE, file=sys.stderr)
        sys.exit(EXIT_BINDINGS_MISSING)


def _open_stack(bindings: ModuleType, host: str, port: int) -> StackUnderProbe:
    """Obtain the stack handle the probe will drive.

    A bindings module may expose :data:`probe.BINDINGS_FACTORY`; that is the
    adapter the reSIProcate bindings are expected to grow, and it is **not**
    implemented in this repository. When it is absent the probe falls back to
    its own socket peer, which speaks to an AS that is already listening on
    ``host:port`` --- still a real socket, just not a stack this repository
    started.

    Args:
        bindings: The imported bindings module.
        host: The host the AS listens on.
        port: The port the AS listens on.

    Returns:
        An object satisfying :class:`StackUnderProbe`.
    """
    factory = getattr(bindings, BINDINGS_FACTORY, None)
    if factory is not None:
        print(f"stack under probe: {bindings.__name__}.{BINDINGS_FACTORY}({host}:{port})")
        return cast(StackUnderProbe, factory(host=host, port=port))
    print(
        f"stack under probe: socket peer at {host}:{port} "
        f"({bindings.__name__} exposes no {BINDINGS_FACTORY!r})"
    )
    return _SocketPeer(host, port)


def _scenario_directory(scenario: str) -> Path | None:
    """Find the capture directory of a scenario.

    Args:
        scenario: The scenario id, for example ``S1`` or ``S7a``.

    Returns:
        The directory, or ``None`` when the scenario has no directory at all.
    """
    matches = sorted(path for path in BASELINE_ROOT.glob(f"{scenario}-*") if path.is_dir())
    return matches[0] if matches else None


def _load_scenario(scenario: str) -> ScenarioBaseline | None:
    """Read the messages of one captured scenario.

    Args:
        scenario: The scenario id.

    Returns:
        The baseline, or ``None`` when the scenario has no directory or no
        message files --- the ``NO_BASELINE`` case, which must never be
        reported as a pass.
    """
    directory = _scenario_directory(scenario)
    if directory is None:
        return None

    # The files are numbered (``01-in-invite-trunk.txt``), so the file name
    # order is the wire order of the capture.
    inbound = tuple(path.read_bytes() for path in sorted(directory.glob("*-in-*.txt")))
    outbound = tuple(path.read_bytes() for path in sorted(directory.glob("*-out-*.txt")))
    if not inbound and not outbound:
        return None
    return ScenarioBaseline(name=directory.name, inbound=inbound, outbound=outbound)


def _run_scenario(stack: StackUnderProbe, scenario: str, out_dir: Path) -> ScenarioResult:
    """Replay one scenario against the stack under probe.

    Args:
        stack: The stack handle, over a real socket.
        scenario: The scenario id.
        out_dir: Where the captured messages are written as evidence.

    Returns:
        The outcome. A scenario with no baseline reports ``NO_BASELINE``; one
        whose AS cannot be reached reports ``FAIL`` with the reason.
    """
    baseline = _load_scenario(scenario)
    if baseline is None:
        return ScenarioResult(
            scenario=scenario,
            status=NO_BASELINE,
            detail=(f"no captured messages under {BASELINE_ROOT}/{scenario}-*",),
        )

    captured: list[bytes] = []
    try:
        for payload in baseline.inbound:
            emitted = stack.send(payload)
            if emitted is not None:
                captured.append(emitted)
    except OSError as error:
        _write_evidence(out_dir, baseline.name, captured)
        return ScenarioResult(
            scenario=scenario,
            status=FAIL,
            detail=(f"the AS under probe could not be driven: {error}",),
        )

    _write_evidence(out_dir, baseline.name, captured)
    matched, differences = compare_sequence(captured, baseline.outbound)
    if matched:
        return ScenarioResult(
            scenario=scenario,
            status=PASS,
            detail=(f"{len(baseline.outbound)} messages compared, all matched",),
        )
    return ScenarioResult(scenario=scenario, status=FAIL, detail=differences)


def _write_evidence(out_dir: Path, scenario: str, captured: Sequence[bytes]) -> None:
    """Write what the stack emitted, so the verdict can be re-derived.

    Args:
        out_dir: Where evidence goes.
        scenario: The capture directory name, used as the sub-directory.
        captured: The messages the stack emitted, in order.
    """
    target = out_dir / scenario
    target.mkdir(parents=True, exist_ok=True)
    for number, raw in enumerate(captured, start=1):
        (target / f"{number:02d}-actual.bin").write_bytes(raw)


def _report(result: ScenarioResult) -> None:
    """Print one scenario's outcome and, for a failure, every difference.

    Args:
        result: The outcome to print.
    """
    print(f"{result.scenario}: {result.status}")
    for line in result.detail:
        print(f"    {line}")


def _exit_code(results: Sequence[ScenarioResult]) -> int:
    """Fold the outcomes into a process exit code.

    Args:
        results: The outcomes of every scenario that ran.

    Returns:
        0 when everything matched, 1 when anything failed, plus 4 when
        something had no baseline to compare against. The 4 is a warning bit:
        it never turns a passing run into a failed one, but it keeps "nothing
        was compared" from looking like success.
    """
    code = EXIT_OK
    if any(result.status == FAIL for result in results):
        code |= EXIT_FAILED
    if any(result.status == NO_BASELINE for result in results):
        code |= EXIT_NO_BASELINE
    return code


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Read the command line.

    Args:
        argv: The arguments, or ``None`` to read ``sys.argv``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="e1_baseline_probe.py",
        description=(
            "Replay the M1 SIP baseline against the stack ADR-0019 selected. "
            "Fails loudly (exit code 2) when the stack's Python bindings are missing."
        ),
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=list(KNOWN_SCENARIOS),
        metavar="ID",
        help=(
            "Scenario to replay; repeatable. Default: "
            f"{', '.join(DEFAULT_SCENARIOS)} (the only ones with message files)."
        ),
    )
    parser.add_argument(
        "--bindings-module",
        default="resip",
        help="Python module of the stack under probe (default: resip).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Where captured messages are written (default: {DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host the AS under probe listens on (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port the AS under probe listens on (default: {DEFAULT_PORT}).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the E1 probe.

    Args:
        argv: The arguments, or ``None`` to read ``sys.argv``.

    Returns:
        The process exit code; see the module docstring.
    """
    args = _parse_args(argv)
    scenarios = args.scenario or list(DEFAULT_SCENARIOS)

    # The bindings gate comes first and is unconditional: without the selected
    # stack there is nothing whose behaviour this run could be evidence about.
    bindings = _load_bindings(args.bindings_module)
    stack = _open_stack(bindings, args.host, args.port)

    print(f"baseline: {BASELINE_ROOT}")
    print(f"evidence: {args.out_dir}")
    print(f"scenarios: {', '.join(scenarios)}")
    print()

    results = [_run_scenario(stack, scenario, args.out_dir) for scenario in scenarios]
    for result in results:
        _report(result)

    close = getattr(stack, "close", None)
    if callable(close):
        close()

    code = _exit_code(results)
    print()
    print(f"exit code: {code} (0 = all matched, 1 = a scenario failed, 4 = no baseline)")
    if not any(result.status == PASS for result in results):
        print("no scenario was verified: E1 stays an open gap in ADR-0019")
    return code


if __name__ == "__main__":
    sys.exit(main())
