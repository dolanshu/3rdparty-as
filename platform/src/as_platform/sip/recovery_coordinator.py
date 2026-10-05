"""Non-blocking Redis checkpoint restore outside SIP callbacks (M7.2 / D10).

SIP stack callbacks must never block on Redis I/O. This coordinator posts
repository loads to a worker thread and delivers results via ``on_restored``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from as_platform.sip.recovery import CallStateRecovery, ProcessStartRestoreResult


@dataclass(frozen=True, slots=True)
class ScheduledRestoreHandle:
    """Opaque handle for a posted restore job (tests may inspect ``done``)."""

    done: bool = False


class RecoveryCoordinator:
    """Thread-pool backed continuation for post-restart checkpoint loads."""

    def __init__(
        self,
        recovery: CallStateRecovery,
        *,
        max_workers: int = 2,
    ) -> None:
        """Attach a :class:`CallStateRecovery` loader and a small worker pool."""
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._recovery = recovery
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="as-recovery"
        )

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting new jobs and optionally wait for workers."""
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def schedule_restore(
        self,
        case: str,
        call_keys: tuple[str, ...],
        on_restored: Callable[[ProcessStartRestoreResult], None],
    ) -> ScheduledRestoreHandle:
        """Post ``call_keys`` restore work; invoke ``on_restored`` on a worker thread.

        Never call this from a path that already holds the SIP stack callback lock
        if ``on_restored`` would recurse into Redis — callers should only schedule
        here and handle results asynchronously.
        """
        handle = ScheduledRestoreHandle()

        def _run() -> None:
            result = self._recovery.on_process_start_restore(case=case, call_keys=call_keys)
            on_restored(result)

        self._executor.submit(_run)
        return handle
