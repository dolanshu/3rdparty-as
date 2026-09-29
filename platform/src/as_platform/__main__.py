"""Executable entry point for the deployable AS process shell."""

from __future__ import annotations

import argparse
import logging
import signal
import time
from collections.abc import Callable, Sequence
from types import FrameType

from as_platform.shell import ProcessShell, ShellConfig

_DEFAULT_DRAIN_TIMEOUT_SECONDS = 300.0
_DRAIN_TIMEOUT_EXIT_CODE = 1
_RUNTIME_ERROR_EXIT_CODE = 2


def build_shell(
    config: ShellConfig,
    active_calls: Callable[[], int],
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> ProcessShell:
    """Assemble the process shell from explicitly injected collaborators.

    Args:
        config: Draining and polling parameters.
        active_calls: Returns the current number of in-flight calls.
        sleep: Suspends draining between active-call checks.
        now: Returns monotonic seconds for the drain deadline.

    Returns:
        A shell that initially accepts new requests.
    """
    return ProcessShell(config=config, active_calls=active_calls, sleep=sleep, now=now)


def _parse_config(argv: Sequence[str] | None) -> ShellConfig:
    """Parse process-shell configuration from command-line arguments."""
    parser = argparse.ArgumentParser(description="Run the AS process shell.")
    parser.add_argument(
        "--drain-timeout-seconds",
        type=float,
        default=_DEFAULT_DRAIN_TIMEOUT_SECONDS,
        help="maximum time to wait for in-flight calls during termination",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=ShellConfig.poll_interval_seconds,
        help="delay between active-call checks while draining",
    )
    arguments = parser.parse_args(argv)
    return ShellConfig(
        drain_timeout_seconds=arguments.drain_timeout_seconds,
        poll_interval_seconds=arguments.poll_interval_seconds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the signal-aware process shell until termination.

    Exit code ``0`` means draining completed normally. A non-zero exit code means
    that draining timed out or the runtime raised an exception.

    Args:
        argv: Optional command-line arguments. ``None`` reads the process command
            line through :mod:`argparse`.

    Returns:
        ``0`` after a clean drain, ``1`` after a drain timeout, or ``2`` after a
        runtime exception.
    """
    config = _parse_config(argv)
    shell = build_shell(
        config=config,
        active_calls=lambda: 0,
        sleep=time.sleep,
        now=time.monotonic,
    )

    def request_terminate(_signum: int, _frame: FrameType | None) -> None:
        # Refuse new work before draining existing calls. See ADR-0009.
        shell.request_terminate()

    termination_signals = (signal.SIGTERM, signal.SIGINT)
    previous_handlers = {signum: signal.getsignal(signum) for signum in termination_signals}

    try:
        for signum in termination_signals:
            signal.signal(signum, request_terminate)

        while shell.accepts_new_requests():
            signal.pause()

        # Process state is external, so termination only drains calls. See ADR-0002.
        return 0 if shell.run_until_drained() else _DRAIN_TIMEOUT_EXIT_CODE
    except Exception:
        logging.exception("The AS process shell failed")
        return _RUNTIME_ERROR_EXIT_CODE
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
