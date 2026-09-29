#!/usr/bin/env python3
"""E4 probe: certificate hot rotation must not restart the process or drop calls.

ADR-0019 §5.2 defines S12 for this, and §3.1 makes it hard constraint H4: the
stack must support SIP over TLS with a certificate rotation that needs no
restart and loses no call in flight. The C++ probe under
``testbed/simulators/resip-probe/`` already recorded the suspicion --- reSIProcate
loads the certificate into the OpenSSL context at ``addTransport`` time and
exposes no reload --- but a suspicion is not a verdict, and K8 keeps this as a
known shortcoming until something has actually been run.

The probe asserts four things, in this order, against one stack handle:

1. A call is established over TLS and stays in-dialog.
2. The certificate is rotated while that call is in flight.
3. The call still completes: the ``BYE`` is answered with a 2xx.
4. The process did not restart: the stack handle's identity is unchanged.

Every assertion is reported separately. One failing assertion fails the probe;
a probe that could not run at all is not a passing probe.

The stack is reached through the :class:`TlsStackUnderProbe` seam, which is
**not** implemented in this repository: the adapter wrapping the reSIProcate
Python bindings is a later step. Until then the probe stops at the bindings
gate with exit code 2.

Exit codes:
    0  every assertion held.
    1  at least one assertion failed.
    2  the stack's Python bindings are missing; nothing was run.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol, cast

from as_platform.sip.message import parse_message, status_code

# Running this file as a script puts ``testbed/probe`` on sys.path, not
# ``testbed``; the package the script belongs to lives one level up.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe import BINDING_GUIDANCE, BINDINGS_FACTORY, EXIT_BINDINGS_MISSING  # noqa: E402

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR: Final = REPOSITORY_ROOT / "testbed" / "probe" / "out"

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 5061
DEFAULT_CERTIFICATE: Final = DEFAULT_OUT_DIR / "tls" / "cert.pem"
DEFAULT_PRIVATE_KEY: Final = DEFAULT_OUT_DIR / "tls" / "key.pem"

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1


class TlsStackUnderProbe(Protocol):
    """The seam between this probe and a stack that speaks SIP over TLS.

    The four methods are exactly the four things S12 asserts, so an adapter has
    nothing to invent: establish a call, rotate the certificate under it, hang
    up, and prove the process is the same one that started.
    """

    def establish_call(self) -> str:
        """Bring up a call over TLS and leave it in-dialog.

        Returns:
            An identifier of the established dialog, non-empty. The probe uses
            it to hang up the same call after the rotation, never a new one.

        Raises:
            Anything the stack raises when it cannot bring the call up. The
            probe catches it and turns it into a failed assertion, because a
            traceback is not a verdict on E4.
        """
        ...

    def rotate_certificate(self, certificate: Path, private_key: Path) -> None:
        """Swap the TLS certificate in a running process.

        Args:
            certificate: The new certificate chain.
            private_key: The new private key.

        Raises:
            OSError: If the files cannot be read. Anything else the stack
                raises is reported as a failed assertion rather than hidden.
        """
        ...

    def hang_up(self, call_id: str) -> bytes:
        """End a call that is in flight.

        Args:
            call_id: The identifier :meth:`establish_call` returned.

        Returns:
            The final response the stack received to its ``BYE``, as it came
            off the wire.

        Raises:
            Anything the stack raises when the call is already gone. That is
            precisely the failure S12 is looking for, so it is reported rather
            than propagated.
        """
        ...

    def process_identity(self) -> str:
        """Identify the running stack instance.

        Returns:
            A value that is stable for the lifetime of the process and changes
            when the process restarts --- a pid, or a start-time token. This is
            what distinguishes a hot rotation from a restart that happens to
            re-establish everything.
        """
        ...


@dataclass(frozen=True)
class Assertion:
    """One thing S12 requires, and whether it held.

    Attributes:
        name: What was asserted.
        held: Whether it held.
        detail: Why, or what was observed. Never empty: an assertion without a
            reason cannot be reviewed.
    """

    name: str
    held: bool
    detail: str


def _load_bindings(module_name: str) -> ModuleType:
    """Import the Python bindings of the stack ADR-0019 selected.

    Args:
        module_name: The module to import, for example ``resip``.

    Returns:
        The imported module.

    Raises:
        SystemExit: With :data:`probe.EXIT_BINDINGS_MISSING` when the module
            cannot be imported. E4 stays an open gap instead of being silently
            skipped.
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


def _open_stack(bindings: ModuleType, host: str, port: int) -> TlsStackUnderProbe:
    """Obtain the TLS stack handle the probe will drive.

    A bindings module may expose :data:`probe.BINDINGS_FACTORY`; that is the
    adapter the reSIProcate bindings are expected to grow, and it is **not**
    implemented in this repository.

    Args:
        bindings: The imported bindings module.
        host: The host the TLS listener binds to.
        port: The port the TLS listener binds to.

    Returns:
        An object satisfying :class:`TlsStackUnderProbe`.

    Raises:
        SystemExit: With :data:`probe.EXIT_BINDINGS_MISSING` when the module
            offers no way to build a stack handle. Without one there is no
            rotation to observe.
    """
    factory = getattr(bindings, BINDINGS_FACTORY, None)
    if factory is None:
        print(
            f"probe aborted: {bindings.__name__} exposes no {BINDINGS_FACTORY!r}, "
            "so no stack handle can be built",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print(BINDING_GUIDANCE, file=sys.stderr)
        sys.exit(EXIT_BINDINGS_MISSING)
    return cast(TlsStackUnderProbe, factory(host=host, port=port))


def _run(stack: TlsStackUnderProbe, certificate: Path, private_key: Path) -> list[Assertion]:
    """Walk through S12 and collect what held.

    Args:
        stack: The stack handle.
        certificate: The certificate to rotate to.
        private_key: The private key to rotate to.

    Returns:
        One :class:`Assertion` per requirement, in the order they were checked.
        The walk continues past a failure where it safely can, so one run
        reports everything that is wrong instead of only the first thing.
    """
    assertions: list[Assertion] = []

    identity_before = stack.process_identity()
    assertions.append(
        Assertion(
            name="the stack under probe is running",
            held=bool(identity_before),
            detail=f"process identity {identity_before!r}",
        )
    )

    try:
        call_id = stack.establish_call()
    except Exception as error:  # the stack raised; report it, do not hide it
        call_id = ""
        established = Assertion(
            name="a call is established over TLS and stays in-dialog",
            held=False,
            detail=f"establish_call() raised {type(error).__name__}: {error}",
        )
        assertions.append(established)
        assertions.append(
            Assertion(
                name="the certificate is rotated while the call is in flight",
                held=False,
                detail="not attempted: no call was established",
            )
        )
        assertions.append(
            Assertion(
                name="the in-flight call still completes (BYE answered 2xx)",
                held=False,
                detail="not attempted: no call was established",
            )
        )
        assertions.append(
            Assertion(
                name="the process was not restarted",
                held=False,
                detail="not attempted: no call was established",
            )
        )
        return assertions

    assertions.append(
        Assertion(
            name="a call is established over TLS and stays in-dialog",
            held=bool(call_id),
            detail=f"dialog {call_id!r}" if call_id else "establish_call() returned no dialog",
        )
    )

    try:
        stack.rotate_certificate(certificate, private_key)
        rotation_held = True
        rotation_detail = f"rotated to {certificate}"
    except Exception as error:  # the stack raised; report it, do not hide it
        rotation_held = False
        rotation_detail = f"rotate_certificate() raised {type(error).__name__}: {error}"
    assertions.append(
        Assertion(
            name="the certificate is rotated while the call is in flight",
            held=rotation_held,
            detail=rotation_detail,
        )
    )

    try:
        response = stack.hang_up(call_id)
        hangup_error = ""
    except Exception as error:  # the stack raised; report it, do not hide it
        response = b""
        hangup_error = f"hang_up() raised {type(error).__name__}: {error}"

    status = _status_code(response)
    if hangup_error:
        assertions.append(
            Assertion(
                name="the in-flight call still completes (BYE answered 2xx)",
                held=False,
                detail=hangup_error,
            )
        )
    else:
        assertions.append(
            Assertion(
                name="the in-flight call still completes (BYE answered 2xx)",
                held=status is not None and 200 <= status < 300,
                detail=f"final response {status!r}" if status is not None else "no response",
            )
        )

    identity_after = stack.process_identity()
    assertions.append(
        Assertion(
            name="the process was not restarted",
            held=bool(identity_before) and identity_after == identity_before,
            detail=f"identity {identity_before!r} -> {identity_after!r}",
        )
    )
    return assertions


def _status_code(raw: bytes) -> int | None:
    """Read the status code of a response with the kernel parser.

    Args:
        raw: The response as it came off the wire.

    Returns:
        The status code, or ``None`` when the bytes carry none --- a request,
        or something that is not a SIP message at all.
    """
    if not raw:
        return None
    try:
        return status_code(parse_message(raw))
    except ValueError:
        return None


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Read the command line.

    Args:
        argv: The arguments, or ``None`` to read ``sys.argv``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="tls_hot_rotation_probe.py",
        description=(
            "Verify S12 (ADR-0019 §5.2, hard constraint H4): a TLS certificate "
            "rotation must not restart the process and must not drop a call in "
            "flight. Fails loudly (exit code 2) when the stack's Python "
            "bindings are missing."
        ),
    )
    parser.add_argument(
        "--bindings-module",
        default="resip",
        help="Python module of the stack under probe (default: resip).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host the TLS listener binds to (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port the TLS listener binds to (default: {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--cert",
        type=Path,
        default=DEFAULT_CERTIFICATE,
        help=f"Certificate to rotate to (default: {DEFAULT_CERTIFICATE}).",
    )
    parser.add_argument(
        "--key",
        type=Path,
        default=DEFAULT_PRIVATE_KEY,
        help=f"Private key to rotate to (default: {DEFAULT_PRIVATE_KEY}).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the E4 / S12 probe.

    Args:
        argv: The arguments, or ``None`` to read ``sys.argv``.

    Returns:
        The process exit code; see the module docstring.
    """
    args = _parse_args(argv)

    # The bindings gate comes first and is unconditional: without the selected
    # stack there is no rotation to observe.
    bindings = _load_bindings(args.bindings_module)
    stack = _open_stack(bindings, args.host, args.port)

    print("scenario: S12 TLS certificate hot rotation (ADR-0019 §5.2, H4)")
    print(f"stack under probe: {bindings.__name__}")
    print(f"listener: {args.host}:{args.port}")
    print(f"certificate: {args.cert}")
    print()

    assertions = _run(stack, args.cert, args.key)
    for assertion in assertions:
        print(f"[{'PASS' if assertion.held else 'FAIL'}] {assertion.name}")
        print(f"       {assertion.detail}")

    failed = [assertion for assertion in assertions if not assertion.held]
    print()
    if failed:
        print(f"S12: FAIL ({len(failed)} of {len(assertions)} assertions failed)")
        print("E4 stays an open gap in ADR-0019")
        return EXIT_FAILED

    print(f"S12: PASS ({len(assertions)} assertions held)")
    print("evidence belongs in docs/acceptance/report.md")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
