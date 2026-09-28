"""The process shell: termination requests and draining.

One use case is one process, and the process holds no state (ADR-0002), so
draining needs no state migration: stop accepting new requests, wait for
``active_calls`` to reach zero, then exit. The grace window is bounded — a
process that never drains must still exit, which is why the wait returns
``False`` on timeout (ADR-0009, skeleton).

The clock, the sleep and the active-call counter are all injected, so draining
is tested without a real signal, a real call or a real second of waiting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ShellConfig:
    """Deployment-side parameters of the shell.

    Attributes:
        drain_timeout_seconds: How long to wait for in-flight calls before
            forcing an exit.
        poll_interval_seconds: How long to sleep between two checks of
            ``active_calls``.
    """

    drain_timeout_seconds: float
    poll_interval_seconds: float = 0.05


class ProcessShell:
    """The lifecycle of one AS process.

    Attributes:
        config: The shell parameters.
    """

    def __init__(
        self,
        config: ShellConfig,
        active_calls: Callable[[], int],
        sleep: Callable[[float], None],
        now: Callable[[], float],
    ) -> None:
        """Create a shell over the injected collaborators.

        Args:
            config: The shell parameters.
            active_calls: Returns the number of in-flight calls.
            sleep: Sleeps for the given number of seconds.
            now: The injected clock, returning seconds.
        """
        self.config = config
        self._active_calls = active_calls
        self._sleep = sleep
        self._now = now
        self._terminating = False

    def request_terminate(self) -> None:
        """Record that SIGTERM/SIGINT arrived; new requests are refused."""
        self._terminating = True

    def accepts_new_requests(self) -> bool:
        """Whether the process still takes new work.

        Returns:
            ``True`` until termination has been requested.
        """
        return not self._terminating

    def run_until_drained(self) -> bool:
        """Wait for in-flight calls to finish, bounded by the drain timeout.

        Returns:
            ``True`` when ``active_calls`` reached zero, ``False`` when the
            grace window elapsed and the exit was forced.
        """
        deadline = self._now() + self.config.drain_timeout_seconds

        while self._active_calls() > 0:
            if self._now() >= deadline:
                # Force the exit: waiting forever would keep a Pod alive with
                # calls that will never finish. See ADR-0009.
                return False

            self._sleep(self.config.poll_interval_seconds)

        return True
